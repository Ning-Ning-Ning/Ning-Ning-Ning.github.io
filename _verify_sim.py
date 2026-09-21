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

    lay = pg.evaluate("""()=>{const w=document.querySelector('.sim-wrap'),t=document.querySelector('.sim-top'),bt=document.querySelector('.sim-bottom');
      const asks=[...document.querySelectorAll('#sim-book .sim-book-row')].filter(e=>e.classList.contains('ask')).length;
      const bids=[...document.querySelectorAll('#sim-book .sim-book-row')].filter(e=>e.classList.contains('bid')).length;
      return {wrapW:w?Math.round(w.getBoundingClientRect().width):0,
        topH:t?Math.round(t.getBoundingClientRect().height):0,
        stacked:!!(t&&bt&&bt.getBoundingClientRect().top>=t.getBoundingClientRect().bottom-2),
        bottomCols:bt?getComputedStyle(bt).gridTemplateColumns:'' ,
        asks,bids,mid:!!document.querySelector('#sim-book .sim-book-mid'),
        bookHead:(document.querySelector('#sim-book .sim-book-head')||{textContent:''}).textContent,
        paths:document.querySelectorAll('#sim-chart path').length,
        bars:document.querySelectorAll('#sim-chart rect:not(.sim-tag)').length,
        dot:document.querySelectorAll('#sim-chart circle').length,
        tradeHead:[...document.querySelectorAll('#sim-trades tr')].slice(0,1).map(tr=>[...tr.children].map(td=>td.textContent).join('/'))[0]||'',
        trades:document.querySelectorAll('#sim-trades tr').length-1,
        myOrders:document.querySelectorAll('#sim-my-orders tr').length-1,
        pnl:document.querySelectorAll('#sim-pnl tr').length-1,
        last:document.querySelector('#sim-last').textContent,
        meta:document.querySelector('#sim-meta').textContent};}""")
    print("  ", lay)
    check(f"固定宽度不拉伸（wrap {lay['wrapW']}px ≤ 1130）", 0 < lay["wrapW"] <= 1130)
    check(f"上下两块结构（下块在下且左图右盘口，下部分 {"两列" if lay['bottomCols'].count(' ')==1 else lay['bottomCols']}）",
          lay["stacked"] and lay["topH"] > 100 and lay["bottomCols"].count(" ") == 1)
    check(f"分时图纯折线（含面积填充+最新价标签）无成交量柱（path {lay['paths']} / 柱 {lay['bars']} / 末点 {lay['dot']}）", lay["paths"] >= 2 and lay["bars"] == 0 and lay["dot"] >= 2)
    check(f"买五卖五 10 档 + 中间价行 ({lay['asks']}/{lay['bids']}/{lay['mid']})", lay["asks"] == 5 and lay["bids"] == 5 and lay["mid"])
    check(f"买五卖五表头含单位（{lay['bookHead']}）", "电价（元/MWh）" in lay["bookHead"] and "电量（MWh）" in lay["bookHead"])
    check(f"成交明细表头为本人成交口径（{lay['tradeHead']}）", "方向" in lay["tradeHead"] and "对手方" in lay["tradeHead"])
    check(f"分账号盈亏表有数据（{lay['pnl']} 行）", lay["pnl"] >= 1)
    check(f"最新价与状态文案（{lay['last']} / {lay['meta'][:36]}）", lay["last"] != "—" and "行情点" in lay["meta"])

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
    wait_my_orders(pg, "已成")
    check("高价买单成交并写入我的委托", True)
    pg.wait_for_function("()=>document.querySelectorAll('#sim-trades tr').length>1", timeout=30000)
    trRows = pg.evaluate("()=>[...document.querySelectorAll('#sim-trades tr')].slice(1).map(tr=>[...tr.children].map(td=>td.textContent))")
    print("   本人成交:", trRows[:2])
    check(f"成交明细仅本人成交（{len(trRows)} 笔，方向列=买入/卖出）", len(trRows) >= 1 and all(r[1] in ("买入","卖出") for r in trRows))

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
    wait_my_orders(pg, "挂单")
    btns = pg.evaluate("()=>document.querySelectorAll('#sim-my-orders button').length")
    check(f"挂单出现在我的委托并带撤单按钮（按钮 {btns}）", btns >= 1)
    pg.evaluate("()=>document.querySelector('#sim-my-orders button').click()")
    pg.wait_for_function("()=>document.querySelector('#sim-hint').textContent.includes('已撤销')", timeout=30000)
    pg.wait_for_function("()=>[...document.querySelectorAll('#sim-my-orders tr')].some(tr=>tr.textContent.includes('已撤'))", timeout=30000)
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
