-- Part 1. Weekly cohort retention (PostgreSQL).
--   cohort      = ISO week of signup (Monday start), UTC
--   week N      = days [7N, 7N+7) after the user's own signup_ts
--   retained    = at least one session_start in week N
--   censoring   = a cell is shown only when every user of the cohort has been observed for the
--                 whole of week N (latest possible signup = cohort start + 7 days; data ends
--                 2026-10-01 00:00). Incomplete cells are NULL, so no cohort is penalised for
--                 being young.
-- Each "-- name:" block is one result set; analysis/run_sql.py saves it to output/.

-- name: retention_long
WITH cohorts AS (
    SELECT user_id, signup_ts, date_trunc('week', signup_ts)::date AS cohort_week
    FROM an.users
),
cohort_size AS (
    SELECT cohort_week, count(*) AS cohort_users
    FROM cohorts
    GROUP BY cohort_week
),
activity AS (
    SELECT DISTINCT
        c.cohort_week,
        c.user_id,
        floor(extract(epoch FROM e.event_ts - c.signup_ts) / (7 * 86400))::int AS week_n
    FROM cohorts c
    JOIN an.events e
      ON e.user_id = c.user_id
     AND e.event_name = 'session_start'
),
grid AS (
    SELECT
        cs.cohort_week,
        cs.cohort_users,
        w.week_n,
        cs.cohort_week + interval '7 days' + (w.week_n + 1) * interval '7 days'
            <= timestamp '2026-10-01'                                   AS is_complete
    FROM cohort_size cs
    CROSS JOIN generate_series(0, 12) AS w(week_n)
)
SELECT
    g.cohort_week,
    g.cohort_users,
    g.week_n,
    count(a.user_id)                                                    AS active_users,
    CASE WHEN g.is_complete
         THEN round(100.0 * count(a.user_id) / g.cohort_users, 1) END   AS retention_pct
FROM grid g
LEFT JOIN activity a
       ON a.cohort_week = g.cohort_week
      AND a.week_n      = g.week_n
GROUP BY g.cohort_week, g.cohort_users, g.week_n, g.is_complete
ORDER BY g.cohort_week, g.week_n;

-- name: retention_table
-- The same numbers pivoted into the classic triangle (one row per cohort, % retained).
WITH cohorts AS (
    SELECT user_id, signup_ts, date_trunc('week', signup_ts)::date AS cohort_week
    FROM an.users
),
cohort_size AS (
    SELECT cohort_week, count(*) AS cohort_users
    FROM cohorts
    GROUP BY cohort_week
),
activity AS (
    SELECT DISTINCT
        c.cohort_week,
        c.user_id,
        floor(extract(epoch FROM e.event_ts - c.signup_ts) / (7 * 86400))::int AS week_n
    FROM cohorts c
    JOIN an.events e
      ON e.user_id = c.user_id
     AND e.event_name = 'session_start'
),
cells AS (
    SELECT
        cs.cohort_week,
        cs.cohort_users,
        w.week_n,
        CASE WHEN cs.cohort_week + interval '7 days' + (w.week_n + 1) * interval '7 days'
                  <= timestamp '2026-10-01'
             THEN round(100.0 * count(a.user_id) / cs.cohort_users, 1) END AS retention_pct
    FROM cohort_size cs
    CROSS JOIN generate_series(0, 12) AS w(week_n)
    LEFT JOIN activity a
           ON a.cohort_week = cs.cohort_week
          AND a.week_n      = w.week_n
    GROUP BY cs.cohort_week, cs.cohort_users, w.week_n
)
SELECT
    cohort_week,
    cohort_users,
    max(retention_pct) FILTER (WHERE week_n = 0)  AS w0,
    max(retention_pct) FILTER (WHERE week_n = 1)  AS w1,
    max(retention_pct) FILTER (WHERE week_n = 2)  AS w2,
    max(retention_pct) FILTER (WHERE week_n = 3)  AS w3,
    max(retention_pct) FILTER (WHERE week_n = 4)  AS w4,
    max(retention_pct) FILTER (WHERE week_n = 5)  AS w5,
    max(retention_pct) FILTER (WHERE week_n = 6)  AS w6,
    max(retention_pct) FILTER (WHERE week_n = 7)  AS w7,
    max(retention_pct) FILTER (WHERE week_n = 8)  AS w8,
    max(retention_pct) FILTER (WHERE week_n = 9)  AS w9,
    max(retention_pct) FILTER (WHERE week_n = 10) AS w10,
    max(retention_pct) FILTER (WHERE week_n = 11) AS w11,
    max(retention_pct) FILTER (WHERE week_n = 12) AS w12
FROM cells
GROUP BY cohort_week, cohort_users
ORDER BY cohort_week;
