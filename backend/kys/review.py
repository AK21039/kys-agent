"""Onay Kuyruğu: önerilen (ONERILDI) kuralların listelenmesi, özetlenmesi ve incelenmesi.

Saf servis katmanı — bağlantıyı (sqlite3.Connection) çağıran verir, burada açılmaz/kapatılmaz.
Yazma fonksiyonları (`review_rule`, `review_bulk`) yazılabilir bir bağlantı ister; salt okunur
(`immutable=True`) bağlantıda çağrılırsa sqlite3 kendisi hata verir — API katmanı (KYS_WRITABLE)
bu fonksiyonlara hiç ulaşmadan 409 döner (bkz. api/app.py).
"""

import sqlite3
from datetime import UTC, datetime

from .ontology import DocStatus, ReviewAction, ReviewStatus, RuleType
from .textnorm import fold

MAX_BULK = 200

_ACTION_STATUS = {
    ReviewAction.ONAYLA: ReviewStatus.ONAYLANDI,
    ReviewAction.DUZELT: ReviewStatus.DUZELTILDI,
    ReviewAction.REDDET: ReviewStatus.REDDEDILDI,
}

# quote kanıt değişmezidir (CLAUDE.md değişmez 1): asla düzenlenemez.
EDITABLE_FIELDS = ("statement", "rule_type", "condition_text", "threshold_op", "threshold_value",
                   "threshold_unit", "action", "object_text")
_THRESHOLD_OPS = {">", ">=", "<", "<=", "="}

_ROW_SQL = """
    SELECT r.id, r.rule_type, r.statement, r.quote, r.clause_no, r.condition_text, r.threshold_op,
           r.threshold_value, r.threshold_unit, r.action, r.object_text, r.confidence, r.extracted_by,
           r.review_status, r.reviewed_by, r.reviewed_at, r.review_note,
           d.code AS doc_code, d.revision AS doc_revision, d.title AS doc_title, d.status AS doc_status,
           e.canonical_name AS subject
    FROM rules r
    JOIN documents d ON d.id = r.document_id
    LEFT JOIN entities e ON e.id = r.subject_entity_id
    WHERE r.id = ?
"""


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _get_row(conn: sqlite3.Connection, rule_id: int) -> dict:
    row = conn.execute(_ROW_SQL, (rule_id,)).fetchone()
    if not row:
        raise LookupError(f"Kural yok: {rule_id}")
    return _row_to_dict(row)


def list_rules(conn: sqlite3.Connection, status: str | None = ReviewStatus.ONERILDI, doc_code: str | None = None,
              rule_type: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0,
              include_cancelled: bool = False) -> dict:
    """Kural listesi (doküman/madde/kural alanları + inceleme alanları) ve toplam sayı.

    `status=None` tüm durumları getirir. Doküman varsayılan olarak yalnız YURURLUKTE olanlardır
    (`include_cancelled=True` ile tümü). `q` Türkçe'ye duyarsız alt dizge araması yapar
    (statement/quote/condition_text/object_text/doküman kodu+başlığı üzerinde).
    """
    sql = """
        SELECT r.id, r.rule_type, r.statement, r.quote, r.clause_no, r.condition_text, r.threshold_op,
               r.threshold_value, r.threshold_unit, r.action, r.object_text, r.confidence, r.extracted_by,
               r.review_status, r.reviewed_by, r.reviewed_at, r.review_note,
               d.code AS doc_code, d.revision AS doc_revision, d.title AS doc_title, d.status AS doc_status,
               e.canonical_name AS subject
        FROM rules r
        JOIN documents d ON d.id = r.document_id
        LEFT JOIN entities e ON e.id = r.subject_entity_id
        WHERE 1=1
    """
    params: list = []
    if status:
        sql += " AND r.review_status = ?"
        params.append(status)
    if not include_cancelled:
        sql += " AND d.status = ?"
        params.append(DocStatus.YURURLUKTE)
    if doc_code:
        sql += " AND d.code = ?"
        params.append(doc_code)
    if rule_type:
        sql += " AND r.rule_type = ?"
        params.append(rule_type)
    sql += " ORDER BY d.code, r.clause_no, r.id"
    rows = [_row_to_dict(r) for r in conn.execute(sql, params)]

    if q and q.strip():
        needle = fold(q)
        def matches(r):
            hay = fold(" ".join(str(r[k] or "") for k in
                                ("statement", "quote", "condition_text", "object_text", "doc_code", "doc_title")))
            return needle in hay
        rows = [r for r in rows if matches(r)]

    total = len(rows)
    offset = max(offset, 0)
    return {"kurallar": rows[offset:offset + max(limit, 0)], "toplam": total}


def summary(conn: sqlite3.Connection) -> dict:
    """Durum başına sayı, doküman başına bekleyen (ONERILDI) sayısı, kural tipi başına bekleyen sayısı.

    Her ikisi de yalnızca YURURLUKTE dokümanlara bakar (iptal/taslak dokümandaki öneriler kuyrukta
    gösterilmez; onlar zaten analiz dışıdır — CLAUDE.md değişmez 2).
    """
    by_status = {r[0]: r[1] for r in conn.execute(
        """SELECT r.review_status, COUNT(*) FROM rules r JOIN documents d ON d.id = r.document_id
           WHERE d.status = ? GROUP BY r.review_status""", (DocStatus.YURURLUKTE,))}
    by_doc = [dict(r) for r in conn.execute(
        """SELECT d.code AS doc_code, d.revision AS doc_revision, d.title AS doc_title, COUNT(*) AS bekleyen
           FROM rules r JOIN documents d ON d.id = r.document_id
           WHERE d.status = ? AND r.review_status = ?
           GROUP BY d.id ORDER BY bekleyen DESC, d.code""", (DocStatus.YURURLUKTE, ReviewStatus.ONERILDI))]
    by_type = {r[0]: r[1] for r in conn.execute(
        """SELECT r.rule_type, COUNT(*) FROM rules r JOIN documents d ON d.id = r.document_id
           WHERE d.status = ? AND r.review_status = ? GROUP BY r.rule_type""",
        (DocStatus.YURURLUKTE, ReviewStatus.ONERILDI))}
    return {
        "durum": by_status,
        "bekleyen_toplam": by_status.get(ReviewStatus.ONERILDI, 0),
        "dokuman_bekleyen": by_doc,
        "tip_bekleyen": by_type,
    }


def _validate_edits(edits: dict) -> dict:
    if "quote" in edits:
        raise ValueError("quote alanı düzenlenemez (kanıt değişmezi)")
    unknown = [f for f in edits if f not in EDITABLE_FIELDS]
    if unknown:
        raise ValueError(f"Düzenlenemeyen alan: {', '.join(sorted(unknown))}")
    cleaned = dict(edits)
    if "rule_type" in cleaned and cleaned["rule_type"] is not None:
        try:
            cleaned["rule_type"] = RuleType(cleaned["rule_type"])
        except ValueError:
            raise ValueError(f"Geçersiz kural tipi: {cleaned['rule_type']}") from None
    if "threshold_op" in cleaned and cleaned["threshold_op"] is not None and cleaned["threshold_op"] not in _THRESHOLD_OPS:
        raise ValueError(f"Geçersiz eşik operatörü: {cleaned['threshold_op']} (>,>=,<,<=,= olmalı)")
    if "threshold_value" in cleaned and cleaned["threshold_value"] is not None:
        try:
            cleaned["threshold_value"] = float(cleaned["threshold_value"])
        except (TypeError, ValueError):
            raise ValueError(f"Geçersiz eşik değeri: {cleaned['threshold_value']}") from None
    return cleaned


def _apply_review(conn: sqlite3.Connection, rule_id: int, action: ReviewAction, note: str | None,
                  reviewer: str | None, edits: dict | None) -> dict:
    if not conn.execute("SELECT 1 FROM rules WHERE id = ?", (rule_id,)).fetchone():
        raise LookupError(f"Kural yok: {rule_id}")
    edits = edits or {}
    if edits and action != ReviewAction.DUZELT:
        raise ValueError("edits yalnızca DUZELT eyleminde kullanılabilir")
    set_clauses: list[str] = []
    params: list = []
    if action == ReviewAction.DUZELT:
        if not edits:
            raise ValueError("DUZELT için en az bir düzenleme gerekir")
        cleaned = _validate_edits(edits)
        for field, value in cleaned.items():
            set_clauses.append(f"{field} = ?")
            params.append(value)
    set_clauses += ["review_status = ?", "reviewed_by = ?", "reviewed_at = ?", "review_note = ?"]
    params += [_ACTION_STATUS[action], (reviewer or "kullanici"), datetime.now(UTC).isoformat(), note]
    conn.execute(f"UPDATE rules SET {', '.join(set_clauses)} WHERE id = ?", (*params, rule_id))
    return _get_row(conn, rule_id)


def review_rule(conn: sqlite3.Connection, rule_id: int, action: str, note: str | None = None,
                reviewer: str | None = None, edits: dict | None = None) -> dict:
    """Bir kural üzerinde ONAYLA/DUZELT/REDDET kararı uygular (tek transaction).

    Zaten incelenmiş bir kural yeniden incelenebilir; son karar geçerli olur.
    Var olmayan `rule_id` -> LookupError. Geçersiz eylem/alan/değer -> ValueError.
    """
    act = ReviewAction(action)
    try:
        row = _apply_review(conn, rule_id, act, note, reviewer, edits)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return row


def review_bulk(conn: sqlite3.Connection, ids: list[int], action: str, note: str | None = None,
                reviewer: str | None = None) -> list[dict]:
    """Birden fazla kuralı tek transactionda ONAYLA/REDDET eder (en çok MAX_BULK adet, DUZELT desteklenmez)."""
    act = ReviewAction(action)
    if act == ReviewAction.DUZELT:
        raise ValueError("Toplu işlem yalnızca ONAYLA veya REDDET için kullanılabilir")
    if not ids:
        raise ValueError("id listesi boş olamaz")
    if len(ids) > MAX_BULK:
        raise ValueError(f"En çok {MAX_BULK} kural aynı anda işlenebilir")
    try:
        rows = [_apply_review(conn, rid, act, note, reviewer, None) for rid in ids]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rows
