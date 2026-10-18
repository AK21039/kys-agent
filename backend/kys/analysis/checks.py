"""Faz 3 katman 1 — 7 deterministik (LLM'siz) kontrol (PLAN.md §2.1 / §3 Denetim Radarı).

Her kontrol tek bir fonksiyondur ve `Context`'ten okuyup `CheckOutcome` döner. Hiçbiri veritabanına yazmaz
(`kys analiz` çağrısı yalnızca `--kaydet` ile yazar, bkz. `store.py`). Analizler YURURLUKTE dokümanlarla
sınırlıdır (CLAUDE.md değişmez 2); ONERILDI kurala dayanan bulgu `unverified_basis=True` taşır.

4 numaralı plan maddesi ("görev tanımı olmayan rol" + "hiçbir süreçte/kuralda geçmeyen rol") iki ayrı, bağımsız
seçilebilir kontrole bölündü (`gorev_tanimi_eksik`, `rol_kullanilmiyor`) — ikisi de BOSLUK/DUSUK üretir ama
farklı verilere bakar, tek fonksiyonda birleştirmek `--kontrol AD` ile tek tek çalıştırmayı imkânsız kılardı.
"""

import re
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from typing import Callable

from ..ontology import FindingType, Severity
from ..textnorm import fold, fold_chars, verify_quote
from .model import CheckOutcome, Context, Finding


# ---- paylaşılan yardımcılar ----------------------------------------------------------------------------------

def _evidence(doc: dict, clause_no: str | None, quote: str | None, section_id: int | None = None) -> dict:
    return {"doc_code": doc["code"], "revision": doc["revision"], "clause_no": clause_no, "quote": quote,
            "section_id": section_id}


def _quote_near(text: str | None, needle: str, radius: int = 120, max_len: int = 260) -> str | None:
    """Kaynak metinden `needle`'ın geçtiği yerin çevresini keser: sonuç kaynağın birebir alt dizgesidir
    (biçim farkı olmaz), bu yüzden ayrıca `verify_quote` doğrulaması gerekmez."""
    if not text or not text.strip():
        return None
    hay = fold_chars(text)
    pos = hay.find(fold_chars(needle))
    if pos < 0:
        snippet = text.strip()
        return snippet[:max_len] or None
    start = max(0, pos - radius)
    end = min(len(text), pos + len(needle) + radius)
    snippet = text[start:end].strip()
    return snippet[:max_len] or None


def _longest_common_quote(text_a: str, text_b: str, min_len: int = 30, max_len: int = 280):
    """İki gövde metninin en uzun ortak alt dizgesi: (a'daki alıntı, b'deki alıntı) ya da (None, None)."""
    fa, fb = fold_chars(text_a or ""), fold_chars(text_b or "")
    # autojunk=False: autojunk, popüler TEK KARAKTERLERİ (boşluk, sık sesli harfler) "junk" sayıp aralarındaki
    # gerçek uzun eşleşmeyi gizliyor (karakter dizisi karşılaştırmasında kullanım amacı dışı — satır bazlı diff
    # için tasarlandı). Kapalıyken ME-TL-001/YP-TL-001 gibi gerçek mükerrer çiftlerde 800+ karakterlik ortak blok
    # bulunuyor; açıkken 0 dönüyordu.
    match = SequenceMatcher(None, fa, fb, autojunk=False).find_longest_match(0, len(fa), 0, len(fb))
    if match.size < min_len:
        return None, None
    qa = text_a[match.a: match.a + min(match.size, max_len)].strip()
    qb = text_b[match.b: match.b + min(match.size, max_len)].strip()
    if len(qa) < min_len or len(qb) < min_len:
        return None, None
    return qa, qb


def _topic_tokens(text: str | None) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", fold(text or "")) if len(w) >= 3}


def _shingles(text: str | None, k: int = 6) -> set[tuple[str, ...]]:
    words = fold(text or "").split()
    if len(words) < k:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + k]) for i in range(len(words) - k + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


# ---- 1. Yürürlükten kalkmış (IPTAL) dokümana/forma atıf (GUNCELLIK) ------------------------------------------

def check_guncellik_atif(ctx: Context) -> CheckOutcome:
    rows = ctx.conn.execute(
        """SELECT r.ref_code, r.section_id, r.resolved_doc_id, sd.id AS src_id, sd.code AS src_code,
                  sd.revision AS src_revision, s.text AS sec_text, s.clause_no AS sec_clause
           FROM doc_references r JOIN documents sd ON sd.id = r.document_id
           LEFT JOIN sections s ON s.id = r.section_id
           WHERE sd.status = 'YURURLUKTE' AND r.resolved_doc_id IS NOT NULL"""
    ).fetchall()
    findings: list[Finding] = []
    for row in rows:
        tgt = ctx.docs.get(row["resolved_doc_id"])
        if not tgt or tgt["status"] != "IPTAL":
            continue
        quote = _quote_near(row["sec_text"], row["ref_code"])
        if not quote:
            continue
        src = {"code": row["src_code"], "revision": row["src_revision"]}
        findings.append(Finding(
            check="guncellik_atif", finding_type=FindingType.GUNCELLIK, severity=Severity.ORTA,
            title=f"{row['src_code']} Rev.{row['src_revision']}, yürürlükten kalkmış {tgt['code']} Rev.{tgt['revision']}'e atıf veriyor",
            explanation=(f"{row['src_code']} Rev.{row['src_revision']} dokümanında geçen '{row['ref_code']}' atfı, "
                         f"durumu İPTAL olan {tgt['code']} Rev.{tgt['revision']}'e işaret ediyor."),
            recommendation=f"{row['src_code']} içindeki atıf, {tgt['code']}'in güncel (yürürlükteki) revizyonuna "
                           "veya onun yerini alan dokümana güncellenmeli.",
            evidence=[_evidence(src, row["sec_clause"], quote, row["section_id"])],
            key=f"guncellik|{row['src_id']}|{row['section_id']}|{row['ref_code']}|{row['resolved_doc_id']}",
        ))
    return CheckOutcome(findings, considered=len(rows))


# ---- 2. Sistemde bulunmayan doküman koduna atıf — kırık referans (BOSLUK) -------------------------------------

def check_kirik_referans(ctx: Context) -> CheckOutcome:
    from ..ingest.metadata import known_segments, looks_like_doc_code
    segments = known_segments([d["code"] for d in ctx.docs.values() if not d["code"].upper().startswith("KODSUZ")])
    rows = ctx.conn.execute(
        """SELECT r.ref_code, r.section_id, sd.id AS src_id, sd.code AS src_code, sd.revision AS src_revision,
                  s.text AS sec_text, s.clause_no AS sec_clause
           FROM doc_references r JOIN documents sd ON sd.id = r.document_id
           LEFT JOIN sections s ON s.id = r.section_id
           WHERE sd.status = 'YURURLUKTE' AND r.resolved_doc_id IS NULL"""
    ).fetchall()
    findings: list[Finding] = []
    considered = 0
    for row in rows:
        if not looks_like_doc_code(row["ref_code"], segments):
            continue
        considered += 1
        quote = _quote_near(row["sec_text"], row["ref_code"])
        if not quote:
            continue
        src = {"code": row["src_code"], "revision": row["src_revision"]}
        findings.append(Finding(
            check="kirik_referans", finding_type=FindingType.BOSLUK, severity=Severity.ORTA,
            title=f"{row['src_code']} Rev.{row['src_revision']}, sistemde olmayan '{row['ref_code']}' koduna atıf veriyor",
            explanation=(f"{row['src_code']} Rev.{row['src_revision']} dokümanında geçen '{row['ref_code']}' kodu "
                         "veritabanındaki hiçbir dokümana karşılık gelmiyor (yüklenmemiş veya yanlış yazılmış kod)."),
            recommendation="İlgili doküman sisteme yüklenmeli veya atıf kodu düzeltilmeli.",
            evidence=[_evidence(src, row["sec_clause"], quote, row["section_id"])],
            key=f"kirik|{row['src_id']}|{row['section_id']}|{row['ref_code']}",
        ))
    return CheckOutcome(findings, considered=considered)


# ---- 3. Sorumlusu/onaycısı tanımsız süreç adımı (BOSLUK) -------------------------------------------------------

def check_adim_sorumlusu(ctx: Context) -> CheckOutcome:
    rows = ctx.conn.execute(
        """SELECT st.id, st.name, st.description, st.quote, st.decision, st.seq,
                  st.responsible_entity_id, st.approver_entity_id,
                  p.code AS pcode, d.code AS code, d.revision AS revision
           FROM process_steps st JOIN processes p ON p.id = st.process_id
           JOIN documents d ON d.id = p.document_id
           WHERE d.status = 'YURURLUKTE'"""
    ).fetchall()
    findings: list[Finding] = []
    for st in rows:
        missing = []
        if not st["responsible_entity_id"]:
            missing.append("sorumlu")
        needs_approval = bool(st["decision"]) or "onay" in fold(f"{st['name']} {st['description'] or ''}")
        if needs_approval and not st["approver_entity_id"]:
            missing.append("onaycı")
        if not missing:
            continue
        quote = st["quote"] or st["description"] or st["name"]
        if not quote:
            continue
        severity = Severity.ORTA if "sorumlu" in missing else Severity.DUSUK
        label = " ve ".join(missing)
        findings.append(Finding(
            check="adim_sorumlusu", finding_type=FindingType.BOSLUK, severity=severity,
            title=f"{st['pcode']} adım {st['seq']} ('{st['name']}'): {label} tanımsız",
            explanation=f"{st['pcode']} sürecinin {st['seq']}. adımı ('{st['name']}') için {label} rolü tanımlı değil.",
            recommendation=f"Adıma {label} rolü atanmalı (dokümanda belirtiliyorsa role bağlanmalı).",
            evidence=[_evidence(st, f"{st['pcode']} adım {st['seq']}", quote)],
            key=f"adim|{st['id']}|{','.join(missing)}",
        ))
    return CheckOutcome(findings, considered=len(rows))


# ---- 4a/4b paylaşılan: rolün DB'de doğrulanabilir bir izi var mı? ----------------------------------------------

def _verify_against_doc(ctx: Context, document_id: int, section_id: int | None, quote: str | None) -> bool:
    """Alıntı, bölümün (varsa) yoksa dokümanın gövde metninin birebir alt dizgesi mi? (değişmez 1)."""
    if not quote:
        return False
    text = ctx.section_text(section_id) if section_id else None
    if text is None:
        doc = ctx.docs.get(document_id)
        text = doc["body_text"] if doc else None
    return bool(text) and verify_quote(quote, text)


def _role_evidence(ctx: Context, role_id: int) -> dict | None:
    """Rolün sistemde doğrulanabilir bir iz bıraktığını gösteren İLK kaynak (doc_code+rev+madde+birebir alıntı,
    `verify_quote` ile bölüm/gövde metnine karşı doğrulanmış). Öncelik: kural öznesi/nesnesi → süreç adımı
    sorumlusu/onaycısı → doküman↔varlık kenarı (`edges`, ör. ExReference ile çözülen bir atıf). Hiçbiri yoksa
    None — çağıran bunu BELIRSIZLIK'e çevirir (değişmez 1: alıntı yoksa bulgu üretme ya da BELIRSIZLIK yap)."""
    for r in ctx.conn.execute(
            """SELECT ru.quote, ru.clause_no, ru.section_id, d.id AS doc_id, d.code, d.revision
               FROM rules ru JOIN documents d ON d.id = ru.document_id
               WHERE d.status = 'YURURLUKTE' AND (ru.subject_entity_id = ? OR ru.object_entity_id = ?)
               ORDER BY ru.id""", (role_id, role_id)):
        if _verify_against_doc(ctx, r["doc_id"], r["section_id"], r["quote"]):
            return _evidence(r, r["clause_no"], r["quote"], r["section_id"])
    for r in ctx.conn.execute(
            """SELECT st.quote, p.document_id AS doc_id, d.code, d.revision, p.code AS pcode, st.seq
               FROM process_steps st JOIN processes p ON p.id = st.process_id JOIN documents d ON d.id = p.document_id
               WHERE d.status = 'YURURLUKTE' AND (st.responsible_entity_id = ? OR st.approver_entity_id = ?)
               ORDER BY st.id""", (role_id, role_id)):
        if _verify_against_doc(ctx, r["doc_id"], None, r["quote"]):
            return _evidence(r, f"{r['pcode']} adım {r['seq']}", r["quote"])
    for r in ctx.conn.execute(
            """SELECT e.quote, e.document_id AS doc_id, e.section_id, d.code, d.revision
               FROM edges e JOIN documents d ON d.id = e.document_id
               WHERE d.status = 'YURURLUKTE' AND e.dst_kind = 'VARLIK' AND e.dst_id = ? AND e.quote IS NOT NULL
                     AND e.review_status != 'REDDEDILDI'
               ORDER BY e.id""", (role_id,)):
        if _verify_against_doc(ctx, r["doc_id"], r["section_id"], r["quote"]):
            return _evidence(r, None, r["quote"], r["section_id"])
    return None


def _role_catalog_rows(ctx: Context) -> list:
    return ctx.conn.execute(
        "SELECT id, canonical_name FROM entities WHERE entity_type = 'ROL' ORDER BY canonical_name").fetchall()


def _belirsiz_rol(check: str, r, explanation_suffix: str) -> Finding:
    """Rol kataloğa kayıtlı ama doğrulanabilir hiçbir alıntı bulunamadı: kanıtsız bulgu üretmek yerine
    BELIRSIZLIK'e düşürülür (değişmez 1), evidence boş kalır — bu, bilinçli 'kaynak yok' durumudur."""
    return Finding(
        check=check, finding_type=FindingType.BELIRSIZLIK, severity=Severity.DUSUK,
        title=f"'{r['canonical_name']}': kaynağı izlenemeyen rol",
        explanation=(f"'{r['canonical_name']}' entities tablosunda ROL olarak kayıtlı, ama yürürlükteki hiçbir "
                     "kuralın/süreç adımının/doküman-varlık ilişkisinin doğrulanabilir bir alıntısında geçmiyor "
                     f"— {explanation_suffix} bu bulgunun doğrulanmış bir kaynağı yok, yalnız DB katalog kaydı."),
        recommendation="Rolün hangi dokümandan/çıkarımdan geldiği elle doğrulanmalı.",
        evidence=[], key=f"{check}_belirsiz|{r['id']}",
    )


# ---- 4a. Görev tanımı olmayan rol (BOSLUK/BELIRSIZLIK, DUSUK) ---------------------------------------------------

def _strip_gorev_suffix(title: str) -> str:
    f = fold(title)
    f = re.sub(r"\bgorev\s*tanimi\b", " ", f)
    f = re.sub(r"\bis\s*tanimi\b", " ", f)
    return re.sub(r"\s+", " ", f).strip(" -:")


def check_gorev_tanimi_eksik(ctx: Context) -> CheckOutcome:
    gorev_docs = [d for d in ctx.docs.values() if d["doc_type"] == "GOREV_TANIMI" and d["status"] == "YURURLUKTE"]
    covered: set[int] = set()
    for d in gorev_docs:
        stripped = _strip_gorev_suffix(d["title"] or "")
        if not stripped:
            continue
        m = ctx.roles.resolve(stripped)
        if m.resolved and m.entity_type == "ROL":
            covered.add(m.entity_id)
    roles = _role_catalog_rows(ctx)
    findings: list[Finding] = []
    for r in roles:
        if r["id"] in covered:
            continue
        ev = _role_evidence(ctx, r["id"])
        if ev is None:
            findings.append(_belirsiz_rol("gorev_tanimi_eksik", r, "görev tanımı da bulunamadı."))
            continue
        findings.append(Finding(
            check="gorev_tanimi_eksik", finding_type=FindingType.BOSLUK, severity=Severity.DUSUK,
            title=f"'{r['canonical_name']}' için görev tanımı bulunamadı",
            explanation=(f"Sistemde '{r['canonical_name']}' rolüne karşılık gelen, yürürlükte bir GOREV_TANIMI "
                         "dokümanı bulunamadı (doküman başlığı role çözümlenerek aranır; başlık yazımı farklıysa "
                         "yanlış pozitif olabilir)."),
            recommendation="Bu rol için görev tanımı dokümanı hazırlanmalı veya mevcut dokümanın başlığı/kodu kontrol edilmeli.",
            evidence=[ev],
            key=f"gorev_eksik|{r['id']}",
        ))
    return CheckOutcome(findings, considered=len(roles))


# ---- 4b. Hiçbir süreç adımında/kuralda geçmeyen rol (BOSLUK/BELIRSIZLIK, DUSUK) ----------------------------------

def check_rol_kullanilmiyor(ctx: Context) -> CheckOutcome:
    used: set[int] = set()
    for row in ctx.conn.execute(
            """SELECT ru.subject_entity_id AS a, ru.object_entity_id AS b FROM rules ru
               JOIN documents d ON d.id = ru.document_id WHERE d.status = 'YURURLUKTE'"""):
        used.add(row["a"]); used.add(row["b"])
    for row in ctx.conn.execute(
            """SELECT st.responsible_entity_id AS a, st.approver_entity_id AS b FROM process_steps st
               JOIN processes p ON p.id = st.process_id JOIN documents d ON d.id = p.document_id
               WHERE d.status = 'YURURLUKTE'"""):
        used.add(row["a"]); used.add(row["b"])
    used.discard(None)
    roles = _role_catalog_rows(ctx)
    findings: list[Finding] = []
    for r in roles:
        if r["id"] in used:
            continue
        # `used` zaten kural/adım eşleşmesini dışladığı için `_role_evidence` burada ancak doküman↔varlık
        # kenarından (edges) bir iz bulabilir; rules/process_steps yolları yapı itibarıyla boş döner.
        ev = _role_evidence(ctx, r["id"])
        if ev is None:
            findings.append(_belirsiz_rol("rol_kullanilmiyor", r, "kural/adım bağlantısı da yok."))
            continue
        findings.append(Finding(
            check="rol_kullanilmiyor", finding_type=FindingType.BOSLUK, severity=Severity.DUSUK,
            title=f"'{r['canonical_name']}' rolü hiçbir kuralın öznesi/nesnesi ya da adımın sorumlusu/onaycısı değil",
            explanation=(f"'{r['canonical_name']}' varlığı bir dokümanda (kanıta bakın) geçiyor, ama yürürlükteki "
                         "hiçbir kuralın öznesi/nesnesi ya da süreç adımının sorumlusu/onaycısı olarak "
                         "bağlanmamış."),
            recommendation="Rol gerçekten kullanılıyorsa ilgili kural/adıma bağlanmalı; kullanılmıyorsa katalogdan çıkarılmalı.",
            evidence=[ev],
            key=f"rol_kullanilmiyor|{r['id']}",
        ))
    return CheckOutcome(findings, considered=len(roles))


# ---- 5. Aynı özne + aynı tür (ESIK/SURE) için çakışan değer (CAKISMA) -------------------------------------------

def check_esik_cakismasi(ctx: Context, object_sim_min: float = 0.4) -> CheckOutcome:
    from ..ontology import ReviewStatus
    from ..process.quantity import Quantity, canonical_unit, compare
    rows = ctx.conn.execute(
        """SELECT r.id, r.subject_entity_id, r.rule_type, r.object_text, r.threshold_op, r.threshold_value,
                  r.threshold_unit, r.quote, r.clause_no, r.review_status, d.code, d.revision
           FROM rules r JOIN documents d ON d.id = r.document_id
           WHERE d.status = 'YURURLUKTE' AND r.rule_type IN ('ESIK', 'SURE') AND r.subject_entity_id IS NOT NULL
                 AND r.review_status != ? AND r.threshold_value IS NOT NULL""",
        (ReviewStatus.REDDEDILDI.value,)).fetchall()
    items = []
    for r in rows:
        unit = canonical_unit(r["threshold_unit"]) or r["threshold_unit"]
        if not unit:
            continue
        items.append({"row": r, "q": Quantity(r["threshold_op"] or "=", float(r["threshold_value"]), unit),
                      "topic": _topic_tokens(r["object_text"])})
    groups: dict[tuple, list] = defaultdict(list)
    for it in items:
        groups[(it["row"]["subject_entity_id"], it["row"]["rule_type"])].append(it)
    findings: list[Finding] = []
    seen: set[tuple] = set()
    for members in groups.values():
        for a, b in combinations(members, 2):
            if a["topic"] or b["topic"]:
                sim = _jaccard(a["topic"], b["topic"])
            else:
                sim = 1.0   # ikisi de konu metni vermiyor: aynı özne + aynı tür yeterli aday sayılır
            if sim < object_sim_min:
                continue
            if compare(a["q"], b["q"]) != "FARKLI":
                continue
            ra, rb = a["row"], b["row"]
            pair = tuple(sorted((ra["id"], rb["id"])))
            if pair in seen:
                continue
            seen.add(pair)
            role_name = ctx.roles.entities.get(ra["subject_entity_id"], (None, None))[0] or "?"
            unverified = ReviewStatus(ra["review_status"]) == ReviewStatus.ONERILDI or \
                ReviewStatus(rb["review_status"]) == ReviewStatus.ONERILDI
            severity = Severity.KRITIK if a["q"].dim.startswith("PARA") else Severity.ORTA
            findings.append(Finding(
                check="esik_cakismasi", finding_type=FindingType.CAKISMA, severity=severity,
                title=f"'{role_name}' için farklı {ra['rule_type'].lower()} değerleri: {a['q']} ↔ {b['q']}",
                explanation=(f"{ra['code']} Rev.{ra['revision']} md.{ra['clause_no'] or '-'} '{a['q']}' derken, "
                             f"{rb['code']} Rev.{rb['revision']} md.{rb['clause_no'] or '-'} aynı özne ve benzer "
                             f"konu için '{b['q']}' diyor."),
                recommendation="Hangi değerin güncel/doğru olduğu belirlenip diğer doküman güncellenmeli.",
                evidence=[_evidence(ra, ra["clause_no"], ra["quote"]), _evidence(rb, rb["clause_no"], rb["quote"])],
                unverified_basis=unverified,
                key=f"esik|{pair[0]}|{pair[1]}",
            ))
    return CheckOutcome(findings, considered=len(items))


# ---- 6. Mükerrer/kopya doküman (CAKISMA) ------------------------------------------------------------------------

def check_mukerrer_dokuman(ctx: Context, threshold: float = 0.6, k: int = 6, min_words: int = 40) -> CheckOutcome:
    docs = [d for d in ctx.docs.values()
            if d["status"] == "YURURLUKTE" and len(fold(d["body_text"] or "").split()) >= min_words]
    shingles = {d["id"]: _shingles(d["body_text"], k) for d in docs}
    findings: list[Finding] = []
    considered = 0
    for a, b in combinations(docs, 2):
        considered += 1
        sim = _jaccard(shingles[a["id"]], shingles[b["id"]])
        if sim < threshold:
            continue
        qa, qb = _longest_common_quote(a["body_text"], b["body_text"])
        if not qa or not qb:
            continue
        same_type = a["doc_type"] == b["doc_type"]
        note = "" if same_type else " Doküman tipleri farklı; mükerrer olmayabilir, elle kontrol edin."
        findings.append(Finding(
            check="mukerrer_dokuman", finding_type=FindingType.CAKISMA, severity=Severity.ORTA,
            title=f"{a['code']} Rev.{a['revision']} ve {b['code']} Rev.{b['revision']} metni neredeyse aynı (%{sim * 100:.0f})",
            explanation=(f"{a['code']} ve {b['code']} aynı anda yürürlükte; gövde metinlerinin kelime-shingle "
                         f"benzerliği %{sim * 100:.0f} (eşik %{threshold * 100:.0f}). İkisi birbirinden bağımsız "
                         "talimat/prosedür gibi duruyor; biri diğerinin kopyası olabilir, ileride ayrı ayrı "
                         "güncellenip çelişmeleri riski var." + note),
            recommendation="İkisinden biri yürürlükten kaldırılmalı veya tek dokümanda birleştirilmeli.",
            evidence=[_evidence(a, None, qa), _evidence(b, None, qb)],
            key=f"mukerrer|{min(a['id'], b['id'])}|{max(a['id'], b['id'])}",
        ))
    return CheckOutcome(findings, considered=considered)


# ---- 7. Karar envanteri sahibi ↔ ONAY/YETKI kural rolü uyumsuzluğu (YETKI_ASIMI) --------------------------------

def check_karar_yetki(ctx: Context) -> CheckOutcome:
    total = ctx.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    if not total:
        return CheckOutcome(findings=[], considered=0, note="decisions tablosu boş; kontrol atlandı (veri yok).")
    rows = ctx.conn.execute(
        """SELECT dc.id, dc.code, dc.title, dc.owner_entity_id, dc.basis_document_id, dc.basis_clause_no,
                  d.code AS doc_code, d.revision AS doc_revision, d.status AS doc_status
           FROM decisions dc LEFT JOIN documents d ON d.id = dc.basis_document_id"""
    ).fetchall()
    findings: list[Finding] = []
    considered = 0
    for dc in rows:
        if not dc["basis_document_id"] or not dc["owner_entity_id"] or dc["doc_status"] != "YURURLUKTE":
            continue
        considered += 1
        rule_rows = ctx.conn.execute(
            """SELECT id, subject_entity_id, clause_no, quote, review_status FROM rules
               WHERE document_id = ? AND rule_type IN ('ONAY', 'YETKI')""", (dc["basis_document_id"],)).fetchall()
        if dc["basis_clause_no"]:
            scoped = [r for r in rule_rows if r["clause_no"] and (
                r["clause_no"] == dc["basis_clause_no"] or r["clause_no"].startswith(dc["basis_clause_no"] + "."))]
            rule_rows = scoped or rule_rows
        if not rule_rows or any(r["subject_entity_id"] == dc["owner_entity_id"] for r in rule_rows):
            continue   # dayanak yok ya da sahip zaten doğrulandı: bulgu değil
        conflicting = [r for r in rule_rows if r["subject_entity_id"]]
        if not conflicting:
            continue
        r = conflicting[0]
        owner_name = ctx.roles.entities.get(dc["owner_entity_id"], (None, None))[0] or "?"
        rule_role = ctx.roles.entities.get(r["subject_entity_id"], (None, None))[0] or "?"
        from ..ontology import ReviewStatus
        findings.append(Finding(
            check="karar_yetki", finding_type=FindingType.YETKI_ASIMI, severity=Severity.KRITIK,
            title=f"Karar '{dc['title'] or dc['code']}': sahip '{owner_name}', dokümandaki yetkili '{rule_role}'",
            explanation=(f"Karar envanterinde bu kararı '{owner_name}' veriyor; ancak dayanak {dc['doc_code']} "
                         f"Rev.{dc['doc_revision']} md.{r['clause_no'] or '-'}'deki ONAY/YETKI kuralının öznesi "
                         f"'{rule_role}'."),
            recommendation="Karar envanterindeki sahip veya dokümandaki yetki kuralı güncellenmeli; ikisi aynı rolü göstermeli.",
            evidence=[_evidence({"code": dc["doc_code"], "revision": dc["doc_revision"]}, r["clause_no"], r["quote"])],
            unverified_basis=ReviewStatus(r["review_status"]) == ReviewStatus.ONERILDI,
            key=f"karar_yetki|{dc['id']}|{r['id']}",
        ))
    return CheckOutcome(findings, considered=considered)


CHECK_REGISTRY: dict[str, Callable[[Context], CheckOutcome]] = {
    "guncellik_atif": check_guncellik_atif,
    "kirik_referans": check_kirik_referans,
    "adim_sorumlusu": check_adim_sorumlusu,
    "gorev_tanimi_eksik": check_gorev_tanimi_eksik,
    "rol_kullanilmiyor": check_rol_kullanilmiyor,
    "esik_cakismasi": check_esik_cakismasi,
    "mukerrer_dokuman": check_mukerrer_dokuman,
    "karar_yetki": check_karar_yetki,
}


def run_checks(conn, codes: list[str] | None = None) -> dict[str, CheckOutcome]:
    """Seçilen (yoksa tüm) kontrolleri çalıştırır. DB'ye yazmaz."""
    names = codes or list(CHECK_REGISTRY)
    unknown = [n for n in names if n not in CHECK_REGISTRY]
    if unknown:
        raise ValueError(f"Bilinmeyen kontrol adı: {', '.join(unknown)}. Geçerli adlar: {', '.join(CHECK_REGISTRY)}")
    ctx = Context(conn)
    return {name: CHECK_REGISTRY[name](ctx) for name in names}
