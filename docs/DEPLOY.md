# KYS Sorgu Servisi — Yayın Rehberi

İşleme ve sorgu birbirinden ayrıdır:

```
Ofis PC (işleme, ara sıra açık)                Bulut (sorgu, 7/24, PC'den bağımsız)
┌───────────────────────────────┐   publish    ┌──────────────────────────────────────┐
│ kys ingest / classify (Ollama)│ ───────────▶ │ Konteyner: ghcr.io/ak21039/kys-agent │
│ kural çıkarımı (Faz 1)        │  kys-query.db│  /qa/        web sayfası             │
│ SQLite (yazılabilir)          │              │  /qa/api/*   REST API                │
└───────────────────────────────┘              │  /qa/mcp     MCP (her yapay zekâ)    │
                                               └──────────────────────────────────────┘
```

Konteyner salt okunurdur, işlemci gerektirmez (arama SQLite'ta, cevap üretimi dış modelde).

## Ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `KYS_DB_PATH` | `/data/kys.db` | Veritabanı dosyası (bağlanan disk) |
| `KYS_DB_URL` | — | Dosya yoksa açılışta buradan indirilir (R2/S3 imzalı bağlantı vb.) |
| `KYS_ACCESS_TOKEN` | — | Doluysa `/api` ve `/mcp` için `Authorization: Bearer <anahtar>` gerekir |
| `KYS_BASE_PATH` | `/qa` | Yol öneki → `paktenops.com/qa` |
| `KYS_ALLOWED_HOSTS` | — | MCP için Host beyaz listesi, ör. `paktenops.com` |
| `KYS_MODEL_QUERY` | `anthropic:claude-haiku-5-5` | Web asistanının modeli (aşağıya bakın) |
| `ANTHROPIC_API_KEY` | — | `anthropic:` sağlayıcısı için |
| `KYS_OPENAI_BASE_URL`, `KYS_OPENAI_API_KEY` | — | `openai:` sağlayıcısı için (OpenAI uyumlu herhangi bir uç nokta) |
| `PORT` | `8080` | Platform belirler (Cloud Run vb.) |

### Modeli değiştirmek (Claude'a bağımlı değil)

```bash
KYS_MODEL_QUERY=anthropic:claude-haiku-5-5                       # şu an
KYS_MODEL_QUERY=openai:glm-4.5-flash                             # + KYS_OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
KYS_MODEL_QUERY=openai:gemini-2.5-flash                          # + https://generativelanguage.googleapis.com/v1beta/openai
KYS_MODEL_QUERY=openai:@cf/meta/llama-3.3-70b-instruct-fp8-fast  # + https://api.cloudflare.com/client/v4/accounts/<id>/ai/v1
KYS_MODEL_QUERY=ollama:gemma4:latest                             # + OLLAMA_URL (Ollama erişilebilir bir makinedeyse)
```

Ücretsiz katmanlarda sağlayıcının verileri eğitimde kullanıp kullanmadığını kontrol edin.

### Yapay zekâ istemcilerini MCP ile bağlamak

MCP adresi: `https://<alan-adı>/qa/mcp` (Streamable HTTP). Araçlar: `search_documents`, `get_document`,
`list_documents`, `missing_references`, `knowledge_base_stats`. Cevabı istemcinin kendi modeli üretir; bu servis
yalnızca veriyi verir.

- **Claude Code / Gemini CLI / Cursor / VS Code:** URL + `Authorization: Bearer <anahtar>` başlığı.
- **claude.ai, ChatGPT web bağlayıcıları:** sabit anahtar yerine OAuth isterler. Yayında Cloudflare Access
  (OAuth) önüne konarak çözülecek.

## Yayın akışı

```powershell
kys publish     # %LOCALAPPDATA%\kys-agent\publish\kys-query.db üretir (yerel yollar ve LLM logları çıkarılır)
```

Dosyayı konteynerin okuyacağı yere yükleyin (bağlı disk veya `KYS_DB_URL` ile erişilen gizli depolama) ve
konteyneri yeniden başlatın.

## Barındırma seçenekleri (karar bekliyor)

| Platform | Ücret | Not |
|---|---|---|
| Google Cloud Run | Ücretsiz kota (kart gerekli) | Boştayken sıfıra iner, ilk istekte birkaç sn bekleme. DB: Cloud Storage. |
| Koyeb / Render | Ücretsiz küçük örnek | Render 15 dk boşta uyur. |
| Hugging Face Spaces (Docker) | Ücretsiz CPU | 48 saat kullanılmazsa uyur; gizli Space yapılabilir. |
| Cloudflare Containers | Workers Paid (5 $/ay) | Alan adıyla aynı yerde; en az parça. |
| Herhangi bir VPS | Değişken | `docker run -p 8080:8080 -v ./data:/data ghcr.io/ak21039/kys-agent` |

`paktenops.com/qa` yolu, hangi platform seçilirse seçilsin Cloudflare'de bir yönlendirme kuralı (Worker route
veya Origin Rule) ile konteynere bağlanır. Cloudflare Access ile e-posta tabanlı giriş eklenir.

## Yerelde deneme

```powershell
kys serve --port 8000     # http://localhost:8000/qa/
```
