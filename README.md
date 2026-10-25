# KYS Sorgu — Kalite Yönetim Sistemi Web İstemcisi

Bu uygulama, Python ile geliştirilmiş KYS (Kalite Yönetim Sistemi) REST API sorgu ve denetim servisinin modern, hafif ve mobil uyumlu **Web İstemcisidir**.

Doküman ayrıştırma, arama, alıntı doğrulama, kural/süreç çıkarımı ve LLM muhakemesi sunucu tarafında çalışır; istemci tüm verileri güvenli REST API üzerinden çeker.

---

## 🚀 Çalıştırma Adımları

### 1. Bağımlılıkların Kurulumu
```bash
npm install
```

### 2. Geliştirme Sunucusunu Başlatma
```bash
npm run dev
```
Uygulama yerel olarak `http://localhost:3000` adresinde çalışmaya başlar.

### 3. Üretim İçin Derleme (Production Build)
```bash
npm run build
npm run preview
```

---

## ⚙️ API_BASE ve Kimlik Doğrulama Ayarları

Uygulama açıldığında sağ üstteki **"Ayarlar"** düğmesine tıklayarak veya ilk `401 Unauthorized` durumunda açılan pencereden bağlantı parametrelerini yapılandırabilirsiniz:

1. **API Base URL (`API_BASE`):**
   - Sunucunuzun kök veya prefix adresidir (örneğin: `https://kys-api.sirket.com` veya ters vekil arkasındaysa `/qa`).
   - Boş bırakılırsa istekler doğrudan mevcut sunucu kök dizinindeki `/api/...` adresine yönlendirilir.
2. **Erişim Token'ı (Bearer Token):**
   - Sunucunun yetkilendirme için beklediği API anahtarı veya Bearer token.
   - İstek başlığı: `Authorization: Bearer <token>`
   - `GET /api/health` dışındaki tüm isteklerde otomatik olarak gönderilir.
   - Yanıtta 401 gelmesi halinde ayarlar ekranı kullanıcıyı bilgilendirmek için otomatik açılır.
3. **Gizlilik ve Güvenlik:**
   - Token ve API adresi yalnızca tarayıcınızın `localStorage` alanında tutulur (`kys_api_base` ve `kys_token`).
   - Kod tabanına, loglara veya depoya hiçbir anahtar ya da şirket dokümanı kaydedilmez.

---

## 📋 Ekranlar ve Yetenekler

1. **Soru Sor (KYS Asistanı):**
   - Doğal dilde soru sorarak KYS bilgi tabanından kaynaklı yanıtlar alın.
   - Alıntı doğrulaması: Sunucu tarafından `verified=false` olarak işaretlenen alıntılar açıkça **"Doğrulanamadı"** rozetiyle gösterilir ("Kanıtsız bulgu yok").
   - Alıntılara tıklayarak doğrudan ilgili dokümanın maddesine gidilebilir.
2. **Ara (Bölüm ve Madde Arama):**
   - `GET /api/search?q=...&limit=20` ile sunucu tabanlı Türkçe metin ve madde arama.
3. **Dokümanlar (Katalog):**
   - Doküman tiplerine göre dinamik filtreleme (`doc_type=PROSEDUR`, `TALIMAT`, vb.).
   - Revizyon, yürürlük durumu ve sorumlu birim görünümü.
4. **Doküman Ayrıntısı:**
   - Bölümler, maddeler, yapılan atıflar ve bu dokümana atıf yapan dokümanlar.
   - Sayfa önizleme desteği (`/api/documents/{code}/pages/{n}.png`).
5. **Süreç & Karar Stüdyosu (Faz 2):**
   - Mermaid kütüphanesiyle dinamik akış diyagramı ve yan yana PDF sayfa görüntüsü.
   - Karar Envanteri & RACI Yetki Matrisi: Karar konusu, rol atamaları (A, R, C, I) ve dayanak onay kuralları.
   - Excel İçe Aktarma: Süreç adımları ve karar matrislerinin Excel üzerinden sisteme yüklenmesi.
   - Ajan 2.1 Eşleştirici: Süreç adımlarının KYS doküman maddeleriyle otomatik eşleştirilmesi ve tek tıkla bağlanması.
6. **Onay Kuyruğu (Faz 1 - İnsan Onayı):**
   - LLM tarafından çıkarılan kural ve varlık önerilerinin incelenmesi (`ONERILDI → ONAYLANDI / DUZELTILDI / REDDEDILDI`).
   - Çıkarılan kural yapısı ile kaynak dokümanın birebir alıntısının yan yana denetlenmesi.
   - Tek tıkla onaylama, modal üzerinden düzeltme ve gerekçeli ret imkanı.
   - Ajan 1.3 tarafından önerilen eş anlamlı rol ve birim adlarının (kanonik ad) tekilleştirilmesi.
7. **Denetim Radarı (Faz 3 - Analiz Motoru):**
   - Deterministik SQL ve LLM yargıçlarıyla sistemdeki yetki aşımı, kural çakışması, iptal forma atıflar ve süreç boşluklarının taranması.
   - Kritik, Orta ve Düşük seviye bulguların izlenmesi ve durum yönetimi (Açık, Kabul, Yanlış Pozitif, Çözüldü).
   - "Tüm Sistemi Denetle" tetikleyicisi.
8. **Uygunluk Kum Havuzu (Faz 3 - Ajan 3.1):**
   - Operasyonel veya satınalma kararlarının KYS prosedürlerine uygunluk simülasyonu.
   - UYGUN / ŞARTLI UYGUN / UYGUN DEĞİL kararı, zorunlu onay makamları, zorunlu formlar ve adımlar.
9. **Eksik Atıflar:**
   - Atıfta bulunulmuş fakat bilgi tabanında henüz tam metni yer almayan doküman kodları.
10. **Koyu / Açık Tema:**
   - Sistem tercihine duyarlı, tek tıkla değiştirilebilir koyu ve açık tema desteği.
   - Mobil ve masaüstü tam uyumluluk (yatay taşma/kaydırma engellenmiştir).

