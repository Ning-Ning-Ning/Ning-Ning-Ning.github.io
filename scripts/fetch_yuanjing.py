#!/usr/bin/env python3
"""远景（Envision）气象数据每日同步：预测 + 实际补齐。"""
import argparse
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import requests
from psycopg2.extras import execute_values

CRED_PATH = Path(os.environ.get('TEMP', '/tmp')) / 'yuanjing_cred.txt'
SECRET_PATH = Path.home() / '.workbuddy' / 'db_secret.txt'
OLD_SECRET_PATH = Path.home() / '.workbuddy' / 'memory' / '5c4ce15d-fb3a-4861-92fd-f47a27bc1fcf_memory.md'

API_URL = 'https://app-portal-cn5.envisioniot.com/kongming/weather-zuul/api/weather/api/hourly/forecast'
SOURCE = 'yuanjing'
VARS = ['TMP', 'RAINFALL', 'WS', 'GHI']

DB_HOST = 'aws-1-ap-northeast-1.pooler.supabase.com'
DB_PORT = 5432
DB_NAME = 'postgres'
DB_USER = 'postgres.kputrrbbcmxbnhwhxvoo'


def read_db_password():
    path = SECRET_PATH if SECRET_PATH.exists() else OLD_SECRET_PATH
    if not path.exists():
        raise FileNotFoundError(f'找不到 Supabase 密码文件: {SECRET_PATH} 或 {OLD_SECRET_PATH}')
    text = path.read_text(encoding='utf-8')
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('password='):
            return urllib.parse.unquote(line.split('=', 1)[1])
    raise ValueError('密码文件中未找到 password= 行')


def db_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=read_db_password()
    )


def read_cred():
    if not CRED_PATH.exists():
        return None, None
    lines = CRED_PATH.read_text(encoding='utf-8').strip().splitlines()
    auth = lines[0].split('=', 1)[1] if lines and lines[0].startswith('authorization=') else None
    cookie = lines[1].split('=', 1)[1] if len(lines) > 1 and lines[1].startswith('cookie=') else None
    return auth, cookie


def save_cred(authorization, cookie):
    CRED_PATH.write_text(f'authorization={authorization}\ncookie={cookie}\n', encoding='utf-8')


def probe_token(auth, cookie):
    """GET + length=24 探测 token 是否有效。"""
    if not auth or not cookie:
        return False
    tomorrow = date.today() + timedelta(days=1)
    start_time = f'{tomorrow}T16:00:00.000Z'
    params = {
        'isRepeat': 'true',
        'datatype': 'weatherHourly',
        'time': str(int(datetime.now().timestamp() * 1000)),
        'startTime': start_time,
        'sourceAttributes': 'TMP',
        'longitude': '113.28',
        'latitude': '23.13',
        'length': '24',
    }
    headers = {'authorization': auth, 'cookie': cookie}
    try:
        r = requests.get(API_URL, params=params, headers=headers, timeout=30)
        if r.status_code in (401, 403):
            return False
        # 其他 4xx（如 400 length 不足）说明 token 本身有效
        return r.status_code < 500 and isinstance(r.json(), dict)
    except Exception:
        return False


def do_login():
    login_script = Path(__file__).with_name('yuanjing_login.py')
    if not login_script.exists():
        raise FileNotFoundError(f'登录脚本不存在: {login_script}')
    print('凭证失效或不存在，启动自动登录...')
    result = subprocess.run(
        [sys.executable, str(login_script)],
        capture_output=True, text=True, encoding='utf-8'
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f'自动登录失败，退出码 {result.returncode}')
    return read_cred()


def ensure_login():
    auth, cookie = read_cred()
    if probe_token(auth, cookie):
        return auth, cookie, False
    auth, cookie = do_login()
    if probe_token(auth, cookie):
        return auth, cookie, True
    # 偶发 401，再登录一次
    time.sleep(2)
    auth, cookie = do_login()
    if not probe_token(auth, cookie):
        raise RuntimeError('二次登录后 token 仍无效')
    return auth, cookie, True


def fetch_data(auth, cookie, start_dt: date, length_hours: int):
    """start_dt 北京日期 -> 对应 UTC 16:00 作为 startTime。"""
    start_time = f'{start_dt}T16:00:00.000Z'
    params = {
        'isRepeat': 'true',
        'datatype': 'weatherHourly',
        'time': str(int(datetime.now().timestamp() * 1000)),
        'startTime': start_time,
        'sourceAttributes': ','.join(VARS),
        'longitude': '113.28',
        'latitude': '23.13',
        'length': str(length_hours),
    }
    headers = {'authorization': auth, 'cookie': cookie}
    r = requests.get(API_URL, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError(f'返回格式异常: {data}')
    return data


def parse_flat_json(data: dict, base_date: date):
    """扁平 JSON：base_date 次日 00:00（北京）为第 0 个点（= base_date 16:00Z）。

    2026-09-16 实测定标：startTime=<D>T16:00:00.000Z 时，第 0 点 = D+1 日 00:00 北京。
    探针证据：GHI 零点在 idx0-6、峰值 idx13（13:00）、TMP 最低 idx6、最高 idx14。
    """
    present_vars = [v for v in VARS if v in data and isinstance(data[v], list)]
    if not present_vars:
        return []
    length = min(len(data[v]) for v in present_vars)
    rows = []
    # API 实际语义：startTime 日期 16:00Z（= 次日 00:00 北京）为第 0 个点
    start_dt = datetime(base_date.year, base_date.month, base_date.day, 16, 0, 0, tzinfo=timezone.utc)
    for i in range(length):
        target = start_dt + timedelta(hours=i)
        target_date = target.astimezone(timezone(timedelta(hours=8))).date()
        target_hour = target.astimezone(timezone(timedelta(hours=8))).hour
        for var in present_vars:
            val = data[var][i]
            if val is None:
                continue
            rows.append((target_date, target_hour, var, float(val)))
    return rows


def upsert_forecast(rows, forecast_date: date):
    """rows: [(target_date, hour, var, value), ...]"""
    if not rows:
        return 0
    conn = db_conn()
    cur = conn.cursor()
    values = [(SOURCE, forecast_date, r[0], r[1], r[2], r[3]) for r in rows]
    execute_values(
        cur,
        '''INSERT INTO weather_forecast (source, forecast_date, target_date, hour, var, value)
           VALUES %s
           ON CONFLICT (source, forecast_date, target_date, hour, var)
           DO UPDATE SET value = EXCLUDED.value''',
        values, page_size=500
    )
    conn.commit()
    cur.close()
    conn.close()
    return len(values)


def upsert_obs(rows, obs_date: date):
    if not rows:
        return 0
    conn = db_conn()
    cur = conn.cursor()
    values = [(SOURCE, obs_date, r[1], r[2], r[3]) for r in rows]
    execute_values(
        cur,
        '''INSERT INTO weather_obs (source, obs_date, hour, var, value)
           VALUES %s
           ON CONFLICT (source, obs_date, hour, var)
           DO UPDATE SET value = EXCLUDED.value''',
        values, page_size=500
    )
    conn.commit()
    cur.close()
    conn.close()
    return len(values)


def get_existing_obs_dates(start: date, end: date):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        'SELECT obs_date FROM weather_obs WHERE source=%s AND obs_date BETWEEN %s AND %s GROUP BY obs_date HAVING COUNT(DISTINCT hour)=24 AND COUNT(DISTINCT var)=4',
        (SOURCE, start, end)
    )
    existing = {r[0] for r in cur.fetchall()}
    cur.close()
    conn.close()
    return existing


def sync_forecast(auth, cookie, fc_start: date):
    data = fetch_data(auth, cookie, fc_start, 480)
    rows = parse_flat_json(data, fc_start)
    inserted = upsert_forecast(rows, fc_start)
    return inserted


def sync_obs(auth, cookie, obs_start: date, obs_end: date):
    existing = get_existing_obs_dates(obs_start, obs_end)
    total = 0
    filled_dates = []
    skipped = []
    current = obs_start
    while current <= obs_end:
        segment_end = min(current + timedelta(days=2), obs_end)
        segment_dates = [current + timedelta(days=i) for i in range((segment_end - current).days + 1)]
        if all(d in existing for d in segment_dates):
            skipped.extend(segment_dates)
            current = segment_end + timedelta(days=1)
            continue
        api_start = current - timedelta(days=2)
        data = fetch_data(auth, cookie, api_start, 72)
        rows = parse_flat_json(data, api_start)
        # 按 obs_date 分组入库
        by_date = {}
        for r in rows:
            by_date.setdefault(r[0], []).append(r)
        for d, drows in by_date.items():
            if obs_start <= d <= obs_end:
                total += upsert_obs(drows, d)
                filled_dates.append(d)
        current = segment_end + timedelta(days=1)
        time.sleep(1.2)
    return total, filled_dates, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fc-start', type=date.fromisoformat, default=date.today())
    parser.add_argument('--fc-end', type=date.fromisoformat, default=None)
    parser.add_argument('--obs-start', type=date.fromisoformat, default=date(2026, 7, 1))
    parser.add_argument('--obs-end', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    auth, cookie, relogin = ensure_login()
    fc_inserted = sync_forecast(auth, cookie, args.fc_start)
    time.sleep(1.2)
    obs_inserted, filled, skipped = sync_obs(auth, cookie, args.obs_start, args.obs_end)

    print(f'重新登录: {"是" if relogin else "否"}')
    print(f'预测入库: {fc_inserted} 行，起报日 {args.fc_start}')
    print(f'实际补齐: {sorted(set(filled))} 共 {len(set(filled))} 天 {obs_inserted} 行')
    print(f'跳过日期: {len(set(skipped))} 天')
    print('失败项: 无')


if __name__ == '__main__':
    main()
