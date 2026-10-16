from pathlib import Path

import pytest

from kys.ingest.metadata import code_key, detect, find_codes, parse_date, table_values
from kys.ontology import DocType


@pytest.mark.parametrize("text,expected", [
    ("Detaylar için PR-04 prosedürüne bakınız.", ["PR-04"]),
    ("KYS-PR-001 ve İK.TL.02 birlikte uygulanır.", ["KYS-PR-001", "İK.TL.02"]),
    ("FR.KAL.012 numaralı form", ["FR.KAL.012"]),
])
def test_find_codes_detects_common_turkish_code_formats(text, expected):
    assert find_codes(text) == expected


def test_find_codes_ignores_revision_and_standard_tokens():
    assert find_codes("REV-03 ISO-9001 S-1 madde") == []


def test_code_key_treats_separator_and_zero_padding_as_same():
    assert code_key("PR-04") == code_key("pr.4") == code_key("PR 004")
    assert code_key("PR-100") != code_key("PR-10")


def test_parse_date_formats():
    assert parse_date("05.06.2024") == "2024-06-05"
    assert parse_date("2024-06-05") == "2024-06-05"
    assert parse_date("31.13.2024") is None


def test_table_values_reads_label_row_with_values_below():
    text = "| Doküman No | Yayın Tarihi | Rev. No | Rev. Tarihi |\n| PR-04 | 01.01.2020 | 03 | 05.06.2024 |"
    kv = table_values(text)
    assert kv["code"] == "PR-04" and kv["revision"] == "03" and kv["revision_date"] == "05.06.2024"


def test_table_values_reads_label_value_pairs_and_uppercase_turkish_labels():
    kv = table_values("| DOKÜMAN NO | TL-SAT-03 | REVİZYON NO | 1 |")
    assert kv == {"code": "TL-SAT-03", "revision": "1"}


def test_detect_prefers_header_table_over_filename():
    header = "| Doküman No | PR-04 | Rev. No | 3 |"
    meta = detect(Path("eski_PR-01_kopya.docx"), header, "")
    assert (meta.code, meta.revision) == ("PR-04", "03")
    assert meta.sources["code"] == "baslik_tablosu"


def test_detect_falls_back_to_filename():
    meta = detect(Path("TL-08 Depo Sayım Talimatı Rev02.docx"), "", "")
    assert meta.code == "TL-08"
    assert meta.revision == "02"
    assert meta.title == "Depo Sayım Talimatı"
    assert meta.doc_type == DocType.TALIMAT


def test_detect_title_from_uppercase_header_line_uses_turkish_casing():
    header = "| Doküman No | PR-04 |\nSATINALMA PROSEDÜRÜ\nİÇ TETKİK"
    meta = detect(Path("PR-04.docx"), header, "")
    assert meta.title == "Satınalma Prosedürü"
    assert meta.sources["title"] == "ustbilgi"


def test_detect_inline_pdf_header_with_spaced_code():
    header = ("Doküman No GT- 161\nİlk Yayın Tarihi 15.05.2024\nELEKTRİK BAKIM TEKNİSYENİ\n"
              "Revizyon No 02\nGÖREV TANIMI\nRevizyon Tarihi 20.05.2026")
    meta = detect(Path("ELEKTRİK BAKIM TEKNİSYENİ GÖREV TANIMI.pdf"), header, "")
    assert (meta.code, meta.revision, meta.revision_date) == ("GT-161", "02", "2026-05-20")
    assert meta.doc_type == DocType.GOREV_TANIMI


def test_detect_inline_header_beats_line_name_in_filename():
    header = "Doküman No ME-TL-008\nPAD-2 HATTI MEKANİK BAKIM İlk Yayın Tarihi 20.02.2026\nTALİMATI Revizyon No 00"
    meta = detect(Path("PAD-2 Hattı Mekanik Bakım Talimatı.pdf"), header, "")
    assert meta.code == "ME-TL-008"
    assert meta.doc_type == DocType.TALIMAT


def test_detect_process_flowchart_compact_labels():
    header = "ÜRETİM SÜREÇLERİ- ARIZA SÜRECİ\nDök.No: PR08- UR-3 İlk Yayın Tar.:15.01.2016 Rev.No:01 Rev. Tar.:09.09.2025"
    meta = detect(Path("Arıza Süreci.pdf"), header, "")
    assert (meta.code, meta.revision, meta.revision_date) == ("PR08-UR-3", "01", "2025-09-09")
    assert meta.doc_type == DocType.PROSES_KARTI


def test_detect_code_split_by_pdf_char_dedupe():
    header = "Dök.No: P R46-PRJ-3 İlk Yayın Tar.:01.10.2021 Rev.No:01 Rev. Tar.:25.09.2025"
    assert detect(Path("x.pdf"), header, "").code == "PR46-PRJ-3"
    header = "Dök.No: PR46-P RJ-1 İlk Yayın Tar.:15.01.2016 Rev.No:03"
    assert detect(Path("x.pdf"), header, "").code == "PR46-PRJ-1"


def test_detect_excel_label_with_empty_cells_and_double_separator():
    header = "| İSG YILLIK EĞİTİM PLANI | | | DOKÜMAN NO | | İSG.PN.-03 |\n| | | | İLK YAYIN TARİHİ | | 2026-01-05 00:00:00 |"
    meta = detect(Path("Yıllık Eğitim Planı.xlsx"), header, "")
    assert code_key(meta.code) == code_key("İSG.PN-03")
    assert meta.revision_date == "2026-01-05"


def test_detect_title_from_header_when_filename_is_a_number():
    header = "Doküman No GT-181\nOTOMASYON TEKNİSYENİ Revizyon No 02"
    meta = detect(Path("TKYS0100001673103.pdf"), header, "")
    assert meta.title == "Otomasyon Teknisyeni"


def test_looks_like_doc_code_separates_machine_names():
    from kys.ingest.metadata import known_segments, looks_like_doc_code
    segs = known_segments(["ME-TL-007", "İSG-FR-002", "GT-161"])
    assert looks_like_doc_code("IK-FR-025", segs)
    assert looks_like_doc_code("İSG.RP-001", segs)
    assert not looks_like_doc_code("PAD-1", segs)
    assert not looks_like_doc_code("TECOM-1", segs)
    assert find_codes("EK-4 ve EK-5 ektedir") == []


def test_detect_type_from_title_beats_code_prefix():
    meta = detect(Path("P-07 Kalite Politikası.docx"), "", "")
    assert meta.doc_type == DocType.POLITIKA


@pytest.mark.parametrize("stem,expected", [
    ("ISG-TL-001Taşeron ve Hizmet Sağlayıcıları İşletmeye Giriş Çıkış Talimatı-rev01", "ISG-TL-001"),  # kod başlığa bitişik
    ("PR.YP-0X Yatırım ve Proje Prosedürü", "PR.YP-0X"),  # yer tutucu numara
    ("PR.İSG-01 İSG Prosedürü-Rev00", "PR.İSG-01"),
    ("PAD-2 MEKANİK BAKIM TALİMATI", "PAD-2"),
    ("Orta Gerilim Açma Kapama Talimatı", None),
])
def test_filename_code_handles_glued_and_placeholder_codes(stem, expected):
    from kys.ingest.metadata import filename_code
    assert filename_code(stem) == expected
