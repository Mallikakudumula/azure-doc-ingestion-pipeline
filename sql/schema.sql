-- Metadata, lineage and audit schema (SQLite syntax; see README for Azure SQL notes).

CREATE TABLE IF NOT EXISTS documents (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash         TEXT NOT NULL UNIQUE,      -- SHA-256 of raw bytes => idempotency key
    filename          TEXT NOT NULL,
    source_channel    TEXT NOT NULL,             -- email | sharepoint | portal | shared_drive
    source_ref        TEXT,                      -- message id / drive item id / path
    landing_path      TEXT,                      -- where the raw copy is staged
    file_format       TEXT,
    page_count        INTEGER,
    sensitivity_label TEXT,                      -- Internal | Confidential | Highly Confidential
    status            TEXT NOT NULL,             -- RECEIVED|COMPLETED|NEEDS_REVIEW|DUPLICATE|FAILED
    business_key      TEXT,                      -- document_number|counterparty|amount
    duplicate_of      INTEGER REFERENCES documents(id),
    received_at       TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    pipeline_version  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_documents_business_key ON documents(business_key);

CREATE TABLE IF NOT EXISTS extracted_fields (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   INTEGER NOT NULL REFERENCES documents(id),
    field_name    TEXT NOT NULL,
    raw_value     TEXT,
    clean_value   TEXT,
    confidence    REAL,
    page          INTEGER,
    model_id      TEXT,
    model_version TEXT,
    UNIQUE (document_id, field_name)
);

-- One row per stage transition = end-to-end lineage
CREATE TABLE IF NOT EXISTS lineage_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id      INTEGER NOT NULL REFERENCES documents(id),
    stage            TEXT NOT NULL,   -- received|staged|normalized|classified|extracted|validated|stored|failed
    status           TEXT NOT NULL,   -- ok | warning | error
    detail           TEXT,
    created_at       TEXT NOT NULL,
    pipeline_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | RESOLVED
    created_at  TEXT NOT NULL,
    resolved_at TEXT,
    reviewer    TEXT
);

-- Who changed what, when (old vs new value)
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    document_id INTEGER REFERENCES documents(id),
    field_name  TEXT,
    old_value   TEXT,
    new_value   TEXT
);

CREATE TABLE IF NOT EXISTS dead_letters (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash      TEXT NOT NULL,
    filename       TEXT NOT NULL,
    reason         TEXT NOT NULL,
    source_channel TEXT,
    created_at     TEXT NOT NULL
);
