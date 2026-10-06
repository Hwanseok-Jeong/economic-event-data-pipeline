-- Repeated means >=2 distinct release timestamps in the supplied snapshot.
-- Narrative announcements remain separate and have unknown numeric surprises.
WITH recurring AS (
 SELECT family FROM event_surprises
 GROUP BY family HAVING COUNT(DISTINCT event_timestamp_utc)>=2
), classified AS (
 SELECT s.*, CASE WHEN numeric_delta IS NULL THEN 'unknown'
   WHEN numeric_delta>0 THEN 'above' WHEN numeric_delta<0 THEN 'below'
   ELSE 'matched' END AS surprise_category
 FROM event_surprises s JOIN recurring f ON f.family=s.family
)
SELECT c.*, r.instrument,r.mode,r.status,r.return_pct,
       r.baseline_timestamp_utc,r.observation_timestamp_utc,
       r.elapsed_hours_since_event,r.co_release_count
FROM classified c JOIN surprise_responses r ON r.event_key=c.event_key
ORDER BY c.family,c.event_timestamp_utc,r.instrument;
