from playwright.sync_api import sync_playwright
import time
BASE="http://localhost:4444"

def wait_attr(pg, sel, attr, val_none=True, timeout_ms=90000):
    end = time.time() + timeout_ms/1000
    while time.time() < end:
        el = pg.locator(sel).first
        if el.count():
            a = el.get_attribute(attr)
            # disabled attr present as "" (empty) counts as disabled
            is_disabled = a is not None
            if val_none and not is_disabled: return True
            if not val_none and is_disabled: return True
        time.sleep(0.7)
    return False

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width":1600,"height":1000})
    errs=[]
    pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
    pg.goto(f"{BASE}/web/login", wait_until="domcontentloaded")
    pg.fill('input[name="login"]',"admin"); pg.fill('input[name="password"]',"admin")
    pg.click('button[type="submit"]'); pg.wait_for_timeout(8000)
    pg.goto(f"{BASE}/odoo/action-social_marketing.action_social_image_template", wait_until="domcontentloaded")
    pg.wait_for_selector(".o_list_view", timeout=150000)
    pg.wait_for_timeout(2000)
    pg.locator("button.o_list_button_add").first.click()
    pg.wait_for_selector("#name_0", timeout=150000)
    pg.locator("#name_0").fill("Testmall OG")
    print("name filled; waiting for fabric load...")
    ok = wait_attr(pg, "button[title='Add text']", "disabled", val_none=True)
    print("addtext enabled:", ok)
    if ok:
        pg.locator("button[title='Add text']").first.click()
        pg.wait_for_timeout(1500)
        ok2 = wait_attr(pg, "button[title='Delete selection']", "disabled", val_none=True)
        print("delete enabled after add:", ok2)
    pg.locator("button[title='Save scene + SVG master']").first.click()
    pg.wait_for_timeout(2500)
    fs = pg.locator(".o_form_button_save")
    print("form save count:", fs.count())
    if fs.count():
        fs.first.click()
        pg.wait_for_timeout(6000)
        print("after save url:", pg.url)
    print("pageerrors:", errs[:8])
    pg.screenshot(path="/tmp/shot_final2.png")
    b.close()
