from kys.ingest import sections as sec
from kys.ingest.sections import detect_heading, split_sections


def test_detect_heading_accepts_clause_headings():
    assert detect_heading("4.2 Satınalma Talebi") == ("4.2", "Satınalma Talebi")
    assert detect_heading("1. Amaç") == ("1", "Amaç")
    assert detect_heading("5 SORUMLULUKLAR") == ("5", "SORUMLULUKLAR")
    assert detect_heading("## 4.1 Talep") == ("4.1", "Talep")


def test_detect_heading_rejects_numbered_list_items_and_sentences():
    assert detect_heading("1. Talep formu doldurulur.") is None
    assert detect_heading("10 gün içinde tedarikçiye bildirilir") is None
    assert detect_heading("| 1 | Satınalma |") is None


def test_split_sections_builds_heading_path():
    body = "Giriş metni\n1. Amaç\nAmaç metni\n4 UYGULAMA\n4.1 Talep\nTalep metni\n4.2 Onay\nOnay metni"
    s = split_sections(body)
    assert [x.clause_no for x in s] == [None, "1", "4", "4.1", "4.2"]
    assert s[0].text == "Giriş metni"
    assert s[4].heading_path == "4 UYGULAMA > 4.2 Onay"
    assert s[4].text == "Onay metni"


def test_split_sections_splits_long_section_keeping_clause(monkeypatch):
    monkeypatch.setattr(sec, "MAX_SECTION_CHARS", 50)
    body = "4.1 Talep\n" + "\n".join(["Uzun bir paragraf metni burada yer alır."] * 4)
    s = split_sections(body)
    assert len(s) > 1
    assert all(x.clause_no == "4.1" for x in s)
    assert s[1].heading == "Talep (devam)"
