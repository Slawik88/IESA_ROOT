from aiogram import Router
from .common import router as common_router, fallback_router, unknown_cmd_router
from .economy import router as eco_router
from .inventory import router as inventory_router
from .profile import router as profile_router
from .admin import router as admin_router
from .marriage import router as marriage_router
from .stats import router as stats_router
from .moderation import router as mod_router
from .events import router as events_router
from .routing import router as routing_router
from .purge import router as purge_router
from .shop import router as shop_router
from .zoo import router as zoo_router
from .expeditions import router as expeditions_router
from .streak import router as streak_router
from .pet_showcase import router as pet_showcase_router
from .gacha import router as gacha_router
from .daily_deal import router as daily_deal_router
from .identity import router as identity_router
from .nicknames import router as nicknames_router
from .wallet_history import router as wallet_history_router
from .warps import router as warps_router
from .achievements import router as achievements_router
from .duel import router as duel_router
from .auction import router as auction_router
from .exchange import router as exchange_router
from .games import router as games_router
from .chat_settings import router as chat_settings_router
from .quests import router as quests_router
from .blacklist import router as blacklist_router
from .promocodes import router as promo_router
from .dark_mora import router as dark_mora_router
from .themes import router as themes_router
from . import dev


main_router = Router(name="main_router")

main_router.include_routers(
    common_router,
    admin_router,      # до eco: "дать ранг" перехватывается раньше чем "дать"
    eco_router,
    inventory_router,
    identity_router,       # я/профиль/кто/анкета — до profile_router чтобы перехватить "профиль"
    profile_router,        # только "кто я" + инфо/досье
    stats_router,
    mod_router,        # до marriage: "снять варн/мут/защиту" перехватывается раньше чем "снять"
    marriage_router,
    events_router,
    routing_router,
    purge_router,
    shop_router,
    zoo_router,
    expeditions_router,
    streak_router,
    pet_showcase_router,
    gacha_router,
    daily_deal_router,
    nicknames_router,      # бот мой ник
    wallet_history_router, # история кошелька
    warps_router,          # варп-команды
    achievements_router,   # достижения
    duel_router,           # B12 PvP дуэли
    auction_router,        # B13 аукцион
    exchange_router,       # B15 конвертер
    games_router,          # B16 мини-игры
    chat_settings_router,  # B19 настройки чата
    quests_router,         # B20 ежедневные квесты
    blacklist_router,      # C1-A чёрный список чата
    promo_router,          # промокоды
    dark_mora_router,      # Тёмная Мора: контрабанда, ритуал
    themes_router,         # темы профиля
    dev.router,
    unknown_cmd_router,    # B6: подсказки опечаток — перед fallback, после всех команд
    fallback_router,       # должен быть последним — ловит неверный синтаксис
)