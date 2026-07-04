from aiogram import Router
from .common import router as common_router, fallback_router, unknown_cmd_router
from .economy import router as eco_router
from .payments import router as payments_router
from .profile import router as profile_router
from .admin import router as admin_router
from .marriage import router as marriage_router
from .stats import router as stats_router
from .moderation import router as mod_router
from .global_moderation import router as global_mod_router
from .events import router as events_router
from .routing import router as routing_router
from .purge import router as purge_router
from .expeditions import router as expeditions_router
from .streak import router as streak_router
from .identity import router as identity_router
from .nicknames import router as nicknames_router
from .wallet_history import router as wallet_history_router
from .warps import router as warps_router
from .games import router as games_router
from .chat_settings import router as chat_settings_router
from .blacklist import router as blacklist_router
from .promocodes import router as promo_router
from .dark_mora import router as dark_mora_router
from .events_info import router as events_info_router
from .vip import router as vip_router
from .web_redirect import router as web_redirect_router
from . import dev

# БЛОК19 Часть1 «Web First»: тяжёлые механики вырезаны из чата и переехали в мини-апп.
# Их старые алиасы ловит web_redirect_router (тонкая кнопка-редирект, без мёртвых команд).
# Удалены из чата: shop, daily_deal, gacha, auction, themes, craft, relics, exchange,
#   duel, battle_pass, quests, inventory, achievements, pet_showcase, zoo, notifications, clans.
# Оставлены: лёгкие/соц (поход/стрик/ник/варпы/брак/контрабанда/промо/вип/я/профиль/топ),
#   мини-игры (нет веб-UI), god-логи (dev), вся админка. XP/прогресс/выдача наград работают
#   в бэке через increment_metric/services — это НЕ чат-роутеры.


main_router = Router(name="main_router")

main_router.include_routers(
    common_router,
    admin_router,      # до eco: "дать ранг" перехватывается раньше чем "дать"
    eco_router,
    payments_router,   # B-Donate-1: покупка ✨ за Stars, /start?buyzarniki
    identity_router,       # я/профиль/кто/анкета — до profile_router чтобы перехватить "профиль"
    profile_router,        # только "кто я" + инфо/досье
    stats_router,
    mod_router,        # до marriage: "снять варн/мут/защиту" перехватывается раньше чем "снять"
    global_mod_router, # B6: глобальная модерация (глоб варн/ограничить/бан, апелляция)
    marriage_router,   # брак @user + просмотр браков чата + семейный банк/подарки (соц, оставлен)
    events_router,
    routing_router,
    purge_router,
    expeditions_router,    # бот поход (оставлен)
    streak_router,
    nicknames_router,      # бот мой ник
    wallet_history_router, # god-логи кошелька (dev)
    warps_router,          # варп-команды (соц)
    games_router,          # R7: старое казино снесено, редирект в мини-апп Арена→Игры
    chat_settings_router,  # настройки чата (админ)
    blacklist_router,      # чёрный список чата (админ)
    promo_router,          # промокоды (лёгкий ввод)
    dark_mora_router,      # Тёмная Мора: контрабанда, ритуал (чат-ивенты, оставлены)
    events_info_router,    # бот ивент: расписание + dev force-команды
    vip_router,            # B2: VIP-подписка (Stars)
    web_redirect_router,   # БЛОК19: редиректы вырезанных тяжёлых команд → мини-апп
    dev.router,
    unknown_cmd_router,    # B6: подсказки опечаток — перед fallback, после всех команд
    fallback_router,       # должен быть последним — ловит неверный синтаксис
)
