from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import html

from database.db import (
    get_active_theme, get_active_expedition, get_crystals, get_daily_top,
    get_all_equipped_items, get_equipped_legendary, get_marriage, get_mora,
    get_mora_batch, get_pet, get_prev_weekly_top, get_received_gifts,
    get_shard_stash, get_top_by_messages_in_chat,
    get_user, get_user_badges, get_user_stats,
    get_user_themes, get_weekly_top, get_yesterday_top,
    get_xp_boost_active, add_user_theme, set_active_theme,
    get_weekly_top_reward_history, WEEKLY_TOP_REWARDS,
)
from filters.bot_command import BotCommand
from utils.helpers import not_your_button, resolve_target, user_mention
from utils.ranks import rank_level, rank_name

# Module-level constants to avoid repeated local imports
from config import MINI_APP_URL as _MINI_APP_URL
from config import MINI_APP_TG_URL as _MINI_APP_TG_URL
import logging
_log = logging.getLogger(__name__)

router = Router()

def _fmt_dt(val) -> str:
    """Format datetime/ISO string as dd.mm.yyyy HH:MM or 'нет данных'."""
    if not val:
        return "нет данных"
    try:
        if isinstance(val, datetime):
            return val.strftime("%d.%m.%Y %H:%M")
        dt = datetime.fromisoformat(str(val))
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return "нет данных"

# ─── Часовые пояса ────────────────────────────────────────────────────────────

_TZ_MAP: dict[str, str] = {
    "москва": "Europe/Moscow",       "moscow": "Europe/Moscow",    "мск": "Europe/Moscow",
    "цюрих":  "Europe/Zurich",       "zurich": "Europe/Zurich",    "zürich": "Europe/Zurich",
    "берлин": "Europe/Berlin",       "berlin": "Europe/Berlin",
    "лондон": "Europe/London",       "london": "Europe/London",
    "нью-йорк": "America/New_York",  "ньюйорк": "America/New_York",  "new york": "America/New_York",  "ny": "America/New_York",
    "токио":  "Asia/Tokyo",          "tokyo":  "Asia/Tokyo",
    "дубай":  "Asia/Dubai",          "dubai":  "Asia/Dubai",
    "пекин":  "Asia/Shanghai",       "beijing": "Asia/Shanghai",   "china": "Asia/Shanghai",
    "лос-анджелес": "America/Los_Angeles",  "la": "America/Los_Angeles",
    "париж":  "Europe/Paris",        "paris":  "Europe/Paris",
    "амстердам": "Europe/Amsterdam", "amsterdam": "Europe/Amsterdam",
    "варшава": "Europe/Warsaw",      "warsaw": "Europe/Warsaw",
    "варна":  "Europe/Sofia",       "софия": "Europe/Sofia",       "sofia": "Europe/Sofia",
    "минск":  "Europe/Minsk",        "minsk":  "Europe/Minsk",
    "астана": "Asia/Almaty",         "алматы": "Asia/Almaty",      "almaty": "Asia/Almaty",
    "бангкок": "Asia/Bangkok",       "bangkok": "Asia/Bangkok",
    "джакарта": "Asia/Jakarta",      "jakarta": "Asia/Jakarta",
    "сидней": "Australia/Sydney",    "sydney": "Australia/Sydney",
    "стамбул": "Europe/Istanbul",    "istanbul": "Europe/Istanbul",
    "тегеран": "Asia/Tehran",        "tehran": "Asia/Tehran",
    "сеул":   "Asia/Seoul",          "seoul":  "Asia/Seoul",
    "сингапур": "Asia/Singapore",    "singapore": "Asia/Singapore",
    "мумбаи": "Asia/Kolkata",        "mumbai": "Asia/Kolkata",     "дели": "Asia/Kolkata",
}

_DEFAULT_TZ_LIST = [
    ("🇷🇺 Москва",      "Europe/Moscow"),
    ("🇨🇭 Цюрих",       "Europe/Zurich"),
    ("🇩🇪 Берлин",      "Europe/Berlin"),
    ("🇬🇧 Лондон",      "Europe/London"),
    ("🇺🇸 Нью-Йорк",    "America/New_York"),
    ("🇦🇪 Дубай",       "Asia/Dubai"),
    ("🇯🇵 Токио",       "Asia/Tokyo"),
    ("🇹🇭 Бангкок",     "Asia/Bangkok"),
    ("🇦🇺 Сидней",      "Australia/Sydney"),
]


# ─── Пагинированное Inline-меню помощи ─────────────────────────────────────

# Структура: секция -> подсекции (для глубокой навигации edit_message_text)
# Callback формат: h:<section>:<uid>:<rank_lvl>

def _help_pages() -> dict[str, dict]:
    """Все страницы справочника. Ключ = page_id, значение = {text, buttons, min_rank}."""
    from config import (
        ANON_MSG_PRICE, GACHA_SINGLE_PRICE, GACHA_MULTI_PRICE,
        MINI_APP_URL, MAX_WARNS, PET_MORA_SKIP_PRICE, PET_RENAME_PRICE,
        PET_CHANGE_TYPE_PRICE, QUEST_REROLL_PRICE, SECRET_MSG_PRICE, VIP_PRICE,
        LOTTERY_TICKET_PRICE, COIN_MIN_BET_CHAT, COIN_MAX_BET, DICE_MAX_BET,
        MORA_TRANSFER_MIN, MORA_TRANSFER_MAX, LOAN_MAX_AMOUNT, LOAN_MAX_ACTIVE,
        WALK_MORA_REWARD, WALK_DURATION_HOURS,
    )
    from shared_prices import (
        GACHA_PITY_MAX, BANK_PLANS, CUSTOM_TITLE_PRICE,
        ROULETTE_MIN_BET, ROULETTE_MAX_BET,
    )
    _bp = BANK_PLANS

    return {
        # ─── Главное меню ────────────────────────────────────────────────
        "main": {
            "text": (
                "📖 <b>Предвестник — Справочник</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Добро пожаловать! Выбери раздел 👇\n\n"
                "<i>💡 Команды пишутся текстом — без «/»\n"
                "🎯 Таргет — @юзер или ответ на сообщение\n"
                "🌐 Mini App — кнопка <b>Открыть App</b> возле строки ввода</i>"
            ),
            "buttons": [
                [("💰 Экономика", "economy"), ("📊 Прогрессия", "progression")],
                [("🎲 Игры & Казино", "games"), ("🐾 Питомцы", "pets")],
                [("💍 Социалка", "social"), ("📈 Финансы & Биржа", "finance")],
                [("📅 Ивенты", "events"), ("ℹ️ Полезное", "info")],
                [("🌐 Mini App", "miniapp_help")],
                [("👮 Модерация", "moderation")],
                [("⚙️ Настройки", "settings")],
                [("👑 Управление", "management")],
            ],
            "min_rank": "user",
        },

        # ─── 🌐 Mini App ────────────────────────────────────────────────
        "miniapp_help": {
            "text": (
                "🌐 <b>Mini App</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🚀 <b>Как открыть:</b>\n"
                "  <code>бот app</code> — прислать кнопку входа\n"
                "  Кнопка <b>Открыть App</b> — всегда рядом со строкой ввода в Telegram\n\n"
                "🧭 <b>Разделы внутри App:</b>\n"
                "  👤 Профиль — баланс, рамка, тема, бейджи\n"
                "  📊 Прогресс — XP, уровень, таланты, шарды\n"
                "  🐾 Питомец — статус, экспедиция, прокачка\n"
                "  💎 Кристаллы — пополнение, эксклюзивный магазин\n"
                "  📈 Облигации & Акции — биржа, история сделок\n"
                "  💳 Долги — заявки, история займов\n"
                "  🏆 Топ — рейтинги по всем категориям\n"
                "  🎯 Таланты — дерево прокачки\n"
                "  ⚔️ Босс — атака и лидерборд урона\n"
                "  🎰 Рулетка — интерактивное казино"
            ),
            "buttons": [
                [("🚀 Открыть Mini App", f"url:{MINI_APP_URL}")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "user",
        },

        # ─── 💰 Экономика ───────────────────────────────────────────────
        "economy": {
            "text": (
                f"💰 <b>Экономика (Мора 🪙)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🪙 <b>Основные команды:</b>\n"
                f"  <code>бот баланс</code> — мора, VIP, рамка, буст XP\n"
                f"  <code>бот магазин</code> — полный каталог покупок\n\n"
                f"👑 <b>Покупки за мору:</b>\n"
                f"  <code>бот купить вип</code> — VIP-статус ({VIP_PRICE:,} 🪙)\n"
                f"  <code>бот купить буст</code> — ×2 XP на 24 часа\n"
                f"  <code>бот рамки</code> — рамки для топа (от 250 🪙)\n"
                f"  <code>бот тема</code> — темы оформления профиля (от 2000 🪙)\n"
                f"  <code>бот титул [текст]</code> — подпись при нике ({CUSTOM_TITLE_PRICE:,} 🪙)\n\n"
                f"📩 <b>Скрытые сообщения:</b>\n"
                f"  <code>бот анонимка [текст]</code> — анон. в чат ({ANON_MSG_PRICE} 🪙)\n"
                f"  <code>бот секрет @user текст</code> — личное послание ({SECRET_MSG_PRICE} 🪙)\n\n"
                f"💡 <i>Мора: 17% шанс за сообщение (КД 3 мин), чекин, квесты, репутация, экспедиции, ивенты</i>"
            ),
            "buttons": [
                [("🏦 Банк", "bank_help"), ("🎰 Гача & Шарды", "gacha_help")],
                [("💎 Кристаллы", "crystals_help")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "user",
        },

        "bank_help": {
            "text": (
                "🏦 <b>Банк Северного Королевства</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>бот банк</code> — открыть меню банка\n\n"
                f"📊 <b>Планы вкладов:</b>\n"
                f"  {_bp['short']['label']}\n"
                f"  {_bp['medium']['label']}\n"
                f"  {_bp['long']['label']}\n\n"
                "⚠️ <b>Досрочное снятие:</b> теряешь ВСЕ проценты + 1% штраф\n"
                "📌 Мин. вклад: 100 🪙  |  Макс.: 10,000 🪙"
            ),
            "buttons": [[("🔙 Назад", "economy")]],
            "min_rank": "user",
        },

        "gacha_help": {
            "text": (
                f"🎰 <b>Молитвы (Гача) & Шарды</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"<code>бот молитва</code> — ×1 ({GACHA_SINGLE_PRICE} 🪙) или ×10 ({GACHA_MULTI_PRICE} 🪙)\n"
                f"<code>бот инвентарь</code> — все предметы и шарды\n"
                f"<code>бот продать мусор</code> — продать ненужное\n"
                f"<code>бот экипировать #ID</code> — надеть легендарку в профиль\n\n"
                f"📊 <b>Шансы дропа (ребаланс):</b>\n"
                f"  🗑 55% Мусор — продаётся за несколько монет\n"
                f"  ⚪ 28% Обычный — снаряжение, расходники\n"
                f"  🔵 14% Редкий — мощное снаряжение, косметика\n"
                f"  🟡  3% Легендарный — топ-снаряжение, VIP-темы\n"
                f"✨ <b>Гарант лего каждые {GACHA_PITY_MAX} круток!</b>\n\n"
                f"⚒️ <b>Шарды и крафт:</b>\n"
                f"  Шарды выпадают из гачи, квестов и за уровни (каждые 10 уровней)\n"
                f"  Накопи нужное кол-во → скрафти лучшее снаряжение или рамки\n"
                f"  Дерево талантов «Мастерство крафта» снижает кол-во нужных шардов\n"
                f"  Управление шардами → <i>Mini App → 📊 → Шарды & Крафт</i>"
            ),
            "buttons": [[("🔙 Назад", "economy")]],
            "min_rank": "user",
        },

        "crystals_help": {
            "text": (
                "💎 <b>Кристаллы (Telegram Stars)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Кристаллы — премиум-валюта, покупается за Telegram Stars ⭐\n\n"
                "<code>бот кристаллы</code> — купить кристаллы\n"
                "<code>бот мои кристаллы</code> — баланс кристаллов\n\n"
                "💰 <b>Пакеты покупки:</b>\n"
                "  💎 Стартовый: 50 ⭐ → 100 💎\n"
                "  💎 Базовый: 150 ⭐ → 330 💎  (+10% бонус)\n"
                "  💎 Продвинутый: 500 ⭐ → 1,200 💎  (+20%)\n"
                "  💎 Премиум: 1,000 ⭐ → 2,600 💎  (+30%)\n"
                "  💎 Легендарный: 2,500 ⭐ → 7,000 💎  (+40%)\n\n"
                "🛍 <b>Эксклюзив за кристаллы:</b>\n"
                "  🔮 Кристальная аура (200 💎)\n"
                "  🌑 Рамка «Тёмная материя» (350 💎)\n"
                "  📯 Рамка «Вестник» (500 💎)\n"
                "  👑 VIP на 7 дней (250 💎)\n"
                "  ⚡ Двойное везение (400 💎) — ×2 к пити\n"
                "  🌟 Рамка «Первое пополнение» — бонус при первой покупке\n\n"
                "💡 <i>Полный магазин кристаллов — Mini App → 💎 Кристаллы</i>"
            ),
            "buttons": [[("🔙 Назад", "economy")]],
            "min_rank": "user",
        },

        # ─── 📊 Прогрессия ──────────────────────────────────────────────
        "progression": {
            "text": (
                "📊 <b>Прогрессия: XP, Уровни & Таланты</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🌟 <b>XP и уровни:</b>\n"
                "  +2 XP за каждое сообщение (кулдаун 60 сек)\n"
                "  VIP ускоряет набор XP\n"
                "  «Форсированное обучение» → ×2 XP на 24 ч\n"
                "  <code>бот я</code> — профиль с прогресс-баром уровня\n\n"
                "⭐ <b>Репутация:</b>\n"
                "  Ответь <code>+</code> на сообщение → +1 репутация автору (+3 🪙 ему, +1 🪙 тебе)\n"
                "  Лимит: 10 раз в сутки одному пользователю\n"
                "  <code>бот репутация [@юзер]</code> — просмотр\n\n"
                "🎯 <b>Дерево Талантов:</b>\n"
                "  3 яруса: Базовые (Т1) → Продвинутые (Т2) → Мастерские (Т3)\n"
                "  Эффекты: +% мора, +ATK, −КД экспедиций, −КД репутации...\n"
                "  Очки дают уровни и ежедневные квесты\n"
                "  <i>Прокачка только в Mini App → 🎯 Таланты</i>\n\n"
                "⚒️ <b>Шарды и крафт:</b>\n"
                "  Выпадают из гачи, квестов, каждые 10 уровней, за достижения\n"
                "  Накопи шарды → скрафти редкие предметы или рамки\n"
                "  <i>Mini App → 📊 → Шарды & Крафт</i>"
            ),
            "buttons": [[("🔙 Назад", "main")]],
            "min_rank": "user",
        },

        # ─── 🎲 Игры & Казино ───────────────────────────────────────────
        "games": {
            "text": (
                "🎲 <b>Игры & Казино</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🪙 <b>Монетка</b>  (мин. {COIN_MIN_BET_CHAT:,} 🪙 в чате, до {COIN_MAX_BET:,} 🪙)\n"
                f"  <code>бот монетка N</code> — орёл или решка? ×2 или потеря\n\n"
                f"🎲 <b>Дуэль на кубиках</b>  (до {DICE_MAX_BET:,} 🪙)\n"
                f"  <code>бот кубик @юзер N</code> — бросаем кости, победит тот, у кого выше\n\n"
                f"🎟 <b>Лотерея</b>  ({LOTTERY_TICKET_PRICE} 🪙 / билет, 5% шанс выигрыша)\n"
                f"  <code>бот купить лотерею</code>  ·  <code>бот мои билеты</code>\n\n"
                f"🎰 <b>Рулетка</b>  (мин. {ROULETTE_MIN_BET} 🪙, макс. {ROULETTE_MAX_BET} 🪙 за ставку)\n"
                f"  Ставки на число, цвет или чётность\n"
                f"  5% комиссия с выигрыша → в казну чата\n"
                f"  Пити-защита: 3+ потери подряд → снижает лимит ставок\n"
                f"  <i>Только в Mini App → 🎰 Рулетка</i>\n\n"
                f"👊 <b>Социальные действия</b> (ответом или @юзер):\n"
                f"  <code>пни · укуси · обними · шлёпни · лизни · погладь · кинь</code>"
            ),
            "buttons": [
                [("📅 Чекин", "checkin"), ("⚔️ Босс", "boss")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "user",
        },

        "checkin": {
            "text": (
                "📅 <b>Ежедневный чекин</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "  <code>бот чекин</code> — отметиться сегодня\n"
                "  <code>бот чекин стрик</code> — стрик и календарь наград\n\n"
                "🎁 <b>Награды за стрик (ребаланс ×3–4):</b>\n"
                "  День 1–4: 100–130 🪙\n"
                "  День 5: 300 🪙 🏆\n"
                "  День 10: 500 🪙 🏆\n"
                "  День 15: 700 🪙 🏆\n"
                "  День 20: 1,000 🪙 🏆 + бесплатная молитва!\n\n"
                "💡 <b>Пропустил день?</b> Стрик откатывается к ближайшему чекпоинту\n"
                "(5/10/15/20) — не с нуля!\n\n"
                "📱 <i>Чекин доступен и в Mini App → 📅</i>"
            ),
            "buttons": [[("🔙 Назад", "games")]],
            "min_rank": "user",
        },

        "boss": {
            "text": (
                "⚔️ <b>Мировой Босс</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "  <code>бот босс</code> — статус и HP босса\n"
                "  <code>бот босс атака</code> — атаковать (КД 30 сек)\n\n"
                "⚔️ <b>Механика урона:</b>\n"
                "  Базовый урон = ATK экипированных предметов\n"
                "  Шанс крита (CRIT_RATE) → ×1.5 к урону\n"
                "  Случайный разброс: 80–120% от базы\n"
                "  Активные зелья ATK дополнительно усиливают атаку\n\n"
                "💰 <b>Награда за атаку:</b> max(5, урон ÷ 20) 🪙\n\n"
                "🏆 <b>Лидерборд урона:</b> Mini App → 🏆 Топ → ⚔️ Урон\n\n"
                "📱 <i>Атака доступна и в Mini App → ⚔️ Босс</i>"
            ),
            "buttons": [[("🔙 Назад", "games")]],
            "min_rank": "user",
        },

        # ─── 🐾 Питомцы ─────────────────────────────────────────────────
        "pets": {
            "text": (
                f"🐾 <b>Питомцы</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🐱🐶 <b>Заведение питомца:</b>\n"
                f"  Требует: брак ≥5 дней + суммарная репутация пары ≥10\n"
                f"  <code>бот завести питомца</code> — 48ч ожидание или {PET_MORA_SKIP_PRICE} 🪙 скип\n"
                f"  <code>бот питомец</code> — посмотреть питомца\n"
                f"  <code>бот назвать питомца [имя]</code> — первое имя бесплатно, далее {PET_RENAME_PRICE} 🪙\n"
                f"  <code>бот сменить вид питомца</code> — кот ↔ собака ({PET_CHANGE_TYPE_PRICE} 🪙)\n\n"
                f"🧭 <b>Экспедиции (добыча моры):</b>\n"
                f"  <code>бот экспедиция</code> — отправить за добычей\n"
                f"  2ч (бесплатно)  ·  4ч (5 🪙)  ·  8ч (10 🪙)\n"
                f"  <i>Питомец должен быть отдохнувшим (усталость &lt;100)</i>\n\n"
                f"🚶 <b>Прогулка:</b>\n"
                f"  <code>бот прогулка</code> — {WALK_DURATION_HOURS}ч прогулка\n"
                f"  Снижает усталость на 30  |  +{WALK_MORA_REWARD} 🪙 хозяину и партнёру\n\n"
                f"🍖 <b>Кормление (восстановление усталости):</b>\n"
                f"  <code>бот еда</code> — меню еды  ·  <code>бот купить еду [блюдо]</code>\n"
                f"  🍜 Лапша путника (20 🪙, −20 усталости)\n"
                f"  🍄 Гриб Слепого Ка (35 🪙, −35 усталости)\n"
                f"  🦀 Золотой краб (40 🪙, −40 усталости)\n"
                f"  🦞 Морской деликатес (80 🪙, −80 усталости)\n\n"
                f"📋 <b>Ежедневный квест питомца:</b>\n"
                f"  <code>бот задание</code> — получить / проверить\n"
                f"  <code>бот перебросить задание</code> — сменить ({QUEST_REROLL_PRICE} 🪙 или купон реролла)"
            ),
            "buttons": [[("🔙 Назад", "main")]],
            "min_rank": "user",
        },

        # ─── 💍 Социалка ────────────────────────────────────────────────
        "social": {
            "text": (
                "💍 <b>Социалка: Отношения & Подарки</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "💕 <b>Брак:</b>\n"
                "  <code>бот брак @юзер</code> — предложить руку и сердце\n"
                "  <code>бот пара</code> — информация о текущей паре\n"
                "  <code>бот развод</code> — расторгнуть брак (питомец теряется!)\n\n"
                "🎁 <b>Подарки партнёру:</b>\n"
                "  <code>бот подарки</code> — витрина подарков\n"
                "  🌹 Роза (50 🪙)  ·  💐 Букет (150 🪙)  ·  🍫 Шоколадка (100 🪙)\n"
                "  💎 Бриллиант (500 🪙)  ·  🏝 Путёвка (1,500 🪙) → +10% мора 24ч\n"
                "  👑 Корона (3,000 🪙) → +15% мора 48ч\n"
                "  🏰 Замок (5,000 🪙) → +20% мора 72ч\n\n"
                "👨‍👩‍👧 <b>Семейный кошелёк:</b>\n"
                "  <code>бот семейный кошелёк</code> — общий баланс пары\n"
                "  <code>бот пополнить семью N</code>  ·  <code>бот снять семью N</code>\n\n"
                "🎭 <b>Роли в сообществе:</b>\n"
                "  <code>бот роли</code> — список ролей  ·  <code>бот мои роли</code>"
            ),
            "buttons": [[("🔙 Назад", "main")]],
            "min_rank": "user",
        },

        # ─── 📈 Финансы & Биржа ─────────────────────────────────────────
        "finance": {
            "text": (
                f"📈 <b>Финансы & Биржа</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💸 <b>Переводы моры:</b>\n"
                f"  <code>бот кошелёк</code> — история транзакций\n"
                f"  <code>бот перевести N @юзер</code> — перевод ({MORA_TRANSFER_MIN}–{MORA_TRANSFER_MAX:,} 🪙)\n\n"
                f"💳 <b>Займы (долги):</b>\n"
                f"  <code>бот дать в долг N @юзер</code> — дать займ\n"
                f"  <code>бот долги</code> — список займов · <code>бот вернуть долг #ID</code> — погасить\n"
                f"  Макс. займ: {LOAN_MAX_AMOUNT:,} 🪙  |  Макс. активных займов: {LOAN_MAX_ACTIVE}\n"
                f"  <i>Заёмщик подтверждает заявку — деньги переходят после принятия</i>\n"
                f"  <i>Управление через Mini App → 💳 Долги</i>\n\n"
                f"🔍 <b>Шпионаж:</b>\n"
                f"  <code>бот шпионить @юзер</code> — узнать баланс другого игрока"
            ),
            "buttons": [
                [("📜 Облигации & Акции", "bonds_help"), ("🏪 Аукцион", "auction_help")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "user",
        },

        "bonds_help": {
            "text": (
                "📜 <b>Облигации & Акции (Биржа)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🏦 <b>Облигации</b> — стабильные инструменты (8–18% волатильность):\n"
                "  <code>бот облигации</code> — просмотр доступных\n"
                "  <code>бот купить обл [название] [кол-во]</code>\n"
                "  <code>бот продать обл [название] [кол-во]</code>\n"
                "  Примеры: 📜 Холодный Ветер (8%), 🏦 Банк Сев. Кор. (5%)\n\n"
                "📊 <b>Акции</b> — высокорисковые (35–50% волатильность):\n"
                "  <code>бот акции</code> — текущие котировки\n"
                "  <code>бот купить акции [название] [кол-во]</code>\n"
                "  Примеры: 🐂 Итто-Коин (50%!), 💰 Дори-Инвесты (45%)\n\n"
                "📌 <b>Правила:</b>\n"
                "  Лимит 55 штук одного типа на руках\n"
                "  Цены обновляются автоматически каждые 2–4 часа\n"
                "  Талант «Биржевой брокер» (Т2) → +% к прибыли\n"
                "  Талант «Биржевая стойкость» (Т3) → −% к убыткам"
            ),
            "buttons": [[("🔙 Назад", "finance")]],
            "min_rank": "user",
        },

        "auction_help": {
            "text": (
                "🏪 <b>Аукцион предметов</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>бот аукцион</code> — список активных лотов\n"
                "<code>бот продать #ID [цена]</code> — выставить предмет из инвентаря\n"
                "<code>бот ставка #лот [сумма]</code> — сделать ставку\n"
                "<code>бот выкупить #лот</code> — купить по buyout\n"
                "<code>бот мои лоты</code> · <code>бот отмена лот #лот</code>\n\n"
                "📌 <b>Правила:</b>\n"
                "  Комиссия с продажи — 5% (скидка талантом «Барыга рынка» Т3)\n"
                "  Лот активен 24 ч (+ 7 ч за «Пропуск переноса»)\n"
                "  Проигравшие ставки возвращаются автоматически"
            ),
            "buttons": [[("🔙 Назад", "finance")]],
            "min_rank": "user",
        },

        # ─── 📅 Ивенты ──────────────────────────────────────────────────
        "events": {
            "text": (
                "📅 <b>Ивенты & Задания</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "📋 <b>Ежедневный квест:</b>\n"
                "  <code>бот задание</code> — получить / проверить квест\n"
                "  <code>бот перебросить задание</code> — сменить (25 🪙 или купон)\n"
                "  Награда: мора + XP + осколок шарда\n\n"
                "🎁 <b>Богатый сундук</b> (авто-ивент, каждые 4–8 ч):\n"
                "  Появляется в чате — успей нажать кнопку первым!\n"
                "  6 победителей, 10–60 🪙 каждому\n\n"
                "🚚 <b>Дилижанс</b> (по пятницам 20:00 Цюрих):\n"
                "  Случайные награды за участие — мора, предметы, бонусы\n\n"
                "🧑‍💼 <b>Торговец</b> (раз в 3 дня):\n"
                "  Приходит в чат с уникальным ограниченным товаром\n\n"
                "🏆 <b>Еженедельный топ</b> (каждый Пн 00:00 Цюрих):\n"
                "  🥇 1 место: 150 🪙  ·  🥈 2 место: 100 🪙  ·  🥉 3 место: 75 🪙\n"
                "  Места 4–10: от 60 до 20 🪙\n"
                "  <code>бот топ неделя</code> — текущий рейтинг"
            ),
            "buttons": [[("🔙 Назад", "main")]],
            "min_rank": "user",
        },

        # ─── ℹ️ Полезное ────────────────────────────────────────────────
        "info": {
            "text": (
                "ℹ️ <b>Полезное</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🏆 <b>Рейтинги:</b>\n"
                "  <code>бот топ</code> — топ за всё время\n"
                "  <code>бот топ день</code>  ·  <code>бот топ неделя</code>\n\n"
                "👤 <b>Информация о пользователях:</b>\n"
                "  <code>бот я</code> — полный профиль\n"
                "  <code>бот инфо [@юзер]</code> — краткая справка\n"
                "  <code>бот кто [@юзер]</code> — полное досье\n"
                "  <code>бот айди [@юзер]</code> — Telegram ID\n\n"
                "📋 <b>Чат:</b>\n"
                "  <code>бот правила</code> — правила чата\n"
                "  <code>бот время [город]</code> — текущее время\n"
                "  <code>бот наши ссылки</code> — соцсети сообщества\n"
                "  <code>бот чат</code> — информация о текущем чате\n"
                "  <code>#название</code> — вызвать сохранённую заметку\n\n"
                "🚨 <b>Жалоба на нарушителя:</b>\n"
                "  <code>бот жалоба [причина]</code> ответом на его сообщение\n"
                "  <i>Уведомление придёт модераторам чата</i>"
            ),
            "buttons": [[("🔙 Назад", "main")]],
            "min_rank": "user",
        },

        # ─── 👮 Модерация [⚡ АдминМл+] ─────────────────────────────────
        "moderation": {
            "text": (
                "👮 <b>Модерация</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Выбери подраздел 👇"
            ),
            "buttons": [
                [("⚠️ Варны & Муты  [⚡АдминМл+]", "s_warns")],
                [("🔨 Бан & Управление  [👑СоВлад+]", "s_mod")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "admin_junior",
        },

        "s_warns": {
            "text": (
                f"⚠️ <b>Варны & Муты</b>  <code>[⚡ АдминМл+]</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🔴 <b>Предупреждения:</b>\n"
                f"  <code>бот варн [@юзер] [причина]</code>\n"
                f"  <i>└ {MAX_WARNS} варна → уведомление всем модераторам+</i>\n"
                f"  <code>бот предупреждения [@юзер]</code> — просмотр\n"
                f"  <code>бот снять варн [@юзер]</code> — снять варн\n"
                f"  <code>бот варнлист</code> — список участников с варнами\n\n"
                f"🔇 <b>Мут:</b>\n"
                f"  <code>бот мут [@юзер] [30с|10м|2ч|1д]</code>\n"
                f"  <code>бот размут [@юзер]</code>\n"
                f"  <code>бот неактив24</code> — замутить неактивных за 24 ч"
            ),
            "buttons": [[("🔙 Назад", "moderation")]],
            "min_rank": "admin_junior",
        },

        "s_mod": {
            "text": (
                "🔨 <b>Бан & Модерация</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🚫 <code>бот бан · разбан · баны · кик</code>\n"
                "🆔 <code>бот юзбан · юзразбан · юзбаны</code> — бан по ID\n\n"
                "📌 <code>бот закрепить · открепить · очистить N</code>\n\n"
                "📒 <code>бот заметка [имя] [текст]</code>  ·  <code>бот заметки</code>\n"
                "🔁 <code>бот автоответ [фраза] | [ответ]</code> — автофильтр\n"
                "🚷 <code>бот блок · разблок · чс</code> — чёрный список слов\n"
                "🚪 <code>бот ушли [N]</code> — список покинувших чат\n"
                "🔍 <code>бот неактив</code> — полный список неактивных"
            ),
            "buttons": [[("🔙 Назад", "moderation")]],
            "min_rank": "co_owner",
        },

        # ─── ⚙️ Настройки [👑 СоВлад+] ──────────────────────────────────
        "settings": {
            "text": (
                "⚙️ <b>Настройки чата</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Выбери подраздел 👇"
            ),
            "buttons": [
                [("👥 Персонал", "s_staff"), ("💬 Правила & Привет.", "s_rules")],
                [("🔒 Замки", "s_locks"), ("🛡 Антифлуд 2.0", "s_flood")],
                [("🔗 Соцсети", "s_social"), ("📥 Импорт данных", "s_import")],
                [("⚙️ Модули", "s_modules")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "co_owner",
        },

        "s_staff": {
            "text": (
                "👥 <b>Персонал & Роли</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>бот ранг [ранг] [@юзер]</code> — назначить ранг\n"
                "  <i>user · moderator · admin_junior · admin_senior · co_owner · owner</i>\n"
                "<code>бот состав</code>  ·  <code>бот статистика</code>\n\n"
                "🎭 <b>Кастомные роли:</b>\n"
                "  <code>бот добавить роль</code> — создать роль\n"
                "  <code>бот выдать роль [@юзер]</code> — назначить\n"
                "  <code>бот снять роль [@юзер]</code> — убрать\n"
                "  <code>бот роли</code>  ·  <code>бот мои роли</code>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "co_owner",
        },

        "s_rules": {
            "text": (
                "💬 <b>Правила & Приветствие</b>  <code>[⚡ АдминСт+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "📜 <code>бот правила установить [текст]</code>\n\n"
                "👋 <code>бот приветствие [текст]</code>\n"
                "  <i>Переменные: {name} · {username} · {chat}</i>\n"
                "<code>бот прощание [текст]</code>\n"
                "<code>бот тег входа [вкл/выкл]</code> — упоминать всех при входе\n"
                "<code>бот история чата</code> — открыть/скрыть историю для новых"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "admin_senior",
        },

        "s_locks": {
            "text": (
                "🔒 <b>Замки контента</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>бот замок [тип]</code>  ·  <code>бот открыть [тип]</code>  ·  <code>бот замки</code>\n"
                "<i>Типы: links · stickers · gifs · forwards · voice · video · photo · audio</i>\n\n"
                "🔤 <b>Фильтр слов:</b>\n"
                "  <code>бот фильтрмат [вкл/выкл]</code> — автоудаление мата\n"
                "  <code>бот блок [слово]</code>  ·  <code>бот разблок</code>  ·  <code>бот чс</code>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "co_owner",
        },

        "s_flood": {
            "text": (
                "🛡 <b>Антифлуд 2.0</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🌊 <b>Базовый антифлуд:</b>\n"
                "  <code>бот антифлуд N [Xс]</code> — N сообщений в X сек → мут\n"
                "  <code>бот антифлуд выкл</code> — отключить\n\n"
                "🧠 <b>Умный Антифлуд 2.0 (trust-level):</b>\n"
                "  Автоматически учитывает «доверие» участника:\n"
                "  🆕 Новичок (&lt;300 сообщ.) — строгие лимиты\n"
                "  👤 Обычный — стандартные лимиты\n"
                "  ⭐ Доверенный (&gt;1000 сообщ.) — мягкие лимиты\n\n"
                "🧹 <b>Чистка неактивных:</b>\n"
                "  <code>бот чистка [N]</code>  ·  <code>бот чистка открыть</code>\n"
                "  <code>бот чистка порог N</code>  ·  <code>бот чистка дата</code>\n\n"
                "😴 <b>Отдых (исключение из чистки):</b>\n"
                "  <code>бот отдых @user [дней]</code>  ·  <code>бот отдых снять</code>  ·  <code>бот отдых список</code>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "co_owner",
        },

        "s_import": {
            "text": (
                "📥 <b>Импорт данных</b>  <code>[🛠 Дев]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "💬 <code>бот загрузить данные</code> — JSON-импорт истории сообщений\n"
                "💍 <code>бот загрузить браки</code> — JSON-импорт пар\n\n"
                "<i>Данные привяжутся к аккаунту при первом сообщении пользователя.</i>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "developer",
        },

        "s_social": {
            "text": (
                "🔗 <b>Соцсети & Ссылки</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>бот соцсети tiktok|youtube|instagram [URL]</code> — установить ссылку\n"
                "<code>бот наши ссылки</code> — показать список в чате\n"
                "<code>бот история чата</code> — управление историей для новых"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "co_owner",
        },

        "s_modules": {
            "text": (
                "⚙️ <b>Модули & Функции</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Управление включёнными модулями бота для этого чата:\n\n"
                "<code>бот настройки</code> — просмотр и переключение модулей\n\n"
                "<i>Доступные модули: economy · website · media · admin · welcome</i>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "co_owner",
        },

        # ─── 👑 Управление [👑 Влад+] ───────────────────────────────────
        "management": {
            "text": (
                "👑 <b>Управление</b>  <code>[👑 Влад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Выбери подраздел 👇"
            ),
            "buttons": [
                [("🔱 Владелец", "s_owner"), ("🎉 Ивенты  [АдминСт+]", "s_events")],
                [("🛠 Разработчик", "s_dev")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "owner",
        },

        "s_owner": {
            "text": (
                "🔱 <b>Команды Владельца</b>  <code>[👑 Влад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>бот совладелец [@юзер]</code> — назначить СоВлада\n\n"
                "📣 <b>Рассылка (колл):</b>\n"
                "  <code>бот колл [#все|#юзеры|#стафф|#модеры|#админы] [текст]</code>\n\n"
                "💰 <b>Казна:</b>\n"
                "  <code>бот казна</code> — текущий баланс казны\n"
                "  <code>бот казна дать @user N</code> — выдать из казны\n"
                "  <code>бот казна забрать @user N</code> — вернуть в казну\n"
                "  <code>бот выдать xp N @user</code> — начислить XP\n\n"
                "🔔 <b>Чат администрации (уведомления):</b>\n"
                "  1️⃣ В осн. чате: <code>бот привязать</code>\n"
                "  2️⃣ В чате адм.: <code>бот принять -100XXXX</code>\n"
                "  <code>бот привязка</code>  ·  <code>бот отвязать</code>"
            ),
            "buttons": [[("🔙 Назад", "management")]],
            "min_rank": "owner",
        },

        "s_events": {
            "text": (
                "🎉 <b>Ивенты — ручной запуск</b>  <code>[⚡ АдминСт+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🎁 <code>бот сундук</code> — запустить Rich Chest\n"
                "  <i>По пятницам автоматически, или вручную</i>\n\n"
                "🚚 <code>бот дилижанс</code> — Дилижанс вручную\n"
                "  <i>По пятницам 20:00 Цюрих автоматически</i>\n\n"
                "🧑‍💼 Торговец запускается раз в 3 дня автоматически\n\n"
                "🛠 <b>Dev-only:</b>\n"
                "  <code>бот эвент [сундук|дилижанс|торговец]</code>\n"
                "  <code>бот сетбаланс [сумма] [@user]</code>"
            ),
            "buttons": [[("🔙 Назад", "management")]],
            "min_rank": "admin_senior",
        },

        "s_dev": {
            "text": (
                "🛠 <b>Разработчик</b>  <code>[🛠 Дев]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>бот разработчик · скан · сетюзер · прибавитьxp · сеттитул</code>\n"
                "<code>бот выдать N @user</code> — эмиссия Моры напрямую\n"
                "<code>бот датьпредмет [item_key] @user</code> — выдать предмет\n\n"
                "📡 <b>Каналы & Чаты:</b>\n"
                "  <code>бот канал правила|основной &lt;id&gt;</code>  ·  <code>бот каналы</code>\n"
                "  <code>бот тестчат [chat_id]</code>  ·  <code>бот тестчаты</code>\n"
                "  <code>бот привязки</code>  ·  <code>бот снятьнадмин [chat_id]</code>\n\n"
                "🎮 <b>Принудительный запуск ивентов:</b>\n"
                "  <code>бот эвент сундук</code>  ·  <code>бот эвент дилижанс</code>  ·  <code>бот эвент торговец</code>\n\n"
                "🕐 <code>бот таймзона [tz]</code> — изменить часовой пояс чата"
            ),
            "buttons": [[("🔙 Назад", "management")]],
            "min_rank": "developer",
        },
    }


def _build_help_kb(page_id: str, uid: int, lvl: int, chat_id: int = 0) -> InlineKeyboardMarkup:
    """Построить Inline-клавиатуру для страницы справочника."""
    pages = _help_pages()
    page = pages.get(page_id)
    if not page:
        return InlineKeyboardMarkup(inline_keyboard=[])
    rows: list[list[InlineKeyboardButton]] = []
    for btn_row in page["buttons"]:
        row: list[InlineKeyboardButton] = []
        for label, target in btn_row:
            if target.startswith("url:"):
                btn_url = target[4:]
                if chat_id and btn_url == _MINI_APP_URL:
                    abs_cid = abs(chat_id)
                    btn_url = f"{_MINI_APP_TG_URL}?startapp={abs_cid}"
                row.append(InlineKeyboardButton(text=label, url=btn_url))
                continue
            target_page = pages.get(target)
            if target_page and lvl < rank_level(target_page["min_rank"]):
                continue
            row.append(InlineKeyboardButton(
                text=label,
                callback_data=f"h:{target}:{uid}:{lvl}",
            ))
        if row:
            rows.append(row)
    rows.append([InlineKeyboardButton(
        text="❌ Закрыть", callback_data=f"h:close:{uid}:{lvl}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _top_keyboard(active: str, uid: int) -> InlineKeyboardMarkup:
    row1 = []
    for label, code in [("📅 День", "d"), ("📆 Неделя", "w"), ("🏆 Всё время", "a")]:
        text = f"· {label} ·" if code == active else label
        row1.append(InlineKeyboardButton(text=text, callback_data=f"top:{uid}:{code}"))
    row2 = []
    for label, code in [("◀ Вчера", "pd"), ("◀ Прошлая нед.", "pw")]:
        text = f"· {label} ·" if code == active else label
        row2.append(InlineKeyboardButton(text=text, callback_data=f"top:{uid}:{code}"))
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


@router.message(BotCommand("помощь", "help", "команды", "справка", "меню", "гайд", "гид", "start", "старт"))
async def cmd_help(message: Message, cmd_args: str):
    from config import DEVELOPER_ID
    stats = await get_user_stats(message.from_user.id, message.chat.id)
    rank = stats["rank"] if stats else "user"
    if DEVELOPER_ID and message.from_user.id == DEVELOPER_ID:
        rank = "developer"
    lvl = rank_level(rank)
    uid = message.from_user.id
    pages = _help_pages()
    text = pages["main"]["text"]
    kb = _build_help_kb("main", uid, lvl, chat_id=message.chat.id)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(BotCommand("app", "miniapp", "миниапп", "сайт", "открыть app"))
async def cmd_open_app(message: Message, cmd_args: str):
    from filters.feature_flag import feature_enabled
    if not await feature_enabled(message, "website"):
        return
    from config import MINI_APP_URL, MINI_APP_TG_URL

    if message.chat.type == "private":
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🚀 Открыть Mini App",
                web_app=WebAppInfo(url=MINI_APP_URL),
            ),
        ]])
        await message.answer(
            "🌐 <b>Mini App</b>\n\n"
            "Нажми кнопку ниже, чтобы открыть приложение внутри Telegram Mini App.\n"
            "Также кнопка <b>Открыть App</b> доступна возле строки ввода в Telegram.",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    abs_cid = abs(message.chat.id)
    app_link = f"{MINI_APP_TG_URL}?startapp={abs_cid}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Открыть Mini App", url=app_link),
    ]])
    await message.answer(
        "🌐 <b>Mini App</b>\n\n"
        "Нажми кнопку — откроется профиль именно этого чата.",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("h:"))
async def cb_help(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer()
        return
    page_id, owner_id_str, lvl_str = parts[1], parts[2], parts[3]

    try:
        owner_id = int(owner_id_str)
        lvl = int(lvl_str)
    except ValueError:
        await callback.answer()
        return

    if await not_your_button(callback, owner_id, "🚫 Это меню не твоё. Напиши «бот помощь»."):
        return

    if page_id == "close":
        try:
            await callback.message.delete()
        except Exception as _e:
            _log.debug("%s", _e)
        await callback.answer()
        return

    pages = _help_pages()
    page = pages.get(page_id)
    if not page:
        await callback.answer()
        return

    if lvl < rank_level(page["min_rank"]):
        await callback.answer("🚫 Нет доступа.", show_alert=True)
        return

    kb = _build_help_kb(page_id, owner_id, lvl, chat_id=callback.message.chat.id)
    try:
        await callback.message.edit_text(page["text"], parse_mode="HTML", reply_markup=kb)
    except Exception as _e:
        _log.debug("%s", _e)
    await callback.answer()


_TOP_MEDALS = ["🥇", "🥈", "🥉", "🎖", "🎗"]


def _make_top_bar(count: int, max_count: int, width: int = 8) -> str:
    """Unicode █░ progress bar relative to maximum count."""
    if max_count == 0:
        return "░" * width
    filled = max(0, min(width, round((count / max_count) * width)))
    return "█" * filled + "░" * (width - filled)


async def _send_long_html(message, text: str, reply_markup=None):
    """Send text as HTML, splitting into multiple messages if >4096 chars."""
    MAX = 4000
    if len(text) <= MAX:
        await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
        return
    lines = text.split("\n")
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for line in lines:
        if buf_len + len(line) + 1 > MAX and buf:
            chunks.append("\n".join(buf))
            buf = []
            buf_len = 0
        buf.append(line)
        buf_len += len(line) + 1
    if buf:
        chunks.append("\n".join(buf))
    for i, chunk in enumerate(chunks):
        kb = reply_markup if i == len(chunks) - 1 else None
        await message.answer(chunk, parse_mode="HTML", reply_markup=kb)


def _build_top_text(
    top: list,
    prev_top: list,
    mora_map: dict,
    title: str,
    count_field: str,
    caller_uid: int | None = None,
    chat_id: int | None = None,
    hof_data: list | None = None,
) -> str:
    # Previous period rank lookup
    prev_rank: dict[int, int] = {}
    for i, u in enumerate(prev_top):
        uid = u["user_id"] if "user_id" in u.keys() else None
        if uid:
            prev_rank[uid] = i + 1

    # Top-10 sets for news section
    top10_cur = {u["user_id"] for u in top[:10] if "user_id" in u.keys()}
    top10_prv = {u["user_id"] for u in prev_top[:10] if "user_id" in u.keys()}

    _MEDALS = ["🥇", "🥈", "🥉"]

    # ── HTML header (title + news) ─────────────────────────────────────────────
    html_lines: list[str] = [title]
    if prev_top and top10_prv:
        entered = [html.escape(u["full_name"]) for u in top[:10]
                   if "user_id" in u.keys() and u["user_id"] not in top10_prv]
        exited  = [html.escape(u["full_name"]) for u in prev_top[:10]
                   if "user_id" in u.keys() and u["user_id"] not in top10_cur]
        if entered or exited:
            if entered:
                e_str = ", ".join(entered[:4]) + (f" +{len(entered)-4}" if len(entered) > 4 else "")
                html_lines.append(f"🆙 <i>В топ-10: {e_str}</i>")
            if exited:
                x_str = ", ".join(exited[:4]) + (f" +{len(exited)-4}" if len(exited) > 4 else "")
                html_lines.append(f"📉 <i>Вышли: {x_str}</i>")

    html_lines.append("")

    # ── Mobile-friendly rows ───────────────────────────────────────────────────
    visible = top

    for i, u in enumerate(visible):
        count    = u[count_field] if count_field in u.keys() else 0
        uid_top  = u["user_id"] if "user_id" in u.keys() else None
        mora_row = mora_map.get(uid_top) if uid_top else None

        place = _MEDALS[i] if i < 3 else f"{i + 1}."

        raw_name = u["full_name"] if "full_name" in u.keys() else "?"
        if len(raw_name) > 18:
            raw_name = raw_name[:17] + "…"
        name = html.escape(raw_name)

        badges = ""
        if mora_row and mora_row.get("vip"):
            badges += " 💎"

        count_str = f"{count:,}".replace(",", "\u00a0")
        html_lines.append(f"{place} {name} — {count_str}{badges}")

    # ── Weekly prize pool info (for weekly / all-time views) ───────────────────
    if count_field in ("wc", "message_count"):
        prize_lines = ["", "🏅 <b>Призы за топ-10 недели:</b>"]
        _MEDALS = ["🥇", "🥈", "🥉"]
        for place, amount in WEEKLY_TOP_REWARDS.items():
            medal = _MEDALS[place - 1] if place <= 3 else f"{place}."
            prize_lines.append(f"  {medal} {amount} 🪙")
        prize_lines.append("<i>Начисляются каждый понедельник в 00:00 Цюрих</i>")
        html_lines.extend(prize_lines)

    # ── Hall of Fame: last week's winners ──────────────────────────────────────
    if hof_data:
        _MEDALS2 = ["🥇", "🥈", "🥉"]
        html_lines.append("")
        html_lines.append("🏆 <b>Зал Славы — прошлая неделя:</b>")
        for row in hof_data:
            place  = row["place"]
            uid    = row["user_id"]
            fname  = html.escape(row.get("full_name") or str(uid))
            amount = row["amount"]
            medal  = _MEDALS2[place - 1] if place <= 3 else f"{place}."
            html_lines.append(f"  {medal} {user_mention(uid, fname)} — {amount} 🪙")

    # ── Personal placement footer ──────────────────────────────────────────────
    footer = ""
    if caller_uid:
        for i, u in enumerate(top):
            if "user_id" in u.keys() and u["user_id"] == caller_uid:
                total = len(top)
                if i == 0:
                    footer = "\n\n🥇 <i>Ты на 1 месте — лучший в чате!</i>"
                else:
                    pct = round((i + 1) / total * 100) if total else 100
                    footer = f"\n\n👤 <i>Ты на {i + 1} месте из {total} (топ {pct}%)</i>"
                break

    return "\n".join(html_lines) + footer


@router.callback_query(F.data.startswith("top:"))
async def cb_top(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer()
        return
    owner_id_str, period = parts[1], parts[2]
    try:
        owner_id = int(owner_id_str)
    except ValueError:
        await callback.answer()
        return
    if await not_your_button(callback, owner_id, "🚫 Это меню не твоё. Напиши «бот топ»."):
        return
    chat_id = callback.message.chat.id

    if period == "close":
        try:
            await callback.message.delete()
        except Exception as _e:
            _log.debug("%s", _e)
        await callback.answer()
        return

    prev_top: list = []
    if period == "d":
        top = await get_daily_top(chat_id, 500)
        prev_top = await get_yesterday_top(chat_id, 500)
        title = "📅 <b>Рейтинг активных за сегодня:</b>"
        count_field = "dc"
    elif period == "w":
        top = await get_weekly_top(chat_id, 500)
        prev_top = await get_prev_weekly_top(chat_id, 500)
        title = "📆 <b>Рейтинг активных за неделю:</b>"
        count_field = "wc"
    elif period == "pd":
        top = await get_yesterday_top(chat_id, 500)
        title = "📅 <b>Рейтинг активных за вчера:</b>"
        count_field = "dc"
    elif period == "pw":
        top = await get_prev_weekly_top(chat_id, 500)
        title = "📆 <b>Рейтинг активных за прошлую неделю:</b>"
        count_field = "wc"
    else:
        top = await get_top_by_messages_in_chat(chat_id, 500)
        title = "🏆 <b>Рейтинг активных за всё время:</b>"
        count_field = "message_count"

    if not top:
        try:
            await callback.message.edit_text(
                "📊 Статистика пока пуста.",
                reply_markup=_top_keyboard(period, owner_id),
            )
        except Exception as _e:
            _log.debug("%s", _e)
        await callback.answer()
        return

    uid_list = [u["user_id"] for u in top if "user_id" in u.keys()]
    mora_map = await get_mora_batch(uid_list, chat_id)
    # Load Hall of Fame for weekly/all-time views
    hof_data = None
    if count_field in ("wc", "message_count"):
        from zoneinfo import ZoneInfo as _ZI
        from datetime import datetime as _dt, timedelta as _td
        _now = _dt.now(_ZI("Europe/Zurich"))
        _prev_iso = (_now - _td(days=7)).isocalendar()
        _prev_key = f"{_prev_iso.year}-W{_prev_iso.week:02d}"
        hof_data = await get_weekly_top_reward_history(chat_id, _prev_key)
    text = _build_top_text(top, prev_top, mora_map, title, count_field, callback.from_user.id,
                           chat_id=chat_id, hof_data=hof_data)

    try:
        if len(text) <= 4000:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=_top_keyboard(period, owner_id),
            )
        else:
            try:
                await callback.message.delete()
            except Exception as _e:
                _log.debug("%s", _e)
            await _send_long_html(callback.message, text, reply_markup=_top_keyboard(period, owner_id))
    except Exception as _e:
        _log.debug("%s", _e)
    await callback.answer()


@router.callback_query(F.data.startswith("pn:"))
async def cb_profile_nav(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    uid = int(parts[2])

    if await not_your_button(callback, uid, "🚫 Это меню не твоё. Напиши «бот профиль»."):
        return

    if action == "close":
        try:
            await callback.message.delete()
        except Exception as _e:
            _log.debug("%s", _e)
        await callback.answer()
        return

    if action == "rep":
        stats = await get_user_stats(uid, callback.message.chat.id)
        user = await get_user(uid)
        name = user["full_name"] if user else "?"
        rep = (stats["reputation"] or 0) if stats else 0
        text = f"⭐ <b>Репутация</b> {user_mention(uid, name)}: <b>{rep:+d}</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📊 Уровень", callback_data=f"pn:lvl:{uid}"),
            InlineKeyboardButton(text="👤 Профиль", callback_data=f"pn:me:{uid}"),
        ]])
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as _e:
            _log.debug("%s", _e)
    elif action == "lvl":
        stats = await get_user_stats(uid, callback.message.chat.id)
        user = await get_user(uid)
        name = user["full_name"] if user else "?"
        xp = (stats["xp"] or 0) if stats else 0
        lvl = (stats["level"] or 1) if stats else 1
        from database.db import xp_for_level
        next_xp = xp_for_level(lvl + 1)
        bar_filled = min(10, int((xp - xp_for_level(lvl)) / max(1, next_xp - xp_for_level(lvl)) * 10))
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        text = (
            f"🌟 <b>Уровень</b> {user_mention(uid, name)}\n\n"
            f"📊 Уровень: <b>{lvl}</b>\n"
            f"✨ XP: <b>{xp}</b> / {next_xp}\n"
            f"[{bar}]"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⭐ Репутация", callback_data=f"pn:rep:{uid}"),
            InlineKeyboardButton(text="👤 Профиль", callback_data=f"pn:me:{uid}"),
        ], [
            InlineKeyboardButton(text="❌ Закрыть", callback_data=f"pn:close:{uid}"),
        ]])
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as _e:
            _log.debug("%s", _e)
    elif action == "me":
        user = await get_user(uid)
        if not user:
            await callback.answer("❌ Не найден", show_alert=True)
            return
        from config import PROFILE_THEMES
        from services.achievements import ACH_BY_KEY
        from handlers.economy import TOP_FRAMES, _frame_emoji
        chat_id = callback.message.chat.id
        stats = await get_user_stats(uid, chat_id)
        rank    = stats["rank"]          if stats else "user"
        xp      = stats["xp"]           if stats else 0
        lvl_val = stats["level"]         if stats else 1
        rep     = stats["reputation"]    if stats else 0
        msgs    = stats["message_count"] if stats else 0
        bio     = stats["bio"]           if stats else None

        mora_row = await get_mora(uid, chat_id)
        mora_bal = (mora_row["balance"] or 0) if mora_row else 0
        frame_key = mora_row["top_frame"] if mora_row else None

        theme_key = await get_active_theme(uid, chat_id)
        theme = PROFILE_THEMES.get(theme_key, PROFILE_THEMES["default"])
        badge_keys = await get_user_badges(uid, chat_id)
        badges_str = " ".join(
            ACH_BY_KEY[bk]["emoji"] for bk in badge_keys if bk in ACH_BY_KEY
        )
        equipped = await get_all_equipped_items(uid, chat_id)

        from database.db import xp_for_level
        next_xp = xp_for_level(lvl_val + 1)
        bar_filled = min(10, int((xp - xp_for_level(lvl_val)) / max(1, next_xp - xp_for_level(lvl_val)) * 10))
        bar = "█" * bar_filled + "░" * (10 - bar_filled)

        sep = theme["separator"]
        lines = [f"{theme['header']}", sep]
        if badges_str:
            lines.append(f"🏅 {badges_str}")
        lines += [
            f"🏷 {html.escape(user['full_name'])}",
            f"🎖 {rank_name(rank)}",
            f"🌟 Ур. <b>{lvl_val}</b>  [{bar}]  {xp}/{next_xp}",
            f"⭐ Репутация: <b>{rep:+d}</b>",
            f"💬 Сообщений: {msgs}",
        ]
        if callback.message.chat.type == "private":
            lines.append(f"🪙 Мора: <b>{mora_bal}</b> 🪙")
        if theme_key != "default":
            from config import COSMETIC_TIER_LABELS
            tier_label = COSMETIC_TIER_LABELS.get(theme.get("tier", "common"), "")
            lines.append(f"🎨 Тема: {theme['name']} [{tier_label}]")
        if equipped:
            equip_str = "  ".join(
                f"{i['emoji']} {i['item_name']}" + (f" +{i['enhancement_level']}" if i['enhancement_level'] else "")
                for i in equipped
            )
            lines.append(f"⚔️ Снаряжение: {equip_str}")
        if frame_key:
            frame_label = next((f[2] for f in TOP_FRAMES if f[0] == frame_key), None)
            if frame_label:
                lines.append(f"🖼 Рамка: {_frame_emoji(frame_key)} {frame_label}")
        if bio:
            lines.append(f"\n📝 <i>{html.escape(bio)}</i>")
        marriage = await get_marriage(uid, chat_id)
        if marriage:
            partner = await get_user(marriage["partner_id"])
            p_name = html.escape(partner["full_name"]) if partner else "?"
            lines.append(f"💍 Партнёр: {user_mention(marriage['partner_id'], p_name)}")
            received = await get_received_gifts(uid, chat_id)
            if received:
                gifts_str = ", ".join(
                    f"{g['gift_name']}×{g['cnt']}" if g["cnt"] > 1 else g["gift_name"]
                    for g in received
                )
                lines.append(f"🎁 Подарки: {gifts_str}")
        if theme["footer"]:
            lines.append(f"\n{theme['footer']}")

        if callback.message.chat.type == "private":
            miniapp_row = [
                InlineKeyboardButton(text="📱 Mini App", web_app=WebAppInfo(url=_MINI_APP_URL)),
                InlineKeyboardButton(
                    text="📋 История кошелька",
                    web_app=WebAppInfo(url=f"{_MINI_APP_URL}?open=wallet_history"),
                ),
            ]
        else:
            abs_cid = abs(callback.message.chat.id)
            miniapp_row = [
                InlineKeyboardButton(text="📱 Mini App", url=f"{_MINI_APP_TG_URL}?startapp={abs_cid}"),
                InlineKeyboardButton(text="📋 История кошелька", url=f"{_MINI_APP_TG_URL}?startapp={abs_cid}"),
            ]

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎨 Тема", callback_data=f"pn:themes:{uid}"),
                InlineKeyboardButton(text="🏅 Бейджи", callback_data=f"pn:badges:{uid}"),
            ],
            [
                InlineKeyboardButton(text="🏆 Топ чата", callback_data=f"top:{uid}:a"),
                InlineKeyboardButton(text="⭐ Репутация", callback_data=f"pn:rep:{uid}"),
            ],
            miniapp_row,
            [
                InlineKeyboardButton(text="❌ Закрыть", callback_data=f"pn:close:{uid}"),
            ],
        ])
        try:
            await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
        except Exception as _e:
            _log.debug("%s", _e)
    elif action == "themes":
        from config import PROFILE_THEMES, COSMETIC_TIER_LABELS
        chat_id = callback.message.chat.id
        if await not_your_button(callback, uid, "🚫 Не твоё меню."):
            return
        owned = {t["theme_key"] for t in await get_user_themes(uid, chat_id)}
        owned.add("default")
        active = await get_active_theme(uid, chat_id)
        lines = ["🎨 <b>Темы профиля</b>\n━━━━━━━━━━━━━━━━━━━━\n"]
        btns: list[list[InlineKeyboardButton]] = []
        row: list[InlineKeyboardButton] = []
        for key, info in PROFILE_THEMES.items():
            mark = " ✅" if key == active else (" 🔓" if key in owned else " 🔒")
            src = {"default": "бесплатно", "shop": f"{info['price']} 🪙", "gacha": "гача"}.get(info["source"], "")
            tier = COSMETIC_TIER_LABELS.get(info.get("tier", "common"), "")
            lines.append(f"{info['name']}{mark} [{tier}] — <i>{src}</i>")
            if key in owned:
                label = f"· {info['name']} ·" if key == active else info["name"]
                row.append(InlineKeyboardButton(text=label, callback_data=f"theme_set:{uid}:{key}"))
            elif info["source"] == "shop" and info["price"] > 0:
                row.append(InlineKeyboardButton(text=f"🛒 {info['name']}", callback_data=f"theme_buy:{uid}:{key}"))
            else:
                # gacha / locked — show as unclickable info button
                row.append(InlineKeyboardButton(text=f"🎲 {info['name']} 🔒", callback_data=f"theme_locked:{uid}:{key}"))
            if len(row) == 2:
                btns.append(row)
                row = []
        if row:
            btns.append(row)
        btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"pn:me:{uid}")])
        try:
            await callback.message.edit_text("\n".join(lines), parse_mode="HTML",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))
        except Exception as _e:
            _log.debug("%s", _e)
    elif action == "badges":
        from services.achievements import ACH_BY_KEY
        chat_id = callback.message.chat.id
        badge_keys = await get_user_badges(uid, chat_id)
        lines = ["🏅 <b>Бейджи</b>\n━━━━━━━━━━━━━━━━━━━━\n"]
        if badge_keys:
            for bk in badge_keys:
                bd = ACH_BY_KEY.get(bk)
                if bd:
                    lines.append(f"{bd['emoji']} <b>{bd['title']}</b> — <i>{bd['description']}</i>")
        else:
            lines.append("<i>Пока нет бейджей. Играй и зарабатывай!</i>")
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"pn:me:{uid}")],
        ])
        try:
            await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
        except Exception as _e:
            _log.debug("%s", _e)
    await callback.answer()


@router.message(BotCommand("айди", "id", "мой айди"))
async def cmd_id(message: Message, cmd_args: str):
    # Reply → use Telegram User object (has live username even if user not in DB)
    if message.reply_to_message and message.reply_to_message.from_user:
        tg = message.reply_to_message.from_user
        lines = [
            f"⁠👤 <b>Пользователь:</b> {html.escape(tg.full_name)}",
            f"🆆 ID: <code>{tg.id}</code>",
        ]
        if tg.username:
            lines.append(f"📛 @{tg.username}")
    elif cmd_args:
        # @username or numeric ID — look up in DB
        uid, name, _ = await resolve_target(message, cmd_args)
        if uid is None:
            await message.answer(
                "❌ Пользователь не найден в базе.\n"
                "ℹ️ Ответь на его сообщение или используй:\n"
                "<code>бот айди @username</code>",
                parse_mode="HTML",
            )
            return
        db_user = await get_user(uid)
        lines = [
            f"👤 <b>Пользователь:</b> {html.escape(name)}",
            f"🆆 ID: <code>{uid}</code>",
        ]
        if db_user and db_user["username"]:
            lines.append(f"📛 @{db_user['username']}")
    else:
        # No args, no reply — show own info
        tg = message.from_user
        lines = [
            f"👤 <b>Пользователь:</b> {html.escape(tg.full_name)}",
            f"🆆 ID: <code>{tg.id}</code>",
        ]
        if tg.username:
            lines.append(f"📛 @{tg.username}")

    if message.chat.type in ("group", "supergroup"):
        lines.append(f"\n💬 <b>Чат:</b> {html.escape(message.chat.title or '')}   ID: <code>{message.chat.id}</code>")
        if message.chat.username:
            lines.append(f"@{message.chat.username}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(BotCommand("чатинфо", "чат", "chatinfo"))
async def cmd_chatinfo(message: Message, cmd_args: str):
    """Show detailed info about the current chat."""
    chat = message.chat
    lines = [
        "💬 <b>Информация о чате</b>\n",
        f"🏷 Название: {html.escape(getattr(chat, 'title', '') or getattr(chat, 'full_name', ''))}",
        f"🆔 Chat ID: <code>{chat.id}</code>",
        f"📌 Тип: {chat.type}",
    ]
    if getattr(chat, "username", None):
        lines.append(f"📛 @{chat.username}")
    if chat.type in ("group", "supergroup"):
        lines.append(
            f"\n<i>Добавить в белый список: <code>бот разрешить {chat.id}</code></i>"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(BotCommand("время", "time", "timezone"))
async def cmd_time(message: Message, cmd_args: str):
    query = cmd_args.strip().lower() if cmd_args else ""
    if query:
        tz_name = _TZ_MAP.get(query)
        if not tz_name:
            known = ", ".join(sorted({k for k in _TZ_MAP if not k.isascii() or len(k) > 3})[:15])
            await message.answer(
                f"❌ Не знаю такой город.\n"
                f"Примеры: <code>бот время москва</code>, <code>бот время цюрих</code>, <code>бот время токио</code>\n"
                f"Доступные: {known}...",
                parse_mode="HTML",
            )
            return
        now = datetime.now(ZoneInfo(tz_name))
        await message.answer(
            f"🕐 <b>{cmd_args.strip().capitalize()}</b>: "
            f"<b>{now.strftime('%H:%M')}</b>  ({now.strftime('%d.%m.%Y')})",
            parse_mode="HTML",
        )
    else:
        lines = ["🌍 <b>Время в разных городах:</b>\n"]
        for label, tz_name in _DEFAULT_TZ_LIST:
            now = datetime.now(ZoneInfo(tz_name))
            lines.append(f"{label}: <b>{now.strftime('%H:%M')}</b>")
        lines.append("\n<i><code>бот время [город]</code> — конкретный город</i>")
        await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(BotCommand("я", "профиль", "me", "мой профиль"))
async def cmd_me(message: Message, cmd_args: str):
    from config import DEVELOPER_ID, PROFILE_THEMES, MAX_WARNS
    from services.achievements import ACH_BY_KEY
    from handlers.economy import TOP_FRAMES, _frame_emoji
    from database.db import xp_for_level, get_active_buffs, get_user_community_roles, get_user_talents
    from shared_prices import TALENT_TREE

    uid = message.from_user.id
    chat_id = message.chat.id
    is_group = message.chat.type in ("group", "supergroup")

    user = await get_user(uid)
    if not user:
        await message.answer("❌ Тебя ещё нет в базе. Напиши любое сообщение в чат.")
        return

    stats = await get_user_stats(uid, chat_id)
    rank    = stats["rank"]          if stats else "user"
    if DEVELOPER_ID and uid == DEVELOPER_ID:
        rank = "developer"
    warns_n  = (stats["warns"]         or 0) if stats else 0
    xp       = (stats["xp"]            or 0) if stats else 0
    lvl_val  = (stats["level"]         or 1) if stats else 1
    rep      = (stats["reputation"]    or 0) if stats else 0
    msgs     = (stats["message_count"] or 0) if stats else 0
    bio      = stats["bio"]            if stats else None
    banned   = (stats["is_banned"]     or 0) if stats else 0
    title    = stats["custom_title"]   if stats else None

    mora_row     = await get_mora(uid, chat_id) if is_group else None
    vip          = (mora_row["vip"]     or 0)   if mora_row else 0
    mora_bal     = (mora_row["balance"] or 0)   if mora_row else 0
    frame_key    = mora_row["top_frame"]         if mora_row else None
    boost_active = await get_xp_boost_active(uid, chat_id) if is_group else False

    # Crystals balance (global, all contexts)
    crystals = await get_crystals(uid)

    # Theme
    theme_key = await get_active_theme(uid, chat_id) if is_group else "default"
    theme     = PROFILE_THEMES.get(theme_key, PROFILE_THEMES["default"])

    # Badges
    badge_keys = await get_user_badges(uid, chat_id) if is_group else []
    badges_str = " ".join(
        ACH_BY_KEY[bk]["emoji"] for bk in badge_keys if bk in ACH_BY_KEY
    )

    # Equipped legendary
    equipped = await get_all_equipped_items(uid, chat_id) if is_group else []

    # ── XP progress bar ───────────────────────────────────────────────────
    lvl_xp   = xp_for_level(lvl_val)
    next_xp  = xp_for_level(lvl_val + 1)
    span     = max(1, next_xp - lvl_xp)
    progress = max(0, min(xp - lvl_xp, span))
    pct      = int(progress / span * 100)
    bar_w    = 12
    filled   = max(0, min(bar_w, round(progress / span * bar_w)))
    xp_bar   = f"[{'█' * filled}{'░' * (bar_w - filled)}] {pct}%  ({xp}/{next_xp} XP)"

    vip_tag = " 💎" if vip else ""
    sep     = theme["separator"]

    # ── Сборка профиля — блочная структура ───────────────────────────────
    lines: list[str] = []

    # ── Блок 1: Шапка (тема + имя + ранг + дата) ─────────────────────────
    lines.append(f"{theme['header']}{vip_tag}")
    lines.append(sep)
    if badges_str:
        lines.append(f"🏅 {badges_str}")
    lines.append(f"🏷 <b>{html.escape(user['full_name'])}</b>")
    lines.append(f"🎖 {rank_name(rank, title)}")
    # Registration date
    first_seen = user.get("first_seen") if user else None
    if first_seen:
        try:
            fs_dt = first_seen if isinstance(first_seen, datetime) else datetime.fromisoformat(str(first_seen))
            lines.append(f"📅 В чате с: {fs_dt.strftime('%d.%m.%Y')}")
        except Exception:
            pass

    # ── Блок 2: Прогресс ─────────────────────────────────────────────────
    lines.append("")
    lines.append(sep)
    lines.append(f"🌟 <b>Уровень {lvl_val}</b>")
    lines.append(f"   {xp_bar}")
    lines.append(f"⭐ Репутация: <b>{rep:+d}</b>   │   💬 Сообщений: <b>{msgs:,}</b>")

    # ── Блок 3: Ресурсы ───────────────────────────────────────────────────
    lines.append("")
    lines.append(sep)
    res_parts: list[str] = []
    if is_group:
        res_parts.append(f"🪙 Мора: <b>{mora_bal:,}</b>")
    res_parts.append(f"💎 Кристаллы: <b>{crystals:,}</b>")
    lines.append("   ".join(res_parts))

    cosmetics: list[str] = []
    if vip:
        cosmetics.append("💎 VIP")
    if boost_active:
        cosmetics.append("⚡ XP ×2 активен")
    if cosmetics:
        lines.append("   ".join(cosmetics))
    if frame_key:
        frame_label = next((f[2] for f in TOP_FRAMES if f[0] == frame_key), None)
        if frame_label:
            lines.append(f"🖼 Рамка: {_frame_emoji(frame_key)} {frame_label}")
    if theme_key != "default":
        from config import COSMETIC_TIER_LABELS
        tier_label = COSMETIC_TIER_LABELS.get(theme.get("tier", "common"), "")
        lines.append(f"🎨 Тема: {theme['name']} [{tier_label}]")
    if equipped:
        equip_str = "  ".join(
            f"{i['emoji']} {i['item_name']}" + (f" +{i['enhancement_level']}" if i['enhancement_level'] else "")
            for i in equipped
        )
        lines.append(f"⚔️ Снаряжение: {equip_str}")

    # ── Блок 4: Отношения ─────────────────────────────────────────────────
    if is_group:
        marriage = await get_marriage(uid, chat_id)
        if marriage:
            partner = await get_user(marriage["partner_id"])
            p_name = html.escape(partner["full_name"]) if partner else "?"
            # Days together
            married_at = marriage.get("married_at")
            days_str = ""
            if married_at:
                try:
                    m_dt = married_at if isinstance(married_at, datetime) else datetime.fromisoformat(str(married_at))
                    if m_dt.tzinfo is None:
                        m_dt = m_dt.replace(tzinfo=timezone.utc)
                    days_together = (datetime.now(timezone.utc) - m_dt).days
                    days_str = f"  <i>({days_together} дн. вместе)</i>"
                except Exception:
                    pass
            lines.append("")
            lines.append(sep)
            lines.append(f"💍 Партнёр: {user_mention(marriage['partner_id'], p_name)}{days_str}")
            received = await get_received_gifts(uid, chat_id)
            if received:
                gifts_str = ", ".join(
                    f"{g['gift_name']}×{g['cnt']}" if g["cnt"] > 1 else g["gift_name"]
                    for g in received
                )
                lines.append(f"🎁 Подарки: {gifts_str}")

    # ── Блок 5: Питомец ───────────────────────────────────────────────────
    if is_group:
        pet_row = await get_pet(uid, chat_id)
        if pet_row:
            pet_emoji  = {"cat": "🐱", "dog": "🐶"}.get(pet_row.get("pet_type") or "", "🐾")
            pet_name   = pet_row.get("name") or "Питомец"
            fatigue    = pet_row.get("fatigue") or 0
            lines.append("")
            lines.append(sep)
            lines.append(f"🐾 <b>ПИТОМЕЦ</b>")
            lines.append(f"{pet_emoji} {html.escape(pet_name)}   │   Усталость: {fatigue}/100")
            # Walk status
            walk_end = pet_row.get("walk_end_at")
            if walk_end:
                try:
                    w_dt = walk_end if isinstance(walk_end, datetime) else datetime.fromisoformat(str(walk_end))
                    if w_dt.tzinfo is None:
                        w_dt = w_dt.replace(tzinfo=timezone.utc)
                    w_mins = int((w_dt - datetime.now(timezone.utc)).total_seconds() / 60)
                    if w_mins > 0:
                        wh, wm = w_mins // 60, w_mins % 60
                        lines.append(f"  🚶 На прогулке  ⏱ осталось {wh}ч {wm}м" if wh else f"  🚶 На прогулке  ⏱ осталось {wm}м")
                except Exception as _e:
                    _log.debug("%s", _e)
            else:
                # Check expedition
                try:
                    exp = await get_active_expedition(uid, chat_id)
                    if exp:
                        from datetime import timedelta
                        started = exp["started_at"]
                        if isinstance(started, str):
                            started = datetime.fromisoformat(started)
                        if started.tzinfo is None:
                            started = started.replace(tzinfo=timezone.utc)
                        end_dt   = started + timedelta(hours=exp["duration_h"])
                        exp_mins = int((end_dt - datetime.now(timezone.utc)).total_seconds() / 60)
                        if exp_mins > 0:
                            eh, em = exp_mins // 60, exp_mins % 60
                            lines.append(f"  🧭 На экспедиции  ⏱ осталось {eh}ч {em}м" if eh else f"  🧭 На экспедиции  ⏱ осталось {em}м")
                    else:
                        lines.append("  😴 Отдыхает дома")
                except Exception as _e:
                    _log.debug("%s", _e)
                    lines.append("  😴 Отдыхает дома")

    # ── Блок 6: Активные баффы ────────────────────────────────────────────
    if is_group:
        _BUFF_MAP = {
            "atk":           ("⚔️", "ATK",    "+15"),
            "def":           ("🛡️", "DEF",    "+20"),
            "hp":            ("❤️", "HP",      "+50"),
            "mora_boost_10": ("🪙", "Мора",   "+10%"),
            "mora_boost_15": ("🪙", "Мора",   "+15%"),
            "mora_boost_20": ("🪙", "Мора",   "+20%"),
        }
        try:
            active_buffs = await get_active_buffs(uid, chat_id)
            if active_buffs:
                now_utc = datetime.now(timezone.utc)
                lines.append("")
                lines.append(sep)
                lines.append("💫 <b>АКТИВНЫЕ ЭФФЕКТЫ</b>")
                buff_parts: list[str] = []
                for buff in active_buffs:
                    btype = buff.get("buff_type") or buff.get("type", "")
                    exp   = buff.get("expires_at")
                    mins_left = 0
                    if exp:
                        try:
                            exp_dt = exp if hasattr(exp, "tzinfo") else datetime.fromisoformat(str(exp))
                            if exp_dt.tzinfo is None:
                                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                            mins_left = max(0, int((exp_dt - now_utc).total_seconds() / 60))
                        except Exception as _e:
                            _log.debug("%s", _e)
                    em, lab, val = _BUFF_MAP.get(btype, ("✨", btype, ""))
                    t_str = f"{mins_left // 60}ч {mins_left % 60}м" if mins_left >= 60 else f"{mins_left}м"
                    buff_parts.append(f"  {em} {lab}: <b>{val}</b>  ⏱ {t_str}")
                lines.extend(buff_parts)
        except Exception as _e:
            _log.debug("%s", _e)

    # ── Блок 7: Таланты ───────────────────────────────────────────────────
    if is_group:
        try:
            tal_data  = await get_user_talents(uid)
            _invested = tal_data.get("talents", {})
            _tp_left  = tal_data.get("talent_points", 0)
            _TLABELS  = {
                "mora_drop_chance":     ("🌾", "Мора +{v}%"),
                "drop_luck_pct":        ("🍀", "Удача +{v}%"),
                "atk_bonus":            ("⚔️", "ATK +{v}"),
                "expedition_cd_minutes":("🗺️", "Экспед. −{v}м"),
                "rep_cd_hours":         ("⭐", "Репа КД −{v}ч"),
                "free_potion_chance":   ("🧪", "Зелье +{v}%"),
                "gacha_pity_reduction": ("🎴", "Пити −{v}"),
                "expedition_reward_pct":("💰", "Экспед. +{v}%"),
                "bonds_profit_pct":     ("📈", "Биржа +{v}%"),
                "craft_shard_discount": ("⚒️", "Крафт −{v}шрд"),
                "gacha_shard_bonus":    ("💎", "Гача +{v}шрд"),
            }
            effect_totals: dict[str, int] = {}
            for tid_k, t_info in TALENT_TREE.items():
                t_lvl = _invested.get(tid_k, 0)
                if t_lvl > 0:
                    ek = t_info["effect_key"]
                    effect_totals[ek] = effect_totals.get(ek, 0) + t_lvl * t_info["effect_per_level"]
            talent_parts = []
            for ek, total in effect_totals.items():
                if ek == "shield_renewal":
                    continue
                tmpl = _TLABELS.get(ek)
                if tmpl:
                    talent_parts.append(f"{tmpl[0]} {tmpl[1].format(v=total)}")
            if talent_parts or _tp_left > 0:
                lines.append("")
                lines.append(sep)
                tp_note = f"  <i>({_tp_left} оч. доступно)</i>" if _tp_left > 0 else ""
                lines.append(f"🎯 <b>ТАЛАНТЫ</b>{tp_note}")
                if talent_parts:
                    # compact: two per line
                    for i in range(0, len(talent_parts), 2):
                        chunk = talent_parts[i:i + 2]
                        lines.append("  " + "   ".join(chunk))
                else:
                    lines.append("  <i>Таланты не прокачаны — открой Mini App</i>")
        except Exception as _e:
            _log.debug("%s", _e)

    # ── Блок 8: Статус и Варны ────────────────────────────────────────────
    lines.append("")
    lines.append(sep)

    # Newbie shield
    if is_group and stats:
        _shield_until = stats.get("newbie_shield_until")
        if _shield_until:
            try:
                _su = _shield_until if hasattr(_shield_until, "tzinfo") else datetime.fromisoformat(str(_shield_until))
                if _su.tzinfo is None:
                    _su = _su.replace(tzinfo=timezone.utc)
                if _su > datetime.now(timezone.utc):
                    _delta = _su - datetime.now(timezone.utc)
                    lines.append(f"🛡 Щит новичка: ещё {_delta.days}д {_delta.seconds // 3600}ч")
            except Exception:
                pass

    # Community roles
    if is_group:
        try:
            c_roles = await get_user_community_roles(uid)
            if c_roles:
                roles_str = "  ".join(
                    f"{r.get('emoji', '')} {html.escape(r['name'])}".strip()
                    for r in c_roles
                )
                lines.append(f"🎭 Роль: {roles_str}")
        except Exception as _e:
            _log.debug("%s", _e)

    status     = "🔴 Заблокирован" if banned else "🟢 Активен"
    warn_icons = "⚠️" * min(warns_n, MAX_WARNS)
    warn_str   = f"{warn_icons}  {warns_n}/{MAX_WARNS}" if warns_n else f"0/{MAX_WARNS}"
    lines.append(f"⚠️ Варны: {warn_str}   │   📊 {status}")

    if bio:
        lines.append(f"\n📝 <i>{html.escape(bio)}</i>")

    if theme["footer"]:
        lines.append(f"\n{theme['footer']}")

    # ── Inline-кнопки навигации ───────────────────────────────────────────
    if message.chat.type == "private":
        miniapp_row = [
            InlineKeyboardButton(text="📱 Mini App", web_app=WebAppInfo(url=_MINI_APP_URL)),
            InlineKeyboardButton(
                text="📋 История кошелька",
                web_app=WebAppInfo(url=f"{_MINI_APP_URL}?open=wallet_history"),
            ),
        ]
    else:
        abs_cid = abs(chat_id)
        miniapp_row = [
            InlineKeyboardButton(text="📱 Mini App", url=f"{_MINI_APP_TG_URL}?startapp={abs_cid}"),
            InlineKeyboardButton(text="📋 История кошелька", url=f"{_MINI_APP_TG_URL}?startapp={abs_cid}"),
        ]

    me_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎨 Тема", callback_data=f"pn:themes:{uid}"),
            InlineKeyboardButton(text="🏅 Бейджи", callback_data=f"pn:badges:{uid}"),
        ],
        [
            InlineKeyboardButton(text="🏆 Топ чата", callback_data=f"top:{uid}:a"),
            InlineKeyboardButton(text="⭐ Репутация", callback_data=f"pn:rep:{uid}"),
        ],
        [
            InlineKeyboardButton(text="🌟 Уровень & XP", callback_data=f"pn:lvl:{uid}"),
            InlineKeyboardButton(text="🎯 Таланты", url=f"{_MINI_APP_TG_URL}?startapp={abs(chat_id)}" if is_group else _MINI_APP_URL),
        ],
        miniapp_row,
        [
            InlineKeyboardButton(text="❌ Закрыть", callback_data=f"pn:close:{uid}"),
        ],
    ])
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=me_kb)


@router.message(BotCommand("тема", "темы", "theme"))
async def cmd_themes(message: Message, cmd_args: str):
    """Показать доступные темы профиля как Inline-меню."""
    from config import PROFILE_THEMES, COSMETIC_TIER_LABELS
    uid = message.from_user.id
    chat_id = message.chat.id
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("ℹ️ Темы доступны только в групповых чатах.")
        return

    owned = {t["theme_key"] for t in await get_user_themes(uid, chat_id)}
    owned.add("default")
    active = await get_active_theme(uid, chat_id)

    lines = ["🎨 <b>Темы профиля</b>\n━━━━━━━━━━━━━━━━━━━━\n"]
    btns: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for key, info in PROFILE_THEMES.items():
        mark = " ✅" if key == active else (" 🔓" if key in owned else " 🔒")
        src = {"default": "бесплатно", "shop": f"{info['price']} 🪙", "gacha": "гача"}.get(info["source"], "")
        tier = COSMETIC_TIER_LABELS.get(info.get("tier", "common"), "")
        lines.append(f"{info['name']}{mark} [{tier}] — <i>{src}</i>")
        if key in owned:
            label = f"· {info['name']} ·" if key == active else info["name"]
            row.append(InlineKeyboardButton(
                text=label, callback_data=f"theme_set:{uid}:{key}",
            ))
        elif info["source"] == "shop" and info["price"] > 0:
            row.append(InlineKeyboardButton(
                text=f"🛒 {info['name']}", callback_data=f"theme_buy:{uid}:{key}",
            ))
        else:
            row.append(InlineKeyboardButton(
                text=f"🎲 {info['name']} 🔒", callback_data=f"theme_locked:{uid}:{key}",
            ))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    btns.append([InlineKeyboardButton(text="❌ Закрыть", callback_data=f"pn:close:{uid}")])
    await message.answer("\n".join(lines), parse_mode="HTML",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))


@router.callback_query(F.data.startswith("theme_set:"))
async def cb_theme_set(callback: CallbackQuery):
    parts = callback.data.split(":")
    uid, key = int(parts[1]), parts[2]
    if await not_your_button(callback, uid, "🚫 Не твоё меню."):
        return
    await set_active_theme(uid, callback.message.chat.id, key)
    await callback.answer(f"✅ Тема «{key}» активирована!")
    try:
        await callback.message.delete()
    except Exception as _e:
        _log.debug("%s", _e)
@router.callback_query(F.data.startswith("theme_buy:"))
async def cb_theme_buy(callback: CallbackQuery):
    from config import PROFILE_THEMES
    parts = callback.data.split(":")
    uid, key = int(parts[1]), parts[2]
    if await not_your_button(callback, uid, "🚫 Не твоё меню."):
        return
    theme = PROFILE_THEMES.get(key)
    if not theme or theme["source"] != "shop":
        await callback.answer("❌ Тема недоступна.", show_alert=True)
        return
    chat_id = callback.message.chat.id
    mora_row = await get_mora(uid, chat_id)
    bal = (mora_row["balance"] or 0) if mora_row else 0
    price = theme["price"]
    if bal < price:
        await callback.answer(f"❌ Не хватает моры ({bal}/{price}).", show_alert=True)
        return
    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (price, uid, price),
        )
        if cursor.rowcount == 0:
            await callback.answer("❌ Не удалось списать Мору.", show_alert=True)
            return
        await db.commit()
        async with db.execute(
            "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=?",
            (uid,),
        ) as c:
            row = await c.fetchone()
        new_bal = row[0] if row else 0
    await add_user_theme(uid, chat_id, key, "shop")
    await set_active_theme(uid, chat_id, key)
    await callback.answer(f"✅ Тема «{theme['name']}» куплена и активирована!")
    try:
        await callback.message.delete()
    except Exception as _e:
        _log.debug("%s", _e)
@router.callback_query(F.data.startswith("theme_locked:"))
async def cb_theme_locked(callback: CallbackQuery):
    parts = callback.data.split(":")
    uid, key = int(parts[1]), parts[2]
    from config import PROFILE_THEMES
    info = PROFILE_THEMES.get(key, {})
    tier = info.get("tier", "")
    await callback.answer(
        f"🎲 Тема «{info.get('name', key)}» ({tier}) выдаётся из гачи!\n"
        f"Попробуй «бот молитва» — вдруг повезёт 🍀",
        show_alert=True,
    )


@router.message(BotCommand("инфо", "info"))
async def cmd_info(message: Message, cmd_args: str):
    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        uid = message.from_user.id
    user = await get_user(uid)

    if not user:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "ℹ️ Ответь на сообщение или укажи:\n"
            "<code>бот инфо @username</code>",
            parse_mode="HTML",
        )
        return

    stats = await get_user_stats(uid, message.chat.id)
    rank  = stats["rank"]           if stats else "user"
    rep   = stats["reputation"]     if stats else 0
    lvl   = stats["level"]          if stats else 1
    xp    = stats["xp"]             if stats else 0
    msgs  = stats["message_count"]  if stats else 0
    bio   = stats["bio"]            if stats else None
    title = stats["custom_title"]   if stats else None

    from config import DEVELOPER_ID
    if DEVELOPER_ID and uid == DEVELOPER_ID:
        rank = "developer"
    from database.db import xp_for_level
    next_xp = xp_for_level(lvl + 1)
    bar_filled = min(10, int((xp - xp_for_level(lvl)) / max(1, next_xp - xp_for_level(lvl)) * 10))
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    lines = [
        f"ℹ️ <b>{user_mention(user['user_id'], user['full_name'])}</b>\n",
        f"🎖 Ранг: {rank_name(rank, title)}",
        f"🌟 Уровень: <b>{lvl}</b>  [{bar}]  {xp}/{next_xp} XP",
        f"⭐ Репутация: <b>{rep:+d}</b>",
        f"💬 Сообщений: {msgs}",
    ]
    if bio:
        lines.append(f"\n📝 <i>{html.escape(bio)}</i>")

    # Брак
    if message.chat.type in ("group", "supergroup"):
        marriage = await get_marriage(uid, message.chat.id)
        if marriage:
            partner = await get_user(marriage["partner_id"])
            partner_name = html.escape(partner["full_name"]) if partner else "?"
            lines.append(f"💍 Партнёр: {user_mention(marriage['partner_id'], partner_name)}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(BotCommand("кто", "досье", "анкета", "whois"))
async def cmd_whois(message: Message, cmd_args: str):
    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(name)
        return

    user = await get_user(uid)
    if not user:
        # Пользователь ещё не регистрировался в боте — показываем то, что есть
        if message.reply_to_message and message.reply_to_message.from_user:
            t = message.reply_to_message.from_user
            await message.answer(
                f"👤 Имя: {html.escape(t.full_name or '')}\n"
                f"🆔 ID: <code>{t.id}</code>\n"
                f"📛 {'@' + t.username if t.username else 'скрыт'}\n"
                f"📊 В базе: нет (ни одного сообщения ещё не записано)",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                "❌ Пользователь не найден.\n"
                "ℹ️ Ответь на сообщение или укажи:\n"
                "<code>бот кто @username</code>",
                parse_mode="HTML",
            )
        return

    from config import MAX_WARNS
    stats = await get_user_stats(uid, message.chat.id)
    rank    = stats["rank"]       if stats else "user"
    title   = stats["custom_title"] if stats else None
    warns_n = stats["warns"]      if stats else 0
    rep     = stats["reputation"] if stats else 0
    xp      = stats["xp"]        if stats else 0
    lvl     = stats["level"]      if stats else 1
    msgs    = stats["message_count"] if stats else 0
    banned  = stats["is_banned"]  if stats else 0
    bio     = stats["bio"]        if stats else None

    from config import DEVELOPER_ID
    if DEVELOPER_ID and uid == DEVELOPER_ID:
        rank = "developer"

    is_group_w = message.chat.type in ("group", "supergroup")
    status = "🔴 Заблокирован" if banned else "🟢 Активен"
    warns_line = f"{warns_n}/{MAX_WARNS}" if warns_n else "нет"

    from database.db import xp_for_level
    from config import PROFILE_THEMES
    from handlers.economy import TOP_FRAMES, _frame_emoji
    next_xp = xp_for_level(lvl + 1)
    mora_row_t = await get_mora(uid, message.chat.id) if is_group_w else None
    frame_key_t = mora_row_t["top_frame"] if mora_row_t else None
    vip_t = (mora_row_t["vip"] or 0) if mora_row_t else 0
    theme_key_t = await get_active_theme(uid, message.chat.id) if is_group_w else "default"
    theme_t = PROFILE_THEMES.get(theme_key_t, PROFILE_THEMES["default"])
    equipped_t = await get_all_equipped_items(uid, message.chat.id) if is_group_w else []
    sep_t = theme_t["separator"]
    vip_tag_t = " 💎" if vip_t else ""

    from utils.flood import get_trust_level
    _trust = get_trust_level(msgs)
    _trust_badge = {"newcomer": "🆕 Новичок (&lt;300)", "regular": "👤 Обычный", "trusted": "⭐ Доверенный (&gt;1000)"}.get(_trust, "👤")

    lines = [
        f"{theme_t['header']}{vip_tag_t}",
        sep_t,
        "",
        f"🔍 <b>Досье</b>",
        f"🏷 Имя: {user_mention(user['user_id'], user['full_name'] or str(user['user_id']))}",
        f"📛 Username: @{user['username'] or 'скрыт'}",
        f"🆔 ID: <code>{user['user_id']}</code>",
        f"🎖 Ранг: {rank_name(rank, title)}",
        f"💬 Сообщений: {msgs}",
        f"🔐 Уровень доверия: {_trust_badge}",
        f"⭐ Репутация: <b>{rep:+d}</b>",
        f"🌟 Уровень: <b>{lvl}</b>  |  {xp}/{next_xp} XP",
        f"⚠️ Предупреждения: {warns_line}",
        f"📊 Статус: {status}",
        f"🟢 Первая активность: {_fmt_dt(stats['first_active'] if stats else None)}",
        f"🔵 Последняя активность: {_fmt_dt(stats['last_active'] if stats else None)}",
    ]

    # Activity breakdown (today / week / all-time)
    if is_group_w:
        from database.db import get_user_activity
        act = await get_user_activity(uid, message.chat.id)
        lines.append("")
        lines.append(f"📈 <b>Активность</b>")
        lines.append(f"   Сегодня: <b>{act['today']}</b>  |  Неделя: <b>{act['week']}</b>  |  Всего: <b>{act['total']}</b>")
    if bio:
        lines.append(f"\n📝 Bio: <i>{html.escape(bio)}</i>")

    # Брак
    if is_group_w:
        marriage = await get_marriage(uid, message.chat.id)
        if marriage:
            partner = await get_user(marriage["partner_id"])
            partner_name = html.escape(partner["full_name"]) if partner else "?"
            lines.append(f"💍 Партнёр: {user_mention(marriage['partner_id'], partner_name)}")

    if equipped_t:
        equip_str_t = "  ".join(
            f"{i['emoji']} {i['item_name']}" + (f" +{i['enhancement_level']}" if i['enhancement_level'] else "")
            for i in equipped_t
        )
        lines.append(f"⚔️ Экипировка: {equip_str_t}")
    if frame_key_t:
        frame_label_t = next((f[2] for f in TOP_FRAMES if f[0] == frame_key_t), None)
        if frame_label_t:
            lines.append(f"🖼️ Рамка: {_frame_emoji(frame_key_t)} {frame_label_t}")
    if theme_key_t != "default":
        from config import COSMETIC_TIER_LABELS
        tier_label_t = COSMETIC_TIER_LABELS.get(theme_t.get("tier", "common"), "")
        lines.append(f"🎨 Тема: {theme_t['name']} [{tier_label_t}]")
    if theme_t["footer"]:
        lines.append(f"\n{theme_t['footer']}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(BotCommand("топ", "top", "активность"))
async def cmd_top(message: Message, cmd_args: str):
    arg = (cmd_args or "").strip().lower()

    prev_top: list = []
    if arg in ("день", "day", "д"):
        top = await get_daily_top(message.chat.id, 500)
        prev_top = await get_yesterday_top(message.chat.id, 500)
        title = "📅 <b>Рейтинг активных за сегодня:</b>"
        count_field = "dc"
    elif arg in ("неделя", "week", "н"):
        top = await get_weekly_top(message.chat.id, 500)
        prev_top = await get_prev_weekly_top(message.chat.id, 500)
        title = "📆 <b>Рейтинг активных за неделю:</b>"
        count_field = "wc"
    else:
        top = await get_top_by_messages_in_chat(message.chat.id, 500)
        title = "🏆 <b>Рейтинг активных за всё время:</b>"
        count_field = "message_count"

    if not top:
        await message.answer("📊 Статистика пока пуста.")
        return

    period_code = "d" if arg in ("день", "day", "д") else ("w" if arg in ("неделя", "week", "н") else "a")
    uid_list = [u["user_id"] for u in top if "user_id" in u.keys()]
    mora_map = await get_mora_batch(uid_list, message.chat.id)
    # Load Hall of Fame for weekly/all-time views
    hof_data = None
    if count_field in ("wc", "message_count"):
        from zoneinfo import ZoneInfo as _ZI
        from datetime import datetime as _dt, timedelta as _td
        _now = _dt.now(_ZI("Europe/Zurich"))
        _prev_iso = (_now - _td(days=7)).isocalendar()
        _prev_key = f"{_prev_iso.year}-W{_prev_iso.week:02d}"
        hof_data = await get_weekly_top_reward_history(message.chat.id, _prev_key)
    text = _build_top_text(top, prev_top, mora_map, title, count_field, message.from_user.id,
                           chat_id=message.chat.id, hof_data=hof_data)
    await _send_long_html(message, text, reply_markup=_top_keyboard(period_code, message.from_user.id))


@router.message(BotCommand("правила", "rules"))
async def cmd_rules(message: Message, cmd_args: str):
    # Эта команда перехватывается admin.py если аргумент "установить"
    # Здесь просто показываем правила
    from database.db import get_chat_settings
    settings = await get_chat_settings(message.chat.id)
    if settings and settings["rules_text"]:
        await message.answer(
            f"📜 <b>Правила чата:</b>\n\n{settings['rules_text']}",
            parse_mode="HTML",
        )
    else:
        await message.answer("📜 Правила чата ещё не установлены.")


@router.message(BotCommand("жалоба", "репорт", "report"))
async def cmd_report(message: Message, bot: Bot, cmd_args: str):
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        target_id, target_name = target.id, target.full_name
        reason = cmd_args or "не указана"
        msg_id = message.reply_to_message.message_id
    elif cmd_args:
        parts = cmd_args.split(maxsplit=1)
        uid, name, remaining = await resolve_target(message, parts[0])
        if uid is None:
            await message.answer(
                "❌ Пользователь не найден.\n"
                "Пример: <code>бот репорт @username причина</code>\n"
                "или ответь на сообщение нарушителя.",
                parse_mode="HTML",
            )
            return
        target_id, target_name = uid, name
        reason = remaining or (parts[1] if len(parts) > 1 else "не указана")
        msg_id = None
    else:
        await message.answer(
            "❌ Укажи на кого жалоба.\n"
            "Пример: <code>бот репорт @username причина</code>\n"
            "или ответь на сообщение нарушителя.",
            parse_mode="HTML",
        )
        return

    reporter = message.from_user
    chat_title = html.escape(getattr(message.chat, "title", None) or str(message.chat.id))

    # Build a working deep-link to the reported message
    link_part = ""
    if msg_id:
        chat_username = getattr(message.chat, "username", None)
        if chat_username:
            msg_link = f"https://t.me/{chat_username}/{msg_id}"
        else:
            bare_id = str(message.chat.id).removeprefix("-100")
            msg_link = f"https://t.me/c/{bare_id}/{msg_id}"
        link_part = f"\n\n🔗 <a href=\"{msg_link}\">Перейти к сообщению</a>"

    notify_text = (
        f"🚨 <b>Репорт в {chat_title}</b>\n\n"
        f"👤 Жалуется: {user_mention(reporter.id, reporter.full_name)}\n"
        f"👤 На кого: {user_mention(target_id, target_name)}\n"
        f"📝 Причина: {html.escape(reason)}"
        f"{link_part}"
    )

    from utils.helpers import notify_admins
    await notify_admins(bot, notify_text, source_chat_id=message.chat.id)

    # Удаляем сообщение из чата — никакого публичного следа
    try:
        await message.delete()
    except Exception as _e:
        _log.debug("%s", _e)
    # Уведомляем репортёра в ЛС (тихо — никто в чате не видит)
    try:
        await bot.send_message(
            reporter.id,
            "✅ Жалоба отправлена администрации анонимно. "
            "Администраторы рассмотрят её в ближайшее время.",
        )
    except Exception:
        pass  # пользователь не начал диалог с ботом — ничего страшного


# ─── Наши ссылки ─────────────────────────────────────────────────────────────

@router.message(BotCommand("наши ссылки", "нашиссылки", "ссылки", "links", "социалки"))
async def cmd_our_links(message: Message):
    from database.db import get_chat_settings
    from config import (
        TIKTOK_URL, TIKTOK_LABEL, YOUTUBE_URL, YOUTUBE_LABEL,
        INSTAGRAM_URL, INSTAGRAM_LABEL,
    )

    settings = await get_chat_settings(message.chat.id)
    s = dict(settings) if settings else {}

    links: list[tuple[str, str]] = []
    # Приоритет: персональная ссылка чата > глобальная из конфига
    tt = s.get("social_tiktok") or TIKTOK_URL
    yt = s.get("social_youtube") or YOUTUBE_URL
    ig = s.get("social_instagram") or INSTAGRAM_URL

    if tt:
        links.append((TIKTOK_LABEL, tt))
    if yt:
        links.append((YOUTUBE_LABEL, yt))
    if ig:
        links.append((INSTAGRAM_LABEL, ig))

    if not links:
        await message.answer("🔗 Ссылки пока не настроены.")
        return

    buttons = [
        [InlineKeyboardButton(text=label, url=url)]
        for label, url in links
    ]
    await message.answer(
        "🔗 <b>Наши ссылки:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.message(BotCommand("автор", "создатель", "creator", "разработчик бота"))
async def cmd_creator(message: Message, bot: Bot, cmd_args: str):
    """Показать информацию о создателе бота."""
    from config import DEVELOPER_ID
    from database.db import xp_for_level

    try:
        chat = await bot.get_chat(DEVELOPER_ID)
        first = chat.first_name or ""
        last = chat.last_name or ""
        full_name = html.escape(f"{first} {last}".strip() or "Разработчик")
        username = chat.username or ""
        bio_tg = html.escape(getattr(chat, "bio", None) or "")
    except Exception:
        full_name = "Разработчик"
        username = ""
        bio_tg = ""

    stats = await get_user_stats(DEVELOPER_ID, message.chat.id)
    rep  = stats["reputation"]    if stats else 0
    lvl  = stats["level"]         if stats else 1
    xp   = stats["xp"]            if stats else 0
    msgs = stats["message_count"] if stats else 0
    bio_db = html.escape(stats["bio"] or "") if stats else ""

    next_xp = xp_for_level(lvl + 1)
    bar_filled = min(10, int((xp - xp_for_level(lvl)) / max(1, next_xp - xp_for_level(lvl)) * 10))
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    contact = f'<a href="tg://user?id={DEVELOPER_ID}">{full_name}</a>'
    lines = [f"🛠 <b>Создатель бота</b>\n"]
    lines.append(f"👤 Имя: {contact}")
    if username:
        lines.append(f"📛 Username: @{html.escape(username)}")
    lines += [
        f"🆔 ID: <code>{DEVELOPER_ID}</code>",
        f"🎖 Ранг: {rank_name('developer')}",
        f"💬 Сообщений: {msgs}",
        f"⭐ Репутация: <b>{rep:+d}</b>",
        f"🌟 Уровень: <b>{lvl}</b>  [{bar}]  {xp}/{next_xp} XP",
    ]
    bio = bio_db or bio_tg
    if bio:
        lines.append(f"\n📝 <i>{bio}</i>")
    await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)

