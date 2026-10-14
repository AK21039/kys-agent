-- KYS bilgi tabanı şeması (SQLite; PostgreSQL'e taşınabilir tutulur).
-- Tip/durum değerleri kys/ontology.py'deki enum'lardır.

CREATE TABLE IF NOT EXISTS documents (
    id                INTEGER PRIMARY KEY,
    code              TEXT NOT NULL,              -- PR-04, IK.TL.02 ...
    code_key          TEXT NOT NULL,              -- metadata.code_key(code): 'pr4'
    revision         TEXT NOT NULL DEFAULT '00',
    title             TEXT NOT NULL,
    doc_type          TEXT NOT NULL,              -- DocType
    status            TEXT NOT NULL DEFAULT 'YURURLUKTE',  -- DocStatus
    revision_date     TEXT,                       -- ISO tarih
    effective_date    TEXT,
    owner_unit        TEXT,
    summary           TEXT,
    header_text       TEXT,                       -- üstbilgi (kod/rev tablosu)
    body_text         TEXT NOT NULL,              -- ayrıştırılmış tam metin
    file_path         TEXT NOT NULL,
    file_sha256       TEXT NOT NULL UNIQUE,
    parse_warnings    TEXT,                       -- JSON liste
    meta_source       TEXT NOT NULL,              -- 'regex' | 'llm' | 'kullanici'
    meta_confidence   REAL,
    supersedes_id     INTEGER REFERENCES documents(id),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (code_key, revision)
);
CREATE INDEX IF NOT EXISTS documents_code_key ON documents(code_key);

CREATE TABLE IF NOT EXISTS sections (
    id           INTEGER PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal      INTEGER NOT NULL,
    clause_no    TEXT,                 -- "4.2.1" (yoksa NULL)
    heading      TEXT,
    heading_path TEXT,                 -- "4 Uygulama > 4.2 Talep"
    text         TEXT NOT NULL,
    search_text  TEXT NOT NULL,        -- textnorm.fold(heading + text)
    UNIQUE (document_id, ordinal)
);

-- Trigram FTS: Türkçe ek yapısında kelime kökü yerine alt dizge eşleşmesi daha güvenilir.
CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
    search_text, content='sections', content_rowid='id', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS sections_ai AFTER INSERT ON sections BEGIN
    INSERT INTO sections_fts(rowid, search_text) VALUES (new.id, new.search_text);
END;
CREATE TRIGGER IF NOT EXISTS sections_ad AFTER DELETE ON sections BEGIN
    INSERT INTO sections_fts(sections_fts, rowid, search_text) VALUES ('delete', old.id, old.search_text);
END;
CREATE TRIGGER IF NOT EXISTS sections_au AFTER UPDATE ON sections BEGIN
    INSERT INTO sections_fts(sections_fts, rowid, search_text) VALUES ('delete', old.id, old.search_text);
    INSERT INTO sections_fts(rowid, search_text) VALUES (new.id, new.search_text);
END;

CREATE TABLE IF NOT EXISTS entities (
    id               INTEGER PRIMARY KEY,
    entity_type      TEXT NOT NULL,       -- EntityType
    canonical_name   TEXT NOT NULL,
    normalized_name  TEXT NOT NULL,       -- fold(canonical_name)
    description      TEXT,
    review_status    TEXT NOT NULL DEFAULT 'ONERILDI',
    UNIQUE (entity_type, normalized_name)
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    id               INTEGER PRIMARY KEY,
    entity_id        INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    alias            TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    UNIQUE (entity_id, normalized_alias)
);

CREATE TABLE IF NOT EXISTS rules (
    id                 INTEGER PRIMARY KEY,
    document_id        INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section_id         INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    clause_no          TEXT,
    rule_type          TEXT NOT NULL,     -- RuleType
    statement          TEXT NOT NULL,     -- normalize edilmiş kural cümlesi
    subject_entity_id  INTEGER REFERENCES entities(id),
    action             TEXT,
    object_text        TEXT,
    object_entity_id   INTEGER REFERENCES entities(id),
    condition_text     TEXT,
    threshold_op       TEXT,              -- '>', '>=', '<', '<=', '='
    threshold_value    REAL,
    threshold_unit     TEXT,              -- TRY, USD, gun, saat, adet ...
    quote              TEXT NOT NULL,     -- birebir alıntı (doğrulanmış)
    review_status      TEXT NOT NULL DEFAULT 'ONERILDI',
    confidence         REAL,
    extracted_by       TEXT,              -- model adı veya 'kullanici'
    reviewed_by        TEXT,
    reviewed_at        TEXT,
    review_note        TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Bilgi grafiği kenarları. Uçlar (kind, id) çiftidir; kind = NodeKind.
CREATE TABLE IF NOT EXISTS edges (
    id            INTEGER PRIMARY KEY,
    src_kind      TEXT NOT NULL,
    src_id        INTEGER NOT NULL,
    rel_type      TEXT NOT NULL,          -- RelType
    dst_kind      TEXT NOT NULL,
    dst_id        INTEGER NOT NULL,
    document_id   INTEGER REFERENCES documents(id) ON DELETE CASCADE,  -- kanıt dokümanı
    section_id    INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    quote         TEXT,
    review_status TEXT NOT NULL DEFAULT 'ONERILDI',
    confidence    REAL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (src_kind, src_id, rel_type, dst_kind, dst_id)
);
CREATE INDEX IF NOT EXISTS edges_src ON edges(src_kind, src_id);
CREATE INDEX IF NOT EXISTS edges_dst ON edges(dst_kind, dst_id);

-- Doküman içinde geçen ama henüz çözülmemiş doküman kodu atıfları.
CREATE TABLE IF NOT EXISTS doc_references (
    id              INTEGER PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section_id      INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    ref_code        TEXT NOT NULL,          -- metinde geçtiği gibi
    resolved_doc_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    UNIQUE (document_id, section_id, ref_code)
);

CREATE TABLE IF NOT EXISTS processes (
    id               INTEGER PRIMARY KEY,
    code             TEXT UNIQUE,
    name             TEXT NOT NULL,
    purpose          TEXT,
    owner_entity_id  INTEGER REFERENCES entities(id),
    inputs           TEXT,
    outputs          TEXT,
    source           TEXT NOT NULL DEFAULT 'KULLANICI',  -- KULLANICI | DOKUMAN
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS process_steps (
    id                     INTEGER PRIMARY KEY,
    process_id             INTEGER NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
    seq                    INTEGER NOT NULL,
    name                   TEXT NOT NULL,
    description            TEXT,
    responsible_entity_id  INTEGER REFERENCES entities(id),
    approver_entity_id     INTEGER REFERENCES entities(id),
    duration_value         REAL,
    duration_unit          TEXT,
    UNIQUE (process_id, seq)
);

-- Karar envanteri
CREATE TABLE IF NOT EXISTS decisions (
    id                 INTEGER PRIMARY KEY,
    code               TEXT UNIQUE,
    title              TEXT NOT NULL,
    description        TEXT,
    owner_entity_id    INTEGER REFERENCES entities(id),   -- kararı veren rol
    process_id         INTEGER REFERENCES processes(id),
    condition_text     TEXT,
    threshold_op       TEXT,
    threshold_value    REAL,
    threshold_unit     TEXT,
    approval_chain     TEXT,          -- JSON: [entity_id, ...] sırayla
    basis_document_id  INTEGER REFERENCES documents(id),
    basis_clause_no    TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id           INTEGER PRIMARY KEY,
    kind         TEXT NOT NULL,       -- 'tutarlilik' | 'yetki' | 'uygunluk' ...
    params       TEXT,                -- JSON
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT,
    status       TEXT NOT NULL DEFAULT 'CALISIYOR'
);

CREATE TABLE IF NOT EXISTS findings (
    id               INTEGER PRIMARY KEY,
    run_id           INTEGER REFERENCES analysis_runs(id) ON DELETE SET NULL,
    finding_type     TEXT NOT NULL,       -- FindingType
    severity         TEXT NOT NULL,       -- Severity
    title            TEXT NOT NULL,
    explanation      TEXT NOT NULL,
    recommendation   TEXT,
    evidence         TEXT NOT NULL,       -- JSON: [{doc_code, revision, clause_no, quote, section_id}]
    unverified_basis INTEGER NOT NULL DEFAULT 0,  -- onaysız kurala dayanıyorsa 1
    fingerprint      TEXT NOT NULL UNIQUE,        -- tekrar çalıştırmada çoğalmayı önler
    status           TEXT NOT NULL DEFAULT 'ACIK',
    status_note      TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT
);

-- Her Claude çağrısının izi (maliyet ve denetlenebilirlik).
CREATE TABLE IF NOT EXISTS llm_calls (
    id                 INTEGER PRIMARY KEY,
    purpose            TEXT NOT NULL,
    model              TEXT NOT NULL,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    cache_read_tokens  INTEGER,
    cache_write_tokens INTEGER,
    stop_reason        TEXT,
    ok                 INTEGER NOT NULL,
    error              TEXT,
    ref                TEXT,              -- ör. "document:12"
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
