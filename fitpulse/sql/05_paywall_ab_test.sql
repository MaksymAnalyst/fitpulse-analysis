-- Part 2, Product Manager: "Paywall B: trials +~40%, revenue per user up. Roll out to 100%."
-- Test population: every external user who signed up 2026-08-01..08-30 (ab_group A or B).
-- Analysis is intention-to-treat: all assigned users count, whether or not they reached the paywall.
-- Significance tests and intervals are computed in analysis/stats.py from ab_users.

-- name: srm
SELECT
    ab_group,
    count(*)                                                AS users,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1)      AS share_pct
FROM an.user_facts
WHERE ab_group IS NOT NULL
GROUP BY ab_group
ORDER BY ab_group;

-- name: balance
SELECT 'platform' AS dimension, platform AS value,
       count(*) FILTER (WHERE ab_group = 'A') AS users_a,
       count(*) FILTER (WHERE ab_group = 'B') AS users_b
FROM an.user_facts WHERE ab_group IS NOT NULL GROUP BY platform
UNION ALL
SELECT 'channel', channel,
       count(*) FILTER (WHERE ab_group = 'A'),
       count(*) FILTER (WHERE ab_group = 'B')
FROM an.user_facts WHERE ab_group IS NOT NULL GROUP BY channel
UNION ALL
SELECT 'country', country,
       count(*) FILTER (WHERE ab_group = 'A'),
       count(*) FILTER (WHERE ab_group = 'B')
FROM an.user_facts WHERE ab_group IS NOT NULL GROUP BY country
ORDER BY dimension, value;

-- name: ab_summary
SELECT
    ab_group,
    count(*)                                                            AS users,
    round(100.0 * avg(onboarded_24h::int), 1)                           AS onboarding_pct,
    round(100.0 * avg(saw_paywall::int), 1)                             AS paywall_view_pct,
    sum(started_trial::int)                                             AS trials,
    round(100.0 * avg(started_trial::int), 1)                           AS trial_pct,
    round(100.0 * sum(started_trial::int) / nullif(sum(saw_paywall::int), 0), 1) AS trial_per_viewer_pct,
    sum(is_payer::int)                                                  AS payers,
    round(100.0 * avg(is_payer::int), 2)                                AS payer_pct,
    round(100.0 * sum(is_payer::int) / nullif(sum(started_trial::int), 0), 1)    AS trial_to_paid_pct,
    count(*) FILTER (WHERE plan = 'annual')                             AS annual_payers,
    count(*) FILTER (WHERE plan = 'monthly')                            AS monthly_payers,
    sum(refunded::int)                                                  AS refunds,
    sum(revenue_30d)                                                    AS revenue_30d,
    round(avg(revenue_30d), 2)                                          AS arpu_30d,
    sum(revenue_total)                                                  AS revenue_to_date,
    round(avg(revenue_total), 2)                                        AS arpu_to_date,
    round(100.0 * avg(active_d1::int), 1)                               AS d1_pct,
    round(100.0 * avg(active_w1::int), 1)                               AS w1_pct
FROM an.user_facts
WHERE ab_group IS NOT NULL
GROUP BY ab_group
ORDER BY ab_group;

-- name: ab_by_platform
SELECT
    platform,
    ab_group,
    count(*)                                        AS users,
    round(100.0 * avg(started_trial::int), 1)       AS trial_pct,
    round(100.0 * avg(is_payer::int), 1)            AS payer_pct,
    round(avg(revenue_30d), 2)                      AS arpu_30d,
    round(100.0 * avg(active_d1::int), 1)           AS d1_pct
FROM an.user_facts
WHERE ab_group IS NOT NULL
GROUP BY platform, ab_group
ORDER BY platform, ab_group;

-- name: ab_revenue_by_plan
-- Descriptive revenue components; keep all assigned users in the denominator.
SELECT
    ab_group,
    coalesce(plan, 'none')                          AS plan,
    count(*)                                        AS users,
    sum(revenue_30d)                                AS revenue_30d
FROM an.user_facts
WHERE ab_group IS NOT NULL
GROUP BY ab_group, coalesce(plan, 'none')
ORDER BY ab_group, plan;

-- name: ab_weekly
SELECT
    signup_week,
    ab_group,
    count(*)                                        AS users,
    round(100.0 * avg(started_trial::int), 1)       AS trial_pct,
    round(100.0 * avg(is_payer::int), 1)            AS payer_pct
FROM an.user_facts
WHERE ab_group IS NOT NULL
GROUP BY signup_week, ab_group
ORDER BY signup_week, ab_group;

-- name: ab_users
-- One row per test user: the input for the statistical tests.
SELECT
    user_id, ab_group, platform, channel, country, signup_week,
    onboarded_24h, saw_paywall, started_trial, is_payer, plan, refunded,
    active_d1, active_w1, revenue_30d, revenue_total,
    signup_ts, mature_38d, revenue_38d, refunded_38d
FROM an.user_facts
WHERE ab_group IS NOT NULL
ORDER BY user_id;


-- name: ab_d38_summary
-- D38 = [signup, signup + 38 days). Only users with the complete window are eligible.
-- Cash after refunds, before store fees. This is exploratory: the metric was chosen after review.
SELECT ab_group, count(*) AS users, sum(revenue_38d) AS revenue_38d,
       round(avg(revenue_38d), 4) AS revenue_38d_per_user,
       sum(refunded_38d::int) AS refund_users,
       round(100.0 * avg(active_d1::int), 2) AS d1_pct
FROM an.user_facts
WHERE ab_group IS NOT NULL AND mature_38d
GROUP BY ab_group ORDER BY ab_group;

-- name: ab_renewal_windows
WITH r AS (
    SELECT p.user_id, p.payment_ts, p.amount_usd, u.signup_ts, u.mature_38d,
           extract(epoch FROM p.payment_ts-u.signup_ts)/86400 AS age_days
    FROM an.payments p JOIN an.user_facts u USING (user_id)
    WHERE p.payment_type='renewal' AND u.ab_group IS NOT NULL
)
SELECT count(*) AS renewals_to_date, sum(amount_usd) AS renewal_revenue_to_date,
       min(age_days) AS first_renewal_min_age_days, max(age_days) AS first_renewal_max_age_days,
       count(*) FILTER (WHERE age_days < 37) AS renewals_before_d37,
       count(*) FILTER (WHERE age_days < 38 AND mature_38d) AS renewals_d38_mature
FROM r;

-- name: all_user_facts
-- Export used by independent verification; no raw rows are modified.
SELECT * FROM an.user_facts ORDER BY user_id;
