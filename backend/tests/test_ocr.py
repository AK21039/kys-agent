"""OCR: eşik tespiti ve ayrıştırıcı/yeniden yükleme entegrasyonu (motor mock'lanır)."""

from pathlib import Path

from kys.ingest import ocr, pipeline
from kys.ingest.parsers import parse


class FakeEngine:
    name = "Sahte OCR (tr)"

    def __init__(self, text="ÖRNEK SÜREÇ\nDök.No: PR99-TST-1 Rev.No: 01\nMal kabul yapılır"):
        self.text, self.calls = text, 0

    def recognize(self, image):
        self.calls += 1
        return self.text


def _blank_pdf(path: Path, pages: int = 1) -> Path:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    for _ in range(pages):
        c.rect(50, 50, 100, 100)  # metinsiz, yalnız çizim
        c.showPage()
    c.save()
    return path


def test_threshold_text_sparse_and_image_heavy():
    assert ocr.pages_needing_ocr([500, 10, 61, 0]) == [1, 3]
    # görüntü ağırlıklı + az metin aday; görüntü ağırlıklı ama bol metin aday değil
    assert ocr.pages_needing_ocr([119, 900, 119], [0.6, 0.6, 0.0]) == [0]


def test_parse_applies_ocr_and_warns(tmp_path, monkeypatch):
    eng = FakeEngine()
    monkeypatch.setattr(ocr, "get_engine", lambda: eng)
    doc = parse(_blank_pdf(tmp_path / "t.pdf"))
    assert "Mal kabul yapılır" in doc.body_text
    assert "PR99-TST-1" in doc.header_text  # kimlik satırı üstbilgiye alınır
    assert any(w.startswith("OCR uygulandı (Sahte OCR (tr); sayfalar: 1)") for w in doc.warnings)
    assert eng.calls == 1


def test_parse_no_ocr_flag_keeps_old_behaviour(tmp_path, monkeypatch):
    eng = FakeEngine()
    monkeypatch.setattr(ocr, "get_engine", lambda: eng)
    doc = parse(_blank_pdf(tmp_path / "t.pdf"), ocr=False)
    assert eng.calls == 0 and any("OCR gerekli" in w for w in doc.warnings)


def test_parse_without_engine_warns_and_keeps_behaviour(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "get_engine", lambda: None)
    doc = parse(_blank_pdf(tmp_path / "t.pdf"))
    assert any("OCR motoru bulunamadı" in w for w in doc.warnings)
    assert any("OCR gerekli" in w for w in doc.warnings)


def test_engine_failure_does_not_break_parse(tmp_path, monkeypatch):
    class Boom(FakeEngine):
        def recognize(self, image):
            raise RuntimeError("kırık")

    monkeypatch.setattr(ocr, "get_engine", lambda: Boom())
    doc = parse(_blank_pdf(tmp_path / "t.pdf"))
    assert any("OCR başarısız sayfalar: 1" in w for w in doc.warnings)


def test_reingest_dry_run_then_apply_keeps_rules(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "get_engine", lambda: None)
    path = _blank_pdf(tmp_path / "t.pdf")
    r = pipeline.ingest_file(conn, path, use_llm=False)
    assert r.status == "eklendi"
    did = r.document_id
    conn.execute("INSERT INTO rules(document_id, rule_type, statement, quote) VALUES (?, 'ONAY', 'x', 'y')",
                 (did,))
    conn.commit()

    monkeypatch.setattr(ocr, "get_engine", lambda: FakeEngine())
    rep = pipeline.reingest_document(conn, r.code)
    assert not rep.applied and rep.rules == 1 and rep.new_chars > rep.old_chars
    assert "Mal kabul" not in conn.execute("SELECT body_text FROM documents WHERE id=?", (did,)).fetchone()[0]

    rep = pipeline.reingest_document(conn, r.code, apply=True)
    assert rep.applied
    row = conn.execute("SELECT body_text, parse_warnings FROM documents WHERE id=?", (did,)).fetchone()
    assert "Mal kabul yapılır" in row["body_text"] and "OCR uygulandı" in row["parse_warnings"]
    assert conn.execute("SELECT COUNT(*) FROM rules WHERE document_id=?", (did,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sections WHERE document_id=?", (did,)).fetchone()[0] >= 1
