#!/usr/bin/env python3
"""Apply the price migration and sync Excel rows to daily_curves through PostgreSQL."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

from import_excel import read_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel", type=Path)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--migration", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise SystemExit("缺少 DATABASE_URL")
    records = read_records(args.excel)
    values = [
        (
            row["date"],
            row["hour"],
            row["actual_value"],
            row["predicted_value"],
            row["adjusted_value"],
            row["day_ahead_price"],
            row["real_time_price"],
        )
        for row in records
    ]
    sql = """
        INSERT INTO public.daily_curves
          (date, hour, actual_value, predicted_value, adjusted_value,
           day_ahead_price, real_time_price)
        VALUES %s
        ON CONFLICT (date, hour) DO UPDATE SET
          actual_value = EXCLUDED.actual_value,
          predicted_value = EXCLUDED.predicted_value,
          adjusted_value = EXCLUDED.adjusted_value,
          day_ahead_price = EXCLUDED.day_ahead_price,
          real_time_price = EXCLUDED.real_time_price,
          updated_at = now()
    """
    with psycopg2.connect(args.database_url, sslmode="require", connect_timeout=20) as conn:
        with conn.cursor() as cur:
            cur.execute(args.migration.read_text(encoding="utf-8"))
            execute_values(cur, sql, values, page_size=500)
            cur.execute(
                """
                SELECT count(*), min(date), max(date),
                       count(day_ahead_price), count(real_time_price)
                FROM public.daily_curves
                """
            )
            print("数据库校验：", cur.fetchone())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
