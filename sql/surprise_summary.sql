-- Portable SQLite / MySQL 8: join, CASE, window ranks, conditional aggregation.
-- The family recurrence denominator includes all releases, even unknown surprises.
WITH recurring AS (
 SELECT family,COUNT(DISTINCT event_timestamp_utc) AS family_release_count
 FROM event_surprises GROUP BY family
 HAVING COUNT(DISTINCT event_timestamp_utc)>=2
), classified AS (
 SELECT s.*, f.family_release_count,
   CASE WHEN numeric_delta IS NULL THEN 'unknown'
     WHEN numeric_delta>0 THEN 'above' WHEN numeric_delta<0 THEN 'below'
     ELSE 'matched' END AS surprise_category
 FROM event_surprises s JOIN recurring f ON f.family=s.family
), ranked AS (
 SELECT c.family,c.family_release_count,c.surprise_category,r.instrument,r.mode,r.return_pct,
   ROW_NUMBER() OVER (PARTITION BY c.family,c.surprise_category,r.instrument,r.mode
                      ORDER BY r.return_pct,c.event_timestamp_utc,c.event_key) AS return_rank,
   COUNT(*) OVER (PARTITION BY c.family,c.surprise_category,r.instrument,r.mode) AS group_n
 FROM classified c JOIN surprise_responses r ON r.event_key=c.event_key
 WHERE r.status='ok'
)
SELECT family,instrument,mode,surprise_category,MAX(family_release_count) AS family_release_count,
 COUNT(*) AS n,AVG(return_pct) AS mean_return_pct,
 AVG(CASE WHEN 2*return_rank BETWEEN group_n AND group_n+2
          THEN return_pct END) AS median_return_pct,
 SUM(CASE WHEN return_pct>? THEN 1 ELSE 0 END) AS positive_n,
 SUM(CASE WHEN return_pct<-? THEN 1 ELSE 0 END) AS negative_n,
 SUM(CASE WHEN ABS(return_pct)<=? THEN 1 ELSE 0 END) AS neutral_n,
 100.0*SUM(CASE WHEN return_pct>? THEN 1 ELSE 0 END)/COUNT(*) AS positive_share_pct,
 100.0*SUM(CASE WHEN return_pct<-? THEN 1 ELSE 0 END)/COUNT(*) AS negative_share_pct,
 100.0*SUM(CASE WHEN ABS(return_pct)<=? THEN 1 ELSE 0 END)/COUNT(*) AS neutral_share_pct
FROM ranked GROUP BY family,instrument,mode,surprise_category
ORDER BY family,instrument,mode,surprise_category;
