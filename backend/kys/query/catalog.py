"""Salt okunur katalog sorguları. REST API ve MCP araçları aynı fonksiyonları kullanır."""

import json
import sqlite3

from .. import db
from ..process import flow
from ..ingest.metadata import code_key, known_segments, looks_like_doc_code

MAX_DOC_CHARS = 60_000


def stats(conn: sqlite3.Connection) -> dict:
    by_type = {r[0]: r[1] for r in conn.execute(
        "SELECT doc_type, COUNT(*) FROM documents WHERE status = 'YURURLUKTE' GROUP BY doc_type")}
    return {
        "documents": sum(by_type.values()),
        "by_type": by_type,
        "sections": conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0],
        "unresolved_references": conn.execute(
            "SELECT COUNT(DISTINCT ref_code) FROM doc_references WHERE resolved_doc_id IS NULL").fetchone()[0],
        "last_update": conn.execute("SELECT MAX(created_at) FROM documents").fetchone()[0],
    }


def list_documents(conn: sqlite3.Connection, doc_type: str | None = None, include_cancelled: bool = False) -> list[dict]:
    sql = "SELECT code, revision, title, doc_type, status, revision_date, owner_unit, summary FROM documents WHERE 1=1"
    params: list = []
    if doc_type:
        sql += " AND doc_type = ?"
        params.append(doc_type.upper())
    if not include_cancelled:
        sql += " AND status = 'YURURLUKTE'"
    return [dict(r) for r in conn.execute(sql + " ORDER BY doc_type, code", params)]


def get_document(conn: sqlite3.Connection, code: str) -> dict | None:
    d = conn.execute("SELECT * FROM documents WHERE code_key = ? ORDER BY (status = 'YURURLUKTE') DESC, "
                     "created_at DESC LIMIT 1", (code_key(code),)).fetchone()
    if not d:
        return None
    sections, total = [], 0
    for s in conn.execute("SELECT id, clause_no, heading, heading_path, text FROM sections "
                          "WHERE document_id = ? ORDER BY ordinal", (d["id"],)):
        total += len(s["text"])
        if total > MAX_DOC_CHARS:
            sections.append({"heading": "[kısaltıldı: doküman çok uzun]", "text": ""})
            break
        sections.append(dict(s))
    refs = [dict(r) for r in conn.execute(
        """SELECT r.ref_code, t.code AS target_code, t.title AS target_title, t.status AS target_status
           FROM doc_references r LEFT JOIN documents t ON t.id = r.resolved_doc_id
           WHERE r.document_id = ? GROUP BY r.ref_code""", (d["id"],))]
    referenced_by = [dict(r) for r in conn.execute(
        """SELECT DISTINCT s.code, s.title FROM doc_references r JOIN documents s ON s.id = r.document_id
           WHERE r.resolved_doc_id = ?""", (d["id"],))]
    keys = ("code", "revision", "title", "doc_type", "status", "revision_date", "effective_date", "owner_unit",
            "summary")
    return {**{k: d[k] for k in keys}, "warnings": json.loads(d["parse_warnings"] or "[]"),
            "sections": sections, "references": refs, "referenced_by": referenced_by}


def search(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    from .retrieval import retrieve
    rows = db.search_sections(conn, query, limit=limit) or retrieve(conn, query, limit=limit)
    return [{"code": r["code"], "revision": r["revision"], "title": r["title"], "clause_no": r["clause_no"],
             "heading": r["heading"], "section_id": r["section_id"], "text": r["text"][:1200]} for r in rows]


def unresolved_references(conn: sqlite3.Connection) -> dict:
    segments = known_segments([r[0] for r in conn.execute(
        "SELECT code FROM documents WHERE code NOT LIKE 'KODSUZ%'")])
    rows = conn.execute(
        """SELECT r.ref_code, GROUP_CONCAT(DISTINCT d.code) AS sources FROM doc_references r
           JOIN documents d ON d.id = r.document_id WHERE r.resolved_doc_id IS NULL
           GROUP BY r.ref_code ORDER BY r.ref_code""").fetchall()
    return {
        "missing_documents": [{"code": r["ref_code"], "referenced_from": r["sources"].split(",")}
                              for r in rows if looks_like_doc_code(r["ref_code"], segments)],
        "probably_not_documents": [r["ref_code"] for r in rows if not looks_like_doc_code(r["ref_code"], segments)],
    }


def get_process_flow(conn: sqlite3.Connection, code: str, with_pages: bool = True) -> dict | None:
    """Süreç adımları + Mermaid metni. Orijinal PDF (veya önceden üretilmiş sayfa dizini) varsa adım başına sayfa no."""
    p = flow.get_process(conn, code)
    if not p:
        return None
    path, sha = p.pop("_file_path"), p.pop("_file_sha256")
    p["page_count"], p["is_pdf"] = None, (path or "").lower().endswith(".pdf")
    if with_pages and p["is_pdf"]:
        from . import pages
        p["page_count"] = pages.page_total(path, sha)
        for s, pg in zip(p["steps"], pages.step_pages(path, sha, [s["quote"] for s in p["steps"]])):
            s["page"] = pg
    return p
