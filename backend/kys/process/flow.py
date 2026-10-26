"""Süreç adımlarından deterministik Mermaid akış şeması (LLM yok).

Kurallar:
- Karar adımı (decision dolu veya birden çok çıkış) rombus; başlangıç ve bitiş adımları oval.
- next_steps sırası: iki çıkışlı karar adımında ilk çıkış "Evet", ikinci "Hayır" kabul edilir
  (decision alanı "Evet/Hayır" gibi açık etiket içeriyorsa o kullanılır).
- Sorumlu rol düğüm metninin altına eklenir.
"""

import json
import re
import sqlite3

_SPLIT = re.compile(r"\s*[/|;]\s*")
_ENT = {"#": "#35;", '"': "#quot;", "<": "#lt;", ">": "#gt;", "&": "#amp;", "`": "#96;", "{": "#123;", "}": "#125;",
        "[": "#91;", "]": "#93;", "(": "#40;", ")": "#41;", "|": "#124;", ";": "#59;", "\\": "#92;"}


def esc(text: str | None, limit: int = 90) -> str:
    """Mermaid tırnaklı etiketini bozan karakterleri varlık koduna çevirir."""
    t = " ".join(str(text or "").split())
    if len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    return "".join(_ENT.get(ch, ch) for ch in t)  # tek geçiş: üretilen varlık kodları yeniden kaçırılmaz


def parse_next(value) -> list[int]:
    if isinstance(value, str):
        try:
            value = json.loads(value or "[]")
        except ValueError:
            return []
    return [int(x) for x in (value or []) if isinstance(x, (int, str)) and str(x).lstrip("-").isdigit()]


def _branch_labels(step: dict, n: int) -> list[str | None]:
    """Çıkış başına ok etiketi."""
    if n < 2:
        return [None] * n
    parts = [p for p in _SPLIT.split(step.get("decision") or "") if p]
    if len(parts) == n and all(len(p) <= 20 for p in parts):  # "Evet/Hayır" biçimi
        return parts
    if n == 2:
        return ["Evet", "Hayır"]
    return [None] * n


def to_mermaid(steps: list[dict]) -> str:
    """steps: seq, name, role (kısa), decision, next_steps ([seq] veya JSON) alanlı sözlükler."""
    seqs = {s["seq"] for s in steps}
    nexts = {s["seq"]: [x for x in parse_next(s.get("next_steps")) if x in seqs] for s in steps}
    incoming = {x for v in nexts.values() for x in v}
    lines = ["flowchart TD"]
    decisions: list[str] = []
    for s in steps:
        sq = s["seq"]
        text = esc(s["name"])
        if s.get("role"):
            text += f"<br/>#40;{esc(s['role'], 40)}#41;"  # (rol)
        is_decision = bool(s.get("decision")) or len(nexts[sq]) > 1
        if is_decision:
            node = f's{sq}{{"{text}"}}'
            decisions.append(f"s{sq}")
        elif not nexts[sq] or sq not in incoming:
            node = f's{sq}(["{text}"])'
        else:
            node = f's{sq}["{text}"]'
        lines.append(f"    {node}")
    for s in steps:
        out = nexts[s["seq"]]
        labels = _branch_labels(s, len(out))
        for target, label in zip(out, labels):
            arrow = f'-->|"{esc(label, 20)}"|' if label else "-->"
            lines.append(f"    s{s['seq']} {arrow} s{target}")
    if decisions:
        lines.append("    classDef karar fill:#fff4e0,stroke:#9a5b00,color:#1d2330")
        lines.append(f"    class {','.join(decisions)} karar")
    return "\n".join(lines) + "\n"


def list_processes(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT p.code, p.name, d.code AS document_code, d.revision, d.status, d.file_path,
                  (SELECT COUNT(*) FROM process_steps s WHERE s.process_id = p.id) AS step_count
           FROM processes p LEFT JOIN documents d ON d.id = p.document_id
           WHERE p.source = 'DOKUMAN' ORDER BY p.code""").fetchall()
    return [dict(r) for r in rows]


def get_process(conn: sqlite3.Connection, code: str) -> dict | None:
    """Süreç + adımlar + mermaid. Kod büyük/küçük harf duyarsız eşleşir."""
    p = conn.execute(
        """SELECT p.id, p.code, p.name, p.purpose, d.code AS document_code, d.revision, d.status, d.file_path,
                  d.file_sha256 FROM processes p LEFT JOIN documents d ON d.id = p.document_id
           WHERE p.code = ? COLLATE NOCASE""", (code,)).fetchone()
    if not p:
        return None
    steps = []
    for r in conn.execute(
        """SELECT s.seq, s.name, s.description, s.decision, s.next_steps, s.inputs, s.outputs, s.system, s.quote,
                  re.canonical_name AS responsible, ap.canonical_name AS approver
           FROM process_steps s LEFT JOIN entities re ON re.id = s.responsible_entity_id
           LEFT JOIN entities ap ON ap.id = s.approver_entity_id
           WHERE s.process_id = ? ORDER BY s.seq""", (p["id"],)):
        d = dict(r)
        d["next_steps"] = parse_next(d["next_steps"])
        for k in ("inputs", "outputs"):
            try:
                d[k] = json.loads(d[k]) if d[k] else []
            except ValueError:
                d[k] = []
        d["role"] = d["responsible"]
        steps.append(d)
    out = {k: p[k] for k in ("code", "name", "purpose", "document_code", "revision", "status")}
    out["steps"] = steps
    out["mermaid"] = to_mermaid(steps)
    out["_file_path"], out["_file_sha256"] = p["file_path"], p["file_sha256"]
    return out
