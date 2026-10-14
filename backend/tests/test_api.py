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
