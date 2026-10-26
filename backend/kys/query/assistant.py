"""Sorgu asistanı: soru → ilgili bölümler → kaynaklı cevap (alıntılar doğrulanır).

Model `KYS_MODEL_QUERY` ile seçilir (varsayılan Claude Haiku); herhangi bir sağlayıcı bağlanabilir.
"""

import sqlite3
from importlib import resources

from pydantic import BaseModel

from .. import llm
from ..textnorm import verify_quote
from .retrieval import retrieve_for_question

SYSTEM = resources.files("kys").joinpath("prompts/assistant.md").read_text(encoding="utf-8")
MAX_SOURCE_CHARS = 3000


class Citation(BaseModel):
    kaynak_no: int
    quote: str


class AnswerOut(BaseModel):
    answer: str
    yeterli_bilgi: bool
    citations: list[Citation]


def _source_label(r: sqlite3.Row) -> str:
    clause = f" md.{r['clause_no']}" if r["clause_no"] else ""
    return f"{r['code']} Rev.{r['revision']}{clause} — {r['title']}"


def ask(conn: sqlite3.Connection, question: str, limit: int = 8) -> dict:
    rows = retrieve_for_question(conn, question, limit=limit)
    sources = [{"no": i + 1, "section_id": r["section_id"], "code": r["code"], "revision": r["revision"],
                "clause_no": r["clause_no"], "heading": r["heading"], "title": r["title"]}
               for i, r in enumerate(rows)]
    if not rows:
        return {"answer": "Bu soruyla ilgili yürürlükte bir doküman bölümü bulunamadı.", "yeterli_bilgi": False,
                "citations": [], "unverified": 0, "sources": [], "model": str(llm.model_for("query"))}

    context = "\n\n".join(
        f'<kaynak no="{i + 1}" ref="{_source_label(r)}">\n{(r["heading"] or "")}\n{r["text"][:MAX_SOURCE_CHARS]}\n</kaynak>'
        for i, r in enumerate(rows))
    out = llm.structured(
        purpose="sorgu", tier="query", system=SYSTEM,
        user=f"<kaynaklar>\n{context}\n</kaynaklar>\n\n<soru>{question}</soru>",
        schema=AnswerOut, max_tokens=4000,
    )

    citations, unverified = [], 0
    for c in out.citations:
        if not 1 <= c.kaynak_no <= len(rows):
            unverified += 1
            continue
        r = rows[c.kaynak_no - 1]
        if verify_quote(c.quote, f"{r['heading'] or ''}\n{r['text']}"):
            citations.append({**sources[c.kaynak_no - 1], "quote": c.quote})
        else:
            unverified += 1  # kaynakta geçmeyen alıntı kanıt sayılmaz (CLAUDE.md değişmez 1)
    return {"answer": out.answer, "yeterli_bilgi": out.yeterli_bilgi, "citations": citations,
            "unverified": unverified, "sources": sources, "model": str(llm.model_for("query"))}
