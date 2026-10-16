"""Karar matrisi dosyası (xlsx / csv) okuma ve sonuç kolonlarını yazma. LLM yok.

İki biçim desteklenir:
- düz tablo: bir satır = bir karar; kolonlar serbest adlı (Karar / Hazırlayan / Onaylayan / Yetkili / Limit / Süre ...)
- RACI: satır = karar, kolon = rol, hücre = harf (R/A/C/I veya H/O/K/B ...). Harf anlamları sayfadaki açıklamadan
  ("A: Onaylayan") okunur, yoksa yaygın kalıplar varsayılır ve satıra not düşülür.
"""

import csv
import io
import re
from copy import copy
from dataclasses import dataclass, field

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..ontology import DecisionStatus
from ..textnorm import fold
from .quantity import Quantity, parse_quantities, unit_in_header

MAX_SCAN_ROWS = 25     # başlık satırı en çok bu satırda aranır


class MatrixError(ValueError):
    """Dosya karar matrisi olarak okunamadı (kullanıcıya gösterilir)."""


# ---- başlık eşleme ----------------------------------------------------------------------------------------------
# alan → eş anlamlı başlıklar (katlanmış). Tam eşleşme 3, kelime dizisi olarak içerme 2 puan; en yüksek puan kazanır.
FIELD_SYNONYMS: dict[str, list[str]] = {
    "onaylayan": ["onaylayan", "onay veren", "onaylayici", "onay", "onay makami", "onay yetkilisi", "karar veren",
                  "onaylayacak"],
    "verici": ["karar verici", "karar vericisi", "karar veren birim"],
    "yetkili": ["yetkili", "yetki sahibi", "karar yetkilisi", "yetkili makam", "yetki", "yetkili kisi"],
    "hazirlayan": ["hazirlayan", "oneren", "talep eden", "baslatan", "baslatici", "talep sahibi", "uygulayan",
                   "uygulayici", "sorumlu", "yurutecek", "hazirlayici", "talep eden birim"],
    "bilgi": ["bilgi verilen", "bilgilendirilen", "bilgi", "bilgi alan", "bilgilendirme"],
    "danisilan": ["danisilan", "gorus", "gorus alinan", "danisma", "gorusu alinan"],
    "limit": ["limit", "tutar", "yetki limiti", "esik", "butce", "tutar limiti", "para limiti", "limit tutari",
              "tutar siniri", "esik deger"],
    "sure": ["sure", "sla", "termin", "vade", "yanit suresi", "sure siniri", "islem suresi"],
    "dokuman": ["ilgili dokuman", "dokuman", "dayanak", "referans", "ilgili prosedur", "dokuman no", "dokuman kodu",
                "dayanak dokuman", "ilgili dokuman no", "prosedur"],
    "no": ["no", "sira", "s no", "sira no", "kod", "madde", "id", "sn"],
    "karar": ["karar", "karar konusu", "faaliyet", "islem", "konu", "is tanimi", "yetki konusu", "surec adimi",
              "aktivite", "karar maddesi", "yetki alani", "is", "karar/faaliyet", "faaliyet/karar",
              "karar tanimi", "tanim", "tanimi", "aciklama", "aciklamasi", "karar aciklamasi"],
    "karar_tipi": ["karar tipi", "karar turu", "tipi", "turu", "tip", "tur"],
    "birim": ["birim", "bolum", "departman"],
    "surec": ["karar sureci", "surec", "ilgili surec"],
    "katilimci": ["katilimci", "ortak birimler", "ortak brimler", "katilimci ortak birimler"],
    "notlar": ["not", "notlar", "aciklama notu"],
}
ROLE_FIELDS = ("hazirlayan", "onaylayan", "yetkili", "verici", "bilgi", "danisilan")
CONTEXT_FIELDS = ("karar_tipi", "birim", "surec", "katilimci", "notlar")


def _norm_header(h: str) -> str:
    h = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", str(h or ""))
    return re.sub(r"[^a-z0-9/]+", " ", fold(h)).strip()


def classify_header(header: str) -> str | None:
    """'Karar Konusu' → 'karar', 'Hazırlayan / Öneren' → 'hazirlayan', 'Limit (TL)' → 'limit'."""
    h = _norm_header(header)
    if not h:
        return None
    best: tuple[int, int, str] | None = None
    parts = [p.strip() for p in h.split("/") if p.strip()] or [h]
    for fld, syns in FIELD_SYNONYMS.items():
        for syn in syns:
            if "/" in syn:
                continue
            for text in parts + ([h] if len(parts) > 1 else []):
                if text == syn:
                    score = 3
                elif f" {syn} " in f" {text} ":
                    score = 2
                else:
                    continue
                cand = (score, len(syn), fld)
                if best is None or cand[:2] > best[:2]:
                    best = cand
    if best and best[2] == "karar" and re.search(r"\b(tipi|turu|tip|tur)\b", h):
        return "karar_tipi"                 # "Karar Tipi / Türü" karar metni değildir
    return best[2] if best else None


# ---- RACI harfleri ------------------------------------------------------------------------------------------------
DEFAULT_LETTERS = {"R": "hazirlayan", "A": "onaylayan", "C": "danisilan", "I": "bilgi",
                   "H": "hazirlayan", "O": "onaylayan", "K": "danisilan", "B": "bilgi",
                   "S": "hazirlayan", "Y": "onaylayan", "U": "hazirlayan"}
AMBIGUOUS_LETTERS = {"K": "K (Katkı/Konsülte/Karar)", "S": "S (Sorumlu/Destek)", "Y": "Y (Yetkili)", "U": "U (Uygulayan)"}
_LEGEND = re.compile(r"(?<![A-Za-zÇĞİÖŞÜçğıöşü])([A-ZÇĞİÖŞÜ])\s*(?:[:=]|\s[-–]\s)\s*")
_LETTER_CELL = re.compile(r"^[A-ZÇĞİÖŞÜa-zçğıöşü](?:\s*[/,+&\-]\s*[A-ZÇĞİÖŞÜa-zçğıöşü])*$")


def _meaning_to_field(text: str) -> str | None:
    t = fold(text)
    for key, fld in (("danis", "danisilan"), ("consult", "danisilan"), ("gorus", "danisilan"), ("katki", "danisilan"),
                     ("bilgi", "bilgi"), ("inform", "bilgi"),
                     ("onay", "onaylayan"), ("accountable", "onaylayan"), ("yetkili", "onaylayan"),
                     ("karar", "onaylayan"), ("hazirla", "hazirlayan"), ("sorumlu", "hazirlayan"),
                     ("uygula", "hazirlayan"), ("responsible", "hazirlayan"), ("yurut", "hazirlayan")):
        if key in t:
            return fld
    return None


def _letters(cell: str) -> list[str]:
    return [c.upper() for c in re.findall(r"[A-ZÇĞİÖŞÜa-zçğıöşü]", cell)] if _LETTER_CELL.match(cell.strip()) else []


# ---- veri sınıfları -----------------------------------------------------------------------------------------------
@dataclass
class DecisionRow:
    idx: int
    sheet_row: int                      # dosyadaki 1 tabanlı satır no (çıktı bu satıra yazılır)
    karar: str
    bolum: str | None = None
    hazirlayan: list[str] = field(default_factory=list)
    onaylayan: list[str] = field(default_factory=list)
    yetkili: list[str] = field(default_factory=list)
    bilgi: list[str] = field(default_factory=list)
    danisilan: list[str] = field(default_factory=list)
    verici: list[str] = field(default_factory=list)     # "Karar Verici" hücresi (birim adı olabilir; "/" = ortak/kademeli)
    sheet: str | None = None
    karar_tipi: str = ""
    birim: str = ""
    surec: str = ""
    notlar: str = ""
    katilimci: list[str] = field(default_factory=list)
    katilan: list[str] = field(default_factory=list)   # anlamı bilinmeyen işaretle (ör. X) bağlanan roller
    limit_text: str = ""
    sure_text: str = ""
    dokuman_text: str = ""
    limit: Quantity | None = None
    sure: Quantity | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def authorities(self) -> list[str]:
        """Karar yetkisi taşıyan roller: onaylayan + yetkili (tekrarsız, sıralı)."""
        return list(dict.fromkeys(self.onaylayan + self.yetkili + self.verici))

    def as_input(self) -> dict:
        return {"karar": self.karar, "bolum": self.bolum, "hazirlayan": self.hazirlayan, "onaylayan": self.onaylayan,
                "yetkili": self.yetkili, "karar_verici": self.verici, "sayfa": self.sheet,
                "karar_tipi": self.karar_tipi or None, "birim": self.birim or None, "surec": self.surec or None,
                "notlar": self.notlar or None, "katilimci": self.katilimci, "bilgi": self.bilgi, "danisilan": self.danisilan,
                "limit": self.limit_text or None, "sure": self.sure_text or None,
                "ilgili_dokuman": self.dokuman_text or None}


@dataclass
class ParsedMatrix:
    filename: str
    kind: str                                   # 'duz' | 'raci'
    sheet: str | None
    header_row: int
    columns: dict[str, list[str]]               # alan → eşleşen başlık metinleri
    rows: list[DecisionRow]
    grid: list[list[str]]                       # CSV çıktısı için ham ızgara (xlsx'te boş)
    last_col: int
    is_xlsx: bool
    raw: bytes
    letter_map: dict[str, str] = field(default_factory=dict)
    letter_source: str | None = None            # 'aciklama' | 'varsayilan'
    role_columns: list[str] = field(default_factory=list)
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    sheets: list[dict] = field(default_factory=list)     # işlenen her sayfa (kendi başlık satırı / kolon eşlemesiyle)

    def meta(self) -> dict:
        return {"dosya": self.filename, "sayfalar": [{k: v for k, v in sh.items() if k != "last_col"} for sh in self.sheets],
                "bicim": self.kind, "sayfa": self.sheet, "baslik_satiri": self.header_row,
                "kolon_eslesmesi": self.columns, "raci_rol_kolonlari": self.role_columns,
                "harf_anlamlari": self.letter_map or None, "harf_kaynagi": self.letter_source,
                "atlanan_satir": self.skipped, "uyarilar": self.warnings}


# ---- okuma --------------------------------------------------------------------------------------------------------
def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).replace("\r\n", "\n").replace("\r", "\n").strip()


def _read_csv(data: bytes) -> list[list[str]]:
    for enc in ("utf-8-sig", "cp1254"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
    return [[_cell(c) for c in row] for row in csv.reader(io.StringIO(text), dialect)]


def _read_xlsx_sheets(data: bytes) -> list[tuple[str, list[list[str]]]]:
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    out = []
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        out.append((ws.title, [[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)]))
    return out


def _find_header(grid: list[list[str]]) -> tuple[int, dict[int, str], int] | None:
    """(satır indeksi 0 tabanlı, {kolon: alan}, puan) — en iyi başlık satırı."""
    best = None
    for r, row in enumerate(grid[:MAX_SCAN_ROWS]):
        cols: dict[int, str] = {}
        used: set[str] = set()
        karar_best: tuple[int, int] | None = None
        for c, h in enumerate(row):
            fld = classify_header(h) if h else None
            if fld == "karar":      # birden çok aday: "Tanımı/Açıklaması" içeren başlık önceliklidir
                pr = 2 if re.search(r"tanim|aciklama", _norm_header(h)) else 1
                if karar_best is None or pr > karar_best[0]:
                    karar_best = (pr, c)
            elif fld and (fld not in used or fld in ROLE_FIELDS + ("limit", "sure", "dokuman")):
                cols[c] = fld
                used.add(fld)
        if karar_best is None:
            continue
        cols[karar_best[1]] = "karar"
        used.add("karar")
        score = len(used)
        if best is None or score > best[2]:
            best = (r, cols, score)
    return best


def _find_raci_header(grid: list[list[str]]) -> tuple[int, int, list[int]] | None:
    """Başlık satırı, karar kolonu, rol kolonları. Rol kolonları: başlığı olan ve altında harf kodları bulunan kolonlar."""
    for r, row in enumerate(grid[:MAX_SCAN_ROWS]):
        texts = [(c, h) for c, h in enumerate(row) if h and classify_header(h) not in ("no", "limit", "sure", "dokuman")]
        if len(texts) < 3:
            continue
        kcol = next((c for c, h in texts if classify_header(h) == "karar"), None)
        if kcol is None:
            kcol = texts[0][0]
        role_cols = []
        for c, h in texts:
            if c == kcol:
                continue
            below = [grid[i][c] for i in range(r + 1, len(grid)) if c < len(grid[i]) and grid[i][c]]
            if below and sum(1 for v in below if _LETTER_CELL.match(v)) / len(below) >= 0.7:
                role_cols.append(c)
        if len(role_cols) >= 2:
            return r, kcol, role_cols
    return None


def split_roles(text: str) -> list[str]:
    parts = re.split(r"\s*(?:/|;|\n|\+|,|\sveya\s)\s*", text or "")
    return [p.strip(" .-") for p in parts if p and p.strip(" .-")]


def _quantity(texts: list[str], header: str | None, notes: list[str], label: str, default_op="<=") -> Quantity | None:
    text = "; ".join(t for t in texts if t)
    if not text:
        return None
    qs = parse_quantities(text, default_unit=unit_in_header(header), default_op=default_op)
    if not qs:
        notes.append(f"{label} sayısal olarak ayrıştırılamadı: '{text[:60]}'")
        return None
    if len(qs) > 1:
        notes.append(f"{label} için birden çok değer var, ilki kullanıldı: {qs[0]}")
    return qs[0]


def parse_matrix(data: bytes, filename: str) -> ParsedMatrix:
    name = (filename or "").lower()
    is_xlsx = name.endswith((".xlsx", ".xlsm")) or data[:2] == b"PK"
    if is_xlsx:
        try:
            sheets = _read_xlsx_sheets(data)
        except Exception as e:  # bozuk dosya
            raise MatrixError(f"Excel dosyası açılamadı: {e}") from e
    elif name.endswith((".csv", ".txt")):
        sheets = [(None, _read_csv(data))]
    else:
        raise MatrixError("Desteklenen biçimler: .xlsx, .csv")

    parsed_sheets: list[ParsedMatrix] = []
    notes: list[str] = []
    for sheet, grid in sheets:
        if sheet == OUTPUT_SUMMARY_SHEET:
            continue
        raci = _find_raci_header(grid)     # rol kolonlarının altında tek harf kodları varsa RACI
        found, kind = None, None
        if raci:
            found, kind = raci, "raci"
        else:
            flat = _find_header(grid)
            if flat and any(f in ROLE_FIELDS + ("limit", "sure", "dokuman") for f in set(flat[1].values())):
                found, kind = flat, "duz"
        if not found:
            notes.append(f"Sayfa '{sheet}' atlandı: başlık satırı bulunamadı.")
            continue
        p = (_parse_flat if kind == "duz" else _parse_raci)(grid, found)
        p.sheet = sheet
        for r in p.rows:
            r.sheet = sheet
        parsed_sheets.append(p)
    if not parsed_sheets:
        seen = [h for _, g in sheets for row in g[:5] for h in row if h][:12]
        raise MatrixError("Başlık satırı bulunamadı. En az bir 'Karar' (veya Karar Tanımı / Karar Konusu / Faaliyet) kolonu "
                          "ve Hazırlayan / Onaylayan / Karar Verici / Yetkili / Limit / Süre / İlgili Doküman kolonlarından "
                          f"biri (ya da RACI rol kolonları) gerekir. Görülen başlıklar: {seen}")
    parsed = parsed_sheets[0]
    parsed.filename, parsed.is_xlsx, parsed.raw = filename, is_xlsx, data
    parsed.grid = [] if is_xlsx else grid_of_first(sheets, parsed.sheet)
    parsed.sheets = [{"sayfa": p.sheet, "bicim": p.kind, "baslik_satiri": p.header_row, "kolon_eslesmesi": p.columns,
                      "raci_rol_kolonlari": p.role_columns, "harf_anlamlari": p.letter_map or None,
                      "harf_kaynagi": p.letter_source, "atlanan_satir": p.skipped, "uyarilar": p.warnings,
                      "satir_sayisi": len(p.rows), "last_col": p.last_col} for p in parsed_sheets]
    parsed.rows = [r for p in parsed_sheets for r in p.rows]
    for n, r in enumerate(parsed.rows, 1):
        r.idx = n
    multi = len(parsed_sheets) > 1
    parsed.warnings = notes + [(f"[{p.sheet}] " if multi else "") + w for p in parsed_sheets for w in p.warnings]
    parsed.skipped = sum(p.skipped for p in parsed_sheets)
    if not parsed.rows:
        raise MatrixError("Başlık bulundu ama karar satırı yok (boş veya yalnızca bölüm başlıkları).")
    return parsed


def grid_of_first(sheets, name):
    return next((g for sh, g in sheets if sh == name), [])


_DOC_COL = re.compile(r"[A-ZÇĞİÖŞÜ]{1,5}[.\-][A-ZÇĞİÖŞÜ0-9]")


def _fix_shifted_headers(grid, hr, cols):
    """Başlık satırı veri kolonlarına göre bir kolon kaymışsa (ör. 'Karar Verici' altında doküman kodları, sondaki başlık
    boş) kaydırır. Dönüş: (yeni kolon eşlemesi, {kolon: başlık metni}, uyarı | None)."""
    header = list(grid[hr])
    ncols = max(len(r) for r in grid)
    htext = {c: header[c] for c in range(len(header))}
    for c, f in sorted(cols.items()):
        if f not in ROLE_FIELDS:
            continue
        vals = [g[c] for g in grid[hr + 1:] if c < len(g) and g[c]]
        if len(vals) >= 3 and sum(1 for v in vals if _DOC_COL.search(v.upper())) / len(vals) >= 0.6:
            e = next((i for i in range(c + 1, ncols) if not (header[i] if i < len(header) else "")), None)
            if e is None:
                return cols, htext, None
            new = {k: v for k, v in cols.items() if k < c or k > e}
            new[c] = "dokuman"
            htext[c] = "(başlıksız: İlgili Doküman)"
            for k in range(c, e):
                if k in cols:
                    new[k + 1] = cols[k]
                htext[k + 1] = header[k] if k < len(header) else ""
            return new, htext, (f"Başlıklar bir kolon kaymış görünüyor: '{header[c]}' kolonunda doküman kodları var; "
                                "bu kolon İlgili Doküman, sonraki başlıklar bir kolon sağa kaydırılarak yorumlandı.")
    return cols, htext, None


def split_deciders(text: str) -> list[str]:
    """'Satınalma/İCKB', 'Yatırım ve Bakım-İCKB' → ayrı karar vericiler (ortak/kademeli). 'Ar-Ge' bölünmez."""
    t = re.sub(r"(?i)ar-ge", "Arge", text or "")
    return [p.strip(" .") for p in re.split(r"\s*(?:/|;|\n|\+|,|\sveya\s|\s-\s|(?<=\w)-(?=[A-ZÇĞİÖŞÜ]))\s*", t) if p.strip(" .")]


def _parse_flat(grid, found) -> ParsedMatrix:
    hr, cols, _ = found
    cols, htext, shift_warning = _fix_shifted_headers(grid, hr, cols)
    header_ = grid[hr]
    header = [htext.get(c, header_[c] if c < len(header_) else "") for c in range(max(len(r) for r in grid))]
    by_field: dict[str, list[int]] = {}
    for c, f in sorted(cols.items()):
        by_field.setdefault(f, []).append(c)
    rows: list[DecisionRow] = []
    section, skipped = None, 0
    ncols = max(len(r) for r in grid)

    def vals(row, f):
        return [row[c] for c in by_field.get(f, []) if c < len(row) and row[c]]

    for r in range(hr + 1, len(grid)):
        row = grid[r] + [""] * (ncols - len(grid[r]))
        if not any(row):
            skipped += 1
            continue
        karar = " ".join(vals(row, "karar")).strip()
        others = [v for f in by_field if f not in ("karar", "no") for v in vals(row, f)]
        if not karar:
            skipped += 1
            continue
        if not others:  # yalnızca karar metni var → bölüm başlığı
            section, skipped = karar, skipped + 1
            continue
        d = DecisionRow(idx=len(rows) + 1, sheet_row=r + 1, karar=karar, bolum=section)
        for f in ROLE_FIELDS:
            splitter = split_deciders if f == "verici" else split_roles
            setattr(d, f, [x for v in vals(row, f) for x in splitter(v)])
        d.karar_tipi, d.birim = " ".join(vals(row, "karar_tipi")), " ".join(vals(row, "birim"))
        d.surec, d.notlar = " ".join(vals(row, "surec")), " ".join(vals(row, "notlar"))
        d.katilimci = [x for v in vals(row, "katilimci") for x in split_roles(v)]
        d.limit_text, d.sure_text = "; ".join(vals(row, "limit")), "; ".join(vals(row, "sure"))
        d.dokuman_text = "; ".join(vals(row, "dokuman"))
        lh = header[by_field["limit"][0]] if "limit" in by_field else None
        sh = header[by_field["sure"][0]] if "sure" in by_field else None
        d.limit = _quantity(vals(row, "limit"), lh, d.notes, "Limit")
        d.sure = _quantity(vals(row, "sure"), sh, d.notes, "Süre")
        rows.append(d)
    columns = {f: [header[c] for c in cs] for f, cs in by_field.items()}
    warnings = []
    if shift_warning:
        warnings.append(shift_warning)
    if not any(f in by_field for f in ("onaylayan", "yetkili", "hazirlayan", "verici")):
        warnings.append("Hazırlayan / Onaylayan / Yetkili kolonu yok; yalnızca karar konusu için dayanak aranır.")
    if "karar_tipi" in by_field and "karar" in by_field:
        warnings.append(f"Karar metni '{header[by_field['karar'][0]]}' kolonundan alındı; "
                        f"'{header[by_field['karar_tipi'][0]]}' bağlam olarak kullanıldı.")
    if "hazirlayan" in by_field and any("sorumlu" in fold(header[c]) for c in by_field["hazirlayan"]):
        warnings.append("'Sorumlu' kolonu hazırlayan/uygulayan olarak yorumlandı.")
    return ParsedMatrix("", "duz", None, hr + 1, columns, rows, [], ncols, True, b"", skipped=skipped, warnings=warnings)


def _parse_raci(grid, found) -> ParsedMatrix:
    hr, kcol, role_cols = found
    header = grid[hr]
    ncols = max(len(r) for r in grid)
    meta_cols: dict[str, list[int]] = {}
    for c, h in enumerate(header):
        f = classify_header(h) if h else None
        if f in ("limit", "sure", "dokuman"):
            meta_cols.setdefault(f, []).append(c)
    body = [(r, grid[r] + [""] * (ncols - len(grid[r]))) for r in range(hr + 1, len(grid))]
    used_letters: set[str] = set()
    last_data = hr
    for r, row in body:
        ls = [x for c in role_cols for x in _letters(row[c])]
        if ls:
            used_letters.update(ls)
            last_data = r
    # açıklama (legend): tablo gövdesinin dışındaki hücreler
    letter_map: dict[str, str] = {}
    last_role_col = max(role_cols + [kcol])
    for r, row in enumerate(grid):
        for c, v in enumerate(row):
            if not v or (hr < r <= last_data and c <= last_role_col):
                continue
            marks = list(_LEGEND.finditer(v))
            for i, m in enumerate(marks):
                end = marks[i + 1].start() if i + 1 < len(marks) else len(v)
                meaning = re.split(r"[,;|\n]", v[m.end():end])[0][:40]
                f = _meaning_to_field(meaning) if len(meaning.strip()) >= 3 else None
                if f:
                    letter_map[m.group(1).upper()] = f
    source = "aciklama" if letter_map else "varsayilan"
    warnings: list[str] = []
    if not letter_map:
        letter_map = {k: v for k, v in DEFAULT_LETTERS.items() if k in used_letters}
        if used_letters:
            warnings.append("Harf anlamları sayfada bulunamadı; yaygın kalıp varsayıldı: " +
                            ", ".join(f"{k}={v}" for k, v in sorted(letter_map.items())) + ".")
    else:
        for k in used_letters - set(letter_map):
            if k in DEFAULT_LETTERS:
                letter_map[k] = DEFAULT_LETTERS[k]
                warnings.append(f"'{k}' harfi açıklamada yok; '{DEFAULT_LETTERS[k]}' varsayıldı.")
    rows: list[DecisionRow] = []
    section, skipped = None, 0
    for r, row in body:
        karar = row[kcol].strip()
        letters = {c: _letters(row[c]) for c in role_cols}
        if not any(letters.values()):
            if karar and not any(row[c] for c in role_cols) and r <= last_data:
                section = karar         # harf içermeyen karar satırı → bölüm başlığı
            skipped += 1
            continue
        if not karar:
            skipped += 1
            warnings.append(f"Satır {r + 1}: harf var ama karar metni boş, atlandı.")
            continue
        d = DecisionRow(idx=len(rows) + 1, sheet_row=r + 1, karar=karar, bolum=section)
        for c, ls in letters.items():
            role = header[c].replace("\n", " ").strip()
            for lt in ls:
                fld = letter_map.get(lt)
                if fld is None:
                    d.katilan.append(role)
                    d.notes.append(f"'{lt}' harfinin anlamı bilinmiyor ({role}); karşılaştırmaya katılmadı.")
                    continue
                if source == "varsayilan" and lt in AMBIGUOUS_LETTERS:
                    d.notes.append(f"{AMBIGUOUS_LETTERS[lt]} açıklaması yok; {role} → {fld} varsayıldı.")
                if role not in getattr(d, fld):
                    getattr(d, fld).append(role)
        d.limit_text = "; ".join(row[c] for c in meta_cols.get("limit", []) if row[c])
        d.sure_text = "; ".join(row[c] for c in meta_cols.get("sure", []) if row[c])
        d.dokuman_text = "; ".join(row[c] for c in meta_cols.get("dokuman", []) if row[c])
        lh = header[meta_cols["limit"][0]] if "limit" in meta_cols else None
        sh = header[meta_cols["sure"][0]] if "sure" in meta_cols else None
        d.limit = _quantity([d.limit_text], lh, d.notes, "Limit")
        d.sure = _quantity([d.sure_text], sh, d.notes, "Süre")
        if not d.onaylayan and not d.yetkili:
            d.notes.append("Matriste onaylayan (A) rolü işaretli değil; rol karşılaştırması yapılmadı.")
        rows.append(d)
    columns = {"karar": [header[kcol]], **{f: [header[c] for c in cs] for f, cs in meta_cols.items()}}
    return ParsedMatrix("", "raci", None, hr + 1, columns, rows, [], ncols, True, b"", letter_map=letter_map,
                        letter_source=source, role_columns=[header[c].replace("\n", " ").strip() for c in role_cols],
                        skipped=skipped, warnings=warnings)


# ---- yazma --------------------------------------------------------------------------------------------------------
OUT_HEADERS = ["Durum", "Kaynak Doküman(lar)", "Madde", "Alıntı", "Açıklama", "Eşleşen Rol",
               "Matristeki Doküman Kontrolü", "Doğrulanmamış Kaynak"]
OUTPUT_SUMMARY_SHEET = "Karar Kontrol Özeti"
STATUS_FILL = {DecisionStatus.KAYNAKLI: "C6EFCE", DecisionStatus.CELISKI: "FFC7CE",
               DecisionStatus.KISMI: "FFEB9C", DecisionStatus.KAYNAK_YOK: "D9D9D9"}


def _sources_text(r: dict) -> tuple[str, str, str]:
    srcs = r.get("kaynaklar") or []
    docs = "\n".join(f"{s['doc_code']} Rev.{s['revision']}" + (f" ({s['title']})" if s.get("title") else "") for s in srcs)
    clauses = "\n".join(s.get("clause_no") or "-" for s in srcs)
    quotes = "\n".join(f"{i}) “{s['quote'][:500]}”" for i, s in enumerate(srcs, 1))
    return docs, clauses, quotes


def _roles_text(r: dict) -> str:
    lines = []
    for m in r.get("eslesen_roller") or []:
        if m.get("rol"):
            lines.append(f"{m['girdi']} → {m['rol']} ({m['yontem']}, {m['skor']:.2f})")
        else:
            sug = ", ".join(s["ad"] for s in m.get("oneriler") or [])
            lines.append(f"{m['girdi']} → ? (sistemde yok" + (f"; öneri: {sug}" if sug else "") + ")")
    return "\n".join(lines)


def _docs_check_text(r: dict) -> str:
    refs = r.get("matris_dokumanlari") or []
    if not refs:
        return ""
    lines = [r.get("dokuman_kontrolu") or ""]
    for d in refs:
        extra = f" → {d['doc_code']} Rev.{d['revision']}" if d.get("doc_code") else ""
        lines.append(f"{d['girdi']}{(' md.' + d['madde']) if d.get('madde') else ''}: {d['durum']}{extra}")
    return "\n".join(lines)


def result_cells(r: dict) -> list[str]:
    docs, clauses, quotes = _sources_text(r)
    return [r.get("durum") or "", docs, clauses, quotes, r.get("aciklama") or "", _roles_text(r), _docs_check_text(r),
            "Evet" if r.get("dogrulanmamis") else "Hayır"]


def render_xlsx(parsed: ParsedMatrix, results: list[dict], summary: dict) -> bytes:
    """Orijinal dosyanın her sayfasına sonuç kolonlarını ve 'Karar Kontrol Özeti' sayfasını ekler."""
    if parsed.is_xlsx:
        wb = openpyxl.load_workbook(io.BytesIO(parsed.raw))   # formüller korunur
    else:
        wb = openpyxl.Workbook()
        ws0 = wb.active
        ws0.title = "Karar Matrisi"
        for r, row in enumerate(parsed.grid, 1):
            for c, v in enumerate(row, 1):
                ws0.cell(r, c, v)
    widths = [14, 28, 10, 60, 55, 40, 36, 14]
    infos = parsed.sheets or [{"sayfa": parsed.sheet, "baslik_satiri": parsed.header_row, "last_col": parsed.last_col}]
    for info in infos:
        ws = wb[info["sayfa"]] if info["sayfa"] in wb.sheetnames else wb.active
        header_row = info["baslik_satiri"]
        first = max(ws.max_column, info["last_col"]) + 1
        hdr_src = ws.cell(header_row, first - 1)
        for i, title in enumerate(OUT_HEADERS):
            cell = ws.cell(header_row, first + i, title)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F5FAE")
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if hdr_src.border:
                cell.border = copy(hdr_src.border)
            ws.column_dimensions[get_column_letter(first + i)].width = widths[i]
        for res in results:
            if "sayfa" in res and res["sayfa"] != info["sayfa"]:
                continue
            r = res["satir"]
            for i, v in enumerate(result_cells(res)):
                cell = ws.cell(r, first + i, v[:32000])
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            status = res.get("durum")
            if status in STATUS_FILL:
                ws.cell(r, first).fill = PatternFill("solid", fgColor=STATUS_FILL[status])
                ws.cell(r, first).font = Font(bold=True)
    _summary_sheet(wb, parsed, results, summary)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _summary_sheet(wb, parsed: ParsedMatrix, results: list[dict], summary: dict) -> None:
    name = OUTPUT_SUMMARY_SHEET
    if name in wb.sheetnames:
        del wb[name]
    ws = wb.create_sheet(name)
    bold = Font(bold=True)
    ws.append(["Karar Matrisi Kontrol Özeti"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Dosya: {parsed.filename}", f"Sayfa sayısı: {len(parsed.sheets) or 1}"])
    ws.append([])
    ws.append(["Durum", "Satır sayısı"])
    for c in ws[ws.max_row]:
        c.font = bold
    for st in DecisionStatus:
        ws.append([st.value, summary.get("durum", {}).get(st.value, 0)])
        ws.cell(ws.max_row, 1).fill = PatternFill("solid", fgColor=STATUS_FILL[st])
    ws.append(["Toplam kontrol edilen", summary.get("kontrol_edilen", len(results))])
    ws.append(["Doğrulanmamış kaynağa dayanan", summary.get("dogrulanmamis", 0)])
    ws.append(["Doğrulanamadığı için atılan kaynak", summary.get("atilan_kaynak", 0)])
    sheets = summary.get("sayfalar") or {}
    if sheets:
        ws.append([])
        ws.append(["Sayfa"] + [st.value for st in DecisionStatus])
        for c in ws[ws.max_row]:
            c.font = bold
        for sh, counts in sheets.items():
            ws.append([sh] + [counts.get(st.value, 0) for st in DecisionStatus])
    dc = summary.get("dokuman_kontrolu") or {}
    if dc:
        ws.append([])
        ws.append(["Matristeki doküman kontrolü", "Satır sayısı"])
        for c in ws[ws.max_row]:
            c.font = bold
        for k, v in dc.items():
            ws.append([k, v])
        if summary.get("sistemde_yok_dokumanlar"):
            ws.append(["Sistemde olmayan dokümanlar", ", ".join(summary["sistemde_yok_dokumanlar"])])
    for title, status in (("Dokümanlarda dayanağı bulunamayan kararlar", DecisionStatus.KAYNAK_YOK),
                          ("Dokümanla çelişen kararlar", DecisionStatus.CELISKI)):
        ws.append([])
        ws.append([title])
        ws.cell(ws.max_row, 1).font = bold
        ws.append(["Sayfa / Satır", "Karar", "Açıklama"])
        for c in ws[ws.max_row]:
            c.font = bold
        rows = [r for r in results if r.get("durum") == status]
        for r in rows:
            ws.append([f"{r.get('sayfa') or '-'} / {r['satir']}", r["karar"], r.get("aciklama") or ""])
        if not rows:
            ws.append(["-", "(yok)", ""])
    if parsed.warnings or any(r.get("uyarilar") for r in results):
        ws.append([])
        ws.append(["Uyarılar"])
        ws.cell(ws.max_row, 1).font = bold
        for w in parsed.warnings:
            ws.append(["", w])
        for r in results:
            for w in r.get("uyarilar") or []:
                ws.append([f"{r.get('sayfa') or '-'} / {r['satir']}", w])
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 80
    for row in ws.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
