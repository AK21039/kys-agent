# KYS Ajan Sistemi — Geliştirici Rehberi

Kalite Yönetim Sistemi dokümanlarını ilişkisel bir bilgi tabanına dönüştüren ve üzerinde uygunluk, yetki ve
tutarlılık analizi yapan uygulama. Plan ve fazlar: [docs/PLAN.md](docs/PLAN.md). Kod, yorum ve kullanıcı metinleri
Türkçe alan adlarını kullanır (ontoloji enum değerleri ASCII Türkçe: `PROSEDUR`, `ONAYLANDI`).

## Yapı

- `backend/kys/` — Python paketi
  - `ontology.py` — tüm enum'ların TEK kaynağı (doküman/varlık/kural/ilişki/bulgu tipleri)
  - `schema.sql`, `db.py` — SQLite şeması ve bağlantı (PostgreSQL'e taşınabilir SQL yaz)
  - `textnorm.py` — Türkçe katlama (`fold`) ve alıntı doğrulama (`verify_quote`)
  - `llm.py` — TÜM Claude çağrılarının geçtiği kapı (model seçimi, yapılandırılmış çıktı, loglama)
  - `ingest/` — ayrıştırma, bölümleme, metadata, sınıflandırma, yükleme hattı
  - `overrides.py` — kullanıcı düzeltmeleri (data/kys_overrides.json, DB yeniden kurulsa da korunur)
  - `query/` — salt okunur katalog, arama, kaynaklı asistan (alıntı doğrulamalı)
  - `api/` — sorgu servisi: FastAPI (web + REST) + MCP; konteyner olarak çalışır (Dockerfile, docs/DEPLOY.md)
  - `cli.py` — `kys ...` komutu
- `backend/tests/` — pytest
- `data/` — yerel veritabanı ve şirket dokümanları (git'e girmez)

## Ortam

Proje W: ağ paylaşımında durur. Sanal ortam ve SQLite veritabanı **yerel diskte** tutulur, çünkü ağ sürücüsüne
exe kopyalanamıyor ve SQLite orada güvenilir kilitlenmiyor:
- venv: `%LOCALAPPDATA%\kys-agent\.venv` (kurulum: `pip install -e backend[dev]`)
- veritabanı: `%LOCALAPPDATA%\kys-agent\kys.db` (`KYS_DB_PATH` ile değiştirilebilir)

Ağ paylaşımına .exe/.cmd yazılamaz (EPERM). Çalıştırılabilir her şey yerel venv'de durur.

## Komutlar

PowerShell (kullanıcı):
```powershell
& "$env:LOCALAPPDATA\kys-agent\.venv\Scripts\kys.exe" ingest data\inbox --no-llm
# diğer: docs | show KOD | search "..." | refs | uncoded | set-code ESKI YENI [--rev NN] | stats
```
Bash (geliştirme):
```bash
PY="$LOCALAPPDATA/kys-agent/.venv/Scripts/python.exe"
(cd backend && "$PY" -m pytest -q -p no:cacheprovider)
```

## LLM sağlayıcıları

`KYS_MODEL_FAST` / `KYS_MODEL_SMART` = `saglayici:model`. `ollama:gemma4:latest` (yerel, ücretsiz, ~7 token/sn,
4 GB GPU) hızlı katmanda; `anthropic:claude-sonnet-5-5` akıllı katmanda. Ollama çağrısı `/api/chat` + JSON şema
(`format`) ile yapılır; şema `$ref`'siz gönderilir (`llm._inline_refs`).

## Değişmezler (ihlal eden kod kabul edilmez)

1. **Kanıtsız bulgu yok.** Her kural, eşleşme ve bulgu kaynak taşır: doküman kodu + revizyon + madde/bölüm +
   birebir alıntı. Alıntı `textnorm.verify_quote` ile kaynak metne karşı doğrulanır; tutmayan çıktı atılır veya
   `BELIRSIZLIK` olarak işaretlenir.
2. **Analiz yalnızca güvenilir veriye dayanır:** `YURURLUKTE` dokümanlar ve `ONAYLANDI`/`DUZELTILDI` kurallar.
   Onaysız kurala dayanan bulgu açıkça "doğrulanmamış kaynak" olarak etiketlenir.
3. **LLM yalnızca yargı gerektiren yerde.** Kodla/SQL ile kesin yapılabilen her şey (atıf çözümleme, iptal
   kontrolü, sayısal eşik karşılaştırma) deterministik yapılır.
4. **Enum'lar yalnızca `ontology.py`'de.** Başka yerde string sabit tekrarlanmaz.
5. **Model adları yalnızca `config.py`/`.env`'de.** Kodda `claude-...` stringi geçmez (`settings.model_fast` /
   `settings.model_smart` kullan).
6. **Her Claude çağrısı `llm.py` üzerinden** yapılır. Böylece `llm_calls` tablosuna loglanır (amaç, model, token).
7. **Türkçe arama:** aranabilir metin ve sorgular `textnorm.fold` ile katlanır (ı/İ/i, ş, ğ, ü, ö, ç).
8. **Testlerde gerçek API çağrısı yok.** LLM mock'lanır. Gerçek şirket dokümanı fixture olarak commit edilmez;
   fixture'lar testte üretilir (`tests/conftest.py`: `make_docx`, `make_xlsx`).
9. Şema değişikliği `schema.sql`'e yapılır ve `CREATE ... IF NOT EXISTS` ile idempotent kalır.
   Kolon değişikliği gerekiyorsa `db.py`'deki `MIGRATIONS` listesine eklenir.

## Claude API kullanımı

- Anthropic Python SDK (`anthropic`), yapılandırılmış çıktı için `client.messages.parse(..., output_format=PydanticModel)`.
- Güncel modeller: hızlı `claude-haiku-5-5`, muhakeme `claude-sonnet-5-5`. Bu modellerde assistant prefill ve
  `budget_tokens` yok; `temperature` gönderme.
- `stop_reason` her zaman kontrol edilir (`refusal`, `max_tokens`). `llm.py` bunları istisnaya çevirir.
- Toplu çıkarım Batch API ile yapılır (Faz 1). Uzun ve sabit sistem promptları önbelleklenir.
