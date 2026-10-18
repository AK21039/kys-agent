# AI Studio çalışma düzeni

- `ai` dalı AI Studio'nun çalışma alanıdır. **main'e merge yasak.** Claude Code yararlı parçaları elle alır.
- Sistemin beyni (veritabanı, OCR, kural çıkarımı, analiz, MCP) **main'deki Python servisidir**.
  `ai` dalındaki React uygulaması bu servisin **REST API istemcisidir**; iş mantığını TypeScript'te tekrar yazmaz.
- AI Studio'nun GitHub senkronu çalışma alanını depo köküne yazdığı için `ai` dalında `backend/` bulunmayabilir; bu beklenen durumdur.

## AI Studio'ya verilecek başlangıç promptu

```
Bu proje, Python ile yazılmış bir KYS (Kalite Yönetim Sistemi) sorgu servisinin WEB İSTEMCİSİDİR.
Sunucu tarafı ayrı bir depoda/dalda çalışıyor ve sana REST API olarak verilmiştir. Kurallar:

1. İş mantığını TypeScript'te YENİDEN YAZMA. Doküman ayrıştırma, Türkçe arama, alıntı doğrulama,
   kural/süreç çıkarımı sunucunun işidir. src/utils/textnorm.ts ve src/services/kysStore.ts içindeki yerel
   arama/indeksleme mantığını kaldır; veriyi yalnızca API'den al.
2. Google Drive'dan doğrudan doküman okuma (DriveModal, googleDriveService) ve localStorage'da doküman/veri
   saklama KALDIRILACAK. localStorage'da yalnızca API adresi ve erişim token'ı tutulabilir.
3. Firebase Auth kullanma; kimlik doğrulama tek bir Bearer token ile yapılır (kullanıcı ayarlar ekranına girer).
4. Arayüz dili Türkçe; koyu/açık tema; mobil uyumlu (telefon genişliğinde yatay kaydırma yok).
5. Anahtar, token veya şirket verisini koda, loglara veya depoya YAZMA.

API (tüm yollar API_BASE altında, ör. https://<servis>/qa; /api/health dışındaki her istekte
"Authorization: Bearer <token>" başlığı gönder; 401 gelirse token ekranını aç):
- GET  /api/health                         -> {ok, auth, model}
- GET  /api/stats                          -> doküman/kural/süreç sayıları
- GET  /api/documents?doc_type=TIP          -> doküman listesi (code, revision, title, doc_type, status, ...)
- GET  /api/documents/{code}               -> doküman ayrıntısı: bölümler, atıflar, atıf yapanlar
- GET  /api/documents/{code}/pages/{n}.png -> PDF sayfa görüntüsü (1 tabanlı; token başlığıyla fetch + blob URL)
- GET  /api/processes                      -> süreç listesi (code, name, step_count)
- GET  /api/processes/{code}               -> adımlar (seq, name, responsible, decision, next_steps, quote, page),
                                              mermaid (flowchart metni), page_count, is_pdf
- GET  /api/search?q=...&limit=20          -> eşleşen bölümler (doküman kodu, madde no, metin)
- GET  /api/references                     -> çözülmemiş doküman atıfları
- POST /api/ask  {"question": "..."}       -> {answer, yeterli_bilgi, citations:[{doc_code, revision, clause_no, quote, verified}]}
Kodda "#" geçebilir (ör. PR12-PRJ-6#2): yol parametresinde encodeURIComponent kullan.

İlk görev: mevcut uygulamayı bu kurallara göre düzelt ve şu ekranları API'ye bağla:
Soru sor (cevap + kaynak alıntıları; verified=false olanları "doğrulanamadı" etiketiyle göster),
Ara, Dokümanlar (filtre: doc_type), Doküman ayrıntısı, Süreçler (mermaid şema + yanında sayfa görüntüsü;
adıma tıklayınca alıntı ve sayfa), Eksik atıflar. API_BASE ve token bir "Ayarlar" ekranından girilsin.
Bitince README.md'ye çalıştırma adımlarını ve API_BASE ayarını yaz.
```

## Sonraki görev örnekleri (tek seferde bir tane)

- Süreçler ekranında Mermaid düğümüne tıklayınca adım kartını açma ve sayfa vurgulama.
- Doküman ayrıntısında "bu dokümana atıf yapanlar" grafiği.

## Karar Matrisi ekranı (API sözleşmesi)

Kullanıcı bir karar matrisi (.xlsx veya .csv; düz tablo ya da RACI) yükler; her karar için KYS dokümanlarındaki
dayanak (doküman kodu, madde, birebir alıntı) ve rol/limit/süre uyumu gösterilir. İş mantığı sunucudadır; istemci yalnızca
yükler ve sonucu çizer. Sunucu dosyayı saklamaz.

```
POST {API_BASE}/api/decisions/check            (multipart/form-data, alan adı: file)
  Başlık:  Authorization: Bearer <token>
           X-LLM-Provider: gemini|anthropic + X-LLM-Key: <anahtar>   (isteğe bağlı BYOK; yalnızca 503 MODEL_YOK sonrası iste)
  Sorgu:   offset=0&limit=12     satırları parça parça işle (uzun istek zaman aşımına uğramasın; önerilen limit 8-12)
           format=json (varsayılan) | xlsx   (xlsx: orijinal dosya + sonuç kolonları + "Karar Kontrol Özeti" sayfası)
  Form:    results=<JSON satır listesi>   (yalnızca format=xlsx ile: önceki parçalardan toplanan satırlar; LLM çağrısı yapılmaz,
           sadece Excel üretilir)
  Sınırlar: dosya <= 5 MB, <= 300 karar satırı (aşılırsa 413), okunamayan dosya/başlık yok 422, model zinciri tükendi
           503 {code:"MODEL_YOK"} (BYOK formunu aç), 401 token.
```

Yanıt (JSON):

```
{ "ozet": {toplam_satir, kontrol_edilen, durum:{KAYNAKLI,CELISKI,KISMI,KAYNAK_YOK}, dogrulanmamis, atilan_kaynak, modeller},
  "matris": {bicim:"duz"|"raci", sayfa, baslik_satiri, kolon_eslesmesi, raci_rol_kolonlari, harf_anlamlari, atlanan_satir, uyarilar[]},
  "aralik": {baslangic, adet, toplam},
  "satirlar": [{
     satir, no, bolum, karar,
     durum: "KAYNAKLI"|"CELISKI"|"KISMI"|"KAYNAK_YOK",
     aciklama,
     kaynaklar: [{doc_code, revision, title, clause_no, quote, tur:"BOLUM"|"KURAL"|"ADIM", dogrulanmamis, dogrulama, iliski, ...}],
     ilgili: [...],                     // konuyla ilgili ama dayanak olmayan maddeler
     celiskiler: [{alan:"ONAYLAYAN"|"HAZIRLAYAN"|"LIMIT"|"SURE", matris, dokuman, kaynak}],
     dogrulanan_alanlar[], dogrulanamayan_alanlar[],
     dogrulanmamis: bool,               // onaysız (ONERILDI) kurala dayanıyorsa true -> "doğrulanmamış kaynak" etiketi göster
     eslesen_roller: [{girdi, rol, yontem, skor, oneriler:[{ad,skor}], alan}],
     atilan_kaynak, uyarilar[], model }] }
```

Ekran davranışı: dosya seç -> ilk istek `offset=0&limit=12`, yanıttaki `aralik.toplam` bitene kadar `offset` artırarak
devam et; ilerleme çubuğu (işlenen/toplam) ve geçen süre göster. Sonuç tablosu: Satır, Karar, Durum rozeti
(KAYNAKLI yeşil, CELISKI kırmızı, KISMI sarı, KAYNAK_YOK gri), Kaynak (kod + madde). Satıra tıklayınca açıklama, alıntılar,
çelişki ayrıntısı (alan: matriste X, dokümanda Y), rol eşleşmeleri ve uyarılar açılır; `dogrulanmamis` olan kaynaklara
"doğrulanmamış kaynak" etiketi koy. "Excel indir": aynı dosya + `results` (toplanan tüm satırlar) ile `format=xlsx` isteği, yanıtı blob olarak indir.
Tek satırlık kontrol MCP aracı: `check_decision(karar, yetkili?, onaylayan?, limit?)`.

## Ekran görevi: Onay Kuyruğu

AI Studio'ya (React istemci, `ai` dalı) yapıştırmaya hazır Türkçe prompt. Sunucu tarafı (main) tamamlandı; bu görev
yalnızca istemci ekranını API'ye bağlar.

```
Yeni bir ekran ekle: "Onay Kuyruğu". Amaç: sistemin dokümanlardan otomatik çıkardığı kuralların (rules tablosu)
kullanıcı tarafından tek tek veya toplu olarak ONAYLANMASI, DÜZELTİLEREK onaylanması veya REDDEDİLMESİDİR. Bu
olmadan hiçbir kural güvenilir sayılmaz (sistem yalnızca ONAYLANDI/DUZELTILDI kurallara dayanarak analiz yapar).

API (API_BASE altında; her istekte Authorization: Bearer <token>; 401 -> token ekranı):

GET {API_BASE}/api/review/summary
  -> { "durum": {"ONERILDI": 1381, "ONAYLANDI": 0, "DUZELTILDI": 0, "REDDEDILDI": 0},
       "bekleyen_toplam": 1381,
       "dokuman_bekleyen": [{"doc_code":"PR-04","doc_revision":"03","doc_title":"...","bekleyen":12}, ...],
       "tip_bekleyen": {"ONAY": 140, "SURE": 60, ...},
       "yazilabilir": true|false }
  "yazilabilir": false ise bu sunucu salt okunurdur (örn. Cloud Run) -> onayla/düzelt/reddet düğmeleri PASİF,
  ekranın üstünde sabit bir bant göster: "Bu sunucu salt okunur — onaylar yerel `kys serve` ile yapılır."

GET {API_BASE}/api/review/rules?status=ONERILDI&doc_code=&rule_type=&q=&limit=50&offset=0&include_cancelled=false
  status: ONERILDI (varsayılan, bekleyenler) | ONAYLANDI | DUZELTILDI | REDDEDILDI | "" (tümü)
  rule_type: ONAY|YETKI|SORUMLULUK|SURE|ESIK|ZORUNLU_KAYIT|ZORUNLU_ADIM|YASAK|TETIKLEYICI|BILGILENDIRME (boş = tümü)
  q: metinde Türkçe'ye duyarsız arama (statement/quote/condition_text/doküman kodu+başlığı)
  include_cancelled=true: iptal/taslak dokümanlardaki öneriler de gelir (varsayılan yalnız YURURLUKTE doküman)
  -> { "toplam": 1381, "kurallar": [{
        "id": 42, "rule_type": "ONAY", "statement": "...", "quote": "...", "clause_no": "4.2",
        "condition_text": null, "threshold_op": ">", "threshold_value": 100000, "threshold_unit": "TRY",
        "action": "onaylar", "object_text": "satınalma talebi", "subject": "Genel Müdür" (veya null),
        "confidence": 0.9, "extracted_by": "claude-sonnet-5-5",
        "review_status": "ONERILDI", "reviewed_by": null, "reviewed_at": null, "review_note": null,
        "doc_code": "PR-04", "doc_revision": "03", "doc_title": "Satınalma Prosedürü", "doc_status": "YURURLUKTE"
     }, ...] }

POST {API_BASE}/api/review/rules/{id}   body: {"action": "ONAYLA"|"DUZELT"|"REDDET", "note"?: "...", "reviewer"?: "...",
                                               "edits"?: {"statement":..., "rule_type":..., "threshold_op":...,
                                                          "threshold_value":..., "threshold_unit":..., "condition_text":...}}
  Başarı -> güncellenmiş kural (yukarıdaki satır biçiminde). `quote` ASLA edits içinde gönderilmez (kanıt alıntısı
  değiştirilemez — sunucu 422 ile reddeder). DUZELT en az bir alan ister.
  Hatalar: 404 (kural yok), 422 {"detail": "..."} (geçersiz eylem/alan/değer — mesajı doğrudan göster),
  409 {"detail": "...", "code": "SALT_OKUNUR"} (salt okunur sunucu — üstteki bantı göster, işlemi geri al).

POST {API_BASE}/api/review/rules/bulk   body: {"ids": [1,2,3], "action": "ONAYLA"|"REDDET", "note"?, "reviewer"?}
  En çok 200 id. DUZELT toplu işlemde YOK (yalnız tek tek). -> {"sonuclar": [güncellenmiş kural, ...]}
  Aynı hata kodları (404/422/409).

UI davranışı:
- Üstte özet: "N bekliyor" + durum rozetleri (Önerildi gri, Onaylandı yeşil, Düzeltildi sarı, Reddedildi kırmızı) +
  doküman/tip başına bekleyen sayıları.
- Süzgeçler: durum (select, varsayılan Önerildi), kural tipi (select), doküman kodu (metin), arama kutusu (metin) —
  her değişiklikte offset=0 ile yeniden yükle. Sayfalama: "←  X-Y / Toplam  →" (limit örn. 50).
- Her satır: doküman kodu+revizyon+madde no (tıklanabilir, doküman ayrıntısına gider), kural tipi etiketi, özne rolü,
  statement, **alıntı (quote) her zaman ayrı ve belirgin gösterilir** (kanıt — kullanıcı kararını buna göre verir),
  varsa koşul/eşik, confidence/extracted_by küçük not. İncelenmişse kim/ne zaman/not bilgisi.
- Satır içi işlemler: "Onayla" (tek tıkla, opsiyonel not istemez), "Düzelt" (satır içinde form açılır: statement,
  rule_type, eşik (op+değer+birim), koşul — **quote alanı formda YOKTUR, düzenlenemez**; "Kaydet"/"Vazgeç"),
  "Reddet" (opsiyonel not sorulur). Yalnızca ONERILDI durumundaki satırlarda çoklu seçim kutusu olur; seçili satır
  sayısı + "Toplu Onayla"/"Toplu Reddet" araç çubuğu görünür.
- `yazilabilir=false` iken tüm onay/düzelt/reddet/toplu düğmeleri devre dışı + üstte sabit uyarı bandı (yukarıda
  metni verildi). 409 SALT_OKUNUR hatası gelirse aynı bandı göster (sunucu modu araya değişmiş olabilir).
- Türkçe arayüz, koyu/açık tema, mobilde yatay taşma yok (mevcut diğer ekranlarla aynı tasarım dili).
```
