"""KYS sorgu servisi (konteyner): web sayfası + REST API + MCP uç noktası.

Salt okunur çalışır: veritabanı ofiste üretilir (`kys publish`), konteynere bağlanır veya KYS_DB_URL'den indirilir.
Yollar KYS_BASE_PATH altındadır (varsayılan /qa → paktenops.com/qa):
    GET  /qa/                  web sayfası
    GET  /qa/api/health        durum (kimlik doğrulamasız)
    GET  /qa/api/stats | documents | documents/{code} | search?q= | references
    POST /qa/api/ask           {"question": "..."} → kaynaklı cevap (KYS_MODEL_QUERY)
    GET  /qa/api/processes | processes/{kod}   süreç listesi / adımlar + Mermaid akış metni
    GET  /qa/api/documents/{kod}/pages/{n}.png  PDF sayfası (1 tabanlı)
    *    /qa/mcp               MCP (Streamable HTTP) — herhangi bir yapay zekâ istemcisi bağlanabilir
"""

import hmac
import logging
import sqlite3
import urllib.request
from contextlib import asynccontextmanager, closing
from importlib import resources
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel

from .. import config, db
from ..llm import LLMError
from ..process import flow
from ..query import assistant, catalog, pages
from .mcp_server import build_server

log = logging.getLogger("kys.api")


def ensure_db(path: Path, url: str) -> None:
    """DB dosyası yoksa ve KYS_DB_URL verilmişse indirir (R2/S3 imzalı bağlantı, Drive vb.)."""
    if path.exists() or not url:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".indiriliyor")
    log.info("Veritabanı indiriliyor: %s", url.split("?")[0])
    with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(path)


class AskIn(BaseModel):
    question: str


def _token_ok(header: str | None, token: str) -> bool:
    if not token:
        return True
    supplied = (header or "").removeprefix("Bearer ").strip()
    return hmac.compare_digest(supplied, token)


class _TokenGuard:
    """MCP alt uygulaması için ASGI düzeyinde jeton kontrolü."""

    def __init__(self, app, token: str):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self.token:
            headers = dict(scope.get("headers") or [])
            if not _token_ok(headers.get(b"authorization", b"").decode(), self.token):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"detail":"yetkisiz"}'})
                return
        await self.app(scope, receive, send)


def create_app(db_path: Path | str | None = None) -> FastAPI:
    s = config.settings
    db_path = Path(db_path or s.db_path)
    base = s.base_path.rstrip("/")
    token = s.access_token

    mcp_server = build_server(db_path)
    security = (TransportSecuritySettings(allowed_hosts=list(s.allowed_hosts))
                if s.allowed_hosts else TransportSecuritySettings(enable_dns_rebinding_protection=False))
    mcp_app = mcp_server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True,
                                             json_response=True, transport_security=security)

    @asynccontextmanager
    async def lifespan(_app):
        ensure_db(db_path, s.db_url)
        if not db_path.exists():
            log.warning("Veritabanı yok: %s (kys publish ile üretip bağlayın)", db_path)
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(title="KYS Sorgu Servisi", lifespan=lifespan, docs_url=f"{base}/api/docs-ui",
                  openapi_url=f"{base}/api/openapi.json")

    def conn():
        if not db_path.exists():
            raise HTTPException(503, "Veritabanı henüz yüklenmedi")
        with closing(db.connect(db_path, readonly=True)) as c:
            yield c

    def auth(request: Request):
        if not _token_ok(request.headers.get("authorization"), token):
            raise HTTPException(401, "yetkisiz")

    guarded = [Depends(auth)]

    if base:
        @app.get(base, include_in_schema=False)
        def to_index():
            return RedirectResponse(f"{base}/")

    @app.get(f"{base}/", response_class=HTMLResponse, include_in_schema=False)
    def index():
        return resources.files("kys").joinpath("api/static/index.html").read_text(encoding="utf-8")

    @app.get(f"{base}/api/health")
    def health():
        return {"ok": db_path.exists(), "auth": bool(token), "model": str(s.model_query)}

    @app.get(f"{base}/api/stats", dependencies=guarded)
    def stats(c: sqlite3.Connection = Depends(conn)):
        return catalog.stats(c)

    @app.get(f"{base}/api/documents", dependencies=guarded)
    def documents(doc_type: str | None = None, c: sqlite3.Connection = Depends(conn)):
        return catalog.list_documents(c, doc_type)

    @app.get(f"{base}/api/documents/{{code}}", dependencies=guarded)
    def document(code: str, c: sqlite3.Connection = Depends(conn)):
        d = catalog.get_document(c, code)
        if not d:
            raise HTTPException(404, f"Doküman bulunamadı: {code}")
        return d

    @app.get(f"{base}/api/documents/{{code}}/pages/{{name}}", dependencies=guarded)
    def document_page(code: str, name: str, c: sqlite3.Connection = Depends(conn)):
        stem, dot, ext = name.rpartition(".")
        if ext.lower() != "png" or not stem.isdigit():
            raise HTTPException(404, "Sayfa numarası geçersiz")
        png = pages.page_image(c, code, int(stem))
        if png is None:
            raise HTTPException(404, "Sayfa görüntüsü yok (PDF değil veya orijinal dosya/önceden üretilmiş sayfa bulunamadı)")
        return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})

    @app.get(f"{base}/api/processes", dependencies=guarded)
    def processes(c: sqlite3.Connection = Depends(conn)):
        return [{k: v for k, v in p.items() if k != "file_path"} for p in flow.list_processes(c)]

    @app.get(f"{base}/api/processes/{{code}}", dependencies=guarded)
    def process(code: str, c: sqlite3.Connection = Depends(conn)):
        p = catalog.get_process_flow(c, code)
        if not p:
            raise HTTPException(404, f"Süreç bulunamadı: {code}")
        return p

    @app.get(f"{base}/api/search", dependencies=guarded)
    def search(q: str, limit: int = 20, c: sqlite3.Connection = Depends(conn)):
        return catalog.search(c, q, limit=min(limit, 50))

    @app.get(f"{base}/api/references", dependencies=guarded)
    def references(c: sqlite3.Connection = Depends(conn)):
        return catalog.unresolved_references(c)

    @app.post(f"{base}/api/ask", dependencies=guarded)
    def ask(body: AskIn, c: sqlite3.Connection = Depends(conn)):
        if not body.question.strip():
            raise HTTPException(400, "Soru boş")
        try:
            return assistant.ask(c, body.question[:2000])
        except LLMError as e:
            raise HTTPException(502, f"Model cevap veremedi: {e}") from e

    # API rotaları önce tanımlandı; kalan {base}/* istekleri (yalnızca /mcp) MCP uygulamasına gider.
    app.mount(base or "/", _TokenGuard(mcp_app, token))
    return app


app = create_app()
