# -*- coding: utf-8 -*-
"""验证：复盘表excel文件页新增 2026-10 模板（下载可用、字节与源文件一致）"""
import time, hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8907"
SRC = Path.home() / "Desktop" / "【模拟】广东10月复盘表 - 售电.xlsx"
ok = True
def check(name, cond):
    global ok
    print(("PASS  " if cond else "FAIL  ") + name)
    if not cond:
        ok = False

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(BASE + "/?v=" + str(int(time.time() * 1000)), wait_until="domcontentloaded")
    pg.fill("#auth-username", "gly")
    pg.keyboard.press("Enter")
    pg.wait_for_function("()=>document.querySelector('#auth-overlay').hidden===true", timeout=25000)
    pg.click("#brand-btn")
    pg.wait_for_timeout(300)
    pg.click("#tab-reviewtable")
    pg.wait_for_function("()=>document.querySelectorAll('#rv-download-list .rv-month-row').length>=4", timeout=30000)

    rows = pg.evaluate("""()=>[...document.querySelectorAll('#rv-download-list .rv-month-row')].map(r=>({
        m:r.dataset.month, t:r.textContent.trim(), btn:!!r.querySelector('button')&&!r.querySelector('button').disabled,
        title:(r.querySelector('button')||{}).title||''}))""")
    print("  模板行:", rows)
    months = [r["m"] for r in rows]
    check(f"模板列表含 2026-10（月份 {months}）", "2026-10" in months)
    r10 = next((r for r in rows if r["m"] == "2026-10"), None)
    check(f"2026-10 下载按钮可用（title={r10['title'] if r10 else ''}）", bool(r10 and r10["btn"]))
    check("10 月文件名正确", bool(r10 and "广东10月复盘表" in r10["title"]))

    with pg.expect_download(timeout=30000) as dl:
        pg.evaluate("""()=>{const r=[...document.querySelectorAll('#rv-download-list .rv-month-row')].find(x=>x.dataset.month==='2026-10');r.querySelector('button').click();}""")
    d = dl.value
    path = d.path()
    size = Path(path).stat().st_size if path else 0
    same = size == SRC.stat().st_size
    check(f"下载文件与源文件同尺寸（{size} vs {SRC.stat().st_size}）", same)
    check(f"下载文件名（{d.suggested_filename}）", "10月复盘表" in d.suggested_filename)

    upl = pg.evaluate("()=>[...document.querySelectorAll('#rv-upload-list .rv-month-row')].map(r=>r.dataset.month)")
    check(f"上传列表也含 2026-10（{upl}）", "2026-10" in upl)
    check("无 JS 错误", not errors)
    if errors: print("JS errors:", errors[:3])
    b.close()

print("RESULT:", "PASS" if ok else "FAIL")
