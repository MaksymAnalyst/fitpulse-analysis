-- Data-quality checks behind the cleaning rules in 01_clean.sql.

-- name: checks
SELECT * FROM (
    SELECT 1 AS n, 'internal QA users (channel = internal)' AS check_name, count(*)::bigint AS value
    FROM raw.users WHERE channel = 'internal'
    UNION ALL
    SELECT 2, 'QA users with paywall/trial events but no install', count(DISTINCT e.user_id)
    FROM raw.events e JOIN raw.users u USING (user_id)
    WHERE u.channel = 'internal' AND e.event_name IN ('paywall_view', 'trial_start')
    UNION ALL
    SELECT 3, '$0.00 purchases (all belong to QA users)', count(*)
    FROM raw.payments WHERE amount_usd = 0
    UNION ALL
    SELECT 4, 'event rows that duplicate another row (same event_id)', count(*) - count(DISTINCT event_id)
    FROM raw.events
    UNION ALL
    SELECT 5, 'event rows with no user_id', count(*)
    FROM raw.events WHERE user_id IS NULL
    UNION ALL
    SELECT 6, 'session_start stamped 23h59m30s before signup (all Android)', count(*)
    FROM (SELECT DISTINCT e.* FROM raw.events e JOIN raw.users u USING (user_id)
          WHERE e.event_ts < u.signup_ts) x
    UNION ALL
    SELECT 7, 'users with more than one app_install (re-installs)', count(*)
    FROM (SELECT user_id FROM raw.events WHERE event_name = 'app_install'
          GROUP BY user_id HAVING count(DISTINCT event_ts) > 1) x
    UNION ALL
    SELECT 8, 'refunds', count(*)
    FROM raw.payments WHERE payment_type = 'refund'
    UNION ALL
    SELECT 9, 'external users kept for analysis', count(*)
    FROM an.users
    UNION ALL
    SELECT 10, 'events kept for analysis', count(*)
    FROM an.events
) c
ORDER BY n;

-- name: trial_counting
-- The PM's "+~40% trials" holds however it is counted: raw events, unique users, or per viewer.
SELECT
    u.ab_group,
    count(*)                                AS trial_events_raw,
    count(DISTINCT e.user_id)               AS trial_users
FROM raw.events e
JOIN an.users u USING (user_id)
WHERE e.event_name = 'trial_start'
  AND u.ab_group IS NOT NULL
GROUP BY u.ab_group
ORDER BY u.ab_group;
