-- SQLite Projection schema (P3). 재생성 가능한 인덱스 — 소스는 JSONL(불변).
-- index.db 삭제 후 rebuild하면 동일 상태 복원. 여기엔 진실의 소유권 없음.

CREATE TABLE IF NOT EXISTS strategies (
    id          TEXT PRIMARY KEY,
    name        TEXT,
    status      TEXT,
    family      TEXT,
    created_at  TEXT,
    updated_at  TEXT,
    config_hash TEXT
);

CREATE TABLE IF NOT EXISTS strategy_events (
    event_id       TEXT PRIMARY KEY,
    strategy_id    TEXT,
    previous_state TEXT,
    new_state      TEXT,
    timestamp      TEXT,
    reason         TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT,
    instrument  TEXT,
    direction   INTEGER,
    strength    REAL,
    timestamp   TEXT
);

CREATE TABLE IF NOT EXISTS allocations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id       TEXT,
    weight            REAL,
    risk_contribution REAL,
    timestamp         TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_decisions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    decision   TEXT,
    reason     TEXT,
    timestamp  TEXT,
    regime     TEXT,
    risk_level TEXT
);

CREATE TABLE IF NOT EXISTS experiments (
    id         TEXT,
    hypothesis TEXT,
    result     TEXT,
    status     TEXT,
    created_at TEXT,
    metadata   TEXT   -- P4 지원: reason/data_source/universe/net/sharpe/percentile(JSON)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event     TEXT,
    actor     TEXT,
    action    TEXT,
    timestamp TEXT,
    metadata  TEXT
);

-- 프로젝션 메타(재생성 provenance — 소스 JSONL 무변경)
CREATE TABLE IF NOT EXISTS projection_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- 읽기 최적화 인덱스
CREATE INDEX IF NOT EXISTS idx_strategies_status   ON strategies(status);
CREATE INDEX IF NOT EXISTS idx_stratevt_sid         ON strategy_events(strategy_id);
CREATE INDEX IF NOT EXISTS idx_stratevt_ts          ON strategy_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_sid          ON signals(strategy_id);
CREATE INDEX IF NOT EXISTS idx_signals_ts           ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_alloc_sid            ON allocations(strategy_id);
CREATE INDEX IF NOT EXISTS idx_experiments_status   ON experiments(status);
CREATE INDEX IF NOT EXISTS idx_audit_ts             ON audit_events(timestamp);
