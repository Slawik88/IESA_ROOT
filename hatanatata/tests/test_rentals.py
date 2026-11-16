import asyncio
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from hatanatata.bot import Bot, listing_text, updated_search
from hatanatata.models import Listing, Search, safe_url
from hatanatata.network import Fetcher, FetchError, retry_after, robots_allowed
from hatanatata.scanner import collect, plans, scan_once
from hatanatata.sources import (
    Page,
    SourceError,
    number,
    parse_flatfox,
    parse_html,
    search_url,
)
from hatanatata.store import Store

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def store(tmp_path):
    state = Store(tmp_path / "test.db")
    for user_id in (1, 2):
        state.ensure_user(user_id)
        state.set_user(user_id, active=True)
    yield state
    state.close()


def listing(**changes):
    return replace(
        Listing(
            "flatfox",
            "https://flatfox.ch/en/flat/test/1/",
            "Wohnung mit Garage",
            "Wetzikon ZH",
            "Teststrasse 12, 8620 Wetzikon ZH",
            1230,
            2.5,
            58,
        ),
        **changes,
    )


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1.420", 1420),
        ("1’350", 1350),
        ("1'230", 1230),
        ("2,5", 2.5),
        (None, None),
        ("auf Anfrage", None),
    ],
)
def test_swiss_numbers(text, value):
    assert number(text) == value


@pytest.mark.parametrize("source", ["rentumo", "huusbro", "realadvisor", "homematch"])
def test_real_public_card_fixtures(source):
    page = parse_html(
        source,
        search_url(source, "Wetzikon ZH"),
        (FIXTURES / (source + ".html")).read_text(encoding="utf-8"),
    )
    assert page.listings
    assert all(x.city and x.price and x.rooms for x in page.listings)
    assert all(x.url.startswith("https://") for x in page.listings)


def test_huusbro_gross_price_not_net():
    page = parse_html(
        "huusbro",
        search_url("huusbro", "Wetzikon ZH"),
        (FIXTURES / "huusbro.html").read_text(encoding="utf-8"),
    )
    assert page.listings[1].price == 2160
    assert page.listings[1].rooms == 4.5


def test_flatfox_details_exclude_shared_rooms():
    page = parse_flatfox((FIXTURES / "flatfox.json").read_text(encoding="utf-8"))
    matches = [x for x in page.listings if Search().matches(x)]
    assert [x.price for x in matches] == [1230]
    assert "Priority" in matches[0].price_note


def test_layout_change_and_captcha_are_errors():
    with pytest.raises(SourceError):
        parse_html(
            "homegate",
            search_url("homegate", "Wetzikon ZH"),
            "Please enable JS and disable any ad blocker",
        )
    with pytest.raises(SourceError):
        parse_html("huusbro", search_url("huusbro", "Wetzikon ZH"), "<h1>Search</h1>")
    assert (
        parse_html(
            "huusbro", search_url("huusbro", "Wetzikon ZH"), "<h1>0 Objekte</h1>"
        ).listings
        == []
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"price": None},
        {"price": 1501},
        {"rooms": None},
        {"rooms": 3.5},
        {"city": "Uster"},
        {"category": "other"},
    ],
)
def test_filters_reject_unknown_and_nonmatching_values(changes):
    assert not Search().matches(listing(**changes))


def test_filters_normalize_city_and_apply_area_and_exclusions():
    assert Search().matches(listing(city="Wetzikon (ZH)"))
    assert not Search(min_area=60).matches(listing())
    assert not Search(exclude="möbliert, Garage").matches(listing())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("price", "-1"),
        ("interval", "1"),
        ("rooms", "3.5 1.5"),
        ("cities", "Ветцикон"),
        ("cities", ""),
        ("area", "-10"),
    ],
)
def test_invalid_preferences(field, value):
    with pytest.raises(ValueError):
        updated_search(Search(), field, value)


def test_room_range_comma_decimal_and_custom_url_reset():
    assert updated_search(Search(), "rooms", "1,5 2,5").min_rooms == 1.5
    search = Search(urls={"huusbro": "https://huusbro.ch/de/mieten/wetzikon"})
    assert updated_search(search, "cities", "Uster").urls == {}


@pytest.mark.parametrize(
    "url",
    [
        "http://flatfox.ch/",
        "https://flatfox.ch.evil.com/",
        "https://127.0.0.1/",
        "https://flatfox.ch:8011/",
        "https://name:pass@flatfox.ch/",
    ],
)
def test_custom_urls_cannot_access_internal_or_other_hosts(url):
    with pytest.raises(ValueError):
        safe_url(url, "flatfox")


def test_robots_wildcards_specific_groups_and_longest_allow():
    rules = "User-agent: *\nAllow: /\nDisallow: /api/\nAllow: /api/public/\nDisallow: /*?sort_by=*\nUser-agent: SomeOtherBot\nDisallow: /\n"
    assert robots_allowed(rules, "https://flatfox.ch/api/public/list/")
    assert not robots_allowed(rules, "https://flatfox.ch/api/private/")
    assert not robots_allowed(rules, "https://flatfox.ch/rent?sort_by=date")
    assert robots_allowed(rules, "https://flatfox.ch/rent")
    assert retry_after("1") == 120
    assert retry_after("nonsense") == 300


def test_personal_settings_and_shared_query(store):
    search = store.search(1)
    search.max_price = 1350
    store.save_search(1, search)
    assert store.search(2).max_price == 1500
    assert len(plans(store)) == 7
    search.paused = True
    store.save_search(1, search)
    assert all(p["users"] == [2] for p in plans(store).values())


def test_durable_outbox_and_conservative_cross_site_dedup(store):
    item = listing()
    store.query("query", "flatfox", "Wetzikon ZH")
    store.query_ok("query", [item], 180, False)
    store.record_delivery(1, item)
    store.record_delivery(1, item)
    store.record_delivery(2, item)
    assert len(store.pending()) == 2
    store.delivery_result(store.pending()[0], "sent")
    assert len(store.pending()) == 1
    assert (
        item.duplicate_key
        == listing(
            source="huusbro", url="https://huusbro.ch/de/listings/test/123"
        ).duplicate_key
    )
    assert (
        listing(address="8620 Wetzikon").duplicate_key
        != listing(
            address="8620 Wetzikon", url="https://flatfox.ch/en/flat/test/2/"
        ).duplicate_key
    )
    search = store.search(2)
    search.max_price = 1000
    store.save_search(2, search)
    assert not store.pending()


def test_baseline_does_not_notify_but_new_discovery_does(store, monkeypatch):
    async def scenario():
        for uid in (1, 2):
            search = store.search(uid)
            search.sources = ["flatfox"]
            store.save_search(uid, search)
        gather = AsyncMock(return_value=Page([listing()]))
        monkeypatch.setattr("hatanatata.scanner.collect", gather)
        await scan_once(store, None)
        assert gather.await_count == 1  # two recipients, one request plan
        assert not store.pending()
        store.db.execute("UPDATE queries SET next_run=0")
        gather.return_value = Page(
            [
                listing(),
                listing(
                    url="https://flatfox.ch/en/flat/test/2/",
                    address="Teststrasse 13, 8620 Wetzikon ZH",
                ),
            ]
        )
        await scan_once(store, None)
        assert len(store.pending()) == 2
        store.db.execute("UPDATE queries SET next_run=0")
        await scan_once(store, None)
        assert len(store.pending()) == 2

    asyncio.run(scenario())


def test_flatfox_uses_pin_ids_not_ignored_map_filters(store):
    class FakeFetcher:
        coordinates = AsyncMock(return_value=(47.32, 8.80))
        robots = AsyncMock()
        raw = AsyncMock(return_value=(200, '[{"pk":123},{"pk":456}]', {}))
        page = AsyncMock(return_value=Page([listing()]))

    fetcher = FakeFetcher()
    page = asyncio.run(collect(fetcher, "flatfox", "Wetzikon ZH", "unused"))
    assert len(page.listings) == 1
    assert "pk=456&pk=123" in fetcher.page.call_args.args[1]
    assert "max_count=100" in fetcher.raw.call_args.args[0]


def test_http_304_reuses_normalized_page(store):
    item = listing()
    store.cache_page(item.url, '"test"', None, Page([item]))
    fetcher = Fetcher(store, None)
    fetcher.robots = AsyncMock()
    fetcher.raw = AsyncMock(return_value=(304, "", {}))
    parser = AsyncMock()
    result = asyncio.run(fetcher.page("flatfox", item.url, parser))
    assert result.listings == [item]
    assert fetcher.raw.call_args.kwargs["headers"]["If-None-Match"] == '"test"'
    parser.assert_not_called()


def test_source_backoff_survives_failure(store, monkeypatch):
    for uid in (1, 2):
        search = store.search(uid)
        search.sources = ["homegate"]
        store.save_search(uid, search)
    monkeypatch.setattr(
        "hatanatata.scanner.collect",
        AsyncMock(side_effect=FetchError("HTTP 403", 1800)),
    )
    asyncio.run(scan_once(store, None))
    row = store.db.execute("SELECT * FROM queries").fetchone()
    assert row["error"] == "HTTP 403"
    assert row["next_run"] > time.time() + 1700
    assert not store.pending()


def test_bot_authorization_and_private_chat_boundary(store):
    telegram = type("FakeTelegram", (), {"send": AsyncMock(), "call": AsyncMock()})()
    bot = Bot(store, telegram, [1, 2])
    for uid, chat_type, chat_id in [
        (3, "private", 3),
        (1, "group", -1),
        (1, "private", 2),
    ]:
        asyncio.run(
            bot.handle(
                {
                    "message": {
                        "from": {"id": uid},
                        "chat": {"id": chat_id, "type": chat_type},
                        "text": "/price 900",
                    }
                }
            )
        )
    telegram.send.assert_not_called()
    assert store.search(1).max_price == 1500
    assert store.user(3) is None


def test_bot_inline_settings_validate_and_persist(store):
    telegram = type("FakeTelegram", (), {"send": AsyncMock(), "call": AsyncMock()})()
    bot = Bot(store, telegram, [1, 2])

    def message(text):
        return {
            "message": {
                "from": {"id": 1},
                "chat": {"id": 1, "type": "private"},
                "text": text,
            }
        }

    asyncio.run(bot.handle(message("/price")))
    assert store.user(1)["pending"] == "price"
    asyncio.run(bot.handle(message("wrong")))
    assert store.search(1).max_price == 1500
    asyncio.run(bot.handle(message("1350")))
    assert store.search(1).max_price == 1350
    assert store.user(1)["pending"] == ""
    assert store.search(2).max_price == 1500
    callback = {
        "callback_query": {
            "id": "cb",
            "from": {"id": 1},
            "message": {"chat": {"id": 1, "type": "private"}},
            "data": "set:rooms:2 3.5",
        }
    }
    asyncio.run(bot.handle(callback))
    assert store.search(1).min_rooms == 2


def test_message_escapes_untrusted_listing_text():
    text = listing_text(listing(title='<a href="evil">bad</a>'))
    assert "&lt;a href=&quot;evil&quot;&gt;" in text
    assert '<a href="evil">' not in text
