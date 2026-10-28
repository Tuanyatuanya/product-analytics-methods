-- Data-quality validation rules for the product event pipeline.
-- Each rule returns the rows that FAIL it. Run with: python src/run_dq_checks.py
-- Tables: users(user_id, signup_ts, region, acquisition_channel, platform, onboarding_completed, ...)
--         events(event_id, user_id, event_ts, event_type, revenue_usd, ingested_ts)
-- Header format: -- rule: <id> | <dimension> | <description>

-- rule: C1 | completeness | Event has no user_id
SELECT * FROM events WHERE user_id IS NULL;

-- rule: C2 | completeness | User has no region
SELECT * FROM users WHERE region IS NULL;

-- rule: C3 | completeness | Event has no timestamp or type
SELECT * FROM events WHERE event_ts IS NULL OR event_type IS NULL;

-- rule: C4 | completeness | Calendar day with zero events (missing partition)
WITH bounds AS (   -- observation window of the pipeline
    SELECT DATE '2025-01-06' AS d0, DATE '2025-05-25' AS d1
),
days AS (SELECT UNNEST(generate_series(d0, d1, INTERVAL 1 DAY))::DATE AS day FROM bounds)
SELECT d.day FROM days d
LEFT JOIN (SELECT DISTINCT event_ts::DATE AS day FROM events) e USING (day)
WHERE e.day IS NULL;

-- rule: K1 | consistency | Duplicate event_id
SELECT event_id, COUNT(*) AS n FROM events GROUP BY event_id HAVING COUNT(*) > 1;

-- rule: K2 | consistency | Duplicate user record
SELECT user_id, COUNT(*) AS n FROM users GROUP BY user_id HAVING COUNT(*) > 1;

-- rule: K3 | consistency | Event references a user that does not exist (orphan)
SELECT e.* FROM events e
WHERE e.user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM users u WHERE u.user_id = e.user_id);

-- rule: K4 | consistency | Event type outside the tracking plan
SELECT * FROM events
WHERE event_type NOT IN ('session_start', 'onboarding_complete', 'feature_use', 'purchase');

-- rule: K5 | consistency | Platform value outside the allowed set
SELECT * FROM users WHERE platform NOT IN ('ios', 'android', 'web');

-- rule: K6 | consistency | Negative revenue
SELECT * FROM events WHERE revenue_usd < 0;

-- rule: K7 | consistency | Revenue recorded on a non-purchase event
SELECT * FROM events WHERE event_type <> 'purchase' AND revenue_usd <> 0;

-- rule: K8 | consistency | Event occurs before the user's signup
SELECT e.* FROM events e
JOIN (SELECT user_id, MIN(signup_ts) AS signup_ts FROM users GROUP BY user_id) u USING (user_id)
WHERE e.event_ts < u.signup_ts - INTERVAL 1 MINUTE;

-- rule: T1 | timeliness | Event timestamp in the future (after load date)
SELECT * FROM events WHERE event_ts > TIMESTAMP '2025-06-30';

-- rule: T2 | timeliness | Event ingested more than 24h after it occurred (late-arriving)
SELECT * FROM events WHERE ingested_ts - event_ts > INTERVAL 24 HOUR;

-- rule: T3 | timeliness | Event ingested before it occurred (clock skew)
SELECT * FROM events WHERE ingested_ts < event_ts;
