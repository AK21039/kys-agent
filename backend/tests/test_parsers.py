from pathlib import Path

import pytest

from kys.ingest.parsers import UnsupportedFormat, parse

from .conftest import make_docx, make_xlsx


def test_docx_header_table_and_autonumbered_headings(tmp_path):
    doc = parse(make_docx(tmp_path / "x.docx"))
    assert "| Doküman No | Yayın Tarihi | Rev. No | Rev. Tarihi |" in doc.header_text
    assert "| PR-04 | 01.01.2020 | 03 | 05.06.2024 |" in doc.header_text
    # Word otomatik numarası metne eklenir; elle yazılmış numara korunur.
    assert "# 1 AMAÇ" in doc.body_text
    assert "# 2 UYGULAMA" in doc.body_text
    assert "## 4.1 Talep" in doc.body_text
    assert "| 100.000 TL üzeri | Genel Müdür |" in doc.body_text


def test_xlsx_sheets_become_tables(tmp_path):
    doc = parse(make_xlsx(tmp_path / "ym.xlsx"))
    assert "# Sayfa: Yetki Matrisi" in doc.body_text
    assert "| Tedarikçi sözleşmesi feshi | | Onaylar |" in doc.body_text
    assert "| Doküman No | YM-01 | Rev. No | 02 |" in doc.header_text


def test_pdf_text_and_repeated_header_lines(tmp_path):
    pytest.importorskip("reportlab")
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font = Path("C:/Windows/Fonts/arial.ttf")
    if not font.exists():
        pytest.skip("Türkçe karakterli TTF font yok")
    pdfmetrics.registerFont(TTFont("Arial", str(font)))
    path = tmp_path / "t.pdf"
    c = canvas.Canvas(str(path))
    for page in range(3):
        c.setFont("Arial", 11)
        c.drawString(50, 800, "Doküman No: TL-08  Rev. No: 02")
        c.drawString(50, 700, f"{page + 1}. sayfa: Depo sayımı yılda iki kez yapılır ve kayıt altına alınır.")
        c.showPage()
    c.save()

    doc = parse(path)
    assert doc.pages == 3
    assert doc.header_text == "Doküman No: TL-08 Rev. No: 02"
    assert "Doküman No" not in doc.body_text
    assert "Depo sayımı yılda iki kez" in doc.body_text
    assert not doc.warnings


def test_legacy_doc_raises_with_conversion_hint(tmp_path):
    p = tmp_path / "eski.doc"
    p.write_bytes(b"x")
    with pytest.raises(UnsupportedFormat, match="soffice"):
        parse(p)


def test_text_file_cp1254_fallback(tmp_path):
    p = tmp_path / "not.txt"
    p.write_bytes("Satınalma işlemleri".encode("cp1254"))
    assert parse(p).body_text == "Satınalma işlemleri"
