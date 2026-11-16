import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from hatanatata.models import SOURCES, Listing, Search
from hatanatata.network import Fetcher
from hatanatata.scanner import collect, plans
from hatanatata.sources import SourceError, parse_html, search_url
from hatanatata.store import Store
from hatanatata.views import settings_screen

FIXTURES = Path(__file__).parent / "fixtures"


def test_rentola_real_schema_and_fractional_rooms_override_rounded_schema():
    page = parse_html(
        "rentola",
        search_url("rentola", "Uster"),
        (FIXTURES / "rentola.html").read_text(encoding="utf-8"),
    )
    assert page.total == 50
    assert page.next_url == "https://rentola.ch/en/for-rent/uster?page=2"
    assert len(page.listings) == 2
    assert page.listings[1].rooms == 2.5
    assert page.listings[1].price == 1450
    assert page.listings[1].city == "Uster"
    assert Search(cities=["Uster"]).matches(page.listings[1])
    assert not Search().matches(page.listings[1])


def test_rentola_empty_search_is_distinct_from_missing_schema():
    body = (FIXTURES / "rentola_empty.html").read_text(encoding="utf-8")
    page = parse_html("rentola", search_url("rentola", "Wetzikon ZH"), body)
    assert page.listings == [] and page.total == 0
    with pytest.raises(SourceError):
        parse_html("rentola", search_url("rentola", "Uster"), "<p>50 results</p>")
    with pytest.raises(SourceError):
        parse_html("rentola", search_url("rentola", "Uster"), "<p>0 results</p>")


def test_rentola_geography_url_and_dynamic_portal_count():
    assert (
        search_url("rentola", "Wetzikon (ZH)")
        == "https://rentola.ch/en/for-rent/wetzikon-zh"
    )
    assert search_url("rentola", "Uster") == "https://rentola.ch/en/for-rent/uster"
    _text, keyboard = settings_screen(Search())
    assert f"из {len(SOURCES)}" in str(keyboard)


def test_rentola_unknown_currency_country_and_room_type_do_not_match():
    body = (FIXTURES / "rentola.html").read_text(encoding="utf-8")
    # Reject incompatible schema rather than announcing an empty search.
    for original, replacement in [
        ('"priceCurrency": "CHF"', '"priceCurrency": "EUR"'),
        ('"addressCountry": "CH"', '"addressCountry": "DE"'),
    ]:
        with pytest.raises(SourceError):
            parse_html(
                "rentola",
                search_url("rentola", "Uster"),
                body.replace(original, replacement),
            )
    room_page = parse_html(
        "rentola",
        search_url("rentola", "Uster"),
        body.replace('"@type": "Apartment"', '"@type": "Room"'),
    )
    assert all(x.category == "other" for x in room_page.listings)


def test_new_source_addition_preserves_filters_queue_and_manual_disable(tmp_path):
    store = Store(tmp_path / "test.db")
    for uid in [1, 2]:
        store.ensure_user(uid)
    search = Search(cities=["Uster"], max_price=1350, paused=True, sources=["flatfox"])
    store.save_search(1, search)
    item = Listing(
        "flatfox",
        "https://flatfox.ch/en/flat/test/1/",
        "Test",
        "Uster",
        price=1200,
        rooms=2,
    )
    store.query("q", "flatfox", "Uster")
    store.query_ok("q", [item], 180, False)
    store.record_delivery(1, item)
    store.add_source_once(1, "rentola")
    actual = store.search(1)
    assert actual.sources == ["flatfox", "rentola"]
    assert actual.paused and actual.max_price == 1350 and actual.cities == ["Uster"]
    assert len(store.pending()) == 1
    actual.sources.remove("rentola")
    store.save_search(1, actual)
    store.add_source_once(1, "rentola")
    assert store.search(1).sources == ["flatfox"]
    disabled = store.search(2)
    disabled.sources = []
    store.save_search(2, disabled)
    store.add_source_once(2, "rentola")
    assert store.search(2).sources == []
    store.close()


def test_rentola_pagination_uses_shared_bounded_collector():
    body = (FIXTURES / "rentola.html").read_text(encoding="utf-8")
    page1 = parse_html("rentola", search_url("rentola", "Uster"), body)
    page2 = parse_html("rentola", page1.next_url, body.replace("page=2", "page=3"))
    fetcher = type(
        "FakeFetcher",
        (),
        {"page": AsyncMock(side_effect=[page1, page2, page2, page2, page2])},
    )()
    result = asyncio.run(
        collect(fetcher, "rentola", "Uster", search_url("rentola", "Uster"))
    )
    assert result.partial
    assert (
        len(result.listings) == 2
    )  # duplicated mobile/desktop or paginated entries are merged
    assert fetcher.page.await_count <= 5


def test_rentola_shares_queries_between_recipients(tmp_path):
    store = Store(tmp_path / "test.db")
    for uid in [1, 2]:
        store.ensure_user(uid)
        store.set_user(uid, active=True)
        store.save_search(uid, Search(cities=["Uster"], sources=["rentola"]))
    grouped = list(plans(store).values())
    assert len(grouped) == 1 and grouped[0]["users"] == [1, 2]
    store.close()


def test_rentola_requests_the_language_of_its_canonical_urls(tmp_path):
    store = Store(tmp_path / "test.db")
    fetcher = Fetcher(store, None)
    fetcher.robots = AsyncMock()
    fetcher.raw = AsyncMock(
        return_value=(200, (FIXTURES / "rentola.html").read_text(encoding="utf-8"), {})
    )
    url = search_url("rentola", "Uster")
    page = asyncio.run(
        fetcher.page("rentola", url, lambda text: parse_html("rentola", url, text))
    )
    assert page.listings
    assert (
        fetcher.raw.call_args.kwargs["headers"]["Accept-Language"] == "en-CH,en;q=0.9"
    )
    store.close()
