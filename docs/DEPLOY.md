# KYS Sorgu Servisi — Yayın Rehberi

İşleme ve sorgu birbirinden ayrıdır:

```
Ofis PC (işleme, ara sıra açık)                Bulut (sorgu, 7/24, PC'den bağımsız)
┌───────────────────────────────┐   publish    ┌──────────────────────────────────────┐
│ kys ingest / classify (Ollama)│ ───────────▶ │ Cloud Run kys-qa (konteyner)         │
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
| `KYS_PAGES_DIR` | — | Önceden üretilmiş sayfa PNG'leri (`kys publish --pages`) |
| `KYS_PUBLISH_BUCKET` | — | (Ofis PC) `kys scheduled` sonunda yayın+yükleme hedefi `gs://...` |
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

## Canlı kurulum (Google Cloud Run)

| Kaynak | Değer |
|---|---|
| Proje | `gen-lang-client-0066123286` ("KYS Agent", no `268170449963`) |
| Servis | `kys-qa`, bölge `europe-west1`, `--min-instances 0 --max-instances 1`, 512 Mi, 1 vCPU, gen2 |
| Adres | `https://kys-qa-53duzoe3kq-ew.a.run.app/qa/` (API: `/qa/api/*`, MCP: `/qa/mcp`) |
| Veri | Özel bucket `gs://kys-agent-qa-data-268170449963` (tek tip erişim, public erişim engelli): `kys.db`, `pages/` |
| Bağlama | Bucket Cloud Run volume (gcsfuse) olarak **salt okunur** `/data`; `KYS_DB_PATH=/data/kys.db`, `KYS_PAGES_DIR=/data/pages`, `KYS_BASE_PATH=/qa` |
| Servis hesabı | `kys-run@<proje>.iam.gserviceaccount.com`: yalnızca bucket `objectViewer` + iki secret `secretAccessor` |
| Secret'lar | `kys-anthropic-api-key` → `ANTHROPIC_API_KEY`, `kys-access-token` → `KYS_ACCESS_TOKEN` |
| İmaj | Artifact Registry `cloud-run-source-deploy` (Cloud Build ile `--source`); temizlik politikası yalnızca son sürümü tutar |
| Erişim | `--allow-unauthenticated` (IAM açık); uygulama kendi `Authorization: Bearer` anahtarını zorlar (`/qa/api/health` ve `/qa/` hariç) |

Erişim anahtarı yerelde `%LOCALAPPDATA%\kys-agent\access_token.txt` dosyasındadır (repoya girmez). Döndürmek için:
yeni sürüm ekleyin (`gcloud secrets versions add kys-access-token --data-file=-`) ve yeni revizyon başlatın
(`gcloud run services update kys-qa --region europe-west1 --update-env-vars KYS_DB_REV=...`).

Sorgu servisi DB'yi `immutable=1` URI parametresiyle açar (`db.connect(..., immutable=True)`): gcsfuse üzerinde
SQLite kilit/journal dosyası oluşturamaz; yayın kopyası zaten tek dosya ve değişmezdir. **Canlı (yazılan) DB'de
`immutable` kullanılmaz** — yalnızca API/MCP bunu ister.

### Kurulum / yeniden kurulum

`infra/deploy-cloudrun.ps1.txt` tekrar çalıştırılabilir (API'ler, bucket, servis hesabı, roller, secret'lar,
yükleme, imaj, servis, temizlik politikası). W: paylaşımı `.ps1` yazmaya izin vermediği için `.txt` uzantılıdır.
Depo kökünden:

```powershell
& ([scriptblock]::Create((Get-Content -Raw infra\deploy-cloudrun.ps1.txt)))            # tam kurulum
& ([scriptblock]::Create((Get-Content -Raw infra\deploy-cloudrun.ps1.txt))) -SkipBuild  # imajı üretme, ayarı/veriyi güncelle
```

Secret'lar zaten varsa değerlerine dokunulmaz; yoksa Anthropic anahtarı yalnızca `.env`'deki `ANTHROPIC_API_KEY`
satırından okunup stdin ile aktarılır, erişim anahtarı rastgele üretilir. Betik hiçbir sır içermez.

## Yayın akışı (veri güncelleme)

```powershell
kys publish --pages --upload gs://kys-agent-qa-data-268170449963
```

1. `kys-query.db` (LLM logları silinmiş, dosya yolları yalnızca ad) ve `pages/` PNG'leri üretilir
   (`%LOCALAPPDATA%\kys-agent\publish\`).
2. `gcloud storage cp` / `rsync` ile bucket'a yüklenir (`gcloud` PowerShell alt süreciyle çağrılır; cmd gerekmez,
   ADC gerekmez — `gcloud auth login` oturumu yeter).
3. `gcloud run services update kys-qa --update-env-vars KYS_DB_REV=<zaman>` ile **yeni revizyon** başlatılır.
   Gerekçe: gcsfuse metadata önbelleği tuttuğu ve DB `immutable` açıldığı için çalışan örnek dosya değişince
   eski/karışık içerik görebilir; yeni revizyon temiz bağlama ve tutarlı veri garantiler. Trafik otomatik geçer.
   `--no-restart` ile atlanır (bu durumda servisi elle yenileyin).

Zamanlanmış görev: `KYS_PUBLISH_BUCKET=gs://...` tanımlıysa `kys scheduled` yükle + sınıflandır sonrasında aynı
yayın+yüklemeyi yapar. Hata olursa yalnızca zamanlı görev loguna yazılır, görev düşmez.
`KYS_RUN_SERVICE` / `KYS_RUN_REGION` varsayılanları `kys-qa` / `europe-west1`.

## Maliyet ve güvenlik notları

- Sıfıra iner (`min-instances 0`), tek örnek (`max-instances 1`); boştayken işlemci ücreti yok. İlk istekte soğuk
  başlangıç birkaç saniye. Ücretsiz kota (180 bin vCPU-sn, 2 milyon istek/ay) bu kullanımı rahatça karşılar.
- Asıl değişken maliyet `/qa/api/ask` çağrılarındaki Haiku token'larıdır (Anthropic faturası, GCP'den ayrı).
- Depolama ~46 MB (bucket) + tek imaj (~80 MB Artifact Registry, ilk 0,5 GB ücretsiz); Secret Manager 2 sır
  (ilk 6 sürüm ücretsiz).
- **Bütçe kesici** (`infra/billing-kill`): aylık 50 TL bütçe aşılınca projenin faturalandırmasını kapatır; Cloud Run
  durur, veri silinmez. Yeniden açmak elle yapılır.
- Anahtar yanlış ellere geçerse secret'ı döndürün; bucket hiçbir zaman public yapılmaz.

## Diğer barındırma seçenekleri (referans)

| Platform | Ücret | Not |
|---|---|---|
| Koyeb / Render | Ücretsiz küçük örnek | Render 15 dk boşta uyur. |
| Hugging Face Spaces (Docker) | Ücretsiz CPU | 48 saat kullanılmazsa uyur; gizli Space yapılabilir. |
| Cloudflare Containers | Workers Paid (5 $/ay) | Alan adıyla aynı yerde. |
| Herhangi bir VPS | Değişken | `docker run -p 8080:8080 -v ./data:/data ghcr.io/ak21039/kys-agent` |

`paktenops.com/qa` yolu, Cloudflare'de bir yönlendirme kuralı (Worker route veya Origin Rule) ile Cloud Run adresine
bağlanır (`KYS_ALLOWED_HOSTS=paktenops.com` ile MCP Host listesi). Cloudflare Access ile e-posta tabanlı giriş eklenir.

## Yerelde deneme

```powershell
kys serve --port 8000     # http://localhost:8000/qa/
```
