# -*- coding: utf-8 -*-
# 直连执行迁移：20260903_review_lt_tables.sql（Supavisor 池，postgres 角色不受 RLS 限制）
import re, psycopg2
from pathlib import Path

CRED = Path.home() / ".workbuddy" / "db_secret.txt"
password = re.search(r"password=(.+)", CRED.read_text(encoding="utf-8")).group(1).strip()
sql = (Path(__file__).resolve().parent.parent / "supabase" / "migrations" / "20260903_review_lt_tables.sql").read_text(encoding="utf-8")

conn = psycopg2.connect(host="aws-1-ap-northeast-1.pooler.supabase.com", port=5432,
                        user="postgres.kputrrbbcmxbnhwhxvoo", password=password, dbname="postgres",
                        connect_timeout=30)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute(sql)
    for t in ("review_holding", "review_holding_summary", "review_trades", "review_trades_summary"):
        cur.execute("select count(*) from information_schema.tables where table_schema='public' and table_name=%s", (t,))
        ok_t = cur.fetchone()[0] == 1
        cur.execute("select count(*) from pg_policies where schemaname='public' and tablename=%s", (t,))
        print(t, "exists:", ok_t, "policies:", cur.fetchone()[0])
conn.close()
print("DONE")
