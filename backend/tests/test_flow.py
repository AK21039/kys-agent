import asyncio
import hashlib
import json

import pytest
from reportlab.pdfgen import canvas

from kys import pdfrender
from kys.api.mcp_server import build_server
from kys.cli import publish_snapshot
from kys.ingest.metadata import code_key
from kys.process import flow
from kys.query import pages

from .test_api import _client

PNG = b"\x89PNG"


def test_mermaid_branches_roles_and_escaping():
    steps = [
        {"seq": 1, "name": "Talep alınır", "next_steps": [2]},
        {"seq": 2, "name": 'Tutar > 100 "TL" mı? [kontrol] {x}', "decision": "Evet/Hayır", "role": "Satınalma (Uzmanı)",
         "next_steps": [3, 4]},
        {"seq": 3, "name": "Onaylanır #1", "next_steps": [5]},
        {"seq": 4, "name": "Reddedilir", "next_steps": []},
        {"seq": 5, "name": "Üç yollu", "decision": "x", "next_steps": [2, 3, 4, 99]},
    ]
    m = flow.to_mermaid(steps)
    assert m.startswith("flowchart TD\n")
    assert 's1(["Talep alınır"])' in m                       # başlangıç oval
    assert "s2{" in m and "#quot;TL#quot;" in m and "#91;kontrol#93;" in m and "#123;x#125;" in m
    assert "<br/>#40;Satınalma #40;Uzmanı#41;#41;" in m      # rol; yerleşik parantez kaçırılır
    assert 's2 -->|"Evet"| s3' in m and 's2 -->|"Hayır"| s4' in m
    assert "#35;1" in m and "#35;35;" not in m               # '#' tek kez kaçırılır
    assert "s99" not in m                                    # olmayan adıma ok yok
    assert "s5 --> s2" in m and "s5 --> s4" in m             # 3 çıkışta etiket yok
    assert "class s2,s5 karar" in m


def test_mermaid_explicit_branch_labels_from_decision():
    steps = [{"seq": 1, "name": "Uygun mu?", "decision": "Uygun / Uygun değil", "next_steps": [2, 3]},
             {"seq": 2, "name": "A"}, {"seq": 3, "name": "B"}]
    m = flow.to_mermaid(steps)
    assert 's1 -->|"Uygun"| s2' in m and 's1 -->|"Uygun değil"| s3' in m


@pytest.fixture
def pdf_file(tmp_path):
    p = tmp_path / "src" / "Ariza Sureci.pdf"
    p.parent.mkdir()
    c = canvas.Canvas(str(p))
    c.drawString(72, 750, "Sayfa bir: MAKINA DURUSU")
    c.showPage()
    c.drawString(72, 750, "Sayfa iki: TEKNISYEN CAGRISI BASLATILIR")
    c.showPage()
    c.save()
    return p


@pytest.fixture
def flow_db(conn, pdf_file):
    sha = hashlib.sha256(pdf_file.read_bytes()).hexdigest()
    conn.execute(
        "INSERT INTO documents(id, code, code_key, revision, title, doc_type, body_text, file_path, file_sha256, meta_source)"
        " VALUES (1, 'PR08-UR-3', ?, '01', 'Arıza Süreci', 'PROSES_KARTI', 'x', ?, ?, 'regex')",
        (code_key("PR08-UR-3"), str(pdf_file), sha))
    conn.execute("INSERT INTO entities(id, entity_type, canonical_name, normalized_name, review_status)"
                 " VALUES (1, 'ROL', 'Operatör', 'operator', 'ONAYLANDI')")
    conn.execute("INSERT INTO processes(id, code, name, source, document_id) "
                 "VALUES (1, 'PR08-UR-3', 'Arıza Süreci', 'DOKUMAN', 1)")
    rows = [(1, "Makina duruşu", None, [2], None, "MAKINA DURUSU"),
            (2, "Çözülebiliyor mu?", "Çözülebiliyor mu?", [3, 4], 1, None),
            (3, "Çalıştırılır", None, [], 1, None),
            (4, "Teknisyen çağrısı", None, [], None, "TEKNİSYEN ÇAĞRISI BAŞLATILIR")]
    for seq, name, dec, nxt, role, quote in rows:
        conn.execute("INSERT INTO process_steps(process_id, seq, name, decision, next_steps, responsible_entity_id, quote)"
                     " VALUES (1, ?, ?, ?, ?, ?, ?)", (seq, name, dec, json.dumps(nxt), role, quote))
    conn.commit()
    return conn


def test_pdfrender_and_quote_page_lookup(pdf_file):
    assert pdfrender.page_count(pdf_file) == 2
    img = pdfrender.render_page(pdf_file, 0, scale=1.0)
    assert img.width > 100 and img.height > 100
    assert pdfrender.page_png(pdf_file, 1).startswith(PNG)
    assert pdfrender.find_page(pdf_file, "teknisyen çağrısı başlatılır") == 1
    assert pdfrender.find_page(pdf_file, "olmayan metin burada") is None
    with pytest.raises(IndexError):
        pdfrender.render_page(pdf_file, 5)


def test_get_process_flow_and_cli(flow_db, monkeypatch, capsys):
    p = flow.get_process(flow_db, "pr08-ur-3")
    assert [s["seq"] for s in p["steps"]] == [1, 2, 3, 4] and p["steps"][1]["responsible"] == "Operatör"
    assert 's2 -->|"Evet"| s3' in p["mermaid"]
    assert flow.get_process(flow_db, "YOK") is None
    from types import SimpleNamespace

    from kys import cli
    monkeypatch.setattr(cli, "_conn", lambda: flow_db)
    cli.cmd_flow(SimpleNamespace(code="PR08-UR-3", out=None))
    assert capsys.readouterr().out.startswith("flowchart TD")


@pytest.fixture
def published_flow(flow_db, tmp_path):
    return flow_db, publish_snapshot(flow_db, tmp_path / "pub" / "kys-query.db")


def test_process_endpoints_with_local_pdf(published_flow, monkeypatch, pdf_file):
    _, db_path = published_flow
    # yayın kopyasında yol yalnızca dosya adıdır; orijinal KYS_FILES_DIR'de aranır
    with _client(monkeypatch, db_path, files_dir=pdf_file.parent) as c:
        lst = c.get("/qa/api/processes").json()
        assert lst[0]["code"] == "PR08-UR-3" and lst[0]["step_count"] == 4 and "file_path" not in lst[0]
        p = c.get("/qa/api/processes/PR08-UR-3").json()
        assert p["mermaid"].startswith("flowchart TD") and p["page_count"] == 2 and p["is_pdf"]
        assert [s["page"] for s in p["steps"]] == [1, None, None, 2]
        assert c.get("/qa/api/processes/YOK").status_code == 404
        r = c.get("/qa/api/documents/PR08-UR-3/pages/2.png")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content.startswith(PNG)
        assert c.get("/qa/api/documents/PR08-UR-3/pages/3.png").status_code == 404
        assert c.get("/qa/api/documents/PR08-UR-3/pages/x.png").status_code == 404
        assert c.get("/qa/api/documents/PR08-UR-3/pages/1.jpg").status_code == 404


def test_page_404_without_original_and_pages_dir(published_flow, monkeypatch, tmp_path):
    conn, db_path = published_flow
    with _client(monkeypatch, db_path) as c:  # konteyner: orijinal yok
        assert c.get("/qa/api/documents/PR08-UR-3/pages/1.png").status_code == 404
        p = c.get("/qa/api/processes/PR08-UR-3").json()
        assert p["page_count"] is None and all(s["page"] is None for s in p["steps"])
    # kys publish --pages ile önceden üretilmiş sayfalar
    pdir = tmp_path / "pages"
    assert pages.render_all(conn, pdir, scale=1.0)[1] == 2
    with _client(monkeypatch, db_path, pages_dir=pdir) as c:
        assert c.get("/qa/api/documents/PR08-UR-3/pages/1.png").content.startswith(PNG)
        p = c.get("/qa/api/processes/PR08-UR-3").json()
        assert p["page_count"] == 2 and p["steps"][3]["page"] == 2


def test_flow_endpoints_require_token(published_flow, monkeypatch):
    _, db_path = published_flow
    with _client(monkeypatch, db_path, access_token="gizli") as c:
        assert c.get("/qa/api/processes").status_code == 401
        assert c.get("/qa/api/documents/PR08-UR-3/pages/1.png").status_code == 401
        assert c.get("/qa/api/processes", headers={"Authorization": "Bearer gizli"}).status_code == 200


def test_mcp_get_process_flow(published_flow):
    from mcp import Client
    _, db_path = published_flow

    async def run():
        async with Client(build_server(db_path)) as client:
            return await client.call_tool("get_process_flow", {"code": "PR08-UR-3"})

    assert "flowchart TD" in str(asyncio.run(run()).content)
