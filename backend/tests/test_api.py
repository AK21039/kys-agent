import asyncio
import dataclasses

import pytest
from fastapi.testclient import TestClient

from kys import config, llm
from kys.api.mcp_server import build_server
from kys.cli import publish_snapshot
from kys.ingest.pipeline import ingest_paths
from kys.query import assistant
from kys.query.assistant import AnswerOut, Citation
from kys.query.retrieval import _terms

from .conftest import make_docx

SECRET = "SIR-ANAHTAR-123"


@pytest.fixture
def published(conn, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    make_docx(inbox / "a.docx")
    make_docx(inbox / "b.docx", code="PR-08", rev="01", title="Tedarikçi Değerlendirme Prosedürü",
              body=[("h2", "4.1 Değerlendirme"), ("p", "Tedarikçiler yılda bir kez değerlendirilir.")])
    ingest_paths(conn, inbox, use_llm=False)
    return publish_snapshot(conn, tmp_path / "pub" / "kys-query.db")


def _client(monkeypatch, db_path, **overrides):
    from kys.api.app import create_app
    values = {"base_path": "/qa", "access_token": "", "db_url": "", "allowed_hosts": (), **overrides}
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, **values))
    return TestClient(create_app(db_path))


def test_publish_snapshot_is_single_file_without_local_paths(published):
    import sqlite3
    c = sqlite3.connect(published)
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert all("\\" not in fp and "/" not in fp for (fp,) in c.execute("SELECT file_path FROM documents"))
    assert c.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0] == 0


def test_terms_drop_stopwords_and_trim_suffixes():
    assert _terms("Tedarikçiler nasıl değerlendirilir?") == ["tedari", "degerl"]


def test_web_page_and_read_only_endpoints(published, monkeypatch):
    with _client(monkeypatch, published) as c:
        assert c.get("/qa", follow_redirects=False).status_code in (307, 302)
        assert "KYS Sorgu" in c.get("/qa/").text
        assert c.get("/qa/api/health").json()["ok"] is True
        assert c.get("/qa/api/stats").json()["documents"] == 2
        assert {d["code"] for d in c.get("/qa/api/documents").json()} == {"PR-04", "PR-08"}
        doc = c.get("/qa/api/documents/pr.4").json()
        assert doc["code"] == "PR-04" and any(r["target_code"] == "PR-08" for r in doc["references"])
        assert c.get("/qa/api/documents/PR-08").json()["referenced_by"][0]["code"] == "PR-04"
        assert c.get("/qa/api/documents/YOK-1").status_code == 404
        hits = c.get("/qa/api/search", params={"q": "genel mudur onaylar"}).json()
        assert hits[0]["code"] == "PR-04" and hits[0]["clause_no"] == "4.2"
        assert "FR-12" in [m["code"] for m in c.get("/qa/api/references").json()["missing_documents"]]


def test_token_required_when_configured(published, monkeypatch):
    with _client(monkeypatch, published, access_token="gizli") as c:
        assert c.get("/qa/api/health").status_code == 200  # sağlık kontrolü açık
        assert c.get("/qa/api/stats").status_code == 401
        assert c.get("/qa/api/stats", headers={"Authorization": "Bearer yanlis"}).status_code == 401
        assert c.get("/qa/api/stats", headers={"Authorization": "Bearer gizli"}).status_code == 200
        assert c.post("/qa/mcp", json={}).status_code == 401


def test_ask_keeps_only_quotes_found_in_sources(published, monkeypatch):
    def fake_structured(**kwargs):
        assert kwargs["tier"] == "query" and "<kaynak no=" in kwargs["user"]
        return AnswerOut(answer="100.000 TL üzerini Genel Müdür onaylar [1].", yeterli_bilgi=True, citations=[
            Citation(kaynak_no=1, quote="Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar"),
            Citation(kaynak_no=1, quote="Satınalma talebi 5 TL'yi aşarsa Yönetim Kurulu onaylar"),
            Citation(kaynak_no=99, quote="olmayan kaynak numarası burada"),
        ])
    monkeypatch.setattr(assistant.llm, "structured", fake_structured)
    with _client(monkeypatch, published) as c:
        a = c.post("/qa/api/ask", json={"question": "Satınalma onay limiti nedir?"}).json()
    assert a["answer"].startswith("100.000")
    assert [x["code"] for x in a["citations"]] == ["PR-04"] and a["citations"][0]["clause_no"] == "4.2"
    assert a["unverified"] == 2


def test_ask_model_error_returns_502(published, monkeypatch):
    def failing(**kwargs):
        raise llm.LLMError("sorgu: kota doldu")
    monkeypatch.setattr(assistant.llm, "structured", failing)
    with _client(monkeypatch, published) as c:
        r = c.post("/qa/api/ask", json={"question": "Satınalma onay limiti nedir?"})
    assert r.status_code == 502 and "kota" in r.json()["detail"]


def test_mcp_tools_in_process(published):
    from mcp import Client

    async def run():
        async with Client(build_server(published)) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            res = await client.call_tool("search_documents", {"query": "tedarikci degerlendirme"})
            doc = await client.call_tool("get_document", {"code": "PR-08"})
            return names, res, doc

    names, res, doc = asyncio.run(run())
    assert {"search_documents", "get_document", "list_documents", "missing_references"} <= names
    assert "PR-08" in str(res.content) and "Tedarikçi" in str(doc.content)


def test_named_document_sections_come_first(published):
    import sqlite3

    from kys.query.retrieval import retrieve_for_question
    c = sqlite3.connect(published)
    c.row_factory = sqlite3.Row
    rows = retrieve_for_question(c, '"Tedarikçi Değerlendirme Prosedürü"ne aykırı bir süreç var mı?')
    assert rows[0]["code"] == "PR-08"
    rows = retrieve_for_question(c, "PR-04 dokümanında onay limitleri")
    assert rows[0]["code"] == "PR-04"


def test_immutable_readonly_connection(published):
    from kys import db
    c = db.connect(published, readonly=True, immutable=True)
    assert c.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2
    with pytest.raises(Exception):
        c.execute("DELETE FROM documents")
    c.close()


# --- Kaynak doküman kodu, BYOK, MODEL_YOK, CORS ----------------------------------

def test_citation_doc_code_comes_from_verified_section_not_model(published, monkeypatch):
    def fake_structured(**kwargs):
        # Model yanlış kaynak numarası veriyor; alıntı aslında PR-04 md.4.2'de geçiyor.
        return AnswerOut(answer="Genel Müdür onaylar [2].", yeterli_bilgi=True, citations=[
            Citation(kaynak_no=2, quote="Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar")])
    monkeypatch.setattr(assistant.llm, "structured", fake_structured)
    with _client(monkeypatch, published) as c:
        a = c.post("/qa/api/ask", json={"question": "Satınalma onay limiti nedir? PR-04"}).json()
    cit = a["citations"][0]
    assert cit["doc_code"] == "PR-04" and cit["code"] == "PR-04" and cit["clause_no"] == "4.2"
    assert cit["revision"] and all(s["doc_code"] for s in a["sources"])


def test_ask_reports_answering_model_and_passes_byok(published, monkeypatch):
    seen = {}

    def fake_structured(**kwargs):
        seen["byok"] = kwargs.get("byok")
        llm.last_model.set("gemini:m2")
        return AnswerOut(answer="x", yeterli_bilgi=True, citations=[])
    monkeypatch.setattr(assistant.llm, "structured", fake_structured)
    with _client(monkeypatch, published) as c:
        q = {"question": "Satınalma onay limiti nedir?"}
        assert c.post("/qa/api/ask", json=q).json()["model"] == "gemini:m2" and seen["byok"] is None
        c.post("/qa/api/ask", json=q, headers={"X-LLM-Provider": "Gemini", "X-LLM-Key": " abc "})
        assert seen["byok"] == ("gemini", "abc")
        r = c.post("/qa/api/ask", json=q, headers={"X-LLM-Provider": "openai", "X-LLM-Key": "abc"})
        assert r.status_code == 400 and "abc" not in r.text
        assert c.post("/qa/api/ask", json=q, headers={"X-LLM-Key": "abc"}).status_code == 400


def test_ask_chain_exhausted_returns_503_model_yok_without_key(published, monkeypatch, caplog):
    def exhausted(**kwargs):
        raise llm.LLMUnavailable(f"sorgu: hiçbir model cevap veremedi (gemini:m1 → HTTP 429 {SECRET})")
    monkeypatch.setattr(assistant.llm, "structured", exhausted)
    with _client(monkeypatch, published) as c, caplog.at_level("DEBUG"):
        r = c.post("/qa/api/ask", json={"question": "Satınalma onay limiti nedir?"},
                   headers={"X-LLM-Provider": "gemini", "X-LLM-Key": SECRET})
    assert r.status_code == 503 and r.json()["code"] == "MODEL_YOK"
    assert SECRET not in r.text and SECRET not in caplog.text


def test_cors_disabled_by_default_and_enabled_by_origin_list(published, monkeypatch):
    pre = {"Origin": "https://app.example", "Access-Control-Request-Method": "POST",
           "Access-Control-Request-Headers": "authorization,content-type,x-llm-provider,x-llm-key"}
    with _client(monkeypatch, published) as c:
        assert "access-control-allow-origin" not in c.options("/qa/api/ask", headers=pre).headers
    with _client(monkeypatch, published, cors_origins=("https://app.example",)) as c:
        r = c.options("/qa/api/ask", headers=pre)
        assert r.headers["access-control-allow-origin"] == "https://app.example"
        assert "x-llm-key" in r.headers["access-control-allow-headers"].lower()
        assert "access-control-allow-credentials" not in r.headers
        bad = c.options("/qa/api/ask", headers={**pre, "Origin": "https://kotu.example"})
        assert "access-control-allow-origin" not in bad.headers
        assert c.get("/qa/api/health", headers={"Origin": "https://kotu.example"}).status_code == 200


# --- Web uygulaması ({base}/app) ---------------------------------------------------------------------------------

@pytest.fixture
def web_dir(tmp_path):
    d = tmp_path / "web"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><html><head><title>Uygulama</title></head><body>kok</body></html>",
                                  encoding="utf-8")
    (d / "assets" / "app-abc123.js").write_text("console.log('x')", encoding="utf-8")
    (d / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return d


def test_web_routes_absent_without_web_dir(published, monkeypatch, tmp_path):
    from kys.api import app as appmod
    monkeypatch.setattr(appmod, "find_web_dir", lambda configured: None)
    with _client(monkeypatch, published, web_dir=tmp_path / "yok") as c:
        assert c.get("/qa/app/").status_code in (404, 405)  # MCP alt uygulamasına düşer, uygulama sunulmaz
        assert "KYS Sorgu" in c.get("/qa/").text            # eski arayüz sağlam
        assert c.get("/qa/api/health").json()["ok"] is True


def test_web_app_served_with_injection_assets_and_spa_fallback(published, monkeypatch, web_dir):
    with _client(monkeypatch, published, web_dir=web_dir, access_token="GIZLI") as c:  # token açık, statik istemez
        r = c.get("/qa/app", follow_redirects=False)
        assert r.status_code in (302, 307) and r.headers["location"] == "/qa/app/"

        r = c.get("/qa/app/")
        assert r.status_code == 200 and "kok" in r.text
        assert r.headers["cache-control"] == "no-cache"
        assert "kys_api_base" in r.text and r.text.index("kys_api_base") < r.text.index("<title>")  # <head> başında
        assert "location.origin" in r.text and "http" not in r.text.split("<script>")[1].split("</script>")[0]

        a = c.get("/qa/app/assets/app-abc123.js")
        assert a.status_code == 200 and "immutable" in a.headers["cache-control"]
        assert c.get("/qa/app/favicon.svg").status_code == 200

        # SPA: bilinmeyen yol index.html; eksik dosya 404; dizin dışına çıkış yok
        spa = c.get("/qa/app/surecler/PR-04")
        assert spa.status_code == 200 and "kok" in spa.text and "kys_api_base" in spa.text
        assert c.get("/qa/app/assets/yok.js").status_code == 404
        # token statik dosyalar için gerekmez ama API ve MCP için gerekir
        assert c.get("/qa/api/stats").status_code == 401
        assert c.post("/qa/mcp", json={}).status_code == 401


def test_web_app_does_not_affect_mcp_and_api(published, monkeypatch, web_dir):
    with _client(monkeypatch, published, web_dir=web_dir, access_token="GIZLI") as c:
        h = {"Authorization": "Bearer GIZLI"}
        assert c.get("/qa/api/stats", headers=h).json()["documents"] == 2
        r = c.post("/qa/mcp", headers={**h, "Accept": "application/json, text/event-stream"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert r.status_code == 200 and "search_documents" in r.text
        assert "KYS Sorgu" in c.get("/qa/").text
