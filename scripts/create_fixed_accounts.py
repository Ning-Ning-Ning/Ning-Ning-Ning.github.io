#!/usr/bin/env python3
"""创建 12 个固定账号（仅用户名登录，密码由用户名派生，仓库内公开）。

用法：
  python scripts/create_fixed_accounts.py
需要环境变量：
  SUPABASE_URL   例如 https://kputrrbbcmxbnhwhxvoo.supabase.co
  SUPABASE_KEY   anon/publishable key（前端公开 key 即可，无敏感权限）
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

ACCOUNTS = [
    "gly",
    "wanliyang",
    "songningning",
    "zhangchenyue",
    "liangweiqi",
    "liubingyan",
    "liuziye",
    "luna",
    "songyihan",
    "wangyanshu",
    "xumanli",
    "zhengkezhuo",
]


def derive_password(username: str) -> str:
    return f"curve-{username}-2026"


def main() -> int:
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_KEY", "")
    if not base or not key:
        raise SystemExit("缺少 SUPABASE_URL 或 SUPABASE_KEY")
    url = f"{base}/auth/v1/signup"
    ok, skip, failed = [], [], []
    for username in ACCOUNTS:
        email = f"{username}@curve.local"
        body = json.dumps(
            {
                "email": email,
                "password": derive_password(username),
                "data": {"username": username},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "apikey": key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                user = payload.get("user") or {}
                print(f"OK   {username:14s} id={user.get('id')}")
                ok.append(username)
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:300]
            print(f"FAIL {username:14s} HTTP {err.code}: {detail}")
            if err.code in (422, 409):
                skip.append(username)  # 已存在（幂等）
            else:
                failed.append(username)
        except Exception as err:  # noqa: BLE001
            print(f"FAIL {username:14s} {type(err).__name__}: {err}")
            failed.append(username)
        time.sleep(0.4)  # 避免触发 Auth 速率限制

    print(f"\n成功 {len(ok)}，已存在 {len(skip)}，失败 {len(failed)}")
    if failed:
        print("失败账号：", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
