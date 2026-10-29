"""Exercise the S12 mockups only; this is not a production navigation gate."""
from __future__ import annotations

import functools
import io
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        return


def screenshot(page, name: str) -> None:
    with Image.open(io.BytesIO(page.screenshot())) as shot:
        shot.convert("RGB").save(OUT / name, "WEBP", quality=76)
    assert (OUT / name).stat().st_size <= 150_000, name


def check() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(OUT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"), headless=True)
            for variant in ("a", "a6", "b", "c"):
                for width in (320, 390, 430):
                    for exchange in (0, 1):
                        for admin in (0, 1):
                            ctx = browser.new_context(viewport={"width": width, "height": 640}, has_touch=True, is_mobile=True)
                            page = ctx.new_page()
                            errors = []
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            url = f"http://127.0.0.1:{server.server_port}/phone.html?v={variant}&w={width}&exchange={exchange}&admin={admin}"
                            page.goto(url, wait_until="networkidle")
                            assert page.locator(".profile-shot").evaluate("n=>n.complete && n.naturalWidth>0"), url
                            more = page.locator('#dock [data-key="more"]')
                            box = more.bounding_box()
                            assert box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1, url
                            if not exchange and not admin:
                                screenshot(page, f"{variant}-profile-{width}.webp")
                            more.click()
                            geometry = page.evaluate("""() => ({overflow:document.documentElement.scrollWidth>innerWidth,
                              small:[...document.querySelectorAll('.tab,.row,#quick button')].filter(n=>{const r=n.getBoundingClientRect();return r.width<44||r.height<44}).map(n=>n.innerText),
                              dock:[...document.querySelectorAll('#dock button,#quick button')].map(n=>n.dataset.key),
                              rows:[...document.querySelectorAll('.row')].map(n=>n.dataset.key)})""")
                            assert not geometry["overflow"] and not geometry["small"], (url, geometry)
                            assert not set(geometry["dock"]) & set(geometry["rows"]), url
                            all_keys = set(geometry["dock"] + geometry["rows"])
                            expected = set(page.evaluate("Object.keys(NAV_FIXTURE.items)"))
                            if not exchange:
                                expected.discard("exchange-v1")
                            if not admin:
                                expected -= {"admin", "purge"}
                            assert all_keys == expected, (url, all_keys ^ expected)
                            if not exchange and not admin:
                                screenshot(page, f"{variant}-more-{width}.webp")
                            page.locator("#search").fill("путеводитель")
                            assert page.locator(".row").count() == 1
                            page.locator("#search").fill("<img src=x onerror=alert(1)>")
                            assert page.locator(".empty").count() == 1
                            assert page.locator("#sections img").count() == 0
                            page.locator(".back").click()
                            # Every modelled destination opens; a sheet restores its origin and focus.
                            for key in sorted(expected - {"profile", "more"}):
                                page.evaluate("openSection('profile')")
                                if key in geometry["dock"]:
                                    target = page.locator(f'#dock button[data-key="{key}"],#quick button[data-key="{key}"]')
                                else:
                                    more.click()
                                    target = page.locator(f'.row[data-key="{key}"]')
                                origin = page.locator('[aria-current="page"]').get_attribute('data-key')
                                target.click()
                                assert page.locator('[aria-current="page"]').count() == 1, (url, key)
                                assert page.locator('[aria-current="page"]').get_attribute('data-key') == (key if key in geometry['dock'] else 'more')
                                if key == "wallet":
                                    assert page.locator("dialog[open]").count() == 1
                                    page.keyboard.press("Escape")
                                    assert page.locator("dialog[open]").count() == 0
                                    page.wait_for_function("origin => document.querySelector('[aria-current=page]')?.dataset.key === origin", arg=origin)
                                    assert target.evaluate('n=>n===document.activeElement')
                                else:
                                    assert page.locator("#content h1").inner_text() == page.evaluate("NAV_FIXTURE.items[current].label")
                            # Network loss after load cannot block the prototype's navigation.
                            ctx.set_offline(True)
                            more.click()
                            page.locator(".row[data-key='guide']").click()
                            assert page.locator("#content h1").inner_text() == "Путеводитель"
                            assert not errors, (url, errors)
                            results.append({"variant": variant, "width": width, "exchange": bool(exchange), "admin": bool(admin), "destinations": len(expected), "result": "pass"})
                            ctx.close()
            page = browser.new_page(viewport={"width": 1500, "height": 1380})
            page.goto(f"http://127.0.0.1:{server.server_port}/preview.html", wait_until="networkidle")
            screenshot(page, "comparison-390.webp")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    (OUT / "checks.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"S12 mockups: {len(results)} combinations passed (production navigation not changed)")


if __name__ == "__main__":
    check()
