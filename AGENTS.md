# ⚠️ KESİN KURAL: KULLANICI ONAYI OLMADAN KODLAMA YAPILAMAZ

> **KALICI TALİMATLAR (DEĞİŞTİRİLEMEZ):**
> 1. **DİL VE MİMARİ:** Dil kesinlikle **Python** kalacaktır. `backend/` yapısı ve `CLAUDE.md` kuralları eksiksiz korunacaktır.
> 2. **GÖREV SINIRI:** Yalnızca kullanıcının açıkça verdiği görev yapılacaktır; inisiyatif alarak başka framework'e çevirme, mimari dönüştürme veya fazladan işlem yapılamaz.
> 3. **AÇIK KULLANICI ONAYI:** Kullanıcının açık ve net onayı olmadan **HİÇBİR kodlama, framework değişikliği, dosya silme veya mimari müdahale YAPILAMAZ.**
> 4. **AÇIKLAMA VE ONAY İSTEMİ:** Yapılması planlanan her değişiklik ve işlem önce kullanıcıya gerekçesi, kapsamı ve yöntemiyle açıkça anlatılacak ve kullanıcının onayı istenecektir. Kullanıcı "Onaylıyorum" demeden tek bir satır kod yazılamaz veya değiştirilemez.
> 5. **KAYNAK VE DOĞRULAMA:** Kaynağı olmayan, doğrulanmamış veya sentetik hiçbir veri sisteme dahil edilemez ("Kanıtsız bulgu yok").

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

## Git ve Dağıtım
Ortamda `GitHub_Personal_Access_Token` tanımlıdır. Depoya push işlemleri şu komutla doğrudan gerçekleştirilir:
```bash
git push https://x-access-token:${GitHub_Personal_Access_Token}@github.com/AK21039/kys-agent.git <dal_adi>
```
Kimlik bilgisi eksikliği gerekçesiyle işlem bekletilmez veya reddedilmez.
