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
                  "karar verici", "onaylayacak"],
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
              "aktivite", "karar maddesi", "yetki alani", "is", "karar/faaliyet", "faaliyet/karar"],
}
ROLE_FIELDS = ("hazirlayan", "onaylayan", "yetkili", "bilgi", "danisilan")


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
        return list(dict.fromkeys(self.onaylayan + self.yetkili))

    def as_input(self) -> dict:
        return {"karar": self.karar, "bolum": self.bolum, "hazirlayan": self.hazirlayan, "onaylayan": self.onaylayan,
                "yetkili": self.yetkili, "bilgi": self.bilgi, "danisilan": self.danisilan,
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

    def meta(self) -> dict:
        return {"dosya": self.filename, "bicim": self.kind, "sayfa": self.sheet, "baslik_satiri": self.header_row,
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
        for c, h in enumerate(row):
            fld = classify_header(h) if h else None
            if fld and (fld not in used or fld in ROLE_FIELDS + ("limit", "sure", "dokuman")):
                cols[c] = fld
                used.add(fld)
        if "karar" not in used:
            continue
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

    candidates = []
    for sheet, grid in sheets:
        grid = [row for row in grid]
        raci = _find_raci_header(grid)     # rol kolonlarının altında tek harf kodları varsa RACI
        if raci:
            candidates.append((100 + len(raci[2]), "raci", sheet, grid, raci))
            continue
        flat = _find_header(grid)
        recog = flat and sum(1 for f in set(flat[1].values()) if f in ROLE_FIELDS + ("limit", "sure", "dokuman"))
        if flat and recog:
            candidates.append((flat[2], "duz", sheet, grid, flat))
    if not candidates:
        seen = [h for _, g in sheets for row in g[:5] for h in row if h][:12]
        raise MatrixError("Başlık satırı bulunamadı. En az bir 'Karar' (veya Karar Konusu / Faaliyet) kolonu ve "
                          "Hazırlayan / Onaylayan / Yetkili / Limit / Süre kolonlarından biri (ya da RACI rol kolonları) "
                          f"gerekir. Görülen başlıklar: {seen}")
    _, kind, sheet, grid, found = max(candidates, key=lambda c: c[0])
    parsed = (_parse_flat if kind == "duz" else _parse_raci)(grid, found)
    parsed.filename, parsed.sheet, parsed.is_xlsx, parsed.raw = filename, sheet, is_xlsx, data
    parsed.grid = [] if is_xlsx else grid
    if not parsed.rows:
        raise MatrixError("Başlık bulundu ama karar satırı yok (boş veya yalnızca bölüm başlıkları).")
    return parsed


def _parse_flat(grid, found) -> ParsedMatrix:
    hr, cols, _ = found
    header = grid[hr]
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
            setattr(d, f, [x for v in vals(row, f) for x in split_roles(v)])
        d.limit_text, d.sure_text = "; ".join(vals(row, "limit")), "; ".join(vals(row, "sure"))
        d.dokuman_text = "; ".join(vals(row, "dokuman"))
        lh = header[by_field["limit"][0]] if "limit" in by_field else None
        sh = header[by_field["sure"][0]] if "sure" in by_field else None
        d.limit = _quantity(vals(row, "limit"), lh, d.notes, "Limit")
        d.sure = _quantity(vals(row, "sure"), sh, d.notes, "Süre")
        rows.append(d)
    columns = {f: [header[c] for c in cs] for f, cs in by_field.items()}
    warnings = []
    if not any(f in by_field for f in ("onaylayan", "yetkili", "hazirlayan")):
        warnings.append("Hazırlayan / Onaylayan / Yetkili kolonu yok; yalnızca karar konusu için dayanak aranır.")
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
OUT_HEADERS = ["Durum", "Kaynak Doküman(lar)", "Madde", "Alıntı", "Açıklama", "Eşleşen Rol", "Doğrulanmamış Kaynak"]
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


def result_cells(r: dict) -> list[str]:
    docs, clauses, quotes = _sources_text(r)
    return [r.get("durum") or "", docs, clauses, quotes, r.get("aciklama") or "", _roles_text(r),
            "Evet" if r.get("dogrulanmamis") else "Hayır"]


def render_xlsx(parsed: ParsedMatrix, results: list[dict], summary: dict) -> bytes:
    """Orijinal dosyaya sonuç kolonlarını ve 'Karar Kontrol Özeti' sayfasını ekler."""
    if parsed.is_xlsx:
        wb = openpyxl.load_workbook(io.BytesIO(parsed.raw))   # formüller korunur
        ws = wb[parsed.sheet] if parsed.sheet in wb.sheetnames else wb.active
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Karar Matrisi"
        for r, row in enumerate(parsed.grid, 1):
            for c, v in enumerate(row, 1):
                ws.cell(r, c, v)
    first = max(ws.max_column, parsed.last_col) + 1
    hdr_src = ws.cell(parsed.header_row, first - 1)
    for i, title in enumerate(OUT_HEADERS):
        cell = ws.cell(parsed.header_row, first + i, title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F5FAE")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if hdr_src.border:
            cell.border = copy(hdr_src.border)
        ws.column_dimensions[get_column_letter(first + i)].width = [14, 28, 10, 60, 55, 40, 14][i]
    for res in results:
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
    name = "Karar Kontrol Özeti"
    if name in wb.sheetnames:
        del wb[name]
    ws = wb.create_sheet(name)
    bold = Font(bold=True)
    ws.append(["Karar Matrisi Kontrol Özeti"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Dosya: {parsed.filename}", f"Biçim: {'RACI' if parsed.kind == 'raci' else 'düz tablo'}",
               f"Sayfa: {parsed.sheet or '-'}"])
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
    for title, status in (("Dokümanlarda dayanağı bulunamayan kararlar", DecisionStatus.KAYNAK_YOK),
                          ("Dokümanla çelişen kararlar", DecisionStatus.CELISKI)):
        ws.append([])
        ws.append([title])
        ws.cell(ws.max_row, 1).font = bold
        ws.append(["Satır", "Karar", "Açıklama"])
        for c in ws[ws.max_row]:
            c.font = bold
        rows = [r for r in results if r.get("durum") == status]
        for r in rows:
            ws.append([r["satir"], r["karar"], r.get("aciklama") or ""])
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
                ws.append([r["satir"], w])
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 80
    for row in ws.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
