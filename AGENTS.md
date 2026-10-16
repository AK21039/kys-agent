# ⚠️ KESİN KURAL: KULLANICI ONAYI OLMADAN KODLAMA YAPILAMAZ

> **KALICI TALİMAT:**
> 1. Kullanıcının açık ve net onayı olmadan **HİÇBİR kodlama, framework değişikliği, dosya silme veya mimari müdahale YAPILAMAZ.**
> 2. Yapılması planlanan her değişiklik ve işlem önce kullanıcıya gerekçesi, kapsamı ve yöntemiyle açıkça anlatılacaktır.
> 3. Kullanıcı "Onaylıyorum" demeden tek bir satır kod yazılamaz veya değiştirilemez.
> 4. Kaynağı olmayan, doğrulanmamış veya sentetik hiçbir veri sisteme dahil edilemez.

---

# KYS Ajanları ve Geliştirme Rolleri

Bu proje Kalite Yönetim Sistemi (KYS) dokümanlarını ilişkisel bir bilgi tabanına dönüştüren ve üzerinde denetim yapan bir uzman sistemdir.

## Geliştirici Ajanlar:
- `kys-ingest-dev`: Ayrıştırma, bölümleme, metadata ve yükleme hattı
- `kys-extraction-dev`: Kural ve ilişki çıkarımı, varlık çözümleme
- `kys-process-dev`: Süreç ve karar envanteri
- `kys-analysis-dev`: Deterministik SQL kontrolleri ve çakışma analizleri
- `kys-assistant-dev`: Kaynaklı sorgu asistanı
- `kys-ui-dev`: Kullanıcı arayüzü
- `kys-reviewer`: Kod ve değişmezler denetimi
