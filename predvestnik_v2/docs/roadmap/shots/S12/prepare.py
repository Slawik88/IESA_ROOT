"""Rebuild S12's source-backed fixture and screenshots on the isolated UI stand.

Run from predvestnik_v2 with --dsn pointing to a disposable loopback test database.
No production routes, data or Telegram calls are needed for the mockup itself.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import io
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))
from PIL import Image
from playwright.sync_api import sync_playwright
from ui_smoke import FREEZE, INIT, chromium_path
from ui_stand import Stand, set_game_flags

OUT = Path(__file__).resolve().parent


async def exchange_only(dsn: str, enabled: bool) -> None:
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import system_flags
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SET search_path TO predvestnik, public")
        await system_flags.set_flag(PGAdapter(conn), "economy_player_exchange_v1", enabled)
    finally:
        await conn.close()


def save_shot(page, name: str, width: int, *, full: bool = False) -> None:
    png = page.screenshot(full_page=full)
    with Image.open(io.BytesIO(png)) as shot:
        shot.crop((0, 0, width, shot.height)).convert("RGB").save(OUT / name, "WEBP", quality=78)


def capture(dsn: str) -> None:
    metrics = []
    asyncio.run(set_game_flags(dsn, True))
    with Stand(18412, dsn, rich=True, name="Искатель") as stand, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_path(), headless=True)
        for enabled in (False, True):
            with ThreadPoolExecutor(max_workers=1) as worker:
                worker.submit(asyncio.run, exchange_only(dsn, enabled)).result()
            for width in (320, 390, 430):
                ctx = browser.new_context(viewport={"width": width, "height": 640}, is_mobile=True, has_touch=True)
                page = ctx.new_page()
                page.add_init_script(INIT + stand.browser_init)
                page.goto(stand.url, wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('#pg-profile')?.textContent.includes('Путеводитель')", timeout=20000)
                page.evaluate("switchPage('profile')")
                page.wait_for_timeout(1200)
                page.add_style_tag(content=FREEZE)
                metrics.append({"width": width, "exchange": enabled, "dock": page.evaluate("""() => [...document.querySelectorAll('.nav .nb')].filter(b=>!b.hidden).map(b=>{
                    const r=b.getBoundingClientRect(),n=b.closest('.nav').getBoundingClientRect();return {label:b.innerText,fullyVisible:r.left>=n.left&&r.right<=n.right,x:r.x,width:r.width};})""")})
                if not enabled:
                    save_shot(page, f"before-profile-{width}.webp", width)
                    hotspots = page.evaluate("""() => [...document.querySelectorAll('#v3-bar button[onclick],#pg-profile button[onclick]')].flatMap(b=>{
                      const action=b.getAttribute('onclick'),r=b.getBoundingClientRect();
                      const key=action.includes('showCurrModal')?'wallet':action.includes('openLooksModal')?'looks':action.includes('openGuide')?'guide':null;
                      return key&&r.width&&r.height?[{key,x:r.x,y:r.y+scrollY,width:r.width,height:r.height}]:[];})""")
                    hidden_nav = page.add_style_tag(content=".nav{visibility:hidden!important}")
                    save_shot(page, f"profile-content-{width}.webp", width, full=True)
                    (OUT / f"profile-hits-{width}.json").write_text(json.dumps(hotspots, ensure_ascii=False, indent=2), encoding="utf-8")
                    page.evaluate("switchPage('more')")
                    hidden_nav.evaluate("node => node.remove()")
                    page.wait_for_timeout(500)
                    save_shot(page, f"before-more-{width}.webp", width, full=True)
                if enabled and width == 390:
                    page.evaluate("switchPage('more')")
                    page.wait_for_timeout(500)
                    fixture = page.evaluate("""() => {
                      const items={profile:{label:'Профиль'},arena:{label:'Игры'},questlog:{label:'Задания'},pets:{label:'Питомцы'},more:{label:'Ещё'}};
                      const read=b=>{const s=b.querySelector('span'),copy=s?.cloneNode(true);copy?.querySelectorAll('small').forEach(n=>n.remove());return {label:copy?.textContent.trim()||b.innerText.trim(),hint:s?.querySelector('small')?.textContent.trim()||'',icon:b.querySelector('svg')?.outerHTML||''};};
                      document.querySelectorAll('.nav .nb').forEach(b=>{const key=b.dataset.page||(b.hasAttribute('aria-haspopup')?'wallet':null);if(key)items[key]=read(b);});
                      const groups=[...document.querySelectorAll('#pg-more [data-nav-group]')].map(g=>({key:g.dataset.navGroup,title:g.querySelector('.v3-eyebrow')?.textContent.trim(),keys:[...g.querySelectorAll('[data-nav-key]')].map(b=>{items[b.dataset.navKey]=read(b);return b.dataset.navKey;})}));
                      return {items,groups};} """)
                    # Access to the purge entry is fetched dynamically in the real app.
                    fixture["items"]["purge"] = {"label": "Чистка чатов", "hint": "Досье и решения, общие с Telegram", "icon": fixture["items"]["admin"]["icon"]}
                    for group in fixture["groups"]:
                        if group["key"] == "community" and "purge" not in group["keys"]:
                            group["keys"].insert(0, "purge")
                        if group["key"] == "shop":
                            group["keys"].insert(0, "exchange-v1")
                    for width_key in (320, 390, 430):
                        fixture.setdefault("hotspots", {})[str(width_key)] = json.loads((OUT / f"profile-hits-{width_key}.json").read_text(encoding="utf-8"))
                    (OUT / "fixture.js").write_text("const NAV_FIXTURE = " + json.dumps(fixture, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
                ctx.close()
        browser.close()
    (OUT / "before-metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    for path in OUT.glob("*.webp"):
        assert path.stat().st_size <= 150_000, f"screenshot too large: {path.name}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    capture(parser.parse_args().dsn)
