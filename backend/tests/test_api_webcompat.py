"""AI Studio web uygulaması uçları (api/webcompat.py): biçim çevirisi, salt okunur/yazılabilir davranış,
doğrulanmamış kaynak etiketi, 501 uçları. Gerçek API/LLM çağrısı yok."""

import json

from kys.analysis.model import CheckOutcome, Finding
from kys.api import webcompat
from kys.ontology import EntityType, FindingStatus, FindingType, ReviewStatus, Severity

from .test_api import _client
from .test_review import _doc, kb  # noqa: F401  (kb fixture)


def _readonly_client(monkeypatch, conn, tmp_path):
    """Salt okunur (immutable) bağlantı WAL'ı okumaz; önce ana dosyaya aktarılır."""
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return _client(monkeypatch, tmp_path / "test.db")


def _finding(conn, title="Kırık atıf", unverified=0, status=FindingStatus.ACIK.value):
    evidence = [{"doc_code": "PR-04", "revision": "03", "clause_no": "4.2", "quote": "Genel Müdür onaylar."}]
    conn.execute(
        """INSERT INTO findings(finding_type, severity, title, explanation, recommendation, evidence,
                                unverified_basis, fingerprint, status)
           VALUES (?, ?, ?, 'açıklama', 'öneri', ?, ?, ?, ?)""",
        (FindingType.GUNCELLIK.value, Severity.KRITIK.value, title, json.dumps(evidence), unverified,
         f"fp-{title}", status))
    conn.commit()


def test_rules_map_to_rule_items_with_source(kb, conn, tmp_path, monkeypatch):
    client = _readonly_client(monkeypatch, conn, tmp_path)
    items = client.get("/qa/api/rules").json()
    assert {i["id"] for i in items} == {kb["r1"], kb["r2"], kb["r3"]}   # tüm durumlar, iptal doküman hariç
    r1 = next(i for i in items if i["id"] == kb["r1"])
    assert r1["source"] == {"document": "PR-04", "revision": "03", "clause": "4.2",
                            "quote": "Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar."}
    assert r1["threshold"] == {"value": 100000, "unit": "TRY", "op": ">"}
    assert r1["status"] == ReviewStatus.ONERILDI
    assert r1["object"] == "Genel Müdür 100.000 TL üzeri talepleri onaylar."   # object_text yoksa kural cümlesi

    only = client.get("/qa/api/rules", params={"doc_code": "PR-08"}).json()
    assert [i["id"] for i in only] == [kb["r3"]]
    approved = client.get("/qa/api/rules", params={"status": "ONAYLANDI"}).json()
    assert [i["id"] for i in approved] == [kb["r2"]]


def test_rule_writes_are_409_on_read_only_server(kb, tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path / "test.db")
    r = client.post(f"/qa/api/rules/{kb['r1']}/approve")
    assert r.status_code == 409 and r.json()["code"] == "SALT_OKUNUR"
    assert client.patch(f"/qa/api/rules/{kb['r1']}", json={"object": "x"}).status_code == 409


def test_rule_writes_go_through_review_when_writable(kb, conn, tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path / "test.db", writable=True)
    assert client.post(f"/qa/api/rules/{kb['r1']}/approve").json()["status"] == ReviewStatus.ONAYLANDI
    rej = client.post(f"/qa/api/rules/{kb['r3']}/reject", json={"reason": "mükerrer"}).json()
    assert rej["status"] == ReviewStatus.REDDEDILDI and rej["notes"] == "mükerrer"

    upd = client.patch(f"/qa/api/rules/{kb['r2']}", json={
        "object": "teklif değerlendirmesi", "source": {"quote": "uydurma alıntı"}}).json()
    assert upd["status"] == ReviewStatus.DUZELTILDI and upd["object"] == "teklif değerlendirmesi"
    assert upd["source"]["quote"] == "Teklif 5 iş günü içinde değerlendirilir."   # alıntı değişmez
    assert client.patch(f"/qa/api/rules/{kb['r2']}", json={}).status_code == 422


def test_findings_label_unverified_basis_and_translate_status(conn, tmp_path, monkeypatch):
    _doc(conn)
    _finding(conn, "Onaylı", unverified=0)
    _finding(conn, "Onaysız", unverified=1, status=FindingStatus.KABUL_EDILDI.value)
    client = _readonly_client(monkeypatch, conn, tmp_path)
    items = {i["title"]: i for i in client.get("/qa/api/findings").json()}
    assert items["Onaysız"]["description"].startswith(webcompat.UNVERIFIED_PREFIX)
    assert not items["Onaylı"]["description"].startswith(webcompat.UNVERIFIED_PREFIX)
    assert items["Onaysız"]["status"] == "KABUL"
    assert items["Onaylı"]["evidence_quote"] == "Genel Müdür onaylar." and items["Onaylı"]["document_code"] == "PR-04"
    assert [i["title"] for i in client.get("/qa/api/findings", params={"status": "KABUL"}).json()] == ["Onaysız"]


def test_finding_status_update_when_writable(conn, tmp_path, monkeypatch):
    _finding(conn)
    fid = conn.execute("SELECT id FROM findings").fetchone()[0]
    assert _client(monkeypatch, tmp_path / "test.db").patch(
        f"/qa/api/findings/{fid}", json={"status": "KABUL"}).status_code == 409
    client = _client(monkeypatch, tmp_path / "test.db", writable=True)
    out = client.patch(f"/qa/api/findings/{fid}", json={"status": "KABUL", "resolution_notes": "bilinçli"}).json()
    assert out["status"] == "KABUL" and out["resolution_notes"] == "bilinçli"
    assert conn.execute("SELECT status FROM findings").fetchone()[0] == FindingStatus.KABUL_EDILDI
    assert client.patch(f"/qa/api/findings/{fid}", json={"status": "UYDURMA"}).status_code == 422


def test_analysis_run_read_only_keeps_results_in_memory(conn, tmp_path, monkeypatch):
    fake = Finding(check="kirik_referans", finding_type=FindingType.BOSLUK, severity=Severity.ORTA,
                   title="PR-77 bulunamadı", explanation="Atıf yapılan doküman yok.",
                   evidence=[{"doc_code": "PR-04", "quote": "PR-77'ye bakınız"}], unverified_basis=True)
    monkeypatch.setattr(webcompat, "run_checks", lambda c: {"kirik_referans": CheckOutcome(findings=[fake])})
    client = _readonly_client(monkeypatch, conn, tmp_path)
    run = client.post("/qa/api/analysis/run").json()
    assert run["findings_count"] == 1 and run["medium_count"] == 1 and run["run_id"] == "bellek"
    items = client.get("/qa/api/findings").json()
    assert items[0]["id"] < 0 and items[0]["description"].startswith(webcompat.UNVERIFIED_PREFIX)
    assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0   # DB'ye yazılmadı


def test_analysis_run_writable_saves_findings(kb, conn, tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path / "test.db", writable=True)
    run = client.post("/qa/api/analysis/run").json()
    assert run["ok"] and run["run_id"].isdigit()
    assert conn.execute("SELECT status FROM analysis_runs").fetchone()[0] == "TAMAMLANDI"
    assert run["findings_count"] == conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]


def test_entities_and_decisions(conn, tmp_path, monkeypatch):
    doc = _doc(conn)
    rol = conn.execute("INSERT INTO entities(entity_type, canonical_name, normalized_name) VALUES (?, ?, ?)",
                       (EntityType.ROL.value, "Genel Müdür", "genel mudur")).lastrowid
    conn.execute("INSERT INTO entity_aliases(entity_id, alias, normalized_alias) VALUES (?, 'GM', 'gm')", (rol,))
    conn.execute("INSERT INTO entities(entity_type, canonical_name, normalized_name) VALUES (?, 'SAP', 'sap')",
                 (EntityType.SISTEM.value,))
    proc = conn.execute("INSERT INTO processes(code, name) VALUES ('SR-01', 'Satınalma')").lastrowid
    conn.execute("""INSERT INTO decisions(code, title, owner_entity_id, process_id, threshold_op, threshold_value,
                                          threshold_unit, basis_document_id, basis_clause_no)
                    VALUES ('K-1', 'Satınalma onayı', ?, ?, '>', 100000, 'TRY', ?, '4.2')""", (rol, proc, doc))
    client = _readonly_client(monkeypatch, conn, tmp_path)

    ents = client.get("/qa/api/entities/resolutions").json()
    assert ents == [{"id": rol, "canonical_name": "Genel Müdür", "entity_type": "ROL", "aliases": ["GM"],
                     "status": ReviewStatus.ONERILDI}]
    dec = client.get("/qa/api/decisions", params={"process_code": "SR-01"}).json()
    assert dec[0]["topic"] == "Satınalma onayı" and dec[0]["decision_maker"] == "Genel Müdür"
    assert dec[0]["source_document"] == "PR-04" and dec[0]["source_clause"] == "4.2"
    assert dec[0]["rule_summary"] == "> 100000 TRY"
    assert client.get("/qa/api/decisions", params={"process_code": "YOK"}).json() == []


def test_missing_backends_return_501_and_routes_need_token(conn, tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path / "test.db")
    for method, path in (("post", "/qa/api/compliance/check"), ("get", "/qa/api/documents/PR-04/impact"),
                         ("delete", "/qa/api/decisions/3"), ("post", "/qa/api/processes/SR-01/steps/2/match-clauses")):
        r = getattr(client, method)(path)
        assert r.status_code == 501 and r.json()["code"] == "HENUZ_YOK", path
    guarded = _client(monkeypatch, tmp_path / "test.db", access_token="SIR")
    for path in ("/qa/api/rules", "/qa/api/findings", "/qa/api/decisions", "/qa/api/entities/resolutions"):
        assert guarded.get(path).status_code == 401, path
