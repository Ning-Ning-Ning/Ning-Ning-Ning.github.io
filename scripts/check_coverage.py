"""巡天同步「缺口自检」
用法：
  python check_coverage.py [--days-back 14] [--json]
规则（用户 2026-11-09 确认）：
  - 抓取当日及之前 5 天没有电价属正常（数据源延迟 5 天），自检窗口截止到 today-5
  - 电价：daily_curves 每日应有 24 小时 × 日前/实时
  - 边界：boundary_actual / boundary_forecast 每日应有 24 小时 × 各变量
    （b_power 因 B 类电源口径特殊，仅提示不判缺口）
退出码：0 全部完整；2 存在缺口（便于定时任务判断）
"""
import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg2

HOME = Path.home() / ".workbuddy"
DB = dict(host="aws-1-ap-northeast-1.pooler.supabase.com", port=5432, dbname="postgres",
          user="postgres.kputrrbbcmxbnhwhxvoo", connect_timeout=20, sslmode="require")
HARD_VARS = ["td_load", "a_power", "local_power", "yuekong"]
SOFT_VARS = ["b_power"]


def db_password():
    for line in (HOME / "db_secret.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*password\s*=\s*(.+)", line)
        if m:
            return m.group(1).strip()
    raise SystemExit("db_secret.txt 缺少 password")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days-back", type=int, default=14, help="回溯天数（默认 14）")
    ap.add_argument("--end-offset", type=int, default=5, help="跳过最近 N 天（默认 5，含今天）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args()

    today = date.today()
    start = today - timedelta(days=a.days_back)
    end = today - timedelta(days=a.end_offset) - timedelta(days=1)  # 今天及前 N 天均视为正常延迟
    if start > end:
        print("自检窗口为空：days_back 需大于 end_offset")
        return 0

    conn = psycopg2.connect(password=db_password(), **DB)
    cur = conn.cursor()

    cur.execute("""
        select date,
               count(*) filter (where day_ahead_price is not null) as da,
               count(*) filter (where real_time_price is not null) as rt
        from public.daily_curves
        where date between %s and %s
        group by date
    """, (start, end))
    price = {str(d): (int(da), int(rt)) for d, da, rt in cur.fetchall()}

    bnd = {}
    for tab in ("boundary_actual", "boundary_forecast"):
        cur.execute(f"""
            select var, date, count(*) from public.{tab}
            where date between %s and %s group by var, date
        """, (start, end))
        for var, d, n in cur.fetchall():
            bnd.setdefault(tab, {}).setdefault(var, {})[str(d)] = int(n)

    cur.close()
    conn.close()

    gaps = []
    soft = []
    d = start
    while d <= end:
        ds = str(d)
        da, rt = price.get(ds, (0, 0))
        miss = []
        if da < 24:
            miss.append("日前电价 %d/24" % da)
        if rt < 24:
            miss.append("实时电价 %d/24" % rt)
        for tab in ("boundary_actual", "boundary_forecast"):
            for var in HARD_VARS:
                n = bnd.get(tab, {}).get(var, {}).get(ds, 0)
                if n < 24:
                    miss.append("%s.%s %d/24" % (tab.replace("boundary_", ""), var, n))
            for var in SOFT_VARS:
                n = bnd.get(tab, {}).get(var, {}).get(ds, 0)
                if n < 24:
                    soft.append("%s %s.%s %d/24" % (ds, tab.replace("boundary_", ""), var, n))
        if miss:
            gaps.append({"date": ds, "missing": miss})
        d += timedelta(days=1)

    result = {
        "window": [str(start), str(end)],
        "checked_days": (end - start).days + 1,
        "gap_days": len(gaps),
        "gaps": gaps,
        "soft_gaps": soft[:20],
    }

    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print("自检窗口: %s ~ %s（%d 天，已跳过最近 %d 天正常延迟）" % (start, end, result["checked_days"], a.end_offset))
        if not gaps:
            print("结果: 完整，无缺口 ✓")
        else:
            print("结果: 发现 %d 天存在缺口" % len(gaps))
            for g in gaps:
                print("  %s -> %s" % (g["date"], "；".join(g["missing"])))
            dates = [g["date"] for g in gaps]
            print("建议补抓: --start %s --end %s" % (dates[0], dates[-1]))
        if soft:
            print("提示（不判缺口）: %d 个 B 类电源空缺，如 %s" % (len(soft), soft[0]))
    return 0 if not gaps else 2


if __name__ == "__main__":
    sys.exit(main())
