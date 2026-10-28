"""AI Studio web uygulamasının (src/services/apiClient.ts) beklediği uçlar → mevcut servis modülleri.

Bu modül yalnızca biçim çevirir; iş mantığı `review.py`, `analysis/` ve tablolardadır. Rotalar `{base}/api/...`
altındadır ve diğer API uçları gibi jeton ister:
    GET   rules?status=&doc_code=&rule_type=&limit=   kurallar (RuleItem[]); status yoksa tüm durumlar
    POST  rules/{id}/approve | rules/{id}/reject      review.review_rule (ONAYLA / REDDET)
    PATCH rules/{id}                                   review.review_rule (DUZELT); alıntı düzenlenemez
    GET   findings?status=&severity=&finding_type=&limit=   bulgular (FindingItem[])
    PATCH findings/{id}                                bulgu durumu
    POST  analysis/run                                 deterministik kontroller (LLM yok)
    GET   decisions?process_code=                      karar envanteri (DecisionItem[])
    GET   entities/resolutions?status=                 rol/birim varlıkları ve yazım varyantları

Yazma uçları yalnız KYS_WRITABLE=1 iken yazar, kapalıyken 409 SALT_OKUNUR döner. Salt okunur sunucuda
`analysis/run` sonucu DB'ye değil bu süreç belleğine yazılır ve `findings` listesine eklenir (negatif id).
Arka ucu henüz olmayan uçlar (uygunluk, etki analizi, madde eşleştirme, içe aktarma, karar yazma) 501 döner.
"""

import json
import sqlite3
from collections import Counter
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import db, review
from ..analysis.checks import run_checks
from ..analysis.store import save_findings
from ..ontology import EntityType, FindingStatus, ReviewAction, Severity

# Arayüzdeki bulgu durumu adları; yalnız KABUL_EDILDI farklı yazılıyor.
_UI_FINDING_STATUS = {FindingStatus.KABUL_EDILDI.value: "KABUL"}
_DB_FINDING_STATUS = {v: k for k, v in _UI_FINDING_STATUS.items()}
UNVERIFIED_PREFIX = "[Doğrulanmamış kaynak] "


class RejectIn(BaseModel):
    reason: str | None = None


class FindingStatusIn(BaseModel):
    status: str
    resolution_notes: str | None = None


def _not_yet() -> JSONResponse:
    return JSONResponse(status_code=501, content={
        "detail": "Bu özellik sunucuda henüz yok.", "code": "HENUZ_YOK"})


def rule_item(r: dict) -> dict:
    """review.list_rules satırı → RuleItem."""
    threshold = None
    if r.get("threshold_value") is not None:
        threshold = {"value": r["threshold_value"], "unit": r.get("threshold_unit") or "",
                     "op": r.get("threshold_op") or ""}
    return {
        "id": r["id"],
        "rule_type": r["rule_type"],
        "subject": r.get("subject") or "",
        "action": r.get("action") or "",
        "object": r.get("object_text") or r.get("statement") or "",
        "statement": r.get("statement"),
        "condition": r.get("condition_text"),
        "threshold": threshold,
        "source": {"document": r["doc_code"], "revision": r.get("doc_revision"), "clause": r.get("clause_no"),
                   "quote": r["quote"]},
        "status": r["review_status"],
        "notes": r.get("review_note"),
        "updated_at": r.get("reviewed_at"),
    }


def rule_edits(body: dict) -> dict:
    """Partial<RuleItem> → review.EDITABLE_FIELDS. `source.quote` kanıttır, buraya hiç taşınmaz."""
    edits = {}
    for ui, col in (("rule_type", "rule_type"), ("statement", "statement"), ("condition", "condition_text"),
                    ("action", "action"), ("object", "object_text")):
        if ui in body:
            edits[col] = body[ui]
    th = body.get("threshold")
    if isinstance(th, dict):
        edits.update({"threshold_value": th.get("value"), "threshold_unit": th.get("unit"),
                      "threshold_op": th.get("op")})
    return edits


def finding_item(f: dict) -> dict:
    """findings satırı veya Finding.to_dict() → FindingItem. Onaysız kurala dayanan bulgu etiketlenir (değişmez 2)."""
    evidence = f["evidence"]
    if isinstance(evidence, str):
        evidence = json.loads(evidence or "[]")
    first = evidence[0] if evidence else {}
    description = (UNVERIFIED_PREFIX if f.get("unverified_basis") else "") + f["explanation"]
    if f.get("recommendation"):
        description += "\nÖneri: " + f["recommendation"]
    status = f.get("status") or FindingStatus.ACIK.value
    return {
        "id": f["id"],
        "finding_type": f["finding_type"],
        "severity": f["severity"],
        "status": _UI_FINDING_STATUS.get(status, status),
        "title": f["title"],
        "description": description,
        "document_code": first.get("doc_code"),
        "process_code": None,
        "rule_id": None,
        "evidence_quote": first.get("quote"),
        "evidence": evidence,
        "resolution_notes": f.get("status_note"),
        "created_at": f.get("created_at"),
        "fingerprint": f.get("fingerprint"),
    }


def list_findings(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM findings ORDER BY id DESC").fetchall()
    return [finding_item(dict(r)) for r in rows]


def list_decisions(conn: sqlite3.Connection, process_code: str | None = None) -> list[dict]:
    sql = """
        SELECT dc.id, dc.code, dc.title, dc.description, dc.condition_text, dc.threshold_op, dc.threshold_value,
               dc.threshold_unit, dc.basis_clause_no, dc.created_at,
               p.code AS process_code, e.canonical_name AS owner, d.code AS basis_doc
        FROM decisions dc
        LEFT JOIN processes p ON p.id = dc.process_id
        LEFT JOIN entities e ON e.id = dc.owner_entity_id
        LEFT JOIN documents d ON d.id = dc.basis_document_id
    """
    params: list = []
    if process_code:
        sql += " WHERE p.code = ?"
        params.append(process_code)
    sql += " ORDER BY dc.id"
    out = []
    for r in conn.execute(sql, params):
        limit = (f"{r['threshold_op']} {r['threshold_value']:g} {r['threshold_unit'] or ''}".strip()
                 if r["threshold_value"] is not None else None)
        out.append({
            "id": r["id"], "topic": r["title"], "process_code": r["process_code"] or "",
            "decision_maker": r["owner"] or "", "responsible": None, "consulted": None, "informed": None,
            "rule_id": None, "rule_summary": " — ".join(x for x in (r["condition_text"], limit) if x) or None,
            "source_document": r["basis_doc"], "source_clause": r["basis_clause_no"], "created_at": r["created_at"],
        })
    return out


def list_entities(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    sql = "SELECT id, entity_type, canonical_name, review_status FROM entities WHERE entity_type IN (?, ?)"
    params: list = [EntityType.ROL.value, EntityType.BIRIM.value]
    if status:
        sql += " AND review_status = ?"
        params.append(status)
    sql += " ORDER BY entity_type, canonical_name"
    rows = conn.execute(sql, params).fetchall()
    aliases: dict[int, list[str]] = {}
    for a in conn.execute("SELECT entity_id, alias FROM entity_aliases ORDER BY alias"):
        aliases.setdefault(a["entity_id"], []).append(a["alias"])
    return [{"id": r["id"], "canonical_name": r["canonical_name"], "entity_type": r["entity_type"],
             "aliases": aliases.get(r["id"], []), "status": r["review_status"]} for r in rows]


def add_routes(app: FastAPI, base: str, conn: Callable, guarded: list, db_path: Path, writable: bool,
               readonly_response: Callable[[], JSONResponse]) -> None:
    api = f"{base}/api"
    memory: dict = {"findings": []}   # salt okunur sunucuda son analiz sonucu

    def write_conn():
        if not db_path.exists():
            raise HTTPException(503, "Veritabanı henüz yüklenmedi")
        return closing(db.connect(db_path))

    def review_one(rule_id: int, action: ReviewAction, note: str | None = None, edits: dict | None = None):
        if not writable:
            return readonly_response()
        with write_conn() as c:
            try:
                return rule_item(review.review_rule(c, rule_id, action, note=note, edits=edits))
            except LookupError as e:
                raise HTTPException(404, str(e)) from e
            except ValueError as e:
                raise HTTPException(422, str(e)) from e

    @app.get(f"{api}/rules", dependencies=guarded)
    def rules(status: str | None = None, doc_code: str | None = None, rule_type: str | None = None,
              q: str | None = None, limit: int = 200, c: sqlite3.Connection = Depends(conn)):
        res = review.list_rules(c, status=status, doc_code=doc_code, rule_type=rule_type, q=q,
                                limit=min(max(limit, 1), 1000))
        return [rule_item(r) for r in res["kurallar"]]

    @app.post(f"{api}/rules/{{rule_id}}/approve", dependencies=guarded)
    def rule_approve(rule_id: int):
        return review_one(rule_id, ReviewAction.ONAYLA)

    @app.post(f"{api}/rules/{{rule_id}}/reject", dependencies=guarded)
    def rule_reject(rule_id: int, body: RejectIn):
        return review_one(rule_id, ReviewAction.REDDET, note=body.reason)

    @app.patch(f"{api}/rules/{{rule_id}}", dependencies=guarded)
    def rule_update(rule_id: int, body: dict):
        return review_one(rule_id, ReviewAction.DUZELT, note=body.get("notes"), edits=rule_edits(body))

    @app.get(f"{api}/findings", dependencies=guarded)
    def findings(status: str | None = None, severity: str | None = None, finding_type: str | None = None,
                 limit: int = 300, c: sqlite3.Connection = Depends(conn)):
        items = list_findings(c)
        known = {i["fingerprint"] for i in items}
        items += [i for i in memory["findings"] if i["fingerprint"] not in known]
        if status:
            items = [i for i in items if i["status"] == status]
        if severity:
            items = [i for i in items if i["severity"] == severity]
        if finding_type:
            items = [i for i in items if i["finding_type"] == finding_type]
        return items[:min(max(limit, 1), 1000)]

    @app.patch(f"{api}/findings/{{finding_id}}", dependencies=guarded)
    def finding_update(finding_id: int, body: FindingStatusIn):
        if not writable:
            return readonly_response()
        status = _DB_FINDING_STATUS.get(body.status, body.status)
        if status not in set(FindingStatus):
            raise HTTPException(422, f"Geçersiz durum: {body.status}")
        with write_conn() as c:
            cur = c.execute("UPDATE findings SET status = ?, status_note = ?, updated_at = datetime('now') "
                            "WHERE id = ?", (status, body.resolution_notes, finding_id))
            c.commit()
            if not cur.rowcount:
                raise HTTPException(404, f"Bulgu yok: {finding_id}")
            return finding_item(dict(c.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()))

    @app.post(f"{api}/analysis/run", dependencies=guarded)
    def analysis_run(c: sqlite3.Connection = Depends(conn)):
        if writable:
            with write_conn() as wc:
                saved = save_findings(wc, run_checks(wc))
                found = list_findings(wc)
            run_id = str(saved["run_id"])
        else:
            outcomes = run_checks(c)
            found = [finding_item({**f.to_dict(), "id": -(n + 1)})
                     for n, f in enumerate(f for o in outcomes.values() for f in o.findings)]
            memory["findings"] = found
            run_id = "bellek"
        counts = Counter(f["severity"] for f in found)
        return {"ok": True, "run_id": run_id, "findings_count": len(found),
                "critical_count": counts[Severity.KRITIK.value], "medium_count": counts[Severity.ORTA.value],
                "low_count": counts[Severity.DUSUK.value], "timestamp": datetime.now(UTC).isoformat()}

    @app.get(f"{api}/decisions", dependencies=guarded)
    def decisions_list(process_code: str | None = None, c: sqlite3.Connection = Depends(conn)):
        return list_decisions(c, process_code)

    @app.get(f"{api}/entities/resolutions", dependencies=guarded)
    def entities(status: str | None = None, c: sqlite3.Connection = Depends(conn)):
        return list_entities(c, status)

    # Arka ucu henüz olmayanlar: arayüz 404 yerine anlaşılır bir mesaj alsın.
    for method, path in (("POST", "decisions"), ("DELETE", "decisions/{decision_id}"),
                         ("POST", "decisions/import"), ("POST", "processes/import"),
                         ("POST", "processes/{code}/steps/{seq}/match-clauses"),
                         ("POST", "processes/{code}/steps/{seq}/link-clause"),
                         ("POST", "entities/resolutions/{entity_id}/approve"),
                         ("PATCH", "entities/resolutions/{entity_id}"),
                         ("POST", "compliance/check"), ("GET", "documents/{code}/impact")):
        app.add_api_route(f"{api}/{path}", _not_yet, methods=[method], dependencies=guarded,
                          include_in_schema=False)
