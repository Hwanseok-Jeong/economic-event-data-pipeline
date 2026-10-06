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
