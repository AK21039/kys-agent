"""PDF sayfa görüntüleme (pypdfium2). Yalnızca okuma; sayfalar 0 tabanlı indekslenir.

    page_count(yol) -> int
    render_page(yol, sayfa_indeksi, scale=2.0) -> PIL.Image
    page_png(yol, sayfa_indeksi, scale=2.0) -> bytes
    page_texts(yol) -> list[str]        # sayfa başına katlanmış (textnorm.fold) metin
    find_page(yol, metin) -> int | None # metnin geçtiği ilk sayfa indeksi
"""

import threading
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium

from .textnorm import fold

_lock = threading.Lock()  # pdfium iş parçacığı güvenli değil


def page_count(path: Path | str) -> int:
    with _lock:
        pdf = pdfium.PdfDocument(str(path))
        try:
            return len(pdf)
        finally:
            pdf.close()


def render_page(path: Path | str, page_index: int, scale: float = 2.0):
    with _lock:
        pdf = pdfium.PdfDocument(str(path))
        try:
            if not 0 <= page_index < len(pdf):
                raise IndexError(f"Sayfa yok: {page_index + 1} (toplam {len(pdf)})")
            return pdf[page_index].render(scale=scale).to_pil()
        finally:
            pdf.close()


def page_png(path: Path | str, page_index: int, scale: float = 2.0) -> bytes:
    buf = BytesIO()
    render_page(path, page_index, scale).save(buf, format="PNG")
    return buf.getvalue()


@lru_cache(maxsize=16)
def _texts(path: str, mtime: float) -> tuple[str, ...]:
    with _lock:
        pdf = pdfium.PdfDocument(path)
        try:
            return tuple(fold(" ".join(pdf[i].get_textpage().get_text_bounded().split())) for i in range(len(pdf)))
        finally:
            pdf.close()


def page_texts(path: Path | str) -> list[str]:
    p = Path(path)
    return list(_texts(str(p), p.stat().st_mtime))


def find_page(path: Path | str, text: str) -> int | None:
    """Metnin (boşluk/büyük-küçük harf/Türkçe karakter farkı gözetmeden) geçtiği ilk sayfa; yoksa None."""
    return find_in_texts(page_texts(path), text)


def find_in_texts(texts: list[str], text: str) -> int | None:
    needle = " ".join(fold(text or "").split())
    if len(needle) < 4:
        return None
    for i, t in enumerate(texts):
        if needle in t:
            return i
    return None
