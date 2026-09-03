# -*- coding: utf-8 -*-
# 直连执行 20260903_review_summary_ord.sql 并复核
import re
from pathlib import Path

import psycopg2

BASE = Path(__file__).resolve().parent.parent
CRED = Path.home() / ".workbuddy" / "db_secret.txt"
text = CRED.read_text(encoding="utf-8")
password = re.search(r"password=(.+)", text).group(1).strip()
ref = "kputrrbbcmxbnhwhxvoo"

sql = (BASE / "supabase" / "migrations" / "20260903_review_summary_ord.sql").read_text(encoding="utf-8")
conn = psycopg2.connect(
    host="aws-1-ap-northeast-1.pooler.supabase.com", port=5432,
    dbname="postgres", user=f"postgres.{ref}", password=password,
)
cur = conn.cursor()
cur.execute(sql)
conn.commit()
cur.execute("""select column_name, data_type from information_schema.columns
               where table_schema='public' and table_name='review_summary' order by ordinal_position""")
print("columns:", cur.fetchall())
cur.close(); conn.close()
print("DONE")
