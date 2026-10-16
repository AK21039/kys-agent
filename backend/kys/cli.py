"""Komut satırı: python -m kys.cli <komut>"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import db, overrides
from .config import PROJECT_ROOT, settings
from .ingest.pipeline import ingest_paths, resolve_references


def _conn():
    conn = db.connect()
    db.init_db(conn)
    return conn


def cmd_init_db(args) -> None:
    _conn()
    print(f"Veritabanı hazır: {settings.db_path}")


def cmd_ingest(args) -> None:
    conn = _conn()
    root = Path(args.path)
    if not root.exists():
        sys.exit(f"Bulunamadı: {root}")

    def progress(r):
        line = f"[{r.status:8}] {r.path.name}"
        if r.code:
            line += f"  →  {r.code} Rev.{r.revision} ({r.doc_type or '-'})"
        if r.message:
            line += f"  · {r.message}"
        print(line)
        for w in r.warnings:
            print(f"           ! {w}")

    results = ingest_paths(conn, root, use_llm=not args.no_llm, progress=progress, ocr=not args.no_ocr)
    counts = {s: sum(r.status == s for r in results) for s in ("eklendi", "atlandi", "hata")}
    unresolved = conn.execute("SELECT COUNT(*) FROM doc_references WHERE resolved_doc_id IS NULL").fetchone()[0]
    print(f"\nÖzet: {counts['eklendi']} eklendi, {counts['atlandi']} atlandı, {counts['hata']} hata. "
          f"Çözülmemiş doküman atfı: {unresolved}")


def cmd_ocr_check(args) -> None:
    """Kayıtlı PDF dokümanlardan OCR adaylarını listeler (DB'ye yazmaz, OCR çalıştırmaz)."""
    from .ingest import ocr
    conn = _conn()
    n = cands = 0
    for r in conn.execute("SELECT code, revision, file_path, parse_warnings FROM documents "
                          "WHERE lower(file_path) LIKE '%.pdf' ORDER BY code"):
        n += 1
        path = Path(r["file_path"])
        if not path.exists():
            print(f"[dosya yok ] {r['code']}  {path}")
            continue
        try:
            pages, todo, counts = ocr.scan_pdf(path)
        except Exception as e:
            print(f"[okunamadı ] {r['code']}  {type(e).__name__}: {e}")
            continue
        done = any(w.startswith("OCR uygulandı") for w in json.loads(r["parse_warnings"] or "[]"))
        if todo:
            cands += 1
            state = "OCR YAPILDI" if done else "ADAY"
            print(f"[{state:11}] {r['code']} Rev.{r['revision']}  {pages} sayfa, aday sayfalar: "
                  f"{ocr.page_ranges(todo)} (karakter: {[counts[i] for i in todo]})  {path.name}")
    eng = ocr.get_engine()
    print(f"\n{n} PDF tarandı, {cands} OCR adayı. OCR motoru: {eng.name if eng else 'YOK (pip install -e backend[ocr])'}")
    if cands:
        print("Yeniden işlemek için: kys reingest KOD  (etkiyi gösterir)  ·  kys reingest KOD --apply")


def cmd_reingest(args) -> None:
    from .ingest.pipeline import reingest_document
    conn = _conn()
    rep = reingest_document(conn, args.code, apply=args.apply, ocr=not args.no_ocr)
    if rep is None:
        sys.exit(f"Doküman yok: {args.code}")
    if rep.error:
        sys.exit(rep.error)
    print(f"{rep.code} Rev.{rep.revision}: gövde {rep.old_chars} → {rep.new_chars} karakter")
    for w in rep.warnings:
        print(f"  ! {w}")
    print(f"Bu dokümana bağlı {rep.rules} kural ve {rep.extraction_edges} çıkarım kenarı SİLİNMEZ "
          "(aynı kayıt güncellenir; bölüm bağları madde no / başlık yoluyla yeniden kurulur).")
    if rep.applied:
        print(f"UYGULANDI. Bölüm bağı korunan: {rep.relinked}, kopan: {rep.unlinked} "
              "(kopanların alıntısı geçerli, yalnızca madde bağı boş). Yeni metin için kural çıkarımını yenilemeyi düşünün.")
    else:
        print("KURU ÇALIŞMA: hiçbir şey yazılmadı. Uygulamak için --apply ekleyin.")


def cmd_docs(args) -> None:
    conn = _conn()
    rows = conn.execute(
        """SELECT d.id, d.code, d.revision, d.doc_type, d.status, d.title, d.meta_source,
                  (SELECT COUNT(*) FROM sections s WHERE s.document_id = d.id) AS n_sec
           FROM documents d ORDER BY d.doc_type, d.code, d.revision"""
    ).fetchall()
    for r in rows:
        print(f"#{r['id']:<4} {r['code']:<14} Rev.{r['revision']:<3} {r['doc_type']:<13} {r['status']:<10} "
              f"{r['n_sec']:>3} bölüm  {r['title']}  [{r['meta_source']}]")
    print(f"\n{len(rows)} doküman")


def cmd_show(args) -> None:
    conn = _conn()
    from .ingest.metadata import code_key
    d = conn.execute("SELECT * FROM documents WHERE code_key = ? ORDER BY created_at DESC LIMIT 1",
                     (code_key(args.code),)).fetchone()
    if not d:
        sys.exit(f"Doküman yok: {args.code}")
    print(f"{d['code']} Rev.{d['revision']} — {d['title']} ({d['doc_type']}, {d['status']})")
    if d["summary"]:
        print(f"Özet: {d['summary']}")
    warnings = json.loads(d["parse_warnings"] or "[]")
    for w in warnings:
        print(f"! {w}")
    print("\nBölümler:")
    for s in conn.execute("SELECT clause_no, heading_path, length(text) AS n FROM sections "
                          "WHERE document_id = ? ORDER BY ordinal", (d["id"],)):
        print(f"  {s['heading_path'] or '(giriş)'}  [{s['n']} kr]")
    print("\nAtıflar:")
    for r in conn.execute(
        """SELECT r.ref_code, t.code, t.revision, t.status FROM doc_references r
           LEFT JOIN documents t ON t.id = r.resolved_doc_id WHERE r.document_id = ?""", (d["id"],)):
        target = f"{r['code']} Rev.{r['revision']} ({r['status']})" if r["code"] else "ÇÖZÜLEMEDİ"
        print(f"  {r['ref_code']} → {target}")


def cmd_search(args) -> None:
    conn = _conn()
    rows = db.search_sections(conn, args.query, limit=args.limit, only_active=not args.all)
    for r in rows:
        snippet = " ".join(r["text"].split())[:220]
        print(f"{r['code']} Rev.{r['revision']} md.{r['clause_no'] or '-'}  {r['heading'] or ''}\n    {snippet}\n")
    if not rows:
        print("Sonuç yok (en az 3 karakterli kelimeler kullanın).")


def cmd_refs(args) -> None:
    from .ingest.metadata import known_segments, looks_like_doc_code
    conn = _conn()
    resolve_references(conn)
    segments = known_segments([r[0] for r in conn.execute("SELECT code FROM documents WHERE code NOT LIKE 'KODSUZ%'")])
    rows = conn.execute(
        """SELECT r.ref_code, GROUP_CONCAT(DISTINCT d.code) AS sources FROM doc_references r
           JOIN documents d ON d.id = r.document_id
           WHERE r.resolved_doc_id IS NULL GROUP BY r.ref_code ORDER BY r.ref_code"""
    ).fetchall()
    missing = [r for r in rows if looks_like_doc_code(r["ref_code"], segments)]
    other = [r for r in rows if not looks_like_doc_code(r["ref_code"], segments)]
    print("Sistemde olmayan dokümanlara atıflar (yüklenmemiş veya yanlış kod):")
    for r in missing:
        print(f"  {r['ref_code']:<16} ← {r['sources']}")
    print("\nDoküman kodu olmayabilir (makine/hat/ekipman adı):")
    print("  " + ", ".join(r["ref_code"] for r in other) if other else "  -")
    print(f"\n{len(missing)} eksik doküman, {len(other)} şüpheli atıf")


def cmd_uncoded(args) -> None:
    conn = _conn()
    rows = conn.execute("SELECT code, title, file_path FROM documents "
                        "WHERE code LIKE 'KODSUZ%' OR code LIKE '%#%' ORDER BY code").fetchall()
    for r in rows:
        print(f"{r['code']:<18} {r['title']}  ({Path(r['file_path']).name})")
    print(f"\n{len(rows)} doküman. Düzeltmek için: kys set-code <geçici_kod> <doğru_kod> [--rev NN]")


def cmd_set_code(args) -> None:
    from .ingest.metadata import code_key
    conn = _conn()
    doc = conn.execute("SELECT id, code, revision, title, file_sha256, file_path FROM documents WHERE code_key = ? "
                       "ORDER BY created_at DESC LIMIT 1", (code_key(args.old),)).fetchone()
    if not doc:
        sys.exit(f"Doküman yok: {args.old}")
    revision = f"{int(args.rev):02d}" if args.rev and args.rev.isdigit() else (args.rev or doc["revision"])
    if conn.execute("SELECT 1 FROM documents WHERE code_key = ? AND revision = ? AND id != ?",
                    (code_key(args.new), revision, doc["id"])).fetchone():
        sys.exit(f"{args.new} Rev.{revision} başka bir dokümanda kayıtlı.")
    conn.execute("UPDATE documents SET code = ?, code_key = ?, revision = ?, meta_source = 'kullanici' WHERE id = ?",
                 (args.new, code_key(args.new), revision, doc["id"]))
    conn.commit()
    overrides.put(doc["file_sha256"], Path(doc["file_path"]).name, code=args.new, revision=revision)
    resolved, _ = resolve_references(conn)
    print(f"{doc['code']} → {args.new} Rev.{revision} ({doc['title']}). Yeni çözülen atıf: {resolved}")


def cmd_classify(args) -> None:
    from .ingest.pipeline import classify_existing
    conn = _conn()
    print(f"Model: {settings.model_fast} — başlangıç {datetime.now():%H:%M}", flush=True)

    def progress(r):
        status = "HATA" if r.error else "ok"
        change = f"{r.old_code} → {r.code}" if r.old_code != r.code else r.code
        print(f"[{status:4}] {r.seconds:5.0f} sn  {change:<22} {r.doc_type:<13} {r.title}"
              + (f"  · {r.error}" if r.error else ""), flush=True)
        for w in r.warnings:
            print(f"           ! {w}", flush=True)

    results = classify_existing(conn, limit=args.limit, redo=args.redo, progress=progress)
    failed = sum(1 for r in results if r.error)
    print(f"\nBitti {datetime.now():%H:%M}: {len(results) - failed} sınıflandırıldı, {failed} hata.")


def cmd_scheduled(args) -> None:
    """Zamanlanmış iş: yeni dosyaları yükle, sonra sınıflandır. Çıktı yerel log dosyasına yazılır.

    Şirket politikası cmd.exe'yi engellediği için Görev Zamanlayıcı doğrudan kys.exe'yi çağırır; yönlendirme burada yapılır.
    """
    from .config import LOCAL_HOME, settings
    log_dir = LOCAL_HOME / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"zamanli-{datetime.now():%Y%m%d-%H%M}.log"
    with open(log_path, "w", encoding="utf-8") as log:
        sys.stdout = sys.stderr = log
        try:
            cmd_ingest(argparse.Namespace(path=str(settings.inbox_dir), no_llm=True, no_ocr=False))
            print()
            cmd_classify(argparse.Namespace(limit=args.limit, redo=False))
        except Exception:
            import traceback
            traceback.print_exc()
            raise
        finally:
            sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__


def publish_snapshot(src_conn, out: Path) -> Path:
    """Sorgu servisi için salt okunur kopya: tek dosya (WAL yok), LLM logları ve yerel yollar hariç."""
    import sqlite3
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    from contextlib import closing
    with closing(sqlite3.connect(tmp)) as dst:  # closing: Windows'ta dosya kilidi kalmasın
        src_conn.backup(dst)
        dst.execute("DELETE FROM llm_calls")
        from pathlib import PureWindowsPath
        dst.executemany("UPDATE documents SET file_path = ? WHERE id = ?",  # yerel ağ yolları dışarı çıkmasın
                        [(PureWindowsPath(fp).name, i) for i, fp in dst.execute("SELECT id, file_path FROM documents")])
        dst.commit()  # journal_mode açık bir işlem içinde sessizce değişmez
        dst.execute("PRAGMA journal_mode = DELETE")
        dst.execute("VACUUM")
    tmp.replace(out)
    return out


def cmd_publish(args) -> None:
    from .config import LOCAL_HOME
    conn = _conn()
    out = Path(args.out) if args.out else LOCAL_HOME / "publish" / "kys-query.db"
    publish_snapshot(conn, out)
    if args.pages is not None:
        from .query import pages
        pdir = Path(args.pages) if args.pages else out.parent / "pages"
        docs, n = pages.render_all(conn, pdir)
        print(f"Sayfa görüntüleri: {docs} yeni PDF, {n} sayfa → {pdir}  (konteynerde KYS_PAGES_DIR ile bağlayın)")
    n = conn.execute("SELECT COUNT(*) FROM documents WHERE status = 'YURURLUKTE'").fetchone()[0]
    print(f"Yayın kopyası hazır: {out} ({out.stat().st_size / 1e6:.1f} MB, {n} yürürlükteki doküman)")
    print("Sorgu servisine yükleyin (KYS_DB_PATH ile bağlayın veya KYS_DB_URL ile indirtin).")


def cmd_flow(args) -> None:
    from .process import flow
    conn = _conn()
    p = flow.get_process(conn, args.code)
    if not p:
        sys.exit(f"Süreç yok: {args.code}")
    text = f"```mermaid\n{p['mermaid']}```\n" if args.out else p["mermaid"]
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"# {p['code']} — {p['name']}\n\n{text}", encoding="utf-8")
        print(f"{len(p['steps'])} adım → {out}")
    else:
        print(text, end="")


def cmd_convert_legacy(args) -> None:
    from .ingest import convert
    src = Path(args.folder)
    if not src.exists():
        sys.exit(f"Bulunamadı: {src}")
    out = Path(args.out) if args.out else PROJECT_ROOT / "data" / "converted" / src.name
    if not convert.com_available():
        sys.exit("Word/Excel COM yalnızca Windows'ta (PowerShell ile) kullanılabilir. "
                 "Alternatif: LibreOffice ile soffice --headless --convert-to docx.")

    def progress(r):
        print(f"[{r.status:12}] {r.src.name}" + (f"  ->  {r.dst}" if r.dst else "") + (f"  · {r.message}" if r.message else ""))

    res = convert.convert_folder(src, out, overwrite=args.overwrite, progress=progress)
    n = {s: sum(r.status == s for r in res) for s in ("donusturuldu", "atlandi", "hata")}
    print(f"\nÖzet: {n['donusturuldu']} dönüştürüldü, {n['atlandi']} atlandı, {n['hata']} hata. Çıktı: {out}")


def cmd_flow_compare(args) -> None:
    """vsdx akış şemasını DB'deki süreç adımlarıyla karşılaştırır; DB'ye yazmaz."""
    from .ingest import flowcompare
    conn = db.connect(readonly=True)
    try:
        rep = flowcompare.compare(conn, args.code, args.vsdx, args.page)
    except (LookupError, ValueError, OSError) as e:
        sys.exit(str(e))
    text = rep.text()
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Rapor yazıldı: {args.out}")
    else:
        print(text)


def cmd_content_compare(args) -> None:
    """Klasördeki Word dosyalarını DB'deki dokümanlarla karşılaştırır; DB'ye yazmaz."""
    from .ingest import doccompare
    root = Path(args.folder)
    if not root.exists():
        sys.exit(f"Bulunamadı: {root}")
    converted = Path(args.converted) if args.converted else PROJECT_ROOT / "data" / "converted" / root.name
    items = doccompare.compare_folder(db.connect(readonly=True), root, converted if converted.exists() else None)
    text = doccompare.to_markdown(items)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"{len(items)} dosya -> {args.out}")
    else:
        print(text)


def cmd_render(args) -> None:
    from . import pdfrender
    from .config import PROJECT_ROOT
    from .query import pages
    conn = _conn()
    from .ingest.metadata import code_key
    d = conn.execute("SELECT code, file_path FROM documents WHERE code_key = ? ORDER BY created_at DESC LIMIT 1",
                     (code_key(args.code),)).fetchone()
    if not d:
        sys.exit(f"Doküman yok: {args.code}")
    src = pages.find_source(d["file_path"])
    if not src or src.suffix.lower() != ".pdf":
        sys.exit(f"PDF dosyası bulunamadı: {d['file_path']}")
    out = Path(args.out) if args.out else PROJECT_ROOT / "data" / "render" / "".join(
        ch if ch.isalnum() or ch in "-_." else "_" for ch in d["code"])
    out.mkdir(parents=True, exist_ok=True)
    n = pdfrender.page_count(src)
    for i in range(n):
        (out / f"sayfa-{i + 1}.png").write_bytes(pdfrender.page_png(src, i, args.scale))
    print(f"{n} sayfa → {out}")


def cmd_serve(args) -> None:
    import os

    import uvicorn
    if args.db:
        os.environ["KYS_DB_PATH"] = str(Path(args.db).resolve())
    print(f"http://localhost:{args.port}{settings.base_path.rstrip('/')}/  (durdurmak için Ctrl+C)")
    uvicorn.run("kys.api.app:app", host=args.host, port=args.port)


def cmd_extract_export(args) -> None:
    from .extract import workflow
    conn = _conn()
    files = workflow.export(conn, only_missing=not args.all)
    print(f"{len(files)} doküman dışa aktarıldı → {workflow.work_dir() / 'in'}")


def cmd_extract_check(args) -> None:
    from .extract import workflow
    conn = _conn()
    failed = 0
    for f in args.files:
        _, r = workflow.check(conn, Path(f))
        failed += not r.ok
        print(f"[{'TAMAM' if r.ok else 'HATA '}] {Path(f).name}  {r.counts}")
        for e in r.errors:
            print(f"    ! {e}")
        for q in r.bad_quotes:
            print(f"    ! Kaynakta birebir bulunamayan alıntı → {q}")
    sys.exit(1 if failed else 0)


def cmd_extract_import(args) -> None:
    from .extract import workflow
    conn = _conn()
    files = [Path(f) for f in args.files] or sorted((workflow.work_dir() / "out").glob("*.json"))
    totals = {"dosya": 0, "kural": 0, "atilan": 0}
    for f in files:
        r = workflow.import_file(conn, f)
        if r.errors and not r.counts:
            print(f"[HATA ] {f.name}: {r.errors[0][:200]}")
            continue
        totals["dosya"] += 1
        totals["kural"] += r.counts.get("eklenen_kural", 0)
        totals["atilan"] += r.counts.get("atilan", 0)
        print(f"[ok   ] {f.name}  {r.counts}")
    print(f"\n{totals['dosya']} doküman, {totals['kural']} kural eklendi (ONERILDI), "
          f"{totals['atilan']} kanıtsız öğe atıldı.")


def cmd_stats(args) -> None:
    conn = _conn()
    for r in conn.execute(
        """SELECT purpose, model, COUNT(*) n, SUM(ok) ok, SUM(input_tokens) i, SUM(output_tokens) o,
                  SUM(cache_read_tokens) c FROM llm_calls GROUP BY purpose, model"""):
        print(f"{r['purpose']:<16} {r['model']:<20} çağrı={r['n']} başarılı={r['ok']} "
              f"girdi={r['i'] or 0} çıktı={r['o'] or 0} önbellek={r['c'] or 0}")


def main(argv=None) -> None:
    # Windows'ta yönlendirilmiş çıktı cp1254 olur; Türkçe ve ok karakterleri için UTF-8'e zorla.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="kys", description="KYS Ajan Sistemi")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="veritabanını oluştur").set_defaults(fn=cmd_init_db)
    s = sub.add_parser("ingest", help="dosya veya klasör yükle")
    s.add_argument("path")
    s.add_argument("--no-llm", action="store_true", help="sınıflandırıcıyı çalıştırma (yalnızca kural tabanlı)")
    s.add_argument("--no-ocr", action="store_true", help="metin katmanı olmayan PDF sayfalarına OCR uygulama")
    s.set_defaults(fn=cmd_ingest)
    s = sub.add_parser("ocr-check", help="OCR gerektiren (metin katmanı az / görüntü ağırlıklı) PDF'leri listele")
    s.set_defaults(fn=cmd_ocr_check)
    s = sub.add_parser("reingest", help="kayıtlı dokümanı yeniden ayrıştır (OCR dahil); --apply olmadan yazmaz")
    s.add_argument("code")
    s.add_argument("--apply", action="store_true")
    s.add_argument("--no-ocr", action="store_true")
    s.set_defaults(fn=cmd_reingest)
    sub.add_parser("docs", help="dokümanları listele").set_defaults(fn=cmd_docs)
    s = sub.add_parser("show", help="doküman ayrıntısı")
    s.add_argument("code")
    s.set_defaults(fn=cmd_show)
    s = sub.add_parser("search", help="tam metin arama")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--all", action="store_true", help="iptal edilmiş revizyonları da ara")
    s.set_defaults(fn=cmd_search)
    sub.add_parser("refs", help="çözülmemiş doküman atıfları").set_defaults(fn=cmd_refs)
    s = sub.add_parser("set-code", help="doküman kodunu elle düzelt (ör. KODSUZ-xxxx → FR-012)")
    s.add_argument("old")
    s.add_argument("new")
    s.add_argument("--rev", help="revizyon numarası (verilmezse korunur)")
    s.set_defaults(fn=cmd_set_code)
    sub.add_parser("uncoded", help="kodu bulunamayan dokümanlar").set_defaults(fn=cmd_uncoded)
    s = sub.add_parser("classify", help="kayıtlı dokümanları hızlı modelle sınıflandır (özet, tip, başlık)")
    s.add_argument("--limit", type=int)
    s.add_argument("--redo", action="store_true", help="daha önce sınıflandırılanları da tekrar işle")
    s.set_defaults(fn=cmd_classify)
    s = sub.add_parser("extract-export", help="kural çıkarımı için dokümanları data/extract/in'e aktar")
    s.add_argument("--all", action="store_true", help="çıktısı olanları da yeniden aktar")
    s.set_defaults(fn=cmd_extract_export)
    s = sub.add_parser("extract-check", help="çıkarım JSON'unu doğrula (şema + birebir alıntı), DB'ye yazmaz")
    s.add_argument("files", nargs="+")
    s.set_defaults(fn=cmd_extract_check)
    s = sub.add_parser("extract-import", help="çıkarım JSON'larını içe aktar (kurallar ONERILDI girer)")
    s.add_argument("files", nargs="*")
    s.set_defaults(fn=cmd_extract_import)
    s = sub.add_parser("publish", help="sorgu servisi için salt okunur veritabanı kopyası üret")
    s.add_argument("--out", help="çıktı dosyası (varsayılan: %%LOCALAPPDATA%%\\kys-agent\\publish\\kys-query.db)")
    s.add_argument("--pages", nargs="?", const="", metavar="KLASÖR",
                   help="PDF sayfa görüntülerini de üret (varsayılan klasör: yayın dosyasının yanında pages/)")
    s.set_defaults(fn=cmd_publish)
    s = sub.add_parser("flow", help="sürecin Mermaid akış şemasını yaz")
    s.add_argument("code")
    s.add_argument("--out", help="Markdown dosyasına yaz (varsayılan: ekrana)")
    s.set_defaults(fn=cmd_flow)
    s = sub.add_parser("convert-legacy", help="eski .doc/.xls dosyalarını Word/Excel COM ile .docx/.xlsx'e çevir (orijinale dokunmaz)")
    s.add_argument("folder")
    s.add_argument("--out", help="çıktı klasörü (varsayılan: data/converted/<klasör adı>)")
    s.add_argument("--overwrite", action="store_true")
    s.set_defaults(fn=cmd_convert_legacy)
    s = sub.add_parser("flow-compare", help="vsdx akış şemasını DB'deki süreç adımlarıyla karşılaştır (yazmaz)")
    s.add_argument("code", help="DB'deki süreç kodu (ör. PR12-PRJ-6#2)")
    s.add_argument("vsdx")
    s.add_argument("--page", help="vsdx sayfa no veya ad parçası (varsayılan: Dök.No / ad benzerliği)")
    s.add_argument("--out", help="raporu dosyaya yaz")
    s.set_defaults(fn=cmd_flow_compare)
    s = sub.add_parser("content-compare", help="Word dosyalarını (.doc dönüştürülmüş haliyle) DB dokümanlarıyla karşılaştır (yazmaz)")
    s.add_argument("folder")
    s.add_argument("--converted", help="dönüştürülmüş .docx klasörü (varsayılan: data/converted/<klasör adı>)")
    s.add_argument("--out", help="raporu dosyaya yaz (markdown)")
    s.set_defaults(fn=cmd_content_compare)
    s = sub.add_parser("render", help="dokümanın PDF sayfalarını PNG yap (varsayılan: data/render/KOD)")
    s.add_argument("code")
    s.add_argument("--out", help="çıktı klasörü")
    s.add_argument("--scale", type=float, default=2.0)
    s.set_defaults(fn=cmd_render)
    s = sub.add_parser("serve", help="sorgu servisini yerelde çalıştır (web + API + MCP)")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--db", help="kullanılacak veritabanı (varsayılan: KYS_DB_PATH)")
    s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("scheduled", help="zamanlanmış iş: yükle + sınıflandır, log dosyasına yaz")
    s.add_argument("--limit", type=int)
    s.set_defaults(fn=cmd_scheduled)
    sub.add_parser("stats", help="LLM kullanım istatistikleri").set_defaults(fn=cmd_stats)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
