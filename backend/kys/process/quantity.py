"""Sayısal eşik (değer + birim + operatör) ayrıştırma ve deterministik karşılaştırma.

"100.000 TL'yi aşarsa", "5 iş günü içinde", "1,5 milyon ₺'ye kadar" gibi metinlerden `Quantity` çıkarır.
LLM yok: karar matrisi limitleri ile doküman eşikleri burada kesin olarak karşılaştırılır (CLAUDE.md değişmez 3).
"""

import re
from dataclasses import dataclass

from ..textnorm import fold

# Birim kanonik adları rules.threshold_unit ile uyumludur (TRY, gun, saat, ay, yil, yuzde, adet ...).
_UNITS: list[tuple[str, str]] = [
    (r"is\s*gun\w*", "gun"), (r"takvim\s*gun\w*", "gun"), (r"gun\w*", "gun"),
    (r"saat\w*", "saat"), (r"dakika\w*|dk\b", "dakika"), (r"hafta\w*", "hafta"), (r"ay\b|ay[a-z]{0,3}\b", "ay"),
    (r"yil\w*|sene\w*", "yil"),
    (r"tl\b|try\b|₺|lira\w*", "TRY"), (r"usd\b|\$|dolar\w*", "USD"), (r"eur\b|€|euro\w*", "EUR"),
    (r"%|yuzde\w*", "yuzde"), (r"adet\w*", "adet"),
    (r"kademe\w*", "kademe"), (r"puan\w*", "puan"), (r"metre\w*", "metre"), (r"bar\b", "bar"),
]
_TIME_DAYS = {"dakika": 1 / 1440, "saat": 1 / 24, "gun": 1.0, "hafta": 7.0, "ay": 30.0, "yil": 365.0}
_CURRENCY = {"TRY", "USD", "EUR"}
_SCALES = {"bin": 1e3, "milyon": 1e6, "milyar": 1e9}

_NUM = r"\d+(?:[.,]\d+)*"
_UNIT_RE = "|".join(f"(?:{p})" for p, _ in _UNITS)
_QTY = re.compile(
    rf"(?P<num>{_NUM})(?:\s*(?P<scale>bin|milyon|milyar)\b)?\s*(?P<unit>{_UNIT_RE})?", re.IGNORECASE)
_RANGE = re.compile(rf"^\s*(?P<lo>{_NUM})\s*(?:-|–|—|ile)\s*(?P<hi>{_NUM})", re.IGNORECASE)

_OP_SYMBOL = re.compile(r"(>=|<=|≥|≤|>|<|=)\s*$")
_GT = ("ustu", "uzeri", "ustunde", "asan", "asar", "asil", "fazla", "buyuk")
_GE = ("ve ustu", "ve uzeri", "en az", "asgari", "minimum", "az olmamak")
_LE = ("kadar", "dahil", "icinde", "icerisinde", "en fazla", "azami", "maksimum", "max", "sinirli")
_LT = ("altinda", "alti", "den az", "dan az")
_SYMBOLS = {"≥": ">=", "≤": "<="}


@dataclass(frozen=True)
class Quantity:
    op: str            # '>', '>=', '<', '<=', '='
    value: float
    unit: str | None   # TRY, USD, EUR, gun, saat, dakika, hafta, ay, yil, yuzde, adet ...
    text: str = ""     # kaynağındaki ifade

    @property
    def dim(self) -> str:
        if self.unit in _CURRENCY:
            return f"PARA:{self.unit}"
        if self.unit in _TIME_DAYS:
            return "ZAMAN"
        return f"BIRIM:{self.unit or '-'}"

    @property
    def base(self) -> float:
        """Karşılaştırma değeri: süreler gün cinsine çevrilir."""
        return self.value * _TIME_DAYS.get(self.unit or "", 1.0)

    def __str__(self) -> str:
        v = f"{self.value:,.2f}".rstrip("0").rstrip(".") if self.value % 1 else f"{int(self.value):,}"
        v = v.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{self.op} {v} {self.unit or ''}".strip()


def to_float(s: str) -> float | None:
    """Türkçe sayı biçimi: '100.000' = 100000, '1,5' = 1.5, '1.250,75' = 1250.75."""
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "." in s:
        s = s.replace(".", "") if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s) else s
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3}){2,}", s) else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def canonical_unit(text: str | None) -> str | None:
    """'TL', 'iş günü', '%' → 'TRY', 'gun', 'yuzde'. Tanınmazsa None."""
    t = fold(text or "")
    if not t:
        return None
    for pattern, unit in _UNITS:
        if re.fullmatch(pattern, t, re.IGNORECASE):
            return unit
    return None


def unit_in_header(header: str | None) -> str | None:
    """'Limit (TL)', 'Süre - gün' gibi başlıklardan varsayılan birim."""
    t = fold(header or "")
    m = re.search(rf"[(\[/-]\s*(?P<u>{_UNIT_RE})\s*[)\]]?\s*$", t) or re.search(rf"\b(?P<u>{_UNIT_RE})\s*$", t)
    return canonical_unit(m.group("u")) if m else None


def _operator(folded: str, start: int, end: int) -> str | None:
    before = folded[max(0, start - 18):start]
    m = _OP_SYMBOL.search(before)
    if m:
        return _SYMBOLS.get(m.group(1), m.group(1))
    after = folded[end:end + 32]
    for words, op in ((_GE, ">="), (_LT, "<"), (_GT, ">"), (_LE, "<=")):
        if any(re.search(rf"\b{re.escape(w)}", after) for w in words):
            return op
    if re.search(r"\b(en az|asgari|minimum)\s*$", before):
        return ">="
    if re.search(r"\b(en fazla|azami|maksimum|max)\s*$", before):
        return "<="
    return None


def parse_quantities(text: str | None, default_unit: str | None = None, default_op: str = "<=") -> list[Quantity]:
    """Metindeki tüm (sayı, birim) ifadeleri. Birimi olmayan sayı yalnızca `default_unit` verilmişse alınır.

    Operatör belirtilmemişse `default_op` (limit/süre için üst sınır '<='). '0-100.000 TL' aralığı üst sınır olur.
    """
    if text is None:
        return []
    raw = str(text)
    folded = re.sub(r"%\s*(\d+(?:[.,]\d+)?)", r"\g<1> %", fold(raw))   # %10 -> 10 %
    out: list[Quantity] = []
    pos = 0
    for m in _QTY.finditer(folded):
        if m.start() < pos:
            continue
        rng = _RANGE.match(folded, m.start())
        num_s = m.group("num")
        span_end = m.end()
        if rng:
            tail = _QTY.match(folded, rng.start("hi"))
            if tail and tail.group("unit"):
                num_s, m, span_end = rng.group("hi"), tail, tail.end()
        value = to_float(num_s)
        if value is None:
            continue
        # '4.2.1' gibi madde numaraları: iki ya da daha fazla nokta içeren ve binlik biçimine uymayan sayı
        if num_s.count(".") >= 2 and not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", num_s):
            continue
        scale = m.group("scale")
        if scale:
            value *= _SCALES[scale]
        unit = None
        if m.group("unit"):
            unit = canonical_unit(m.group("unit")) or next(
                (u for p, u in _UNITS if re.fullmatch(p, m.group("unit"), re.IGNORECASE)), None)
        if unit is None:
            unit = default_unit
            if unit is None:
                continue
        op = _operator(folded, m.start(), span_end) or default_op
        out.append(Quantity(op, value, unit, raw.strip()[:120]))
        pos = span_end
    return out


def compare(matrix: Quantity, doc: Quantity) -> str | None:
    """'UYUMLU' | 'FARKLI' | None (aynı boyutta değil → karşılaştırılamaz).

    Aynı sınır değeri her iki operatörde de uyumlu sayılır (matris '<= 100.000 TL', doküman '> 100.000 TL' üst kademe
    sınırı olarak aynı eşiği tarif eder). Farklı değer FARKLI'dır.
    """
    if matrix.dim != doc.dim:
        return None
    a, b = matrix.base, doc.base
    return "UYUMLU" if abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b)) else "FARKLI"
