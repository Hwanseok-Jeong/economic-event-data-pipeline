-- SQLite / MySQL 8. One row per country + release time, not per co-released indicator.
-- Input: session_responses_report, materialized by build_case_report.py.
WITH releases AS (
 SELECT country, event_timestamp_utc, MIN(event_key) AS representative_key,
        COUNT(DISTINCT event_key) AS indicator_count
 FROM session_responses_report
 GROUP BY country, event_timestamp_utc
), ranked AS (
 SELECT r.*, ROW_NUMBER() OVER (
   PARTITION BY r.event_key ORDER BY observation_timestamp_utc, instrument
 ) AS observation_order
 FROM session_responses_report r
 JOIN releases g ON r.event_key=g.representative_key
 WHERE r.status='ok'
), cases AS (
 SELECT r.country, r.event_timestamp_utc, r.event_key,
        MAX(g.indicator_count) AS indicator_count, COUNT(*) AS market_count,
        SUM(CASE WHEN return_pct > ? THEN 1 ELSE 0 END) AS positive_count,
        SUM(CASE WHEN return_pct < -? THEN 1 ELSE 0 END) AS negative_count,
        MAX(CASE WHEN observation_order=1 THEN ABS(return_pct) END) AS first_magnitude,
        MAX(CASE WHEN observation_order=2 THEN ABS(return_pct) END) AS second_magnitude,
        MAX(CASE WHEN observation_order=3 THEN ABS(return_pct) END) AS last_magnitude,
        COUNT(DISTINCT observation_timestamp_utc) AS distinct_observation_times
 FROM ranked r JOIN releases g ON r.event_key=g.representative_key
 GROUP BY r.country, r.event_timestamp_utc, r.event_key
 HAVING COUNT(*)=3
)
SELECT *, CASE WHEN positive_count=3 THEN 'all_positive'
 WHEN negative_count=3 THEN 'all_negative'
 WHEN positive_count>0 AND negative_count>0 THEN 'mixed_direction'
 ELSE 'includes_neutral' END AS direction,
 CASE WHEN (positive_count=3 OR negative_count=3)
   AND distinct_observation_times=3
   AND first_magnitude < second_magnitude AND second_magnitude < last_magnitude
 THEN 1 ELSE 0 END AS increasing_magnitude
FROM cases ORDER BY event_timestamp_utc, country;
