"""Yükleme hattı: dosya → ayrıştır → kimlik tespiti → (sınıflandır) → kaydet → bölümle → atıfları çöz."""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .. import overrides
from ..llm import LLMError
from ..ontology import DocStatus, DocType, NodeKind, RelType, ReviewStatus
from ..textnorm import fold
from . import metadata
from .parsers import LEGACY, SUPPORTED, UnsupportedFormat, parse
from .sections import split_sections


@dataclass
class IngestResult:
    path: Path
    status: str                      # 'eklendi' | 'atlandi' | 'hata'
    document_id: int | None = None
    code: str | None = None
    revision: str | None = None
    doc_type: str | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)


def iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    exts = SUPPORTED | LEGACY
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() in exts and not p.name.startswith("~$"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rev_num(rev: str) -> tuple[int, str]:
    m = re.search(r"\d+", rev or "")
    return (int(m.group()) if m else -1, rev or "")


def merge_classification(meta: metadata.DocMeta, c, warnings: list[str]) -> None:
    """Model sonucunu kural tabanlı tespitle birleştirir. Üstbilgiden okunan kod/revizyon korunur."""
    if meta.code and c.code and metadata.code_key(meta.code) != metadata.code_key(c.code):
        warnings.append(f"Kod uyuşmazlığı: kural '{meta.code}', model '{c.code}'. Kural tabanlı değer korundu.")
    meta.code = meta.code or c.code
    meta.revision = meta.revision or c.revision
    meta.title = c.title or meta.title
    meta.doc_type = c.doc_type
    meta.revision_date = meta.revision_date or c.revision_date
    meta.effective_date = meta.effective_date or c.effective_date


def apply_override(meta: metadata.DocMeta, sha: str) -> bool:
    """Kullanıcı düzeltmesi varsa uygular (her şeyin önündedir)."""
    ov = overrides.get(sha)
    if not ov:
        return False
    for f in overrides.FIELDS:
        if ov.get(f):
            setattr(meta, f, DocType(ov[f]) if f == "doc_type" else ov[f])
    return True


def ingest_file(conn: sqlite3.Connection, path: Path, use_llm: bool = True, ocr: bool = True) -> IngestResult:
    try:
        return _ingest_file(conn, path, use_llm, ocr)
    except Exception:
        conn.rollback()  # yarım kalan doküman/bölüm kaydı bırakma
        raise


def _ingest_file(conn: sqlite3.Connection, path: Path, use_llm: bool, ocr: bool = True) -> IngestResult:
    sha = _sha256(path)
    row = conn.execute("SELECT id, code, revision FROM documents WHERE file_sha256 = ?", (sha,)).fetchone()
    if row:
        return IngestResult(path, "atlandi", row["id"], row["code"], row["revision"], message="aynı dosya zaten yüklü")

    try:
        parsed = parse(path, ocr=ocr)
    except UnsupportedFormat as e:
        return IngestResult(path, "hata", message=str(e))
    except Exception as e:  # bozuk / şifreli dosya
        return IngestResult(path, "hata", message=f"ayrıştırılamadı: {type(e).__name__}: {e}")

    warnings = list(parsed.warnings)
    meta = metadata.detect(path, parsed.header_text, parsed.body_text)
    meta_source, confidence = "regex", meta.confidence
    summary = owner_unit = None

    if use_llm:
        from .classify import classify
        try:
            c = classify(parsed, meta, conn=conn)
            merge_classification(meta, c, warnings)
            summary, owner_unit = c.summary, c.owner_unit
            meta_source, confidence = "llm", c.confidence
        except LLMError as e:
            warnings.append(f"Sınıflandırma yapılamadı, kural tabanlı değerler kullanıldı: {e}")

    if apply_override(meta, sha):
        meta_source = "kullanici"

    if not meta.code:
        meta.code = f"KODSUZ-{sha[:8]}"
        warnings.append("Doküman kodu bulunamadı; geçici kod atandı. Doküman Merkezi'nden düzeltin.")
    revision = meta.revision or "00"
    key = metadata.code_key(meta.code)

    clash = conn.execute("SELECT id, title FROM documents WHERE code_key = ? AND revision = ?",
                         (key, revision)).fetchone()
    if clash and fold(clash["title"]) == fold(meta.title or path.stem):
        return IngestResult(path, "hata", code=meta.code, revision=revision,
                            message=f"{meta.code} Rev.{revision} farklı içerikle zaten kayıtlı (doküman #{clash['id']}). "
                                    "Revizyon numarasını kontrol edin.", warnings=warnings)
    if clash:
        # Farklı dokümanlar aynı kodu taşıyor: doküman kontrol uyumsuzluğu. Reddetme, ayrı kodla kaydet ve işaretle.
        warnings.append(f"KOD ÇAKIŞMASI: {meta.code} Rev.{revision} '{clash['title']}' dokümanında da kullanılıyor. "
                        "Doküman kontrolünde düzeltilmeli.")
        n = conn.execute("SELECT COUNT(*) FROM documents WHERE code_key LIKE ?", (key + "#%",)).fetchone()[0]
        meta.code = f"{meta.code}#{n + 2}"
        key = metadata.code_key(meta.code)

    # Revizyon yönetimi: aynı koddaki yürürlükteki dokümanla karşılaştır.
    status, supersedes = DocStatus.YURURLUKTE, None
    current = conn.execute("SELECT id, revision FROM documents WHERE code_key = ? AND status = ?",
                           (key, DocStatus.YURURLUKTE)).fetchall()
    for old in current:
        if _rev_num(revision) > _rev_num(old["revision"]):
            conn.execute("UPDATE documents SET status = ? WHERE id = ?", (DocStatus.IPTAL, old["id"]))
            supersedes = old["id"]
        else:
            status = DocStatus.IPTAL
            warnings.append(f"Daha yeni revizyon (Rev.{old['revision']}) yürürlükte; bu dosya geçmiş revizyon olarak kaydedildi.")

    cur = conn.execute(
        """INSERT INTO documents(code, code_key, revision, title, doc_type, status, revision_date, effective_date,
                                 owner_unit, summary, header_text, body_text, file_path, file_sha256,
                                 parse_warnings, meta_source, meta_confidence, supersedes_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (meta.code, key, revision, meta.title or path.stem, meta.doc_type or DocType.DIGER, status,
         meta.revision_date, meta.effective_date, owner_unit, summary, parsed.header_text, parsed.body_text,
         str(path), sha, json.dumps(warnings, ensure_ascii=False), meta_source, confidence, supersedes),
    )
    doc_id = cur.lastrowid
    if supersedes:
        _add_edge(conn, NodeKind.DOKUMAN, doc_id, RelType.YERINE_GECER, NodeKind.DOKUMAN, supersedes, doc_id)

    _insert_sections(conn, doc_id, key, parsed.body_text)
    conn.commit()
    return IngestResult(path, "eklendi", doc_id, meta.code, revision, str(meta.doc_type or DocType.DIGER),
                        warnings=warnings)


def _insert_sections(conn: sqlite3.Connection, doc_id: int, key: str, body_text: str) -> None:
    for s in split_sections(body_text):
        sid = conn.execute(
            """INSERT INTO sections(document_id, ordinal, clause_no, heading, heading_path, text, search_text)
               VALUES (?,?,?,?,?,?,?)""",
            (doc_id, s.ordinal, s.clause_no, s.heading, s.heading_path, s.text,
             fold(f"{s.heading or ''} {s.text}")),
        ).lastrowid
        for ref in metadata.find_codes(s.text):
            # Kendi kodu veya aralıklı yazılmış kendi kodunun parçası ("PR46-P RJ-1" → "RJ-1") atıf değildir.
            if not key.split("#")[0].endswith(metadata.code_key(ref)):
                conn.execute("INSERT OR IGNORE INTO doc_references(document_id, section_id, ref_code) VALUES (?,?,?)",
                             (doc_id, sid, ref))


def _add_edge(conn, src_kind, src_id, rel, dst_kind, dst_id, document_id, section_id=None) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO edges(src_kind, src_id, rel_type, dst_kind, dst_id, document_id, section_id,
                                      review_status, confidence)
           VALUES (?,?,?,?,?,?,?,?,1.0)""",
        (src_kind, src_id, rel, dst_kind, dst_id, document_id, section_id, ReviewStatus.ONAYLANDI),
    )


def resolve_references(conn: sqlite3.Connection) -> tuple[int, int]:
    """Çözülmemiş kod atıflarını yürürlükteki (yoksa en son) revizyona bağlar. (çözülen, kalan) döner.

    Deterministik eşleşme olduğu için oluşan REFERANS_VERIR kenarları doğrudan ONAYLANDI girer.
    """
    resolved = 0
    for ref in conn.execute("SELECT id, document_id, section_id, ref_code FROM doc_references "
                            "WHERE resolved_doc_id IS NULL").fetchall():
        target = conn.execute(
            """SELECT id FROM documents WHERE code_key = ?
               ORDER BY (status = 'YURURLUKTE') DESC, created_at DESC LIMIT 1""",
            (metadata.code_key(ref["ref_code"]),),
        ).fetchone()
        if target:
            conn.execute("UPDATE doc_references SET resolved_doc_id = ? WHERE id = ?", (target["id"], ref["id"]))
            _add_edge(conn, NodeKind.DOKUMAN, ref["document_id"], RelType.REFERANS_VERIR,
                      NodeKind.DOKUMAN, target["id"], ref["document_id"], ref["section_id"])
            resolved += 1
    conn.commit()
    remaining = conn.execute("SELECT COUNT(*) FROM doc_references WHERE resolved_doc_id IS NULL").fetchone()[0]
    return resolved, remaining


def ingest_paths(conn: sqlite3.Connection, root: Path, use_llm: bool = True, progress=None, ocr: bool = True) -> list[IngestResult]:
    results = []
    for path in iter_files(root):
        r = ingest_file(conn, path, use_llm=use_llm, ocr=ocr)
        results.append(r)
        if progress:
            progress(r)
    resolve_references(conn)
    return results


@dataclass
class ClassifyResult:
    document_id: int
    old_code: str
    code: str
    title: str
    doc_type: str
    seconds: float
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


def classify_existing(conn: sqlite3.Connection, limit: int | None = None, redo: bool = False,
                      progress=None) -> list[ClassifyResult]:
    """Kayıtlı dokümanları hızlı modelle sınıflandırır (özet, sahip birim, başlık, tip).

    Kesintiye dayanıklıdır: her doküman ayrı commit edilir; tekrar çalıştırınca özeti olmayanlardan devam eder.
    Kullanıcı düzeltmeleri (overrides) her zaman en son uygulanır.
    """
    import time

    from .classify import classify
    from .metadata import DocMeta
    from .parsers import ParsedDoc

    sql = "SELECT * FROM documents" + ("" if redo else " WHERE summary IS NULL") + " ORDER BY id"
    rows = conn.execute(sql).fetchall()[:limit]
    results = []
    for row in rows:
        t0 = time.time()
        code = None if row["code"].startswith("KODSUZ-") or "#" in row["code"] else row["code"]
        meta = DocMeta(code=code, revision=row["revision"], title=row["title"],
                       doc_type=None if row["doc_type"] == DocType.DIGER else DocType(row["doc_type"]),
                       revision_date=row["revision_date"], effective_date=row["effective_date"])
        parsed = ParsedDoc(path=Path(row["file_path"]), header_text=row["header_text"] or "",
                           body_text=row["body_text"])
        warnings: list[str] = []
        try:
            c = classify(parsed, meta, conn=conn)
        except LLMError as e:
            r = ClassifyResult(row["id"], row["code"], row["code"], row["title"], row["doc_type"],
                               time.time() - t0, error=str(e))
            results.append(r)
            if progress:
                progress(r)
            continue

        merge_classification(meta, c, warnings)
        source = "kullanici" if apply_override(meta, row["file_sha256"]) else "llm"
        new_code = meta.code or row["code"]
        if metadata.code_key(new_code) != row["code_key"] and conn.execute(
                "SELECT 1 FROM documents WHERE code_key = ? AND revision = ? AND id != ?",
                (metadata.code_key(new_code), meta.revision or row["revision"], row["id"])).fetchone():
            warnings.append(f"Model kodu '{new_code}' başka dokümanda kayıtlı; eski kod korundu.")
            new_code = row["code"]
        old_warnings = json.loads(row["parse_warnings"] or "[]")
        conn.execute(
            """UPDATE documents SET code = ?, code_key = ?, revision = ?, title = ?, doc_type = ?,
                      revision_date = ?, effective_date = ?, owner_unit = ?, summary = ?,
                      meta_source = ?, meta_confidence = ?, parse_warnings = ?
               WHERE id = ?""",
            (new_code, metadata.code_key(new_code), meta.revision or row["revision"], meta.title or row["title"],
             meta.doc_type or DocType.DIGER, meta.revision_date, meta.effective_date, c.owner_unit, c.summary,
             source, c.confidence, json.dumps(old_warnings + warnings, ensure_ascii=False), row["id"]),
        )
        conn.commit()
        r = ClassifyResult(row["id"], row["code"], new_code, meta.title or row["title"],
                           str(meta.doc_type or DocType.DIGER), time.time() - t0, warnings=warnings)
        results.append(r)
        if progress:
            progress(r)
    resolve_references(conn)
    return results


@dataclass
class ReingestReport:
    document_id: int
    code: str
    revision: str
    old_chars: int
    new_chars: int
    applied: bool
    warnings: list[str]
    rules: int = 0                  # bu dokümana bağlı kurallar (silinmez)
    extraction_edges: int = 0       # atıf dışı kenarlar (silinmez)
    relinked: int = 0               # bölüm bağı korunan kayıt
    unlinked: int = 0               # bölüm bağı kopan kayıt (alıntı hâlâ geçerli, madde bağı boş)
    error: str | None = None


def reingest_document(conn: sqlite3.Connection, code: str, apply: bool = False, ocr: bool = True) -> "ReingestReport | None":
    """Kayıtlı dokümanın dosyasını yeniden ayrıştırır (OCR dahil) ve AYNI kayıt üzerinde günceller.

    Kayıt silinmez: kimlik (id), kod/revizyon, durum, sınıflandırma ve kullanıcı düzeltmeleri korunur; kurallar ve
    kenarlar dokümana bağlı kalır. Bölümler yeniden üretildiğinden kural/kenar bölüm bağları madde numarasıyla
    (yoksa başlık yoluyla) yeniden kurulur. Varsayılan (apply=False) hiçbir şey yazmaz, yalnızca etkiyi raporlar.
    """
    row = conn.execute("SELECT * FROM documents WHERE code_key = ? ORDER BY created_at DESC LIMIT 1",
                       (metadata.code_key(code),)).fetchone()
    if not row:
        return None
    path = Path(row["file_path"])
    rep = ReingestReport(row["id"], row["code"], row["revision"], len(row["body_text"]), 0, False, [])
    if not path.exists():
        rep.error = f"Dosya bulunamadı: {path}"
        return rep
    try:
        parsed = parse(path, ocr=ocr)
    except Exception as e:
        rep.error = f"ayrıştırılamadı: {type(e).__name__}: {e}"
        return rep
    rep.new_chars = len(parsed.body_text)
    rep.warnings = list(parsed.warnings)
    did = row["id"]
    rep.rules = conn.execute("SELECT COUNT(*) FROM rules WHERE document_id = ?", (did,)).fetchone()[0]
    rep.extraction_edges = conn.execute("SELECT COUNT(*) FROM edges WHERE document_id = ? AND rel_type != ?",
                                        (did, RelType.REFERANS_VERIR)).fetchone()[0]
    if not apply:
        return rep

    old = {r["id"]: (r["clause_no"], r["heading_path"]) for r in
           conn.execute("SELECT id, clause_no, heading_path FROM sections WHERE document_id = ?", (did,))}
    links = {t: conn.execute(f"SELECT id, section_id FROM {t} WHERE document_id = ? AND section_id IS NOT NULL",
                             (did,)).fetchall() for t in ("rules", "edges")}
    try:
        conn.execute("DELETE FROM edges WHERE document_id = ? AND rel_type = ?", (did, RelType.REFERANS_VERIR))
        conn.execute("DELETE FROM doc_references WHERE document_id = ?", (did,))
        conn.execute("DELETE FROM sections WHERE document_id = ?", (did,))
        # Önceki uyarılardan OCR ile ilgili olanları yenileriyle değiştir.
        prev = [w for w in json.loads(row["parse_warnings"] or "[]")
                if not w.startswith(("OCR", "Metin katmanı çok az"))]
        warnings = prev + parsed.warnings
        conn.execute("UPDATE documents SET header_text = ?, body_text = ?, parse_warnings = ? WHERE id = ?",
                     (parsed.header_text, parsed.body_text, json.dumps(warnings, ensure_ascii=False), did))
        _insert_sections(conn, did, row["code_key"], parsed.body_text)
        new = conn.execute("SELECT id, clause_no, heading_path FROM sections WHERE document_id = ?", (did,)).fetchall()
        by_clause = {r["clause_no"]: r["id"] for r in new if r["clause_no"]}
        by_path = {r["heading_path"]: r["id"] for r in new if r["heading_path"]}
        for table, rows in links.items():
            for r in rows:
                clause, path_ = old.get(r["section_id"], (None, None))
                sid = by_clause.get(clause) if clause else None
                sid = sid or (by_path.get(path_) if path_ else None)
                conn.execute(f"UPDATE {table} SET section_id = ? WHERE id = ?", (sid, r["id"]))
                if sid:
                    rep.relinked += 1
                else:
                    rep.unlinked += 1
        resolve_references(conn)  # commit eder
    except Exception:
        conn.rollback()
        raise
    rep.applied = True
    return rep
