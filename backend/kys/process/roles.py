"""Rol / birim adı çözümleme: `entities` + `entity_aliases` üzerinden, Türkçe katlama ve basit bulanık eşleşme.

Aynı pozisyonun farklı unvanları (Müdür/Yönetici/Sorumlu), çoğul ve hâl ekleri, "Satınalma" / "Satın Alma" gibi
yazım varyantları aynı role bağlanır. Çözülemeyen ad için öneri listesi döner. LLM yok.
"""

import re
import sqlite3
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ..ontology import EntityType
from ..textnorm import fold

RESOLVE_MIN = 0.80    # bu skor ve üstü: role bağlanır
SUGGEST_MIN = 0.45    # bu skor ve üstü: öneri listesine girer
SAME_ROLE_MIN = 0.85  # iki adın "aynı rol" sayılması için

_STOP = {"ve", "ile", "veya", "ilgili", "the", "of"}
# Aynı kademede birbirinin yerine kullanılan unvanlar
_TITLE_GROUPS = [{"mudur", "yonetici", "sorumlu"}, {"direktor", "direktoru"}, {"sef", "seflik"},
                 {"departman", "birim", "bolum", "mudurluk", "mudurlugu"}]
_TITLES = set().union(*_TITLE_GROUPS) | {"muhendis", "teknisyen", "uzman", "eleman", "formen", "amir", "operator",
                                         "lider", "koordinator", "temsilci", "asistan", "kurul", "ekip", "ekibi"}
# Eksik/fazla olunca rolü değiştiren nitelikler (Genel Müdür ≠ Genel Müdür Yardımcısı)
_QUALIFIERS = {"yardimci", "yrd", "vekil", "asistan", "kidemli", "bas", "sef", "stajyer", "genel"}
_ABBREV = {"gm": "genel mudur", "gmy": "genel mudur yardimcisi", "yk": "yonetim kurulu", "ik": "insan kaynaklari",
           "bt": "bilgi teknolojileri", "kys": "kalite yonetim sistemi"}
_SUFFIXES = ["lerinin", "larinin", "lerine", "larina", "leri", "lari", "ler", "lar", "inin", "unun", "nin", "nun",
             "si", "su", "in", "un", "den", "dan", "de", "da", "ne", "na", "yi", "yu", "i", "u", "e", "a"]


def _stem(tok: str) -> str:
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= (3 if len(suf) == 1 else 4):
            return tok[: -len(suf)]
    return tok


def tokens(name: str) -> list[str]:
    """Katlanmış, ekleri budanmış anlamlı kelimeler (kısaltmalar açılır)."""
    f = fold(name)
    out: list[str] = []
    for w in re.split(r"[^a-z0-9]+", f):
        if not w or w in _STOP:
            continue
        for part in (_ABBREV.get(w) or w).split():
            out.append(_stem(part))
    return out


def _title_group(tok: str) -> int | None:
    for i, g in enumerate(_TITLE_GROUPS):
        if tok in g or any(tok.startswith(x) and len(x) >= 4 for x in g):
            return i
    return None


def score_names(a: str, b: str) -> float:
    """İki ad arasında 0..1 benzerlik (aynı rol olma olasılığı)."""
    fa, fb = fold(a), fold(b)
    if not fa or not fb:
        return 0.0
    if fa == fb or fa.replace(" ", "") == fb.replace(" ", ""):
        return 1.0
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    qa = {t for t in ta if t in _QUALIFIERS}
    qb = {t for t in tb if t in _QUALIFIERS}
    da = [t for t in ta if t not in _QUALIFIERS and _title_group(t) is None and t not in _TITLES]
    db_ = [t for t in tb if t not in _QUALIFIERS and _title_group(t) is None and t not in _TITLES]
    sa, sb = set(da), set(db_)
    titles_a = {t for t in ta if t in _TITLES}
    titles_b = {t for t in tb if t in _TITLES}
    if sa and sb:
        dom = len(sa & sb) / len(sa | sb)
        joined = SequenceMatcher(None, "".join(da), "".join(db_)).ratio()   # 'satin alma' ~ 'satinalma'
        if joined >= 0.9:
            dom = max(dom, joined)
    elif not sa and not sb:
        dom = 1.0 if (titles_a == titles_b and qa == qb) else 0.75
    else:
        dom = 0.0
    if titles_a == titles_b:
        title = 1.0
    elif {g for g in map(_title_group, titles_a) if g is not None} & {g for g in map(_title_group, titles_b) if g is not None}:
        title = 0.92
    elif not titles_a or not titles_b:
        title = 0.8
    else:
        title = 0.6
    s = dom * title
    if qa != qb:
        s *= 0.6
    ratio = SequenceMatcher(None, fa, fb).ratio()
    if ratio >= 0.9:
        s = max(s, ratio)
    return round(min(s, 1.0), 3)


@dataclass
class RoleMatch:
    input: str
    entity_id: int | None = None
    canonical: str | None = None
    entity_type: str | None = None
    method: str = "yok"          # tam | takma_ad | kisaltma | bulanik | yok
    score: float = 0.0
    suggestions: list[dict] = field(default_factory=list)   # çözülemeyen ad için [{ad, skor}]

    @property
    def resolved(self) -> bool:
        return self.entity_id is not None

    def as_dict(self) -> dict:
        return {"girdi": self.input, "rol": self.canonical, "yontem": self.method, "skor": self.score,
                "oneriler": self.suggestions}


class RoleIndex:
    """`entities` (ROL, BIRIM) ve `entity_aliases` bellek içi dizini; bir kez yüklenir."""

    def __init__(self, conn: sqlite3.Connection):
        types = (EntityType.ROL.value, EntityType.BIRIM.value)
        marks = ",".join("?" * len(types))
        self.entities: dict[int, tuple[str, str]] = {}   # id → (kanonik ad, tip)
        self.names: list[tuple[str, int, bool]] = []     # (ad, entity_id, takma_ad_mi)
        for e in conn.execute(f"SELECT id, canonical_name, entity_type FROM entities WHERE entity_type IN ({marks})", types):
            self.entities[e["id"]] = (e["canonical_name"], e["entity_type"])
            self.names.append((e["canonical_name"], e["id"], False))
        for a in conn.execute(
                f"""SELECT a.alias, a.entity_id FROM entity_aliases a JOIN entities e ON e.id = a.entity_id
                    WHERE e.entity_type IN ({marks})""", types):
            self.names.append((a["alias"], a["entity_id"], True))
        self._exact: dict[str, tuple[int, bool]] = {}
        for name, eid, is_alias in self.names:
            self._exact.setdefault(fold(name), (eid, is_alias))

    def resolve(self, name: str) -> RoleMatch:
        name = " ".join((name or "").split())
        m = RoleMatch(input=name)
        if not name:
            return m
        f = fold(name)
        hit = self._exact.get(f) or self._exact.get(f.replace(" ", ""))
        if not hit:
            squashed = {k.replace(" ", ""): v for k, v in self._exact.items()}
            hit = squashed.get(f.replace(" ", ""))
        if hit:
            eid, is_alias = hit
            return self._fill(m, eid, "takma_ad" if is_alias and fold(self.entities[eid][0]) != f else "tam", 1.0)
        if f in _ABBREV:  # kısaltma → açılımı ara
            inner = self.resolve(_ABBREV[f])
            if inner.resolved:
                inner.input, inner.method = name, "kisaltma"
                return inner
        best: dict[int, float] = {}
        for cand, eid, _ in self.names:
            s = score_names(name, cand)
            if s > best.get(eid, 0.0):
                best[eid] = s
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        if ranked and ranked[0][1] >= RESOLVE_MIN:
            return self._fill(m, ranked[0][0], "bulanik", ranked[0][1])
        m.suggestions = [{"ad": self.entities[eid][0], "skor": s} for eid, s in ranked[:3] if s >= SUGGEST_MIN]
        return m

    def _fill(self, m: RoleMatch, eid: int, method: str, score: float) -> RoleMatch:
        m.entity_id, (m.canonical, m.entity_type) = eid, self.entities[eid]
        m.method, m.score = method, score
        return m


def _unit_vs_person(a: str, b: str) -> bool:
    """Aynı alan adı, biri birim biri unvan ('İnsan Kaynakları Bölümü' / 'İnsan Kaynakları Müdürü'): aynı rol sayılmaz
    ama çelişki de sayılmaz (belirsiz)."""
    def split(name):
        toks = tokens(name)
        titles = {t for t in toks if t in _TITLES}
        dom = {t for t in toks if t not in _TITLES and t not in _QUALIFIERS and _title_group(t) is None}
        return dom, titles
    da, ta = split(a)
    db_, tb = split(b)
    if not da or da != db_:
        return False
    unit = _TITLE_GROUPS[3]
    return bool(ta) and bool(tb) and (ta <= unit) != (tb <= unit)


def same_role(a: RoleMatch, b: RoleMatch) -> bool | None:
    """True: aynı rol · False: farklı roller (ikisi de sistemde tanımlı) · None: karşılaştırılamıyor."""
    na, nb = a.canonical or a.input, b.canonical or b.input
    if _unit_vs_person(na, nb) and score_names(na, nb) < SAME_ROLE_MIN:
        return None
    if a.resolved and b.resolved:
        if a.entity_id == b.entity_id:
            return True
        return score_names(a.canonical, b.canonical) >= SAME_ROLE_MIN
    if score_names(a.input, b.input) >= SAME_ROLE_MIN:
        return True
    return None
