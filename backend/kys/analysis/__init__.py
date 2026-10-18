"""Faz 3 katman 1 — deterministik (LLM'siz) çelişki/boşluk taramaları ve bulgu raporu.

PLAN.md §2.1 "Analiz motoru: üç katman" / §3 "Denetim Radarı". Bulgular `findings` tablosu biçimindedir
(CLAUDE.md değişmez 1/2): her bulgu kaynak (doküman kodu + revizyon + madde + birebir alıntı) taşır,
ONERILDI kaynaklı bulgu `unverified_basis=True` işaretlenir. LLM çağrısı yok (değişmez 3).

Kullanım: `kys analiz [--kontrol AD ...] [--kaydet] [--out RAPOR.md] [--json YOL]` (bkz. `cli.py`).
"""

from .checks import CHECK_REGISTRY, run_checks
from .model import CheckOutcome, Context, Finding
from .report import render_report
from .store import save_findings

__all__ = [
    "CHECK_REGISTRY", "run_checks", "CheckOutcome", "Context", "Finding", "render_report", "save_findings",
]
