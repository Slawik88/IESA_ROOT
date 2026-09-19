"""Contract test: chat volume and referrals cannot create power or currency."""
import ast
import asyncio
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent


def source(path: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    if path.endswith(".py"):
        ast.parse(text, filename=path)
    return text


async def main() -> None:
    leveling = source("services/leveling.py")
    chat = source("infrastructure/repositories/chat.py")
    middleware = source("bot/middlewares/db.py")
    payments = source("bot/handlers/payments.py")
    web_inventory = source("FastAPI/routers/inventory.py")
    profile_ui = source("FastAPI/static/app.02.js")

    for marker in ("add_balance", "add_account_xp", "set_account_level", "get_species_bonus"):
        assert marker not in leveling, f"message progression still calls {marker}"
    assert "user_xp + 10" not in chat
    assert "VALUES ($1, $2, 1, 1, 1, 1, 10" not in chat
    assert "messages_in_chat_today" not in middleware
    assert "messages_total_global" not in middleware
    assert "_checkLevelUp(lvl);" not in profile_ui
    # The release profile must not silently keep the old message/level loop
    # visible as a progression promise.  It is now an identity + family view.
    assert "Личный профиль" in profile_ui
    assert "Уровень профиля" not in profile_ui
    assert not (ROOT / "bot/handlers/inventory.py").exists()

    assert not (ROOT / "services/referral.py").exists()
    assert "REFERRAL_SIGNUP" not in payments
    assert "оба в плюсе" not in payments.lower()

    assert "UPDATE inventory SET quantity = quantity - 1" not in web_inventory.split("@router.get(\"/buffs\")", 1)[0]
    assert "архивный предмет" in web_inventory.lower()

    registry = source("core/registry.py")
    assert '"item_id": "study_notes"' not in registry

    promo = source("services/promocodes.py")
    assert "activate_promocode" in promo and 'source="promocode"' in promo

    print("OK: messages are stats-only; referrals are inert; promos remain enabled")


asyncio.run(main())
