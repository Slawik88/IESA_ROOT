"""Contract test: legacy streak is read-only and never mints currency."""
import asyncio
import importlib.util
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# The repository contract tests run without the optional Telegram dependency.
aiogram = types.ModuleType("aiogram")
aiogram_types = types.ModuleType("aiogram.types")
aiogram_types.TelegramObject = object
aiogram.types = aiogram_types
sys.modules.setdefault("aiogram", aiogram)
sys.modules.setdefault("aiogram.types", aiogram_types)

spec = importlib.util.spec_from_file_location(
    "streak_mw_contract", pathlib.Path("bot/middlewares/streak_mw.py")
)
streak_mw = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(streak_mw)


class ExplodingDB:
    """Any database access from middleware is an economic side effect regression."""

    def __getattribute__(self, name):
        if name.startswith("__"):
            return object.__getattribute__(self, name)
        raise AssertionError(f"streak middleware touched db.{name}")


async def main():
    calls = []

    async def handler(event, data):
        calls.append((event, data))
        return "handled"

    event = object()
    data = {"db": ExplodingDB()}
    result = await streak_mw.streak_middleware(handler, event, data)

    assert result == "handled"
    assert calls == [(event, data)], "middleware must pass every update exactly once"

    middleware_source = pathlib.Path("bot/middlewares/streak_mw.py").read_text(encoding="utf-8")
    handler_source = pathlib.Path("bot/handlers/streak.py").read_text(encoding="utf-8")
    forbidden = ("add_balance", "spend_balance", "spin_token", "UPDATE users")
    for marker in forbidden:
        assert marker not in middleware_source, f"middleware contains retired writer: {marker}"
        assert marker not in handler_source, f"handler contains retired writer: {marker}"

    ui_source = pathlib.Path("FastAPI/static/app.02.js").read_text(encoding="utf-8")
    for stale_copy in ("Следующая награда", "бот стрик восстановить", "Алмазы из стрика"):
        assert stale_copy not in ui_source, f"UI still promises retired streak reward: {stale_copy}"
    assert "число сообщений не усиливает награду" in ui_source
    assert "сохранённый рекорд старой системы" in ui_source

    print("OK: legacy streak is read-only; messages cannot mint currency or sell recovery")


asyncio.run(main())
