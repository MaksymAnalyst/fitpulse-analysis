-- Part 2, Head of Marketing: "Paid social gives the cheapest installs. Double its budget in Q4."
-- One signup = one install (signup_ts equals the app_install timestamp for every user).
--   cpi             = spend / installs
--   cost_per_payer  = spend / users whose first purchase is within D14 (acquisition cost per payer)
--   roas_30d        = revenue in each user's first 30 days / spend. Used for comparisons because
--                     it is fully observed for every cohort; revenue-to-date favours older cohorts,
--                     and paid social is skewed towards the youngest (August).
-- Organic has no spend. Referral spend = bonuses paid to referrers.

-- name: channel_month
WITH cm AS (
    SELECT
        signup_month              AS month,
        channel,
        count(*)                  AS installs,
        sum(onboarded_24h::int)   AS onboarded,
        sum(started_trial::int)   AS trials,
        sum(is_payer::int)        AS payers,
        sum(revenue_30d)          AS revenue_30d,
        sum(revenue_total)        AS revenue_to_date
    FROM an.user_facts
    GROUP BY signup_month, channel
)
SELECT
    cm.month,
    cm.channel,
    s.spend_usd,
    cm.installs,
    round(s.spend_usd / cm.installs, 2)                 AS cpi,
    round(100.0 * cm.onboarded / cm.installs, 1)        AS onboarding_pct,
    round(100.0 * cm.trials / cm.installs, 1)           AS trial_pct,
    cm.payers,
    round(100.0 * cm.payers / cm.installs, 1)           AS payer_pct,
    round(s.spend_usd / nullif(cm.payers, 0), 2)        AS cost_per_payer,
    cm.revenue_30d,
    round(cm.revenue_30d / s.spend_usd, 2)              AS roas_30d,
    cm.revenue_to_date,
    round(cm.revenue_to_date / s.spend_usd, 2)          AS roas_to_date
FROM cm
LEFT JOIN an.marketing_spend s
       ON s.month = cm.month
      AND s.channel = cm.channel
ORDER BY cm.channel, cm.month;

-- name: channel_summary
WITH c AS (
    SELECT
        channel,
        count(*)                  AS installs,
        avg(onboarded_24h::int)   AS onboarding,
        avg(active_d1::int)       AS d1,
        avg(active_w1::int)       AS w1,
        avg(started_trial::int)   AS trial,
        sum(is_payer::int)        AS payers,
        sum(revenue_30d)          AS revenue_30d,
        sum(revenue_total)        AS revenue_to_date
    FROM an.user_facts
    GROUP BY channel
),
s AS (
    SELECT channel, sum(spend_usd) AS spend
    FROM an.marketing_spend
    GROUP BY channel
)
SELECT
    c.channel,
    s.spend,
    c.installs,
    round(s.spend / c.installs, 2)                      AS cpi,
    round(100 * c.onboarding, 1)                        AS onboarding_pct,
    round(100 * c.d1, 1)                                AS d1_pct,
    round(100 * c.w1, 1)                                AS w1_pct,
    round(100 * c.trial, 1)                             AS trial_pct,
    c.payers,
    round(100.0 * c.payers / c.installs, 1)             AS payer_pct,
    round(s.spend / nullif(c.payers, 0), 2)             AS cost_per_payer,
    round(c.revenue_30d / c.installs, 2)                AS revenue_30d_per_install,
    round(c.revenue_30d / s.spend, 2)                   AS roas_30d,
    round(c.revenue_to_date / s.spend, 2)               AS roas_to_date
FROM c
LEFT JOIN s USING (channel)
ORDER BY s.spend DESC NULLS LAST;

-- name: paid_social_monthly_change
-- Descriptive ratio of month-over-month changes; NOT causal marginal/incremental CPI.
WITH m AS (
    SELECT
        u.signup_month                AS month,
        s.spend_usd                   AS spend,
        count(*)                      AS installs,
        sum(u.is_payer::int)          AS payers,
        sum(u.revenue_30d)            AS revenue_30d
    FROM an.user_facts u
    JOIN an.marketing_spend s
      ON s.month = u.signup_month
     AND s.channel = u.channel
    WHERE u.channel = 'paid_social'
    GROUP BY u.signup_month, s.spend_usd
)
SELECT
    month,
    spend,
    installs,
    round(spend / installs, 2)                                                   AS avg_cpi,
    round((spend - lag(spend) OVER w) / nullif(installs - lag(installs) OVER w, 0), 2) AS spend_change_per_install_change,
    payers,
    round(spend / nullif(payers, 0), 2)                                          AS avg_cost_per_payer,
    round(revenue_30d / spend, 2)                                                AS roas_30d
FROM m
WINDOW w AS (ORDER BY month)
ORDER BY month;

-- name: channel_month_ios
-- The same quality metrics on iOS only, as a descriptive sensitivity check alongside the Android
-- onboarding decline around 2026-08-15 (see 03_ceo_august_cohort.sql).
SELECT
    signup_month                                AS month,
    channel,
    count(*)                                    AS installs,
    sum(is_payer::int)                           AS payers,
    round(100.0 * avg(onboarded_24h::int), 1)   AS onboarding_pct,
    round(100.0 * avg(active_w1::int), 1)       AS w1_pct,
    round(100.0 * avg(started_trial::int), 1)   AS trial_pct,
    round(100.0 * avg(is_payer::int), 1)        AS payer_pct
FROM an.user_facts
WHERE platform = 'ios'
GROUP BY signup_month, channel
ORDER BY channel, signup_month;
