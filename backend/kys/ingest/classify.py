"""Ajan 1.1 — Doküman Sınıflandırıcı (hızlı model).

Kural tabanlı metadata tespitini doğrular ve eksiklerini tamamlar; özet ve sahip birim üretir.
"""

import json
import sqlite3
from importlib import resources

from pydantic import BaseModel, Field

from .. import llm
from ..ontology import DocType
from .metadata import DocMeta
from .parsers import ParsedDoc

HEAD_CHARS = 6000
SYSTEM = resources.files("kys").joinpath("prompts/classify.md").read_text(encoding="utf-8")


class DocClassification(BaseModel):
    code: str | None
    title: str
    doc_type: DocType
    revision: str | None
    revision_date: str | None = Field(description="YYYY-AA-GG veya null")
    effective_date: str | None = Field(description="YYYY-AA-GG veya null")
    owner_unit: str | None
    summary: str
    confidence: float


def classify(parsed: ParsedDoc, meta: DocMeta, conn: sqlite3.Connection | None = None) -> DocClassification:
    hints = {k: getattr(meta, k) for k in ("code", "revision", "title", "doc_type", "revision_date", "effective_date")}
    hints["kaynaklar"] = meta.sources
    user = (
        f"<dosya_adi>{parsed.path.name}</dosya_adi>\n"
        f"<ipuclari>{json.dumps(hints, ensure_ascii=False, default=str)}</ipuclari>\n"
        f"<ustbilgi>\n{parsed.header_text[:2000]}\n</ustbilgi>\n"
        f"<govde_basi>\n{parsed.body_text[:HEAD_CHARS]}\n</govde_basi>"
    )
    return llm.structured(
        purpose="siniflandirma", tier="fast", system=SYSTEM, user=user,
        schema=DocClassification, max_tokens=2000, conn=conn, ref=parsed.path.name,
    )
