"""Read-only end-to-end smoke test of the production Streamlit UI code.
Runs on an isolated GitHub Actions branch with Chromium at phone and desktop sizes.
No data or selection logic is modified.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT = Path("validation/ui-results")
OUTPUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:8501"
RESULTS = {"checks": [], "measurements": {}, "failures": [], "warnings": []}

def check(label, condition, details=None, critical=True):
    outcome = {"name": label, "passed": bool(condition)}
    if details is not None:
        outcome["details"] = details
    RESULTS["checks"].append(outcome)
    if not condition:
        (RESULTS["failures"] if critical else RESULTS["warnings"]).append(label)
    print("CHECK", "PASS" if condition else "FAIL", label, details or "", flush=True)
    return bool(condition)

def browser_dimensions(page):
    return page.evaluate("""() => {
      const app = document.querySelector('[data-testid="stAppViewContainer"]');
      const tabs = [...document.querySelectorAll('[role="tablist"] [role="tab"]')];
      const tabRects = tabs.map(t => {
        const r=t.getBoundingClientRect();
        return {text:t.innerText, left:+r.left.toFixed(1),
            right:+r.right.toFixed(1),top:+r.top.toFixed(1),bottom:+r.bottom.toFixed(1)}
      });
      const footers = [...document.querySelectorAll('.prediction-disclaimer')];
      const overflow = [...document.querySelectorAll('main, [data-testid="stMain"], [data-testid="stMainBlockContainer"]')]
        .map(e => ({selector:e.getAttribute('data-testid') || e.tagName,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth}));
      return {
        viewportWidth:innerWidth, viewportHeight:innerHeight,
        documentWidth:document.documentElement.scrollWidth,
        bodyWidth:document.body.scrollWidth,
        overflow, tabRects, footerCount:footers.length,
        footerText:footers.map(x=>x.innerText),
        background: app ? getComputedStyle(app).backgroundColor : null,
        themeToken: app ? getComputedStyle(app).getPropertyValue("--background-color").trim() : null,
        appSurface: getComputedStyle(document.querySelector(".stApp") || document.body).backgroundColor,
        exceptionCount:document.querySelectorAll('[data-testid="stException"]').length
      };
    }""")

def run():
    proc = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.headless=true", "--server.port=8501",
        "--browser.gatherUsageStats=false",
    ], stdout=(OUTPUT/"server.log").open("w"), stderr=subprocess.STDOUT,
    env={**os.environ,"STREAMLIT_BROWSER_GATHER_USAGE_STATS":"false"})
    try:
        import urllib.request
        ready = False
        for attempt in range(100):
            if proc.poll() is not None:
                raise RuntimeError("Streamlit exited prematurely")
            try:
                with urllib.request.urlopen(BASE+"/_stcore/health", timeout=2) as r:
                    ready = r.status == 200
            except Exception:
                pass
            if ready:
                break
            time.sleep(1)
        check("Streamlit health endpoint",ready)
        if not ready:
            return
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(
                viewport={"width":390,"height":844},
                device_scale_factor=1,
                is_mobile=True,
                has_touch=True,
                color_scheme="dark",
            )
            page = context.new_page()
            console_errors = []
            page.on("pageerror", lambda err: console_errors.append(str(err)))
            t0 = time.monotonic()
            page.goto(BASE,wait_until="domcontentloaded",timeout=90000)
            check("Brand header visible", bool(page.get_by_text("Saturday Forecast",exact=False).first.wait_for(timeout=90000) is None))
            try:
                page.get_by_role("tab",name="Game cards").wait_for(timeout=240000)
                page.get_by_text("Matchup center").first.wait_for(timeout=240000)
                ready_ui=True
            except Exception as e:
                ready_ui=False
                RESULTS["warnings"].append("Prediction content unavailable: "+str(e)[:150])
            elapsed=round(time.monotonic()-t0,2)
            RESULTS["measurements"]["mobile_first_content_seconds"]=elapsed
            check("Game cards render",ready_ui,{"elapsed_seconds":elapsed})
            # Take a top-of-page screenshot even on a failed render.
            page.screenshot(path=str(OUTPUT/"mobile-top.png"),full_page=False,timeout=30000)
            if not ready_ui:
                RESULTS["measurements"]["failed_page_text"]=page.locator("body").inner_text(timeout=10000)[-2400:]
                return
            try:
                page.get_by_text("Saturday Live Mode", exact=True).first.click(timeout=20000)
                page.get_by_text("Refresh scores now").first.wait_for(timeout=40000)
                check("Live Mode opens from visible toggle",True)
            except Exception as exc:
                check("Live Mode opens from visible toggle",False,str(exc)[:250])
            try:
                page.locator(".prediction-disclaimer").wait_for(timeout=55000)
                footer_ready=True
            except Exception:
                footer_ready=False
                RESULTS["warnings"].append("Prediction footer missing after waiting 55 seconds")
            RESULTS["measurements"]["footer_arrived"]=footer_ready
            RESULTS["measurements"]["body_footer_text_found"]=page.evaluate("() => document.body.innerText.includes('Prediction disclaimer')")
            if not footer_ready:
                RESULTS["measurements"]["body_tail"]=page.locator("body").inner_text()[-3600:]
                RESULTS["measurements"]["footer_html_mentions"]=page.evaluate("() => (document.documentElement.outerHTML.match(/prediction.disclaimer/gi)||[]).length")
            info=browser_dimensions(page)
            RESULTS["measurements"]["mobile_390"]=info
            check("No global horizontal scroll at 390px",
                info["documentWidth"] <= info["viewportWidth"]+2,
                {"document":info["documentWidth"],"viewport":info["viewportWidth"]},critical=False)
            check("Eight navigation tabs present",len(info["tabRects"])==8,
                  {"count":len(info["tabRects"])})
            check("No exceptions on Game cards",info["exceptionCount"]==0,info["exceptionCount"])
            check("Single prediction disclaimer",info["footerCount"]==1,{"count":info["footerCount"],"waited_for_completion":footer_ready})
            check("Default dark background",
                  (info["appSurface"] not in (None,"rgb(255, 255, 255)","rgba(0, 0, 0, 0)")),
                  {"container":info["background"],"themeToken":info["themeToken"],"appSurface":info["appSurface"]},
                  critical=False)
            # On mobile, each tab's rectangle should remain inside the viewport.
            clip=[r for r in info["tabRects"] if r["left"] < -1 or r["right"] > 391]
            check("Mobile tabs are not clipped",len(clip)==0,clip,critical=False)
            if footer_ready:
                page.locator(".prediction-disclaimer").scroll_into_view_if_needed(timeout=10000)
                page.screenshot(path=str(OUTPUT/"mobile-footer.png"),full_page=False,timeout=30000)
            # Validate the active tab switches without duplicating the shared footer.
            page.get_by_role("tab",name="Value shortlist").click(timeout=20000)
            page.wait_for_timeout(1200)
            try:
                page.get_by_text("Value Picks · Five-stage waterfall").wait_for(timeout=35000)
                value_tab_loaded=True
            except Exception:
                value_tab_loaded=False
            check("Value Shortlist opens",value_tab_loaded)
            check("Footer remains single after changing tabs",
                  page.locator(".prediction-disclaimer").count()==1)
            page.get_by_role("tab",name="Game cards").click(timeout=20000)
            check("Live Mode toggle is present",page.get_by_text("Saturday Live Mode").count()>0)
            # Verify that Live Mode can be toggled, score-only refresh exists, no errors.
            try:
                page.get_by_text("Refresh scores now").first.wait_for(timeout=30000)
                check("Live Mode toolbar opens",True)
                check("No exceptions in Live Mode",
                      page.locator('[data-testid="stException"]').count()==0)
            except Exception as exc:
                check("Live Mode toolbar opens",False,str(exc)[:180])
            # Reset and verify an independent, narrower iPhone size.
            page.set_viewport_size({"width":360,"height":780})
            page.wait_for_timeout(700)
            small=browser_dimensions(page)
            RESULTS["measurements"]["mobile_360"]=small
            check("No global horizontal scroll at 360px",
                  small["documentWidth"]<=small["viewportWidth"]+2,
                  {"document":small["documentWidth"],"viewport":small["viewportWidth"]},critical=False)
            page.screenshot(path=str(OUTPUT/"mobile-360.png"),full_page=False,timeout=30000)
            # On the same running session, switch to desktop width.
            page.set_viewport_size({"width":1280,"height":900})
            page.wait_for_timeout(1000)
            desktop=browser_dimensions(page)
            RESULTS["measurements"]["desktop_1280"]=desktop
            check("No desktop global horizontal scroll",
                  desktop["documentWidth"]<=desktop["viewportWidth"]+2,
                  {"document":desktop["documentWidth"],"viewport":desktop["viewportWidth"]},critical=False)
            check("No desktop exceptions",desktop["exceptionCount"]==0)
            page.screenshot(path=str(OUTPUT/"desktop-top.png"),full_page=False,timeout=30000)
            check("No uncaught browser page errors",len(console_errors)==0,
                  console_errors[:6],critical=False)
            browser.close()
    except Exception as exc:
        check("Browser smoke test completed",False,str(exc)[:1000])
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=12)
        except Exception:
            proc.kill()
        (OUTPUT/"report.json").write_text(json.dumps(RESULTS,indent=2)+"\n")
        print("VALIDATION_JSON",json.dumps(RESULTS),flush=True)

if __name__=="__main__":
    run()
    if RESULTS["failures"]:
        sys.exit(1)
