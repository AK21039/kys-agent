# KYS Agent — Durum ve Devir Notu (2026-10-16)

Yeni bir oturum bu dosyayla başlar. Ayrıntı: [PLAN.md](PLAN.md) (fazlar), [DEPLOY.md](DEPLOY.md) (yayın),
[AI_STUDIO.md](AI_STUDIO.md) (ai dalı ve API sözleşmeleri), [../CLAUDE.md](../CLAUDE.md) (kurallar, komutlar).

## Canlı sistem

| Bileşen | Adres / yer |
|---|---|
| Sorgu servisi (Cloud Run `kys-qa`, europe-west1) | https://kys-qa-53duzoe3kq-ew.a.run.app/qa/ (eski arayüz), `/qa/app/` (AI Studio arayüzü), `/qa/mcp` |
| Cloudflare | `qa.paktenops.com` (custom domain), `paktenops.com/qa*` (route, Access korumalı) → Worker `qa` |
| GCP projesi | `gen-lang-client-0066123286` ("KYS Agent"), PrePay faturalandırma; 50 TL bütçe kesici (`infra/billing-kill`) |
| Veri kopyası | `gs://kys-agent-qa-data-268170449963` (özel): `kys.db` + `pages/` |
| Secret Manager | `kys-access-token`, `kys-anthropic-api-key`, `kys-gemini-api-key` (PrePay projesinde oluşturuldu) |
| Sorgu modeli zinciri | `gemini-3.6-flash → gemini-3.1-flash-lite → claude-haiku-5-5`; hepsi düşerse 503 `MODEL_YOK` + BYOK |

## Bu PC'ye bağlı olanlar (uzak oturum erişemez)

- Kod: `W:\KYS Agent` (= `\\10.10.10.25\Proje\KYS Agent`), GitHub `AK21039/kys-agent` (main).
- venv + yazılabilir DB: `%LOCALAPPDATA%\kys-agent\` (`kys.exe`, `kys.db`, `access_token.txt`, `lan_token.txt`).
- `.env` (API anahtarları; asla yazdırılmaz, git'e girmez), şirket dokümanları (`data/`, Drive senkronu).
- Doküman kaynağı: `C:\Users\aydin.kaleoglu\Drive’ım (azekaleoglu@gmail.com)\kys-agent\data\inbox` (`KYS_INBOX_DIR`).
- Ollama (gemma4, sınıflandırma), Word/Excel/Visio COM (eski Office dönüştürme), Windows OCR (Türkçe).
- Betikler (LOCALAPPDATA ve masaüstü): `yayinla.ps1` (DB'yi buluta yayınla), `token-degistir.ps1`.
- Zamanlanmış görev `KYS Agent - Siniflandirma` (`kys.exe scheduled`; cmd kapalı olduğu için doğrudan exe).

## Veri durumu

- 108 yürürlükteki doküman (+ eski sürümler), 9'u 2026-10-16'da eklenen **kodsuz taslak prosedür** (`KODSUZ-xxxx`,
  "Ekim 2026", doküman no boş) — kullanıcıdan kod/yürürlük bilgisi bekleniyor.
- 1381 kural (hepsi `ONERILDI`, onay bekliyor), 30 süreç / 317 adım, 279 rol (çok sayıda yazım varyantı), 344 denetçi gözlemi.
- Düzeltilen kodlar: `PR12-PRJ-6#2 → PR12-PRJ-5` (Malzeme Talebi), `İSG-FR-008`, `İŞ-FR-002` (İSG-FR-002'den farklı form).
- Kural: **yayımlanmış PDF esastır** (Word/Visio ham kaynak eksik olabilir); YP-TL-005 ve ME-TL-001 Word'leri PDF'e eşitlendi.
- PR46-PRJ-1 için verilen Visio Rev.02, PDF Rev.03'ten eski — akış kaynağı yapılmadı.

## Yapılanlar (özet)

- Ingest: DOCX/PDF/XLSX/TXT, OCR, eski .doc/.xls (Word/Excel COM), Visio okuyucu, kod/başlık tespiti, override'lar.
- Çıkarım: Claude Code alt ajanlarıyla 64 doküman (kural, rol, adım, atıf, gözlem) → `extract-import`.
- Sorgu: kaynaklı asistan (alıntı doğrulamalı), arama, doküman/süreç görünümü (Mermaid + PDF sayfası), MCP.
- Karar matrisi kontrolü (`kys karar-kontrol`, `POST /api/decisions/check`, "Karar Matrisi" sekmesi, MCP
  `check_decision`): tüm sayfalar, "Karar Tanımı" kolonu, matristeki doküman kontrolü (DOGRULANDI/DESTEKLEMIYOR/SISTEMDE_YOK),
  birim adı karar verici, ortak onay (A/B).
- Yayın: Cloud Run + gcsfuse salt okunur DB, `publish --pages --upload`, web uygulaması `/qa/app/` (`infra/build_web.py`).

## Son karar matrisi sonucu (`Yatırım ve Bakım.xlsx`, yalnızca "Proje ve Yatırım" sayfası — kullanıcı isteği)

KAYNAKLI 0, ÇELİŞKİ 4, KISMİ 29, KAYNAK YOK 13. Matristeki doküman: 22 doğrulandı, 21 desteklemiyor, 3 sistemde yok
(PR11-SA-2/3/4). KAYNAKLI'nın 0 olmasının ana nedeni: matriste karar verici çoğunlukla birim adı, dokümanlarda unvan →
rol birleştirme gerekiyor. Diğer sayfalar (Planlama, Satınalma, Üretim) ilgili dokümanlar yüklenince işlenecek.

## Öne çıkan bulgular (kullanıcıya raporlandı)

- Mükerrer talimatlar: ME-TL-001/YP-TL-001, ME-TL-005/YP-TL-002, ME-TL-006/YP-TL-003 birebir aynı.
- Kaynak izni çelişkisi: İSG-TL-001 md.3.1.18 (İş Güvenliği Uzmanı izni) ↔ YP-TL-003/ME-TL-006 (izin yok) ↔ SZ-İSG-01 md.16 (bölge yetkilisi).
- Arıza çağrısı: PR.BK-01 md.5.2 (ekip lideri) ↔ PR08-UR-3 (operatör).
- Terfi onayı: PR.İK-07 (Üst Yönetim) ↔ PR.İK-13 (İCKB/YK); terfi kriterleri çelişkisi.
- Görev tanımları: kopya şablonlar, unvan varyantları, vekalet döngüleri, yetki/bütçe alanları boş.

## Açık işler (öncelik sırasıyla)

1. **Rol birleştirme (Faz 3 ilk adım):** kod hazır (2026-10-16, `process/role_merge.py`, `tests/test_role_merge.py`):
   `kys rol-grupla` → `data/rol_gruplari.xlsx` (KARAR EVET/HAYIR, ANA AD) → `kys rol-onayla DOSYA` (önizleme) →
   `--apply`. Eski adlar ana rolün takma adı olur, tüm atıflar (kural, süreç, adım, karar, onay zinciri, kenar) taşınır;
   karar kontrolü (`RoleIndex`) takma adları zaten okuyor. Kararlar `data/kys_role_merges.json` (DB dışında).
   **Bekleyen:** canlı DB'de (bu PC) çalıştırma + kullanıcı onayı + karar matrisini yeniden koşma.
   Sonraki adım: birim ↔ yönetici (örn. "Yatırım ve Bakım" ↔ "Yatırımlar ve Bakım Direktörü") onaylı eşlemesi.
2. **Onay Kuyruğu:** 1381 `ONERILDI` kuralın onay/düzelt/reddet ekranı (API + `/qa/` sekmesi; AI Studio'ya ekran görevi).
3. Kodsuz 9 prosedürün kod ve yürürlük durumu (kullanıcıdan); PR11-SA-2/3/4 dokümanlarının yüklenmesi.
4. Analiz motoru: deterministik çelişki/boşluk taramaları, bulgu raporu.
5. Arama: "kaynak" (kaynak işi/doküman kaynağı) gibi çok anlamlı terimlerde geri getirme zayıf.
6. Cloudflare: Access + Worker `KYS_TOKEN` (token'sız kullanım); workers.dev adresini kapatma.

## Çalışma kuralları (kullanıcı tercihleri)

- İletişim Türkçe. Kısa ve sonuç odaklı; gereksiz uzatma yok.
- Postpay faturadan kesinlikle kaçın; yeni bulut kaynağı/faturalandırma öncesi onay al.
- Şirket verisi dışarı gönderilmez; ücretsiz katman (eğitimde kullanılabilen) LLM anahtarları şirket verisiyle kullanılmaz.
- `ai` dalı AI Studio'nundur, merge yasak; oradan elle beslenilir.
- Alt ajanlar DB'ye yazmaz, dışarı veri göndermez; commit/push/deploy ana oturumda yapılır.
