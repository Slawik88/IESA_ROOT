#!/usr/bin/env python3
"""Release boundary: current systems stay usable; retired faucets fail closed."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
read = lambda path: (ROOT / path).read_text(encoding="utf-8")

main = read("FastAPI/main.py")
bot = read("bot/handlers/__init__.py")
scheduler = read("bot/__main__.py")
database_init = read("bot/core/database.py")
gacha = read("FastAPI/routers/gacha.py")
shop = read("FastAPI/routers/shop.py")
deals = read("FastAPI/routers/daily_deal.py")
auction = read("FastAPI/routers/auction.py")
family = read("FastAPI/routers/marriage.py")
family_repo = read("infrastructure/repositories/marriages.py")
shadow_archive_repo = read("infrastructure/repositories/shadow_merchant.py")
zoo = read("FastAPI/routers/zoo.py")
cosmetics = read("FastAPI/routers/cosmetics.py")
barracks = read("FastAPI/routers/barracks.py")
bp = read("FastAPI/routers/battle_pass.py")
registry = read("core/registry.py")
ai = read("services/ai_assistant.py")
web_redirect = read("bot/handlers/web_redirect.py")
common = read("bot/handlers/common.py")

# The new game and the features the owner explicitly kept are registered.
for marker in (
    "reconstruction_router.router", "promocodes.router", "marriage.router",
    "clans.router", "payments.router", "cosmetics.router",
):
    assert marker in main
for marker in ("promo_router", "marriage_router", "dark_mora_router", "unknown_cmd_router"):
    assert marker in bot

# Old cellular combat cannot return through either public router registry.
assert "battle.router" not in main
assert "battle_router" not in bot
assert "expeditions_router" not in bot

# Random/paid-power and obsolete economy entry points fail closed.
for source, markers in (
    (gacha, ("raise HTTPException(410", "Случайные крутки закрыты")),
    (shop, ('"active": False', "Старый каталог закрыт")),
    (deals, ('"active": False', "Старая акция закрыта")),
    (auction, ('"market_open": False', "Новые ставки закрыты")),
    (family, ("Семейный кошелёк заморожен",)),
    (zoo, ("Старые походы больше не запускаются", "Старая усталость закрыта")),
    (cosmetics, ("Случайное открытие закрыто", "Старый крафт закрыт")),
    (barracks, ("Старая Казарма закрыта",)),
    (bp, ("Покупка уровней закрыта",)),
):
    for marker in markers:
        assert marker in source, marker

# VIP is service/cosmetic only; owned cosmetics do not expire with it.
assert registry.count('"extra_slots": 0') >= 5
assert registry.count('"weekly": ()') >= 5
assert '"gift": {"mora": 0, "diamonds": 0, "items": ()}' in registry
assert "propose_expedition" not in ai
assert "get_duel_cooldowns" not in ai

# Retired automatic faucets are not started by the bot process.
assert "create_task(chest_spawn_task" not in scheduler
assert "create_task(shadow_merchant_task" not in scheduler

# Production runs the embedded FastAPI app with lifespan disabled.  The bot
# startup therefore owns schema-only ensures for every current v3 table, while
# balance migrations must remain an explicit, reviewed release operation.
for marker in (
    "_ensure_reconstruction", "_ensure_gameplay_events", "_ensure_economy_shadow",
    "_ensure_reconstruction_units", "_ensure_companions_v3", "_ensure_alliance_v3",
):
    assert marker in database_init
for forbidden in (
    "migrate_all_to_gates2 as", "migrate_clan_coins_to_shards as",
    "compensate_pets_migration as",
):
    assert forbidden not in database_init

# Mini-app CTAs stay inside Telegram: WebAppInfo in private chat and the
# registered t.me startapp deep link where Telegram forbids web_app buttons.
assert 'web_app=types.WebAppInfo' in web_redirect
assert 'https://t.me/{_BOT}?startapp={section}' in web_redirect
assert 'https://t.me/{_bot_username}?startapp=home' in common

# Social keepsakes stay useful but spend through the same idempotent ledger as
# every other current purchase; they never recreate the removed XP buff path.
assert 'reason_code="partner_gift"' in family_repo
assert "apply_balance_change(" in family_repo
assert "player_buffs" not in family_repo
assert 'alias="Idempotency-Key"' in family
assert 'reason_code="shadow_relic"' in shadow_archive_repo
assert "UPDATE users SET user_balance_dark_mora" not in shadow_archive_repo

print("first release boundary: OK")
