from aiogram import Router
from .common import router as common_router, fallback_router, unknown_cmd_router
from .payments import router as payments_router
from .release_profile import router as release_profile_router
from .quests_v1 import router as quests_v1_router
from .pets_v1 import router as pets_v1_router
from .admin import router as admin_router
from .marriage import router as marriage_router
from .stats import router as stats_router
from .moderation import router as mod_router
from .global_moderation import router as global_mod_router
from .routing import router as routing_router
from .purge import router as purge_router
from .nicknames import router as nicknames_router
from .wallet_history import router as wallet_history_router
from .warps import router as warps_router
from .games import router as games_router
from .mafia_v1 import router as mafia_v1_router
from .rhythm import router as rhythm_router
from .chat_settings import router as chat_settings_router
from .chat_echo import router as chat_echo_router
from .blacklist import router as blacklist_router
from . import dev

# Release scope: chat keeps moderation, family, identity and approved games.
# All former economy, pets, campaigns, cosmetics and event commands are archived
# server-side and deliberately not registered as public bot routes.


main_router = Router(name="main_router")

main_router.include_routers(
    common_router,
    admin_router,
    payments_router,   # B-Donate-1: покупка ✨ за Stars, /start?buyzarniki
    release_profile_router,
    quests_v1_router,
    pets_v1_router,
    stats_router,
    mod_router,        # до marriage: "снять варн/мут/защиту" перехватывается раньше чем "снять"
    global_mod_router, # B6: глобальная модерация (глоб варн/ограничить/бан, апелляция)
    marriage_router,   # брак @user + просмотр браков чата + семейный банк/подарки (соц, оставлен)
    routing_router,
    purge_router,
    nicknames_router,      # бот мой ник
    wallet_history_router, # god-логи кошелька (dev)
    warps_router,          # варп-команды (соц)
    games_router,          # R7: старое казино снесено, редирект в мини-апп Арена→Игры
    mafia_v1_router,       # утверждённая чатовая групповая игра; отдельное состояние/фазы
    rhythm_router,         # лёгкий общий слой: выбор/прогресс Ритма, бой остаётся в Mini App
    chat_settings_router,  # настройки чата (админ)
    chat_echo_router,      # ручной opt-in чат-ивент без наград и push-спама
    blacklist_router,      # чёрный список чата (админ)
    dev.router,
    unknown_cmd_router,    # B6: подсказки опечаток — перед fallback, после всех команд
    fallback_router,       # должен быть последним — ловит неверный синтаксис
)
