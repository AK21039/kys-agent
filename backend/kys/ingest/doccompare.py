"""Düzenlenebilir orijinal Word dosyalarını DB'deki dokümanlarla karşılaştırır. DB'ye YAZMAZ.

Eşleme: dosya adındaki kod -> DB `code_key`. Kod tutmazsa içerik benzerliğiyle en yakın DB dokümanı önerilir
(ör. aynı içerik farklı kodla kayıtlıysa). Benzerlik, katlanmış (`fold`) sözcük dizileri üzerinden hesaplanır:
- sira: SequenceMatcher oranı (sıra duyarlı)  - ortak: sözcük çoklu kümesi Dice (sıra duyarsız)
"""

import difflib
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..textnorm import fold
from . import metadata, parsers

WORD_EXT = {".doc", ".docx"}
_TOKEN = re.compile(r"[a-z0-9]{2,}")
SAME = 0.90      # sira >= -> "aynı içerik"
SIMILAR = 0.60   # sira >= -> "benzer, farklar var"


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(fold(text))


def dice(a: Counter, b: Counter) -> float:
    n = sum(a.values()) + sum(b.values())
    return 2 * sum((a & b).values()) / n if n else 0.0


def seq_ratio(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


@dataclass
class Item:
    file: str
    parsed_from: str            # gerçekte okunan dosya (dönüştürülmüş .docx olabilir)
    file_code: str | None
    file_rev: str | None
    file_rev_date: str | None
    db_code: str | None = None
    db_rev: str | None = None
    db_rev_date: str | None = None
    match_by: str = ""          # 'kod' | 'icerik' | ''
    sira: float = 0.0
    ortak: float = 0.0
    verdict: str = ""
    notes: list[str] = field(default_factory=list)
    suggestion: tuple[str, float] | None = None   # kod eşleşmedi: içerik olarak en yakın (DB kodu, sira)


def _converted_path(src: Path, root: Path, converted: Path | None) -> Path | None:
    if src.suffix.lower() == ".docx":
        return src
    if converted is None:
        return None
    p = converted / src.relative_to(root).with_suffix(".docx")
    return p if p.exists() else None


def compare_folder(conn: sqlite3.Connection, root: Path, converted: Path | None = None) -> list[Item]:
    root = Path(root)
    db_docs = [dict(r) for r in conn.execute(
        "SELECT id, code, code_key, revision, revision_date, title, header_text, body_text FROM documents")]
    db_tok = {d["id"]: tokens(d["body_text"] or "") for d in db_docs}
    db_cnt = {k: Counter(v) for k, v in db_tok.items()}
    by_key = {}
    for d in db_docs:
        by_key.setdefault(d["code_key"], []).append(d)

    items: list[Item] = []
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in WORD_EXT and not p.name.startswith("~$"))
    for src in files:
        fcode = metadata.filename_code(src.stem)
        read_path = _converted_path(src, root, converted)
        item = Item(file=src.name, parsed_from=str(read_path or ""), file_code=fcode, file_rev=None, file_rev_date=None)
        items.append(item)
        if read_path is None:
            item.verdict = "OKUNAMADI"
            item.notes.append(".doc dönüştürülmemiş: önce `kys convert-legacy` çalıştırın.")
            continue
        try:
            parsed = parsers.parse(read_path, ocr=False)
        except Exception as e:  # bozuk dosya vb.: raporla, durma
            item.verdict = "OKUNAMADI"
            item.notes.append(f"{type(e).__name__}: {e}")
            continue
        meta = metadata.detect(src, parsed.header_text, parsed.body_text)
        item.file_rev, item.file_rev_date = meta.revision, meta.revision_date
        hcode = meta.code if meta.sources.get("code") != "dosya_adi" else None
        item.file_code = hcode or fcode
        if hcode and fcode and metadata.code_key(hcode) != metadata.code_key(fcode):
            item.notes.append(f"KOD FARKI: dosya adında '{fcode}', üstbilgide '{hcode}' (eşleme üstbilgi koduyla).")
        for w in parsed.warnings:
            item.notes.append(f"ayrıştırma: {w}")
        ftok = tokens(parsed.header_text + " " + parsed.body_text)
        fcnt = Counter(ftok)

        cands = by_key.get(metadata.code_key(item.file_code), []) if item.file_code else []
        if not cands and fcode:
            cands = by_key.get(metadata.code_key(fcode), [])
        if cands:
            best = max(cands, key=lambda d: seq_ratio(ftok, db_tok[d["id"]]))
            item.match_by = "kod"
        else:
            # kod yok: içerik olarak en yakın DB dokümanı (önce Dice ile ön eleme)
            ranked = sorted(db_docs, key=lambda d: dice(fcnt, db_cnt[d["id"]]), reverse=True)[:3]
            best = max(ranked, key=lambda d: seq_ratio(ftok, db_tok[d["id"]])) if ranked else None
            if best is not None:
                sc = seq_ratio(ftok, db_tok[best["id"]])
                item.suggestion = (best["code"], sc)
                if sc >= SIMILAR:
                    item.match_by = "icerik"
                else:
                    best = None
        if best is None:
            item.verdict = "DB'DE YOK"
            continue
        item.db_code, item.db_rev, item.db_rev_date = best["code"], best["revision"], best["revision_date"]
        item.sira = seq_ratio(ftok, db_tok[best["id"]])
        item.ortak = dice(fcnt, db_cnt[best["id"]])
        item.verdict = "AYNI" if item.sira >= SAME else "BENZER (fark var)" if item.sira >= SIMILAR else "FARKLI İÇERİK"
        if item.match_by == "icerik":
            item.verdict = "KOD FARKLI, İÇERİK EŞLEŞTİ"
            item.notes.append(f"Dosya kodu {fcode or '-'} DB'de yok; içerik DB '{best['code']}' ile eşleşti.")
        _rev_notes(item)
        if item.verdict in ("BENZER (fark var)", "FARKLI İÇERİK"):
            item.notes.append("fark örnekleri: " + _diff_samples(ftok, db_tok[best["id"]]))
    # aynı kodu taşıyan birden çok dosya
    by_code: dict[str, list[Item]] = {}
    for it in items:
        if it.file_code:
            by_code.setdefault(metadata.code_key(it.file_code), []).append(it)
    for group in by_code.values():
        if len(group) > 1:
            win = max(group, key=lambda i: i.sira)
            for it in group:
                if it is not win and it.verdict == "FARKLI İÇERİK":
                    it.notes.append(f"DB'deki '{it.db_code}' kaydı başka dosyayla eşleşti; bu dosyanın DB karşılığı YOK (kod çakışması).")
                    it.verdict = "DB'DE YOK (kod çakışıyor)"
    seen: dict[str, list[str]] = {}
    for it in items:
        if it.file_code:
            seen.setdefault(metadata.code_key(it.file_code), []).append(it.file)
    for it in items:
        dup = seen.get(metadata.code_key(it.file_code or ""), [])
        if len(dup) > 1:
            it.notes.append("AYNI KODU taşıyan dosyalar: " + " | ".join(f for f in dup if f != it.file))
    return items


def _diff_samples(a: list[str], b: list[str], n: int = 3, width: int = 10) -> str:
    """En büyük n fark bloğu: '-' yalnız dosyada, '+' yalnız DB'de (katlanmış sözcüklerle)."""
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    ops.sort(key=lambda o: (o[2] - o[1]) + (o[4] - o[3]), reverse=True)
    out = []
    for tag, i1, i2, j1, j2 in ops[:n]:
        out.append(f"[-{' '.join(a[i1:i2][:width])}|+{' '.join(b[j1:j2][:width])}]")
    return " ".join(out) or "-"


def _rev_notes(it: Item) -> None:
    if it.file_rev and it.db_rev and it.file_rev.zfill(2) != str(it.db_rev).zfill(2):
        it.notes.append(f"Revizyon farkı: dosya Rev.{it.file_rev} / DB Rev.{it.db_rev}")
    if it.file_rev_date and it.db_rev_date and it.file_rev_date != it.db_rev_date:
        it.notes.append(f"Rev. tarihi farkı: dosya {it.file_rev_date} / DB {it.db_rev_date}")


def to_markdown(items: list[Item]) -> str:
    L = ["| Dosya | Dosya kodu/rev | DB kodu/rev | Benzerlik (sıra / ortak) | Sonuç | Not |", "|---|---|---|---|---|---|"]
    for it in items:
        f = f"{it.file_code or '-'} / {it.file_rev or '-'}" + (f" ({it.file_rev_date})" if it.file_rev_date else "")
        d = f"{it.db_code} / {it.db_rev or '-'}" + (f" ({it.db_rev_date})" if it.db_rev_date else "") if it.db_code else "-"
        sim = f"%{it.sira * 100:.0f} / %{it.ortak * 100:.0f}" if it.db_code else "-"
        notes = list(it.notes)
        if it.suggestion and not it.db_code:
            notes.insert(0, f"en yakın DB içeriği: {it.suggestion[0]} (%{it.suggestion[1] * 100:.0f})")
        L.append(f"| {it.file} | {f} | {d} | {sim} | {it.verdict} | {'; '.join(notes)} |")
    return "\n".join(L)
