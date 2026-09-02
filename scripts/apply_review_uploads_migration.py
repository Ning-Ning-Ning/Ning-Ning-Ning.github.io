# -*- coding: utf-8 -*-
"""执行 20260902_review_uploads.sql：复盘表上传相关表 + RLS + Storage 桶（幂等）"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import psycopg2

CRED = r"C:\Users\ningning2.song\.workbuddy\db_secret.txt"
SQL = r"C:\Users\ningning2.song\WorkBuddy\2026-07-27-13-49-01\Ning-Ning-Ning.github.io\supabase\migrations\20260902_review_uploads.sql"

secret = {}
with open(CRED, "r", encoding="utf-8") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            secret[k] = v

with open(SQL, "r", encoding="utf-8") as f:
    sql = f.read()

conn = psycopg2.connect(
    host="aws-1-ap-northeast-1.pooler.supabase.com",
    port=5432, dbname="postgres",
    user="postgres.kputrrbbcmxbnhwhxvoo", password=secret["password"],
    sslmode="require", connect_timeout=15,
)
conn.autocommit = False
cur = conn.cursor()
try:
    cur.execute(sql)
    conn.commit()
    print("OK: 迁移执行成功")
except Exception as e:
    conn.rollback()
    print("FAIL:", e)
    raise

# 复核：表、policy、bucket
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema='public' AND table_name LIKE 'review_%' ORDER BY 1
""")
print("表:", [r[0] for r in cur.fetchall()])
cur.execute("""
    SELECT tablename, policyname FROM pg_policies
    WHERE schemaname='public' AND tablename LIKE 'review_%' ORDER BY 1,2
""")
for r in cur.fetchall():
    print("policy:", r)
cur.execute("""
    SELECT policyname FROM pg_policies
    WHERE schemaname='storage' AND tablename='objects' AND policyname LIKE 'rvo%' ORDER BY 1
""")
print("storage policy:", [r[0] for r in cur.fetchall()])
cur.execute("SELECT id, public FROM storage.buckets WHERE id='review-uploads'")
print("bucket:", cur.fetchall())
cur.close(); conn.close()
