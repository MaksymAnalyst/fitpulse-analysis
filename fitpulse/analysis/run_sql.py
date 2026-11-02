"""Load the CSVs into PostgreSQL and run every SQL file in sql/.

Each "-- name: <result>" block in sql/02_*.sql and later files is executed and saved to
output/<file stem>__<result>.csv. Files without name blocks (00, 01) are run as DDL.

Database: $DATABASE_URL if set, otherwise a throwaway local PostgreSQL started with the
`pgserver` package (pip install pgserver) in .pgdata/.
"""
import csv
import os
import re
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR, DATA_DIR, OUT_DIR = ROOT / "sql", ROOT / "data", ROOT / "output"
TABLES = ["users", "events", "payments", "marketing_spend"]


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        import pgserver
        url = pgserver.get_server(str(ROOT / ".pgdata"), cleanup_mode=None).get_uri()
    return psycopg.connect(url, autocommit=True)


def load_raw(cur):
    cur.execute((SQL_DIR / "00_schema.sql").read_text(encoding="utf-8"))
    for table in TABLES:
        with open(DATA_DIR / f"{table}.csv", encoding="utf-8") as f, \
                cur.copy(f"COPY raw.{table} FROM STDIN WITH (FORMAT csv, HEADER true)") as copy:
            copy.write(f.read())
        cur.execute(f"SELECT count(*) FROM raw.{table}")
        print(f"loaded raw.{table}: {cur.fetchone()[0]} rows")


def named_blocks(sql_text):
    parts = re.split(r"^-- name:\s*(\w+)\s*$", sql_text, flags=re.M)
    return list(zip(parts[1::2], parts[2::2]))


def run_file(cur, path):
    text = path.read_text(encoding="utf-8")
    blocks = named_blocks(text)
    if not blocks:
        cur.execute(text)
        print(f"ran {path.name}")
        return
    for name, query in blocks:
        cur.execute(query)
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
        out = OUT_DIR / f"{path.stem}__{name}.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        print(f"{path.name} :: {name} -> {out.name} ({len(rows)} rows)")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    only = sys.argv[1:]  # optional: run only files whose name starts with these prefixes
    with connect() as conn, conn.cursor() as cur:
        load_raw(cur)
        for path in sorted(SQL_DIR.glob("*.sql")):
            if path.name == "00_schema.sql":
                continue
            if only and path.name != "01_clean.sql" and not path.name.startswith(tuple(only)):
                continue
            run_file(cur, path)


if __name__ == "__main__":
    main()
