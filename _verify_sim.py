# -*- coding: utf-8 -*-
"""模拟页真机验证：渲染 / 下单成交 / 挂单撤单 / 盈亏表 / 秒级推进"""
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8907"
ok = True
def check(name, cond):
    global ok
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        ok = False

def wait_my_orders(pg, contains, timeout=30000):
    pg.wait_for_function(
        "(txt)=>[...document.querySelectorAll('#sim-my-orders tr')].some(tr=>tr.textContent.includes(txt))",
        arg=contains, timeout=timeout)

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 1100})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(BASE + "/?v=" + str(int(time.time() * 1000)), wait_until="domcontentloaded")
    pg.fill("#auth-username", "songningning")
    pg.keyboard.press("Enter")
    pg.wait_for_function("()=>document.querySelector('#auth-overlay').hidden===true", timeout=25000)
    pg.click("#brand-btn")
    pg.wait_for_timeout(300)
    check("long 模式显示「模拟」菜单", pg.evaluate("()=>!document.querySelector('#tab-sim').hidden"))
    pg.click("#tab-sim")
    pg.wait_for_function("()=>!document.querySelector('#page-sim').hidden", timeout=20000)
    pg.wait_for_function("()=>document.querySelectorAll('#sim-chart path').length>0", timeout=40000)

    r = pg.evaluate("""()=>{
      const rows=[...document.querySelectorAll('#sim-book .sim-book-row')];
      return {paths:document.querySelectorAll('#sim-chart path').length,
        bars:document.querySelectorAll('#sim-chart rect').length,
        dot:document.querySelectorAll('#sim-chart circle').length,
        asks:rows.filter(e=>e.classList.contains('ask')).length,
        bids:rows.filter(e=>e.classList.contains('bid')).length,
        mid:!!document.querySelector('#sim-book .sim-book-mid'),
        trades:document.querySelectorAll('#sim-trades tr').length-1,
        pnl:document.querySelectorAll('#sim-pnl tr').length-1,
        last:document.querySelector('#sim-last').textContent,
        meta:document.querySelector('#sim-meta').textContent};}""")
    print("  ", r)
    check(f"分时图折线+量柱渲染（path {r['paths']} / 柱 {r['bars']} / 末点 {r['dot']}）", r["paths"] >= 1 and r["bars"] > 10 and r["dot"] >= 1)
    check(f"买五卖五 10 档 + 中间价行 ({r['asks']}/{r['bids']}/{r['mid']})", r["asks"] == 5 and r["bids"] == 5 and r["mid"])
    check(f"成交明细有数据（{r['trades']} 笔）", r["trades"] > 0)
    check(f"分账号盈亏表有数据（{r['pnl']} 行）", r["pnl"] >= 1)
    check(f"最新价与状态文案（{r['last']} / {r['meta'][:36]}）", r["last"] != "—" and "行情点" in r["meta"])

    v1 = pg.locator("#sim-last").text_content()
    pg.wait_for_timeout(1600)
    v2 = pg.locator("#sim-last").text_content()
    check(f"页面秒级推进（{v1} → {v2}）", v1 != v2)

    def market_price():
        return float(pg.evaluate("()=>Number(simLastPrice)"))

    # 1) 高价买单 → 立即成交
    mp = market_price()
    pg.fill("#sim-qty", "5")
    pg.fill("#sim-price", str(round(mp + 20, 1)))
    pg.click("#sim-submit")
    pg.wait_for_function("()=>document.querySelector('#sim-hint').textContent.includes('已成交')", timeout=30000)
    print("   成交提示:", pg.locator("#sim-hint").text_content())
    wait_my_orders(pg, "已成交")
    check("高价买单成交并写入我的委托", True)
    pg.wait_for_function("()=>[...document.querySelectorAll('#sim-trades tr')].some(tr=>tr.textContent.includes('用户委托'))", timeout=30000)
    check("成交明细含用户委托记录", True)

    # 2) 低价卖单 → 立即成交
    mp = market_price()
    pg.click("#sim-sell")
    pg.fill("#sim-qty", "3")
    pg.fill("#sim-price", str(round(mp - 20, 1)))
    pg.click("#sim-submit")
    pg.wait_for_function("()=>document.querySelector('#sim-hint').textContent.includes('已成交')", timeout=30000)
    check("低价卖单成交", True)

    # 3) 远价挂单 + 撤单
    mp = market_price()
    pg.click("#sim-buy")
    pg.fill("#sim-qty", "7")
    pg.fill("#sim-price", str(round(mp - 40, 1)))
    pg.wait_for_timeout(300)
    check(f"远价单提示将挂单（{pg.locator('#sim-hint').text_content()[:26]}）", "将转为限价挂单" in pg.locator("#sim-hint").text_content())
    pg.click("#sim-submit")
    pg.wait_for_function("()=>document.querySelector('#sim-hint').textContent.includes('已挂单')", timeout=30000)
    wait_my_orders(pg, "挂单中")
    btns = pg.evaluate("()=>document.querySelectorAll('#sim-my-orders button').length")
    check(f"挂单出现在我的委托并带撤单按钮（按钮 {btns}）", btns >= 1)
    pg.evaluate("()=>document.querySelector('#sim-my-orders button').click()")
    pg.wait_for_function("()=>document.querySelector('#sim-hint').textContent.includes('已撤销')", timeout=30000)
    pg.wait_for_function("()=>[...document.querySelectorAll('#sim-my-orders tr')].some(tr=>tr.textContent.includes('已撤销'))", timeout=30000)
    check("撤单成功并更新状态", True)

    # 4) 盈亏表出现本人持仓
    pg.wait_for_timeout(800)
    pnl = pg.evaluate("()=>[...document.querySelectorAll('#sim-pnl tr')].slice(1).map(tr=>[...tr.children].map(td=>td.textContent))")
    print("   盈亏表:", pnl[:3])
    check("分账号盈亏表含净持仓与盈亏数值", len(pnl) >= 1 and len(pnl[0]) == 6 and pnl[0][1] != "—")

    pg.evaluate("()=>document.querySelector('#page-sim').scrollIntoView({block:'start'})")
    pg.wait_for_timeout(400)
    pg.locator("#page-sim").screenshot(path="_rv_dl/shot_sim.png")
    check("无 JS 错误", not errors)
    if errors: print("JS errors:", errors[:3])
    b.close()

print("RESULT:", "PASS" if ok else "FAIL")
