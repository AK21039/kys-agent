# KYS Ajan Sistemi — Revize Uygulama Planı

> Sürüm: 1.0 · 2026-10-14
> Kapsam: Kalite Yönetim Sistemi (KYS) dokümanlarını ilişkisel bir bilgi tabanına dönüştürmek; bunun üzerinde
> (1) yeni işlerin KYS'ye uygunluk denetimi, (2) karar envanterinin yetki ve süreçlere uyumu,
> (3) süreçlerdeki çakışma, boşluk ve uyumsuzlukların tespiti. Gelecekteki ihtiyaçlar için genişletilebilir yapı.

---

## 0. Önerilen plana göre değişiklikler (özet)

Önerilen planın yönü doğru: belge arama motoru değil, **ilişkileri bilen** bir bilgi tabanı gerekiyor. Ancak
uygulamada riskli veya gereksiz ağır bulduğum noktaları aşağıdaki gibi değiştirdim:

| # | Önerilen | Revize | Gerekçe |
|---|---|---|---|
| 1 | PostgreSQL + pgvector + Neo4j (3 veri katmanı) | **Tek veritabanı**: Başlangıçta SQLite (FTS5), çok kullanıcıya geçişte PostgreSQL (+pgvector). Graf, `edges` tablosu ve özyinelemeli SQL ile tutulur. | Makinede Docker ve Postgres yok. Bir KYS külliyatı (yüzlerce doküman, on binlerce ilişki) Neo4j gerektirmez. Üç veritabanını senkron tutmak ayrıca hata kaynağı olur. SQL taşınabilir yazılır, Neo4j gerekirse sonradan dışa aktarım olarak eklenir. |
| 2 | LangGraph orkestrasyonu | **Doğrudan Anthropic SDK** + sabit iş akışları (Python kodu). Serbest ajan döngüsü yalnızca Asistan ve Uygunluk Denetçisi'nde. | Hattın çoğu deterministik (yükle → ayrıştır → çıkar → onayla). Ajan çatısı burada karmaşıklık ekler, kontrol kazandırmaz. |
| 3 | "Ajan"lar her işi LLM ile yapıyor | **Üç katmanlı analiz**: (a) deterministik SQL kontrolleri, (b) aday küme üretimi, (c) yalnızca adaylar üzerinde LLM yargısı. | "Yürürlükten kalkmış forma atıf", "sorumlusu olmayan adım", "tanımsız rol" gibi kontroller SQL ile kesin ve bedavadır. "Tüm kuralları birbiriyle çarpıştırmak" n² patlar; kümeleme şart. |
| 4 | Çıkarılan kuralların onayı UI'da bir ayrıntı | **İnsan onay kuyruğu birinci sınıf özellik.** Kural durumu: `ONERILDI → ONAYLANDI / DUZELTILDI / REDDEDILDI`. Analizler onaylı kurallara dayanır, onaysız kaynaklı bulgular etiketlenir. | LLM çıkarımı %100 doğru olmaz. Denetim sistemi yanlış kurala dayanırsa güven kaybolur. |
| 5 | Kaynak gösterme örneklerde var, kural değil | **"Kanıtsız bulgu yok" değişmezi**: her bulgu doküman kodu + revizyon + madde + birebir alıntı taşır. Alıntı, kaynak metinde kodla doğrulanır; tutmazsa bulgu reddedilir. | Halüsinasyona karşı en etkili tek önlem budur. Denetçinin dili de budur. |
| 6 | Varlık çözümleme yok | **Ajan 1.3 Varlık Çözümleyici** eklendi: "Kalite Md.", "Kalite Müdürü", "KYS Sorumlusu" gibi adların tekilleştirilmesi (öneri + kullanıcı onayı). | Rol adları dokümanlarda tutarsız yazılır. Çözülmezse yetki ve çakışma analizleri sessizce yanlış sonuç verir. |
| 7 | Süreçler sürükle-bırak akış şemasıyla giriliyor | **Önce Excel şablonu ile içe aktarma + tablo/form ekranı.** React Flow ilk aşamada görselleştirme amaçlı. | Kalite ekipleri Excel'de çalışır. Akış editörü pahalıdır ve ilk değeri geciktirir. |
| 8 | Ajan 4.2 Haiku ile Text-to-Cypher | Asistan (Sonnet) içinde **salt okunur SQL aracı** + beyaz listeli görünümler. | Serbest sorgu üretimi hataya açık. Salt okunur bağlantı + görünüm katmanı güvenli ve denetlenebilir. |
| 9 | Vektör DB zorunlu | **Önce FTS5 (Türkçe katlamalı trigram) + graf.** Embedding Faz 1b'de opsiyonel ve hibrit. | Doküman kodları (PR-04) ve madde numaraları anahtar kelimeyle bulunur. Modellerin 1M bağlam penceresi, ilgili dokümanların tamamını okutmayı mümkün kılıyor; parça (chunk) RAG'ine bağımlılık azalır. |
| 10 | Değerlendirme yok | **Altın test seti** (Faz 0): kalite ekibinden 20-30 gerçek soru + beklenen cevap/kaynak. Her faz bununla ölçülür. | Ölçmeden "çalışıyor" denemez; prompt değişikliklerinin etkisi görülmez. |
| 11 | Revizyon yönetimi belirsiz | Doküman = (kod, revizyon) çifti. Yeni revizyon eskisini `IPTAL` yapar ve `YERINE_GECER` ilişkisi kurar. | "Güncellik uyumsuzluğu" tespiti bunu gerektirir. |
| 12 | Veri gizliliği yok | Bölüm 7'de ele alındı. | Şirket dokümanları API'ye gidiyor. İmza sirkülerinde kişisel veri (KVKK) var. |

**Model eşlemesi:** Güncel nesil kullanılır: `claude-sonnet-5-5` (muhakeme, analiz) ve `claude-haiku-5-5`
(sınıflandırma, hızlı çıkarım). Sonnet 5.5, Sonnet 5 ile aynı fiyattadır. Model adları yalnızca `.env` / `config.py`
içindedir, tek satırla değiştirilebilir.

---

## 1. Mimari

```
┌────────────────────────── Arayüz (Next.js) ──────────────────────────┐
│ Doküman Merkezi · Onay Kuyruğu · Süreç & Karar Stüdyosu ·            │
│ Uygunluk Kum Havuzu · Denetim Radarı · Asistan                       │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ REST (FastAPI)
┌───────────────────────────────┴──────────────────────────────────────┐
│ Uygulama katmanı (Python)                                            │
│  ingest/   ayrıştırma, bölümleme, metadata, sınıflandırma            │
│  extract/  kural & ilişki çıkarımı, varlık çözümleme                 │
│  process/  süreç & karar envanteri, Excel içe aktarma, eşleştirme    │
│  analysis/ deterministik kontroller + LLM yargıçları                 │
│  assistant/ araç kullanan sohbet ajanı                               │
│  llm.py    TEK LLM kapısı: model seçimi, yapılandırılmış çıktı,      │
│            önbellekleme, loglama, maliyet                            │
└───────────────────────────────┬──────────────────────────────────────┘
┌───────────────────────────────┴──────────────────────────────────────┐
│ Veritabanı (SQLite → PostgreSQL)                                     │
│  documents, sections (+FTS), entities, entity_aliases, rules,        │
│  edges (graf), processes, process_steps, decisions,                  │
│  analysis_runs, findings, llm_calls                                  │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.1 Ontoloji (tek kaynak: `backend/kys/ontology.py`)

- **Doküman tipleri:** EL_KITABI, POLITIKA, PROSEDUR, TALIMAT, PROSES_KARTI, GOREV_TANIMI, YETKI_MATRISI, FORM, LISTE, PLAN, DIS_KAYNAK, DIGER
- **Varlık tipleri:** ROL, BIRIM, SUREC, FORM, KAYIT, SISTEM, KPI, STANDART_MADDESI, DIS_TARAF
- **Kural tipleri:** ONAY, YETKI, SORUMLULUK, SURE, ESIK, ZORUNLU_KAYIT, ZORUNLU_ADIM, YASAK, TETIKLEYICI, BILGILENDIRME
- **İlişki tipleri:** REFERANS_VERIR, YERINE_GECER, KULLANIR, URETIR, SORUMLUDUR, ONAYLAR, YURUTUR, DANISILIR, BILGILENDIRILIR, PARCASIDIR, DAYANAGIDIR, ESLESIR
- **Bulgu tipleri:** CAKISMA, BOSLUK, GUNCELLIK, YETKI_ASIMI, EKSIK_ONAY, UYGUNSUZLUK, BELIRSIZLIK. **Önem:** KRITIK, ORTA, DUSUK

Bir kural örneği (yapılandırılmış):

```json
{
  "rule_type": "ONAY",
  "subject": "Genel Müdür",            // → entities(ROL)
  "action": "onaylar",
  "object": "Satınalma talebi",
  "condition": "tutar > 100.000 TL",
  "threshold": {"value": 100000, "unit": "TRY", "op": ">"},
  "source": {"document": "PR-04", "revision": "03", "clause": "5.2",
             "quote": "Satınalma talebi 100.000 TL'yi aşarsa Genel Müdür onaylar."},
  "status": "ONERILDI"
}
```

---

## 2. Çalışma zamanı ajanları (uygulamanın içindeki LLM rolleri)

| Ajan | Model | Tür | Görev |
|---|---|---|---|
| — Ayrıştırıcı | *(LLM yok)* | Kod | PDF/DOCX/XLSX → metin + üstbilgi + tablolar, madde bazlı bölümleme |
| 1.1 Sınıflandırıcı | Haiku 5.5 | Tek çağrı, yapılandırılmış çıktı | Kod, başlık, tip, revizyon, tarihler, sahip birim. Regex ipuçlarını doğrular ve tamamlar. |
| 1.2 Kural & İlişki Çıkarıcı | Sonnet 5.5 | Doküman başına tek çağrı (Batch API, %50 indirim) | Kurallar, roller, form/kayıt atıfları, doküman atıfları. Her öğe için birebir alıntı. |
| 1.3 Varlık Çözümleyici | Haiku 5.5 → kullanıcı onayı | Tek çağrı | Eş anlamlı rol/birim adlarını kümeler, kanonik ad önerir |
| 2.1 Süreç Eşleştirici | Haiku 5.5 + FTS | Tek çağrı | Kullanıcı süreç adımlarını ilgili doküman maddeleriyle eşleştirme önerisi |
| 3.1 KYS Uygunluk Denetçisi | Sonnet 5.5 | **Araç kullanan ajan** | "Şu işi yapacağım" → ilgili kurallar, zorunlu formlar/adımlar, Uygun / Şartlı / Uygun değil |
| 3.2 Yetki Doğrulayıcı | Kod + Sonnet 5.5 | Deterministik eşleştirme + yargı | Karar envanteri ↔ yetki matrisi / görev tanımı / onay kuralları |
| 3.3 Tutarlılık Analisti | Kod + Haiku ön eleme + Sonnet yargı | Toplu iş | Çakışma, boşluk, güncellik taraması |
| 4.1 Asistan | Sonnet 5.5 | **Araç kullanan ajan** | Serbest sorular. Araçlar: `search_sections`, `get_document`, `graph_neighbors`, `run_readonly_sql`, `list_findings` |

Genişletme (sonraki ajanlar): Revizyon Etki Analizi (graf üzerinde tek sorgu), DÖF Taslakçısı, İç Tetkik Soru Listesi Üretici, ISO 9001 madde eşleme.

### 2.1 Analiz motoru: üç katman

1. **Deterministik kontroller (SQL, LLM yok):**
   - Yürürlükten kalkmış (`IPTAL`) dokümana/forma atıf
   - Sistemde bulunmayan doküman koduna atıf (kırık referans)
   - Sorumlusu veya onaycısı tanımsız süreç adımı
   - Görev tanımı olmayan rol; hiçbir süreçte geçmeyen rol
   - Aynı konu için aynı sahipte farklı eşik/süre değerleri (sayısal karşılaştırma)
   - Karar envanterindeki karar sahibinin, ilgili ONAY/YETKI kuralındaki rolle eşleşmemesi
2. **Aday küme üretimi:** Aynı süreç, aynı rol veya aynı nesneye bağlı kurallar gruplanır. Yalnızca grup içi
   çiftler karşılaştırılır. Haiku ucuz bir ön elemeyle "ilgisiz" çiftleri atar.
3. **LLM yargısı (Sonnet):** Aday çiftte gerçek çakışma var mı, hangisi baskın (hiyerarşi: Politika > Prosedür >
   Talimat; yeni revizyon > eski), öneri nedir. Çıktı yapılandırılmıştır; alıntılar doğrulanır.

---

## 3. Arayüz modülleri

1. **Doküman Merkezi:** yükleme, sürüm geçmişi, ayrıştırma uyarıları (taranmış PDF, .doc formatı), arama
2. **Onay Kuyruğu:** çıkarılan kural/varlık önerileri, alıntı ve kaynakla yan yana. Onayla / Düzelt / Reddet. *(yeni)*
3. **Süreç & Karar Stüdyosu:** Excel içe aktarma, tablo düzenleme, eşleşme önerileri, akış görselleştirme
4. **Uygunluk Kum Havuzu:** yeni iş tanımı → adım adım rapor (Uygun / Şartlı uygun / Uygun değil + kaynaklar)
5. **Denetim Radarı:** bulgular (Kritik/Orta/Düşük). Durum: Açık / Kabul / Yanlış pozitif / Çözüldü. Yanlış pozitif geri bildirimi değerlendirme setine akar.
6. **Asistan:** serbest sorgu, rapor üretimi (Excel/Word dışa aktarım)

---

## 4. Teknoloji yığını

| Katman | Seçim | Not |
|---|---|---|
| Dil / API | Python 3.12, FastAPI | |
| Veritabanı | SQLite (WAL) + FTS5 trigram → PostgreSQL (+pgvector) | SQL taşınabilir tutulur. Geçiş tetikleyicisi: eşzamanlı çok kullanıcı. SQLite dosyası yerel diskte durur (ağ paylaşımında kilitleme güvenilmez). Ekip kullanımında sunucuya PostgreSQL kurulur. |
| Graf | `edges` tablosu + özyinelemeli CTE | Neo4j gerekmez. Gerekirse dışa aktarım. |
| Arama | FTS5 (Türkçe karakter katlama: ı/i, ş/s…) + opsiyonel embedding (Faz 1b) | Embedding seçeneği: Voyage (API) veya yerel bge-m3 |
| LLM | Katman bazında sağlayıcı: hızlı katman **Ollama (gemma4, yerel/ücretsiz)**, akıllı katman **Claude Sonnet** (Anthropic SDK: yapılandırılmış çıktı, önbellek, Batch API) | LangGraph yok. Tamamen yerel mod mümkün (gemma4:31b) ama 4 GB GPU'da yavaş ve kalite düşük; pilotta Claude ile karşılaştırılarak karar verilir. |
| Ayrıştırma | python-docx (üstbilgi dahil), pdfplumber, openpyxl | Docling opsiyonel. Taranmış PDF için OCR sonra. .doc/.xls için LibreOffice dönüştürme. |
| Arayüz | Next.js (React) + shadcn/ui; React Flow (görselleştirme) | Faz 1 sonunda |
| Test | pytest; LLM çağrıları mock'lanır; altın set ayrı "eval" komutuyla | |

---

## 5. Fazlar

Her faz, kullanılabilir bir dikey dilimle biter. Önce **pilot küme**: 20-30 doküman + tek bir süreç ailesi
(ör. Satınalma). Tüm külliyat pilot ölçümleri tuttuktan sonra yüklenir.

> **Güncel durum ve devir notu:** [DURUM.md](DURUM.md) (2026-10-16). Faz 0 tamam; Faz 1'in çıkarım ve yayın kısmı
> tamam (onay kuyruğu ve varlık çözümleme bekliyor); Faz 2'nin karar matrisi kontrolü çalışıyor.

### Faz 0: Temel (≈1 hafta) ✔
- [x] Revize plan, proje yapısı, CLAUDE.md, geliştirme alt ajanları
- [x] Ontoloji, veritabanı şeması, Türkçe metin normalizasyonu, alıntı doğrulayıcı
- [x] Ayrıştırıcılar (DOCX/PDF/XLSX/TXT), bölümleme, regex metadata, CLI ile yükleme + arama
- [x] `llm.py` kapısı + Haiku sınıflandırıcı
- [ ] **Kullanıcıdan:** pilot dokümanlar, doküman kodlama kuralları, API anahtarı, altın test seti

### Faz 1: Doküman Merkezi & Bilgi Çıkarımı (≈3 hafta)
- Pilot dokümanların yüklenmesi; ayrıştırma kalitesi raporu
- Ajan 1.2 (Sonnet) kural/ilişki çıkarımı → Batch API
- Doküman atıflarının deterministik çözümlenmesi (kod eşleştirme)
- Ajan 1.3 varlık çözümleme
- FastAPI + Doküman Merkezi + Onay Kuyruğu ekranları
- **Çıkış ölçütü:** pilot setin çıkarılan kurallarının ≥%85'i kullanıcı tarafından "doğru/küçük düzeltme" olarak onaylanır

### Faz 2: Süreç & Karar Envanteri (≈2 hafta)
- Excel şablonları (süreç adımları, karar envanteri / RACI) + içe aktarma doğrulaması
- Süreç & Karar Stüdyosu ekranı; Ajan 2.1 eşleşme önerileri
- **Çıkış ölçütü:** pilot süreç ailesi tamamen tanımlı ve dokümanlara bağlı

### Faz 3: Analiz Motoru (≈3 hafta)
- Deterministik kontroller (2.1/1)
- Ajan 3.2 Yetki Doğrulayıcı, Ajan 3.3 Tutarlılık Analisti, Ajan 3.1 Uygunluk Denetçisi
- Denetim Radarı + Kum Havuzu ekranları
- **Çıkış ölçütü:** altın setteki bilinen uyumsuzlukların ≥%80'i bulunur, yanlış pozitif oranı ≤%25

### Faz 4: Asistan & Genişleme (≈2 hafta)
- Ajan 4.1 Asistan (araçlarla), rapor dışa aktarma
- Revizyon Etki Analizi ("PR-04 değişirse ne etkilenir?")
- Tüm külliyatın yüklenmesi, maliyet/performans ayarı

---

## 6. Geliştirme alt ajanları (Claude Code)

`.claude/agents/` altında tanımlıdır. Her faz için uzman bir geliştirici ajan vardır. Görevler, Sonnet/Haiku
seviyesinde bir ajanın tek oturumda bitirebileceği büyüklükte bölünür.

| Ajan | Model | Faz | Sorumluluk |
|---|---|---|---|
| `kys-ingest-dev` | sonnet | 0-1 | Ayrıştırıcılar, bölümleme, metadata, yükleme hattı |
| `kys-extraction-dev` | sonnet | 1 | Kural/ilişki çıkarımı, varlık çözümleme, Batch API, onay kuyruğu mantığı |
| `kys-process-dev` | sonnet | 2 | Süreç/karar envanteri, Excel şablon ve içe aktarma, eşleştirme |
| `kys-analysis-dev` | sonnet | 3 | Deterministik kontroller, LLM yargıçları, bulgu modeli |
| `kys-assistant-dev` | sonnet | 4 | Asistan aracı seti, salt okunur SQL görünümleri, raporlama |
| `kys-ui-dev` | sonnet | 1-4 | FastAPI uç noktaları ve Next.js ekranları |
| `kys-test-writer` | haiku | tümü | Test ve fixture yazımı, regresyon testleri |
| `kys-reviewer` | sonnet | tümü | Salt okunur inceleme: CLAUDE.md değişmezlerine ve plana uyum |

---

## 7. Veri gizliliği ve güvenlik

- Dokümanlar Anthropic API'ye gönderilir. Ticari API verileri model eğitiminde kullanılmaz, ancak şirket bilgi
  güvenliği politikası ve KVKK açısından **onay alınmalıdır**.
- İmza sirküleri ve görev tanımlarında kişi adları olabilir. Rol bazlı çalışılır, kişi adları gerekirse maskelenir.
- Gerçek dokümanlar ve veritabanı (`data/`) sürüm kontrolüne girmez.
- Asistanın SQL aracı salt okunur bağlantı ve beyaz listeli görünümlerle çalışır.

## 8. Maliyet tahmini (pilot sonrası güncellenecek)

300 doküman × ortalama 6.000 token ≈ 1,8M token girdi.
- Sınıflandırma (Haiku 5.5): < 1 $
- Kural çıkarımı (Sonnet 5.5, Batch): ≈ 5-10 $ (tek seferlik, revizyonlarda artımlı)
- Analiz ve asistan: kullanım başına sent mertebesi

Maliyet kısıt değil. Asıl kısıt **doğruluk ve izlenebilirlik**. Bütçe bu nedenle onay kuyruğu ve değerlendirmeye ayrılmalıdır.
