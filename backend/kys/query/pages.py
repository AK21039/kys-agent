"""Doküman sayfa görüntüleri: önceden üretilmiş PNG klasörü (KYS_PAGES_DIR) veya yerel orijinal PDF.

Yayın kopyasında file_path yalnızca dosya adıdır; konteynerde orijinal bulunmaz, bu yüzden `kys publish --pages`
sayfaları <pages_dir>/<dosya_sha256>/<n>.png olarak önceden üretir.
"""

import json
import sqlite3
from pathlib import Path, PureWindowsPath

from .. import config, pdfrender
from ..ingest.metadata import code_key


def find_source(file_path: str | None) -> Path | None:
    """Orijinal PDF'i yerelde bulur (mutlak yol, proje köküne göreli yol, KYS_FILES_DIR/dosya_adı)."""
    if not file_path:
        return None
    s = config.settings
    name = PureWindowsPath(file_path).name
    candidates = [Path(file_path), config.PROJECT_ROOT / PureWindowsPath(file_path).as_posix()]
    if s.files_dir:
        candidates.append(s.files_dir / name)
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            pass
    return None


def _doc(conn: sqlite3.Connection, code: str):
    return conn.execute("SELECT code, file_path, file_sha256 FROM documents WHERE code_key = ? "
                        "ORDER BY (status = 'YURURLUKTE') DESC, created_at DESC LIMIT 1", (code_key(code),)).fetchone()


def _cached_dir(sha: str | None) -> Path | None:
    d = config.settings.pages_dir
    if d and sha and (d / sha).is_dir():
        return d / sha
    return None


def page_total(file_path: str | None, sha: str | None) -> int | None:
    if not (file_path or "").lower().endswith(".pdf"):
        return None
    cached = _cached_dir(sha)
    if cached:
        return len(list(cached.glob("*.png"))) or None
    src = find_source(file_path)
    return pdfrender.page_count(src) if src else None


def page_image(conn: sqlite3.Connection, code: str, page_no: int) -> bytes | None:
    """1 tabanlı sayfa numarası; görüntü üretilemiyorsa None (API 404 döner)."""
    d = _doc(conn, code)
    if not d or not d["file_path"].lower().endswith(".pdf") or page_no < 1:
        return None
    cached = _cached_dir(d["file_sha256"])
    if cached:
        f = cached / f"{page_no}.png"
        return f.read_bytes() if f.is_file() else None
    src = find_source(d["file_path"])
    if not src:
        return None
    try:
        return pdfrender.page_png(src, page_no - 1)
    except IndexError:
        return None


def step_pages(file_path: str | None, sha: str | None, quotes: list[str | None]) -> list[int | None]:
    """Her alıntının 1 tabanlı sayfası. Önce önceden üretilmiş metin dizini (texts.json), yoksa yerel PDF; yoksa None."""
    if not (file_path or "").lower().endswith(".pdf"):
        return [None] * len(quotes)
    cached = _cached_dir(sha)
    if cached and (cached / "texts.json").is_file():
        texts = json.loads((cached / "texts.json").read_text(encoding="utf-8"))
        find = lambda q: pdfrender.find_in_texts(texts, q)  # noqa: E731
    elif src := find_source(file_path):
        find = lambda q: pdfrender.find_page(src, q)  # noqa: E731
    else:
        return [None] * len(quotes)
    out = []
    for q in quotes:
        i = find(q) if q else None
        out.append(None if i is None else i + 1)
    return out


def render_all(conn: sqlite3.Connection, out_dir: Path, scale: float = 2.0) -> tuple[int, int]:
    """Yerelde bulunan tüm PDF'lerin sayfalarını out_dir/<sha>/<n>.png olarak üretir. (doküman, sayfa) döner."""
    docs = pages = 0
    for r in conn.execute("SELECT file_path, file_sha256 FROM documents WHERE lower(file_path) LIKE '%.pdf'"):
        src = find_source(r["file_path"])
        if not src or not r["file_sha256"]:
            continue
        target = out_dir / r["file_sha256"]
        n = pdfrender.page_count(src)
        if target.is_dir() and len(list(target.glob("*.png"))) == n:
            continue
        target.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (target / f"{i + 1}.png").write_bytes(pdfrender.page_png(src, i, scale))
        (target / "texts.json").write_text(json.dumps(pdfrender.page_texts(src), ensure_ascii=False), encoding="utf-8")
        docs, pages = docs + 1, pages + n
    return docs, pages
