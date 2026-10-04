-- schema.sql
-- Creates the 5 tables for the Crop Lab ETL pipeline
-- Safe to run more than onceL IF NOT EXISTS skips the tables that already exist
-- Order is important: a table must exist before another table can point to it

--1. Diary: one row per pipeline run
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running','success','partial','failed')),
    files_seen      INTEGER NOT NULL DEFAULT 0,
    files_loaded    INTEGER NOT NULL DEFAULT 0,
    files_skipped   INTEGER NOT NULL DEFAULT 0,
    files_failed    INTEGER NOT NULL DEFAULT 0,
    rows_loaded     INTEGER NOT NULL DEFAULT 0,
    rows_rejected   INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT
);

--2.Memory: one row per file the pipeline has looked at
CREATE TABLE IF NOT EXISTS processed_files (
    file_id         INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES pipeline_runs (run_id),
    file_name       TEXT NOT NULL,
    file_hash       CHAR(64) NOT NULL,
    file_type       TEXT CHECK (file_type IN ('lab','practice')),
    status          TEXT NOT NULL
                    CHECK (status IN ('loaded', 'skipped duplicate','failed')),
    rows_loaded     INTEGER NOT NULL DEFAULT 0,
    rows_rejected   INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

--Only one successful load per fingerprint, skipped and failed attempts may repeat
CREATE UNIQUE INDEX IF NOT EXISTS uq_processed_files_loaded_hash
    ON processed_files (file_hash)
    WHERE status = 'loaded';

-- 3. Clean lab results: one row per sample (a retest replaces the older value)
CREATE TABLE IF NOT EXISTS lab_results (
    sample_id                 TEXT PRIMARY KEY,
    commodity                 TEXT NOT NULL
                              CHECK (commodity IN ('Tur', 'Groundnut', 'Chana', 'Turmeric')),
    batch_no                  TEXT,
    test_date                 DATE NOT NULL,
    moisture_pct              NUMERIC(5,2) CHECK (moisture_pct BETWEEN 0 AND 100),
    oil_pct                   NUMERIC(5,2) CHECK (oil_pct BETWEEN 0 AND 100),
    foreign_matter_pct        NUMERIC(5,2) CHECK (foreign_matter_pct BETWEEN 0 AND 100),
    aflatoxin_ppb             NUMERIC(7,2) CHECK (aflatoxin_ppb >= 0),
    aflatoxin_below_detection BOOLEAN NOT NULL DEFAULT FALSE,
    needs_review              BOOLEAN NOT NULL DEFAULT FALSE,
    review_note               TEXT,
    remarks                   TEXT,
    source_file_id            INTEGER NOT NULL REFERENCES processed_files (file_id),
    loaded_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- "below detection" means no number was measured, so the value must be empty
    CHECK (NOT (aflatoxin_below_detection AND aflatoxin_ppb IS NOT NULL))
);

-- 4. Clean market prices, always in Rs per quintal
CREATE TABLE IF NOT EXISTS market_prices (
    price_id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    price_date          DATE NOT NULL,
    market              TEXT NOT NULL,
    district            TEXT,
    commodity           TEXT NOT NULL
                        CHECK (commodity IN ('Tur', 'Groundnut', 'Chana', 'Turmeric')),
    variety             TEXT,
    grade               TEXT,
    min_price_rs_qtl    NUMERIC(10,2) NOT NULL CHECK (min_price_rs_qtl > 0),
    max_price_rs_qtl    NUMERIC(10,2) NOT NULL CHECK (max_price_rs_qtl > 0),
    modal_price_rs_qtl  NUMERIC(10,2) NOT NULL CHECK (modal_price_rs_qtl > 0),
    source              TEXT NOT NULL CHECK (source IN ('agmarknet', 'trader')),
    source_file_id      INTEGER NOT NULL REFERENCES processed_files (file_id),
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (min_price_rs_qtl <= modal_price_rs_qtl
           AND modal_price_rs_qtl <= max_price_rs_qtl),
    UNIQUE (market, commodity, price_date)
);

-- 5. Quarantine: bad rows, kept exactly as they arrived, with the reason
CREATE TABLE IF NOT EXISTS rejected_rows (
    rejected_id     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file_id  INTEGER NOT NULL REFERENCES processed_files (file_id),
    target_table    TEXT NOT NULL CHECK (target_table IN ('lab_results', 'market_prices')),
    excel_row       INTEGER,
    reason          TEXT NOT NULL,
    raw_data        JSONB NOT NULL,
    rejected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);