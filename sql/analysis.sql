-- Return calculation is partitioned by instrument and ordered by UTC time.
WITH previous_prices AS (
    SELECT instrument, timestamp_utc, close,
           LAG(close) OVER (
               PARTITION BY instrument ORDER BY timestamp_utc
           ) AS previous_close
    FROM prices
)
SELECT instrument, timestamp_utc, close / previous_close - 1 AS simple_return
FROM previous_prices
WHERE previous_close IS NOT NULL
ORDER BY instrument, timestamp_utc;
