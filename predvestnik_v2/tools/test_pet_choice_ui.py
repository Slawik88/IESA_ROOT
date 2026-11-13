"""Actual pet choice UI: free first choice, server price, stale payload and long names."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path

from playwright.sync_api import sync_playwright
from ui_smoke import chromium_path, open_app
from ui_stand import DEFAULT_DSN, Stand
from test_screen_consistency_ui import check_width, shot


def run(stand, browser, directory: Path) -> None:
    for width in (320, 390, 430):
        ctx, page, probe = open_app(stand, browser, width)
        page.wait_for_function("!document.getElementById('preloader')")
        page.evaluate("_sysFlags.pets_v2=false; _trClassic()")
        page.locator('#pg-pets .pet-tabs').wait_for()
        original = page.evaluate("async () => await api('/pets-v1/me')")
        assert len(original['pets']) >= 2
        selected, previous = original['pets'][:2]
        long_name = '<img src=x onerror=alert(1)>' + 'ОченьДлинноеИмя' * 8
        data = copy.deepcopy(original)
        data['active_pet_id'] = previous['id']
        data['active_slot_swap_cost'] = 7  # A fixture verifies the UI reads the server price.
        data['level_up'] = {'enabled': True, 'max_level': 16, 'steps': {
            str(selected['id']): {'cards': 1, 'cards_have': 1, 'level_after': 2, 'mora': 123, 'essence': 0},
        }}
        for pet in data['pets']:
            pet['active'] = pet['id'] == previous['id']
            if pet['id'] == previous['id']:
                pet['name'] = long_name
        data['activity'] = {'pet_id': previous['id']}
        page.route('**/pets-v1/me', lambda route: route.fulfill(json=data))
        page.evaluate('openPetsV1()')
        page.locator('#pg-pets .pet-tabs').wait_for()
        page.evaluate('(id) => petSelect(id)', selected['id'])
        cost = page.locator('.pt-choice-cost')
        assert '7 выносливости' in cost.inner_text()
        assert cost.locator('small span').inner_text() == long_name
        assert cost.locator('img').count() == 0
        assert float(cost.evaluate('(e)=>getComputedStyle(e).fontSize').removesuffix('px')) >= 14
        assert page.locator('.pt-choice .pt-main').is_enabled(), 'an ongoing trip must not block selection'
        assert page.locator('.pt-choice .pt-note').is_visible()
        assert page.locator('.pt-choice .pt-main').bounding_box()['height'] >= 48
        details = page.get_by_role('button', name='О питомце', exact=False)
        assert details.bounding_box()['height'] >= 48
        assert page.locator('.pt-up .v3-pill--ghost').count() == 1, 'upgrade must render as a secondary action'
        assert page.locator('.pt-up .pt-main:not(.v3-pill--ghost)').count() == 0
        check_width(page)
        shot(page, directory, 'pet-choice-long', width)
        details.click()
        page.get_by_role('dialog').wait_for()
        assert page.locator('.pt-sheet .pt-lore').count() == 1
        page.keyboard.press('Escape')
        assert page.get_by_role('dialog').count() == 0

        del data['active_slot_swap_cost']
        page.evaluate('openPetsV1()')
        page.get_by_role('button', name='Обновить список', exact=True).wait_for()
        assert 'без затрат' not in page.locator('.pt-choice-cost').inner_text()
        assert 'NaN' not in page.locator('.pt-choice-cost').inner_text()

        data['active_pet_id'] = None
        data['activity'] = None
        for pet in data['pets']:
            pet['active'] = False
        page.evaluate('openPetsV1()')
        page.get_by_role('button', name='Сделать активным', exact=True).wait_for()
        assert page.locator('.pt-choice-cost').inner_text() == 'Первый выбор — без затрат.'
        check_width(page)
        shot(page, directory, 'pet-choice-first', width)

        data['active_pet_id'] = previous['id']
        data['active_slot_swap_cost'] = original['active_slot_swap_cost']
        data['pets'] = original['pets']
        data['level_up'] = original['level_up']
        page.evaluate('openPetsV1()')
        page.locator('.pt-choice').wait_for()
        page.evaluate('window.scrollTo(0,0)')
        shot(page, directory, 'pet-choice', width)
        assert not probe.problems, probe.problems
        ctx.close()
        print(f'OK pet choice @{width}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn', default=os.getenv('DATABASE_URL', DEFAULT_DSN))
    parser.add_argument('--shots', type=Path, required=True)
    args = parser.parse_args()
    with Stand(18434, args.dsn, skin='void', tier='SSS', rich=True) as stand:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chromium_path())
            run(stand, browser, args.shots)
            browser.close()
