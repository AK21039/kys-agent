"""Doküman ayrıştırıcıları: dosya → ParsedDoc (üstbilgi + gövde metni).

Çıktı metni markdown benzeridir: başlıklar `#`, tablolar `| a | b |` satırları.
LLM kullanılmaz; bu katman tamamen deterministiktir.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED = {".docx", ".pdf", ".xlsx", ".xlsm", ".txt", ".md"}
LEGACY = {".doc", ".xls", ".ppt", ".rtf"}
MAX_SHEET_ROWS = 3000
_ID_LINE = re.compile(r"(?i)(?:d[öo]k(?:[üu]man)?|belge)\s*\.?\s*no\b|rev(?:[iİı]zyon)?\s*\.?\s*no\b")


class UnsupportedFormat(Exception):
    pass


@dataclass
class ParsedDoc:
    path: Path
    header_text: str
    body_text: str
    pages: int | None = None
    warnings: list[str] = field(default_factory=list)


def parse(path: Path | str) -> ParsedDoc:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in LEGACY:
        raise UnsupportedFormat(
            f"{ext} eski Office biçimi. LibreOffice ile dönüştürün: "
            f"soffice --headless --convert-to {ext.lstrip('.')}x \"{path.name}\""
        )
    if ext not in SUPPORTED:
        raise UnsupportedFormat(f"Desteklenmeyen dosya türü: {ext}")
    if ext == ".docx":
        doc = _parse_docx(path)
    elif ext == ".pdf":
        doc = _parse_pdf(path)
    elif ext in (".xlsx", ".xlsm"):
        doc = _parse_xlsx(path)
    else:
        doc = _parse_text(path)
    if not doc.body_text.strip():
        doc.warnings.append("Gövde metni boş.")
    return doc


def _cell(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().replace("|", "/")


def _table_rows(rows: list[list[str]]) -> list[str]:
    """Satırları pipe tabloya çevirir; birleştirilmiş hücrelerin tekrarını ve boş satırları atar."""
    out = []
    for row in rows:
        cells: list[str] = []
        for c in row:
            c = _cell(c)
            if cells and c and c == cells[-1]:
                continue  # yatay birleştirilmiş hücre tekrarı
            cells.append(c)
        while cells and not cells[-1]:
            cells.pop()  # sondaki boş kolonlar
        if cells:
            out.append("|" + "|".join(f" {c} " if c else " " for c in cells) + "|")
    return out


# --- DOCX -----------------------------------------------------------------

_HEADING_STYLE = re.compile(r"^(?:heading|başlık|baslik)\s*(\d)", re.IGNORECASE)
_LEADING_NUM = re.compile(r"^\d{1,2}(?:\.\d{1,2})*\.?\s")


def _heading_level(paragraph) -> int | None:
    name = paragraph.style.name if paragraph.style is not None else ""
    m = _HEADING_STYLE.match(name or "")
    if m:
        return int(m.group(1))
    if (name or "").lower() in ("title", "konu başlığı"):
        return 1
    return None


def _has_numbering(paragraph) -> bool:
    ppr = paragraph._p.pPr
    if ppr is not None and ppr.numPr is not None:
        return True
    style = paragraph.style
    while style is not None:
        sppr = style.element.pPr
        if sppr is not None and sppr.numPr is not None:
            return True
        style = style.base_style
    return False


def _docx_blocks(container, heading_counters: list[int] | None) -> list[str]:
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    lines: list[str] = []
    for block in container.iter_inner_content():
        if isinstance(block, Paragraph):
            text = _cell(block.text)
            if not text:
                continue
            level = _heading_level(block) if heading_counters is not None else None
            if level:
                # Word otomatik numaralandırması metinde yer almaz; madde numarasını yeniden üret.
                if _has_numbering(block) and not _LEADING_NUM.match(text):
                    heading_counters[level - 1] += 1
                    for i in range(level, len(heading_counters)):
                        heading_counters[i] = 0
                    num = ".".join(str(n) for n in heading_counters[:level] if n)
                    text = f"{num} {text}"
                lines.append("#" * level + " " + text)
            else:
                lines.append(text)
        elif isinstance(block, Table):
            rows = [[cell.text for cell in row.cells] for row in block.rows]
            lines.extend(_table_rows(rows))
            lines.append("")
    return lines


def _parse_docx(path: Path) -> ParsedDoc:
    import docx

    d = docx.Document(str(path))
    header_lines: list[str] = []
    seen_headers: set[int] = set()
    for section in d.sections:
        for hdr in (section.first_page_header, section.header):
            if hdr.is_linked_to_previous and seen_headers:
                continue
            key = id(hdr._element) if hdr._element is not None else None
            if key in seen_headers:
                continue
            seen_headers.add(key)
            header_lines.extend(_docx_blocks(hdr, None))
    body = _docx_blocks(d, [0] * 9)
    return ParsedDoc(path=path, header_text="\n".join(_dedupe(header_lines)), body_text="\n".join(body))


def _dedupe(lines: list[str]) -> list[str]:
    seen, out = set(), []
    for line in lines:
        if line and line not in seen:
            seen.add(line)
            out.append(line)
    return out


# --- PDF ------------------------------------------------------------------

def _parse_pdf(path: Path) -> ParsedDoc:
    import pdfplumber

    warnings: list[str] = []
    page_lines: list[list[str]] = []
    with pdfplumber.open(str(path)) as pdf:
        n_pages = len(pdf.pages)
        for page in pdf.pages:
            # Sahte kalın yazı (aynı harfin üst üste iki kez çizilmesi) "DDöökk" üretir; tekrarları at.
            text = page.dedupe_chars().extract_text() or ""
            page_lines.append([ln.strip() for ln in text.splitlines() if ln.strip()])

    total_chars = sum(len(ln) for lines in page_lines for ln in lines)
    if n_pages and total_chars < 40 * n_pages:
        warnings.append("Metin katmanı çok az: taranmış PDF olabilir, OCR gerekli.")

    # Sayfaların çoğunda tekrarlanan satırlar üstbilgi/altbilgidir.
    repeated: set[str] = set()
    if n_pages >= 2:
        counts = Counter(ln for lines in page_lines for ln in set(lines))
        repeated = {ln for ln, c in counts.items() if c >= max(2, n_pages // 2)}
    # Tekrar yoksa (tek sayfa) ilk satırlar üstbilgi adayı olarak kopyalanır, gövdeden çıkarılmaz.
    # Akış şemalarında metin sırası karışıktır; ilk sayfadaki kimlik satırları ("Dök.No: ...") her zaman alınır.
    first = page_lines[0] if page_lines else []
    header = [ln for ln in first if ln in repeated] or first[:12]
    header += [ln for ln in first if _ID_LINE.search(ln) and ln not in header]
    body = [ln for lines in page_lines for ln in lines if ln not in repeated]
    return ParsedDoc(path=path, header_text="\n".join(header), body_text="\n".join(body),
                     pages=n_pages, warnings=warnings)


# --- XLSX -----------------------------------------------------------------

def _parse_xlsx(path: Path) -> ParsedDoc:
    import openpyxl

    warnings: list[str] = []
    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    lines: list[str] = []
    for ws in wb.worksheets:
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= MAX_SHEET_ROWS:
                warnings.append(f"'{ws.title}' sayfası {MAX_SHEET_ROWS} satırda kesildi.")
                break
            rows.append(["" if v is None else str(v) for v in row])
        table = _table_rows(rows)
        if table:
            lines.append(f"# Sayfa: {ws.title}")
            lines.extend(table)
            lines.append("")
    wb.close()
    # Excel dokümanlarında kod/rev genelde ilk satırlardadır.
    header = [ln for ln in lines[:8] if ln.startswith("|")]
    return ParsedDoc(path=path, header_text="\n".join(header), body_text="\n".join(lines), warnings=warnings)


# --- Düz metin ------------------------------------------------------------

def _parse_text(path: Path) -> ParsedDoc:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1254")  # Türkçe Windows kodlaması
    return ParsedDoc(path=path, header_text="", body_text=text)
