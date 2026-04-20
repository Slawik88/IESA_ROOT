"""
handlers/router.py — единая точка сборки всех Telegram-роутеров.

Вместо 31 строки dp.include_router() в main.py — один импорт:
    from handlers.router import main_router
    dp.include_router(main_router)

ПОРЯДОК ВАЖЕН: более специфичные роутеры — сверху, catch-all (extras) — последним.
"""

from aiogram import Router

# ─── Импорт всех хэндлеров ────────────────────────────────────────────────────
from handlers import (
    owner,
    admin,
    moderator,
    helper,
    notes,
    auto_mod,
    reputation,
    fun,
    quests,
    pets,
    wallet,
    economy,
    casino,
    expeditions,
    gacha,
    bank,
    espionage,
    diligence,
    food,
    checkin,
    boss,
    dev_panel,
    shop,
    stars,
    gifts,
    tax_event,
    weather,
    user,
    extras,
)
from handlers import auction as auction_handler
from handlers import join_flow
from handlers import chat_tracker
from handlers import dm_roles

# ─── Главный роутер ───────────────────────────────────────────────────────────
main_router = Router(name="main")

# Порядок: от специфичных к общим.
# stars.payment_router регистрируется ОТДЕЛЬНО без MainChatOnly-фильтра —
# он обрабатывает pre_checkout_query и successful_payment глобально.
main_router.include_router(owner.router)
main_router.include_router(admin.router)
main_router.include_router(moderator.router)
main_router.include_router(helper.router)
main_router.include_router(notes.router)
main_router.include_router(auto_mod.router)
main_router.include_router(reputation.router)    # репутация/XP/bio — до catch-all
main_router.include_router(fun.router)            # весёлые команды
main_router.include_router(quests.router)         # ежедневные задания
main_router.include_router(pets.router)           # система питомцев
main_router.include_router(wallet.router)         # переводы и займы Моры
main_router.include_router(economy.router)        # экономика (Мора, балансы)
main_router.include_router(casino.router)         # казино (монетка, кубик, лотерея)
main_router.include_router(expeditions.router)    # экспедиции питомцев
main_router.include_router(gacha.router)          # молитвы (гача)
main_router.include_router(bank.router)           # банк вкладов
main_router.include_router(espionage.router)      # шпионаж + облигации
main_router.include_router(diligence.router)      # ивент «Дилижанс»
main_router.include_router(food.router)           # магазин еды для питомцев
main_router.include_router(checkin.router)        # ежедневный чекин
main_router.include_router(boss.router)           # битва с боссом
main_router.include_router(auction_handler.router)  # аукцион
main_router.include_router(dev_panel.router)      # панель разработчика
main_router.include_router(shop.router)           # магазин
main_router.include_router(stars.router)          # Telegram Stars (кристаллы)
main_router.include_router(join_flow.router)      # вступление по тегам (до dm_roles)
main_router.include_router(chat_tracker.router)   # реактивный трекинг чатов
main_router.include_router(gifts.router)          # подарки партнёру
main_router.include_router(tax_event.router)      # налоговая инспекция
main_router.include_router(weather.router)        # погода
main_router.include_router(user.router)
main_router.include_router(dm_roles.router)       # DM-онбординг ролей
main_router.include_router(extras.router)         # ← catch-all ПОСЛЕДНИМ

# payment_router регистрируется в main.py отдельно (нет MainChatOnly фильтра)
payment_router = stars.payment_router

__all__ = ["main_router", "payment_router"]
