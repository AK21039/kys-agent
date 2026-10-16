"""Karar matrisi kontrolü: her kararın KYS dokümanlarındaki dayanağını bulur, rol/limit/süre uyumunu denetler.

Akış (satır başına):
1. Deterministik aday toplama: FTS bölümleri + ilgili kurallar (ONAY/YETKI/ESIK/SORUMLULUK/SURE öncelikli) +
   süreç adımları; matristeki roller `entities`/`entity_aliases` ile çözülür.
2. LLM yargısı (`llm.structured`, tier="query"): hangi adaylar dayanak, alıntı ne. Alıntı `verify_quote` ile kaynak
   bölüme karşı doğrulanır; tutmayan kaynak atılır ve sayılır. Doküman kodu / revizyon / madde bölümden gelir.
3. Durum sınıflaması tamamen deterministiktir (rol eşdeğerliği, sayısal limit/süre karşılaştırması).
Onaysız (ONERILDI) kurala dayanan sonuç `dogrulanmamis` işaretlenir (CLAUDE.md değişmez 2).
"""

import math
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from importlib import resources
from typing import Callable

from pydantic import BaseModel, Field

from .. import llm
from ..ontology import (TRUSTED_REVIEW, CandidateKind, DecisionField, DecisionStatus, ReviewStatus, RuleType,
                        SourceStance)
from ..query import retrieval
from ..textnorm import fold, fold_chars, verify_quote
from . import matrix_io
from .matrix_io import DecisionRow, MatrixError, ParsedMatrix
from .quantity import Quantity, canonical_unit, compare, parse_quantities
from .roles import RoleIndex, RoleMatch, same_role, tokens

MAX_ROWS = int(os.getenv("KYS_DECISION_MAX_ROWS", "300"))
MAX_FILE_BYTES = int(os.getenv("KYS_DECISION_MAX_BYTES", str(5 * 1024 * 1024)))
WORKERS = int(os.getenv("KYS_DECISION_WORKERS", "6"))
MAX_SECTIONS, MAX_RULES, MAX_STEPS, MAX_SOURCES = 10, 8, 4, 4
WINDOW = 900
PRIORITY_RULES = (RuleType.ONAY, RuleType.YETKI, RuleType.ESIK, RuleType.SORUMLULUK, RuleType.SURE)
SYSTEM = resources.files("kys").joinpath("prompts/decision_check.md").read_text(encoding="utf-8")


# ---- LLM şeması ---------------------------------------------------------------------------------------------------
class SecilenKaynak(BaseModel):
    aday_no: int
    quote: str
    iliski: SourceStance
    dokuman_onaylayanlar: list[str] = Field(default_factory=list)
    dokuman_hazirlayanlar: list[str] = Field(default_factory=list)
    nicelikler: list[str] = Field(default_factory=list)
    aciklama: str = ""


class KararHukmu(BaseModel):
    kaynaklar: list[SecilenKaynak] = Field(default_factory=list)
    ozet: str = ""


# ---- aday ve kaynak -----------------------------------------------------------------------------------------------
@dataclass
class Candidate:
    no: int
    kind: CandidateKind
    document_id: int
    code: str
    revision: str
    title: str
    section_id: int | None
    clause_no: str | None
    heading: str | None
    shown: str                          # modele gösterilen metin
    rule: dict | None = None
    step: dict | None = None

    @property
    def label(self) -> str:
        clause = f" md.{self.clause_no}" if self.clause_no else ""
        return f"{self.code} Rev.{self.revision}{clause} — {self.title}"


@dataclass
class Source:
    cand: Candidate
    quote: str
    iliski: SourceStance
    clause_no: str | None
    section_id: int | None
    approvers: list[RoleMatch] = field(default_factory=list)
    preparers: list[RoleMatch] = field(default_factory=list)
    quantities: list[Quantity] = field(default_factory=list)
    untrusted: bool = False
    note: str = ""
    verification: str = "birebir"       # 'birebir' | 'kelime' (bkz. _locate)
    weak_roles: bool = False            # roller alıntıdan değil, kural/adım yapısal alanından (yedek) geldi

    def as_dict(self) -> dict:
        c = self.cand
        return {"doc_code": c.code, "revision": c.revision, "title": c.title, "clause_no": self.clause_no,
                "heading": c.heading, "quote": self.quote, "tur": c.kind.value, "section_id": self.section_id,
                "rule_id": c.rule["id"] if c.rule else None,
                "review_status": c.rule["review_status"] if c.rule else None,
                "dogrulanmamis": self.untrusted, "dogrulama": self.verification, "iliski": self.iliski.value,
                "dokuman_onaylayanlar": [m.canonical or m.input for m in self.approvers],
                "dokuman_hazirlayanlar": [m.canonical or m.input for m in self.preparers],
                "nicelikler": [str(q) for q in self.quantities], "aciklama": self.note}


# ---- bağlam: bir çalıştırmada bir kez yüklenen veriler ----------------------------------------------------------------
class Context:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.roles = RoleIndex(conn)
        self.rules = [dict(r) | {"blob": fold(" ".join(str(r[k] or "") for k in
                                                       ("statement", "object_text", "condition_text", "action", "quote", "subject")))}
                      for r in conn.execute(
            """SELECT r.id, r.document_id, r.section_id, r.clause_no, r.rule_type, r.statement, r.action, r.object_text,
                      r.condition_text, r.threshold_op, r.threshold_value, r.threshold_unit, r.quote, r.review_status,
                      r.subject_entity_id, e.canonical_name AS subject,
                      d.code, d.revision, d.title
               FROM rules r JOIN documents d ON d.id = r.document_id
               LEFT JOIN entities e ON e.id = r.subject_entity_id
               WHERE d.status = 'YURURLUKTE' AND r.review_status != ?""", (ReviewStatus.REDDEDILDI.value,))]
        self.steps = [dict(r) | {"blob": fold(" ".join(str(r[k] or "") for k in ("name", "description", "quote", "pname")))}
                      for r in conn.execute(
            """SELECT s.id, s.seq, s.name, s.description, s.quote, s.duration_value, s.duration_unit,
                      p.code AS pcode, p.name AS pname, p.document_id,
                      re.canonical_name AS responsible, ae.canonical_name AS approver,
                      re.id AS responsible_id, ae.id AS approver_id, d.code, d.revision, d.title
               FROM process_steps s JOIN processes p ON p.id = s.process_id
               JOIN documents d ON d.id = p.document_id
               LEFT JOIN entities re ON re.id = s.responsible_entity_id
               LEFT JOIN entities ae ON ae.id = s.approver_entity_id
               WHERE d.status = 'YURURLUKTE' AND s.quote IS NOT NULL AND s.quote != ''""")]
        self._sections: dict[int, list[sqlite3.Row]] = {}
        self._section_by_id: dict[int, sqlite3.Row] = {}
        self._bodies: dict[int, str] = {}

    def section(self, section_id: int) -> sqlite3.Row | None:
        if section_id not in self._section_by_id:
            self._section_by_id[section_id] = self.conn.execute(
                "SELECT id, document_id, clause_no, heading, heading_path, text FROM sections WHERE id = ?",
                (section_id,)).fetchone()
        return self._section_by_id[section_id]

    def body(self, document_id: int) -> str:
        if document_id not in self._bodies:
            r = self.conn.execute("SELECT body_text FROM documents WHERE id = ?", (document_id,)).fetchone()
            self._bodies[document_id] = r["body_text"] if r else ""
        return self._bodies[document_id]

    def doc_sections(self, document_id: int) -> list[sqlite3.Row]:
        if document_id not in self._sections:
            self._sections[document_id] = self.conn.execute(
                "SELECT id, document_id, clause_no, heading, heading_path, text FROM sections "
                "WHERE document_id = ? ORDER BY ordinal", (document_id,)).fetchall()
        return self._sections[document_id]


def _window(text: str, terms: list[str]) -> str:
    """Metnin ilgili kısmı: ilk terim isabetinin çevresi (en çok WINDOW karakter)."""
    if len(text) <= WINDOW:
        return text
    folded = fold_chars(text)
    pos = min((p for p in (folded.find(t) for t in terms) if p >= 0), default=0)
    start = max(0, pos - 150)
    return text[start:start + WINDOW]


def _hits(blob: str, terms: list[str]) -> int:
    return sum(1 for t in terms if t in blob)


def gather(ctx: Context, row: DecisionRow, matrix_roles: dict[str, list[RoleMatch]]) -> list[Candidate]:
    """Deterministik aday toplama (LLM yok)."""
    terms = retrieval._terms(row.karar)
    cands: list[Candidate] = []

    def add(**kw) -> None:
        cands.append(Candidate(no=len(cands) + 1, **kw))

    # 1) FTS bölümleri: karar metni (+ ilgili doküman hücresi), ardından karar + yetkili rol adları
    secs = list(retrieval.retrieve_for_question(ctx.conn, f"{row.karar} {row.dokuman_text}".strip(), limit=6))
    if row.authorities:
        secs += retrieval.retrieve(ctx.conn, f"{row.karar} {' '.join(row.authorities)}", limit=4)
    seen: set[int] = set()
    for s in secs:
        if s["section_id"] in seen or len(seen) >= MAX_SECTIONS:
            continue
        seen.add(s["section_id"])
        body = f"{s['heading'] or ''}\n{_window(s['text'], terms)}".strip()
        add(kind=CandidateKind.BOLUM, document_id=s["document_id"], code=s["code"], revision=s["revision"],
            title=s["title"], section_id=s["section_id"], clause_no=s["clause_no"], heading=s["heading"], shown=body)

    # 2) kurallar: terim örtüşmesi + tür önceliği + yetkili rol eşleşmesi
    if terms:
        auth_ids = {m.entity_id for m in matrix_roles.get("authorities", []) if m.resolved}
        scored = []
        for r in ctx.rules:
            h = _hits(r["blob"], terms)
            if h < min(2, len(terms)):
                continue
            score = h / len(terms) + (0.6 if r["rule_type"] in PRIORITY_RULES else 0.0) \
                + (0.5 if r["subject_entity_id"] in auth_ids else 0.0)
            scored.append((score, r))
        for _, r in sorted(scored, key=lambda x: -x[0])[:MAX_RULES]:
            th = (f"; eşik: {r['threshold_op'] or ''}{r['threshold_value']:g} {r['threshold_unit'] or ''}"
                  if r["threshold_value"] is not None else "")
            shown = (f"Kural türü: {r['rule_type']}; özne: {r['subject'] or '-'}; eylem: {r['action'] or '-'}; "
                     f"nesne: {r['object_text'] or '-'}; koşul: {r['condition_text'] or '-'}{th}\nAlıntı: {r['quote']}")
            add(kind=CandidateKind.KURAL, document_id=r["document_id"], code=r["code"], revision=r["revision"],
                title=r["title"], section_id=r["section_id"], clause_no=r["clause_no"], heading=None, shown=shown, rule=r)
        # 3) süreç adımları
        scored = []
        for st in ctx.steps:
            h = _hits(st["blob"], terms)
            if h >= min(2, len(terms)):
                scored.append((h / len(terms), st))
        for _, st in sorted(scored, key=lambda x: -x[0])[:MAX_STEPS]:
            dur = f"; süre: {st['duration_value']:g} {st['duration_unit'] or ''}" if st["duration_value"] is not None else ""
            shown = (f"Süreç {st['pcode']} '{st['pname']}', adım {st['seq']}: {st['name']}. "
                     f"Sorumlu: {st['responsible'] or '-'}; onaycı: {st['approver'] or '-'}{dur}\nAlıntı: {st['quote']}")
            add(kind=CandidateKind.ADIM, document_id=st["document_id"], code=st["code"], revision=st["revision"],
                title=st["title"], section_id=None, clause_no=None, heading=None, shown=shown, step=st)
    return cands


# ---- LLM yargısı ----------------------------------------------------------------------------------------------------
def _prompt(row: DecisionRow, cands: list[Candidate]) -> str:
    def line(label, vals):
        return f"{label}: {', '.join(vals) if vals else '-'}"
    head = "\n".join([f"Karar: {row.karar}", f"Bölüm: {row.bolum or '-'}", line("Hazırlayan", row.hazirlayan),
                      line("Onaylayan", row.onaylayan), line("Yetkili", row.yetkili),
                      line("Bilgi verilen", row.bilgi), line("Danışılan", row.danisilan),
                      f"Limit: {row.limit_text or '-'}", f"Süre: {row.sure_text or '-'}",
                      f"İlgili doküman: {row.dokuman_text or '-'}"])
    body = "\n\n".join(f'<aday no="{c.no}" tur="{c.kind.value}" kaynak="{c.label}">\n{c.shown}\n</aday>' for c in cands)
    return f"<karar>\n{head}\n</karar>\n\n<adaylar>\n{body}\n</adaylar>"


def judge(row: DecisionRow, cands: list[Candidate], byok=None) -> tuple[KararHukmu, str | None]:
    out = llm.structured(purpose="karar_kontrol", tier="query", system=SYSTEM, user=_prompt(row, cands),
                         schema=KararHukmu, max_tokens=8000, byok=byok)
    return out, (llm.last_model.get() or str(llm.model_for("query")))


# ---- doğrulama ve kaynak üretimi (deterministik) ----------------------------------------------------------------------
def _locate(ctx: Context, cand: Candidate, quote: str) -> tuple[int | None, str | None, str] | None:
    """Alıntıyı adayın kaynak bölümünde (yoksa dokümanın bölümlerinde) arar → (section_id, clause_no, yöntem) ya da None.

    Yöntem: 'birebir' (verify_quote) ya da 'kelime' (yalnızca süreç adımı: akış şemasından çıkan metin PDF'de sırası
    bozuk olduğu için adımın kayıtlı alıntısındaki tüm kelimelerin doküman metninde geçmesi aranır)."""
    if cand.section_id is not None:
        s = ctx.section(cand.section_id)
        if s and verify_quote(quote, f"{s['heading'] or ''}\n{s['text']}"):
            return s["id"], s["clause_no"], "birebir"
    if cand.kind == CandidateKind.BOLUM:
        return None
    for s in ctx.doc_sections(cand.document_id):
        if verify_quote(quote, f"{s['heading'] or ''}\n{s['text']}"):
            return s["id"], s["clause_no"], "birebir"
    # akış şeması / tablo metni bölüm sınırlarına bölünmüş olabilir: tüm doküman metninde ara (madde no bilinmez)
    body = ctx.body(cand.document_id)
    if verify_quote(quote, body):
        return None, None, "birebir"
    if cand.step and verify_quote(quote, cand.step["quote"]):
        words = {w for w in fold(cand.step["quote"]).split() if len(w) >= 3}
        if words and words <= set(fold(body).split()):
            return None, None, "kelime"
    return None


def _role_in_quote(role: str, quote: str) -> bool:
    qtoks = tokens(quote)
    toks = tokens(role)
    return bool(toks) and all(any(q == t or (len(q) >= 3 and len(t) >= 3 and (q.startswith(t[:5]) or t.startswith(q[:5]))) for q in qtoks)
               for t in toks)


def build_sources(ctx: Context, cands: list[Candidate], out: KararHukmu) -> tuple[list[Source], int, list[str]]:
    """Modelin seçtiği kaynakları doğrular. Dönüş: (kaynaklar, atılan sayısı, uyarılar)."""
    sources: list[Source] = []
    dropped, warnings = 0, []
    seen: set[tuple] = set()
    for pick in out.kaynaklar[:MAX_SOURCES + 2]:
        first = pick.aday_no - 1
        order = ([first] if 0 <= first < len(cands) else []) + [i for i in range(len(cands)) if i != first]
        hit = None
        for i in order:
            loc = _locate(ctx, cands[i], pick.quote)
            if loc:
                hit = (cands[i], loc)
                break
        if hit is None:
            dropped += 1   # kaynakta geçmeyen alıntı kanıt sayılmaz (CLAUDE.md değişmez 1)
            continue
        cand, (section_id, clause_no, method) = hit
        key = (cand.document_id, section_id, cand.rule["id"] if cand.rule else None,
               cand.step["id"] if cand.step else None, fold(pick.quote)[:60])
        if key in seen:
            continue
        seen.add(key)
        clause_no = clause_no or cand.clause_no
        if not clause_no and cand.step:
            clause_no = f"{cand.step['pcode']} adım {cand.step['seq']}"
        src = Source(cand=cand, quote=pick.quote.strip(), iliski=pick.iliski, clause_no=clause_no,
                     section_id=section_id, note=pick.aciklama.strip(), verification=method)
        # modelin aktardığı rol ve nicelikler alıntıda geçmiyorsa atılır
        for names, dest in ((pick.dokuman_onaylayanlar, src.approvers), (pick.dokuman_hazirlayanlar, src.preparers)):
            for name in names:
                for part in matrix_io.split_roles(name):
                    if _role_in_quote(part, pick.quote):
                        dest.append(ctx.roles.resolve(part))
                    else:
                        warnings.append(f"'{part}' rolü alıntıda geçmediği için yok sayıldı ({cand.code}).")
        for snippet in pick.nicelikler:
            if not verify_quote(snippet, pick.quote, min_len=2):
                warnings.append(f"'{snippet[:40]}' ifadesi alıntıda geçmediği için yok sayıldı ({cand.code}).")
                continue
            src.quantities += parse_quantities(snippet, default_op="=")
        # kural / adım yapısal alanları: modelden boş geldiyse yedek olarak kullanılır (doğrulanmamış olabilir)
        if cand.rule:
            r = cand.rule
            if r["threshold_value"] is not None and canonical_unit(r["threshold_unit"]):
                src.quantities.append(Quantity(r["threshold_op"] or "=", float(r["threshold_value"]),
                                               canonical_unit(r["threshold_unit"]), "kural eşiği"))
            if r["subject"] and not src.approvers and r["rule_type"] in (RuleType.ONAY, RuleType.YETKI):
                src.approvers.append(ctx.roles.resolve(r["subject"]))
                src.weak_roles = True
            if r["subject"] and not src.preparers and r["rule_type"] == RuleType.SORUMLULUK:
                src.preparers.append(ctx.roles.resolve(r["subject"]))
                src.weak_roles = True
            src.untrusted = ReviewStatus(r["review_status"]) not in TRUSTED_REVIEW
        elif cand.step:
            st = cand.step
            used_fallback = False
            if st["approver"] and not src.approvers:
                src.approvers.append(ctx.roles.resolve(st["approver"]))
                used_fallback = src.weak_roles = True
            if st["responsible"] and not src.preparers:
                src.preparers.append(ctx.roles.resolve(st["responsible"]))
                used_fallback = src.weak_roles = True
            if st["duration_value"] is not None and canonical_unit(st["duration_unit"]):
                src.quantities.append(Quantity("=", float(st["duration_value"]), canonical_unit(st["duration_unit"]), "adım süresi"))
            src.untrusted = used_fallback   # süreç adımı rolleri çıkarım ürünüdür, incelenmemiştir
        sources.append(src)
        if len([s for s in sources if s.iliski != SourceStance.ILGILI]) >= MAX_SOURCES:
            break
    return sources, dropped, warnings


# ---- sınıflama (saf fonksiyonlar) -------------------------------------------------------------------------------------
def role_verdict(matrix_roles: list[RoleMatch], src_roles: list[RoleMatch], weak: bool = False) -> str | None:
    """UYUMLU | FARKLI | None. Biri eşleşirse UYUMLU; hepsi çözülmüş ve farklıysa FARKLI; aksi halde belirsiz.

    `weak`: roller alıntıdan değil kural/adım yapısal alanından geldiyse (incelenmemiş çıkarım) yalnızca uyum kanıt
    sayılır; fark çelişki üretmez."""
    if not matrix_roles or not src_roles:
        return None
    results = [same_role(m, d) for m in matrix_roles for d in src_roles]
    if any(r is True for r in results):
        return "UYUMLU"
    if weak:
        return None
    return None if any(r is None for r in results) else "FARKLI"


def quantity_verdict(matrix_q: Quantity | None, src_qs: list[Quantity]) -> tuple[str | None, Quantity | None]:
    """UYUMLU | FARKLI | None ve (FARKLI ise) doküman değeri. Aynı boyutta olmayan değerler yok sayılır."""
    if matrix_q is None:
        return None, None
    results = [(compare(matrix_q, q), q) for q in src_qs]
    results = [(v, q) for v, q in results if v]
    if any(v == "UYUMLU" for v, _ in results):
        return "UYUMLU", None
    diff = next((q for v, q in results if v == "FARKLI"), None)
    return ("FARKLI", diff) if diff else (None, None)


def _names(ms: list[RoleMatch]) -> str:
    return ", ".join(dict.fromkeys(m.canonical or m.input for m in ms))


def classify(row: DecisionRow, matrix_roles: dict[str, list[RoleMatch]], sources: list[Source],
             model_summary: str = "", dropped: int = 0) -> dict:
    """Durum, çelişkiler ve açıklama. LLM kullanmaz."""
    support = [s for s in sources if s.iliski != SourceStance.ILGILI]
    related = [s for s in sources if s.iliski == SourceStance.ILGILI]
    base = {"celiskiler": [], "dogrulanan": [], "dogrulanamayan": [], "dogrulanmamis": False}
    if not support:
        text = "Dokümanlarda bu karara dayanak olan bir madde bulunamadı."
        if related:
            text += " Konuyla ilgili ama dayanak olmayan maddeler: " + "; ".join(
                f"{s.cand.code} md.{s.clause_no or '-'}" for s in related[:3]) + "."
        if dropped:
            text += (f" Model {dropped} dayanak önerdi ancak alıntısı kaynak metinde doğrulanamadığı için kanıt sayılmadı;"
                     " elle kontrol edin.")
        elif model_summary:
            text += f" Model notu: {model_summary}"
        return {**base, "durum": DecisionStatus.KAYNAK_YOK, "aciklama": text}

    def ref(s: Source) -> str:
        return f"{s.cand.code} Rev.{s.cand.revision}" + (f" md.{s.clause_no}" if s.clause_no else "")

    conflicts, mixed, verified, unverified, notes = [], [], [], [], []

    def settle(fld: DecisionField, matrix_val: str, results: list[tuple[str | None, Source, str]]) -> None:
        """results: (karar, kaynak, dokümandaki değer metni)."""
        ok = [r for r in results if r[0] == "UYUMLU"]
        bad = [r for r in results if r[0] == "FARKLI"]
        if bad and not ok:
            conflicts.append({"alan": fld.value, "matris": matrix_val, "dokuman": bad[0][2], "kaynak": ref(bad[0][1])})
        elif bad and ok:
            mixed.append(fld)
            notes.append(f"{fld.value}: {ref(ok[0][1])} uyumlu, {ref(bad[0][1])} farklı ('{bad[0][2]}'); "
                         f"kademeli yetki ya da dokümanlar arası tutarsızlık olabilir; elle inceleyin.")
        elif ok:
            verified.append(fld)
        else:
            unverified.append(fld)

    auth = matrix_roles.get("authorities", [])
    if auth:
        res = [(role_verdict(auth, s.approvers, s.weak_roles), s, _names(s.approvers)) for s in support if s.approvers]
        settle(DecisionField.ONAYLAYAN, _names(auth), res)
        if DecisionField.ONAYLAYAN in unverified and not res:
            notes.append("Dayanak maddelerde onaylayan/yetkili rol belirtilmemiş.")
        elif DecisionField.ONAYLAYAN in unverified:
            notes.append(f"Matristeki rol ({_names(auth)}) ile dokümandaki rol(ler) (" +
                         "; ".join(dict.fromkeys(_names(s.approvers) for s in support if s.approvers)) +
                         ") sistemdeki tanımlı rollerle eşleştirilemediği için karşılaştırılamadı.")
    prep = matrix_roles.get("hazirlayan", [])
    if prep:
        res = [(role_verdict(prep, s.preparers, s.weak_roles), s, _names(s.preparers)) for s in support if s.preparers]
        if res:
            settle(DecisionField.HAZIRLAYAN, _names(prep), res)
    if row.limit:
        res = []
        for s in support:
            v, q = quantity_verdict(row.limit, s.quantities)
            res.append((v, s, str(q) if q else ""))
        settle(DecisionField.LIMIT, str(row.limit), res)
        if DecisionField.LIMIT in unverified:
            notes.append("Dayanak maddelerde karşılaştırılabilir limit bulunamadı.")
    if row.sure:
        res = []
        for s in support:
            v, q = quantity_verdict(row.sure, s.quantities)
            res.append((v, s, str(q) if q else ""))
        settle(DecisionField.SURE, str(row.sure), res)
        if DecisionField.SURE in unverified:
            notes.append("Dayanak maddelerde karşılaştırılabilir süre bulunamadı.")
    # HAZIRLAYAN doğrulanamaması durumu bozmaz (zorunlu alan değil)
    unverified = [f for f in unverified if f != DecisionField.HAZIRLAYAN]

    refs = ", ".join(dict.fromkeys(ref(s) for s in support))
    untrusted = any(s.untrusted for s in support)
    if conflicts:
        status = DecisionStatus.CELISKI
        text = "Dokümanla çelişki: " + "; ".join(
            f"{c['alan']} — matriste '{c['matris']}', dokümanda '{c['dokuman']}' ({c['kaynak']})" for c in conflicts) + "."
    elif mixed or unverified:
        status = DecisionStatus.KISMI
        text = f"Karar dokümanda geçiyor ({refs}) ancak doğrulanamayan alan: " + \
               ", ".join(f.value for f in dict.fromkeys(mixed + unverified)) + "."
    elif all(s.iliski == SourceStance.CELISIR for s in support):
        status = DecisionStatus.KISMI
        text = (f"Model {refs} maddesinin kararla çeliştiğini bildirdi ancak karşılaştırılabilir bir rol/limit/süre farkı "
                "bulunamadı; elle inceleyin.")
    else:
        status = DecisionStatus.KAYNAKLI
        ok_txt = ", ".join(f.value.lower() for f in dict.fromkeys(verified)) or "karar konusu"
        text = f"Dayanak: {refs}. Doğrulanan: {ok_txt}."
    if notes:
        text += " " + " ".join(dict.fromkeys(notes))
    if untrusted:
        text += " Doğrulanmamış kaynak: dayanak, henüz insan onayından geçmemiş (ONERILDI) kurala/çıkarıma dayanıyor."
    if any(s.verification == "kelime" for s in support):
        text += " Not: süreç adımı alıntısı akış şeması metninden kelime düzeyinde doğrulandı (PDF'de metin sırası bozuk)."
    if row.notes:
        text += " Not: " + " ".join(row.notes)
    return {"durum": status, "aciklama": text, "celiskiler": conflicts,
            "dogrulanan": [f.value for f in dict.fromkeys(verified)],
            "dogrulanamayan": [f.value for f in dict.fromkeys(mixed + unverified)], "dogrulanmamis": untrusted}


# ---- satır işleme -------------------------------------------------------------------------------------------------------
def resolve_matrix_roles(ctx: Context, row: DecisionRow) -> dict[str, list[RoleMatch]]:
    out = {f: [ctx.roles.resolve(n) for n in getattr(row, f)] for f in matrix_io.ROLE_FIELDS}
    out["authorities"] = [ctx.roles.resolve(n) for n in row.authorities]
    return out


def _role_report(roles: dict[str, list[RoleMatch]]) -> list[dict]:
    seen, out = set(), []
    for f in matrix_io.ROLE_FIELDS:
        for m in roles[f]:
            if m.input not in seen:
                seen.add(m.input)
                out.append({**m.as_dict(), "alan": f})
    return out


def _result(row: DecisionRow, roles, cands, sources, dropped, warnings, verdict: dict, model: str | None) -> dict:
    support = [s for s in sources if s.iliski != SourceStance.ILGILI]
    related = [s for s in sources if s.iliski == SourceStance.ILGILI]
    for m in (m for ms in roles.values() for m in ms):
        if not m.resolved:
            sug = ", ".join(s["ad"] for s in m.suggestions)
            warnings.append(f"Rol sistemde bulunamadı: '{m.input}'" + (f" (öneri: {sug})" if sug else ""))
    return {"no": row.idx, "satir": row.sheet_row, "bolum": row.bolum, "karar": row.karar,
            "girdi": row.as_input(), "durum": verdict["durum"].value, "aciklama": verdict["aciklama"],
            "kaynaklar": [s.as_dict() for s in support], "ilgili": [s.as_dict() for s in related],
            "celiskiler": verdict["celiskiler"], "dogrulanan_alanlar": verdict["dogrulanan"],
            "dogrulanamayan_alanlar": verdict["dogrulanamayan"], "dogrulanmamis": verdict["dogrulanmamis"],
            "atilan_kaynak": dropped, "aday_sayisi": len(cands), "eslesen_roller": _role_report(roles),
            "uyarilar": list(dict.fromkeys(warnings + row.notes)), "model": model}


def check_rows(conn: sqlite3.Connection, rows: list[DecisionRow], byok: tuple[str, str] | None = None,
               workers: int | None = None, progress: Callable[[int, int], None] | None = None) -> list[dict]:
    """Satırları kontrol eder. LLM çağrıları sınırlı paralellikle yapılır; veritabanına yalnızca ana iş parçacığı dokunur.

    Model zinciri tükenirse `llm.LLMUnavailable` yükselir (kısmi sonuç sessizce döndürülmez).
    """
    ctx = Context(conn)
    prepared = []
    for row in rows:
        roles = resolve_matrix_roles(ctx, row)
        prepared.append((row, roles, gather(ctx, row, roles)))
    verdicts: dict[int, tuple[KararHukmu, str | None]] = {}
    todo = [i for i, (_, _, cands) in enumerate(prepared) if cands]
    done = len(prepared) - len(todo)
    if progress and done:
        progress(done, len(prepared))
    with ThreadPoolExecutor(max_workers=max(1, min(workers or WORKERS, len(todo) or 1))) as pool:
        futures = {pool.submit(judge, prepared[i][0], prepared[i][2], byok): i for i in todo}
        try:
            for f in as_completed(futures):
                verdicts[futures[f]] = f.result()
                done += 1
                if progress:
                    progress(done, len(prepared))
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    results = []
    for i, (row, roles, cands) in enumerate(prepared):
        if i in verdicts:
            out, model = verdicts[i]
            sources, dropped, warnings = build_sources(ctx, cands, out)
            summary = out.ozet.strip()
        else:
            sources, dropped, warnings, model = [], 0, [], None
            summary = "FTS, kural ve süreç adımı taramasında aday çıkmadı."
        verdict = classify(row, roles, sources, summary, dropped=dropped)
        if dropped:
            warnings.append(f"{dropped} kaynak, alıntısı kaynak metinde doğrulanamadığı için atıldı.")
        results.append(_result(row, roles, cands, sources, dropped, warnings, verdict, model))
    return results


def summarize(results: list[dict], total: int | None = None) -> dict:
    counts = {s.value: 0 for s in DecisionStatus}
    for r in results:
        counts[r["durum"]] += 1
    return {"toplam_satir": total if total is not None else len(results), "kontrol_edilen": len(results),
            "durum": counts, "dogrulanmamis": sum(1 for r in results if r["dogrulanmamis"]),
            "atilan_kaynak": sum(r["atilan_kaynak"] for r in results),
            "modeller": sorted({r["model"] for r in results if r["model"]})}


@dataclass
class MatrixResult:
    parsed: ParsedMatrix
    rows: list[dict]
    summary: dict

    def to_json(self) -> dict:
        return {"ozet": self.summary, "matris": self.parsed.meta(), "satirlar": self.rows}


def load_matrix(file_bytes: bytes, filename: str) -> ParsedMatrix:
    if len(file_bytes) > MAX_FILE_BYTES:
        raise MatrixError(f"Dosya en çok {MAX_FILE_BYTES // (1024 * 1024)} MB olabilir.")
    parsed = matrix_io.parse_matrix(file_bytes, filename)
    if len(parsed.rows) > MAX_ROWS:
        raise MatrixError(f"Bir dosyada en çok {MAX_ROWS} karar satırı kontrol edilir ({len(parsed.rows)} satır var). "
                          "Dosyayı bölün.")
    return parsed


def analyze_matrix(conn: sqlite3.Connection, file_bytes: bytes, filename: str, byok=None, offset: int = 0,
                   limit: int | None = None, progress=None) -> MatrixResult:
    parsed = load_matrix(file_bytes, filename)
    chosen = parsed.rows[max(0, offset):(max(0, offset) + limit) if limit else None]
    results = check_rows(conn, chosen, byok=byok, progress=progress)
    return MatrixResult(parsed, results, summarize(results, total=len(parsed.rows)))


def check_matrix(conn: sqlite3.Connection, file_bytes: bytes, filename: str, byok=None, limit: int | None = None,
                 progress=None) -> tuple[list[dict], bytes]:
    """Tek giriş: (satır sonuçları, orijinal dosyaya sonuç kolonları eklenmiş xlsx baytları)."""
    res = analyze_matrix(conn, file_bytes, filename, byok=byok, limit=limit, progress=progress)
    return res.rows, matrix_io.render_xlsx(res.parsed, res.rows, res.summary)


def render_results(file_bytes: bytes, filename: str, results: list[dict]) -> bytes:
    """Daha önce hesaplanmış satır sonuçlarını (parça parça işlenmiş olabilir) Excel'e yazar; LLM çağrısı yapmaz."""
    parsed = load_matrix(file_bytes, filename)
    valid = {r.sheet_row: r for r in parsed.rows}
    rows = []
    for r in results:
        src = valid.get(r.get("satir"))
        if src is None or r.get("durum") not in {s.value for s in DecisionStatus}:
            raise MatrixError("Sonuçlar bu dosyaya ait değil (satır numarası veya durum geçersiz).")
        rows.append({**r, "karar": src.karar, "kaynaklar": r.get("kaynaklar") or [], "eslesen_roller": r.get("eslesen_roller") or []})
    return matrix_io.render_xlsx(parsed, sorted(rows, key=lambda x: x["satir"]), summarize(rows, total=len(parsed.rows)))


def check_single(conn: sqlite3.Connection, karar: str, yetkili: str | None = None, onaylayan: str | None = None,
                 limit: str | None = None, byok=None) -> dict:
    """Tek karar kontrolü (MCP aracı). Limit metni birim içermelidir ('100.000 TL')."""
    if not karar.strip():
        raise MatrixError("Karar metni boş")
    row = DecisionRow(idx=1, sheet_row=0, karar=karar.strip(), yetkili=matrix_io.split_roles(yetkili or ""),
                      onaylayan=matrix_io.split_roles(onaylayan or ""), limit_text=limit or "")
    if limit:
        qs = parse_quantities(limit)
        if qs:
            row.limit = qs[0]
        else:
            row.notes.append(f"Limit sayısal ayrıştırılamadı: '{limit[:60]}' (birim yazın: '100.000 TL')")
    return check_rows(conn, [row], byok=byok)[0]
