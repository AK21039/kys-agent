"""Arama geri getirme ölçümü: altın soru seti → hit@k / MRR (saf hesaplama).

Doküman düzeyinde ölçüm: bir soru için beklenen dokümanlardan EN AZ BİRİ üst-k sonuç içinde
geçiyorsa isabet sayılır (çok-kaynaklı çelişki soruları için OR semantiği). DB'ye yazmaz;
ölçülecek fonksiyon dışarıdan verilebilir (varsayılan: `query.retrieval.retrieve`).

CLI: `kys arama-olc [--set YOL] [--k 10] [--json]` (bkz. cli.py:cmd_arama_olc).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from . import retrieval

RetrieveFn = Callable[[sqlite3.Connection, str, int], Iterable[sqlite3.Row]]

VARSAYILAN_SET = Path(__file__).resolve().parents[3] / "data" / "eval" / "arama_altin.json"


@dataclass
class SoruSonucu:
    id: str
    soru: str
    cok_anlamli: bool
    beklenen_kodlar: list[str]
    bulunan_kodlar: list[str]          # sıralı, tekrarsız (ilk görüldüğü rütbe sırasıyla)
    ilk_isabet_rutbe: int | None       # 1-indeksli; hiç isabet yoksa None

    @property
    def hit5(self) -> bool:
        return self.ilk_isabet_rutbe is not None and self.ilk_isabet_rutbe <= 5

    @property
    def hit10(self) -> bool:
        return self.ilk_isabet_rutbe is not None and self.ilk_isabet_rutbe <= 10

    def to_dict(self) -> dict:
        return {"id": self.id, "soru": self.soru, "cok_anlamli": self.cok_anlamli,
                "beklenen": self.beklenen_kodlar, "bulunan": self.bulunan_kodlar,
                "rutbe": self.ilk_isabet_rutbe, "hit5": self.hit5, "hit10": self.hit10}


@dataclass
class OlcumSonucu:
    k: int
    sorular: list[SoruSonucu]

    def alt_kume(self, pred: Callable[[SoruSonucu], bool]) -> "OlcumSonucu":
        return OlcumSonucu(k=self.k, sorular=[s for s in self.sorular if pred(s)])

    def hit_at(self, k: int) -> float:
        """hit@k: beklenen dokümanlardan biri ilk k sonuç içinde geçen soru oranı."""
        if not self.sorular:
            return 0.0
        return sum(1 for s in self.sorular if s.ilk_isabet_rutbe is not None and s.ilk_isabet_rutbe <= k) / len(self.sorular)

    def mrr(self) -> float:
        """Mean Reciprocal Rank — ilk isabetin rütbesinin tersinin ortalaması (isabet yoksa 0)."""
        if not self.sorular:
            return 0.0
        return sum((1 / s.ilk_isabet_rutbe) if s.ilk_isabet_rutbe else 0.0 for s in self.sorular) / len(self.sorular)

    def to_dict(self) -> dict:
        return {
            "k": self.k, "n": len(self.sorular),
            "hit_at_5": self.hit_at(5), "hit_at_10": self.hit_at(10), "mrr": self.mrr(),
            "sorular": [s.to_dict() for s in self.sorular],
        }


def load_gold(path: Path | str = VARSAYILAN_SET) -> list[dict]:
    """Altın soru setini okur (bkz. data/eval/arama_altin.json — git'e girmez, şirket verisi)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["sorular"]


def _expected_codes(item: dict) -> list[str]:
    seen: list[str] = []
    for b in item["beklenen"]:
        if b["kod"] not in seen:
            seen.append(b["kod"])
    return seen


def evaluate_query(conn: sqlite3.Connection, item: dict, k: int = 10,
                    retrieve_fn: RetrieveFn | None = None) -> SoruSonucu:
    retrieve_fn = retrieve_fn or retrieval.retrieve
    rows = retrieve_fn(conn, item["soru"], k)
    expected = set(_expected_codes(item))
    bulunan: list[str] = []
    rutbe: int | None = None
    for i, r in enumerate(rows, start=1):
        code = r["code"]
        if code not in bulunan:
            bulunan.append(code)
        if rutbe is None and code in expected:
            rutbe = i
    return SoruSonucu(id=item["id"], soru=item["soru"], cok_anlamli=bool(item.get("cok_anlamli")),
                       beklenen_kodlar=_expected_codes(item), bulunan_kodlar=bulunan, ilk_isabet_rutbe=rutbe)


def run(conn: sqlite3.Connection, gold: list[dict], k: int = 10,
        retrieve_fn: RetrieveFn | None = None) -> OlcumSonucu:
    return OlcumSonucu(k=k, sorular=[evaluate_query(conn, item, k=k, retrieve_fn=retrieve_fn) for item in gold])


def format_text(result: OlcumSonucu) -> str:
    out = []
    coklu = result.alt_kume(lambda s: s.cok_anlamli)
    duz = result.alt_kume(lambda s: not s.cok_anlamli)
    for s in result.sorular:
        durum = f"rütbe {s.ilk_isabet_rutbe}" if s.ilk_isabet_rutbe else "ISABET YOK"
        etiket = "çokanlamlı" if s.cok_anlamli else "düz"
        out.append(f"[{etiket:10}] {s.id:26} {durum:12} beklenen={','.join(s.beklenen_kodlar)} "
                    f"bulunan={','.join(s.bulunan_kodlar[:5])}")
    out.append("")
    out.append(f"Genel (n={len(result.sorular)}): hit@5={result.hit_at(5):.2f}  hit@10={result.hit_at(10):.2f}  MRR={result.mrr():.3f}")
    if coklu.sorular:
        out.append(f"Çok anlamlı (n={len(coklu.sorular)}): hit@5={coklu.hit_at(5):.2f}  hit@10={coklu.hit_at(10):.2f}  MRR={coklu.mrr():.3f}")
    if duz.sorular:
        out.append(f"Düz kontrol (n={len(duz.sorular)}): hit@5={duz.hit_at(5):.2f}  hit@10={duz.hit_at(10):.2f}  MRR={duz.mrr():.3f}")
    return "\n".join(out)
