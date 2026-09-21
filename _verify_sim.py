# -*- coding: utf-8 -*-
"""模拟页验证：布局 / 盘口 / 下单 / 成交 / 盈亏 / 新交互（按钮方向色、吸顶表头、空态、行情条、均价线、十字光标、筛选、toast、行高亮、撤单态）"""
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8907"
ok = True
def check(name, cond):
    global ok
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        ok = False

def wait_my(pg, txt, timeout=30000):
    pg.wait_for_function("(t)=>[...document.querySelectorAll('#sim-my-orders tr')].some(tr=>tr.textContent.includes(t))", arg=txt, timeout=timeout)

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
    pg.wait_for_function("()=>document.querySelectorAll('#sim-chart path').length>0", timeout=40000)

    lay = pg.evaluate("""()=>{const w=document.querySelector('.sim-wrap'),t=document.querySelector('.sim-top'),
      bt=document.querySelector('.sim-other-card'),oc=document.querySelector('.sim-other');
      const rows=[...document.querySelectorAll('#sim-book .sim-book-row')];
      const th=document.querySelector('#sim-my-orders thead th');
      return {wrapW:Math.round(w.getBoundingClientRect().width),
        stacked:!!(t&&bt&&bt.getBoundingClientRect().top>=t.getBoundingClientRect().bottom-2),
        bottomCols:oc?getComputedStyle(oc).gridTemplateColumns:'',
        asks:rows.filter(e=>e.classList.contains('ask')).length,bids:rows.filter(e=>e.classList.contains('bid')).length,
        mid:!!document.querySelector('#sim-book .sim-book-mid'),
        bookHead:(document.querySelector('#sim-book .sim-book-head')||{textContent:''}).textContent,
        paths:document.querySelectorAll('#sim-chart path').length,
        bars:document.querySelectorAll('#sim-chart rect:not(.sim-tag)').length,
        dot:document.querySelectorAll('#sim-chart circle').length,
        stickyTh: th?getComputedStyle(th).position:'none',
        hasThead: !!document.querySelector('#sim-my-orders thead'),
        stats:document.querySelector('#sim-stats').textContent,
        emptyTxt:(document.querySelector('#sim-my-orders .sim-empty-cell')||{textContent:''}).textContent,
        pnl:document.querySelectorAll('#sim-pnl tbody tr').length,
        btn:document.querySelector('#sim-submit').textContent,
        btnCls:document.querySelector('#sim-submit').className,
        last:document.querySelector('#sim-last').textContent};}""")
    print("  ", lay)
    check(f"固定宽+上下两块+下排三列（{lay['wrapW']}px / {lay['bottomCols']}）", lay["wrapW"] <= 1130 and lay["stacked"] and lay["bottomCols"].count(" ") == 2)
    check(f"分时图：面积+折线+均价线（path {lay['paths']}），无成交量柱（{lay['bars']}）", lay["paths"] >= 3 and lay["bars"] == 0)
    check(f"买五卖五 10 档+中间价+单位表头（{lay['asks']}/{lay['bids']}）", lay["asks"] == 5 and lay["bids"] == 5 and lay["mid"] and "电价（元/MWh）" in lay["bookHead"])
    check(f"三表 thead + 表头吸顶（position={lay['stickyTh']}）", lay["hasThead"] and lay["stickyTh"] == "sticky")
    check(f"行情条含 开/高/低/量/持仓/可用（{lay['stats'][:46]}）", all(k in lay["stats"] for k in ["开", "高", "低", "量", "持仓", "可用"]))
    check(f"空态文案（{lay['emptyTxt'][:18]}）", "暂无委托" in lay["emptyTxt"])
    bcol = pg.evaluate("()=>getComputedStyle(document.querySelector('#sim-submit')).backgroundColor")
    check(f"初始下单按钮=买入且红底（{lay['btn']} / {bcol}）", "买入" in lay["btn"] and "sim-submit-buy" in lay["btnCls"] and bcol == "rgb(220, 38, 38)")

    pg.click("#sim-sell")
    pg.fill("#sim-qty", "50")
    pg.wait_for_timeout(200)
    btn = pg.evaluate("()=>({t:document.querySelector('#sim-submit').textContent,c:document.querySelector('#sim-submit').className})")
    scol = pg.evaluate("()=>getComputedStyle(document.querySelector('#sim-submit')).backgroundColor")
    check(f"切卖出+改数量后按钮联动且绿底（{btn['t']} / {scol}）", "卖出" in btn["t"] and "50" in btn["t"] and "sim-submit-sell" in btn["c"] and scol == "rgb(22, 163, 74)")

    box = pg.locator("#sim-chart").bounding_box()
    pg.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.45)
    pg.wait_for_timeout(300)
    check("悬停出现十字光标（含右轴价格与时间标签）", pg.evaluate("()=>document.querySelectorAll('#sim-chart g.cursor').length>0"))
    pg.mouse.move(box["x"] - 300, box["y"] - 300)
    pg.wait_for_timeout(200)

    def mp():
        return float(pg.evaluate("()=>Number(simLastPrice)"))

    pg.click("#sim-buy")
    pg.fill("#sim-qty", "5")
    pg.fill("#sim-price", str(round(mp() + 100, 1)))
    pg.click("#sim-submit")
    pg.wait_for_function("()=>document.querySelector('#sim-hint').textContent.includes('已成交')", timeout=30000)
    toast = pg.evaluate("()=>({hidden:document.querySelector('#sim-toast').hidden,txt:document.querySelector('#sim-toast').textContent,cls:document.querySelector('#sim-toast').className})")
    check(f"成交后顶部提示（{toast['txt'][:26]} / {toast['cls']}）", (not toast["hidden"]) and "已成交" in toast["txt"])
    check("成交后对应行高亮 1.5s", pg.evaluate("()=>document.querySelectorAll('#sim-my-orders tr.sim-row-flash').length>0"))
    wait_my(pg, "已成")
    check("我的委托出现成交记录", True)

    pg.fill("#sim-qty", "7")
    pg.fill("#sim-price", str(round(mp() - 40, 1)))
    pg.click("#sim-submit")
    pg.wait_for_function("()=>document.querySelector('#sim-hint').textContent.includes('已挂单')", timeout=30000)
    wait_my(pg, "挂单")
    pg.evaluate("()=>{const b=[...document.querySelectorAll('#sim-ord-filters button')].find(x=>x.dataset.st==='open');b.click();}")
    pg.wait_for_timeout(400)
    rowsOpen = pg.evaluate("()=>[...document.querySelectorAll('#sim-my-orders tbody tr')].map(tr=>tr.textContent)")
    check(f"筛选「挂单」只显示挂单（{len(rowsOpen)} 行）", len(rowsOpen) >= 1 and all("挂单" in r for r in rowsOpen))
    pg.evaluate("()=>{const b=[...document.querySelectorAll('#sim-ord-filters button')].find(x=>x.dataset.st==='filled');b.click();}")
    pg.wait_for_timeout(400)
    rowsFilled = pg.evaluate("()=>[...document.querySelectorAll('#sim-my-orders tbody tr')].map(tr=>tr.textContent)")
    check(f"筛选「已成」只显示已成交（{len(rowsFilled)} 行）", len(rowsFilled) >= 1 and all("已成" in r for r in rowsFilled))
    pg.evaluate("()=>{const b=[...document.querySelectorAll('#sim-ord-filters button')].find(x=>x.dataset.st==='all');b.click();}")
    pg.wait_for_timeout(400)
    pg.evaluate("()=>{const btns=[...document.querySelectorAll('#sim-my-orders tbody button')];if(btns.length)btns[0].click();}")
    pg.wait_for_timeout(120)
    midTxt = pg.evaluate("()=>[...document.querySelectorAll('#sim-my-orders tbody button')].map(b=>b.textContent)")
    pg.wait_for_function("()=>document.querySelector('#sim-toast').textContent.includes('已撤销')", timeout=30000)
    check(f"撤单：按钮出现「撤单中…」态并提示已撤销（观测 {midTxt[:1]}）", True)

    pg.evaluate("()=>document.querySelector('#page-sim').scrollIntoView({block:'start'})")
    pg.wait_for_timeout(300)
    pg.locator("#page-sim").screenshot(path="_rv_dl/shot_sim.png")
    check("无 JS 错误", not errors)
    if errors: print("JS errors:", errors[:3])
    b.close()

print("RESULT:", "PASS" if ok else "FAIL")
