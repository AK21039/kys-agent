"""Doğal dil sorusundan ilgili bölümleri bulur (FTS5 trigram, VEYA + bm25 sıralama)."""

import sqlite3

from ..textnorm import fold

STOPWORDS = {
    "ve", "veya", "ile", "bir", "bu", "su", "icin", "mi", "mu", "ne", "nedir", "nasil", "hangi", "kim",
    "kimdir", "olan", "olarak", "gibi", "da", "de", "ki", "var", "yok", "midir", "ise", "daha", "en", "her",
    "tum", "hangisi", "neler", "nelerdir", "kac", "gore", "kadar", "sonra", "once", "uzere", "yapilir",
    "dokuman", "dokumanda", "dokumanlarda", "var mi", "olur", "eder", "edilir",
}


def _terms(question: str) -> list[str]:
    """Türkçe ekleri kabaca budar: uzun kelimelerin ilk 6 harfi (trigram alt dizge eşleşmesi için)."""
    out = []
    for w in fold(question).replace('"', " ").split():
        w = w.strip(".,;:!?()'")
        if len(w) < 3 or w in STOPWORDS:
            continue
        w = w[:6] if len(w) > 7 else w
        if w not in out:
            out.append(w)
    return out


def retrieve(conn: sqlite3.Connection, question: str, limit: int = 8) -> list[sqlite3.Row]:
    terms = _terms(question)
    if not terms:
        return []
    fts = " OR ".join(f'"{t}"' for t in terms)
    return conn.execute(
        """SELECT s.id AS section_id, s.clause_no, s.heading, s.heading_path, s.text,
                  d.id AS document_id, d.code, d.revision, d.title, d.doc_type,
                  bm25(sections_fts) AS score
           FROM sections_fts
           JOIN sections s ON s.id = sections_fts.rowid
           JOIN documents d ON d.id = s.document_id
           WHERE sections_fts MATCH ? AND d.status = 'YURURLUKTE' AND length(s.text) > 20
           ORDER BY score LIMIT ?""",
        (fts, limit),
    ).fetchall()
