"""Faz 3 katman 1 — deterministik (LLM'siz) çelişki/boşluk taramaları. Her kontrol için pozitif + negatif
fixture, fingerprint idempotensi, `--kaydet` yokken DB'nin değişmediği ve ONERILDI kaynağın
`unverified_basis=True` taşıdığı doğrulanır. Gerçek şirket dokümanı fixture edilmez (sentetik kod/ad)."""

from kys.analysis import checks, model, report, store
from kys.ontology import FindingType, Severity
from kys.textnorm import fold, verify_quote


def _doc(conn, id_, code, status="YURURLUKTE", doc_type="PROSEDUR", title=None, body="Gövde metni.", revision="01"):
    from kys.ingest.metadata import code_key
    conn.execute(
        """INSERT INTO documents(id, code, code_key, revision, title, doc_type, status, body_text, file_path,
                                 file_sha256, meta_source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'kullanici')""",
        (id_, code, code_key(code), revision, title or code, doc_type, status, body, f"{code}.docx", f"sha-{id_}"))
    return id_


def _section(conn, id_, document_id, text, clause_no=None, heading=None, ordinal=1):
    conn.execute(
        """INSERT INTO sections(id, document_id, ordinal, clause_no, heading, text, search_text)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (id_, document_id, ordinal, clause_no, heading, text, fold(f"{heading or ''} {text}")))
    return id_


def _role(conn, id_, name):
    conn.execute("INSERT INTO entities(id, entity_type, canonical_name, normalized_name) VALUES (?, 'ROL', ?, ?)",
                 (id_, name, fold(name)))
    return id_


# ---- 1. guncellik_atif -------------------------------------------------------------------------------------

def test_guncellik_atif_flags_reference_to_cancelled_doc(conn):
    _doc(conn, 1, "PR-01", body="Satınalma PR-02'ye göre yapılır.")
    _section(conn, 1, 1, "Satınalma PR-02'ye göre yapılır.", clause_no="4.1")
    _doc(conn, 2, "PR-02", status="IPTAL")
    conn.execute("INSERT INTO doc_references(document_id, section_id, ref_code, resolved_doc_id) VALUES (1,1,'PR-02',2)")
    conn.commit()
    outcome = checks.check_guncellik_atif(model.Context(conn))
    assert len(outcome.findings) == 1
    f = outcome.findings[0]
    assert f.finding_type == FindingType.GUNCELLIK and f.severity == Severity.ORTA
    assert verify_quote(f.evidence[0]["quote"], "Satınalma PR-02'ye göre yapılır.")
    assert f.evidence[0]["doc_code"] == "PR-01"


def test_guncellik_atif_negative_when_target_active(conn):
    _doc(conn, 1, "PR-01", body="Satınalma PR-02'ye göre yapılır.")
    _section(conn, 1, 1, "Satınalma PR-02'ye göre yapılır.", clause_no="4.1")
    _doc(conn, 2, "PR-02", status="YURURLUKTE")
    conn.execute("INSERT INTO doc_references(document_id, section_id, ref_code, resolved_doc_id) VALUES (1,1,'PR-02',2)")
    conn.commit()
    outcome = checks.check_guncellik_atif(model.Context(conn))
    assert outcome.findings == []


def test_fingerprint_stable_across_reruns(conn):
    _doc(conn, 1, "PR-01", body="Satınalma PR-02'ye göre yapılır.")
    _section(conn, 1, 1, "Satınalma PR-02'ye göre yapılır.", clause_no="4.1")
    _doc(conn, 2, "PR-02", status="IPTAL")
    conn.execute("INSERT INTO doc_references(document_id, section_id, ref_code, resolved_doc_id) VALUES (1,1,'PR-02',2)")
    conn.commit()
    a = checks.check_guncellik_atif(model.Context(conn)).findings[0].fingerprint()
    b = checks.check_guncellik_atif(model.Context(conn)).findings[0].fingerprint()
    assert a == b


# ---- 2. kirik_referans --------------------------------------------------------------------------------------

def test_kirik_referans_detects_missing_code(conn):
    _doc(conn, 1, "PR-01", body="Bakım PR-99'a göre yapılır.")
    _section(conn, 1, 1, "Bakım PR-99'a göre yapılır.", clause_no="5.1")
    conn.execute("INSERT INTO doc_references(document_id, section_id, ref_code, resolved_doc_id) VALUES (1,1,'PR-99',NULL)")
    conn.commit()
    outcome = checks.check_kirik_referans(model.Context(conn))
    assert len(outcome.findings) == 1
    assert outcome.findings[0].finding_type == FindingType.BOSLUK


def test_kirik_referans_ignores_non_code_like_ref(conn):
    _doc(conn, 1, "PR-01", body="Hat TECOM-1 durdu.")
    _section(conn, 1, 1, "Hat TECOM-1 durdu.", clause_no="5.1")
    conn.execute("INSERT INTO doc_references(document_id, section_id, ref_code, resolved_doc_id) VALUES (1,1,'TECOM-1',NULL)")
    conn.commit()
    outcome = checks.check_kirik_referans(model.Context(conn))
    assert outcome.findings == []


# ---- 3. adim_sorumlusu --------------------------------------------------------------------------------------

def test_adim_sorumlusu_missing_responsible(conn):
    _doc(conn, 1, "PR-10")
    conn.execute("INSERT INTO processes(id, code, name, document_id) VALUES (1,'SUR-1','Satınalma',1)")
    conn.execute(
        """INSERT INTO process_steps(id, process_id, seq, name, description, quote)
           VALUES (1, 1, 1, 'Talep oluştur', 'Talep oluşturulur.', 'Talep oluşturulur.')""")
    conn.commit()
    outcome = checks.check_adim_sorumlusu(model.Context(conn))
    assert len(outcome.findings) == 1
    assert "sorumlu" in outcome.findings[0].explanation.lower()
    assert outcome.findings[0].severity == Severity.ORTA


def test_adim_sorumlusu_negative_when_defined(conn):
    _doc(conn, 1, "PR-10")
    _role(conn, 1, "Depo Sorumlusu")
    conn.execute("INSERT INTO processes(id, code, name, document_id) VALUES (1,'SUR-1','Satınalma',1)")
    conn.execute(
        """INSERT INTO process_steps(id, process_id, seq, name, description, quote, responsible_entity_id)
           VALUES (1, 1, 1, 'Talep oluştur', 'Talep oluşturulur.', 'Talep oluşturulur.', 1)""")
    conn.commit()
    outcome = checks.check_adim_sorumlusu(model.Context(conn))
    assert outcome.findings == []


def test_adim_sorumlusu_missing_approver_on_decision_step(conn):
    _doc(conn, 1, "PR-10")
    _role(conn, 1, "Depo Sorumlusu")
    conn.execute("INSERT INTO processes(id, code, name, document_id) VALUES (1,'SUR-1','Satınalma',1)")
    conn.execute(
        """INSERT INTO process_steps(id, process_id, seq, name, description, quote, decision, responsible_entity_id)
           VALUES (1, 1, 1, 'Onay ver', '100.000 TL üstü onay gerekir.', '100.000 TL üstü onay gerekir.',
                   'Limit üstü mü?', 1)""")
    conn.commit()
    outcome = checks.check_adim_sorumlusu(model.Context(conn))
    assert len(outcome.findings) == 1 and outcome.findings[0].severity == Severity.DUSUK


# ---- 4a. gorev_tanimi_eksik ---------------------------------------------------------------------------------

def test_gorev_tanimi_eksik_negative_when_title_resolves(conn):
    _role(conn, 1, "Satınalma Müdürü")
    _doc(conn, 1, "GT-01", doc_type="GOREV_TANIMI", title="Satınalma Müdürü Görev Tanımı")
    conn.commit()
    outcome = checks.check_gorev_tanimi_eksik(model.Context(conn))
    assert outcome.findings == []


def test_gorev_tanimi_eksik_falls_back_to_belirsizlik_without_any_trace(conn):
    """Rol hiçbir kuralda/adımda/kenarda geçmiyor: kanıtsız BOSLUK üretilmez, BELIRSIZLIK'e düşer (değişmez 1)."""
    _role(conn, 1, "Hayalet Rol")
    conn.commit()
    outcome = checks.check_gorev_tanimi_eksik(model.Context(conn))
    assert len(outcome.findings) == 1
    f = outcome.findings[0]
    assert f.finding_type == FindingType.BELIRSIZLIK and f.evidence == []
    assert "kaynağı izlenemeyen" in f.title


def test_gorev_tanimi_eksik_uses_rule_quote_as_verified_evidence(conn):
    """GOREV_TANIMI dokümanı yok, ama rol başka bir kuralın öznesi: BOSLUK, kanıt o kuralın (doğrulanmış) alıntısı."""
    _doc(conn, 1, "PR-01", body="Satınalma Müdürü talebi onaylar.")
    _section(conn, 1, 1, "Satınalma Müdürü talebi onaylar.", clause_no="4.2")
    _role(conn, 1, "Satınalma Müdürü")
    conn.execute(
        """INSERT INTO rules(document_id, section_id, rule_type, statement, subject_entity_id, quote, clause_no)
           VALUES (1, 1, 'ONAY', 'Satınalma Müdürü talebi onaylar.', 1, 'Satınalma Müdürü talebi onaylar.', '4.2')""")
    conn.commit()
    outcome = checks.check_gorev_tanimi_eksik(model.Context(conn))
    assert len(outcome.findings) == 1
    f = outcome.findings[0]
    assert f.finding_type == FindingType.BOSLUK and len(f.evidence) == 1
    assert verify_quote(f.evidence[0]["quote"], "Satınalma Müdürü talebi onaylar.")
    assert f.evidence[0]["doc_code"] == "PR-01"


# ---- 4b. rol_kullanilmiyor ----------------------------------------------------------------------------------

def test_rol_kullanilmiyor_falls_back_to_belirsizlik_without_any_trace(conn):
    _role(conn, 1, "Hayalet Rol")
    conn.commit()
    outcome = checks.check_rol_kullanilmiyor(model.Context(conn))
    assert len(outcome.findings) == 1
    f = outcome.findings[0]
    assert f.finding_type == FindingType.BELIRSIZLIK and f.evidence == []
    assert "kaynağı izlenemeyen" in f.title


def test_rol_kullanilmiyor_negative_when_used_in_rule(conn):
    _doc(conn, 1, "PR-01")
    _role(conn, 1, "Kullanılan Rol")
    conn.execute(
        """INSERT INTO rules(document_id, rule_type, statement, subject_entity_id, quote)
           VALUES (1, 'SORUMLULUK', 'Kullanılan Rol kaydı tutar.', 1, 'Kullanılan Rol kaydı tutar.')""")
    conn.commit()
    outcome = checks.check_rol_kullanilmiyor(model.Context(conn))
    assert outcome.findings == []


def test_rol_kullanilmiyor_uses_edge_quote_as_verified_evidence(conn):
    """Rol hiçbir kuralın/adımın öznesi değil ama bir doküman-varlık kenarında (ör. ExReference) geçiyor:
    BOSLUK, kanıt o kenarın (doğrulanmış) alıntısı — kanıtsız bulgu yok."""
    _doc(conn, 1, "PR-01", body="Bakım işlerinde Harici Denetçi'ye danışılır.")
    _section(conn, 1, 1, "Bakım işlerinde Harici Denetçi'ye danışılır.", clause_no="6.1")
    _role(conn, 1, "Harici Denetçi")
    conn.execute(
        """INSERT INTO edges(src_kind, src_id, rel_type, dst_kind, dst_id, document_id, section_id, quote)
           VALUES ('DOKUMAN', 1, 'KULLANIR', 'VARLIK', 1, 1, 1, 'Harici Denetçi’ye danışılır.')""")
    conn.commit()
    outcome = checks.check_rol_kullanilmiyor(model.Context(conn))
    assert len(outcome.findings) == 1
    f = outcome.findings[0]
    assert f.finding_type == FindingType.BOSLUK and len(f.evidence) == 1
    assert verify_quote(f.evidence[0]["quote"], "Bakım işlerinde Harici Denetçi'ye danışılır.")


# ---- 5. esik_cakismasi --------------------------------------------------------------------------------------

def _esik_rule(conn, id_, document_id, subject_entity_id, value, object_text="satınalma talebi", clause_no="4.2",
              review_status="ONAYLANDI", quote=None):
    quote = quote or f"{object_text} {value:.0f} TL üstü onaylanır."
    conn.execute(
        """INSERT INTO rules(id, document_id, rule_type, statement, subject_entity_id, object_text,
                             threshold_op, threshold_value, threshold_unit, quote, clause_no, review_status)
           VALUES (?, ?, 'ESIK', 'esik', ?, ?, '>', ?, 'TRY', ?, ?, ?)""",
        (id_, document_id, subject_entity_id, object_text, value, quote, clause_no, review_status))


def test_esik_cakismasi_conflicting_threshold(conn):
    _doc(conn, 1, "PR-01"); _doc(conn, 2, "PR-02")
    _role(conn, 1, "Genel Müdür")
    _esik_rule(conn, 1, 1, 1, 100000)
    _esik_rule(conn, 2, 2, 1, 250000, clause_no="3.1")
    conn.commit()
    outcome = checks.check_esik_cakismasi(model.Context(conn))
    assert len(outcome.findings) == 1
    f = outcome.findings[0]
    assert f.finding_type == FindingType.CAKISMA and f.severity == Severity.KRITIK  # PARA boyutu
    assert len(f.evidence) == 2 and not f.unverified_basis


def test_esik_cakismasi_negative_same_value(conn):
    _doc(conn, 1, "PR-01"); _doc(conn, 2, "PR-02")
    _role(conn, 1, "Genel Müdür")
    _esik_rule(conn, 1, 1, 1, 100000)
    _esik_rule(conn, 2, 2, 1, 100000, clause_no="3.1")
    conn.commit()
    outcome = checks.check_esik_cakismasi(model.Context(conn))
    assert outcome.findings == []


def test_esik_cakismasi_negative_unrelated_topic(conn):
    _doc(conn, 1, "PR-01"); _doc(conn, 2, "PR-02")
    _role(conn, 1, "Genel Müdür")
    _esik_rule(conn, 1, 1, 1, 100000, object_text="satınalma talebi")
    _esik_rule(conn, 2, 2, 1, 250000, object_text="seyahat avansı", clause_no="3.1")
    conn.commit()
    outcome = checks.check_esik_cakismasi(model.Context(conn))
    assert outcome.findings == []


def test_esik_cakismasi_unverified_when_onerildi(conn):
    _doc(conn, 1, "PR-01"); _doc(conn, 2, "PR-02")
    _role(conn, 1, "Genel Müdür")
    _esik_rule(conn, 1, 1, 1, 100000, review_status="ONAYLANDI")
    _esik_rule(conn, 2, 2, 1, 250000, clause_no="3.1", review_status="ONERILDI")
    conn.commit()
    outcome = checks.check_esik_cakismasi(model.Context(conn))
    assert len(outcome.findings) == 1 and outcome.findings[0].unverified_basis


# ---- 6. mukerrer_dokuman ------------------------------------------------------------------------------------

def test_mukerrer_dokuman_detects_near_duplicate(conn):
    body = " ".join(["Bu bir test cümlesidir ve tekrarlanan metin parçası oluşturur"] * 10)
    _doc(conn, 1, "ME-TL-001", body=body)
    _doc(conn, 2, "YP-TL-001", body=body)
    conn.commit()
    outcome = checks.check_mukerrer_dokuman(model.Context(conn))
    assert len(outcome.findings) == 1
    f = outcome.findings[0]
    assert f.finding_type == FindingType.CAKISMA
    assert verify_quote(f.evidence[0]["quote"], body) and verify_quote(f.evidence[1]["quote"], body)


def test_mukerrer_dokuman_negative_when_different(conn):
    _doc(conn, 1, "ME-TL-002", body=" ".join(["Alfa metni tamamen farklı bir konu anlatıyor burada"] * 10))
    _doc(conn, 2, "YP-TL-002", body=" ".join(["Beta konusu bambaşka bir süreci tarif ediyor burada"] * 10))
    conn.commit()
    outcome = checks.check_mukerrer_dokuman(model.Context(conn))
    assert outcome.findings == []


# ---- 7. karar_yetki ------------------------------------------------------------------------------------------

def test_karar_yetki_no_data_reports_note(conn):
    outcome = checks.check_karar_yetki(model.Context(conn))
    assert outcome.findings == [] and outcome.note and "veri yok" in outcome.note


def test_karar_yetki_flags_owner_mismatch(conn):
    _doc(conn, 1, "PR-01")
    _role(conn, 1, "Genel Müdür")
    _role(conn, 2, "Satınalma Müdürü")
    conn.execute(
        """INSERT INTO rules(id, document_id, rule_type, statement, subject_entity_id, quote, clause_no, review_status)
           VALUES (1, 1, 'ONAY', 'Genel Müdür onaylar', 1, 'Genel Müdür onaylar.', '4.2', 'ONAYLANDI')""")
    conn.execute(
        """INSERT INTO decisions(id, code, title, owner_entity_id, basis_document_id, basis_clause_no)
           VALUES (1, 'K-1', 'Satınalma onayı', 2, 1, '4.2')""")
    conn.commit()
    outcome = checks.check_karar_yetki(model.Context(conn))
    assert len(outcome.findings) == 1 and outcome.findings[0].finding_type == FindingType.YETKI_ASIMI


def test_karar_yetki_negative_when_owner_matches(conn):
    _doc(conn, 1, "PR-01")
    _role(conn, 1, "Genel Müdür")
    conn.execute(
        """INSERT INTO rules(id, document_id, rule_type, statement, subject_entity_id, quote, clause_no, review_status)
           VALUES (1, 1, 'ONAY', 'Genel Müdür onaylar', 1, 'Genel Müdür onaylar.', '4.2', 'ONAYLANDI')""")
    conn.execute(
        """INSERT INTO decisions(id, code, title, owner_entity_id, basis_document_id, basis_clause_no)
           VALUES (1, 'K-1', 'Satınalma onayı', 1, 1, '4.2')""")
    conn.commit()
    outcome = checks.check_karar_yetki(model.Context(conn))
    assert outcome.findings == []


# ---- çalıştırıcı / depolama / rapor ---------------------------------------------------------------------------

def test_run_checks_rejects_unknown_name(conn):
    import pytest
    with pytest.raises(ValueError):
        checks.run_checks(conn, ["yok_boyle_bir_kontrol"])


def test_run_checks_without_kaydet_does_not_write_db(conn):
    _doc(conn, 1, "PR-01", body="Satınalma PR-02'ye göre yapılır.")
    _section(conn, 1, 1, "Satınalma PR-02'ye göre yapılır.", clause_no="4.1")
    _doc(conn, 2, "PR-02", status="IPTAL")
    conn.execute("INSERT INTO doc_references(document_id, section_id, ref_code, resolved_doc_id) VALUES (1,1,'PR-02',2)")
    conn.commit()
    outcomes = checks.run_checks(conn, ["guncellik_atif"])
    assert outcomes["guncellik_atif"].findings
    assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0] == 0


def test_save_findings_upserts_by_fingerprint_and_preserves_status(conn):
    _doc(conn, 1, "PR-01", body="Satınalma PR-02'ye göre yapılır.")
    _section(conn, 1, 1, "Satınalma PR-02'ye göre yapılır.", clause_no="4.1")
    _doc(conn, 2, "PR-02", status="IPTAL")
    conn.execute("INSERT INTO doc_references(document_id, section_id, ref_code, resolved_doc_id) VALUES (1,1,'PR-02',2)")
    conn.commit()
    outcomes = checks.run_checks(conn, ["guncellik_atif"])
    res1 = store.save_findings(conn, outcomes)
    assert res1["yeni"] == 1 and res1["guncellenen"] == 0
    row = conn.execute("SELECT id, status FROM findings").fetchone()
    assert row["status"] == "ACIK"
    conn.execute("UPDATE findings SET status = 'COZULDU' WHERE id = ?", (row["id"],))
    conn.commit()
    outcomes2 = checks.run_checks(conn, ["guncellik_atif"])
    res2 = store.save_findings(conn, outcomes2)
    assert res2["yeni"] == 0 and res2["guncellenen"] == 1
    assert conn.execute("SELECT status FROM findings WHERE id = ?", (row["id"],)).fetchone()["status"] == "COZULDU"
    assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 1


def test_render_report_zero_findings_on_empty_db(conn):
    outcomes = checks.run_checks(conn)
    text = report.render_report(outcomes)
    assert "Toplam bulgu: 0" in text
    assert "decisions tablosu boş" in text


def test_no_evidence_free_finding_outside_belirsizlik(conn):
    """Değişmez 1 ("kanıtsız bulgu yok ya da BELİRSİZLİK yap") — karışık bir fixture'da BELIRSIZLIK DIŞINDA hiçbir
    bulgu evidence=[] taşımaz, ve her kanıtın alıntısı kendi doküman/bölüm metnine karşı doğrulanır. Ayrıca
    rapor BELİRSİZLİK'i ayrı bir bölümde sayar."""
    _doc(conn, 1, "PR-01", body="Satınalma Müdürü talebi onaylar.")
    _section(conn, 1, 1, "Satınalma Müdürü talebi onaylar.", clause_no="4.2")
    _role(conn, 1, "Satınalma Müdürü")   # rules.quote üzerinden iz bırakır → BOSLUK
    conn.execute(
        """INSERT INTO rules(document_id, section_id, rule_type, statement, subject_entity_id, quote, clause_no)
           VALUES (1, 1, 'ONAY', 'Satınalma Müdürü talebi onaylar.', 1, 'Satınalma Müdürü talebi onaylar.', '4.2')""")
    _role(conn, 2, "Hayalet Rol")   # hiçbir izi yok → BELIRSIZLIK
    conn.commit()
    outcomes = checks.run_checks(conn, ["gorev_tanimi_eksik", "rol_kullanilmiyor"])
    all_findings = [f for o in outcomes.values() for f in o.findings]
    assert any(f.finding_type == FindingType.BELIRSIZLIK for f in all_findings)
    for f in all_findings:
        if f.finding_type == FindingType.BELIRSIZLIK:
            assert f.evidence == []
        else:
            assert f.evidence, f"{f.check}: BELIRSIZLIK dışı bulgu kanıtsız: {f.title}"
            for ev in f.evidence:
                assert ev.get("quote")
    text = report.render_report(outcomes)
    assert "BELİRSİZLİK" in text and "kaynağı izlenemeyen" in text
