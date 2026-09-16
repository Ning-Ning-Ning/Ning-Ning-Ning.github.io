# -*- coding: utf-8 -*-
# 验证：电费变化 / 全员总览 色深压缩映射（对数压缩，小值可区分、极值不压扁）
import time, re, json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8907"
SHOT = "_rv_dl/shot_heat_scale.png"

ok = True
def check(name, cond):
    global ok
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        ok = False

def alpha_of(style_obj):
    m = re.search(r"([\d.]+)%", style_obj.get("background", "") or "")
    return float(m.group(1)) if m else None

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1500, "height": 1000})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(BASE + "/?v=" + str(int(time.time() * 1000)), wait_until="domcontentloaded")
    pg.fill("#auth-username", "songningning")
    pg.keyboard.press("Enter")
    pg.wait_for_function("()=>document.querySelector('#auth-overlay').hidden===true", timeout=20000)

    # ---- A. 映射单元断言 ----
    res = pg.evaluate("""()=>{
      const a=[1,2,3,4,5].map(v=>strategyCellStyle(v,5,true));
      const b=[1,2,3,4,80].map(v=>strategyCellStyle(v,80,true));
      const c=[1,2,3,4,80].map(v=>strategyCellStyle(v,80,false));
      return {a:a,b:b,c:c};}""")
    A = [alpha_of(x) for x in res["a"]]
    B = [alpha_of(x) for x in res["b"]]
    C = [alpha_of(x) for x in res["c"]]
    print("alphas [1..5] compressed:", A)
    print("alphas [1,2,3,4,80] compressed:", B)
    print("alphas [1,2,3,4,80] linear   :", C)
    check("均匀数列 [1..5] 递增且每档可区分", all(A[i] < A[i+1] for i in range(4)) and min(A[i+1]-A[i] for i in range(4)) >= 3)
    check(f"极端数列 [1,2,3,4,80] 前四项仍递增可区分 {B[:4]}", all(B[i] < B[i+1] for i in range(3)) and min(B[i+1]-B[i] for i in range(3)) >= 2)
    check(f"压缩后小值与极值差距收窄（4→80 跨度 {round(B[4]-B[3],1)} vs 线性 {round(C[4]-C[3],1)}）", (B[4]-B[3]) < (C[4]-C[3]))
    check(f"小值被抬升（4: 压缩 {B[3]} > 线性 {C[3]}）", B[3] > C[3])
    check(f"极值仍最深（{B[4]} == 上限 48）", abs(B[4]-48) < 0.6)
    check("未启用压缩时保持线性（价差展示不受影响）", abs(C[0]-9.0) < 1.5 and abs(C[4]-48) < 0.6)

    # ---- B. 全员总览冒烟 + 色深分布 ----
    pg.wait_for_function("()=>document.querySelector('#overview-month').disabled===false", timeout=30000)
    pg.evaluate("()=>{document.querySelector('#overview-month').value='2026-08';document.querySelector('#overview-month').dispatchEvent(new Event('change'));}")
    pg.wait_for_function("()=>document.querySelector('#overview-status').textContent.includes('已展示')", timeout=40000)
    ov = pg.evaluate("""()=>{const cells=[...document.querySelectorAll('#overview-daily-body td.spread-cell')];
      const alphas=cells.map(td=>{const m=/[\\d.]+%/.exec(td.style.background||'');return m?parseFloat(m[0]):null;}).filter(v=>v!==null);
      return {n:cells.length,alphas:alphas};}""")
    uniq = sorted(set(ov["alphas"]))
    check(f"全员总览渲染 {ov['n']} 格、色深档位 {len(uniq)} 个 (min={uniq[0] if uniq else None} max={uniq[-1] if uniq else None})",
          ov["n"] > 0 and len(uniq) >= 3 and uniq[0] >= 8 and uniq[-1] <= 48)
    pg.screenshot(path=SHOT)

    # ---- C. 电费变化冒烟（用有调整数据的账号 zhangchenyue，2026-08 价格覆盖 1-26 日）----
    pg2 = b.new_page(viewport={"width": 1500, "height": 1000})
    pg2.on("pageerror", lambda e: errors.append(str(e)))
    pg2.goto(BASE + "/?v=" + str(int(time.time() * 1000)), wait_until="domcontentloaded")
    pg2.fill("#auth-username", "zhangchenyue")
    pg2.keyboard.press("Enter")
    pg2.wait_for_function("()=>document.querySelector('#auth-overlay').hidden===true", timeout=20000)
    pg2.wait_for_function("()=>document.querySelector('#strategy-month').disabled===false", timeout=30000)
    pg2.evaluate("()=>{document.querySelector('#strategy-month').value='2026-08';document.querySelector('#strategy-month').dispatchEvent(new Event('change'));}")
    pg2.click("#strategy-load")
    pg2.wait_for_function("()=>{const t=document.querySelector('#strategy-status').textContent;return t.length>0&&!t.includes('正在加载');}", timeout=60000)
    pg2.wait_for_function("()=>document.querySelectorAll('#strategy-body td.spread-cell[style*=\"color-mix\"]').length>0", timeout=60000)
    st = pg2.evaluate("""()=>{const cells=[...document.querySelectorAll('#strategy-body td.spread-cell')];
      const alphas=cells.map(td=>{const m=/[\d.]+%/.exec(td.style.background||'');return m?parseFloat(m[0]):null;}).filter(v=>v!==null);
      return {n:cells.length,colored:alphas.length,alphas:alphas,status:document.querySelector('#strategy-status').textContent};}""")
    uni2 = sorted(set(st["alphas"]))
    check(f"电费变化渲染 {st['n']} 格（着色 {st['colored']} 格、{len(uni2)} 档，min={uni2[0] if uni2 else None} max={uni2[-1] if uni2 else None}）",
          st["colored"] > 0 and len(uni2) >= 3 and uni2[0] >= 8 and uni2[-1] <= 48)
    pg2.screenshot(path="_rv_dl/shot_heat_strategy.png")

    check("无 JS 错误", not errors)
    if errors: print("JS errors:", errors[:3])
    b.close()

print("RESULT:", "PASS" if ok else "FAIL")
