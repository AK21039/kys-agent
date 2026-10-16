"""MCP sunucusu: KYS bilgi tabanını MCP destekleyen herhangi bir yapay zekâ istemcisine açar
(Claude, ChatGPT, Gemini CLI, Cursor...). Araçlar yalnızca veri döndürür; yorumu istemcinin modeli yapar.
"""

from contextlib import closing

from mcp.server.mcpserver import MCPServer

from .. import db
from ..config import settings as _boot_settings
from ..query import catalog

INSTRUCTIONS = (
    "Şirketin Kalite Yönetim Sistemi (KYS) doküman bilgi tabanı: prosedürler, talimatlar, formlar, görev "
    "tanımları, süreç akışları. Cevap verirken her iddia için doküman kodu ve madde numarası göster. "
    "Önce search_documents ile ilgili bölümleri bul, gerekirse get_document ile dokümanın tamamını oku."
)


def build_server(db_path=None) -> MCPServer:
    server = MCPServer(name="kys", title="KYS Bilgi Tabanı", instructions=INSTRUCTIONS)

    def conn():
        return db.connect(db_path or _boot_settings.db_path, readonly=True, immutable=True)

    @server.tool(description="KYS dokümanlarında tam metin arama. Türkçe karaktersiz yazılabilir. "
                             "Her sonuç doküman kodu, revizyon, madde numarası ve metin içerir.")
    def search_documents(query: str, limit: int = 15) -> list[dict]:
        with closing(conn()) as c:
            return catalog.search(c, query, limit=min(limit, 50))

    @server.tool(description="Bir dokümanın tamamını getirir: kimlik bilgileri, bölümleri, atıf yaptığı ve "
                             "kendisine atıf yapan dokümanlar. Örnek kod: 'PR.BK-01', 'GT-161'.")
    def get_document(code: str) -> dict:
        with closing(conn()) as c:
            return catalog.get_document(c, code) or {"error": f"Doküman bulunamadı: {code}"}

    @server.tool(description="Yürürlükteki dokümanları listeler. doc_type ile filtrelenebilir: PROSEDUR, TALIMAT, "
                             "FORM, GOREV_TANIMI, PROSES_KARTI, PLAN, LISTE, POLITIKA, YETKI_MATRISI, DIGER.")
    def list_documents(doc_type: str | None = None) -> list[dict]:
        with closing(conn()) as c:
            return [{k: d[k] for k in ("code", "revision", "title", "doc_type", "owner_unit")}
                    for d in catalog.list_documents(c, doc_type)]

    @server.tool(description="Dokümanlarda atıf yapılan ama sistemde bulunmayan doküman kodları "
                             "(eksik/yüklenmemiş doküman veya yanlış yazılmış kod).")
    def missing_references() -> dict:
        with closing(conn()) as c:
            return catalog.unresolved_references(c)

    @server.tool(description="Bilgi tabanının özeti: doküman sayıları, tip dağılımı, son güncelleme.")
    def knowledge_base_stats() -> dict:
        with closing(conn()) as c:
            return catalog.stats(c)

    @server.tool(description="Bir sürecin akışını getirir: adımlar (sorumlu, karar, sonraki adımlar, kaynak alıntı) ve "
                             "Mermaid flowchart metni. Örnek kod: 'PR08-UR-3', 'PR46-PRJ-1'.")
    def get_process_flow(code: str) -> dict:
        with closing(conn()) as c:
            return catalog.get_process_flow(c, code) or {"error": f"Süreç bulunamadı: {code}"}

    return server
