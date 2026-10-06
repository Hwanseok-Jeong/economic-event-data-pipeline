CREATE TABLE IF NOT EXISTS prices (
    instrument VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    timestamp_utc VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    close DOUBLE NOT NULL CHECK (close > 0),
    PRIMARY KEY (instrument, timestamp_utc)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS events (
    event_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    name TEXT NOT NULL,
    country VARCHAR(255) NOT NULL,
    timestamp_utc VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    importance VARCHAR(6) NOT NULL,
    INDEX events_time (timestamp_utc),
    CHECK (importance IN ('Low', 'Medium', 'High'))
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    started_utc VARCHAR(32) NOT NULL,
    source VARCHAR(255) NOT NULL,
    price_rows INTEGER NOT NULL,
    event_rows INTEGER NOT NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS market_bars (
    instrument VARCHAR(64) NOT NULL,
    bar_start_utc VARCHAR(32) NOT NULL,
    bar_end_utc VARCHAR(32) NOT NULL,
    open_price DOUBLE NOT NULL CHECK (open_price > 0),
    close_price DOUBLE NOT NULL CHECK (close_price > 0),
    session_date CHAR(10) NOT NULL,
    PRIMARY KEY (instrument, bar_start_utc)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS market_sessions (
    instrument VARCHAR(64) NOT NULL,
    segment_open_utc VARCHAR(32) NOT NULL,
    segment_close_utc VARCHAR(32) NOT NULL,
    session_date CHAR(10) NOT NULL,
    PRIMARY KEY (instrument, segment_open_utc)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS event_details (
    event_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    family VARCHAR(512) NOT NULL,
    actual TEXT,
    forecast TEXT,
    previous TEXT,
    source_event_id VARCHAR(64),
    FOREIGN KEY (event_key) REFERENCES events(event_key)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS study_metadata (
    metadata_key VARCHAR(64) PRIMARY KEY,
    value_json LONGTEXT NOT NULL
) ENGINE=InnoDB;
