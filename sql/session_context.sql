-- Portable SQLite / MySQL 8 query: event market state and next-opening reference.
-- Stored timestamps are UTC; instrument types are cash indices only.
WITH instruments AS (
    SELECT DISTINCT instrument FROM market_bars
)
SELECT e.name, e.country, e.timestamp_utc, i.instrument,
       CASE WHEN EXISTS (
           SELECT 1 FROM market_sessions s
           WHERE s.instrument = i.instrument
             AND e.timestamp_utc >= s.segment_open_utc
             AND e.timestamp_utc < s.segment_close_utc
       ) THEN 'open_at_release' ELSE 'closed_at_release' END AS market_state,
       (SELECT MIN(s.segment_open_utc) FROM market_sessions s
        WHERE s.instrument = i.instrument
          AND s.segment_open_utc > e.timestamp_utc) AS next_segment_open_utc,
       (SELECT MAX(b.bar_end_utc) FROM market_bars b
        WHERE b.instrument = i.instrument
          AND b.bar_end_utc <= e.timestamp_utc) AS previous_observed_close_utc
FROM events e CROSS JOIN instruments i
ORDER BY e.timestamp_utc, i.instrument;
