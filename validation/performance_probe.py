"""Measure completion of the normal (not Live Mode) Streamlit Game Cards.
A slow or unavailable external sports feed may extend the timings; this is
a browser smoke and diagnostic rather than a contractual performance SLA.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("validation/performance-results")
OUT.mkdir(parents=True, exist_ok=True)
URI = "http://127.0.0.1:8501"
REPORT={"checks": {}, "timing_seconds": {}, "screens": [], "errors":[]}


def browser_run():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        context=browser.new_context(
            viewport={"width":390,"height":844},is_mobile=True,has_touch=True,
            color_scheme="dark", device_scale_factor=1,
        )
        page=context.new_page()
        page.on("pageerror",lambda exc: REPORT["errors"].append(str(exc)))
        start=time.perf_counter()
        page.goto(URI,wait_until="domcontentloaded",timeout=120000)
        page.get_by_role("tab",name="Game cards").wait_for(timeout=180000)
        page.get_by_text("Matchup center").first.wait_for(timeout=180000)
        REPORT["timing_seconds"]["first_game_card_controls"]=round(time.perf_counter()-start,2)
        page.locator(".prediction-disclaimer").wait_for(timeout=120000)
        REPORT["timing_seconds"]["full_game_cards_page"]=round(time.perf_counter()-start,2)
        REPORT["checks"]["single_footer"]=page.locator(".prediction-disclaimer").count()==1
        REPORT["checks"]["red_zone_load_buttons_exist"]=page.locator('button:has-text("Load red-zone touchdown comparison")').count()>0
        REPORT["checks"]["normal_mode_rendered"]=page.get_by_text("Saturday Live Mode").count()>0
        REPORT["checks"]["no_browser_exceptions"]=page.locator('[data-testid="stException"]').count()==0
        page.screenshot(path=str(OUT/"normal-game-cards-mobile.png"),timeout=30000)
        REPORT["screens"].append("normal-game-cards-mobile.png")
        REPORT["checks"]["no_mobile_overflow"]=page.evaluate(
            "() => document.documentElement.scrollWidth <= innerWidth + 2")
        page.set_viewport_size({"width":1280,"height":900})
        page.wait_for_timeout(1000)
        REPORT["checks"]["no_desktop_overflow"]=page.evaluate(
            "() => document.documentElement.scrollWidth <= innerWidth + 2")
        page.screenshot(path=str(OUT/"normal-game-cards-desktop.png"),timeout=30000)
        REPORT["screens"].append("normal-game-cards-desktop.png")
        context.close()
        browser.close()


def main():
    log=(OUT/"server.log").open("w")
    proc=subprocess.Popen(
        [sys.executable,"-m","streamlit","run","app.py","--server.headless=true",
         "--server.port=8501","--browser.gatherUsageStats=false"],
        stdout=log,stderr=subprocess.STDOUT,
        env={**os.environ,"STREAMLIT_BROWSER_GATHER_USAGE_STATS":"false"},
    )
    try:
        ready=False
        for _ in range(90):
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(URI+"/_stcore/health",timeout=2) as resp:
                    ready=resp.status==200
            except Exception:
                pass
            if ready: break
            time.sleep(1)
        REPORT["checks"]["server_health"]=ready
        if ready: browser_run()
    except Exception as exc:
        REPORT["errors"].append(type(exc).__name__+": "+str(exc)[:1200])
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        log.close()
        (OUT/"report.json").write_text(json.dumps(REPORT,indent=2)+"\n")
        print("PERFORMANCE_VALIDATION",json.dumps(REPORT),flush=True)
    return not REPORT["errors"] and all(REPORT["checks"].values())


if __name__=="__main__":
    sys.exit(0 if main() else 1)
