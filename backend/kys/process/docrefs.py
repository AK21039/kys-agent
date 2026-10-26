"""Karar matrisindeki "İlgili Doküman" hücresini ayrıştırır ve veritabanındaki dokümana çözer. LLM yok.

Hücre değerleri: kod ("PR11-SA-4", "PR12-PRJ-7 "), kod + madde ("PR.AR-01 5.8.2"), dosya adı
("Satin_Alma_Tedarik_Yonetimi_ve_SLA_Proseduru.docx"), "/" ile birden çok değer, serbest metin
("PR.UR-01 / PLANLAMA VE ARGE BÖLÜMÜNDE DÖKÜMAN BULUNMAMAKTA"). Çözülemeyen kod/dosya adı SISTEMDE_YOK olur.
"""

import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import PureWindowsPath

from ..ingest.metadata import code_key, find_codes
from ..textnorm import fold

_FILE_EXT = re.compile(r"\.(docx?|pdf|xlsx?|vsdx?|txt)$", re.IGNORECASE)
_CLAUSE = re.compile(r"(?:\bmd\.?|\bmadde|\bm\.)?\s*(\d+(?:\.\d+)+|\d+)\s*$", re.IGNORECASE)
_IGNORE = ("bulunmamakta", "promanage", "canias")     # dokümansız birim notu, yazılım adı


@dataclass
class DocRef:
    raw: str
    kind: str                       # 'kod' | 'dosya' | 'baslik'
    code: str | None = None         # matristeki yazım
    clause_no: str | None = None
    document_id: int | None = None
    doc_code: str | None = None     # DB'deki kod
    revision: str | None = None
    title: str | None = None
    status: str | None = None       # DB doküman durumu

    @property
    def resolved(self) -> bool:
        return self.document_id is not None

    @property
    def label(self) -> str:
        return self.raw.strip()

    def as_dict(self) -> dict:
        return {"girdi": self.raw, "kod_girdi": self.code or self.raw, "tur": self.kind, "madde": self.clause_no, "doc_code": self.doc_code,
                "revision": self.revision, "title": self.title, "doc_status": self.status, "cozuldu": self.resolved}


def _split(text: str) -> list[str]:
    parts = re.split(r"\s*(?:/|;|\n|,|\+)\s*", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def parse_doc_refs(text: str | None) -> list[DocRef]:
    """Hücre metninden aday doküman başvuruları (çözümlenmemiş)."""
    out: list[DocRef] = []
    for part in _split(text or ""):
        f = fold(part)
        if any(w in f for w in ("promanage", "canias")):
            continue                                       # yazılım adı, doküman değil
        if "bulunmamakta" in f and not find_codes(part.upper()):
            continue                                       # "... BÖLÜMÜNDE DÖKÜMAN BULUNMAMAKTA"
        name = PureWindowsPath(part).name
        if _FILE_EXT.search(name) or ("_" in part and " " not in part.strip() and len(part) > 8):
            out.append(DocRef(raw=part, kind="dosya"))
            continue
        codes = find_codes(part.upper())
        if codes:
            code = codes[0]
            rest = part.upper().split(code, 1)[1] if code in part.upper() else ""
            m = _CLAUSE.search(rest.strip()) if rest.strip() else None
            out.append(DocRef(raw=part, kind="kod", code=code, clause_no=m.group(1) if m else None))
            continue
        if len(f) >= 8 and not any(w in f for w in _IGNORE):
            out.append(DocRef(raw=part, kind="baslik"))
    # sonuncusu boş bırakılmış serbest cümleleri ("... BÖLÜMÜNDE DÖKÜMAN ...") yok say: kod olmayan 'baslik' yalnızca
    # çözülebilirse tutulur (resolve_refs çözülemeyen başlıkları eler)
    return out


def _norm_name(text: str) -> str:
    stem = _FILE_EXT.sub("", PureWindowsPath(text).name)
    return fold(stem.replace("_", " "))


class DocResolver:
    def __init__(self, conn: sqlite3.Connection):
        self.docs = [dict(r) for r in conn.execute(
            "SELECT id, code, code_key, revision, title, status, file_path FROM documents")]
        self.by_key: dict[str, list[dict]] = {}
        for d in self.docs:
            self.by_key.setdefault(d["code_key"], []).append(d)
            d["_stem"] = _norm_name(d["file_path"] or "")
            d["_title"] = fold(d["title"] or "")

    @staticmethod
    def _pick(cands: list[dict]) -> dict:
        """Aynı kodun birden çok revizyonu: yürürlükteki, yoksa en yeni."""
        live = [d for d in cands if d["status"] == "YURURLUKTE"]
        return max(live or cands, key=lambda d: d["revision"])

    def resolve(self, ref: DocRef) -> DocRef:
        d = None
        if ref.kind == "kod":
            hits = self.by_key.get(code_key(ref.code))
            d = self._pick(hits) if hits else None
        else:
            name = _norm_name(ref.raw)
            best, best_s = None, 0.0
            for cand in self.docs:
                if name in (cand["_stem"], cand["_title"]):
                    best, best_s = cand, 1.0
                    break
                for other in (cand["_stem"], cand["_title"]):
                    if not other:
                        continue
                    s = SequenceMatcher(None, name, other).ratio()
                    if ref.kind == "baslik" and len(name) >= 8 and name in other:
                        s = max(s, 0.95)
                    if s > best_s:
                        best, best_s = cand, s
            d = best if best_s >= 0.88 else None
        if d:
            ref.document_id, ref.doc_code, ref.revision = d["id"], d["code"], d["revision"]
            ref.title, ref.status = d["title"], d["status"]
        return ref

    def resolve_cell(self, text: str | None) -> list[DocRef]:
        refs = [self.resolve(r) for r in parse_doc_refs(text)]
        # serbest metinden gelen çözülemeyen "baslik" adayları doküman başvurusu değil
        return [r for r in refs if r.kind != "baslik" or r.resolved]
