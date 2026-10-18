"""Onay Kuyruğu: listeleme/süzme/arama, özet, ONAYLA/DUZELT/REDDET, toplu işlem, API (salt okunur/yazılabilir),
çift kayıt (ONERILDI ikizi) düzeltmesi. Gerçek API/LLM çağrısı yok."""

import dataclasses

import pytest

from kys import config, db, review
from kys.ontology import ReviewAction, ReviewStatus, RuleType

from .test_api import _client

# --- yardımcılar: kuralları gerçek doküman ayrıştırma/çıkarım akışından geçirmeden doğrudan DB'ye yazar ----------


def _doc(conn, code="PR-04", rev="03", title="Satınalma Prosedürü", status="YURURLUKTE"):
    code_key = code.lower().replace("-", "")
    cur = conn.execute(
        """INSERT INTO documents(code, code_key, revision, title, doc_type, status, body_text, file_path,
                                 file_sha256, meta_source)
           VALUES (?, ?, ?, ?, 'PROSEDUR', ?, 'govde metni', 'x.docx', ?, 'kullanici')""",
        (code, code_key, rev, title, status, f"sha-{code}-{rev}-{status}"))
    return cur.lastrowid


def _rule(conn, document_id, rule_type=RuleType.ONAY, statement="Genel Müdür onaylar.",
         quote="Genel Müdür onaylar ifadesi", review_status=ReviewStatus.ONERILDI, clause_no="4.2", **extra):
    cols = ["document_id", "rule_type", "statement", "quote", "review_status", "clause_no", *extra.keys()]
    vals = [document_id, rule_type, statement, quote, review_status, clause_no, *extra.values()]
    sql = f"INSERT INTO rules({','.join(cols)}) VALUES ({','.join('?' * len(vals))})"
    return conn.execute(sql, vals).lastrowid


@pytest.fixture
def kb(conn):
    """PR-04 (2 kural, biri onaylı), PR-08 (1 kural), iptal edilmiş PR-99 (1 kural)."""
    pr04 = _doc(conn, "PR-04", "03")
    r1 = _rule(conn, pr04, rule_type=RuleType.ONAY,
              statement="Genel Müdür 100.000 TL üzeri talepleri onaylar.",
              quote="Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar.", clause_no="4.2",
              threshold_op=">", threshold_value=100000, threshold_unit="TRY", confidence=0.9,
              extracted_by="claude-sonnet-5-5")
    r2 = _rule(conn, pr04, rule_type=RuleType.SURE, statement="SATINALMA İŞLEMLERİ 5 gün içinde tamamlanır.",
              quote="Teklif 5 iş günü içinde değerlendirilir.", clause_no="4.3",
              review_status=ReviewStatus.ONAYLANDI, reviewed_by="admin", reviewed_at="2026-01-01T00:00:00+00:00")
    pr08 = _doc(conn, "PR-08", "01", "Tedarikçi Değerlendirme Prosedürü")
    r3 = _rule(conn, pr08, rule_type=RuleType.ZORUNLU_ADIM, statement="Tedarikçiler yılda bir değerlendirilir.",
              quote="Tedarikçiler yılda bir kez değerlendirilir.", clause_no="4.1")
    pr99 = _doc(conn, "PR-99", "00", "İptal Prosedürü", status="IPTAL")
    r4 = _rule(conn, pr99, rule_type=RuleType.ONAY, statement="İptal edilmiş kuraldır.",
              quote="İptal edilmiş kural metni burada yer alır.", clause_no="1.0")
    conn.commit()
    return {"pr04": pr04, "pr08": pr08, "pr99": pr99, "r1": r1, "r2": r2, "r3": r3, "r4": r4}


# --- list_rules --------------------------------------------------------------------------------------------------

def test_list_rules_default_only_onerildi_and_active_docs(kb, conn):
    out = review.list_rules(conn)
    ids = {r["id"] for r in out["kurallar"]}
    assert ids == {kb["r1"], kb["r3"]}  # r2 ONAYLANDI, r4 iptal dokümanda -> dışarıda
    assert out["toplam"] == 2
    row = next(r for r in out["kurallar"] if r["id"] == kb["r1"])
    assert row["doc_code"] == "PR-04" and row["doc_revision"] == "03" and row["clause_no"] == "4.2"
    assert row["threshold_op"] == ">" and row["threshold_value"] == 100000 and row["threshold_unit"] == "TRY"
    assert row["extracted_by"] == "claude-sonnet-5-5" and row["review_status"] == "ONERILDI"


def test_list_rules_status_none_returns_all_and_include_cancelled(kb, conn):
    out = review.list_rules(conn, status=None, include_cancelled=True)
    assert out["toplam"] == 4
    out2 = review.list_rules(conn, status=ReviewStatus.ONAYLANDI)
    assert [r["id"] for r in out2["kurallar"]] == [kb["r2"]]


def test_list_rules_filters_by_doc_code_and_rule_type(kb, conn):
    assert [r["id"] for r in review.list_rules(conn, doc_code="PR-08")["kurallar"]] == [kb["r3"]]
    assert [r["id"] for r in review.list_rules(conn, rule_type=RuleType.ZORUNLU_ADIM)["kurallar"]] == [kb["r3"]]
    assert review.list_rules(conn, doc_code="PR-08", rule_type=RuleType.ONAY)["toplam"] == 0


def test_list_rules_q_is_turkish_fold_insensitive(kb, conn):
    # r2 ONAYLANDI olduğu için status=None ile aranır; statement "SATINALMA İŞLEMLERİ ..." (büyük Türkçe harf).
    out = review.list_rules(conn, status=None, q="satinalma islemleri")
    assert [r["id"] for r in out["kurallar"]] == [kb["r2"]]
    out2 = review.list_rules(conn, status=None, q="100.000 TL")
    assert kb["r1"] in {r["id"] for r in out2["kurallar"]}


def test_list_rules_pagination(conn):
    pr = _doc(conn, "PR-77", "00")
    ids = [_rule(conn, pr, clause_no=str(i), quote=f"madde {i} metni burada uzunca yazılı") for i in range(1, 6)]
    conn.commit()
    page = review.list_rules(conn, doc_code="PR-77", limit=2, offset=2)
    assert page["toplam"] == 5
    assert [r["id"] for r in page["kurallar"]] == ids[2:4]


# --- summary -----------------------------------------------------------------------------------------------------

def test_summary_counts_by_status_doc_and_type(kb, conn):
    s = review.summary(conn)
    assert s["durum"] == {"ONERILDI": 2, "ONAYLANDI": 1}  # PR-99 (iptal) sayılmaz
    assert s["bekleyen_toplam"] == 2
    by_doc = {d["doc_code"]: d["bekleyen"] for d in s["dokuman_bekleyen"]}
    assert by_doc == {"PR-04": 1, "PR-08": 1}
    assert s["tip_bekleyen"] == {"ONAY": 1, "ZORUNLU_ADIM": 1}


# --- review_rule: ONAYLA / DUZELT / REDDET -----------------------------------------------------------------------

def test_review_rule_onayla_sets_status_reviewer_and_timestamp(kb, conn):
    row = review.review_rule(conn, kb["r1"], ReviewAction.ONAYLA)
    assert row["review_status"] == "ONAYLANDI" and row["reviewed_by"] == "kullanici"
    assert row["reviewed_at"] and "T" in row["reviewed_at"]
    assert conn.execute("SELECT review_status FROM rules WHERE id=?", (kb["r1"],)).fetchone()[0] == "ONAYLANDI"


def test_review_rule_reddet_with_custom_reviewer_and_note(kb, conn):
    row = review.review_rule(conn, kb["r1"], "REDDET", note="kaynak yetersiz", reviewer="ayse")
    assert row["review_status"] == "REDDEDILDI" and row["reviewed_by"] == "ayse" and row["review_note"] == "kaynak yetersiz"


def test_review_rule_duzelt_applies_edits_and_keeps_quote(kb, conn):
    row = review.review_rule(conn, kb["r1"], ReviewAction.DUZELT, edits={
        "statement": "Genel Müdür 50.000 TL üzeri talepleri onaylar.", "threshold_value": 50000,
        "threshold_op": "<", "rule_type": "ESIK", "condition_text": "yalnız yurt içi tedarik"})
    assert row["review_status"] == "DUZELTILDI"
    assert row["statement"] == "Genel Müdür 50.000 TL üzeri talepleri onaylar."
    assert row["threshold_value"] == 50000 and row["threshold_op"] == "<" and row["rule_type"] == "ESIK"
    assert row["condition_text"] == "yalnız yurt içi tedarik"
    assert row["quote"] == "Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar."  # değişmez


def test_review_rule_duzelt_requires_at_least_one_edit(kb, conn):
    with pytest.raises(ValueError):
        review.review_rule(conn, kb["r1"], ReviewAction.DUZELT)
    with pytest.raises(ValueError):
        review.review_rule(conn, kb["r1"], ReviewAction.DUZELT, edits={})


def test_review_rule_duzelt_rejects_quote_edit(kb, conn):
    with pytest.raises(ValueError, match="quote"):
        review.review_rule(conn, kb["r1"], ReviewAction.DUZELT, edits={"quote": "başka bir şey"})


def test_review_rule_duzelt_rejects_invalid_rule_type_and_threshold_op(kb, conn):
    with pytest.raises(ValueError):
        review.review_rule(conn, kb["r1"], ReviewAction.DUZELT, edits={"rule_type": "YOK_BOYLE_BIR_TIP"})
    with pytest.raises(ValueError):
        review.review_rule(conn, kb["r1"], ReviewAction.DUZELT, edits={"threshold_op": "!="})
    with pytest.raises(ValueError):
        review.review_rule(conn, kb["r1"], ReviewAction.DUZELT, edits={"statement": "x", "unknown_field": "y"})


def test_review_rule_invalid_action_raises_value_error(kb, conn):
    with pytest.raises(ValueError):
        review.review_rule(conn, kb["r1"], "KARARSIZ")


def test_review_rule_missing_id_raises_lookup_error(conn):
    with pytest.raises(LookupError):
        review.review_rule(conn, 999999, ReviewAction.ONAYLA)


def test_review_rule_already_reviewed_can_be_re_reviewed(kb, conn):
    review.review_rule(conn, kb["r1"], ReviewAction.ONAYLA)
    row = review.review_rule(conn, kb["r1"], ReviewAction.REDDET, note="aslında hayır")
    assert row["review_status"] == "REDDEDILDI" and row["review_note"] == "aslında hayır"


# --- review_bulk --------------------------------------------------------------------------------------------------

def test_review_bulk_onayla_in_one_transaction(kb, conn):
    rows = review.review_bulk(conn, [kb["r1"], kb["r3"]], ReviewAction.ONAYLA, reviewer="toplu")
    assert {r["review_status"] for r in rows} == {"ONAYLANDI"}
    assert all(r["reviewed_by"] == "toplu" for r in rows)


def test_review_bulk_rejects_duzelt(kb, conn):
    with pytest.raises(ValueError):
        review.review_bulk(conn, [kb["r1"]], ReviewAction.DUZELT)


def test_review_bulk_rejects_empty_and_over_200(kb, conn):
    with pytest.raises(ValueError):
        review.review_bulk(conn, [], ReviewAction.ONAYLA)
    with pytest.raises(ValueError):
        review.review_bulk(conn, list(range(1, 202)), ReviewAction.ONAYLA)


def test_review_bulk_rolls_back_fully_on_invalid_id(kb, conn):
    with pytest.raises(LookupError):
        review.review_bulk(conn, [kb["r1"], 999999, kb["r3"]], ReviewAction.ONAYLA)
    assert conn.execute("SELECT review_status FROM rules WHERE id=?", (kb["r1"],)).fetchone()[0] == "ONERILDI"
    assert conn.execute("SELECT review_status FROM rules WHERE id=?", (kb["r3"],)).fetchone()[0] == "ONERILDI"


# --- API: salt okunur / yazılabilir ---------------------------------------------------------------------------

@pytest.fixture
def api_db_path(tmp_path):
    """Kapatılmış, yazılabilir bir SQLite dosyası (test API'nin kendi bağlantılarını açabilmesi için)."""
    path = tmp_path / "kys.db"
    c = db.connect(path)
    db.init_db(c)
    pr04 = _doc(c, "PR-04", "03")
    r1 = _rule(c, pr04, rule_type=RuleType.ONAY, statement="Genel Müdür onaylar.",
              quote="Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar.", clause_no="4.2")
    c.commit()
    c.close()
    return path, r1


def test_review_get_endpoints_work_in_readonly_mode(api_db_path, monkeypatch):
    path, r1 = api_db_path
    with _client(monkeypatch, path) as c:
        s = c.get("/qa/api/review/summary").json()
        assert s["yazilabilir"] is False and s["bekleyen_toplam"] == 1
        rules = c.get("/qa/api/review/rules").json()
        assert rules["toplam"] == 1 and rules["kurallar"][0]["id"] == r1


def test_review_post_returns_409_salt_okunur_when_not_writable(api_db_path, monkeypatch):
    path, r1 = api_db_path
    with _client(monkeypatch, path) as c:
        r = c.post(f"/qa/api/review/rules/{r1}", json={"action": "ONAYLA"})
        assert r.status_code == 409
        assert r.json() == {"detail": "Bu sunucu salt okunur; onaylar yerel `kys serve` ile yapılır.",
                            "code": "SALT_OKUNUR"}
        rb = c.post("/qa/api/review/rules/bulk", json={"ids": [r1], "action": "ONAYLA"})
        assert rb.status_code == 409 and rb.json()["code"] == "SALT_OKUNUR"


def test_review_post_writes_when_writable_and_persists(api_db_path, monkeypatch):
    path, r1 = api_db_path
    with _client(monkeypatch, path, writable=True) as c:
        r = c.post(f"/qa/api/review/rules/{r1}", json={"action": "ONAYLA", "reviewer": "ayse"})
        assert r.status_code == 200
        body = r.json()
        assert body["review_status"] == "ONAYLANDI" and body["reviewed_by"] == "ayse"
        # DB'de gerçekten değişti (yalnız yanıt değil) ve GET uçları da artık bunu görüyor.
        assert c.get("/qa/api/review/summary").json()["bekleyen_toplam"] == 0
    conn2 = db.connect(path)
    assert tuple(conn2.execute("SELECT review_status, reviewed_by FROM rules WHERE id=?", (r1,)).fetchone()) == \
        ("ONAYLANDI", "ayse")
    conn2.close()


def test_review_post_404_for_missing_rule_and_422_for_bad_action(api_db_path, monkeypatch):
    path, r1 = api_db_path
    with _client(monkeypatch, path, writable=True) as c:
        assert c.post("/qa/api/review/rules/999999", json={"action": "ONAYLA"}).status_code == 404
        assert c.post(f"/qa/api/review/rules/{r1}", json={"action": "KARARSIZ"}).status_code == 422
        assert c.post(f"/qa/api/review/rules/{r1}", json={"action": "DUZELT", "edits": {"quote": "x"}}).status_code == 422
        assert c.post("/qa/api/review/rules/bulk",
                      json={"ids": list(range(1, 202)), "action": "ONAYLA"}).status_code == 422


def test_review_bulk_endpoint_writable(api_db_path, monkeypatch):
    path, r1 = api_db_path
    with _client(monkeypatch, path, writable=True) as c:
        r = c.post("/qa/api/review/rules/bulk", json={"ids": [r1], "action": "REDDET", "reviewer": "toplu"})
        assert r.status_code == 200
        assert r.json()["sonuclar"][0]["review_status"] == "REDDEDILDI"


def test_review_token_required_when_configured(api_db_path, monkeypatch):
    path, r1 = api_db_path
    with _client(monkeypatch, path, access_token="gizli", writable=True) as c:
        assert c.get("/qa/api/review/summary").status_code == 401
        assert c.post(f"/qa/api/review/rules/{r1}", json={"action": "ONAYLA"}).status_code == 401
        h = {"Authorization": "Bearer gizli"}
        assert c.get("/qa/api/review/summary", headers=h).status_code == 200
        assert c.post(f"/qa/api/review/rules/{r1}", json={"action": "ONAYLA"}, headers=h).status_code == 200


# --- Çift kayıt (ONERILDI ikizi) düzeltmesi: extract/workflow.py --------------------------------------------------

def test_import_does_not_recreate_reviewed_rule_with_same_type_and_quote(conn, tmp_path):
    """Aynı alıntı + aynı rule_type incelenmişse (ONERILDI dışı), yeniden içe aktarımda ikizi açılmaz;
    atlanan sayısı 'zaten_incelenmis' ile rapora yansır (bkz. extract/workflow.py import_file)."""
    import json

    from kys.extract import workflow
    from kys.ingest.pipeline import ingest_paths

    from .conftest import make_docx

    ingest_paths(conn, make_docx(tmp_path / "a.docx"), use_llm=False)
    doc_id = conn.execute("SELECT id FROM documents").fetchone()[0]
    quote = "Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar."
    payload = {
        "document_id": doc_id, "document_code": "PR-04",
        "roles": [{"name": "Genel Müdür", "aliases": []}],
        "rules": [{"rule_type": "ONAY", "statement": "Genel Müdür onaylar.", "subject": "Genel Müdür",
                   "clause_no": "4.2", "quote": quote}],
        "steps": [], "references": [], "observations": [],
    }
    out = tmp_path / "x.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    rep1 = workflow.import_file(conn, out)
    assert rep1.counts["eklenen_kural"] == 1 and rep1.counts["zaten_incelenmis"] == 0
    rule_id = conn.execute("SELECT id FROM rules").fetchone()[0]
    conn.execute("UPDATE rules SET review_status='ONAYLANDI', reviewed_by='ayse' WHERE id=?", (rule_id,))
    conn.commit()

    rep2 = workflow.import_file(conn, out)
    assert rep2.counts["eklenen_kural"] == 0 and rep2.counts["zaten_incelenmis"] == 1
    assert conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 1  # ONERILDI ikizi açılmadı
    row = conn.execute("SELECT review_status, reviewed_by FROM rules WHERE id=?", (rule_id,)).fetchone()
    assert tuple(row) == ("ONAYLANDI", "ayse")  # incelenmiş kayıt dokunulmadı
    obs = json.loads(conn.execute(
        "SELECT observations FROM extraction_runs ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert any("zaten incelenmiş" in o for o in obs)


def test_import_recreates_as_onerildi_when_rule_type_differs(conn, tmp_path):
    """Aynı alıntı ama farklı rule_type öneriliyorsa bu FARKLI bir kuraldır; ikiz sayılmaz, ONERILDI eklenir."""
    import json

    from kys.extract import workflow
    from kys.ingest.pipeline import ingest_paths

    from .conftest import make_docx

    ingest_paths(conn, make_docx(tmp_path / "a.docx"), use_llm=False)
    doc_id = conn.execute("SELECT id FROM documents").fetchone()[0]
    quote = "Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar."
    base_payload = {
        "document_id": doc_id, "document_code": "PR-04", "roles": [{"name": "Genel Müdür", "aliases": []}],
        "steps": [], "references": [], "observations": [],
    }
    out = tmp_path / "x.json"
    out.write_text(json.dumps({**base_payload, "rules": [
        {"rule_type": "ONAY", "statement": "a.", "subject": "Genel Müdür", "clause_no": "4.2", "quote": quote}]},
        ensure_ascii=False), encoding="utf-8")
    workflow.import_file(conn, out)
    conn.execute("UPDATE rules SET review_status='REDDEDILDI'")
    conn.commit()

    out.write_text(json.dumps({**base_payload, "rules": [
        {"rule_type": "YETKI", "statement": "b.", "subject": "Genel Müdür", "clause_no": "4.2", "quote": quote}]},
        ensure_ascii=False), encoding="utf-8")
    rep = workflow.import_file(conn, out)
    assert rep.counts["eklenen_kural"] == 1 and rep.counts["zaten_incelenmis"] == 0
    assert conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 2
