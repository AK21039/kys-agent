"""KYS ontolojisi: tüm tip ve durum sabitlerinin tek kaynağı.

Değerler ASCII Türkçe tutulur (veritabanında ve promptlarda aynen kullanılır).
"""

from enum import StrEnum


class DocType(StrEnum):
    EL_KITABI = "EL_KITABI"          # Kalite El Kitabı
    POLITIKA = "POLITIKA"
    PROSEDUR = "PROSEDUR"
    TALIMAT = "TALIMAT"
    PROSES_KARTI = "PROSES_KARTI"    # süreç kartı / süreç tanım dokümanı
    GOREV_TANIMI = "GOREV_TANIMI"
    YETKI_MATRISI = "YETKI_MATRISI"  # imza sirküleri, yetki / RACI matrisi
    FORM = "FORM"
    LISTE = "LISTE"
    PLAN = "PLAN"
    DIS_KAYNAK = "DIS_KAYNAK"        # standart, mevzuat, müşteri şartnamesi
    DIGER = "DIGER"


# Analizlerde baskınlık sırası: küçük sayı daha üst düzey doküman.
DOC_HIERARCHY: dict[DocType, int] = {
    DocType.DIS_KAYNAK: 0,
    DocType.EL_KITABI: 1,
    DocType.POLITIKA: 1,
    DocType.YETKI_MATRISI: 2,
    DocType.PROSEDUR: 3,
    DocType.PROSES_KARTI: 3,
    DocType.GOREV_TANIMI: 3,
    DocType.TALIMAT: 4,
    DocType.PLAN: 4,
    DocType.FORM: 5,
    DocType.LISTE: 5,
    DocType.DIGER: 6,
}


class DocStatus(StrEnum):
    YURURLUKTE = "YURURLUKTE"
    TASLAK = "TASLAK"
    IPTAL = "IPTAL"


class EntityType(StrEnum):
    ROL = "ROL"
    BIRIM = "BIRIM"
    SUREC = "SUREC"
    FORM = "FORM"
    KAYIT = "KAYIT"
    SISTEM = "SISTEM"                # yazılım / ERP / donanım
    KPI = "KPI"
    STANDART_MADDESI = "STANDART_MADDESI"
    DIS_TARAF = "DIS_TARAF"          # tedarikçi, müşteri, otorite


class RuleType(StrEnum):
    ONAY = "ONAY"
    YETKI = "YETKI"
    SORUMLULUK = "SORUMLULUK"
    SURE = "SURE"
    ESIK = "ESIK"
    ZORUNLU_KAYIT = "ZORUNLU_KAYIT"
    ZORUNLU_ADIM = "ZORUNLU_ADIM"
    YASAK = "YASAK"
    TETIKLEYICI = "TETIKLEYICI"
    BILGILENDIRME = "BILGILENDIRME"


class RelType(StrEnum):
    REFERANS_VERIR = "REFERANS_VERIR"
    YERINE_GECER = "YERINE_GECER"
    KULLANIR = "KULLANIR"
    URETIR = "URETIR"
    SORUMLUDUR = "SORUMLUDUR"
    ONAYLAR = "ONAYLAR"
    YURUTUR = "YURUTUR"
    DANISILIR = "DANISILIR"
    BILGILENDIRILIR = "BILGILENDIRILIR"
    PARCASIDIR = "PARCASIDIR"
    DAYANAGIDIR = "DAYANAGIDIR"
    ESLESIR = "ESLESIR"


class NodeKind(StrEnum):
    """`edges` tablosundaki uç tipleri (her biri bir tabloya karşılık gelir)."""
    DOKUMAN = "DOKUMAN"        # documents
    BOLUM = "BOLUM"            # sections
    VARLIK = "VARLIK"          # entities
    KURAL = "KURAL"            # rules
    SUREC = "SUREC"            # processes
    SUREC_ADIMI = "SUREC_ADIMI"  # process_steps
    KARAR = "KARAR"            # decisions


class ReviewStatus(StrEnum):
    ONERILDI = "ONERILDI"
    ONAYLANDI = "ONAYLANDI"
    DUZELTILDI = "DUZELTILDI"
    REDDEDILDI = "REDDEDILDI"


TRUSTED_REVIEW = (ReviewStatus.ONAYLANDI, ReviewStatus.DUZELTILDI)


class FindingType(StrEnum):
    CAKISMA = "CAKISMA"
    BOSLUK = "BOSLUK"
    GUNCELLIK = "GUNCELLIK"
    YETKI_ASIMI = "YETKI_ASIMI"
    EKSIK_ONAY = "EKSIK_ONAY"
    UYGUNSUZLUK = "UYGUNSUZLUK"
    BELIRSIZLIK = "BELIRSIZLIK"


class Severity(StrEnum):
    KRITIK = "KRITIK"
    ORTA = "ORTA"
    DUSUK = "DUSUK"


class FindingStatus(StrEnum):
    ACIK = "ACIK"
    KABUL_EDILDI = "KABUL_EDILDI"
    YANLIS_POZITIF = "YANLIS_POZITIF"
    COZULDU = "COZULDU"


class DecisionStatus(StrEnum):
    """Karar matrisi satırının doküman karşısındaki durumu (process/decisions.py)."""
    KAYNAKLI = "KAYNAKLI"        # dayanak bulundu, matristeki rol/limit/süre dokümanla uyumlu
    CELISKI = "CELISKI"          # dokümanda farklı rol/limit/süre var
    KISMI = "KISMI"              # karar dokümanda var ama rol/limit/süre doğrulanamadı
    KAYNAK_YOK = "KAYNAK_YOK"    # dokümanlarda dayanak bulunamadı


class DecisionField(StrEnum):
    """Karar matrisinde karşılaştırılan alanlar."""
    ONAYLAYAN = "ONAYLAYAN"      # onaylayan + yetkili
    HAZIRLAYAN = "HAZIRLAYAN"
    LIMIT = "LIMIT"
    SURE = "SURE"


class SourceStance(StrEnum):
    """Seçilen kaynağın karar karşısındaki konumu (LLM yargısı)."""
    DESTEKLER = "DESTEKLER"
    CELISIR = "CELISIR"
    ILGILI = "ILGILI"            # konuyla ilgili ama karara dayanak değil


class CandidateKind(StrEnum):
    BOLUM = "BOLUM"
    KURAL = "KURAL"
    ADIM = "ADIM"


class DocCheck(StrEnum):
    """Matristeki "İlgili Doküman" hücresinin kontrol sonucu."""
    DOGRULANDI = "DOGRULANDI"            # dayanak bu dokümanda bulundu
    DESTEKLEMIYOR = "DESTEKLEMIYOR"      # doküman sistemde var ama dayanak başka dokümanda
    SISTEMDE_YOK = "SISTEMDE_YOK"        # doküman veritabanında yok


class MergeDecision(StrEnum):
    """Rol birleştirme Excel'inde kullanıcının satır kararı (`kys rol-onayla`)."""
    EVET = "EVET"      # varyant bu gruba aittir, ana ada birleştirilir
    HAYIR = "HAYIR"    # varyant ayrı roldür; bir daha bu gruba önerilmez
