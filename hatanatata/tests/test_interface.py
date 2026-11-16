import asyncio
import time
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from hatanatata.bot import Bot
from hatanatata.models import Listing
from hatanatata.preferences import updated_search
from hatanatata.scanner import query_key
from hatanatata.sources import search_url
from hatanatata.store import Store
from hatanatata.telegram import Telegram, TelegramError
from hatanatata.views import listing_text


def item(number=1, price=1200):
    return Listing(
        "flatfox",
        f"https://flatfox.ch/en/flat/test/{number}/",
        "Helle Wohnung",
        "Wetzikon ZH",
        f"Teststrasse {number}, 8620 Wetzikon ZH",
        price,
        2.5,
        58,
    )


@pytest.fixture
def env(tmp_path):
    store = Store(tmp_path / "isolated.db")
    for uid in (1, 2):
        store.ensure_user(uid)
        store.set_user(uid, active=True)
    telegram = type(
        "FakeTelegram",
        (),
        {
            "send": AsyncMock(),
            "call": AsyncMock(),
            "panel": AsyncMock(return_value={"message_id": 41}),
        },
    )()
    yield store, telegram, Bot(store, telegram, [1, 2])
    store.close()


def message(text, uid=1):
    return {
        "message": {
            "from": {"id": uid},
            "chat": {"id": uid, "type": "private"},
            "text": text,
        }
    }


def callback(data, uid=1, mid=41):
    return {
        "callback_query": {
            "id": "cb",
            "from": {"id": uid},
            "message": {"message_id": mid, "chat": {"id": uid, "type": "private"}},
            "data": data,
        }
    }


def action_button(telegram, prefix):
    keyboard = telegram.panel.call_args.args[2]
    return next(
        b["callback_data"]
        for row in keyboard["inline_keyboard"]
        for b in row
        if b.get("callback_data", "").startswith(prefix)
    )


def seed(store, items):
    store.query("q", "flatfox", "Wetzikon ZH")
    store.query_ok("q", items, 180, False)


def test_carousel_sends_one_panel_and_navigates_in_place(env):
    store, tg, bot = env
    seed(store, [item(1, 1400), item(2, 1100), item(3, 1300)])
    asyncio.run(bot.handle(message("/current")))
    assert tg.panel.call_count == 1
    assert "1 из 3" in tg.panel.call_args.args[1]
    assert "1 100 CHF" in tg.panel.call_args.args[1]
    assert tg.panel.call_args.args[3] is None
    asyncio.run(bot.handle(callback(action_button(tg, "browse:"))))
    assert "2 из 3" in tg.panel.call_args.args[1]
    assert "1 300 CHF" in tg.panel.call_args.args[1]
    assert tg.panel.call_args.args[3] == 41
    tg.send.assert_not_called()


def test_favorite_buttons_are_idempotent_and_personal(env):
    store, tg, bot = env
    seed(store, [item()])
    asyncio.run(bot.handle(message("/current")))
    save = action_button(tg, "fav:add:")
    asyncio.run(bot.handle(callback(save)))
    asyncio.run(bot.handle(callback(save)))
    assert len(store.favorites(1)) == 1
    assert not store.favorites(2)
    assert "Убрать из избранного" in str(tg.panel.call_args.args[2])
    remove = action_button(tg, "fav:remove:")
    asyncio.run(bot.handle(callback(remove)))
    asyncio.run(bot.handle(callback(remove)))
    assert not store.favorites(1)


def test_favorite_survives_cache_pruning_filters_and_reopen(env):
    store, tg, bot = env
    seed(store, [item()])
    store.save_favorite(1, item(), time.time() - 86400 * 40)
    search = store.search(1)
    search.cities = ["Uster"]
    store.save_search(1, search)
    with store.db:
        store.db.execute("DELETE FROM listings")
    with StoreForTest(
        store.db.execute("PRAGMA database_list").fetchone()[2]
    ) as reopened:
        assert reopened.is_favorite(1, item().key)
        assert reopened.find_listing(item().key[:24], 1)[0].price == 1200
    asyncio.run(bot.handle(message("/favorites")))
    assert "1 из 1" in tg.panel.call_args.args[1]
    assert "Сохранённый вариант" in tg.panel.call_args.args[1]
    assert not store.find_listing(item().key[:24], 2)


class StoreForTest:
    def __init__(self, path):
        self.store = Store(path)

    def __enter__(self):
        return self.store

    def __exit__(self, *args):
        self.store.close()


def test_remove_last_favorite_returns_helpful_empty_screen(env):
    store, tg, bot = env
    seed(store, [item()])
    store.save_favorite(1, item(), time.time())
    asyncio.run(bot.handle(message("/favorites")))
    asyncio.run(bot.handle(callback(action_button(tg, "fav:remove:"))))
    assert "В избранном пока пусто" in tg.panel.call_args.args[1]
    assert "На главную" in str(tg.panel.call_args.args[2])


def test_stale_browser_buttons_cannot_save_another_card(env):
    store, tg, bot = env
    seed(store, [item(1), item(2)])
    asyncio.run(bot.handle(message("/current")))
    stale = action_button(tg, "fav:add:")
    asyncio.run(bot.handle(message("/current")))
    asyncio.run(bot.handle(callback(stale)))
    assert not store.favorites(1)
    assert "список уже обновился" in tg.panel.call_args.args[1]


def test_updated_filters_reapply_when_navigating_old_results(env):
    store, tg, bot = env
    seed(store, [item(1), item(2)])
    asyncio.run(bot.handle(message("/current")))
    next_card = action_button(tg, "browse:")
    search = store.search(1)
    search.max_price = 500
    store.save_search(1, search)
    asyncio.run(bot.handle(callback(next_card)))
    assert "Подходящих вариантов пока нет" in tg.panel.call_args.args[1]


def test_settings_error_stays_in_context_and_cancel_preserves_value(env):
    store, tg, bot = env
    asyncio.run(bot.handle(callback("edit:price")))
    assert "Сейчас: до 1 500" in tg.panel.call_args.args[1]
    asyncio.run(bot.handle(message("abc")))
    assert "Не удалось сохранить" in tg.panel.call_args.args[1]
    assert store.search(1).max_price == 1500
    assert tg.panel.call_args.args[3] == 41
    asyncio.run(bot.handle(callback("settings")))
    assert store.user(1)["pending"] == ""
    assert store.search(1).max_price == 1500


def test_status_summary_and_details_distinguish_partial_and_failed(env):
    store, tg, bot = env
    key = query_key("flatfox", "Wetzikon ZH", search_url("flatfox", "Wetzikon ZH"))
    store.query(key, "flatfox", "Wetzikon ZH")
    store.query_ok(key, [item()], 180, True)
    assert bot.source_state(1, "flatfox") == "часть выдачи"
    asyncio.run(bot.handle(message("/status")))
    assert "Flatfox · часть выдачи" in str(tg.panel.call_args.args[2])
    store.query_error(key, "HTTP 403", 1800)
    asyncio.run(bot.handle(callback("source:flatfox")))
    text = tg.panel.call_args.args[1]
    assert "недоступен" in text and "HTTP 403" in text
    assert "не раньше чем через 30 мин." in text


def test_status_does_not_claim_all_cities_checked(env):
    store, _, bot = env
    search = store.search(1)
    search.cities = ["Wetzikon ZH", "Uster"]
    store.save_search(1, search)
    key = query_key("flatfox", "Wetzikon ZH", search_url("flatfox", "Wetzikon ZH"))
    store.query(key, "flatfox", "Wetzikon ZH")
    store.query_ok(key, [item()], 180, False)
    assert bot.source_state(1, "flatfox") == "ожидает проверки"


@pytest.mark.parametrize("value", ["1500", "1 500 CHF", "CHF 1500", "1’500", "1.500"])
def test_friendly_budget_input(env, value):
    assert updated_search(env[0].search(1), "price", value).max_price == 1500


@pytest.mark.parametrize(
    "data",
    [
        "set:",
        "fav:add:",
        "browse:fake:-1",
        "browse:fake:999",
        "sort:invalid:price",
        "toggle:unknown",
    ],
)
def test_invalid_buttons_do_not_crash_or_modify_preferences(env, data):
    store, _, bot = env
    before = store.search(1).to_dict()
    asyncio.run(bot.handle(callback(data)))
    assert store.search(1).to_dict() == before


def test_all_callback_payloads_fit_telegram_limit(env):
    store, tg, bot = env
    seed(store, [item(1), item(2)])
    for action in [
        "home",
        "settings",
        "edit:cities",
        "edit:price",
        "sources",
        "status",
        "current",
        "favorites",
    ]:
        asyncio.run(bot.handle(callback(action)))
        for row in tg.panel.call_args.args[2]["inline_keyboard"]:
            for button in row:
                if "callback_data" in button:
                    assert 1 <= len(button["callback_data"].encode()) <= 64


def test_panel_edits_and_handles_deleted_or_unchanged_messages():
    async def scenario():
        tg = Telegram("fake-test-token", None)
        tg.call = AsyncMock(return_value={"message_id": 12})
        tg.send = AsyncMock(return_value={"message_id": 13})
        await tg.panel(1, "text", {"inline_keyboard": []}, 12)
        assert tg.call.call_args.args[0] == "editMessageText"
        tg.send.assert_not_called()
        tg.call.side_effect = TelegramError(400, not_modified=True)
        assert await tg.panel(1, "text", {}, 12) == {"message_id": 12}
        tg.send.assert_not_called()
        tg.call.side_effect = TelegramError(400)
        assert await tg.panel(1, "text", {}, 12) == {"message_id": 13}
        tg.send.reset_mock()
        tg.call.side_effect = TelegramError(429, 50)
        with pytest.raises(TelegramError):
            await tg.panel(1, "text", {}, 12)
        tg.send.assert_not_called()

    asyncio.run(scenario())


def test_saved_card_handles_unknown_updated_price_and_rooms():
    text = listing_text(replace(item(), price=None, rooms=None, area=None))
    assert "Цена по запросу" in text
    assert "Комнаты не указаны" in text


def test_new_notification_has_open_and_save_buttons(env):
    store, tg, bot = env
    seed(store, [item()])
    store.record_delivery(1, item())

    async def scenario():
        sent = asyncio.Event()

        async def capture(*args):
            sent.set()

        tg.send.side_effect = capture
        worker = asyncio.create_task(bot.deliver())
        try:
            await asyncio.wait_for(sent.wait(), timeout=2)
            keyboard = tg.send.call_args.args[2]
            assert keyboard["inline_keyboard"][0][0]["url"] == item().url
            assert keyboard["inline_keyboard"][1][0]["callback_data"].startswith(
                "fav:add:"
            )
            assert not store.pending()
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())
