"""Contract test: chat volume and referrals cannot create power or currency."""
import ast
import asyncio
import importlib.util
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent


def source(path: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    if path.endswith(".py"):
        ast.parse(text, filename=path)
    return text


async def check_referral_noop() -> None:
    spec = importlib.util.spec_from_file_location("referral_contract", ROOT / "services/referral.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    class ExplodingDB:
        def __getattribute__(self, name):
            if name.startswith("__"):
                return object.__getattribute__(self, name)
            raise AssertionError(f"retired referral touched db.{name}")

    assert await module.register_referral(ExplodingDB(), 10, 20) is False


async def main() -> None:
    leveling = source("services/leveling.py")
    chat = source("infrastructure/repositories/chat.py")
    middleware = source("bot/middlewares/db.py")
    referral = source("services/referral.py")
    payments = source("bot/handlers/payments.py")
    web_inventory = source("FastAPI/routers/inventory.py")
    bot_inventory = source("bot/handlers/inventory.py")
    profile_ui = source("FastAPI/static/app.02.js")

    for marker in ("add_balance", "add_account_xp", "set_account_level", "get_species_bonus"):
        assert marker not in leveling, f"message progression still calls {marker}"
    assert "user_xp + 10" not in chat
    assert "VALUES ($1, $2, 1, 1, 1, 1, 10" not in chat
    assert "messages_in_chat_today" not in middleware
    assert "messages_total_global" not in middleware
    assert "_checkLevelUp(lvl);" not in profile_ui
    assert "Уровень наследия" in profile_ui

    for marker in ("add_balance", "grant_vip_days", "UPDATE users SET referred_by"):
        assert marker not in referral, f"referral still grants or binds through {marker}"
    assert "REFERRAL_SIGNUP" not in payments
    assert "оба в плюсе" not in payments.lower()

    assert "UPDATE inventory SET quantity = quantity - 1" not in web_inventory.split("@router.get(\"/buffs\")", 1)[0]
    assert "UPDATE inventory SET quantity = quantity - 1 WHERE user_id = ? AND item_id = 'study_notes'" not in bot_inventory
    assert "архивный предмет" in web_inventory.lower()

    registry = source("core/registry.py")
    assert '"item_id": "study_notes"' not in registry

    promo = source("services/promocodes.py")
    assert "activate_promocode" in promo and 'source="promocode"' in promo

    await check_referral_noop()
    print("OK: messages are stats-only; referrals are inert; promos remain enabled")


asyncio.run(main())
