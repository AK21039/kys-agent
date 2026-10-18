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
| `KYS_MODEL_QUERY` | `gemini:gemini-3.6-flash,gemini:gemini-3.1-flash-lite,anthropic:claude-haiku-5-5` | Web asistanının model zinciri; virgülle ayrılır, sırayla denenir (aşağıya bakın) |
| `GEMINI_API_KEY` | — | `gemini:` sağlayıcısı için (Cloud Run'da Secret Manager: `kys-gemini-api-key`) |
| `KYS_CORS_ORIGINS` | — | Tarayıcıdan çağıran istemci adresleri (virgüllü); boşsa CORS kapalı |
| `KYS_REMOTE_TIMEOUT` | `90` | gemini/openai istek zaman aşımı (sn) |
| `ANTHROPIC_API_KEY` | — | `anthropic:` sağlayıcısı için |
| `KYS_OPENAI_BASE_URL`, `KYS_OPENAI_API_KEY` | — | `openai:` sağlayıcısı için (OpenAI uyumlu herhangi bir uç nokta) |
| `KYS_WRITABLE` | — (kapalı) | `1` ise `/api/review/rules*` POST uçları (Onay Kuyruğu: onayla/düzelt/reddet) yazar; kapalıyken 409 `{code:"SALT_OKUNUR"}` döner. Sorgu servisi DB'yi `immutable=1` açtığı için Cloud Run'da **asla** `1` yapılmaz — onaylar yalnızca yerel `kys serve` ile, yazılabilir yerel DB üzerinde yapılır |
| `PORT` | `8080` | Platform belirler (Cloud Run vb.) |

### Model zinciri, BYOK ve CORS

- `KYS_MODEL_QUERY` virgüllü listedir. 429/5xx/zaman aşımı/anahtar yok gibi hatalarda sıradaki model denenir
  (400/401/403 de sıradakine geçer, loglanır). Hepsi düşerse `POST /api/ask` **503** ve
  `{"detail": "...", "code": "MODEL_YOK"}` döner; web arayüzü kullanıcıdan kendi anahtarını ister.
- BYOK: istemci `X-LLM-Provider: gemini|anthropic` ve `X-LLM-Key: <anahtar>` başlıklarını gönderirse zincirin yalnızca
  o sağlayıcıya ait modelleri o anahtarla denenir. Anahtar loglanmaz/saklanmaz; web arayüzünde yalnızca sessionStorage'dadır.
- Cevaptaki `model` alanı cevabı üreten modeli gösterir. Alıntılardaki `doc_code`/`revision`/`clause_no` modelden değil,
  alıntının doğrulandığı bölümden gelir.
- `KYS_CORS_ORIGINS=https://istemci.example,https://baska.example`: izin verilen başlıklar Authorization, Content-Type,
  X-LLM-Provider, X-LLM-Key; çerez/credentials kapalı.
- Cloud Run:

```bash
gcloud run services update kys-qa --region europe-west1   --update-secrets GEMINI_API_KEY=kys-gemini-api-key:latest   --update-env-vars "^@^KYS_MODEL_QUERY=gemini:gemini-3.6-flash,gemini:gemini-3.1-flash-lite,anthropic:claude-haiku-5-5@KYS_CORS_ORIGINS=https://istemci.example"
```

### Modeli değiştirmek (Claude'a bağımlı değil)

```bash
KYS_MODEL_QUERY=anthropic:claude-haiku-5-5                       # şu an
KYS_MODEL_QUERY=openai:glm-4.5-flash                             # + KYS_OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
KYS_MODEL_QUERY=gemini:gemini-3.6-flash                          # + GEMINI_API_KEY (yerleşik Gemini sağlayıcısı)
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

## Web uygulaması (`/qa/app/`)

AI Studio'nun React/Vite istemcisi (`origin/ai` dalı, main'e merge edilmez) aynı Cloud Run servisinde `/qa/app/`
altında yayınlanır. Uygulama yalnızca `/qa/api/*` REST API'sini kullanır; statik dosyalar token istemez, veri token'la gelir.

- `/qa/` eski sade sayfa olarak kalır. Web klasörü yoksa `/qa/app` rotası hiç eklenmez, servis eskisi gibi çalışır.
- API adresi ayarlanmamışsa (`localStorage.kys_api_base` boşsa) sunucu `index.html`'e küçük bir script ekler ve adresi
  bulunduğu yoldan türetir (`https://<host>/qa/app/` → `https://<host>/qa`); `paktenops.com/qa` proxy'sinde de çalışır.
  Kullanıcı başka adres girdiyse dokunulmaz.
- `KYS_WEB_DIR` (imajda `/app/web`; yerelde yoksa `%LOCALAPPDATA%\kys-agent\web-dist`) sunulacak klasördür.
  `assets/*` bir yıl önbelleklenir, `index.html` `no-cache`'tir.

Güncelleme adımları (depo kökünden):

```powershell
& "$env:LOCALAPPDATA\kys-agent\.venv\Scripts\python.exe" infra\build_web.py     # origin/ai -> derle -> web-dist.zip
gcloud run deploy kys-qa --source . --region europe-west1 --project gen-lang-client-0066123286 --quiet
```

`build_web.py`: `origin/ai`'yi fetch eder, `%LOCALAPPDATA%\kys-agent\web-src` altına ayrık git worktree olarak alır,
`npm ci` (node ile `npm-cli.js`) + `vite build --base /qa/app/` çalıştırır; çıktıyı yerel `web-dist\` klasörüne ve depo
kökündeki `web-dist.zip` paketine yazar (içinde `BUILD.txt`: ai commit'i). W: paylaşımı `.js` dosyası yazdırmadığı için
Cloud Build'e giden paket zip'tir; Dockerfile imajda `/app/web` içine açar. `web-dist.zip` yoksa build yine geçer
(web uygulaması yayınlanmaz). Yerel deneme: `kys serve --port 8768` → `http://localhost:8768/qa/app/`.
Doğrulama: `/qa/app/` açılır, `/qa/api/health` 200, tokensız `/qa/api/stats` 401, `/qa/mcp` çalışır.

## Maliyet ve güvenlik notları

- Sıfıra iner (`min-instances 0`), tek örnek (`max-instances 1`); boştayken işlemci ücreti yok. İlk istekte soğuk
  başlangıç birkaç saniye. Ücretsiz kota (180 bin vCPU-sn, 2 milyon istek/ay) bu kullanımı rahatça karşılar.
- Asıl değişken maliyet `/qa/api/ask` çağrılarındaki Haiku token'larıdır (Anthropic faturası, GCP'den ayrı).
- Depolama ~46 MB (bucket) + tek imaj (~80 MB Artifact Registry, ilk 0,5 GB ücretsiz); Secret Manager 2 sır
  (ilk 6 sürüm ücretsiz).
- **Maliyet sınırı:** Gemini API, fatura hesabının Prepay (AI Studio) kredisinden ödenir; kredi bitince yalnızca Gemini
  çağrıları durur ve zincir sıradaki modele geçer. Bütçe kesici (`billing-kill`) 2026-10-17'de kaldırıldı.
- Anahtar yanlış ellere geçerse secret'ı döndürün; bucket hiçbir zaman public yapılmaz.

## Diğer barındırma seçenekleri (referans)

| Platform | Ücret | Not |
|---|---|---|
| Koyeb / Render | Ücretsiz küçük örnek | Render 15 dk boşta uyur. |
| Hugging Face Spaces (Docker) | Ücretsiz CPU | 48 saat kullanılmazsa uyur; gizli Space yapılabilir. |
| Cloudflare Containers | Workers Paid (5 $/ay) | Alan adıyla aynı yerde. |
| Herhangi bir VPS | Değişken | `docker run -p 8080:8080 -v ./data:/data ghcr.io/ak21039/kys-agent` |

## Cloudflare (qa.paktenops.com, paktenops.com/qa)

Ayrı bir Worker (`qa`, kod: `infra/cloudflare-qa-worker.mjs`, panelden yapıştırılır) istekleri Cloud Run'a iletir.
paktenops.com'un kendi Worker'ı (`paktencare-tunnel`, canlı PaktenCare sistemi) **değiştirilmez**.

| Giriş | Tür | Not |
|---|---|---|
| `qa.paktenops.com` | Custom Domain | `/` → `/qa/app/` yönlendirmesi |
| `paktenops.com/qa*` | Route | Yalnızca `/qa` ile başlayan yollar; PaktenCare'in diğer yolları etkilenmez |
| `qa.pakten.workers.dev` | Worker URL | `KYS_TOKEN` tanımlıyken 403 döner; kapatılması önerilir |

- **Token'sız kullanım:** Zero Trust → Access ile ilgili adres(ler) korunur (One-time PIN, e-posta listesi). Access
  uygulamaları adres bazlıdır: `qa.paktenops.com` ve `paktenops.com/qa` için ayrı ayrı tanımlanmalıdır. Access
  kurulduktan sonra Worker'a `KYS_TOKEN` secret'ı eklenir; Worker Authorization başlığını kendisi ekler.
  **Sıra önemli:** Access'siz `KYS_TOKEN` eklemek veriyi herkese açar.
- MCP istemcileri Access'ten geçemez; MCP için Cloud Run adresi + Bearer token kullanılır.
- Kurumsal DNS yeni alt alan adını geç öğrenebilir; doğrulama için `nslookup qa.paktenops.com 1.1.1.1`.

## Yerelde deneme

```powershell
kys serve --port 8000     # http://localhost:8000/qa/
```
