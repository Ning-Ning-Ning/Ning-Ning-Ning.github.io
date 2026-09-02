# -*- coding: utf-8 -*-
"""新增 Auth 账号 zhangqiong@curve.local（幂等：已存在则跳过）"""
import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import psycopg2

CRED = r"C:\Users\ningning2.song\.workbuddy\db_secret.txt"
secret = {}
with open(CRED, "r", encoding="utf-8") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            secret[k] = v

conn = psycopg2.connect(
    host="aws-1-ap-northeast-1.pooler.supabase.com",
    port=5432, dbname="postgres",
    user="postgres.kputrrbbcmxbnhwhxvoo", password=secret["password"],
    sslmode="require", connect_timeout=15,
)
cur = conn.cursor()

# 1. 查看现有账号形态（确认 identities 结构）
cur.execute("""
    SELECT u.email, count(i.id) AS ident_cnt
    FROM auth.users u LEFT JOIN auth.identities i ON i.user_id = u.id
    WHERE u.email LIKE '%%@curve.local'
    GROUP BY u.email ORDER BY u.email LIMIT 3
""")
print("现有账号样例（email, identities 数）:", cur.fetchall())

# 2. 检查 zhangqiong 是否已存在
cur.execute("SELECT id FROM auth.users WHERE email='zhangqiong@curve.local'")
row = cur.fetchone()
if row:
    print("SKIP: zhangqiong 已存在, id =", row[0])
else:
    cur.execute("""
        INSERT INTO auth.users (
            instance_id, id, aud, role, email, encrypted_password,
            email_confirmed_at, created_at, updated_at,
            raw_app_meta_data, raw_user_meta_data,
            confirmation_token, recovery_token, email_change, email_change_token_new
        )
        SELECT '00000000-0000-0000-0000-000000000000', gen_random_uuid(),
               'authenticated', 'authenticated', 'zhangqiong@curve.local',
               crypt('curve-zhangqiong-2026', gen_salt('bf')),
               now(), now(), now(),
               '{"provider":"email","providers":["email"]}'::jsonb, '{}'::jsonb,
               '', '', '', ''
        RETURNING id
    """)
    uid = cur.fetchone()[0]
    # 3. 补 auth.identities（缺这条会导致登录失败）
    cur.execute("""
        INSERT INTO auth.identities (
            id, user_id, provider_id, identity_data, provider,
            last_sign_in_at, created_at, updated_at
        )
        SELECT gen_random_uuid(), %s, 'email',
               jsonb_build_object('sub', %s::text, 'email', 'zhangqiong@curve.local'),
               'email', now(), now(), now()
    """, (uid, str(uid)))
    conn.commit()
    print("OK: zhangqiong 已创建, id =", uid)

# 4. 复核
cur.execute("""
    SELECT u.email, count(i.id)
    FROM auth.users u LEFT JOIN auth.identities i ON i.user_id=u.id
    WHERE u.email='zhangqiong@curve.local' GROUP BY u.email
""")
print("复核:", cur.fetchall())
cur.close(); conn.close()
