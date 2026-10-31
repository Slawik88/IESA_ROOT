"""Portable gallery usability and shared-renderer parity with the real local Mini App."""
import argparse
import difflib
import json
import os
import shutil
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_smoke import INIT, PROFILE_READY
from ui_stand import Stand


def check(gallery, dsn):
    manifest = json.loads((gallery / "manifest.js").read_text(encoding="utf-8")[14:-1])
    assert len(manifest["skins"]) == 42 and len(manifest["coverage"]) == 2646
    assert all(row["changed_percent"] == 0 for row in manifest["coverage"])
    assert all(row.get("telegram_original", {}).get("changed_percent", 0) == 0 for row in manifest["coverage"])
    checks = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None,
                                     args=["--disable-gpu", "--disable-lcd-text", "--force-color-profile=srgb"])
        errors = []
        for width in (320, 390, 430, 1280):
            context = browser.new_context(viewport={"width": width, "height": 844})
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto((gallery / "index.html").as_uri())
            assert page.locator(".skin").count() == 6
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.locator("#search").fill("Бездна")
            assert page.locator(".skin").count() == 1
            page.locator('[data-tier="SSS"]').click()
            page.locator("#detail").wait_for(state="visible")
            page.frame_locator("#before").locator('html[data-ready="yes"]').wait_for()
            assert page.locator("#concept tbody tr").count() == 7
            for mode in ("profile", "nick", "top", "telegram"):
                page.locator("#mode").select_option(mode)
                # Chromium suspends rAF in an offscreen iframe: inspect the same visible frame a reader sees.
                page.locator('#after').scroll_into_view_if_needed()
                frame = page.locator("#after").element_handle().content_frame()
                frame.wait_for_function("mode=>document.documentElement.dataset.ready==='yes'&&LAB_STATE.mode===mode", arg=mode)
            for device, cap in (("high", 7), ("mid", 6), ("low", 3), ("calm", 7)):
                page.locator("#device").select_option(device)
                page.locator('#before').scroll_into_view_if_needed()
                frame = page.locator("#before").element_handle().content_frame()
                frame.wait_for_function("device=>document.documentElement.dataset.ready==='yes'&&LAB_STATE.device===device", arg=device)
                assert frame.evaluate("LAB_STATE.device_cap") == cap
            page.locator('#mode').select_option('profile')
            page.locator('#device').select_option('reduced')
            page.frame_locator('#before').locator('img').wait_for()
            assert page.locator('#mode').is_disabled() and page.locator('#play').is_disabled()
            page.locator('#device').select_option('high')
            page.locator("#notes").fill("Оставить тёмный центр")
            page.keyboard.press("Escape")
            assert not page.locator("#detail").is_visible()
            assert page.evaluate("document.activeElement.dataset.tier==='SSS'")
            page.locator('[data-tier="D"]').click()
            assert page.locator("#notes").input_value() == "Оставить тёмный центр"
            page.locator("#close").click()
            page.locator("#search").fill("")
            page.locator("#score").select_option("2")
            assert "Найдено: 3" in page.locator("#count").inner_text()
            page.locator("#score").select_option("")
            page.locator("#rarity").select_option("D")
            assert "Найдено: 4" in page.locator("#count").inner_text()
            page.locator("#rarity").select_option("")
            page.locator("#set").select_option("sakura")
            assert "Найдено: 3" in page.locator("#count").inner_text()
            page.locator('#search').fill('несуществующий образ')
            assert 'Таких образов нет' in page.locator('#rows').inner_text()
            page.screenshot(path=str(gallery.parent / f"s16-gallery-{width}.png"))
            checks += 24
            context.close()
        with tempfile.TemporaryDirectory(prefix='s16-gallery-faults-') as folder:
            copy = Path(folder) / 'gallery'
            shutil.copytree(gallery, copy)
            altered = json.loads(json.dumps(manifest))
            target = next(row for row in altered['coverage'] if row['mode'] == 'telegram')
            target['telegram_original']['changed_percent'] = .00001
            target['telegram_original']['changed_pixels'] = 1
            target['has_changes'] = True
            (copy/'manifest.js').write_text('const COMPARE='+json.dumps(altered,ensure_ascii=False)+';',encoding='utf-8')
            page = browser.new_page()
            page.goto((copy/'index.html').as_uri())
            page.locator('#search').fill(altered['skins'][target['skin']]['name'])
            assert page.locator(f'.tile.changed[data-tier="{target["tier"]}"]').count() == 1, 'Telegram-only change must highlight the tier'
            assert 'Есть изменения' in page.locator('#overview').inner_text()
            page.close()
            # Reproduce a missing lazy scene stylesheet: fail within a bounded time, never accept an empty scene.
            (copy/'before/static/skin-scene-c-v3.css').unlink()
            page = browser.new_page()
            page.goto((copy/'before/preview.html').as_uri())
            outcome = page.evaluate("""async()=>{try{await labRender({skin:'void',tier:'SSS'});return 'accepted';}catch(error){return error.message;}}""")
            assert outcome != 'accepted' and ('missing' in outcome or '8 seconds' in outcome), outcome
            page.close()
            checks += 3
        if dsn:
            with Stand(18416, dsn, skin="void", tier="SSS", rich=True) as stand:
                context = browser.new_context(viewport={"width": 390, "height": 844})
                context.add_init_script(INIT + stand.browser_init)
                context.route("https://**/*", lambda route: route.abort())
                real = context.new_page()
                real.goto(stand.url, wait_until="domcontentloaded")
                real.wait_for_function(PROFILE_READY, timeout=60000)
                preview = browser.new_page(viewport={"width": 390, "height": 430})
                preview.goto((gallery / "before/preview.html").as_uri())
                fixture = preview.evaluate("labFixture")
                for skin in ("hanami", "void", "scarlet_star"):
                    for tier in ("D", "SSS"):
                        preview.evaluate("o=>labRender(o)", {"skin": skin, "tier": tier})
                        look = preview.evaluate("LAB_DATA.looks[LAB_STATE.skin][LAB_STATE.tier]")
                        expected = real.evaluate("""({fixture,look})=>{
                          _v3Skew=Date.now()-Date.UTC(2026,9,30,12);_v3SkewKnown=true;_v3ServerTz=0;
                          const t=document.createElement('template');t.innerHTML=renderProfileHome({...fixture,look});
                          return t.content.querySelector('.ap-stage').outerHTML;
                        }""", {"fixture": fixture, "look": look})
                        assert preview.locator(".ap-stage").evaluate("e=>e.outerHTML") == expected, (skin, tier, "profile DOM differs")
                        preview.evaluate("o=>labRender(o)", {"skin": skin, "tier": tier, "mode": "top"})
                        expected = real.evaluate("""look=>{const t=document.createElement('template');
                          t.innerHTML=_v3FullRow({place:4,name:'Предвестник',look,ref:'skin_review_player_ref',level:12,is_me:false,is_vip:true,count:840},'global');
                          return t.content.firstElementChild.outerHTML;}""", look)
                        actual = preview.locator(".v3-top-list>li").evaluate("e=>e.outerHTML")
                        if actual != expected:
                            raise AssertionError((skin, tier, 'top DOM differs', '\n'.join(difflib.ndiff([expected],[actual]))))
                        checks += 2
                preview.close()
                context.close()
        assert not errors, errors
        browser.close()
    print(f"PASS {checks} gallery/parity checks; filters, four surfaces, device caps, notes, Escape/focus, and shared profile/top DOM")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gallery", type=Path, required=True)
    parser.add_argument("--dsn")
    args = parser.parse_args()
    if args.dsn:
        from urllib.parse import urlparse
        if urlparse(args.dsn).hostname not in ("127.0.0.1", "localhost", "::1"):
            raise SystemExit("loopback PostgreSQL required")
    check(args.gallery.resolve(), args.dsn)
