"""Файлы интерфейса: кэш только у версионированных адресов, ссылка-приглашение и ближайшие уборки."""
import re
from datetime import date, timedelta
from types import SimpleNamespace

import httpx
import pytest
from aiogram.exceptions import TelegramNetworkError

from core import config
from services import cleaning, households
from test_web import TOKEN, headers
from web.app import create_app


class FakeBot:
    def __init__(self, username="Domovskii_bot", broken=False):
        self.username, self.broken = username, broken

    async def me(self):
        if self.broken:
            raise TelegramNetworkError(method=None, message="offline")
        return SimpleNamespace(username=self.username)


async def make_client(monkeypatch, bot=None):
    monkeypatch.setattr(config, "BOT_TOKEN", TOKEN)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(bot=bot)), base_url="http://test")


@pytest.fixture
async def house(database):
    return await households.create_house(100, "Хозяин", "Закрытый дом")


async def test_page_is_never_cached_and_points_to_versioned_files(monkeypatch, database):
    async with await make_client(monkeypatch) as client:
        page = await client.get("/")
        assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
        assert "__V__" not in page.text
        version = re.search(r"/v/([0-9a-f]{12})/app\.css", page.text)[1]
        asset = await client.get(f"/v/{version}/js/main.js")
        assert asset.status_code == 200
        assert "immutable" in asset.headers["cache-control"] and "private" in asset.headers["cache-control"]
        assert asset.headers["content-type"].startswith("text/javascript")
        font = await client.get(f"/v/{version}/fonts/onest.woff2")
        assert font.status_code == 200 and font.headers["content-type"] == "font/woff2"


@pytest.mark.parametrize("path", [
    "index.html", "fonts/OFL.txt", "fonts/README.md", "../core/config.py", "%2e%2e/core/config.py", "js/missing.js",
])
async def test_only_interface_files_are_served(monkeypatch, database, path):
    async with await make_client(monkeypatch) as client:
        assert (await client.get(f"/v/x/{path}")).status_code == 404


async def test_invite_link_points_to_the_bot_and_follows_rotation(monkeypatch, house):
    async with await make_client(monkeypatch, FakeBot()) as client:
        current = (await client.get(f"/api/houses/{house}/invite", headers=headers())).json()
        assert current["link"] == f"https://t.me/Domovskii_bot?start=join_{current['invite_token']}"
        rotated = (await client.post(f"/api/houses/{house}/invite/rotate", headers=headers())).json()
        assert rotated["invite_token"] != current["invite_token"]
        assert rotated["link"].endswith(f"join_{rotated['invite_token']}")


@pytest.mark.parametrize("bot", [None, FakeBot(broken=True)])
async def test_invite_without_telegram_still_gives_the_code(monkeypatch, house, bot):
    async with await make_client(monkeypatch, bot) as client:
        result = (await client.get(f"/api/houses/{house}/invite", headers=headers())).json()
        assert result["link"] is None and result["invite_token"]


async def test_overview_lists_the_next_cleaning_days_after_today(monkeypatch, house):
    async with await make_client(monkeypatch) as client:
        first = (await client.get(f"/api/houses/{house}", headers=headers())).json()
        today = date.fromisoformat(first["today"])
        assert first["upcoming"] == []
        await cleaning.save_weekday_map(house, {100: (today.weekday() + 1) % 7}, first["today"])
        upcoming = (await client.get(f"/api/houses/{house}", headers=headers())).json()["upcoming"]
        expected = [(today + timedelta(days=1)).isoformat(), (today + timedelta(days=8)).isoformat()]
        assert [row["planned_date"] for row in upcoming] == expected
        assert upcoming[0]["display_name"] == "Хозяин"
        assert all(row["planned_date"] > first["today"] for row in upcoming)
