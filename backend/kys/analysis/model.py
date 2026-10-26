"""Faz 3 katman 1 veri modeli: `Finding`, `CheckOutcome`, paylaşılan salt-okunur `Context`.

LLM yok (CLAUDE.md değişmez 3). Alıntılar kaynak metinden ÇIKARTILIR (birebir dilim) ya da içe aktarımda
zaten doğrulanmış `rules.quote` / `process_steps.quote` sütunlarından gelir — bu yüzden her bulguda ayrıca
`textnorm.verify_quote` çağrısı gerekmez, kaynaktan kopya oldukları için biçim farkı dışında her zaman tutar
(değişmez 1). Yapısal (yokluk) bulgularda kanıt listesi boş kalabilir; bu durum raporda açıkça belirtilir.
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field

from ..ontology import FindingType, Severity


@dataclass
class Finding:
    check: str                      # kontrol adı (CHECK_REGISTRY anahtarı)
    finding_type: FindingType
    severity: Severity
    title: str
    explanation: str
    evidence: list[dict] = field(default_factory=list)   # [{doc_code, revision, clause_no, quote, section_id}]
    recommendation: str = ""
    unverified_basis: bool = False  # ONERILDI kurala/çıkarıma dayanıyorsa True (değişmez 2)
    key: str = ""                   # fingerprint'in tabanı; aynı anlamdaki bulgu her çalıştırmada aynı anahtarı üretir

    def fingerprint(self) -> str:
        basis = self.key or self.title
        return f"{self.check}:{hashlib.sha1(basis.encode('utf-8')).hexdigest()}"

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "finding_type": self.finding_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "explanation": self.explanation,
            "recommendation": self.recommendation,
            "evidence": self.evidence,
            "unverified_basis": self.unverified_basis,
            "fingerprint": self.fingerprint(),
        }

    def as_row(self, run_id: int | None) -> dict:
        row = self.to_dict()
        row["evidence"] = json.dumps(self.evidence, ensure_ascii=False)
        row["run_id"] = run_id
        return row


@dataclass
class CheckOutcome:
    findings: list[Finding] = field(default_factory=list)
    considered: int = 0              # kontrolün gözden geçirdiği aday sayısı (DB'de veri varsa her zaman > 0 olabilir)
    note: str | None = None          # örn. "decisions tablosu boş; kontrol atlandı (veri yok)."


class Context:
    """Bir `kys analiz` çalıştırmasında bir kez yüklenen salt-okunur veriler. DB'ye yazmaz."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.docs: dict[int, sqlite3.Row] = {
            r["id"]: r for r in conn.execute(
                "SELECT id, code, code_key, revision, title, doc_type, status, body_text FROM documents")
        }
        self.active_ids = {i for i, d in self.docs.items() if d["status"] == "YURURLUKTE"}
        from ..process.roles import RoleIndex
        self.roles = RoleIndex(conn)
        self._sections: dict[int, sqlite3.Row | None] = {}

    def section_text(self, section_id: int | None) -> str | None:
        if section_id is None:
            return None
        if section_id not in self._sections:
            self._sections[section_id] = self.conn.execute(
                "SELECT clause_no, heading, text FROM sections WHERE id = ?", (section_id,)).fetchone()
        row = self._sections[section_id]
        return row["text"] if row else None
