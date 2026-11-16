"""One cooperative scanner shared by all authorized personal searches."""

import asyncio
import hashlib
import json
import logging
import random
import time
from urllib.parse import urlencode

from .models import Search
from .network import FetchError
from .sources import Page, SourceError, parse_flatfox, parse_html, search_url

log = logging.getLogger(__name__)
MAX_PAGES = 5


def query_key(source, city, url):
    return hashlib.sha256((source + "|" + city + "|" + url).encode()).hexdigest()


def plans(store):
    result = {}
    for user in store.users():
        search = Search(**json.loads(user["config"]))
        if search.paused:
            continue
        for source in search.sources:
            cities = search.cities[:1] if source in search.urls else search.cities
            for city in cities:
                url = search.urls.get(source) or search_url(source, city)
                key = query_key(source, city, url)
                if key not in result:
                    result[key] = {
                        "source": source,
                        "city": city,
                        "url": url,
                        "users": [],
                        "interval": search.interval,
                    }
                result[key]["users"].append(user["id"])
                result[key]["interval"] = min(result[key]["interval"], search.interval)
    return result


async def collect(fetcher, source, city, url):
    if source == "flatfox":
        latitude, longitude = await fetcher.coordinates(city)
        pin_url = "https://flatfox.ch/api/v1/pin/?" + urlencode(
            {
                "east": round(longitude + 0.075, 6),
                "west": round(longitude - 0.075, 6),
                "north": round(latitude + 0.04, 6),
                "south": round(latitude - 0.04, 6),
                "offer_type": "RENT",
                "max_count": 100,
            }
        )
        await fetcher.robots(source, pin_url)
        _, body, _ = await fetcher.raw(pin_url, limit=1000000)
        pins = json.loads(body)
        if not isinstance(pins, list) or any(
            not isinstance(p, dict) or "pk" not in p for p in pins
        ):
            raise SourceError("Flatfox изменил формат карты")
        ids = sorted({int(p["pk"]) for p in pins}, reverse=True)[:100]
        if not ids:
            return Page([])
        # The generic public-listing endpoint ignores map filters. Resolve explicit IDs from /pin/.
        detail_url = "https://flatfox.ch/api/v1/public-listing/?" + urlencode(
            [("limit", 0)] + [("pk", pk) for pk in ids]
        )
        page = await fetcher.page(source, detail_url, parse_flatfox)
        page.partial = len(pins) >= 100
        return page
    found, seen, partial, total = {}, set(), False, 0
    for _ in range(MAX_PAGES):
        if not url or url in seen:
            break
        seen.add(url)
        current_url = url
        page = await fetcher.page(
            source,
            url,
            lambda body, current_url=current_url: parse_html(source, current_url, body),
        )
        for listing in page.listings:
            found[listing.key] = listing
        partial = partial or page.partial
        total = max(total, page.total or 0)
        url = page.next_url
    return Page(
        list(found.values()), partial=partial or bool(url) or total > len(found)
    )


async def scan_once(store, fetcher):
    for key, plan in plans(store).items():
        row = store.query(key, plan["source"], plan["city"])
        if row["next_run"] > time.time():
            continue
        try:
            page = await collect(fetcher, plan["source"], plan["city"], plan["url"])
            if page.listings and not any(
                x.city and x.price is not None and x.rooms is not None
                for x in page.listings
            ):
                raise SourceError(
                    "Объявления найдены, но цена, комнаты или город не распознаны"
                )
            store.query_ok(
                key,
                page.listings,
                plan["interval"] + random.uniform(0, 15),
                page.partial,
            )
            for user_id in plan["users"]:
                user = store.user(user_id)
                search = store.search(user_id)
                if not user["active"] or search.paused:
                    continue
                marker = "baseline:" + str(user_id) + ":" + key
                baseline = not store.get(marker, False)
                for listing in page.listings:
                    if search.matches(listing):
                        store.record_delivery(user_id, listing, baseline=baseline)
                store.put(marker, True)
            log.info(
                "scan source=%s city=%s count=%s partial=%s",
                plan["source"],
                plan["city"],
                len(page.listings),
                page.partial,
            )
        except (FetchError, SourceError, ValueError, KeyError, TypeError) as exc:
            delay = max(
                getattr(exc, "delay", 300),
                min(3600, 120 * 2 ** min(row["failures"], 5)),
            )
            error = (
                str(exc)
                if isinstance(exc, SourceError)
                else "Не удалось распознать данные источника"
            )
            store.query_error(key, error, delay)
            log.warning(
                "scan source=%s error=%s retry_seconds=%s", plan["source"], error, delay
            )
        await asyncio.sleep(1)


async def run_scanner(store, fetcher):
    last_prune = 0
    while True:
        await scan_once(store, fetcher)
        if time.monotonic() - last_prune > 3600:
            store.prune()
            last_prune = time.monotonic()
        await asyncio.sleep(5)
