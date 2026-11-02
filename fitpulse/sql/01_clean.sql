-- Clean layer: every analysis query reads from schema "an", never from "raw".
-- Data-quality rules (counts in 06_data_quality.sql):
--   1. 15 internal QA accounts (channel = 'internal', user_id 'qa_*') are excluded everywhere,
--      together with their 15 $0.00 test purchases.
--   2. 648 event rows are exact duplicates of another row (same event_id) -> de-duplicated.
--   3. 40 event rows have no user_id -> dropped (cannot be attributed).
--   4. 30 Android session_start events are stamped exactly 23h59m30s BEFORE signup
--      (suspected date offset) -> shifted +1 day for this exact pattern only.
--      This is a documented repair assumption, not a verified server timestamp.
--   5. Activity is capped at the end of the observation window, 2026-10-01 00:00 UTC.

DROP SCHEMA IF EXISTS an CASCADE;
CREATE SCHEMA an;

CREATE VIEW an.users AS
SELECT *
FROM raw.users
WHERE channel <> 'internal';

CREATE VIEW an.events AS
WITH fixed AS (
    SELECT DISTINCT
        e.event_id,
        e.user_id,
        e.event_name,
        CASE WHEN u.platform = 'android'
              AND e.event_name = 'session_start'
              AND e.event_ts = u.signup_ts - interval '1 day' + interval '30 seconds'
             THEN e.event_ts + interval '1 day'      -- rule 4: exact-pattern repair assumption
             ELSE e.event_ts END AS event_ts,
        u.signup_ts
    FROM raw.events e
    JOIN an.users u USING (user_id)
)
SELECT event_id, user_id, event_name, event_ts
FROM fixed
WHERE event_ts >= signup_ts
  AND event_ts <  timestamp '2026-10-01';

CREATE VIEW an.payments AS
SELECT p.*
FROM raw.payments p
JOIN an.users u USING (user_id)
WHERE p.payment_ts >= u.signup_ts AND p.payment_ts < timestamp '2026-10-01';

CREATE VIEW an.marketing_spend AS
SELECT to_date(month, 'YYYY-MM') AS month, channel, spend_usd
FROM raw.marketing_spend;

-- One row per user with every flag the analyses need.
-- Windows are measured from signup_ts, so cohorts of different calendar months are comparable.
--   active_d1  : session_start between 24 h and 48 h after signup
--   active_w1  : session_start between day 7 and day 14 after signup (= week 1 of the cohort table)
--   revenue_30d: net payments within 30 days of signup; fully observed for every cohort
--                (last signup 2026-08-30 + 30 d < 2026-10-01). It covers the 7-day trial and the
--                first purchase, but no renewal in this dataset. Revenue is cash net of refunds,
--                BEFORE store fees/tax/service costs: those are not supplied. D38 is NULL for
--                immature users. Trial is D7; is_payer is explicitly first purchase before D14.
CREATE VIEW an.user_facts AS
WITH ev AS (
    SELECT
        e.user_id,
        bool_or(e.event_name = 'onboarding_complete')                                                AS onboarded,
        bool_or(e.event_name = 'onboarding_complete' AND e.event_ts < u.signup_ts + interval '1 day') AS onboarded_24h,
        bool_or(e.event_name = 'paywall_view')                                                        AS saw_paywall,
        bool_or(e.event_name = 'trial_start' AND e.event_ts < u.signup_ts + interval '7 days')                                                         AS started_trial,
        bool_or(e.event_name = 'session_start'
                AND e.event_ts >= u.signup_ts + interval '1 day'
                AND e.event_ts <  u.signup_ts + interval '2 days')                                    AS active_d1,
        bool_or(e.event_name = 'session_start'
                AND e.event_ts >= u.signup_ts + interval '7 days'
                AND e.event_ts <  u.signup_ts + interval '14 days')                                   AS active_w1,
        count(*) FILTER (WHERE e.event_name = 'workout_complete'
                           AND e.event_ts < u.signup_ts + interval '7 days')                          AS workouts_7d
    FROM an.events e
    JOIN an.users u USING (user_id)
    GROUP BY e.user_id
),
pay AS (
    SELECT
        p.user_id,
        min(p.payment_ts) FILTER (WHERE p.payment_type = 'purchase' AND p.amount_usd > 0) AS first_purchase_ts,
        min(p.plan)       FILTER (WHERE p.payment_type = 'purchase' AND p.amount_usd > 0) AS plan,
        bool_or(p.payment_type = 'refund')                                      AS refunded,
        sum(p.amount_usd)                                                       AS revenue_total,
        sum(p.amount_usd) FILTER (WHERE p.payment_ts < u.signup_ts + interval '30 days') AS revenue_30d,
        sum(p.amount_usd) FILTER (WHERE p.payment_ts < u.signup_ts + interval '38 days') AS revenue_38d,
        bool_or(p.payment_type = 'refund' AND p.payment_ts < u.signup_ts + interval '38 days') AS refunded_38d
    FROM an.payments p
    JOIN an.users u USING (user_id)
    GROUP BY p.user_id
)
SELECT
    u.user_id,
    u.signup_ts,
    date_trunc('week',  u.signup_ts)::date              AS signup_week,   -- ISO week, Monday start
    date_trunc('month', u.signup_ts)::date              AS signup_month,
    u.platform,
    u.country,
    u.channel,
    u.ab_group,
    coalesce(ev.onboarded, false)                       AS onboarded,
    coalesce(ev.onboarded_24h, false)                   AS onboarded_24h,
    coalesce(ev.saw_paywall, false)                     AS saw_paywall,
    coalesce(ev.started_trial, false)                   AS started_trial,
    coalesce(ev.active_d1, false)                       AS active_d1,
    coalesce(ev.active_w1, false)                       AS active_w1,
    coalesce(ev.workouts_7d, 0)                         AS workouts_7d,
    coalesce(pay.first_purchase_ts < u.signup_ts + interval '14 days', false) AS is_payer, -- D14
    u.signup_ts + interval '38 days' <= timestamp '2026-10-01' AS mature_38d,
    CASE WHEN u.signup_ts + interval '38 days' <= timestamp '2026-10-01'
         THEN coalesce(pay.revenue_38d, 0) END AS revenue_38d,
    CASE WHEN u.signup_ts + interval '38 days' <= timestamp '2026-10-01'
         THEN coalesce(pay.refunded_38d, false) END AS refunded_38d,
    pay.plan,
    coalesce(pay.refunded, false)                       AS refunded,
    coalesce(pay.revenue_total, 0)                      AS revenue_total,
    coalesce(pay.revenue_30d, 0)                        AS revenue_30d
FROM an.users u
LEFT JOIN ev  USING (user_id)
LEFT JOIN pay USING (user_id);
