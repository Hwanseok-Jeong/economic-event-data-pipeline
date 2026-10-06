PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS prices (
    instrument TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    close REAL NOT NULL CHECK (close > 0),
    PRIMARY KEY (instrument, timestamp_utc)
);
CREATE TABLE IF NOT EXISTS events (
    event_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    importance TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_time ON events(timestamp_utc);
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id INTEGER PRIMARY KEY,
    started_utc TEXT NOT NULL,
    source TEXT NOT NULL,
    price_rows INTEGER NOT NULL,
    event_rows INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS market_bars (
    instrument TEXT NOT NULL,
    bar_start_utc TEXT NOT NULL,
    bar_end_utc TEXT NOT NULL,
    open_price REAL NOT NULL CHECK (open_price > 0),
    close_price REAL NOT NULL CHECK (close_price > 0),
    session_date TEXT NOT NULL,
    PRIMARY KEY (instrument, bar_start_utc)
);
CREATE TABLE IF NOT EXISTS market_sessions (
    instrument TEXT NOT NULL,
    segment_open_utc TEXT NOT NULL,
    segment_close_utc TEXT NOT NULL,
    session_date TEXT NOT NULL,
    PRIMARY KEY (instrument, segment_open_utc)
);
CREATE TABLE IF NOT EXISTS event_details (
    event_key TEXT PRIMARY KEY REFERENCES events(event_key),
    family TEXT NOT NULL,
    actual TEXT,
    forecast TEXT,
    previous TEXT,
    source_event_id TEXT
);
CREATE TABLE IF NOT EXISTS study_metadata (
    metadata_key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);
