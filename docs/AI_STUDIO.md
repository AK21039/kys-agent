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
- "Onay Kuyruğu" ekran taslağı (API hazır olunca: önerilen kuralları onayla/düzelt/reddet).
- Doküman ayrıntısında "bu dokümana atıf yapanlar" grafiği.
