-- Part 2, CEO: "Were August users less engaged than June/July users?"
-- Metrics (all windows from signup, all fully observed for every cohort):
--   onboarding_pct = onboarding_complete within 24 h of signup
--   d1_pct         = session_start 24-48 h after signup
--   w1_pct         = session_start on days 7-13 after signup (week 1 of the cohort table)

-- name: funnel_by_month
SELECT
    signup_month,
    count(*)                                        AS users,
    round(100.0 * avg(onboarded_24h::int), 1)       AS onboarding_pct,
    round(100.0 * avg(saw_paywall::int), 1)         AS paywall_pct,
    round(100.0 * avg(started_trial::int), 1)       AS trial_pct,
    round(100.0 * avg(active_d1::int), 1)           AS d1_pct,
    round(100.0 * avg(active_w1::int), 1)           AS w1_pct,
    round(100.0 * avg(is_payer::int), 1)            AS payer_pct,
    round(avg(revenue_30d), 2)                      AS revenue_30d_per_user
FROM an.user_facts
GROUP BY signup_month
ORDER BY signup_month;

-- name: funnel_by_month_platform
SELECT
    signup_month,
    platform,
    count(*)                                        AS users,
    round(100.0 * avg(onboarded_24h::int), 1)       AS onboarding_pct,
    round(100.0 * avg(saw_paywall::int), 1)         AS paywall_pct,
    round(100.0 * avg(active_d1::int), 1)           AS d1_pct,
    round(100.0 * avg(active_w1::int), 1)           AS w1_pct
FROM an.user_facts
GROUP BY signup_month, platform
ORDER BY platform, signup_month;

-- name: funnel_by_month_channel
SELECT
    signup_month,
    channel,
    count(*)                                                                    AS users,
    round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY signup_month), 1) AS share_of_signups_pct,
    round(100.0 * avg(onboarded_24h::int), 1)                                   AS onboarding_pct,
    round(100.0 * avg(active_d1::int), 1)                                       AS d1_pct,
    round(100.0 * avg(active_w1::int), 1)                                       AS w1_pct
FROM an.user_facts
GROUP BY signup_month, channel
ORDER BY channel, signup_month;

-- name: onboarding_by_week_platform
SELECT
    signup_week,
    platform,
    count(*)                                        AS users,
    round(100.0 * avg(onboarded_24h::int), 1)       AS onboarding_pct,
    round(100.0 * avg(active_d1::int), 1)           AS d1_pct
FROM an.user_facts
GROUP BY signup_week, platform
ORDER BY platform, signup_week;

-- name: onboarding_by_day_android_aug
-- Locates the break: Android onboarding by signup day around mid-August.
SELECT
    signup_ts::date                                 AS signup_date,
    platform,
    count(*)                                        AS users,
    round(100.0 * avg(onboarded_24h::int), 1)       AS onboarding_pct
FROM an.user_facts
WHERE signup_ts >= '2026-08-01'
GROUP BY signup_ts::date, platform
ORDER BY platform, signup_date;

-- name: period_platform
-- Before / after the Android break on 2026-08-15.
SELECT
    CASE WHEN signup_ts <  '2026-08-01' THEN '1. Jun-Jul'
         WHEN signup_ts <  '2026-08-15' THEN '2. Aug 1-14'
         ELSE '3. Aug 15-30' END                    AS period,
    platform,
    count(*)                                        AS users,
    round(100.0 * avg(onboarded_24h::int), 1)       AS onboarding_pct,
    round(100.0 * avg(saw_paywall::int), 1)         AS paywall_pct,
    round(100.0 * avg(active_d1::int), 1)           AS d1_pct,
    round(100.0 * avg(active_w1::int), 1)           AS w1_pct,
    round(100.0 * avg(started_trial::int), 1)       AS trial_pct
FROM an.user_facts
GROUP BY 1, platform
ORDER BY platform, period;
