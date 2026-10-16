"""Doküman kimliğinin (kod, revizyon, başlık, tip, tarihler) kural tabanlı tespiti.

Türk KYS dokümanlarında bu bilgiler çoğunlukla üstbilgi tablosundadır:
    | Doküman No | Yayın Tarihi | Rev. No | Rev. Tarihi |
    | PR-04      | 01.01.2020   | 03      | 05.06.2024  |
veya etiket-değer çiftleri halinde: | Doküman No | PR-04 | Rev No | 03 |
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..ontology import DocType
from ..textnorm import fold, fold_chars

# PR-04, KYS-PR-001, İK.TL.02, FR.KAL.012, P.01, TL-SAT-03, PR08-UR-3
CODE_RE = re.compile(
    r"(?<![\w.\-])([A-ZÇĞİÖŞÜ]{1,5}\d{0,3}(?:[.\-_][A-ZÇĞİÖŞÜ0-9]{1,5}){0,3}[.\-_]\d{1,4})(?![\w])"
)
# "EK-4" bir ektir, doküman kodu değildir.
_CODE_STOP = {"rev", "no", "s", "sy", "sayfa", "madde", "md", "tel", "fax", "iso", "ts", "en", "iatf", "tc", "ek"}

# Aynı satırda "Etiket değer" biçimi (PDF üstbilgileri): "Doküman No GT- 161", "Rev.No:01 Rev. Tar.:09.09.2025"
_INLINE_LABELS: list[tuple[str, re.Pattern]] = [
    ("code", re.compile(r"\b(?:dok(?:uman)?|belge|form)\s*\.?\s*(?:no|kodu?|numarasi)\b\s*[:.]?")),
    ("revision_date", re.compile(r"\brev(?:izyon)?\s*\.?\s*tar(?:ihi)?\b\.?\s*:?")),
    ("revision", re.compile(r"\brev(?:izyon)?\s*\.?\s*(?:no|numarasi)\b\s*[:.]?")),
    ("issue_date", re.compile(r"\b(?:ilk\s+)?yayin\s*tar(?:ihi)?\b\.?\s*:?")),
    ("effective_date", re.compile(r"\byururlu(?:k|ge giris)\s*tarihi\b\s*:?")),
]

_LABELS = {
    "code": ("dokuman no", "dokuman kodu", "dokuman numarasi", "dok no", "dok kodu", "belge no",
             "belge kodu", "form no", "form kodu", "kod no", "dokuman kod"),
    "revision": ("rev no", "revizyon no", "revizyon numarasi", "rev", "revizyon"),
    "revision_date": ("rev tarihi", "revizyon tarihi", "rev tar", "son revizyon tarihi"),
    "issue_date": ("yayin tarihi", "ilk yayin tarihi", "yayim tarihi", "hazirlanma tarihi"),
    "effective_date": ("yururluk tarihi", "yururluge giris tarihi", "gecerlilik tarihi"),
    "title": ("dokuman adi", "dokuman basligi", "belge adi", "form adi", "konu"),
}

_TYPE_KEYWORDS: list[tuple[str, DocType]] = [
    ("el kitabi", DocType.EL_KITABI),
    ("politika", DocType.POLITIKA),
    ("gorev tanimi", DocType.GOREV_TANIMI),
    ("is tanimi", DocType.GOREV_TANIMI),
    ("imza sirkuleri", DocType.YETKI_MATRISI),
    ("yetki matrisi", DocType.YETKI_MATRISI),
    ("yetki tablosu", DocType.YETKI_MATRISI),
    ("raci", DocType.YETKI_MATRISI),
    ("proses karti", DocType.PROSES_KARTI),
    ("surec karti", DocType.PROSES_KARTI),
    ("prosedur", DocType.PROSEDUR),
    ("talimat", DocType.TALIMAT),
    ("formu", DocType.FORM),
    ("form", DocType.FORM),
    ("listesi", DocType.LISTE),
    ("plani", DocType.PLAN),
    ("sureci", DocType.PROSES_KARTI),     # süreç akış şemaları
    ("akis semasi", DocType.PROSES_KARTI),
]

# Kod öneklerinden tip tahmini. Şirket kodlama kuralına göre genişletilir.
PREFIX_TYPES: dict[str, DocType] = {
    "pr": DocType.PROSEDUR, "p": DocType.PROSEDUR, "prs": DocType.PROSEDUR, "prd": DocType.PROSEDUR,
    "tl": DocType.TALIMAT, "t": DocType.TALIMAT, "ta": DocType.TALIMAT, "tlm": DocType.TALIMAT,
    "fr": DocType.FORM, "f": DocType.FORM, "frm": DocType.FORM,
    "gt": DocType.GOREV_TANIMI, "gtn": DocType.GOREV_TANIMI, "gr": DocType.GOREV_TANIMI,
    "pl": DocType.POLITIKA, "pol": DocType.POLITIKA,
    "ek": DocType.EL_KITABI, "kek": DocType.EL_KITABI, "kk": DocType.EL_KITABI,
    "ls": DocType.LISTE, "lst": DocType.LISTE, "l": DocType.LISTE,
    "pln": DocType.PLAN, "pn": DocType.PLAN,
    "pk": DocType.PROSES_KARTI, "prk": DocType.PROSES_KARTI, "sk": DocType.PROSES_KARTI,
    "ym": DocType.YETKI_MATRISI,
}

_DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
_REV_FREE = re.compile(r"\brev(?:[iİıI]zyon)?\.?\s*(?:no|numaras[ıi])?\s*[:.]?\s*(\d{1,3})\b", re.IGNORECASE)
_REV_FILENAME = re.compile(r"rev[._\-\s]?(\d{1,3})", re.IGNORECASE)


@dataclass
class DocMeta:
    code: str | None = None
    revision: str | None = None
    title: str | None = None
    doc_type: DocType | None = None
    revision_date: str | None = None
    effective_date: str | None = None
    sources: dict[str, str] = field(default_factory=dict)  # alan -> 'baslik_tablosu' | 'dosya_adi' | 'metin'

    @property
    def confidence(self) -> float:
        keys = ("code", "revision", "title", "doc_type")
        return sum(getattr(self, k) is not None for k in keys) / len(keys)


def code_key(code: str) -> str:
    """Kod karşılaştırma anahtarı: 'PR-04', 'pr.4', 'PR 004' → 'pr4'."""
    key = re.sub(r"[.\-_\s]", "", fold(code))
    return re.sub(r"(?<!\d)0+(?=\d)", "", key)


def find_codes(text: str) -> list[str]:
    out: list[str] = []
    for m in CODE_RE.finditer(text):
        code = m.group(1)
        if fold(re.split(r"[.\-_]", code)[0]) in _CODE_STOP:
            continue
        if code not in out:
            out.append(code)
    return out


_FILENAME_CODE = re.compile(
    r"^\s*([A-ZÇĞİÖŞÜ]{1,5}\d{0,3}(?:[.\-_][A-ZÇĞİÖŞÜ0-9]{1,5}){0,3}[.\-_](?:\d{0,3}X(?![^\W\d_])|\d{1,4}))(?=[\s_\-]|[^\W\d_]|$)")


def filename_code(stem: str) -> str | None:
    """Dosya adının BAŞINDAKİ kodu verir. find_codes'tan farkı: kod başlığa bitişik olabilir
    ("ISG-TL-001Taşeron...") ve numara yer tutucu olabilir ("PR.YP-0X")."""
    m = _FILENAME_CODE.match(stem)
    if m:
        return m.group(1)
    codes = find_codes(stem)
    return codes[0] if codes else None


def parse_date(text: str) -> str | None:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    if m.group(1):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        y, mo, d = int(m.group(4)), int(m.group(5)), int(m.group(6))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _label_of(cell: str) -> str | None:
    key = re.sub(r"[^a-z0-9 ]", " ", fold(cell))
    key = re.sub(r"\s+", " ", key).strip()
    if not key or len(key) > 40:
        return None
    for field_name, labels in _LABELS.items():
        if key in labels:
            return field_name
    return None


def table_values(text: str) -> dict[str, str]:
    """Pipe tablolarından etiket → değer çiftlerini çıkarır (yan yana veya alt satırda)."""
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")]
            for ln in text.splitlines() if ln.strip().startswith("|")]
    found: dict[str, str] = {}
    for r, row in enumerate(rows):
        for i, cell in enumerate(row):
            label = _label_of(cell)
            if not label or label in found:
                continue
            value = None
            # Sağdaki ilk dolu hücre (Excel'de araya boş birleştirilmiş hücreler girer), yoksa alttaki hücre
            right = next((c for c in row[i + 1:i + 8] if c), None)
            if right and not _label_of(right):
                value = right
            elif r + 1 < len(rows) and i < len(rows[r + 1]) and rows[r + 1][i] and not _label_of(rows[r + 1][i]):
                value = rows[r + 1][i]
            if value:
                found[label] = value
    # Hücre içinde "Doküman No: PR-04" biçimi
    for ln in text.splitlines():
        for part in ln.split("|"):
            if ":" in part:
                lab, _, val = part.partition(":")
                label = _label_of(lab)
                if label and label not in found and val.strip():
                    found[label] = val.strip()
    return found


def _fold_same_len(text: str) -> str:
    """fold() gibi ama boşlukları daraltmaz; konumlar orijinal metinle birebir eşleşir."""
    folded = fold_chars(text)
    return folded if len(folded) == len(text) else ""


def inline_values(text: str) -> dict[str, str]:
    """Tablo dışı "Etiket değer" satırlarından ham değerleri çıkarır (etiketten sonraki kısa metin)."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        folded = _fold_same_len(line)
        if not folded:
            continue
        for name, pattern in _INLINE_LABELS:
            if name in found:
                continue
            m = pattern.search(folded)
            if m:
                value = line[m.end():].strip(" :.\t")[:40]
                if value:
                    found[name] = value
    return found


def _code_from_value(value: str) -> str | None:
    """Etiket değerinden kodu çıkarır. PDF'lerde kod aralıklı gelebilir: 'GT- 161', 'P R46-PRJ-3', 'PN.-03'."""
    folded = _fold_same_len(value)
    if folded:  # değeri bir sonraki etikette kes: "P R46-PRJ-3 İlk Yayın Tar..." → "P R46-PRJ-3"
        cuts = [m.start() for _, p in _INLINE_LABELS if (m := p.search(folded))]
        if cuts:
            value = value[:min(cuts)]
    value = re.sub(r"[.\-_]+([.\-_])", r"\1", value.strip())  # "PN.-03" → "PN-03"
    for candidate in (re.sub(r"\s+", "", value), re.sub(r"\s*([.\-_])\s*", r"\1", value)):
        codes = find_codes(candidate)
        if codes:
            return codes[0]
    return None


def known_segments(codes: list[str]) -> set[str]:
    """Yüklü doküman kodlarındaki harf bölümleri: {'pr', 'gt', 'me', 'tl', 'yp', 'fr', ...}."""
    return {seg for code in codes for seg in re.split(r"[.\-_\d]+", fold(code)) if seg.isalpha()}


def looks_like_doc_code(code: str, segments: set[str]) -> bool:
    """Atıf gerçekten doküman kodu mu, yoksa makine/hat adı mı ('PAD-1', 'TECOM-1')?"""
    segs = {s for s in re.split(r"[.\-_\d]+", fold(code)) if s.isalpha()}
    return bool(segs & (segments | set(PREFIX_TYPES)))


def _norm_revision(value: str) -> str | None:
    m = re.search(r"\d{1,3}", value)
    return f"{int(m.group()):02d}" if m else None


def _type_from(title: str | None, code: str | None) -> DocType | None:
    if title:
        t = fold(title)
        for kw, dt in _TYPE_KEYWORDS:
            if re.search(rf"\b{kw}", t):
                return dt
    if code:
        for seg in re.split(r"[.\-_]", fold(code)):
            if seg.isalpha() and seg in PREFIX_TYPES:
                return PREFIX_TYPES[seg]
    return None


def tr_title(text: str) -> str:
    """Türkçe kurallarla başlık biçimi: 'SATINALMA PROSEDÜRÜ' → 'Satınalma Prosedürü'."""
    words = []
    for w in text.replace("I", "ı").replace("İ", "i").lower().split():
        words.append(("İ" if w[0] == "i" else w[0].upper()) + w[1:])
    return " ".join(words)


def _title_from_header(header_text: str, code: str | None) -> str | None:
    """Üstbilgide tablo dışında kalan, etiket olmayan ilk anlamlı satır (çoğunlukla doküman adı)."""
    for line in header_text.splitlines():
        line = line.strip().lstrip("#").strip()
        folded = _fold_same_len(line)
        hits = [p.search(folded) for _, p in _INLINE_LABELS] if folded else []
        starts = [m.start() for m in hits if m]
        if starts:
            line = line[:min(starts)].strip()  # "BAKIM PROSEDÜRÜ Revizyon No 01" → "BAKIM PROSEDÜRÜ"
        if (line.startswith("|") or not 5 <= len(line) <= 100 or _label_of(line.split(":")[0])
                or (code and code in line) or sum(c.isalpha() for c in line) < 5):
            continue
        return tr_title(line) if line.isupper() else line
    return None


def _informative(title: str | None) -> bool:
    """Dosya adı başlık olarak kullanılabilir mi? 'TKYS0100001673103' değil, 'Arıza Süreci' evet."""
    return bool(title) and sum(1 for w in title.split() if sum(c.isalpha() for c in w) >= 2) >= 2


def _title_from_filename(path: Path, code: str | None) -> str | None:
    stem = path.stem
    if code:
        stem = re.sub(re.escape(code), " ", stem, flags=re.IGNORECASE)
    stem = _REV_FILENAME.sub(" ", stem)
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"^\W+|\W+$", "", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or None


def detect(path: Path, header_text: str, body_text: str) -> DocMeta:
    meta = DocMeta()
    head = header_text + "\n" + "\n".join(body_text.splitlines()[:40])
    kv = table_values(head)
    iv = inline_values(head)

    if "code" in kv and _code_from_value(kv["code"]):
        meta.code, meta.sources["code"] = _code_from_value(kv["code"]), "baslik_tablosu"
    elif "code" in iv and _code_from_value(iv["code"]):
        meta.code, meta.sources["code"] = _code_from_value(iv["code"]), "baslik_satiri"
    elif filename_code(path.stem):
        meta.code, meta.sources["code"] = filename_code(path.stem), "dosya_adi"
    elif find_codes(header_text):
        meta.code, meta.sources["code"] = find_codes(header_text)[0], "metin"

    if "revision" in kv and _norm_revision(kv["revision"]):
        meta.revision, meta.sources["revision"] = _norm_revision(kv["revision"]), "baslik_tablosu"
    elif "revision" in iv and _norm_revision(iv["revision"][:6]):
        meta.revision, meta.sources["revision"] = _norm_revision(iv["revision"][:6]), "baslik_satiri"
    elif m := _REV_FILENAME.search(path.stem):
        meta.revision, meta.sources["revision"] = f"{int(m.group(1)):02d}", "dosya_adi"
    elif m := _REV_FREE.search(head):
        meta.revision, meta.sources["revision"] = f"{int(m.group(1)):02d}", "metin"

    # Başlık önceliği: tablo etiketi > anlamlı dosya adı > üstbilgi satırı > dosya adı
    from_file = _title_from_filename(path, meta.code)
    if "title" in kv:
        meta.title, meta.sources["title"] = kv["title"], "baslik_tablosu"
    elif _informative(from_file):
        meta.title, meta.sources["title"] = from_file, "dosya_adi"
    elif t := _title_from_header(header_text, meta.code):
        meta.title, meta.sources["title"] = t, "ustbilgi"
    elif from_file:
        meta.title, meta.sources["title"] = from_file, "dosya_adi"

    meta.doc_type = _type_from(meta.title, meta.code)
    if meta.doc_type:
        meta.sources["doc_type"] = "kural"

    def date_of(name: str) -> str | None:
        return parse_date(kv.get(name, "")) or parse_date(iv.get(name, "")[:20])

    meta.revision_date = date_of("revision_date") or date_of("issue_date")
    meta.effective_date = date_of("effective_date")
    return meta
