"""Kural çıkarımı iş akışı: dışa aktar → (ajan/model JSON üretir) → kontrol et → içe aktar.

Dosyalar (varsayılan data/extract/):
    in/<kod>.md     ajanın okuyacağı doküman metni (madde numaralı) + kimlik başlığı
    out/<kod>.json  ajanın yazdığı DocExtraction
    schema.json     çıktı JSON şeması
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .. import config
from ..ingest.metadata import code_key
from ..ontology import EntityType, NodeKind, RelType, ReviewStatus, RuleType
from ..textnorm import fold, verify_quote
from .schema import DocExtraction

# Kural/süreç içeren tipler; formlar ve listeler sonraya bırakılır.
DEFAULT_TYPES = ("PROSEDUR", "PROSES_KARTI", "TALIMAT", "GOREV_TANIMI", "PLAN", "POLITIKA", "YETKI_MATRISI",
                 "EL_KITABI", "DIGER")


def work_dir() -> Path:
    return config.PROJECT_ROOT / "data" / "extract"


def file_stem(code: str) -> str:
    return re.sub(r"[^\w.\-]", "_", code)


def export(conn: sqlite3.Connection, out_dir: Path | None = None, types=DEFAULT_TYPES,
           only_missing: bool = True) -> list[Path]:
    out_dir = out_dir or work_dir()
    (out_dir / "in").mkdir(parents=True, exist_ok=True)
    (out_dir / "out").mkdir(parents=True, exist_ok=True)
    (out_dir / "schema.json").write_text(json.dumps(DocExtraction.model_json_schema(), ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    marks = ",".join("?" * len(types))
    docs = conn.execute(f"SELECT * FROM documents WHERE status = 'YURURLUKTE' AND doc_type IN ({marks}) "
                        "ORDER BY doc_type, code", list(types)).fetchall()
    written = []
    for d in docs:
        stem = file_stem(d["code"])
        if only_missing and (out_dir / "out" / f"{stem}.json").exists():
            continue
        lines = [
            f"<!-- document_id: {d['id']} -->",
            f"# {d['code']} Rev.{d['revision']} — {d['title']}",
            f"- Tip: {d['doc_type']}",
            f"- Orijinal dosya: {d['file_path']}",
            "",
            "## Üstbilgi",
            d["header_text"] or "(yok)",
            "",
            "## Metin (bölümler)",
        ]
        for s in conn.execute("SELECT clause_no, heading_path, text FROM sections WHERE document_id = ? "
                              "ORDER BY ordinal", (d["id"],)):
            lines.append(f"\n### [md. {s['clause_no'] or '-'}] {s['heading_path'] or ''}".rstrip())
            lines.append(s["text"])
        path = out_dir / "in" / f"{stem}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(path)
    return written


@dataclass
class CheckReport:
    document_code: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    bad_quotes: list[str] = field(default_factory=list)
    counts: dict = field(default_factory=dict)


def _doc_text(conn, document_id: int) -> str:
    d = conn.execute("SELECT header_text, body_text FROM documents WHERE id = ?", (document_id,)).fetchone()
    return f"{d['header_text'] or ''}\n{d['body_text']}" if d else ""


def check(conn: sqlite3.Connection, path: Path) -> tuple[DocExtraction | None, CheckReport]:
    """Şema ve alıntı kontrolü (veritabanına yazmaz). Ajan bitirmeden önce bunu çalıştırır."""
    try:
        ex = DocExtraction.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as e:  # pydantic ValidationError veya bozuk JSON
        return None, CheckReport(path.stem, False, errors=[f"Şema hatası: {e}"])
    text = _doc_text(conn, ex.document_id)
    if not text:
        return ex, CheckReport(ex.document_code, False, errors=[f"document_id {ex.document_id} bulunamadı"])
    report = CheckReport(ex.document_code, True)
    for kind, items in (("kural", ex.rules), ("atıf", ex.references)):
        for it in items:
            if not verify_quote(it.quote, text):
                report.bad_quotes.append(f"{kind}: {it.quote[:120]}")
    role_names = {fold(r.name) for r in ex.roles} | {fold(a) for r in ex.roles for a in r.aliases}
    for rule in ex.rules:
        if rule.subject and fold(rule.subject) not in role_names:
            report.errors.append(f"Kural öznesi roles listesinde yok: {rule.subject}")
    seqs = {s.seq for s in ex.steps}
    for s in ex.steps:
        for who in (s.responsible, s.approver):
            if who and fold(who) not in role_names:
                report.errors.append(f"Adım {s.seq} rolü roles listesinde yok: {who}")
        for n in s.next_steps:
            if n not in seqs:
                report.errors.append(f"Adım {s.seq} → {n}: böyle bir adım yok")
    report.counts = {"rol": len(ex.roles), "kural": len(ex.rules), "adim": len(ex.steps),
                     "atif": len(ex.references), "gozlem": len(ex.observations)}
    report.ok = not report.errors and not report.bad_quotes
    return ex, report


# --- İçe aktarma -----------------------------------------------------------

def resolve_entity(conn: sqlite3.Connection, etype: EntityType, name: str, aliases=(), create: bool = True) -> int | None:
    """Ad veya takma adla varlık bulur; yoksa ONERILDI olarak oluşturur. Takma adları ekler."""
    name = name.strip()
    norm = fold(name)
    row = conn.execute(
        """SELECT e.id FROM entities e LEFT JOIN entity_aliases a ON a.entity_id = e.id
           WHERE e.entity_type = ? AND (e.normalized_name = ? OR a.normalized_alias = ?) LIMIT 1""",
        (etype, norm, norm)).fetchone()
    if row:
        eid = row["id"]
    elif create:
        eid = conn.execute("INSERT INTO entities(entity_type, canonical_name, normalized_name) VALUES (?,?,?)",
                           (etype, name, norm)).lastrowid
    else:
        return None
    for a in (name, *aliases):
        if a and fold(a) != conn.execute("SELECT normalized_name FROM entities WHERE id = ?", (eid,)).fetchone()[0]:
            conn.execute("INSERT OR IGNORE INTO entity_aliases(entity_id, alias, normalized_alias) VALUES (?,?,?)",
                         (eid, a, fold(a)))
    return eid


def _section_for(conn, document_id: int, clause_no: str | None, quote: str) -> int | None:
    rows = conn.execute("SELECT id, clause_no, heading, text FROM sections WHERE document_id = ? ORDER BY ordinal",
                        (document_id,)).fetchall()
    for r in rows:  # önce alıntının geçtiği bölüm (en güvenilir)
        if verify_quote(quote, f"{r['heading'] or ''}\n{r['text']}"):
            return r["id"]
    for r in rows:
        if clause_no and r["clause_no"] == clause_no:
            return r["id"]
    return None


def _edge(conn, src_kind, src_id, rel, dst_kind, dst_id, document_id, section_id=None, quote=None):
    conn.execute(
        """INSERT OR IGNORE INTO edges(src_kind, src_id, rel_type, dst_kind, dst_id, document_id, section_id,
                                      quote, review_status) VALUES (?,?,?,?,?,?,?,?,?)""",
        (src_kind, src_id, rel, dst_kind, dst_id, document_id, section_id, quote, ReviewStatus.ONERILDI))


def _clear_previous(conn, document_id: int) -> None:
    """Aynı dokümanın önceki önerilerini siler (onaylanmış/düzeltilmiş olanlara dokunmaz)."""
    conn.execute("DELETE FROM edges WHERE document_id = ? AND review_status = 'ONERILDI'", (document_id,))
    conn.execute("DELETE FROM rules WHERE document_id = ? AND review_status = 'ONERILDI'", (document_id,))
    conn.execute("DELETE FROM processes WHERE document_id = ? AND source = 'DOKUMAN'", (document_id,))
    conn.execute("DELETE FROM extraction_runs WHERE document_id = ?", (document_id,))


def import_file(conn: sqlite3.Connection, path: Path, extractor: str = "ajan:claude-code") -> CheckReport:
    ex, report = check(conn, path)
    if ex is None or any(e.startswith("document_id") for e in report.errors):
        return report
    doc = conn.execute("SELECT id, code, title FROM documents WHERE id = ?", (ex.document_id,)).fetchone()
    text = _doc_text(conn, doc["id"])
    try:
        _clear_previous(conn, doc["id"])
        roles = {}
        for r in ex.roles:
            eid = resolve_entity(conn, EntityType.ROL, r.name, r.aliases)
            for n in (r.name, *r.aliases):
                roles[fold(n)] = eid

        def role_id(name):
            if not name:
                return None
            return roles.get(fold(name)) or resolve_entity(conn, EntityType.ROL, name)

        reviewed = {fold(q) for (q,) in conn.execute(
            "SELECT quote FROM rules WHERE document_id = ? AND review_status != 'ONERILDI'", (doc["id"],))}
        added = dropped = 0
        for rule in ex.rules:
            if not verify_quote(rule.quote, text):
                dropped += 1  # kanıtsız kural kaydedilmez (CLAUDE.md değişmez 1)
                continue
            if fold(rule.quote) in reviewed:
                continue  # kullanıcı zaten onayladı/düzeltti/reddetti; tekrar önerme
            sid = _section_for(conn, doc["id"], rule.clause_no, rule.quote)
            subj = role_id(rule.subject)
            rid = conn.execute(
                """INSERT INTO rules(document_id, section_id, clause_no, rule_type, statement, subject_entity_id,
                                     action, object_text, condition_text, threshold_op, threshold_value,
                                     threshold_unit, quote, extracted_by)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc["id"], sid, rule.clause_no, rule.rule_type, rule.statement, subj, rule.action, rule.object,
                 rule.condition, rule.threshold_op, rule.threshold_value, rule.threshold_unit, rule.quote,
                 extractor)).lastrowid
            if subj:
                rel = RelType.ONAYLAR if rule.rule_type in (RuleType.ONAY, RuleType.YETKI) else RelType.SORUMLUDUR
                _edge(conn, NodeKind.VARLIK, subj, rel, NodeKind.KURAL, rid, doc["id"], sid, rule.quote)
            added += 1

        if ex.steps:
            pid = conn.execute(
                "INSERT INTO processes(code, name, source, document_id) VALUES (?,?,'DOKUMAN',?)",
                (f"{doc['code']}", doc["title"], doc["id"])).lastrowid
            for s in ex.steps:
                resp, appr = role_id(s.responsible), role_id(s.approver)
                st = conn.execute(
                    """INSERT INTO process_steps(process_id, seq, name, description, responsible_entity_id,
                                                 approver_entity_id, duration_value, duration_unit, decision,
                                                 next_steps, inputs, outputs, system, quote)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid, s.seq, s.name, None, resp, appr, s.duration_value, s.duration_unit, s.decision,
                     json.dumps(s.next_steps), json.dumps(s.inputs, ensure_ascii=False),
                     json.dumps(s.outputs, ensure_ascii=False), s.system, s.quote)).lastrowid
                if resp:
                    _edge(conn, NodeKind.VARLIK, resp, RelType.YURUTUR, NodeKind.SUREC_ADIMI, st, doc["id"])
                if appr:
                    _edge(conn, NodeKind.VARLIK, appr, RelType.ONAYLAR, NodeKind.SUREC_ADIMI, st, doc["id"])

        refs = 0
        for ref in ex.references:
            if not verify_quote(ref.quote, text):
                dropped += 1
                continue
            sid = _section_for(conn, doc["id"], ref.clause_no, ref.quote)
            target = conn.execute("SELECT id FROM documents WHERE code_key = ? ORDER BY (status='YURURLUKTE') DESC "
                                  "LIMIT 1", (code_key(ref.target),)).fetchone()
            if target and target["id"] != doc["id"]:
                _edge(conn, NodeKind.DOKUMAN, doc["id"], ref.relation, NodeKind.DOKUMAN, target["id"], doc["id"],
                      sid, ref.quote)
            else:
                # Sistemde olmayan hedef: form/kayıt adı ya da (dayanak ise) standart/mevzuat maddesi
                etype = EntityType.STANDART_MADDESI if ref.relation == RelType.DAYANAGIDIR else EntityType.FORM
                eid = resolve_entity(conn, etype, ref.target)
                _edge(conn, NodeKind.DOKUMAN, doc["id"], ref.relation, NodeKind.VARLIK, eid, doc["id"], sid, ref.quote)
            refs += 1

        conn.execute(
            """INSERT INTO extraction_runs(document_id, extractor, source_file, n_rules, n_dropped, n_roles, n_steps,
                                           n_refs, observations) VALUES (?,?,?,?,?,?,?,?,?)""",
            (doc["id"], extractor, path.name, added, dropped, len(ex.roles), len(ex.steps), refs,
             json.dumps(ex.observations, ensure_ascii=False)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    report.counts.update({"eklenen_kural": added, "atilan": dropped})
    return report
