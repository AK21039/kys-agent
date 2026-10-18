"""retrieval.py ve search_eval.py testleri.

Gerçek şirket dokümanı fixture olarak kullanılmaz (CLAUDE.md değişmez 8); senaryolar burada
doğrudan documents/sections tablolarına INSERT edilerek üretilir (ingest hattından bağımsız,
hızlı ve deterministik).
"""

import sqlite3

from kys.query import retrieval, search_eval
from kys.textnorm import fold


def _add_doc(conn: sqlite3.Connection, code: str, title: str, sections: list[tuple[str | None, str, str]],
             doc_type: str = "TALIMAT") -> int:
    """`sections`: (clause_no, heading, text) üçlüleri. search_text = fold(heading + text) (pipeline.py ile aynı kural)."""
    doc_id = conn.execute(
        """INSERT INTO documents(code, code_key, revision, title, doc_type, status, body_text, file_path,
                                 file_sha256, meta_source)
           VALUES (?, ?, '00', ?, ?, 'YURURLUKTE', ?, 'test.docx', ?, 'kullanici')""",
        (code, code.lower(), title, doc_type, title, f"sha-{code}"),
    ).lastrowid
    for i, (clause_no, heading, text) in enumerate(sections):
        conn.execute(
            """INSERT INTO sections(document_id, ordinal, clause_no, heading, heading_path, text, search_text)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, i, clause_no, heading, heading, text, fold(f"{heading or ''} {text}")),
        )
    conn.commit()
    return doc_id


def _seed_ambiguous_kaynak(conn: sqlite3.Connection) -> None:
    """'Kaynak' çok anlamlılığını taklit eden sentetik korpus: kaynak işi (weld) vs. gürültü.

    DOC_WELD: "kaynak" bağlam terimiyle (izin) YAKIN geçer — gerçek hedef.
    DOC_NOISE: "kaynak" çok daha SIK geçer (bm25 ham sıklıkla bu dokümanı öne çıkarabilir) ama
    hep "kaynaklı/kaynaklanan" gibi ilgisiz biçimlerde ve bağlam teriminden UZAKTA — trigram alt
    dizge eşleşmesinin yakalayıp bm25'in ayırt edemediği gürültü biçimi.
    DOC_HR: "kaynak" bambaşka bir anlamda (insan kaynakları) ve sorudaki diğer terimlerle hiç
    örtüşmüyor — ilgisiz bir üçüncü anlam için negatif kontrol.
    """
    _add_doc(conn, "T-WELD", "Kaynak Makinası Kullanma Talimatı", [
        ("1", "Genel Kurallar",
         "Kaynak yapmadan önce iş güvenliği uzmanından izin alınır. Aksi halde kaynak makinesi çalıştırılmaz."),
    ])
    noise_text = (
        "İş kazalarının çoğu ortam kaynaklı risklerden kaynaklanır. Ekipmandan kaynaklanan arızalar, "
        "elektromekanik parçalardan kaynaklanan gürültü, nemden kaynaklanan paslanma ve bakımdan kaynaklanan "
        "duruşlar ayrı ayrı değerlendirilir. " + ("Dolgu metni tekrarlanır. " * 20) +
        "Bu bölümün sonunda izin ve onay süreçleri başka bir prosedürde ayrıca tanımlanmıştır."
    )
    _add_doc(conn, "T-NOISE", "Genel Risk Değerlendirme Talimatı", [(None, None, noise_text)])
    _add_doc(conn, "T-HR", "İnsan Kaynakları Organizasyon Şeması", [
        ("1", "Birimler", "İnsan kaynakları birimi personel özlük işlerinden sorumludur."),
    ])


def test_ambiguous_term_with_context_ranks_above_noise(conn):
    """'Kaynak' + bağlam (izin) sorusu, kaynak+izin YAKIN geçen bölümü; sadece 'kaynak' sıklığı
    yüksek ama bağlamdan uzak olan gürültü dokümanının ÖNÜNE taşımalı (hit@1)."""
    _seed_ambiguous_kaynak(conn)
    rows = retrieval.retrieve(conn, "Kaynak yapmak için kimden izin alınır?", limit=5)
    assert rows, "sonuç boş olmamalı"
    assert rows[0]["code"] == "T-WELD"
    codes = [r["code"] for r in rows]
    assert codes.index("T-WELD") < codes.index("T-NOISE")


def test_plain_query_regression(conn):
    """Çok anlamlılık içermeyen düz bir soru, hâlâ doğru dokümanı ilk sırada getirmeli (yeniden
    sıralama düz sorguları bozmamalı)."""
    _add_doc(conn, "T-DRILL", "Matkap Tezgahı Kullanma Talimatı", [
        ("4", "Kullanım", "Delik açılacak yüzey ile matkap ucu ekseni arasının 90 derecelik açı yapmasına dikkat et."),
    ])
    _add_doc(conn, "T-OTHER", "Forklift Kullanma Talimatı", [
        ("1", "Kullanım", "Forklift çalıştırılmadan önce günlük kontrol listesi doldurulur."),
    ])
    rows = retrieval.retrieve(conn, "Matkap tezgahı kullanırken nelere dikkat edilir?", limit=5)
    assert rows and rows[0]["code"] == "T-DRILL"


def test_turkish_folding_matches_ascii_typed_query(conn):
    """Türkçe karaktersiz yazılan sorgu, Türkçe karakterli başlık/metinle eşleşmeli (textnorm.fold)."""
    _add_doc(conn, "T-FOLD", "Çağrı ve İşletme Güvenliği Talimatı", [
        ("1", "Giriş Çıkış", "Taşeronlar işletmeye girişte güvenlik kartı ibraz eder."),
    ])
    rows = retrieval.retrieve(conn, "tasoronlar isletmeye giriste ne ibraz eder", limit=5)
    assert rows and rows[0]["code"] == "T-FOLD"


def test_heading_match_bonus_breaks_ties_toward_on_topic_section(conn):
    """Soru terimleri madde başlığında geçen bölüm, aynı terimleri sadece gövdede taşıyan ama
    konu dışı bir bölümün önüne geçmeli (başlık/doküman başlığı bonusu)."""
    _add_doc(conn, "T-WELD2", "Kaynak Makinası Kullanma Talimatı", [
        ("2", "Koruyucu Ekipman", "Kaynak yaparken mutlaka gözlük ve koruyucu siper kullanılmalıdır."),
    ])
    _add_doc(conn, "T-UNRELATED", "Genel Talimat", [
        ("9", "Diğer", "Koruyucu ekipman ve gözlük kullanımı diğer tezgahlarda da zorunludur, kaynak değildir."),
    ])
    rows = retrieval.retrieve(conn, "Kaynak makinesi kullanırken hangi koruyucu ekipmanlar giyilmelidir?", limit=5)
    assert rows[0]["code"] == "T-WELD2"


# --- search_eval.py: saf metrik hesaplama -----------------------------------------------------

def test_hit_at_k_and_mrr_pure_computation():
    sorular = [
        search_eval.SoruSonucu(id="a", soru="x", cok_anlamli=True, beklenen_kodlar=["A"],
                                bulunan_kodlar=["A"], ilk_isabet_rutbe=1),
        search_eval.SoruSonucu(id="b", soru="y", cok_anlamli=True, beklenen_kodlar=["B"],
                                bulunan_kodlar=["X", "B"], ilk_isabet_rutbe=2),
        search_eval.SoruSonucu(id="c", soru="z", cok_anlamli=False, beklenen_kodlar=["C"],
                                bulunan_kodlar=["X", "Y", "X", "X", "X", "X", "X", "X", "X", "C"],
                                ilk_isabet_rutbe=10),
        search_eval.SoruSonucu(id="d", soru="w", cok_anlamli=False, beklenen_kodlar=["D"],
                                bulunan_kodlar=["X"], ilk_isabet_rutbe=None),
    ]
    sonuc = search_eval.OlcumSonucu(k=10, sorular=sorular)
    assert sonuc.hit_at(5) == 0.5          # a (rütbe1), b (rütbe2) ⇒ 2/4
    assert sonuc.hit_at(10) == 0.75        # + c (rütbe10) ⇒ 3/4, d hiç bulunamadı
    assert sonuc.mrr() == (1 / 1 + 1 / 2 + 1 / 10 + 0) / 4
    coklu = sonuc.alt_kume(lambda s: s.cok_anlamli)
    assert len(coklu.sorular) == 2 and coklu.hit_at(5) == 1.0


def test_evaluate_query_or_semantics_counts_first_matching_expected_doc(conn):
    """Birden çok beklenen dokümandan BİRİNİN bulunması isabet sayılır (çelişki soruları için)."""
    _seed_ambiguous_kaynak(conn)
    item = {"id": "t1", "soru": "Kaynak yapmak için kimden izin alınır?", "cok_anlamli": True,
            "beklenen": [{"kod": "T-HR"}, {"kod": "T-WELD"}]}
    sonuc = search_eval.evaluate_query(conn, item, k=5)
    assert sonuc.ilk_isabet_rutbe == 1 and sonuc.hit5 and sonuc.hit10
    assert sonuc.beklenen_kodlar == ["T-HR", "T-WELD"]


def test_evaluate_query_no_match_within_k(conn):
    _add_doc(conn, "T-ALONE", "Konu Dışı Talimat", [("1", "Giriş", "Bununla hiç ilgisi olmayan bir metin.")])
    item = {"id": "t2", "soru": "Konu dışı talimat nasıl uygulanır?", "cok_anlamli": False,
            "beklenen": [{"kod": "YOK-DOC"}]}
    sonuc = search_eval.evaluate_query(conn, item, k=5)
    assert sonuc.ilk_isabet_rutbe is None and not sonuc.hit5 and not sonuc.hit10


def test_load_gold_set_file_is_well_formed():
    """Gerçek altın soru seti (data/eval/arama_altin.json) en az 15 soru içerir, her sorunun en
    az bir beklenen dokümanı vardır; şirket verisi testte COMMIT edilmez, sadece okunur."""
    if not search_eval.VARSAYILAN_SET.is_file():
        return  # paylaşımda data/ yoksa (ör. yalnızca kod kopyalandıysa) sessizce atla
    gold = search_eval.load_gold()
    assert len(gold) >= 15
    for item in gold:
        assert item["beklenen"], f"{item['id']}: beklenen doküman boş olamaz"
