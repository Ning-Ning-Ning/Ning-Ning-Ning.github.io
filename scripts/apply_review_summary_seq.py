# -*- coding: utf-8 -*-
# 直连执行迁移：20260904_review_summary_seq.sql（Supavisor 池）
import re, psycopg2
from pathlib import Path

CRED = Path.home() / ".workbuddy" / "db_secret.txt"
password = re.search(r"password=(.+)", CRED.read_text(encoding="utf-8")).group(1).strip()
sql = (Path(__file__).resolve().parent.parent / "supabase" / "migrations" / "20260904_review_summary_seq.sql").read_text(encoding="utf-8")

conn = psycopg2.connect(host="aws-1-ap-northeast-1.pooler.supabase.com", port=5432,
                        user="postgres.kputrrbbcmxbnhwhxvoo", password=password, dbname="postgres",
                        connect_timeout=30)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute(sql)
    cur.execute("""select column_name, is_nullable from information_schema.columns
                   where table_schema='public' and table_name='review_summary' order by ordinal_position""")
    print("columns:", cur.fetchall())
    cur.execute("""select constraint_name from information_schema.table_constraints
                   where table_schema='public' and table_name='review_summary' and constraint_type='PRIMARY KEY'""")
    print("pk:", cur.fetchall())
    cur.execute("select count(*), count(seq), count(distinct seq) from public.review_summary where username='songningning' and month='2026-08'")
    print("songningning 2026-08 rows/seq/nonnull-distinct:", cur.fetchone())
conn.close()
print("DONE")
