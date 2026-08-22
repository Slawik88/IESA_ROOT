#!/usr/bin/env python3
"""Keep promocodes useful without allowing paid or retired currency faucets."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if importlib.util.find_spec("aiosqlite") is None:
    sys.modules["aiosqlite"] = types.SimpleNamespace(Connection=object)

from infrastructure.repositories.promocodes import create_promocode  # noqa: E402


class FakeDB:
    def __init__(self):
        self.calls = []
        self.commits = 0

    async def execute(self, sql, args=()):
        self.calls.append((" ".join(sql.split()), tuple(args)))

    async def commit(self):
        self.commits += 1


async def main():
    db = FakeDB()
    ok = await create_promocode(
        db,
        "WELCOME",
        "Стартовый набор",
        500,
        2,
        0,
        0,
        '{"food_apple":2}',
        100,
        None,
        None,
        7,
    )
    assert ok and db.commits == 1 and len(db.calls) == 1
    assert db.calls[0][1][2:6] == (500, 2, 0, 0)

    for dark_mora, zarniki in ((1, 0), (0, 1), (4, 9)):
        before = len(db.calls)
        try:
            await create_promocode(
                db, "BLOCKED", "", 0, 0, dark_mora, zarniki, "{}", 0,
                None, None, 7,
            )
        except ValueError as exc:
            assert "Мору, Алмазы или предметы" in str(exc)
        else:
            raise AssertionError("A promocode minted a retired or paid currency")
        assert len(db.calls) == before

    web = (ROOT / "FastAPI/static/app.08.js").read_text(encoding="utf-8")
    assert 'id="dev-promo-dark"' not in web
    assert 'id="dev-promo-zar"' not in web
    assert "Промокод выдаёт Мору, Алмазы и предметы" in web

    bot = (ROOT / "bot/handlers/promocodes.py").read_text(encoding="utf-8")
    assert "await state.set_state(PromoCreate.items)" in bot
    assert "Шаг 5/10 — <b>Предметы" in bot
    assert "Шаг 12/12" not in bot
    print("promocode_v3: Mora+Diamonds+items preserved; paid/retired faucets blocked  OK")


if __name__ == "__main__":
    asyncio.run(main())
