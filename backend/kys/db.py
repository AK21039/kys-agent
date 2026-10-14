"""SQLite bağlantısı, şema kurulumu ve ortak sorgular."""

import sqlite3
from importlib import resources
from pathlib import Path

from .config import settings
from .textnorm import fold

# Şema ilk kurulduktan sonraki kolon değişiklikleri: (sürüm, SQL). Yalnızca sona ekle.
MIGRATIONS: list[tuple[int, str]] = []


def connect(path: Path | str | None = None, readonly: bool = False) -> sqlite3.Connection:
    path = Path(path or settings.db_path)
    if readonly:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(resources.files("kys").joinpath("schema.sql").read_text(encoding="utf-8"))
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    for version, sql in MIGRATIONS:
        if version not in applied:
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
    conn.commit()


def _fts_query(query: str) -> str | None:
    """Kullanıcı sorgusunu FTS5 ifadesine çevirir: her kelime tırnaklı, AND ile.

    Trigram tokenizer 3 karakterden kısa terimleri eşleştiremez; onlar atlanır.
    """
    terms = [t.replace('"', "") for t in fold(query).split()]
    terms = [t for t in terms if len(t) >= 3]
    if not terms:
        return None
    return " AND ".join(f'"{t}"' for t in terms)


def search_sections(conn: sqlite3.Connection, query: str, limit: int = 20,
                    only_active: bool = True) -> list[sqlite3.Row]:
    fts = _fts_query(query)
    if fts is None:
        return []
    sql = """
        SELECT s.id AS section_id, s.clause_no, s.heading, s.text,
               d.id AS document_id, d.code, d.revision, d.title, d.doc_type, d.status,
               bm25(sections_fts) AS score
        FROM sections_fts
        JOIN sections s ON s.id = sections_fts.rowid
        JOIN documents d ON d.id = s.document_id
        WHERE sections_fts MATCH ?
    """
    if only_active:
        sql += " AND d.status = 'YURURLUKTE'"
    sql += " ORDER BY score LIMIT ?"
    return conn.execute(sql, (fts, limit)).fetchall()
