"""Bounded HTTP, conditional requests, robots rules and shared host backoff."""

import asyncio
import json
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import aiohttp

from .models import safe_url
from .sources import Page, SourceError

USER_AGENT = (
    "HataNatata/1.0 (private rental notifications; low-frequency public search)"
)


class FetchError(SourceError):
    def __init__(self, message, delay=300):
        super().__init__(message)
        self.delay = delay


def retry_after(value, default=300):
    try:
        return min(86400, max(120, int(value)))
    except (TypeError, ValueError):
        try:
            dt = parsedate_to_datetime(value)
            return min(86400, max(120, int((dt - datetime.now(UTC)).total_seconds())))
        except (TypeError, ValueError, OverflowError):
            return default


def robots_allowed(text, url):
    """Longest matching Allow/Disallow rule, including * and terminal $."""
    groups, agents, rules = [], [], []
    for line in text.splitlines() + ["User-agent: __end__"]:
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        name, value = (part.strip() for part in line.split(":", 1))
        name = name.lower()
        if name == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif name in {"allow", "disallow"} and value:
            rules.append((name, value))
    specific = [
        r for a, r in groups if any(x != "*" and x in USER_AGENT.lower() for x in a)
    ]
    selected = specific or [r for a, r in groups if "*" in a]
    path = urlsplit(url).path or "/"
    if urlsplit(url).query:
        path += "?" + urlsplit(url).query
    matched = []
    for group in selected:
        for name, pattern in group:
            regex = (
                "^"
                + re.escape(pattern.rstrip("$")).replace(r"\*", ".*")
                + ("$" if pattern.endswith("$") else "")
            )
            if re.search(regex, path):
                matched.append(
                    (len(pattern.replace("*", "").rstrip("$")), name == "allow")
                )
    return max(matched, default=(0, True))[1]


class Fetcher:
    def __init__(self, store, session):
        self.store, self.session = store, session
        self.host_next = {}

    async def raw(self, url, *, headers=None, limit=5_000_000):
        host = urlsplit(url).hostname
        blocked = self.store.get("host_block:" + host, 0)
        if blocked > time.time():
            raise FetchError(
                "Сайт временно недоступен; действует пауза повторных запросов",
                int(blocked - time.time()),
            )
        await asyncio.sleep(max(0, self.host_next.get(host, 0) - time.monotonic()))
        self.host_next[host] = time.monotonic() + 2
        try:
            async with self.session.get(
                url,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=25, connect=10),
            ) as response:
                if response.status in {403, 429}:
                    delay = retry_after(
                        response.headers.get("Retry-After"),
                        1800 if response.status == 403 else 300,
                    )
                    self.store.put("host_block:" + host, time.time() + delay)
                    raise FetchError(
                        "Сайт отклонил автоматический запрос (HTTP "
                        + str(response.status)
                        + ")",
                        delay,
                    )
                if response.status == 304:
                    return 304, "", response.headers
                if response.status != 200:
                    raise FetchError(
                        "Источник вернул HTTP " + str(response.status), 600
                    )
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > limit:
                        raise FetchError(
                            "Ответ источника превысил безопасный размер", 1800
                        )
                    chunks.append(chunk)
                return (
                    200,
                    b"".join(chunks).decode("utf-8", errors="replace"),
                    response.headers,
                )
        except (TimeoutError, aiohttp.ClientError) as exc:
            raise FetchError("Ошибка соединения с источником", 300) from exc

    async def robots(self, source, url):
        host = urlsplit(url).hostname
        cached = self.store.get("robots:" + host)
        if not cached or cached["expires"] < time.time():
            robots_url = "https://" + host + "/robots.txt"
            try:
                _, body, _ = await self.raw(robots_url, limit=100000)
            except FetchError as exc:
                if "HTTP 404" in str(exc):
                    body = ""
                else:
                    raise FetchError(
                        "Не удалось проверить правила автоматического доступа сайта",
                        exc.delay,
                    ) from exc
            cached = {"text": body, "expires": time.time() + 86400}
            self.store.put("robots:" + host, cached)
        if not robots_allowed(cached["text"], url):
            raise FetchError("Этот адрес запрещён правилами robots.txt сайта", 86400)

    async def page(self, source, url, parser):
        safe_url(url, source)
        await self.robots(source, url)
        cached = self.store.cache(url)
        headers = {}
        if source == "rentola":
            # Its locale middleware redirects /en pages when given the shared German preference.
            headers["Accept-Language"] = "en-CH,en;q=0.9"
        if cached and cached["etag"]:
            headers["If-None-Match"] = cached["etag"]
        if cached and cached["modified"]:
            headers["If-Modified-Since"] = cached["modified"]
        status, body, meta = await self.raw(url, headers=headers)
        if status == 304 and cached:
            return Page.load(json.loads(cached["data"]))
        if status == 304:
            raise FetchError("Источник вернул пустой ответ без сохранённой копии")
        page = await asyncio.to_thread(parser, body)
        self.store.cache_page(url, meta.get("ETag"), meta.get("Last-Modified"), page)
        return page

    async def coordinates(self, city):
        from urllib.parse import urlencode

        cached = self.store.get("geo:" + city)
        if cached:
            return cached
        url = "https://api3.geo.admin.ch/rest/services/api/SearchServer?" + urlencode(
            {"searchText": city, "type": "locations", "limit": 5}
        )
        _, body, _ = await self.raw(url, limit=100000)
        rows = json.loads(body).get("results", [])
        attrs = next(
            (r["attrs"] for r in rows if r["attrs"].get("origin") == "gg25"), None
        )
        if not attrs:
            raise FetchError(
                "Не найден город для карты Flatfox; уточните название и кантон", 3600
            )
        coords = [float(attrs["lat"]), float(attrs["lon"])]
        if not 45.7 < coords[0] < 47.9 or not 5.8 < coords[1] < 10.6:
            raise FetchError("Город за пределами Швейцарии", 3600)
        self.store.put("geo:" + city, coords)
        return coords


def session():
    return aiohttp.ClientSession(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de-CH,de;q=0.9"},
        connector=aiohttp.TCPConnector(limit=2, ttl_dns_cache=300),
    )
