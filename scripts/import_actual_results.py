# -*- coding: utf-8 -*-
"""导入「实际运行结果」Excel：日前/实时统一结算价 → daily_curves
文件结构：企业名称 | 数据项 | 00:00 ... 23:00（转置结构，24 列时段）
数据项行：日前统一结算价 / 实时统一结算价（实际用电量不再导入，2026-08-31 起）
铁律：UPSERT + COALESCE 空值保护，不覆盖 DB 已存在值；精度 电价 2 位。
"""
import os, re, glob, time, openpyxl
from urllib.parse import quote, unquote

CRED = os.path.expanduser(r'~/.workbuddy/db_secret.txt')
REF = 'kputrrbbcmxbnhwhxvoo'
SRC_DIR = r'D:/A广交数据'

ROW_DA = '日前统一结算价'
ROW_RT = '实时统一结算价'


def build_url():
    txt = open(CRED, encoding='utf-8').read()
    pw_raw = re.search(r'password=([A-Za-z0-9*#%]+)', txt).group(1).strip()
    pw = unquote(pw_raw) if '%' in pw_raw else pw_raw
    return f'postgresql://{quote("postgres." + REF)}:{quote(pw)}@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres'


def parse_file(f):
    """返回 (date, [(hour, da, rt), ...], skip_reason)"""
    name = os.path.basename(f)
    m = re.search(r'\((\d{4}-\d{2}-\d{2})\)', name)
    if not m or '实际运行结果' not in name:
        return None, [], '非实际运行结果或无日期'
    date = m.group(1)
    wb = openpyxl.load_workbook(f, data_only=True)
    ws = wb[wb.sheetnames[0]]

    # 第一行表头：企业名称 | 数据项 | 00:00 ... 23:00
    header = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    hours = []
    for h in header[2:]:
        if h is None or ':' not in str(h):
            hours.append(None)
            continue
        try:
            hours.append(int(str(h).strip().split(':')[0]))
        except ValueError:
            hours.append(None)

    # 按数据项名定位行
    rows_map = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[1] is None:
            continue
        item = str(r[1]).strip()
        rows_map[item] = r

    def get_row(keyword):
        for k, v in rows_map.items():
            if keyword in k:
                return v
        return None

    row_da, row_rt = get_row(ROW_DA), get_row(ROW_RT)
    if row_da is None or row_rt is None:
        return date, [], f'缺行(日前={row_da is not None}, 实时={row_rt is not None})'

    def num(v, nd):
        if v is None or str(v).strip() == '':
            return None
        try:
            return round(float(v), nd)
        except ValueError:
            return None

    out = []
    for i, hour in enumerate(hours):
        if hour is None:
            continue
        da = num(row_da[2 + i], 2) if row_da else None
        rt = num(row_rt[2 + i], 2) if row_rt else None
        if da is None and rt is None:
            continue  # 双空跳过，保留 DB 原值
        out.append((hour, da, rt))
    if not out:
        return date, [], '文件为空/全时段无数据'
    return date, out, None


def main():
    import psycopg2
    files = sorted(glob.glob(os.path.join(SRC_DIR, '实际运行结果*.xlsx')))
    print(f'扫描 {SRC_DIR}: 找到 {len(files)} 个实际运行结果文件\n')

    if not files:
        print('未找到实际运行结果文件，退出')
        return

    conn = psycopg2.connect(build_url(), sslmode='require', connect_timeout=20)
    conn.autocommit = True
    cur = conn.cursor()

    # DB 日期范围
    cur.execute('SELECT MIN(date), MAX(date) FROM public.daily_curves')
    db_min, db_max = cur.fetchone()
    print(f'daily_curves 日期范围: {db_min} ~ {db_max}\n')

    report = []
    for f in files:
        fname = os.path.basename(f)
        date, rows, err = parse_file(f)
        if date is None or err:
            report.append((fname, f'跳过：{err}', '-', '-', '-'))
            print(f'[跳过] {fname}: {err}')
            continue

        # 日期范围检查
        if date < str(db_min) or date > str(db_max):
            report.append((fname, '日期超出范围跳过', date, '-', '-'))
            print(f'[超出范围] {fname}: {date}')
            continue

        # 导入前 DB 现状
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE day_ahead_price IS NULL),
                   COUNT(*) FILTER (WHERE real_time_price IS NULL)
            FROM public.daily_curves WHERE date = %s
        """, (date,))
        da_null, rt_null = cur.fetchone()

        # UPSERT（COALESCE 空值保护）
        da_put = rt_put = 0
        for hour, da, rt in rows:
            cur.execute("""
                INSERT INTO public.daily_curves (date, hour, day_ahead_price, real_time_price)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (date, hour) DO UPDATE
                SET day_ahead_price = COALESCE(EXCLUDED.day_ahead_price, public.daily_curves.day_ahead_price),
                    real_time_price = COALESCE(EXCLUDED.real_time_price, public.daily_curves.real_time_price)
            """, (date, hour, da, rt))
            if da is not None:
                da_put += 1
            if rt is not None:
                rt_put += 1

        report.append((fname, '已更新', date, f'日前{da_put}/24', f'实时{rt_put}/24'))
        print(f'[更新] {fname}: {date} 日前{da_put} 实时{rt_put}'
              f' (导入前空: 日前{da_null} 实时{rt_null})')

    # 复核
    print('\n--- 复核 (date | 日前空 | 实时空) ---')
    for fname, status, date, *_ in report:
        if status != '已更新':
            continue
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE day_ahead_price IS NULL),
                   COUNT(*) FILTER (WHERE real_time_price IS NULL)
            FROM public.daily_curves WHERE date = %s
        """, (date,))
        r = cur.fetchone()
        print(f'  {date}: 日前空={r[0]} 实时空={r[1]}')

    cur.close()
    conn.close()

    print('\n=== 导入报告 ===')
    print('文件 | 状态 | 日期 | 日前 | 实时')
    for r in report:
        print(' | '.join(r))
    print('=== END ===')


if __name__ == '__main__':
    main()
