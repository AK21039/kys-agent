"""Doğal dil sorusundan ilgili bölümleri bulur (FTS5 trigram VEYA + bm25; geniş aday havuzu yakınlık ve başlık örtüşmesiyle yeniden sıralanır)."""

import sqlite3

from ..textnorm import fold

# Yeniden sıralamada eklenen bonuslar (bm25'te düşük = iyi, bu yüzden ceza değil BONUS olarak
# ÇIKARILIR). Başlık/madde başlığı eşleşmesi daha güçlü bir konu sinyali olduğu için gövde
# yakınlığından ağırlıklı.
_PROX_WINDOW = 150          # iki terimin "birlikte geçiyor" sayılacağı karakter mesafesi
_BONUS_PER_PROX_PAIR = 4.0
_BONUS_PER_HEAD_TERM = 6.0
_POOL_MIN = 120

STOPWORDS = {
    "ve", "veya", "ile", "bir", "bu", "su", "icin", "mi", "mu", "ne", "nedir", "nasil", "hangi", "kim",
    "kimdir", "olan", "olarak", "gibi", "da", "de", "ki", "var", "yok", "midir", "ise", "daha", "en", "her",
    "tum", "hangisi", "neler", "nelerdir", "kac", "gore", "kadar", "sonra", "once", "uzere", "yapilir",
    "dokuman", "dokumanda", "dokumanlarda", "var mi", "olur", "eder", "edilir",
}


def _terms(question: str) -> list[str]:
    """Türkçe ekleri kabaca budar: uzun kelimelerin ilk 6 harfi (trigram alt dizge eşleşmesi için)."""
    out = []
    for w in fold(question).replace('"', " ").split():
        w = w.strip(".,;:!?()'")
        if len(w) < 3 or w in STOPWORDS:
            continue
        w = w[:6] if len(w) > 7 else w
        if w not in out:
            out.append(w)
    return out


_SECTION_SQL = """SELECT s.id AS section_id, s.clause_no, s.heading, s.heading_path, s.text,
                         d.id AS document_id, d.code, d.revision, d.title, d.doc_type, 0.0 AS score
                  FROM sections s JOIN documents d ON d.id = s.document_id"""


def named_documents(conn: sqlite3.Connection, question: str) -> list[int]:
    """Soruda kodu veya başlığı geçen yürürlükteki dokümanlar (ör. '"Yatırım ve Proje Süreci"ne aykırı...')."""
    from ..ingest.metadata import code_key, find_codes
    q = fold(question)
    keys = {code_key(c) for c in find_codes(question.upper())}
    ids = []
    for d in conn.execute("SELECT id, code_key, title FROM documents WHERE status = 'YURURLUKTE'"):
        title = fold(d["title"] or "")
        if d["code_key"] in keys or (len(title) >= 8 and title in q):
            ids.append(d["id"])
    return ids


def retrieve_for_question(conn: sqlite3.Connection, question: str, limit: int = 8,
                          max_named_sections: int = 12) -> list[sqlite3.Row]:
    """Adı geçen dokümanların bölümleri önce (tamamı), ardından arama sonuçları."""
    named = named_documents(conn, question)[:3]
    rows: list[sqlite3.Row] = []
    if named:
        marks = ",".join("?" * len(named))
        rows = conn.execute(f"{_SECTION_SQL} WHERE d.id IN ({marks}) ORDER BY d.id, s.ordinal",
                            named).fetchall()[:max_named_sections]
    seen = {r["section_id"] for r in rows}
    rows += [r for r in retrieve(conn, question, limit=limit + len(rows)) if r["section_id"] not in seen][:limit]
    return rows


def _run_fts(conn: sqlite3.Connection, fts: str, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT s.id AS section_id, s.clause_no, s.heading, s.heading_path, s.text,
                  d.id AS document_id, d.code, d.revision, d.title, d.doc_type,
                  bm25(sections_fts) AS score
           FROM sections_fts
           JOIN sections s ON s.id = sections_fts.rowid
           JOIN documents d ON d.id = s.document_id
           WHERE sections_fts MATCH ? AND d.status = 'YURURLUKTE' AND length(s.text) > 20
           ORDER BY score LIMIT ?""",
        (fts, limit),
    ).fetchall()


def _term_coverage(terms: list[str], *texts: str | None) -> int:
    """Katlanmış metinlerin herhangi birinde alt dizge olarak geçen FARKLI terim sayısı."""
    blob = fold(" ".join(t for t in texts if t))
    return sum(1 for t in terms if t in blob)


def _positions(term: str, blob: str) -> list[int]:
    pos, start = [], 0
    while True:
        i = blob.find(term, start)
        if i < 0:
            return pos
        pos.append(i)
        start = i + 1


def _proximity_hits(terms: list[str], text: str, window: int = _PROX_WINDOW) -> int:
    """Soru terimlerinden FARKLI en az ikisinin metinde `window` karakter içinde BİRLİKTE geçtiği çift sayısı.

    Terimlerin metnin herhangi bir yerinde (birbirinden uzak) geçmesi bonus almaz — yalnızca
    YAKIN geçmesi bağlamsal ilgiyi gösterir. Bu, uzun/genel bir bölümün sadece büyük olduğu için
    her terimi (nerede olursa olsun) içermesinin yanlış yere bonus almasını önler.
    """
    blob = fold(text)
    pos = {t: p for t in terms if (p := _positions(t, blob))}
    keys = list(pos)
    return sum(1 for i, a in enumerate(keys) for b in keys[i + 1:]
               if any(abs(x - y) <= window for x in pos[a] for y in pos[b]))


def retrieve(conn: sqlite3.Connection, question: str, limit: int = 8) -> list[sqlite3.Row]:
    """FTS5 (trigram, tek terimli VEYA) ile arar; bağlamla eşleşen bölümleri bm25'in önüne taşır.

    Tek terimli VEYA çok anlamlı bir kelimeyi ("kaynak" gibi) soru bağlamından (ör. "izin")
    koparır: o kelimeyle eşleşen HER bölüm — ilgisiz anlamı taşıyan ya da trigram alt dizge
    eşleşmesiyle gelen "kaynaklı/kaynaklanan" gibi biçimler dahil — bm25'e göre eşit aday sayılır.
    Düzeltme: aday havuzu genişletilip (bm25 sırasında daha gerilerde kalan ama bağlamla GERÇEKTEN
    ilişkili bölümler de rekabete girsin diye), iki genel sinyalle yeniden ağırlıklandırılır:
    1) Yakınlık: soru terimlerinden en az ikisinin METİNDE YAKIN (aynı cümle/paragraf mesafesinde)
       birlikte geçmesi — tek terimin uzak bir yerde geçmesinden daha güçlü bir bağlam kanıtıdır.
    2) Başlık örtüşmesi: soru terimlerinin madde başlığı / doküman başlığında geçmesi — konunun
       kendisiyle eşleşme, gövdedeki rastgele geçişten daha güçlü bir sinyaldir.
    Her ikisi de GENEL mekanizmalardır: belirli bir terime özel kural yoktur, sorudaki terimlerin
    TÜMÜNE aynı şekilde uygulanır.
    """
    terms = _terms(question)
    if not terms:
        return []
    fts = " OR ".join(f'"{t}"' for t in terms)
    pool = max(limit * 15, _POOL_MIN)
    rows = _run_fts(conn, fts, pool)

    def _key(r: sqlite3.Row) -> tuple[float, float]:
        prox = _proximity_hits(terms, r["text"]) if len(terms) >= 2 else 0
        head = _term_coverage(terms, r["heading"], r["heading_path"], r["title"])
        return (r["score"] - _BONUS_PER_PROX_PAIR * prox - _BONUS_PER_HEAD_TERM * head, r["score"])

    return sorted(rows, key=_key)[:limit]
