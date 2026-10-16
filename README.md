# KYS Sorgu — Kalite Yönetim Sistemi Doküman Sorgu ve Asistan Uygulaması

Kalite Yönetim Sistemi (KYS) dokümanlarını ilişkisel bir bilgi tabanına dönüştüren, arama ve kanıt doğrulamalı asistan servisi sunan React uygulaması.

## Özellikler

1. **Soru Sor (KYS Asistanı)**:
   - Soruya en uygun yürürlükteki doküman ve maddeleri tespit eder.
   - Cevap üretir ve her iddiayı köşeli parantezle kaynak numarasına bağlar.
   - **Kanıtsız bulgu yok**: Alıntıları kaynak metne karşı `verifyQuote` ile karakter katlama (ı/İ, ş, ğ, ü, ö, ç) ve noktalama normalizasyonu yaparak doğrular. Doğrulanamayan alıntılar uyarı ile bildirilir.

2. **Ara (Türkçe Arama Motoru)**:
   - Türkçe karakter katlama ve ek budama algoritması.
   - Doküman kodları, madde numaraları, başlıklar ve gövde metinlerinde hızlı arama.

3. **Dokümanlar (Katalog)**:
   - Doküman tipi bazında filtreleme (El Kitabı, Prosedür, Talimat, Görev Tanımı, Yetki Matrisi, Plan, vb.).
   - Her dokümanın kod, revizyon, başlık, birim ve durum bilgisi.

4. **Eksik Atıflar**:
   - Doküman metinlerinde atıf yapılan ancak sistemde yer almayan doküman kodlarının analizi.
   - Makine/hat adları gibi doküman olmayan referansların ayrıştırılması.

5. **Doküman Detayı**:
   - Üstbilgi, revizyon ve geçerlilik tarihleri, sahip birim.
   - Atıf yaptığı ve atıf yapan doküman bağlantıları.
   - Madde bazlı hiyerarşik bölüm ve içerik görünümü.

## Geliştirme

```bash
npm install
npm run dev
```

Uygulama port 3000 üzerinde çalışır.
