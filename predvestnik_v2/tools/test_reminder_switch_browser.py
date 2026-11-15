#!/usr/bin/env python3
"""«Напоминать о …» на игровых экранах (S23cw) в настоящем приложении на стенде «как прод» (tools/ui_stand.py, порт 8403).

Проверяет то, что видит игрок: переключатель под шапкой показывает согласие из базы; нажатие сразу включает и выключает
ту же категорию, что «Настройки › Уведомления» (строка user_notification_prefs меняется, ничего лишнего не включается);
чат с ботом не открыт — лист «Осталось открыть чат с ботом» с кнопкой «Открыть чат»; включено, но писать некуда — тот же лист
с «Выключить»; категории нет — переключатель прячется; «Настройки» и переключатель на экране не расходятся;
VIP-тумблер «Напоминать о поручении дня» горит, только когда письмо действительно уйдёт.

    BOT_TOKEN=1:x PYTHONPATH=. DATABASE_URL=postgresql://predvestnik_preprod@127.0.0.1:55432/predvestnik_preprod \\
        python tools/test_reminder_switch_browser.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui_smoke import chromium_path, open_app  # noqa: E402
from ui_stand import DEFAULT_DSN, PERSONA_ID as USER_ID, Stand, set_game_flags  # noqa: E402

DSN = os.getenv("DATABASE_URL", DEFAULT_DSN)
SWITCH = "[data-reminder='{key}']"
# Ответ GET /profile/notification-prefs правится на месте, как в ui_smoke_checks._reminder: «чат с ботом не открыт» без Telegram
CHAT_CLOSED = ("window.__realApi = window.__realApi || api; window.api = (p, o) => p === '/profile/notification-prefs' && !o "
               "? window.__realApi.call(null, p, o).then(d => Object.assign({}, d, {dm_ready: false})) : window.__realApi.call(null, p, o);")
CHAT_OPEN = "if (window.__realApi) window.api = window.__realApi; _remind.at = 0;"


async def _consent(key: str) -> bool | None:
    import asyncpg
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute("SET search_path TO predvestnik, public")
        return await conn.fetchval("SELECT enabled FROM user_notification_prefs WHERE user_id = $1 AND category = $2", USER_ID, key)
    finally:
        await conn.close()


async def _reset() -> None:
    """Согласий нет, а чат с ботом открыт (игрок нажимал «Старт»): так бот вправе писать, если игрок включит напоминание."""
    import asyncpg
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute("SET search_path TO predvestnik, public")
        await conn.execute("DELETE FROM user_notification_prefs WHERE user_id = $1", USER_ID)
        await conn.execute("INSERT INTO dm_push_settings (user_id, dm_confirmed_at) VALUES ($1, NOW()) ON CONFLICT (user_id) "
                           "DO UPDATE SET dm_confirmed_at = NOW(), dm_disabled_at = NULL, paused_at = NULL", USER_ID)
    finally:
        await conn.close()


def _in_thread(coro_fn, *args):
    """Playwright's sync API owns this thread's loop, so the database is used from a thread of its own."""
    box: list = []
    thread = threading.Thread(target=lambda: box.append(asyncio.run(coro_fn(*args))))
    thread.start(); thread.join()
    return box[0] if box else None


def consent(key: str) -> bool | None:
    return _in_thread(_consent, key)


def state(page, key: str) -> str | None:
    return page.get_attribute(SWITCH.format(key=key), "aria-checked")


def wait_state(page, key: str, value: str) -> None:
    page.wait_for_function(f"() => {{ const b = document.querySelector(\"{SWITCH.format(key=key)}\"); "
                           f"return b && !b.hasAttribute('data-state') && !b.hasAttribute('aria-busy') && b.getAttribute('aria-checked') === '{value}'; }}",
                           timeout=8000)


def main() -> int:
    asyncio.run(set_game_flags(DSN, True))
    with Stand(8403, DSN, skin="void", tier="SSS", rich=True) as stand:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chromium_path())
            ctx, page, probe = open_app(stand, browser, 390)
            page.evaluate("() => api('/profile/notification-prefs')")   # таблицы лички создаёт первый запрос, как в проде
            _in_thread(_reset)

            # 1. Чат открыт: экран показывает «выключено», нажатие включает категорию в базе, второе — выключает
            page.evaluate("() => { _remind.at = 0; openQuestsV1(); }")
            page.wait_for_selector(SWITCH.format(key="quests"))
            wait_state(page, "quests", "false")
            assert "Напоминать о заданиях" in page.inner_text(SWITCH.format(key="quests"))
            page.click(SWITCH.format(key="quests"))
            wait_state(page, "quests", "true")
            assert consent("quests") is True, "the tap saves the same consent as «Настройки › Уведомления»"
            assert consent("chests") is None and consent("pets") is None, "nothing else is switched on"
            page.wait_for_function("() => { const t = el('toast'); return t && t.classList.contains('show') && t.textContent.includes('Напоминание включено'); }",
                                   timeout=8000)   # заголовок тоста и сама подсказка категории: о чём напишет бот
            assert not page.evaluate("() => el('modal').open"), "with the chat open no sheet is needed"
            page.click(SWITCH.format(key="quests"))
            wait_state(page, "quests", "false")
            assert consent("quests") is False

            # 2. Чат с ботом не открыт: включение сохраняется и открывает лист с кнопкой «Открыть чат»
            page.evaluate("() => { " + CHAT_CLOSED + " _remind.at = 0; openChestsV1(); }")
            page.wait_for_selector(SWITCH.format(key="chests"))
            wait_state(page, "chests", "false")
            page.click(SWITCH.format(key="chests"))
            page.wait_for_function("() => el('modal').open", timeout=8000)
            assert "Осталось открыть чат с ботом" in page.inner_text("#mt")
            assert [b.inner_text() for b in page.query_selector_all("#mf button")] == ["Позже", "Открыть чат"]
            assert consent("chests") is True and state(page, "chests") == "true"
            page.evaluate("() => CM()")
            # включено, а писать по-прежнему некуда: нажатие предлагает «Выключить» или открыть чат, ничего не меняя молча
            page.click(SWITCH.format(key="chests"))
            page.wait_for_function("() => el('modal').open", timeout=8000)
            assert [b.inner_text() for b in page.query_selector_all("#mf button")] == ["Выключить", "Открыть чат"]
            assert consent("chests") is True
            page.click("#mf button:has-text('Выключить')")
            wait_state(page, "chests", "false")
            assert consent("chests") is False

            # 3. «Настройки» и переключатель на экране — одно и то же согласие
            page.evaluate("() => { " + CHAT_OPEN + " openSettingsModal(); }")
            page.wait_for_function("() => _ST.notif && document.querySelector('#pg-settings .st-switch')", timeout=8000)
            page.evaluate("() => _stNotifSet('pets', true)")
            page.wait_for_function("() => _remind.prefs && (_remind.prefs.categories.find(c => c.key === 'pets') || {}).enabled === true", timeout=8000)
            page.evaluate("() => openPetsV1()")
            page.wait_for_selector(SWITCH.format(key="pets"))
            wait_state(page, "pets", "true")
            assert consent("pets") is True

            # 4. Категории нет в ответе (закрыта): переключатель прячется, а не ведёт в никуда
            page.evaluate("() => { window.__realApi = window.__realApi || api; window.api = (p, o) => p === '/profile/notification-prefs' && !o "
                          "? window.__realApi.call(null, p, o).then(d => Object.assign({}, d, {categories: d.categories.filter(c => c.key !== 'market')})) "
                          ": window.__realApi.call(null, p, o); _remind.at = 0; openPlayerExchangeV1(); }")
            page.wait_for_selector(SWITCH.format(key="market"), state="attached")
            page.wait_for_function("() => document.querySelector(\"[data-reminder='market']\").hidden", timeout=8000)

            # 5. VIP «Напоминать о поручении дня»: письмо уходит только с категорией «VIP», поэтому без неё тумблер не горит,
            #    а включение тут же включает и категорию (до S23cw тумблер «горел», а писем не было)
            page.evaluate("() => { " + CHAT_OPEN + " openStoreV3('vip'); }")
            vip = "[data-reminder-also='vip_expiry']"
            page.wait_for_selector(vip, state="attached", timeout=15000)
            page.wait_for_function(f"() => document.querySelector(\"{vip}\").getAttribute('aria-checked') === 'false'", timeout=8000)
            page.evaluate(f"() => document.querySelector(\"{vip}\").click()")
            page.wait_for_function(f"() => document.querySelector(\"{vip}\").getAttribute('aria-checked') === 'true'", timeout=8000)
            assert consent("vip_expiry") is True, "the VIP switch turns the «VIP» category on as well"

            fails = probe.take()
            assert not fails, fails
            ctx.close()
            browser.close()
    print("OK: reminder switch — consent on/off, chat-closed sheet, settings in sync, hidden without a category, VIP switch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
