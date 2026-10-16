"""KYS sorgu servisi (konteyner): web sayfası + REST API + MCP uç noktası.

Salt okunur çalışır: veritabanı ofiste üretilir (`kys publish`), konteynere bağlanır veya KYS_DB_URL'den indirilir.
Yollar KYS_BASE_PATH altındadır (varsayılan /qa → paktenops.com/qa):
    GET  /qa/                  web sayfası
    GET  /qa/app/              AI Studio web uygulaması (yalnızca KYS_WEB_DIR / web-dist varsa; token istemez)
    GET  /qa/api/health        durum (kimlik doğrulamasız)
    GET  /qa/api/stats | documents | documents/{code} | search?q= | references
    POST /qa/api/decisions/check  multipart `file` (xlsx/csv karar matrisi) → satır başına kaynaklı kontrol (JSON);
                               ?format=xlsx Excel döner; ?offset=&limit= parça parça işleme; `results` alanı ile yalnızca Excel üretimi
    POST /qa/api/ask           {"question": "..."} → kaynaklı cevap (KYS_MODEL_QUERY model zinciri; cevapta `model`)
                               İsteğe bağlı BYOK başlıkları: X-LLM-Provider (gemini|anthropic) + X-LLM-Key.
                               Zincir tükenirse 503 {"detail": ..., "code": "MODEL_YOK"}
    GET  /qa/api/processes | processes/{kod}   süreç listesi / adımlar + Mermaid akış metni
    GET  /qa/api/documents/{kod}/pages/{n}.png  PDF sayfası (1 tabanlı)
    *    /qa/mcp               MCP (Streamable HTTP) — herhangi bir yapay zekâ istemcisi bağlanabilir
"""

import hmac
import json
import logging
import sqlite3
import urllib.request
from contextlib import asynccontextmanager, closing
from importlib import resources
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel

from .. import config, db
from ..llm import LLMError, LLMUnavailable
from ..process import decisions, flow, matrix_io
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


# Web uygulaması API adresi ayarlanmamışsa (localStorage kys_api_base boş) bulunduğu yolun üstünü kullanır:
# https://host/qa/app/ → https://host/qa (paktenops.com/qa proxy'sinde de çalışır). Kullanıcı değer girdiyse dokunmaz.
_API_BASE_SCRIPT = (
    "<script>try{if(!localStorage.getItem('kys_api_base')){localStorage.setItem('kys_api_base',"
    r"location.origin+location.pathname.replace(/\/app(\/.*)?$/,''));}}catch(e){}</script>"
)


def find_web_dir(configured: Path | None) -> Path | None:
    """Derlenmiş web uygulaması klasörü: KYS_WEB_DIR, yoksa /app/web, yoksa yerel web-dist (build_web.py çıktısı)."""
    for cand in (configured, Path("/app/web"), config.LOCAL_HOME / "web-dist"):
        if cand and (cand / "index.html").is_file():
            return cand
    return None


def _add_web_routes(app: FastAPI, base: str, web_dir: Path) -> None:
    """{base}/app altında statik web uygulaması + SPA geri dönüşü. Token istemez (veri API'den token'la gelir)."""
    index_html = (web_dir / "index.html").read_text(encoding="utf-8")
    head = index_html.lower().find("<head>")
    page = (index_html[:head + 6] + _API_BASE_SCRIPT + index_html[head + 6:]) if head >= 0 else _API_BASE_SCRIPT + index_html
    no_cache = {"Cache-Control": "no-cache"}

    @app.get(f"{base}/app", include_in_schema=False)
    def app_redirect():
        return RedirectResponse(f"{base}/app/")

    @app.get(f"{base}/app/", include_in_schema=False)
    def app_index():
        return HTMLResponse(page, headers=no_cache)

    @app.get(f"{base}/app/{{path:path}}", include_in_schema=False)
    def app_file(path: str):
        f = (web_dir / path).resolve()
        if f.is_file() and f.is_relative_to(web_dir) and f.name != "index.html":
            immutable = path.startswith("assets/")
            return FileResponse(f, headers={"Cache-Control": "public, max-age=31536000, immutable" if immutable
                                            else "public, max-age=3600"})
        if "." in path.rsplit("/", 1)[-1]:  # eksik dosya (js/css/png...) index.html olarak dönmesin
            raise HTTPException(404, "Dosya yok")
        return HTMLResponse(page, headers=no_cache)  # SPA geri dönüşü


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
        with closing(db.connect(db_path, readonly=True, immutable=True)) as c:
            yield c

    def auth(request: Request):
        if not _token_ok(request.headers.get("authorization"), token):
            raise HTTPException(401, "yetkisiz")

    guarded = [Depends(auth)]

    if s.cors_origins:  # boşsa CORS kapalı; kimlik bilgisi (çerez) yok, jeton başlıkla gelir
        app.add_middleware(CORSMiddleware, allow_origins=list(s.cors_origins), allow_credentials=False,
                           allow_methods=["GET", "POST", "OPTIONS"],
                           allow_headers=["Authorization", "Content-Type", "X-LLM-Provider", "X-LLM-Key"])

    if base:
        @app.get(base, include_in_schema=False)
        def to_index():
            return RedirectResponse(f"{base}/")

    @app.get(f"{base}/", response_class=HTMLResponse, include_in_schema=False)
    def index():
        return resources.files("kys").joinpath("api/static/index.html").read_text(encoding="utf-8")

    web_dir = find_web_dir(s.web_dir)
    if web_dir:
        _add_web_routes(app, base, web_dir.resolve())

    @app.get(f"{base}/api/health")
    def health():
        return {"ok": db_path.exists(), "auth": bool(token), "model": ",".join(str(m) for m in s.model_query)}

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
    def ask(body: AskIn, c: sqlite3.Connection = Depends(conn),
            provider: str | None = Header(None, alias="X-LLM-Provider"),
            key: str | None = Header(None, alias="X-LLM-Key")):
        if not body.question.strip():
            raise HTTPException(400, "Soru boş")
        byok = None
        if provider or key:
            provider = (provider or "").strip().lower()
            if provider not in config.BYOK_PROVIDERS or not (key or "").strip():
                raise HTTPException(400, "X-LLM-Provider (" + "|".join(config.BYOK_PROVIDERS) + ") ve X-LLM-Key birlikte verilmeli")
            byok = (provider, key.strip())
        try:
            return assistant.ask(c, body.question[:2000], byok=byok)
        except LLMUnavailable as e:
            # Hata metni anahtarı içermez (llm.structured maskeler); yine de BYOK anahtarı ayrıca temizlenir.
            detail = str(e).replace(byok[1], "***") if byok else str(e)
            log.warning("Model zinciri tükendi: %s", detail)
            return JSONResponse(status_code=503, content={
                "detail": "Model şu an kullanılamıyor: " + detail, "code": "MODEL_YOK"})
        except LLMError as e:
            raise HTTPException(502, f"Model cevap veremedi: {e}") from e

    @app.post(f"{base}/api/decisions/check", dependencies=guarded)
    def decisions_check(file: UploadFile = File(...), format: str = Query("json", pattern="^(json|xlsx)$"),
                        offset: int = Query(0, ge=0), limit: int | None = Query(None, ge=1, le=decisions.MAX_ROWS),
                        results: str | None = Form(None), c: sqlite3.Connection = Depends(conn),
                        provider: str | None = Header(None, alias="X-LLM-Provider"),
                        key: str | None = Header(None, alias="X-LLM-Key")):
        """Karar matrisi (xlsx/csv) → her karar için kaynaklı kontrol. Dosya saklanmaz.

        `offset`/`limit` ile satırlar parça parça işlenebilir (uzun istek zaman aşımını önler). `format=xlsx` ile Excel döner;
        `results` (önceden alınmış satır sonuçları JSON listesi) verilirse LLM çağrısı yapılmaz, yalnızca Excel üretilir."""
        data = file.file.read(decisions.MAX_FILE_BYTES + 1)
        filename = file.filename or "matris.xlsx"
        xlsx_headers = {"Content-Disposition": "attachment; filename*=UTF-8''" + quote(Path(filename).stem + "_kontrol.xlsx")}
        xlsx_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        byok = None
        try:
            if results is not None:
                try:
                    given = json.loads(results)
                except ValueError as e:
                    raise HTTPException(400, "results geçerli bir JSON değil") from e
                if not isinstance(given, list):
                    raise HTTPException(400, "results bir satır listesi olmalı")
                return Response(decisions.render_results(data, filename, given), media_type=xlsx_type, headers=xlsx_headers)
            if provider or key:
                provider = (provider or "").strip().lower()
                if provider not in config.BYOK_PROVIDERS or not (key or "").strip():
                    raise HTTPException(400, "X-LLM-Provider (" + "|".join(config.BYOK_PROVIDERS) + ") ve X-LLM-Key birlikte verilmeli")
                byok = (provider, key.strip())
            res = decisions.analyze_matrix(c, data, filename, byok=byok, offset=offset, limit=limit)
            if format == "xlsx":
                return Response(matrix_io.render_xlsx(res.parsed, res.rows, res.summary), media_type=xlsx_type,
                                headers=xlsx_headers)
            return res.to_json() | {"aralik": {"baslangic": offset, "adet": len(res.rows), "toplam": res.summary["toplam_satir"]}}
        except decisions.MatrixError as e:
            raise HTTPException(413 if "en çok" in str(e) else 422, str(e)) from e
        except LLMUnavailable as e:
            detail = str(e).replace(byok[1], "***") if byok else str(e)
            log.warning("Model zinciri tükendi: %s", detail)
            return JSONResponse(status_code=503, content={
                "detail": "Model şu an kullanılamıyor: " + detail, "code": "MODEL_YOK"})
        except LLMError as e:
            raise HTTPException(502, f"Model cevap veremedi: {e}") from e

    # API rotaları önce tanımlandı; kalan {base}/* istekleri (yalnızca /mcp) MCP uygulamasına gider.
    app.mount(base or "/", _TokenGuard(mcp_app, token))
    return app


app = create_app()
