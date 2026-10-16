"""Metin katmanı olmayan / az olan PDF sayfaları için yerel OCR.

Motor: Windows yerleşik OCR (Windows.Media.Ocr, WinRT). Her şey yerelde çalışır; veri dışarı çıkmaz.
Motor yoksa ya da başarısız olursa çağıran taraf mevcut davranışı (uyarı) korur.
"""

import asyncio
import io
import re
from dataclasses import dataclass
from pathlib import Path

# Bir sayfada bu kadar karakterden azı varsa sayfa OCR adayıdır.
MIN_PAGE_CHARS = 60
# Görüntü ağırlıklı sayfa (akış şeması, organizasyon şeması): sayfanın bu oranından fazlasını görüntü
# kaplıyorsa ve metin MAX_IMAGE_PAGE_CHARS'tan azsa metin katmanı büyük olasılıkla yalnızca başlıktır.
IMAGE_RATIO = 0.3
MAX_IMAGE_PAGE_CHARS = 400
RENDER_SCALE = 3.0           # 72 dpi * 3 = 216 dpi
PREFERRED_LANGS = ("tr", "en-US")


@dataclass
class OcrResult:
    engine: str
    pages: dict[int, str]    # 0 tabanlı sayfa no -> metin
    failed: list[int]
    notes: list[str]


def pages_needing_ocr(page_char_counts: list[int], image_ratios: list[float] | None = None,
                      min_chars: int = MIN_PAGE_CHARS) -> list[int]:
    """OCR gereken sayfa indeksleri: metin eşiğin altında, ya da görüntü ağırlıklı ve metin az."""
    out = []
    for i, n in enumerate(page_char_counts):
        ratio = image_ratios[i] if image_ratios else 0.0
        if n < min_chars or (ratio >= IMAGE_RATIO and n < MAX_IMAGE_PAGE_CHARS):
            out.append(i)
    return out


class WinOcrEngine:
    """Windows.Media.Ocr sarmalayıcısı. Dil: yüklü Türkçe paketi, yoksa kullanıcı profil dilleri."""

    def __init__(self):
        from winrt.windows.media.ocr import OcrEngine

        self._OcrEngine = OcrEngine
        self._engine = None
        self.language = None
        from winrt.windows.globalization import Language
        for tag in PREFERRED_LANGS:
            if OcrEngine.is_language_supported(Language(tag)):
                self._engine = OcrEngine.try_create_from_language(Language(tag))
                self.language = tag
                break
        if self._engine is None:
            self._engine = OcrEngine.try_create_from_user_profile_languages()
            self.language = "kullanıcı-profili"
        if self._engine is None:
            raise RuntimeError("Windows OCR için dil paketi yok.")
        self.name = f"Windows.Media.Ocr ({self.language})"

    def recognize(self, image) -> str:
        return asyncio.run(self._recognize(image))

    async def _recognize(self, image) -> str:
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(buf.getvalue())
        await writer.store_async()
        await writer.flush_async()
        writer.detach_stream()
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await self._engine.recognize_async(bitmap)
        return "\n".join(line.text for line in result.lines)


def get_engine():
    """Kullanılabilir OCR motorunu döner; yoksa None."""
    try:
        return WinOcrEngine()
    except Exception:
        return None


def render_page(path: Path, index: int, scale: float = RENDER_SCALE):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        max_dim = 9000  # WinRT OCR sınırı (OcrEngine.MaxImageDimension ~10000)
        page = pdf[index]
        w, h = page.get_size()
        scale = min(scale, max_dim / max(w, h))
        return page.render(scale=scale).to_pil()
    finally:
        pdf.close()


def _clean(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines() if ln.strip()]


def ocr_pdf_pages(path: Path, pages: list[int], engine=None) -> OcrResult | None:
    """Verilen sayfaları render edip OCR yapar. Motor yoksa None."""
    engine = engine or get_engine()
    if engine is None:
        return None
    out: dict[int, str] = {}
    failed: list[int] = []
    notes: list[str] = []
    for i in pages:
        try:
            text = engine.recognize(render_page(path, i))
            out[i] = "\n".join(_clean(text))
        except Exception as e:
            failed.append(i)
            notes.append(f"sayfa {i + 1}: {type(e).__name__}: {e}")
    return OcrResult(engine.name, out, failed, notes)


def page_ranges(pages: list[int]) -> str:
    return ", ".join(str(p + 1) for p in pages)


def scan_pdf(path: Path) -> tuple[int, list[int], list[int]]:
    """OCR'sız hızlı tarama: (sayfa sayısı, aday sayfa indeksleri, sayfa başına karakter)."""
    import pdfplumber

    from .parsers import _image_ratio

    counts, ratios = [], []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            counts.append(len((page.dedupe_chars().extract_text() or "").strip()))
            ratios.append(_image_ratio(page))
    return len(counts), pages_needing_ocr(counts, ratios), counts
