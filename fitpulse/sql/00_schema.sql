-- FitPulse test assignment — raw schema (PostgreSQL 16).
-- analysis/run_sql.py creates these tables and loads data/*.csv with COPY.
-- To load by hand from psql instead, run this file and then the \copy lines at the bottom.

DROP SCHEMA IF EXISTS raw CASCADE;
CREATE SCHEMA raw;

CREATE TABLE raw.users (
    user_id    text PRIMARY KEY,
    signup_ts  timestamp NOT NULL,          -- UTC
    platform   text,
    country    text,
    channel    text,
    ab_group   text                         -- 'A' / 'B' only for users in the paywall test
);

CREATE TABLE raw.events (
    event_id   bigint,                      -- NOT unique in the export: 648 rows are exact duplicates
    user_id    text,                        -- 40 rows have no user_id
    event_name text,
    event_ts   timestamp                    -- UTC
);

CREATE TABLE raw.payments (
    payment_id integer PRIMARY KEY,
    user_id    text,
    payment_ts timestamp,                   -- UTC
    plan       text,                        -- monthly / annual
    payment_type text,                      -- purchase / renewal / refund
    amount_usd numeric(10, 2)               -- refunds are negative
);

CREATE TABLE raw.marketing_spend (
    month      text,                        -- 'YYYY-MM'
    channel    text,
    spend_usd  numeric(12, 2)
);

-- \copy raw.users           FROM 'data/users.csv'           WITH (FORMAT csv, HEADER true)
-- \copy raw.events          FROM 'data/events.csv'          WITH (FORMAT csv, HEADER true)
-- \copy raw.payments        FROM 'data/payments.csv'        WITH (FORMAT csv, HEADER true)
-- \copy raw.marketing_spend FROM 'data/marketing_spend.csv' WITH (FORMAT csv, HEADER true)
