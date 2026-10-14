"""Ajan 1.2 — Kural & İlişki Çıkarımı çıktı şeması (tek doküman).

Çıktıyı Claude Code alt ajanları (ilk kurulum) veya API/Ollama (rutin) üretebilir; içe aktarma aynıdır.
"""

from typing import Literal

from pydantic import BaseModel, Field

from ..ontology import RelType, RuleType


class ExRole(BaseModel):
    name: str = Field(description="Rol/unvan, dokümanda geçtiği gibi (ör. 'Mekanik Bakım Yöneticisi')")
    aliases: list[str] = Field(default=[], description="Aynı dokümanda aynı rol için geçen diğer yazımlar")
    unit: str | None = Field(default=None, description="Bağlı olduğu birim (biliniyorsa)")


class ExRule(BaseModel):
    rule_type: RuleType
    statement: str = Field(description="Kuralın tek cümlelik, normalize Türkçe ifadesi")
    subject: str | None = Field(default=None, description="Kuralın öznesi olan rol (roles listesindeki ad)")
    action: str | None = Field(default=None, description="Fiil: onaylar, yapar, kaydeder, bildirir...")
    object: str | None = Field(default=None, description="Neyi: satınalma talebi, arıza kaydı...")
    condition: str | None = Field(default=None, description="Koşul/istisna (varsa)")
    threshold_op: Literal[">", ">=", "<", "<=", "="] | None = None
    threshold_value: float | None = None
    threshold_unit: str | None = Field(default=None, description="TRY, USD, gun, saat, hafta, ay, yil, adet")
    clause_no: str | None = Field(default=None, description="Madde numarası (ör. '5.2'), yoksa null")
    quote: str = Field(description="Kaynak metinden BİREBİR alıntı (bir cümle veya kutu metni)")


class ExStep(BaseModel):
    seq: int
    name: str = Field(description="Adımın kısa adı")
    responsible: str | None = Field(default=None, description="Adımı yapan rol")
    approver: str | None = Field(default=None, description="Adımı onaylayan rol (varsa)")
    decision: str | None = Field(default=None, description="Karar kutusuysa soru metni (ör. 'Operatör çözebiliyor mu?')")
    next_steps: list[int] = Field(default=[], description="Sonraki adımların seq numaraları (dallanma dahil)")
    inputs: list[str] = Field(default=[], description="Girdi form/kayıt/doküman adları veya kodları")
    outputs: list[str] = Field(default=[], description="Çıktı form/kayıt/doküman adları veya kodları")
    system: str | None = Field(default=None, description="Kullanılan sistem/yazılım (ör. PROMANAGE, ERP)")
    duration_value: float | None = None
    duration_unit: str | None = None
    quote: str | None = Field(default=None, description="Adımı gösteren birebir metin (kutu yazısı)")


class ExReference(BaseModel):
    target: str = Field(description="Atıf yapılan doküman kodu veya form/kayıt adı")
    relation: Literal[RelType.REFERANS_VERIR, RelType.KULLANIR, RelType.URETIR, RelType.DAYANAGIDIR]
    clause_no: str | None = None
    quote: str


class DocExtraction(BaseModel):
    document_id: int
    document_code: str
    roles: list[ExRole] = []
    rules: list[ExRule] = []
    steps: list[ExStep] = []
    references: list[ExReference] = []
    observations: list[str] = Field(default=[], description="Belirsizlik, iç çelişki, eksik sorumlu, okunamayan "
                                                             "kısım gibi denetçi gözlemleri (kısa cümleler)")
