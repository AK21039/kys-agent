# KYS Agent — Durum ve Devir Notu (2026-10-18)

Yeni bir oturum bu dosyayla başlar. Ayrıntı: [PLAN.md](PLAN.md) (fazlar), [DEPLOY.md](DEPLOY.md) (yayın),
[AI_STUDIO.md](AI_STUDIO.md) (ai dalı ve API sözleşmeleri), [../CLAUDE.md](../CLAUDE.md) (kurallar, komutlar).

## Canlı sistem

| Bileşen | Adres / yer |
|---|---|
| Sorgu servisi (Cloud Run `kys-qa`, europe-west1) | https://kys-qa-53duzoe3kq-ew.a.run.app/qa/ (eski arayüz), `/qa/app/` (AI Studio arayüzü), `/qa/mcp` |
| Cloudflare | `qa.paktenops.com` (custom domain), `paktenops.com/qa*` (route, Access korumalı) → Worker `qa` |
| GCP projesi | `gen-lang-client-0066123286` ("KYS Agent"), fatura hesabı 017A8D-8EDFD8-8982A6 (Cloud servisleri Postpay, Gemini API Prepay kredisi); bütçe kesici 2026-10-17'de kaldırıldı |
| Veri kopyası | `gs://kys-agent-qa-data-268170449963` (özel): `kys.db` + `pages/` |
| Secret Manager | `kys-access-token`, `kys-anthropic-api-key`, `kys-gemini-api-key` (PrePay projesinde oluşturuldu) |
| Sorgu modeli zinciri | `gemini-3.6-flash → gemini-3.1-flash-lite → claude-haiku-5-5`; hepsi düşerse 503 `MODEL_YOK` + BYOK |

## Bu PC'ye bağlı olanlar (uzak oturum erişemez)

- Kod: `W:\KYS Agent` (= `\\10.10.10.25\Proje\KYS Agent`), GitHub `AK21039/kys-agent` (main).
- venv + yazılabilir DB: `%LOCALAPPDATA%\kys-agent\` (`kys.exe`, `kys.db`, `access_token.txt`). Erişim anahtarı tektir: `access_token.txt` = `.env` = Secret Manager `kys-access-token` = Cloudflare `qa` Worker `KYS_TOKEN` (2026-10-18; ayrı `lan_token.txt` kaldırıldı).
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

## 2026-10-18 gece çalışması (yapılanlar)

- **Rol birleştirme uygulandı** (279 → 267 rol; ayrıntı aşağıda). Karar matrisi ("Proje ve Yatırım") yeniden koşuldu:
  Gemini ücretsiz kotası 12/46 satırda doldu (429). İlk 12 satır: KISMİ 10, KAYNAK YOK 2, KAYNAKLI 0; 11 satır önceki
  koşuyla aynı (satır 12 ÇELİŞKİ→KAYNAK YOK, model farkı). Sonuç: rol birleştirme tek başına KAYNAKLI'yı artırmıyor, çünkü
  karar verici birim adı ("Yatırım ve Bakım"). Darboğaz birim ↔ yönetici eşlemesi. Kısmi sonuç:
  `%LOCALAPPDATA%\kys-tmp\karar-gemini.json` (bakım PC'si). Kalan 34 satır kullanıcı PC'sinde Ollama ile
  `karar-kontrol --sayfa ... --ekle ...` komutuyla tamamlanacak.
- **Onay Kuyruğu** (`review.py`, `/api/review/*`, `/qa/` "Onay Kuyruğu" sekmesi): onayla/düzelt/reddet + toplu işlem;
  alıntı düzenlenemez. Yazma yalnız `KYS_WRITABLE=1` ile yerel `kys serve`'de; Cloud Run salt okunur (409 `SALT_OKUNUR`).
  extract-import artık incelenmiş kuralın ONERILDI ikizini açmıyor. AI Studio ekran promptu: AI_STUDIO.md.
- **Analiz motoru** (`kys analiz`, `backend/kys/analysis/`): 8 deterministik kontrol. Test DB kopyasında 675 bulgu:
  kırık referans 62, sorumlusuz süreç adımı 211, görev tanımı eksik 88 (+155 BELİRSİZLİK), kullanılmayan rol 152
  BELİRSİZLİK (kaynağı izlenemeyen rol), eşik çakışması 1, mükerrer doküman 6 çift (ME-TL-001/YP-TL-001,
  ME-TL-005/YP-TL-002, ME-TL-006/YP-TL-003, ME-TL-007/ME-TL-008, GT-176/GT-186, GT-188/GT-171), iptal dokümana atıf 0,
  karar-yetki: veri yok. Bulgular DB'ye yazılmadı (`--kaydet` ile yazılır; henüz API/ekran yok).
- **Arama**: yakınlık + başlık örtüşmesiyle yeniden sıralama. Altın set (`data/eval/arama_altin.json`, 18 soru)
  MRR 0.903 → 0.972; çok anlamlı alt küme 0.932 → 1.000. Ölçüm: `kys arama-olc`.
- **Cloudflare**: `qa.pakten.workers.dev` HTTP ile 404 / error 1042 döndürüyor (var olmayan worker'la aynı) → kapalı
  doğrulandı. `qa.paktenops.com` Access girişine yönlendiriyor.

## Açık işler (öncelik sırasıyla)

1. **Karar matrisi kalan 34 satır** (Ollama, kullanıcı PC'si), ardından **birim ↔ yönetici onaylı eşlemesi**
   (örn. "Yatırım ve Bakım" ↔ "Yatırımlar ve Bakım Direktörü"; `data/birim_gruplari.xlsx` başlangıç olabilir).
   Rol birleştirme kodu: `process/role_merge.py`, kararlar `data/kys_role_merges.json`.
2. **Onay Kuyruğu kullanımı:** 1381 kuralın incelenmesi kullanıcı PC'sinde (`KYS_WRITABLE=1 kys serve`), sonra yayın.
   AI Studio arayüzüne ekranın eklenmesi (`ai` dalı, prompt AI_STUDIO.md'de).
3. Kodsuz 9 prosedürün kodu/yürürlük bilgisi ve PR11-SA-2/3/4 dokümanları (kullanıcıdan). Not: 9 kodsuz taslak DB'de
   `YURURLUKTE` görünüyor; analiz ve karar kontrolüne giriyorlar.
4. Analiz motoru 2. katman: bulguların DB'ye kaydı + Denetim Radarı (API/ekran), aday kümeler + LLM yargısı.
   BELİRSİZLİK'teki 307 rolün çoğu rol birleştirme ve onay kuyruğuyla azalır.
5. Arama: SZ-İSG-01 md.16 tek uzun blok olarak bölümlenmiş, "kaynak izni" sorgusunda ilk 10'a girmiyor (ingest bölümleme sorunu).

## Çalışma kuralları (kullanıcı tercihleri)

- İletişim Türkçe. Kısa ve sonuç odaklı; gereksiz uzatma yok.
- Postpay faturadan kesinlikle kaçın; yeni bulut kaynağı/faturalandırma öncesi onay al.
- Şirket verisi dışarı gönderilmez; ücretsiz katman (eğitimde kullanılabilen) LLM anahtarları şirket verisiyle kullanılmaz.
- `ai` dalı AI Studio'nundur, merge yasak; oradan elle beslenilir.
- Alt ajanlar DB'ye yazmaz, dışarı veri göndermez; commit/push/deploy ana oturumda yapılır.
