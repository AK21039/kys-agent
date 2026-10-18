"""Bulguları `analysis_runs` + `findings`'e kalıcı yazar. Yalnızca `kys analiz --kaydet` çağırır.

Fingerprint ile upsert: aynı anlamdaki bulgu tekrar çalıştırmada çoğalmaz. Var olan bir bulgunun kullanıcı
tarafından verilmiş `status`/`status_note`'u EZİLMEZ — yalnızca içerik (açıklama, kanıt, şiddet ...) ve
`run_id` güncellenir.
"""

import json
import sqlite3

from .model import CheckOutcome


def save_findings(conn: sqlite3.Connection, outcomes: dict[str, CheckOutcome], kind: str = "tutarlilik") -> dict:
    cur = conn.execute("INSERT INTO analysis_runs(kind, params) VALUES (?, ?)",
                        (kind, json.dumps({"kontroller": list(outcomes)}, ensure_ascii=False)))
    run_id = cur.lastrowid
    yeni = guncellenen = 0
    for outcome in outcomes.values():
        for f in outcome.findings:
            row = f.as_row(run_id)
            existing = conn.execute("SELECT id FROM findings WHERE fingerprint = ?", (row["fingerprint"],)).fetchone()
            if existing:
                conn.execute(
                    """UPDATE findings SET run_id = ?, finding_type = ?, severity = ?, title = ?, explanation = ?,
                              recommendation = ?, evidence = ?, unverified_basis = ?, updated_at = datetime('now')
                       WHERE fingerprint = ?""",
                    (row["run_id"], row["finding_type"], row["severity"], row["title"], row["explanation"],
                     row["recommendation"], row["evidence"], int(row["unverified_basis"]), row["fingerprint"]))
                guncellenen += 1
            else:
                conn.execute(
                    """INSERT INTO findings(run_id, finding_type, severity, title, explanation, recommendation,
                                            evidence, unverified_basis, fingerprint)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row["run_id"], row["finding_type"], row["severity"], row["title"], row["explanation"],
                     row["recommendation"], row["evidence"], int(row["unverified_basis"]), row["fingerprint"]))
                yeni += 1
    conn.execute("UPDATE analysis_runs SET status = 'TAMAMLANDI', finished_at = datetime('now') WHERE id = ?",
                 (run_id,))
    conn.commit()
    return {"run_id": run_id, "yeni": yeni, "guncellenen": guncellenen}
