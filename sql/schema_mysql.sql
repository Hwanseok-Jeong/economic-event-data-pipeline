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
