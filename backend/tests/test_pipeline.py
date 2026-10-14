from kys import db
from kys.ingest import classify as classify_mod
from kys.ingest.classify import DocClassification
from kys.ingest.pipeline import ingest_paths
from kys.llm import LLMError
from kys.ontology import DocStatus, DocType

from .conftest import make_docx, make_xlsx


def _docs(conn):
    return {(r["code"], r["revision"]): r for r in conn.execute("SELECT * FROM documents")}


def test_ingest_folder_without_llm_stores_docs_sections_and_resolves_refs(conn, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    make_docx(inbox / "satinalma.docx")
    make_docx(inbox / "tedarikci.docx", code="PR-08", rev="01", title="Tedarikçi Değerlendirme Prosedürü",
              body=[("h2", "4.1 Değerlendirme"), ("p", "Tedarikçiler yılda bir kez değerlendirilir.")])
    make_xlsx(inbox / "yetki.xlsx")
    (inbox / "~$gecici.docx").write_bytes(b"lock")

    results = ingest_paths(conn, inbox, use_llm=False)

    assert sorted(r.status for r in results) == ["eklendi"] * 3
    docs = _docs(conn)
    assert docs[("PR-04", "03")]["doc_type"] == DocType.PROSEDUR
    assert docs[("PR-04", "03")]["revision_date"] == "2024-06-05"
    assert docs[("YM-01", "02")]["doc_type"] == DocType.YETKI_MATRISI

    refs = {r["ref_code"]: r["resolved_doc_id"] for r in conn.execute("SELECT * FROM doc_references")}
    assert refs["PR-08"] == docs[("PR-08", "01")]["id"]
    assert refs["FR-12"] is None  # sistemde olmayan form → çözülmemiş atıf
    edge = conn.execute("SELECT * FROM edges WHERE rel_type = 'REFERANS_VERIR'").fetchone()
    assert edge["review_status"] == "ONAYLANDI"


def test_ingest_same_file_twice_is_skipped(conn, tmp_path):
    p = make_docx(tmp_path / "a.docx")
    ingest_paths(conn, p, use_llm=False)
    assert [r.status for r in ingest_paths(conn, p, use_llm=False)] == ["atlandi"]


def test_new_revision_supersedes_old_and_old_revision_is_historical(conn, tmp_path):
    ingest_paths(conn, make_docx(tmp_path / "r3.docx", rev="03"), use_llm=False)
    ingest_paths(conn, make_docx(tmp_path / "r4.docx", rev="04", title="Satınalma Prosedürü X"), use_llm=False)
    ingest_paths(conn, make_docx(tmp_path / "r2.docx", rev="02", title="Satınalma Prosedürü Y"), use_llm=False)

    docs = _docs(conn)
    assert docs[("PR-04", "04")]["status"] == DocStatus.YURURLUKTE
    assert docs[("PR-04", "03")]["status"] == DocStatus.IPTAL
    assert docs[("PR-04", "02")]["status"] == DocStatus.IPTAL
    assert docs[("PR-04", "04")]["supersedes_id"] == docs[("PR-04", "03")]["id"]


def test_same_document_with_different_bytes_is_rejected(conn, tmp_path):
    ingest_paths(conn, make_docx(tmp_path / "a.docx"), use_llm=False)
    r = ingest_paths(conn, make_docx(tmp_path / "b.docx", body=[("p", "Farklı gövde metni burada.")]),
                     use_llm=False)
    assert r[0].status == "hata" and "zaten kayıtlı" in r[0].message


def test_different_documents_sharing_a_code_are_kept_and_flagged(conn, tmp_path):
    ingest_paths(conn, make_docx(tmp_path / "a.docx"), use_llm=False)
    r = ingest_paths(conn, make_docx(tmp_path / "b.docx", title="Malzeme Kabul Prosedürü"), use_llm=False)[0]
    assert r.status == "eklendi" and r.code == "PR-04#2"
    assert any("KOD ÇAKIŞMASI" in w for w in r.warnings)


def test_search_matches_query_typed_without_turkish_chars(conn, tmp_path):
    ingest_paths(conn, make_docx(tmp_path / "a.docx"), use_llm=False)
    rows = db.search_sections(conn, "genel mudur onaylar")
    assert rows and rows[0]["code"] == "PR-04" and rows[0]["clause_no"] == "4.2"


def test_llm_classification_fills_fields_but_keeps_header_code(conn, tmp_path, monkeypatch):
    def fake_classify(parsed, meta, conn=None):
        return DocClassification(code="PR-99", title="Satınalma Prosedürü", doc_type=DocType.PROSEDUR,
                                 revision="03", revision_date=None, effective_date="2024-07-01",
                                 owner_unit="Satınalma Müdürlüğü", summary="Satınalma kuralları.", confidence=0.9)
    monkeypatch.setattr(classify_mod, "classify", fake_classify)

    r = ingest_paths(conn, make_docx(tmp_path / "a.docx"), use_llm=True)[0]
    d = _docs(conn)[("PR-04", "03")]
    assert d["owner_unit"] == "Satınalma Müdürlüğü"
    assert d["effective_date"] == "2024-07-01"
    assert d["meta_source"] == "llm"
    assert any("Kod uyuşmazlığı" in w for w in r.warnings)


def test_llm_failure_falls_back_to_rule_based_metadata(conn, tmp_path, monkeypatch):
    def failing(parsed, meta, conn=None):
        raise LLMError("siniflandirma: API hatası")
    monkeypatch.setattr(classify_mod, "classify", failing)

    r = ingest_paths(conn, make_docx(tmp_path / "a.docx"), use_llm=True)[0]
    assert r.status == "eklendi" and r.code == "PR-04"
    assert any("Sınıflandırma yapılamadı" in w for w in r.warnings)


def test_manual_override_survives_database_rebuild(tmp_path):
    from kys import overrides
    from kys.ingest.pipeline import _sha256

    p = make_docx(tmp_path / "a.docx", code="", rev="")
    c1 = db.connect(tmp_path / "1.db"); db.init_db(c1)
    assert ingest_paths(c1, p, use_llm=False)[0].code.startswith("KODSUZ-")
    overrides.put(_sha256(p), p.name, code="YP-FR-032", revision="00")

    c2 = db.connect(tmp_path / "2.db"); db.init_db(c2)  # sıfırdan kurulan veritabanı
    r = ingest_paths(c2, p, use_llm=False)[0]
    assert (r.code, r.revision) == ("YP-FR-032", "00")
    assert c2.execute("SELECT meta_source FROM documents").fetchone()[0] == "kullanici"


def test_classify_existing_fills_summary_and_keeps_user_code(conn, tmp_path, monkeypatch):
    from kys import overrides
    from kys.ingest.pipeline import _sha256, classify_existing

    p = make_docx(tmp_path / "a.docx")
    ingest_paths(conn, p, use_llm=False)
    overrides.put(_sha256(p), p.name, code="PR-04-OZEL")
    conn.execute("UPDATE documents SET code = 'PR-04-OZEL', code_key = 'pr4ozel'")

    def fake_classify(parsed, meta, conn=None):
        return DocClassification(code="PR-99", title="Satınalma Prosedürü", doc_type=DocType.PROSEDUR,
                                 revision="03", revision_date=None, effective_date=None,
                                 owner_unit="Satınalma", summary="Özet.", confidence=0.9)
    monkeypatch.setattr(classify_mod, "classify", fake_classify)

    results = classify_existing(conn)
    assert len(results) == 1 and results[0].error is None
    d = conn.execute("SELECT * FROM documents").fetchone()
    assert (d["code"], d["summary"], d["owner_unit"], d["meta_source"]) == ("PR-04-OZEL", "Özet.", "Satınalma", "kullanici")
    assert classify_existing(conn) == []  # özeti olanlar tekrar işlenmez


def test_classify_existing_continues_after_model_error(conn, tmp_path, monkeypatch):
    from kys.ingest.pipeline import classify_existing

    ingest_paths(conn, make_docx(tmp_path / "a.docx"), use_llm=False)
    monkeypatch.setattr(classify_mod, "classify", lambda *a, **k: (_ for _ in ()).throw(LLMError("zaman aşımı")))
    results = classify_existing(conn)
    assert results[0].error and conn.execute("SELECT summary FROM documents").fetchone()[0] is None


def test_extraction_check_and_import(conn, tmp_path):
    import json

    from kys.extract import workflow
    ingest_paths(conn, make_docx(tmp_path / "a.docx"), use_llm=False)
    doc_id = conn.execute("SELECT id FROM documents").fetchone()[0]
    out = tmp_path / "x.json"
    payload = {
        "document_id": doc_id, "document_code": "PR-04",
        "roles": [{"name": "Genel Müdür", "aliases": ["GM"]}, {"name": "Satınalma Müdürü"}],
        "rules": [
            {"rule_type": "ONAY", "statement": "Genel Müdür 100.000 TL üzeri talepleri onaylar.",
             "subject": "Genel Müdür", "action": "onaylar", "object": "satınalma talebi",
             "threshold_op": ">", "threshold_value": 100000, "threshold_unit": "TRY", "clause_no": "4.2",
             "quote": "Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar."},
            {"rule_type": "ONAY", "statement": "Uydurma kural.", "subject": "GM",
             "quote": "Satınalma talebi 1 TL'yi aşarsa Yönetim Kurulu onaylar."},
        ],
        "steps": [{"seq": 1, "name": "Talep", "responsible": "Satınalma Müdürü", "next_steps": [2]},
                  {"seq": 2, "name": "Onay", "approver": "Genel Müdür"}],
        "references": [{"target": "FR-12", "relation": "KULLANIR", "quote": "Satınalma Talep Formu ile yapılır"},
                       {"target": "PR-08", "relation": "REFERANS_VERIR", "quote": "Tedarikçi seçimi için PR-08'e bakınız"}],
        "observations": ["4.1'de talebi kimin açacağı yazmıyor."],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    _, rep = workflow.check(conn, out)
    assert not rep.ok and len(rep.bad_quotes) == 1

    rep = workflow.import_file(conn, out)
    assert rep.counts["eklenen_kural"] == 1 and rep.counts["atilan"] == 1
    rule = conn.execute("SELECT * FROM rules").fetchone()
    assert (rule["review_status"], rule["threshold_value"], rule["clause_no"]) == ("ONERILDI", 100000, "4.2")
    gm = conn.execute("SELECT id FROM entities WHERE normalized_name = 'genel mudur'").fetchone()[0]
    assert rule["subject_entity_id"] == gm
    assert conn.execute("SELECT COUNT(*) FROM process_steps").fetchone()[0] == 2
    assert conn.execute("SELECT next_steps FROM process_steps WHERE seq = 1").fetchone()[0] == "[2]"
    assert conn.execute("SELECT COUNT(*) FROM edges WHERE rel_type = 'KULLANIR'").fetchone()[0] == 1

    # Tekrar içe aktarma çoğaltmaz; onaylanmış kural korunur.
    conn.execute("UPDATE rules SET review_status = 'ONAYLANDI'")
    workflow.import_file(conn, out)
    assert conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 1  # onaylı kural tekrar önerilmez
    assert conn.execute("SELECT COUNT(*) FROM processes").fetchone()[0] == 1
