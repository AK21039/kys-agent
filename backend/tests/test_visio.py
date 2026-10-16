"""Visio okuyucu, akış karşılaştırma, Word içerik karşılaştırma ve eski format dönüştürme testleri.
Gerçek şirket dosyası kullanılmaz; minimal vsdx testte zipfile ile üretilir."""

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from kys.ingest import convert, doccompare, flowcompare
from kys.ingest.visio import (ALT_SUREC, BASLANGIC_BITIS, DOKUMAN, ISLEM, KARAR, parse_vsdx)

from .conftest import make_docx

V = "http://schemas.microsoft.com/office/visio/2012/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

MASTERS = {"2": "CFF Container", "8": "Swimlane (vertical)", "10": "Process", "11": "Start/End", "12": "Dynamic connector",
           "13": "Document", "14": "Subprocess", "37": "Decision", "4": "Swimlane List"}


def _shape(sid, master, text, x, y, w=2.0, h=1.0, extra="", sub=""):
    t = f"<Text>{text}</Text>" if text else ""
    return (f"<Shape ID='{sid}' Type='Shape' Master='{master}'><Cell N='PinX' V='{x}'/><Cell N='PinY' V='{y}'/>"
            f"<Cell N='Width' V='{w}'/><Cell N='Height' V='{h}'/>{extra}{t}{sub}</Shape>")


def _lane(sid, name, x, w):
    child = f"<Shapes><Shape ID='{sid + 1}' Type='Shape'><Text>{name}</Text></Shape></Shapes>"
    return (f"<Shape ID='{sid}' Type='Group' Master='8'><Cell N='PinX' V='{x}'/><Cell N='PinY' V='10'/>"
            f"<Cell N='Width' V='{w}'/><Cell N='Height' V='20'/>{child}</Shape>")


def _conn(sid, label="", extra=""):
    return f"<Shape ID='{sid}' Type='Shape' Master='12'>{extra}" + (f"<Text>{label}</Text>" if label else "") + "</Shape>"


def _connect(cid, begin, end):
    out = ""
    if begin:
        out += f"<Connect FromSheet='{cid}' FromCell='BeginX' ToSheet='{begin}' ToCell='PinX'/>"
    if end:
        out += f"<Connect FromSheet='{cid}' FromCell='EndX' ToSheet='{end}' ToCell='PinX'/>"
    return out


def make_vsdx(path: Path, page_name="Sayfa-1", title="TEST SÜREÇLERİ - ÖRNEK SÜREÇ Dök.No: PR99-TST-1 İlk Yayın Tar.:01.01.2025 Rev.No:01 Rev. Tar.:09.10.2025") -> Path:
    """İki kulvar (Depo | Satınalma). Akış: Başla(1) -> Talep al(2) -> Uygun mu?(3) -Evet-> Sipariş ver(4) -Hayır-> İptal(5);
    4 -> alt süreç(6); form(7) -> Başla (ters oklu bağlayıcı)."""
    shapes = [
        "<Shape ID='1' Type='Group' Master='2'><Shapes><Shape ID='90' Type='Shape'><Text>" + title + "</Text></Shape></Shapes></Shape>",
        _lane(10, "DEPO", 3, 6), _lane(20, "SATINALMA", 9, 6),
        _shape(31, 11, "Başla", 3, 18), _shape(32, 10, "Talep alınır", 3, 15),
        _shape(33, 37, "Talep uygun mu?", 3, 12), _shape(34, 10, "Sipariş verilir", 9, 12),
        _shape(35, 10, "Talep iptal edilir", 3, 8), _shape(36, 14, "PR11-SA-2 Satın Alma Süreci", 9, 8),
        _shape(37, 13, "LJ-FR-013 Talep Formu", 3, 19),
        _conn(41), _conn(42), _conn(43, "Evet"), _conn(44, "Hayır"), _conn(45),
        _conn(46, extra="<Cell N='BeginArrow' V='4'/><Cell N='EndArrow' V='0'/>"),
    ]
    connects = "".join([_connect(41, 31, 32), _connect(42, 32, 33), _connect(43, 33, 34), _connect(44, 33, 35),
                        _connect(45, 34, 36),
                        _connect(46, 31, 37)])  # ok başlangıçta: yön 37 -> 31
    page = (f"<PageContents xmlns='{V}' xmlns:r='{R}'><Shapes>{''.join(shapes)}</Shapes>"
            f"<Connects>{connects}</Connects></PageContents>")
    masters = "".join(f"<Master ID='{i}' NameU='{n}'/>" for i, n in MASTERS.items())
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("visio/masters/masters.xml", f"<Masters xmlns='{V}'>{masters}</Masters>")
        z.writestr("visio/pages/pages.xml",
                   f"<Pages xmlns='{V}' xmlns:r='{R}'><Page ID='1' Name='{page_name}'><Rel r:id='rId1'/></Page></Pages>")
        z.writestr("visio/pages/_rels/pages.xml.rels",
                   "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                   "<Relationship Id='rId1' Type='x' Target='page1.xml'/></Relationships>")
        z.writestr("visio/pages/page1.xml", page)
    return path


def test_parse_vsdx_shapes_lanes_edges_and_labels(tmp_path):
    doc = parse_vsdx(make_vsdx(tmp_path / "a.vsdx"))
    page = doc.pages[0]
    assert page.name == "Sayfa-1" and "Dök.No: PR99-TST-1" in page.title
    assert page.lanes == ["DEPO", "SATINALMA"]
    kinds = {s.id: s.kind for s in page.shapes}
    assert kinds == {"31": BASLANGIC_BITIS, "32": ISLEM, "33": KARAR, "34": ISLEM, "35": ISLEM, "36": ALT_SUREC, "37": DOKUMAN}
    assert {s.id: s.lane for s in page.shapes} == {"31": "DEPO", "32": "DEPO", "33": "DEPO", "34": "SATINALMA",
                                                   "35": "DEPO", "36": "SATINALMA", "37": "DEPO"}
    edges = {(e.source, e.target, e.label) for e in page.edges}
    assert ("33", "34", "Evet") in edges and ("33", "35", "Hayır") in edges
    assert ("31", "32", "") in edges and ("34", "36", "") in edges
    assert ("37", "31", "") in edges and ("31", "37", "") not in edges   # BeginArrow -> yön ters
    assert [s.id for s in page.ordered()][:3] == ["31", "32", "33"]   # başlangıçtan genişlik öncelikli
    assert not page.warnings


def test_parse_vsdx_geometry_fallback_and_bad_files(tmp_path):
    p = make_vsdx(tmp_path / "a.vsdx")
    # Bir bağlayıcının ucu hiçbir şekle yapışık değil: uç noktası şeklin yanına düşüyorsa geometriyle eşlenir
    with zipfile.ZipFile(p) as z:
        files = {n: z.read(n) for n in z.namelist()}
    page = files["visio/pages/page1.xml"].decode()
    page = page.replace(_connect(45, 34, 36), _connect(45, 34, None))
    page = page.replace(_conn(45), _conn(45, extra="<Cell N='EndX' V='9.2'/><Cell N='EndY' V='8.3'/>"))
    files["visio/pages/page1.xml"] = page.encode()
    q = tmp_path / "b.vsdx"
    with zipfile.ZipFile(q, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    doc = parse_vsdx(q)
    assert any(e.source == "34" and e.target == "36" for e in doc.pages[0].edges)
    assert any("geometriden" in w for w in doc.pages[0].warnings)

    (tmp_path / "bozuk.vsdx").write_bytes(b"degil")
    assert "zip" in parse_vsdx(tmp_path / "bozuk.vsdx").warnings[0]
    assert "vsdx" in parse_vsdx(tmp_path / "x.vsd").warnings[0]


def _insert_process(conn, code="PR99-TST-1", steps=None, rev="01"):
    conn.execute("INSERT INTO documents(id, code, code_key, revision, title, doc_type, revision_date, body_text, file_path,"
                 " file_sha256, meta_source) VALUES (1, ?, 'pr99tst1', ?, 'Örnek Süreç', 'SUREC', '2025-10-09', 'x', 'a.pdf', 'sha', 'regex')",
                 (code, rev))
    conn.execute("INSERT INTO processes(id, code, name, source, document_id) VALUES (1, ?, 'Örnek Süreç', 'DOKUMAN', 1)", (code,))
    steps = steps or [
        (1, "Başla", None, [2]), (2, "Talep alınır", None, [3]),
        (3, "Talep uygun mu?", "Evet/Hayır", [4, 5]),   # DB sırası ters: ilk çıkış (Evet sayılır) iptale gidiyor
        (4, "Talep iptal edilir", None, []), (5, "Satınalma siparişi verilir", None, []),
        (6, "Fazladan DB adımı", None, []),
    ]
    for seq, name, dec, nxt in steps:
        conn.execute("INSERT INTO process_steps(process_id, seq, name, decision, next_steps) VALUES (1, ?, ?, ?, ?)",
                     (seq, name, dec, json.dumps(nxt)))
    conn.commit()


def test_flow_compare_reports_missing_extra_branch_and_code(conn, tmp_path):
    _insert_process(conn, code="PR99-TST-9")   # DB kodu farklı: vsdx PR99-TST-1 diyor
    rep = flowcompare.compare(conn, "PR99-TST-9", make_vsdx(tmp_path / "a.vsdx"))
    assert rep.page_selected_by.startswith("ad benzerliği")
    assert rep.page_doc_code == "PR99-TST-1"
    assert any("KOD FARKI" in n and "PR99-TST-1" in n for n in rep.notes)
    assert any("PR11-SA-2" in m for m in rep.missing)          # alt süreç şekli DB'de yok
    assert any("Fazladan DB adımı" in e for e in rep.extra)
    assert any("ters" in d for d in rep.label_diffs)           # Evet/Hayır sırası ters
    assert len(rep.matched) == 5
    assert "EKSİK adım" in rep.text()


def test_flow_compare_selects_page_by_code_and_flags_revision(conn, tmp_path):
    _insert_process(conn, rev="02")                            # DB Rev.02, vsdx Rev.01
    rep = flowcompare.compare(conn, "PR99-TST-1", make_vsdx(tmp_path / "a.vsdx"))
    assert rep.page_selected_by == "Dök.No eşleşti"
    assert any("REVİZYON FARKI" in n and "daha eski" in n for n in rep.notes)
    with pytest.raises(LookupError):
        flowcompare.compare(conn, "YOK-1", make_vsdx(tmp_path / "b.vsdx"))


def test_similarity_tolerates_turkish_suffixes_and_case():
    assert flowcompare.similarity("TALEP İPTAL EDİLİR.", "Talep iptal edilir") > 0.9
    assert flowcompare.similarity("Malzeme talebi kontrol edilir", "Yatırım kararı alınmaz") < 0.4


def test_compare_folder_matches_by_header_code_content_and_duplicates(conn, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    conv = tmp_path / "conv"
    body = [("h1", "AMAÇ"), ("p", "Bu talimat kompresörün güvenli açılıp kapatılmasını anlatır. " * 5)]
    make_docx(src / "ME-TL-001 Kompresör.docx", code="ME-TL-001", rev="01", title="Kompresör", body=body)
    make_docx(src / "PAD-2 Bakım.docx", code="ME-TL-008", rev="00", title="Bakım",
              body=[("h1", "AMAÇ"), ("p", "Bakım planı hattın mekanik bakımı için hazırlanmıştır. " * 5)])
    make_docx(src / "ZZ-TL-009 Yok.docx", code="ZZ-TL-009", rev="00", title="Yok",
              body=[("h1", "AMAÇ"), ("p", "Tamamen başka konu: kimyasal depolama kuralları. " * 5)])
    (src / "eski.doc").write_bytes(b"x")  # dönüştürülmemiş
    from kys.ingest import parsers
    for code, name, rev, path in (("ME-TL-001", "Kompresör", "01", src / "ME-TL-001 Kompresör.docx"),
                                  ("ME-TL-008", "Bakım", "00", src / "PAD-2 Bakım.docx")):
        pd = parsers.parse(path)
        conn.execute("INSERT INTO documents(code, code_key, revision, title, doc_type, revision_date, header_text, body_text,"
                     " file_path, file_sha256, meta_source) VALUES (?, ?, ?, ?, 'TALIMAT', '2024-06-05', ?, ?, 'x.pdf', ?, 'regex')",
                     (code, doccompare.metadata.code_key(code), rev, name, pd.header_text, pd.header_text + " " + pd.body_text, code))
    conn.commit()
    items = {i.file: i for i in doccompare.compare_folder(conn, src, conv)}
    a = items["ME-TL-001 Kompresör.docx"]
    assert a.verdict == "AYNI" and a.db_code == "ME-TL-001" and a.sira > 0.95
    b = items["PAD-2 Bakım.docx"]
    assert b.verdict == "AYNI" and b.db_code == "ME-TL-008" and any("KOD FARKI" in n for n in b.notes)
    assert items["ZZ-TL-009 Yok.docx"].verdict == "DB'DE YOK"
    assert items["eski.doc"].verdict == "OKUNAMADI"
    assert "| ME-TL-001 Kompresör.docx |" in doccompare.to_markdown(list(items.values()))


def test_convert_folder_keeps_originals_and_reports_errors(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "alt").mkdir(parents=True)
    (src / "a.doc").write_bytes(b"orijinal")
    (src / "alt" / "b.xls").write_bytes(b"orijinal2")
    (src / "c.docx").write_bytes(b"yok sayilir")
    (src / "~$gecici.doc").write_bytes(b"x")
    calls = []

    def fake_run(cmd, env, **kw):
        calls.append((cmd[:3], env["KYS_SRC"], env["KYS_DST"]))
        if env["KYS_SRC"].endswith("b.xls"):
            return subprocess.CompletedProcess(cmd, 1, "", "Excel açılamadı\nayrıntı")
        Path(env["KYS_DST"]).write_bytes(b"yeni")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(convert, "com_available", lambda: True)
    monkeypatch.setattr(convert.subprocess, "run", fake_run)
    out = tmp_path / "out"
    res = convert.convert_folder(src, out)
    assert [(r.src.name, r.status) for r in res] == [("a.doc", "donusturuldu"), ("b.xls", "hata")]
    assert res[1].message == "Excel açılamadı"
    assert (out / "a.docx").read_bytes() == b"yeni"
    assert (src / "a.doc").read_bytes() == b"orijinal"             # orijinale dokunulmadı
    assert calls[0][0][:2] == ["powershell", "-NoProfile"]
    again = convert.convert_folder(src, out)
    assert again[0].status == "atlandi"                           # çıktı varsa üzerine yazmaz


def test_convert_without_com_gives_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, "com_available", lambda: False)
    with pytest.raises(convert.ConvertError, match="COM"):
        convert.convert_file(tmp_path / "a.doc", tmp_path / "a.docx")
