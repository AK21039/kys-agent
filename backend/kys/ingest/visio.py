"""Visio (.vsdx) okuyucu: zip + XML, COM gerekmez. Akış şemasını adım + kenar listesine çevirir.

- Şekil türü, şekil şablonunun (master) adından çıkarılır: Process / Decision / Start-End / Subprocess / Document...
- Kulvar (swimlane) = sorumlu birim: kulvar şekillerinin sınırları ile adım şeklinin merkezi eşleştirilir.
- Bağlayıcı yönü: Connects içindeki BeginX/EndX bağlantılarından; etiket (Evet/Hayır) bağlayıcının kendi metnidir.
- Kenarın bir ucu hiçbir şekle yapışık değilse, uç noktasına en yakın şekil (geometri) kullanılır ve uyarı yazılır.
Deterministiktir; LLM yok.
"""

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"v": "http://schemas.microsoft.com/office/visio/2012/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_R_ID = "{%s}id" % NS["r"]
_SHAPE = "{%s}Shape" % NS["v"]

# Şekil türleri (bu modülün çıktı sözlüğü; ontoloji enum'u değildir)
ISLEM, KARAR, BASLANGIC_BITIS, ALT_SUREC, DOKUMAN, REFERANS, VERI, NOT = (
    "ISLEM", "KARAR", "BASLANGIC_BITIS", "ALT_SUREC", "DOKUMAN", "REFERANS", "VERI", "NOT")

_MASTER_KIND = [  # (regex, tür) sırayla
    (r"decision|karar", KARAR),
    (r"start|end|terminat|ba[sş]lang|biti[sş]", BASLANGIC_BITIS),
    (r"subprocess|sub-process|predefined|alt s[uü]re", ALT_SUREC),
    (r"document|dok[uü]man|belge", DOKUMAN),
    (r"page reference|sayfa ba[gğ]|on-page|off-page", REFERANS),
    (r"^data\b|veri", VERI),
]
_CONNECTOR_MASTER = re.compile(r"connector|ba[gğ]lay[ıi]c[ıi]|1-d", re.I)
_LANE_MASTER = re.compile(r"swimlane|kulvar", re.I)
_LAYOUT_MASTER = re.compile(r"container|swimlane list|phase list|separator|kapsay|ayra[cç]", re.I)


@dataclass
class VisioShape:
    id: str
    kind: str
    text: str
    lane: str | None
    x: float
    y: float
    w: float
    h: float


@dataclass
class VisioEdge:
    source: str | None
    target: str | None
    label: str


@dataclass
class VisioPage:
    name: str
    shapes: list[VisioShape] = field(default_factory=list)
    edges: list[VisioEdge] = field(default_factory=list)
    lanes: list[str] = field(default_factory=list)
    title: str = ""
    warnings: list[str] = field(default_factory=list)

    def shape(self, sid: str | None) -> VisioShape | None:
        return next((s for s in self.shapes if s.id == sid), None)

    def out_edges(self, sid: str) -> list[VisioEdge]:
        return [e for e in self.edges if e.source == sid]

    def ordered(self) -> list[VisioShape]:
        """Akış sırası: başlangıç şekillerinden (gelen kenarı olmayan) genişlik öncelikli; kalanlar yukarıdan aşağı."""
        steps = [s for s in self.shapes if s.kind != NOT]
        ids = {s.id for s in steps}
        incoming = {e.target for e in self.edges if e.target}
        out: list[VisioShape] = []
        seen: set[str] = set()

        def visit(root: VisioShape) -> None:
            queue = [root]
            while queue:
                cur = queue.pop(0)
                if cur.id in seen:
                    continue
                seen.add(cur.id)
                out.append(cur)
                for e in self.out_edges(cur.id):
                    if e.target in ids and e.target not in seen:
                        queue.append(self.shape(e.target))

        roots = sorted((s for s in steps if s.id not in incoming or (s.kind == BASLANGIC_BITIS and self.out_edges(s.id))),
                       key=lambda s: (s.kind != BASLANGIC_BITIS, -s.y, s.x))
        for r in roots:
            visit(r)
        for s in sorted((s for s in steps if s.id not in seen), key=lambda s: (-s.y, s.x)):
            visit(s)
        return out


@dataclass
class VisioDoc:
    path: Path
    pages: list[VisioPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_YES_NO = {"evet", "hayir"}


def _fold_label(label: str) -> str:
    from ..textnorm import fold
    return fold(label).strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _shape_text(el) -> str:
    t = el.find("v:Text", NS)
    return _clean(" ".join(t.itertext())) if t is not None else ""


def _num(el, name: str) -> float | None:
    c = el.find(f"v:Cell[@N='{name}']", NS)
    try:
        return float(c.get("V")) if c is not None and c.get("V") not in (None, "") else None
    except ValueError:
        return None


def _master_names(z: zipfile.ZipFile) -> dict[str, str]:
    if "visio/masters/masters.xml" not in z.namelist():
        return {}
    root = ET.fromstring(z.read("visio/masters/masters.xml"))
    return {m.get("ID"): f"{m.get('NameU') or ''} {m.get('Name') or ''}".strip() for m in root.findall("v:Master", NS)}


def _kind_for(master: str) -> str:
    m = master.lower()
    for pat, kind in _MASTER_KIND:
        if re.search(pat, m):
            return kind
    return ISLEM


def _page_files(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    """[(sayfa adı, dosya yolu)] sayfa sırasıyla."""
    root = ET.fromstring(z.read("visio/pages/pages.xml"))
    rels = ET.fromstring(z.read("visio/pages/_rels/pages.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = []
    for p in root.findall("v:Page", NS):
        rel = p.find("v:Rel", NS)
        tgt = target.get(rel.get(_R_ID)) if rel is not None else None
        if tgt:
            out.append((p.get("Name") or p.get("NameU") or "", "visio/pages/" + tgt))
    return out


def _lane_bounds(shape, master: str) -> tuple[str, float, float, bool] | None:
    """Kulvar grubu -> (ad, min, max, dikey_mi). Dikey kulvar x aralığını, yatay kulvar y aralığını kaplar."""
    if not _LANE_MASTER.search(master) or re.search(r"list", master, re.I):
        return None
    name = ""
    for sub in shape.iter(_SHAPE):
        if sub is not shape and _shape_text(sub):
            name = _shape_text(sub)
            break
    name = name or _shape_text(shape)
    vertical = "vertical" in master.lower() or "dikey" in master.lower()
    if vertical:
        pin, size = _num(shape, "PinX"), _num(shape, "Width")
    else:
        pin, size = _num(shape, "PinY"), _num(shape, "Height")
    if pin is None or size is None or not name:
        return None
    return name, pin - size / 2, pin + size / 2, vertical


def _parse_page(name: str, root, masters: dict[str, str]) -> VisioPage:
    page = VisioPage(name=name)
    top = root.find("v:Shapes", NS)
    if top is None:
        page.warnings.append("Sayfada şekil yok.")
        return page
    parent_top: dict[str, str] = {}
    for s in top.findall("v:Shape", NS):
        for sub in s.iter(_SHAPE):
            parent_top[sub.get("ID")] = s.get("ID")

    connects: dict[str, dict[str, str]] = {}  # bağlayıcı id -> {'begin': hedef, 'end': hedef}
    for c in root.findall("v:Connects/v:Connect", NS):
        end = "begin" if (c.get("FromCell") or "").startswith("Begin") else "end"
        connects.setdefault(c.get("FromSheet"), {})[end] = c.get("ToSheet")

    lanes: list[tuple[str, float, float, bool]] = []
    candidates: list[tuple[ET.Element, str]] = []
    connector_els: list[ET.Element] = []
    for s in top.findall("v:Shape", NS):
        master = masters.get(s.get("Master") or "", "")
        lane = _lane_bounds(s, master)
        if lane:
            lanes.append(lane)
            continue
        if s.get("ID") in connects or _CONNECTOR_MASTER.search(master):
            connector_els.append(s)
            continue
        if _LAYOUT_MASTER.search(master) or s.get("Type") == "Foreign":
            if re.search(r"container|kapsay", master, re.I):  # kapsayıcı içindeki metin = sayfa başlığı
                for sub in s.iter(_SHAPE):
                    if _shape_text(sub) and not page.title:
                        page.title = _shape_text(sub)
            continue
        candidates.append((s, master))
    page.lanes = [n for n, *_ in lanes]

    def lane_of(x: float, y: float) -> str | None:
        for n, lo, hi, vertical in lanes:
            if lo <= (x if vertical else y) <= hi:
                return n
        return None

    for s, master in candidates:
        text = _shape_text(s) or _clean(" ".join(_shape_text(sub) for sub in s.iter(_SHAPE) if sub is not s))
        x, y = _num(s, "PinX") or 0.0, _num(s, "PinY") or 0.0
        w, h = _num(s, "Width") or 0.0, _num(s, "Height") or 0.0
        if not master and not text:
            continue  # boş dekor
        kind = _kind_for(master) if master else NOT
        if not text:
            page.warnings.append(f"Metinsiz şekil atlandı (id {s.get('ID')}, {master or 'şablonsuz'}).")
            continue
        page.shapes.append(VisioShape(s.get("ID"), kind, text, lane_of(x, y), x, y, w, h))
    step_ids = {s.id for s in page.shapes}

    def resolve(target: str | None) -> str | None:
        if target is None:
            return None
        tid = target if target in step_ids else parent_top.get(target)
        return tid if tid in step_ids else None

    def nearest(px: float | None, py: float | None) -> str | None:
        if px is None or py is None:
            return None
        best, best_d = None, 0.35  # inç
        for sh in page.shapes:
            dx = max(abs(px - sh.x) - sh.w / 2, 0.0)
            dy = max(abs(py - sh.y) - sh.h / 2, 0.0)
            d = (dx * dx + dy * dy) ** 0.5
            if d < best_d:
                best, best_d = sh.id, d
        return best

    for c in connector_els:
        cid = c.get("ID")
        label = _shape_text(c)
        ends = {k: resolve(connects.get(cid, {}).get(k)) for k in ("begin", "end")}
        for k, (cx, cy) in (("begin", ("BeginX", "BeginY")), ("end", ("EndX", "EndY"))):
            if ends[k] is None:
                ends[k] = nearest(_num(c, cx), _num(c, cy))
                if ends[k] is not None:
                    page.warnings.append(f"Bağlayıcı {cid}: {k} ucu şekle yapışık değil; geometriden eşlendi.")
        src, dst = ends["begin"], ends["end"]
        b_arrow, e_arrow = _num(c, "BeginArrow") or 0, _num(c, "EndArrow") or 0
        if b_arrow and not e_arrow:  # ok başlangıç ucunda: yön ters
            src, dst = dst, src
        if src is None and dst is None and not label:
            continue
        if src is not None and src == dst and not connects.get(cid):
            page.warnings.append(f"Bağlayıcı {cid}: iki ucu da aynı şekle eşlendi (geometri); atlandı.")
            continue
        if src is None or dst is None:
            page.warnings.append(f"Bağlayıcı {cid} ({label or 'etiketsiz'}): bir ucu bilinmiyor.")
        page.edges.append(VisioEdge(src, dst, label))
    # Şablonu "Process" olsa da Evet/Hayır dallı çıkışı olan şekil karardır.
    for sh in page.shapes:
        if sh.kind == ISLEM and len({_fold_label(e.label) for e in page.out_edges(sh.id)} & _YES_NO) >= 1                 and len(page.out_edges(sh.id)) >= 2:
            sh.kind = KARAR
    return page


def parse_vsdx(path: Path | str) -> VisioDoc:
    path = Path(path)
    doc = VisioDoc(path=path)
    if path.suffix.lower() != ".vsdx":
        doc.warnings.append(f"Yalnızca .vsdx desteklenir: {path.suffix}")
        return doc
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        doc.warnings.append("Geçerli bir vsdx (zip) dosyası değil.")
        return doc
    with z:
        masters = _master_names(z)
        for name, fn in _page_files(z):
            if fn not in z.namelist():
                doc.warnings.append(f"Sayfa dosyası yok: {fn}")
                continue
            doc.pages.append(_parse_page(name, ET.fromstring(z.read(fn)), masters))
    if not doc.pages:
        doc.warnings.append("Sayfa bulunamadı.")
    return doc
