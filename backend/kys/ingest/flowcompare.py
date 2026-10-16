"""Visio akış şeması (.vsdx) ile veritabanındaki süreç adımlarını karşılaştırır. DB'ye YAZMAZ.

Eşleme: adım adları `textnorm.fold` ile katlanır; karakter benzerliği + kök (ilk 5 harf) kümesi benzerliği karması.
Açgözlü en iyi eşleşme, eşik altı eşleşmez. Çıktı: eksik adım (vsdx'te var, DB'de yok), fazla adım (DB'de var, vsdx'te yok),
farklı dallar, farklı sorumlu, karar etiketleri. Kesin hüküm değil: adım ayrıntı düzeyi farklı olabilir; insan gözden geçirir.
"""

import difflib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from ..textnorm import fold
from .visio import (ALT_SUREC, BASLANGIC_BITIS, DOKUMAN, ISLEM, KARAR, VisioDoc, VisioPage, parse_vsdx)

THRESHOLD = 0.5
_STEP_KINDS = {ISLEM, KARAR, BASLANGIC_BITIS, ALT_SUREC}
_CODE_IN_TITLE = re.compile(r"(?i)d[öo]k\.?\s*no\s*:?\s*([A-Za-zÇĞİÖŞÜçğıöşü0-9.\- ]+?)\s+(?:[İI]lk|Rev)")
_TITLE_PREFIX = re.compile(r"^.*?(?:S[ÜU]RE[ÇC]LER[İI]|SURECLERI)\s*[-–]\s*", re.I)
_YES = {"evet"}
_NO = {"hayir"}


def _stems(text: str) -> set[str]:
    return {t[:5] for t in re.findall(r"[a-z0-9]+", fold(text)) if len(t) > 1}


def similarity(a: str, b: str) -> float:
    fa, fb = fold(a), fold(b)
    if not fa or not fb:
        return 0.0
    seq = difflib.SequenceMatcher(None, fa, fb).ratio()
    sa, sb = _stems(a), _stems(b)
    jac = len(sa & sb) / len(sa | sb) if sa | sb else 0.0
    cont = len(sa & sb) / min(len(sa), len(sb)) if sa and sb else 0.0  # biri diğerini kapsıyorsa
    return 0.4 * seq + 0.3 * jac + 0.3 * cont


def page_code(page: VisioPage) -> str | None:
    m = _CODE_IN_TITLE.search(page.title or "")
    return re.sub(r"\s+", "", m.group(1)).upper() if m else None


def page_name(page: VisioPage) -> str:
    return _TITLE_PREFIX.sub("", re.split(r"(?i)\s+d[öo]k\.?\s*no", page.title or page.name)[0]).strip() or page.name


def _clean_code(code: str) -> str:
    return re.sub(r"\s+", "", code or "").upper()


@dataclass
class DbStep:
    seq: int
    name: str
    decision: str | None
    next_steps: list[int]
    role: str | None
    blob: str  # ad + açıklama + girdi/çıktı + alıntı (form kodu aramak için)
    score: float = 0.0


@dataclass
class Report:
    code: str
    db_name: str
    db_document: str | None
    page: str
    page_title: str
    page_doc_code: str | None
    page_selected_by: str
    vsdx_steps: int = 0
    db_steps: int = 0
    matched: list[tuple[str, int, float]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)       # vsdx'te var, DB'de yok
    extra: list[str] = field(default_factory=list)         # DB'de var, vsdx'te yok
    branch_diffs: list[str] = field(default_factory=list)
    role_diffs: list[str] = field(default_factory=list)
    label_diffs: list[str] = field(default_factory=list)
    form_diffs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def text(self) -> str:
        L = [f"# Akış karşılaştırma: {self.code} — {self.db_name}",
             f"DB dokümanı: {self.db_document or '-'}",
             f"vsdx sayfası: {self.page} (seçim: {self.page_selected_by}); sayfadaki Dök.No: {self.page_doc_code or '-'}",
             f"Adım sayısı: vsdx {self.vsdx_steps}, DB {self.db_steps}; eşleşen {len(self.matched)}", ""]
        sections = [("Eşleşmeler (vsdx adımı -> DB seq, benzerlik)",
                     [f"{n} -> #{s} ({sc:.2f})" for n, s, sc in self.matched]),
                    ("EKSİK adım (vsdx'te var, DB'de yok)", self.missing),
                    ("FAZLA adım (DB'de var, vsdx'te yok)", self.extra),
                    ("Farklı dal / bağlantı", self.branch_diffs),
                    ("Farklı sorumlu (kulvar != DB sorumlusu)", self.role_diffs),
                    ("Karar etiketleri", self.label_diffs),
                    ("Form / doküman şekilleri", self.form_diffs),
                    ("Notlar", self.notes)]
        for title, items in sections:
            L.append(f"## {title}: {len(items)}")
            L.extend(f"- {i}" for i in items)
            L.append("")
        return "\n".join(L)


def load_db_process(conn: sqlite3.Connection, code: str) -> tuple[sqlite3.Row, list[DbStep]] | None:
    p = conn.execute("""SELECT p.id, p.code, p.name, d.code AS document_code FROM processes p
                        LEFT JOIN documents d ON d.id = p.document_id WHERE p.code = ? COLLATE NOCASE""", (code,)).fetchone()
    if not p:
        return None
    steps = []
    for r in conn.execute("""SELECT s.seq, s.name, s.description, s.decision, s.next_steps, s.inputs, s.outputs, s.quote,
                                    e.canonical_name AS role
                             FROM process_steps s LEFT JOIN entities e ON e.id = s.responsible_entity_id
                             WHERE s.process_id = ? ORDER BY s.seq""", (p["id"],)):
        try:
            nxt = [int(x) for x in json.loads(r["next_steps"] or "[]")]
        except (ValueError, TypeError):
            nxt = []
        blob = " ".join(str(r[k] or "") for k in ("name", "description", "inputs", "outputs", "quote"))
        steps.append(DbStep(r["seq"], r["name"], r["decision"], nxt, r["role"], blob))
    return p, steps


def select_page(doc: VisioDoc, code: str, db_name: str, page_arg: str | None) -> tuple[VisioPage, str]:
    if page_arg:
        if page_arg.isdigit() and 1 <= int(page_arg) <= len(doc.pages):
            return doc.pages[int(page_arg) - 1], f"--page {page_arg}"
        hits = [p for p in doc.pages if fold(page_arg) in fold(p.name)]
        if hits:
            return hits[0], f"--page '{page_arg}'"
    want = _clean_code(code)
    for p in doc.pages:
        if page_code(p) == want:
            return p, "Dök.No eşleşti"
    best = max(doc.pages, key=lambda p: similarity(page_name(p), db_name))
    return best, f"ad benzerliği ({similarity(page_name(best), db_name):.2f})"


def _match(vs: list, db: list[DbStep]) -> dict[str, DbStep]:
    pairs = sorted(((similarity(v.text, d.name), v.id, d.seq) for v in vs for d in db), reverse=True)
    used_v: set[str] = set()
    used_d: set[int] = set()
    out: dict[str, DbStep] = {}
    by_seq = {d.seq: d for d in db}
    for sc, vid, seq in pairs:
        if sc < THRESHOLD:
            break
        if vid in used_v or seq in used_d:
            continue
        used_v.add(vid)
        used_d.add(seq)
        out[vid] = by_seq[seq]
        out[vid].score = sc
    return out


def _short(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


_REV = re.compile(r"(?i)rev\.?\s*no\s*:?\s*(\d+)")
_REV_DATE = re.compile(r"(?i)rev\.?\s*tar\.?\s*:?\s*(\d{2})\.(\d{2})\.(\d{4})")


def _revision_note(conn, doc_code: str | None, page: VisioPage, rep: Report) -> None:
    m, d = _REV.search(page.title or ""), _REV_DATE.search(page.title or "")
    if not doc_code or not (m or d):
        return
    row = conn.execute("SELECT revision, revision_date FROM documents WHERE code = ?", (doc_code,)).fetchone()
    if not row:
        return
    v_rev = m.group(1).zfill(2) if m else None
    v_date = f"{d.group(3)}-{d.group(2)}-{d.group(1)}" if d else None
    if v_rev and row["revision"] and v_rev != str(row["revision"]).zfill(2):
        rep.notes.append(f"REVİZYON FARKI: vsdx Rev.{v_rev} (Rev.Tar. {v_date or '-'}), DB Rev.{row['revision']} "
                         f"({row['revision_date'] or '-'}); vsdx {'daha eski' if v_rev < str(row['revision']).zfill(2) else 'daha yeni'}.")
    elif v_date and row["revision_date"] and v_date != row["revision_date"]:
        rep.notes.append(f"Revizyon tarihi farkı: vsdx {v_date}, DB {row['revision_date']}.")


def compare(conn: sqlite3.Connection, code: str, vsdx: Path | str, page_arg: str | None = None) -> Report:
    loaded = load_db_process(conn, code)
    if loaded is None:
        raise LookupError(f"DB'de süreç yok: {code}")
    proc, db_steps = loaded
    doc = parse_vsdx(vsdx)
    if not doc.pages:
        raise ValueError("; ".join(doc.warnings) or "vsdx boş")
    page, how = select_page(doc, code, proc["name"], page_arg)
    rep = Report(code=proc["code"], db_name=proc["name"], db_document=proc["document_code"], page=page.name,
                 page_title=page.title, page_doc_code=page_code(page), page_selected_by=how)
    rep.notes.extend(f"vsdx uyarısı: {w}" for w in page.warnings)
    if rep.page_doc_code and _clean_code(rep.page_doc_code) != _clean_code(proc["document_code"] or proc["code"]):
        rep.notes.append(f"KOD FARKI: vsdx sayfasındaki Dök.No '{rep.page_doc_code}', DB kodu '{proc['document_code'] or proc['code']}'.")

    _revision_note(conn, proc["document_code"], page, rep)
    vsteps = [s for s in page.ordered() if s.kind in _STEP_KINDS]
    rep.vsdx_steps, rep.db_steps = len(vsteps), len(db_steps)
    mapping = _match(vsteps, db_steps)
    by_id = {s.id: s for s in vsteps}
    for v in vsteps:
        d = mapping.get(v.id)
        if d:
            rep.matched.append((_short(v.text, 60), d.seq, d.score))
        else:
            rep.missing.append(f"[{v.kind}] {_short(v.text, 110)}" + (f" (kulvar: {v.lane})" if v.lane else ""))
    matched_seqs = {d.seq for d in mapping.values()}
    rep.extra = [f"#{d.seq} {_short(d.name, 110)}" for d in db_steps if d.seq not in matched_seqs]

    empty_role: list[str] = []
    for v in vsteps:
        d = mapping.get(v.id)
        if not d:
            continue
        # dallar: vsdx çıkışlarını DB seq'ine çevir (eşleşmeyenler "?" olarak raporlanır)
        v_out = [(e.label, e.target) for e in page.out_edges(v.id) if e.target in by_id]
        v_targets = {mapping[t].seq if t in mapping else f"?{_short(by_id[t].text, 40)}" for _, t in v_out}
        d_targets = set(d.next_steps)
        miss = [t for t in v_targets - d_targets]
        more = [t for t in d_targets - v_targets]
        if miss or more:
            msg = f"#{d.seq} '{_short(d.name, 50)}':"
            if miss:
                msg += " vsdx'te olup DB'de olmayan çıkış -> " + ", ".join(
                    f"#{t}" if isinstance(t, int) else str(t) for t in miss) + "."
            if more:
                msg += " DB'de olup vsdx'te olmayan çıkış -> " + ", ".join(
                    f"#{t}" + (f" '{_short(next((x.name for x in db_steps if x.seq == t), ''), 40)}'") for t in more) + "."
            rep.branch_diffs.append(msg)
        # sorumlu
        if v.lane and d.role and similarity(v.lane, d.role) < 0.5 and fold(d.role) not in fold(v.lane) \
                and fold(v.lane) not in fold(d.role):
            rep.role_diffs.append(f"#{d.seq} '{_short(d.name, 50)}': vsdx kulvarı '{v.lane}' / DB '{d.role}'")
        elif v.lane and not d.role:
            empty_role.append(f"#{d.seq}")
        # karar etiketleri
        labels = [fold(l) for l, _ in v_out if l]
        if v.kind == KARAR or labels:
            if v.kind == KARAR and len(v_out) >= 2 and not labels:
                rep.label_diffs.append(f"#{d.seq} '{_short(d.name, 50)}': vsdx karar çıkışlarında etiket yok")
            if (v.kind == KARAR) != bool(d.decision) and len(d.next_steps) < 2 and v.kind == KARAR:
                rep.label_diffs.append(f"#{d.seq} '{_short(d.name, 50)}': vsdx'te karar (rombus), DB'de tek çıkışlı/karar değil")
            for lab, t in v_out:
                if t in mapping and lab:
                    tgt = mapping[t].seq
                    # DB'de iki çıkışlı kararda ilk=Evet, ikinci=Hayır varsayımı (flow.py ile aynı)
                    if tgt in d.next_steps and len(d.next_steps) == 2:
                        guess = "evet" if d.next_steps.index(tgt) == 0 else "hayir"
                        fl = fold(lab)
                        if fl in (_YES | _NO) and fl != guess:
                            rep.label_diffs.append(
                                f"#{d.seq}: '{lab}' dalı vsdx'te #{tgt}'a gidiyor; DB sırası bunu '{guess}' sayıyor (ters olabilir)")
    if empty_role:
        rep.role_diffs.append(f"DB'de sorumlu boş olan {len(empty_role)} adım (vsdx kulvarından doldurulabilir): "
                              + ", ".join(empty_role))
    rep.notes.append("Sorumlu karşılaştırması kaba: vsdx kulvarı birimdir, DB'deki sorumlu çoğu zaman roldür.")
    # form / doküman şekilleri
    db_blob = fold(" ".join(d.blob for d in db_steps))
    for s in page.shapes:
        if s.kind == DOKUMAN:
            m = re.search(r"[A-Za-z]{1,4}-[A-Za-z]{1,4}-\d+", s.text)
            key = fold(m.group(0)) if m else fold(s.text)
            if key not in db_blob:
                rep.form_diffs.append(f"vsdx'te form/doküman: '{_short(s.text, 90)}' — DB adımlarında geçmiyor")
    # DB'de kullanılan ama vsdx'te olmayan form kodları
    v_blob = fold(" ".join(s.text for s in page.shapes))
    for code_ in sorted(set(re.findall(r"[A-Za-z]{1,4}-[A-Za-z]{1,4}-\d+", " ".join(d.blob for d in db_steps)))):
        if fold(code_) not in v_blob:
            rep.form_diffs.append(f"DB adımlarında geçen form kodu '{code_}' vsdx'te yok")
    return rep
