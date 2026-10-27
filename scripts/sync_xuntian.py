# -*- coding: utf-8 -*-
"""
巡天（xuntian-cloud.tcl.com）市场行情 → Supabase 同步
  1) 统一出清电价（用户侧全省，日前/实时，24 点）→ daily_curves.day_ahead_price / real_time_price
     以巡天为准：巡天有值即覆盖；巡天无值不置空
  2) 电网运行数据（统调负荷/省内A类/地方电源/粤港联络线/省内B类，96 点→24 时段均值）
     日前→boundary_forecast，实时→boundary_actual，source='xuntian'；巡天无值不写
     例外：B类电源「预测」若与实际完全相同（巡天用实际回填），且库中已有该时段值，则不覆盖

登录：复用 ~/.workbuddy/xuntian_state.json；失效时自动短信验证码登录
     （取码接口凭据见 ~/.workbuddy/sms_secret.txt，只调用 get_sms_code）
用法：python sync_xuntian.py [--days N]   默认回溯 7 天 + 向后 3 天
凭据：数据库密码 ~/.workbuddy/db_secret.txt；本文件不含任何凭据
"""
import argparse, asyncio, datetime as dt, json, re, sys, time, urllib.request
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from playwright.async_api import async_playwright

HOME = Path.home() / ".workbuddy"
STATE = HOME / "xuntian_state.json"
LOGIN_URL = "https://xuntian-cloud.tcl.com/login"
DASH = "https://xuntian-cloud.tcl.com/saas-vpp/ElectricityTrade/DataAnalysis/MarketSituationDashboard"
API = "https://xuntian-cloud.tcl.com/xts_api/vpp_base/api/common/"
PROVINCE = "440000000000"
BND = {100: "td_load", 102: "a_power", 103: "local_power", 104: "yuekong", 105: "b_power"}
DB = dict(host="aws-1-ap-northeast-1.pooler.supabase.com", port=5432, dbname="postgres",
          user="postgres.kputrrbbcmxbnhwhxvoo", connect_timeout=20)


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def kv(path):
    d = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Za-z_]+)\s*=\s*(.+)", line)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def sms_poll(since_iso, cfg, timeout=60):
    body = json.dumps({"p_token": cfg["sms_token"], "p_since": since_iso}).encode()
    hdr = {"apikey": cfg["sms_apikey"], "Authorization": "Bearer " + cfg["sms_apikey"],
           "Content-Type": "application/json"}
    end = time.time() + timeout
    while time.time() < end:
        try:
            r = urllib.request.urlopen(urllib.request.Request(cfg["sms_url"], data=body, headers=hdr), timeout=10)
            d = json.loads(r.read().decode() or "null")
            d = d[0] if isinstance(d, list) and d else d
            if isinstance(d, dict) and d.get("code") and float(d.get("age_sec") or 0) <= 50:
                return str(d["code"])
        except Exception as e:
            log("取码请求异常:", type(e).__name__)
        time.sleep(1)
    return None


class Session:
    async def start(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(channel="msedge", headless=True)
        if STATE.exists() and await self._open(use_state=True):
            return
        log("登录态无效，执行短信验证码登录")
        await self._open(use_state=False)
        await self._sms_login()

    async def _open(self, use_state):
        if getattr(self, "ctx", None):
            await self.ctx.close()
        self.ctx = await self.browser.new_context(storage_state=str(STATE) if use_state else None)
        self.page = await self.ctx.new_page()
        self.auth = None

        def on_req(r):
            if "vpp_base" in r.url and r.headers.get("authorization"):
                self.auth = r.headers["authorization"]
        self.page.on("request", on_req)
        if not use_state:
            return False
        return await self._goto_dash()

    async def _goto_dash(self):
        await self.page.goto(DASH, wait_until="domcontentloaded", timeout=60000)
        for _ in range(40):
            if self.auth or "/login" in self.page.url:
                break
            await self.page.wait_for_timeout(1000)
        return bool(self.auth) and "/login" not in self.page.url

    async def _sms_login(self):
        cfg = kv(HOME / "sms_secret.txt")
        pg = self.page
        await pg.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(4000)
        await pg.click("text=验证码登录")
        await pg.wait_for_timeout(800)
        await pg.fill("input[placeholder='请输入手机号']", cfg["xuntian_phone"])
        t0 = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)).isoformat()
        await pg.click("button.code-btn")
        code = sms_poll(t0, cfg)
        if not code:
            raise SystemExit("60 秒内未取到短信验证码")
        await pg.fill("input[placeholder='请输入验证码']", code)
        await pg.click("button:has-text('登 录')")
        await pg.wait_for_timeout(6000)
        if "/login" in pg.url:
            raise SystemExit("验证码登录未成功")
        if not await self._goto_dash():
            raise SystemExit("登录后无法访问市场行情看板")
        await self.ctx.storage_state(path=str(STATE))
        log("短信验证码登录成功，登录态已保存")

    async def post(self, ep, body):
        for i in range(3):
            try:
                r = await self.ctx.request.post(API + ep, data=json.dumps(body), timeout=60000,
                                                headers={"authorization": self.auth, "content-type": "application/json"})
                j = await r.json()
                if j.get("retCode") == "T200":
                    return j.get("data") or []
                log("接口返回异常:", ep, j.get("retCode"), j.get("retMsg"))
            except Exception as e:
                log("接口请求失败:", ep, type(e).__name__)
            await asyncio.sleep(3)
        raise SystemExit(f"接口 {ep} 连续失败")

    async def close(self):
        try:
            await self.ctx.storage_state(path=str(STATE))
        except Exception:
            pass
        await self.browser.close()
        await self.pw.stop()


def chunks(start, end, step):
    d = start
    while d <= end:
        e = min(d + dt.timedelta(days=step - 1), end)
        yield d, e
        d = e + dt.timedelta(days=1)


async def fetch(start, end):
    s = Session()
    await s.start()
    price, bnd = {}, {}
    try:
        for a, b in chunks(start, end, 31):
            for it in await s.post("queryMarketClearElectricityPrice", {"provinceId": PROVINCE, "dataGranularityType": 5,
                                   "regulateType": 1, "startDate": str(a), "endDate": str(b)}):
                k = {1: 0, 2: 1}.get(it.get("spotMarketType"))
                if k is None:
                    continue
                for c in it.get("dateCurveDataList") or []:
                    m, arr = c["dataPointListMeta"], c.get("actualData") or []
                    if m.get("size") != 24 or len(arr) != 24 or not m["startDateTime"].endswith("00:00:00"):
                        continue
                    for h, v in enumerate(arr):
                        if v is not None:
                            price.setdefault((m["startDateTime"][:10], h), [None, None])[k] = float(v)
        for a, b in chunks(start, end, 10):
            for it in await s.post("queryMarketSupplyDemandOperationData", {"provinceId": PROVINCE,
                                   "marketSupplyAndDemandTypes": list(BND), "dataGranularityType": 6,
                                   "startDate": str(a), "endDate": str(b)}):
                var = BND.get(it.get("marketSupplyAndDemandType"))
                kind = {1: "f", 2: "a"}.get(it.get("spotMarketType"))
                if not var or not kind:
                    continue
                for c in it.get("dateCurveDataList") or []:
                    m, arr = c["dataPointListMeta"], c.get("actualData") or []
                    if m.get("size") != 96 or len(arr) != 96 or m.get("delta") != 15 or not m["startDateTime"].endswith("00:00:00"):
                        continue
                    bnd[(kind, m["startDateTime"][:10], var)] = arr
    finally:
        await s.close()
    return price, bnd


def write(price, bnd):
    pw = kv(HOME / "db_secret.txt")["password"]
    conn = None
    for i in range(5):
        try:
            conn = psycopg2.connect(password=pw, **DB)
            break
        except Exception as e:
            log("数据库连接失败，重试", i + 1, type(e).__name__)
            time.sleep(5)
    if conn is None:
        raise SystemExit("数据库连接失败")
    cur = conn.cursor()
    rep = {}
    # 电价
    cur.execute("create temp table tp(date date,hour int,da numeric,rt numeric) on commit drop")
    if price:
        execute_values(cur, "insert into tp values %s", [(d, h, v[0], v[1]) for (d, h), v in price.items()], page_size=5000)
    cur.execute("""update daily_curves d set day_ahead_price=coalesce(t.da,d.day_ahead_price),
                   real_time_price=coalesce(t.rt,d.real_time_price),updated_at=now()
                   from tp t where d.date=t.date and d.hour=t.hour
                   and (d.day_ahead_price is distinct from coalesce(t.da,d.day_ahead_price)
                        or d.real_time_price is distinct from coalesce(t.rt,d.real_time_price))""")
    rep["电价更新行"] = cur.rowcount
    cur.execute("select count(*) from tp t left join daily_curves d using(date,hour) where d.date is null")
    rep["电价无对应日期行(未写)"] = cur.fetchone()[0]
    # 边界
    days = sorted({d for _, d, _ in bnd})
    existing_fb = set()
    if days:
        cur.execute("select date::text,hour from boundary_forecast where var='b_power' and date between %s and %s",
                    (days[0], days[-1]))
        existing_fb = set(cur.fetchall())
    recs = {"boundary_actual": [], "boundary_forecast": []}
    for (kind, d, var), arr in bnd.items():
        tab = "boundary_actual" if kind == "a" else "boundary_forecast"
        polluted = kind == "f" and var == "b_power" and bnd.get(("a", d, "b_power")) == arr
        for h in range(24):
            ch = [x for x in arr[h * 4:h * 4 + 4] if x is not None]
            if not ch or (polluted and (d, h) in existing_fb):
                continue
            recs[tab].append(("xuntian", d, h, var, sum(ch) / len(ch)))
    for tab, r in recs.items():
        n = 0
        if r:
            cur.execute(f"""create temp table tb_{tab}(source text,date date,hour smallint,var text,value float8) on commit drop""")
            execute_values(cur, f"insert into tb_{tab} values %s", r, page_size=5000)
            cur.execute(f"""insert into public.{tab}(source,date,hour,var,value) select * from tb_{tab}
                            on conflict(date,hour,var) do update set value=excluded.value,source=excluded.source
                            where {tab}.value is distinct from excluded.value""")
            n = cur.rowcount
        rep[f"{tab} 新增/更新行"] = n
    conn.commit()
    cur.execute("""select max(date) filter(where day_ahead_price is not null),max(date) filter(where real_time_price is not null)
                   from daily_curves""")
    rep["电价最新日(日前/实时)"] = [str(x) for x in cur.fetchone()]
    for tab in recs:
        cur.execute(f"select max(date) from {tab}")
        rep[f"{tab} 最新日"] = str(cur.fetchone()[0])
    conn.close()
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="回溯天数（默认 7）")
    ap.add_argument("--start")
    ap.add_argument("--end")
    a = ap.parse_args()
    today = dt.date.today()
    start = dt.date.fromisoformat(a.start) if a.start else today - dt.timedelta(days=a.days)
    end = dt.date.fromisoformat(a.end) if a.end else today + dt.timedelta(days=3)
    log(f"同步区间 {start} ~ {end}")
    price, bnd = asyncio.run(fetch(start, end))
    pd = sorted({d for d, _ in price})
    log(f"抓取：电价 {len(price)} 时点（{pd[0] if pd else '-'} ~ {pd[-1] if pd else '-'}），边界曲线 {len(bnd)} 条")
    for k, v in write(price, bnd).items():
        log(f"{k}: {v}")
    log("完成")


if __name__ == "__main__":
    main()
