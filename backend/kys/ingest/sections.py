"""Gövde metnini madde numarasına göre bölümlere ayırır."""

import re
from dataclasses import dataclass

MAX_SECTION_CHARS = 4000

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_NUM_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,4})(\.?)\s+(\S.*)$")
_LEADING_CLAUSE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,4})\.?\s+(.*)$")


@dataclass
class Section:
    ordinal: int
    clause_no: str | None
    heading: str | None
    heading_path: str | None
    text: str


def _is_upper(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def detect_heading(line: str) -> tuple[str | None, str] | None:
    """Satır başlıksa (madde_no, başlık) döner, değilse None.

    Numaralı liste maddesini ("1. Talep formu doldurulur.") başlıktan ayırmak için:
    başlık kısa olur, noktalama ile bitmez; tek seviyeli numarada nokta veya büyük harf gerekir.
    """
    line = line.strip()
    m = _MD_HEADING.match(line)
    if m:
        text = m.group(2).strip()
        lc = _LEADING_CLAUSE.match(text)
        return (lc.group(1), lc.group(2).strip() or text) if lc else (None, text)
    if len(line) > 120 or line.startswith("|"):
        return None
    m = _NUM_HEADING.match(line)
    if not m:
        return None
    clause, dot, title = m.groups()
    if title.rstrip().endswith((".", ":", ";", ",")) or not any(c.isalpha() for c in title):
        return None
    if "." not in clause and not dot and not _is_upper(title):
        return None
    return clause, title.strip()


def split_sections(body: str) -> list[Section]:
    raw: list[tuple[str | None, str | None, list[str]]] = [(None, None, [])]
    for line in body.splitlines():
        h = detect_heading(line)
        if h:
            raw.append((h[0], h[1], []))
        else:
            raw[-1][2].append(line)

    sections: list[Section] = []
    stack: list[tuple[int, str]] = []  # (derinlik, "4.2 Başlık")
    for clause, heading, lines in raw:
        text = "\n".join(lines).strip()
        if heading is None and not text:
            continue
        path = None
        if heading is not None:
            depth = clause.count(".") + 1 if clause else (stack[-1][0] + 1 if stack else 1)
            stack = [s for s in stack if s[0] < depth]
            stack.append((depth, f"{clause} {heading}" if clause else heading))
            path = " > ".join(s[1] for s in stack)
        for i, chunk in enumerate(_chunks(text)):
            sections.append(Section(
                ordinal=len(sections),
                clause_no=clause,
                heading=heading if i == 0 or heading is None else f"{heading} (devam)",
                heading_path=path,
                text=chunk,
            ))
    return sections


def _chunks(text: str) -> list[str]:
    if len(text) <= MAX_SECTION_CHARS:
        return [text]
    out, cur = [], ""
    for para in text.split("\n"):
        if cur and len(cur) + len(para) + 1 > MAX_SECTION_CHARS:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out
