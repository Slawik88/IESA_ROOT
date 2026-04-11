from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import html

from database.db import (
    get_active_theme, get_daily_top, get_equipped_legendary, get_marriage, get_mora,
    get_mora_batch, get_prev_weekly_top, get_received_gifts, get_top_by_messages_in_chat,
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
    """Все страницы справки. Ключ = page_id, значение = {text, buttons, min_rank}."""
    from config import (
        ANON_MSG_PRICE, GACHA_SINGLE_PRICE, GACHA_MULTI_PRICE,
        MINI_APP_URL,
        MAX_WARNS, PET_MORA_SKIP_PRICE, PET_RENAME_PRICE,
        QUEST_REROLL_PRICE, SECRET_MSG_PRICE, VIP_PRICE,
    )
    return {
        # ─── Главное меню ─────────────────────────────────────────────────
        "main": {
            "text": (
                "📖 <b>Предвестник — Справка</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Добро пожаловать! Выбери раздел 👇\n\n"
                "🌐 <b>Mini App:</b> кнопка <b>Открыть App</b> доступна возле строки ввода.\n"
                "Также можно написать <code>бот app</code>.\n\n"
                "<i>💡 Команды пишутся текстом — без «/»\n"
                "🎯 Таргет — @юзер или ответ на сообщение</i>"
            ),
            "buttons": [
                [("🌐 Mini App", "miniapp_help")],
                [("👤 Профиль", "profile"), ("💍 Отношения", "relations")],
                [("🐾 Питомцы", "pets"), ("🎲 Игры & Босс", "games")],
                [("💰 Экономика", "economy"), ("📋 Инфо", "info")],
                [("👮 Модерация", "moderation"), ("⚙️ Настройки", "settings")],
                [("👑 Управление", "management")],
            ],
            "min_rank": "user",
        },
        "miniapp_help": {
            "text": (
                "🌐 <b>Mini App / Сайт</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🚀 <b>Как открыть:</b>\n"
                "  <code>бот app</code> — прислать кнопку входа\n"
                "  Кнопка <b>Открыть App</b> — всегда возле строки ввода в Telegram\n\n"
                " Внутри App доступны: баланс, рамка, XP, облигации, инвентарь и питомец."
            ),
            "buttons": [
                [("🚀 Открыть Mini App", f"url:{MINI_APP_URL}")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "user",
        },

        # ─── 🛍 Экономика ────────────────────────────────────────────────
        "economy": {
            "text": (
                f"💰 <b>Экономика (Мора)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 <b>Основные:</b>\n"
                f"  <code>бот баланс</code> — Мора, VIP, рамка, буст\n"
                f"  <code>бот магазин</code> — всё, что можно купить\n"
                f"  <code>бот банк</code> — вклады с процентами\n"
                f"  <code>бот молитва</code> — гача x1/x10 ({GACHA_SINGLE_PRICE}/{GACHA_MULTI_PRICE} 🪙)\n\n"
                f"👑 <b>Покупки:</b>\n"
                f"  <code>бот купить вип</code> — VIP ({VIP_PRICE} 🪙)\n"
                f"  <code>бот купить буст</code> — XP x2 на время\n"
                f"  <code>бот рамки</code> — рамки для топа\n"
                f"  <code>бот анонимка [текст]</code> — ({ANON_MSG_PRICE} 🪙)\n"
                f"  <code>бот секрет @user текст</code> — ({SECRET_MSG_PRICE} 🪙)\n\n"
                f"👨‍👩‍👧 <b>Для пар:</b>\n"
                f"  <code>бот семейный кошелёк</code> · <code>бот пополнить семью N</code> · <code>бот снять семью N</code>\n\n"
                f"💳 <b>Долги:</b> заёмщик должен принять заявку — деньги переходят только после подтверждения.\n"
                f"  Максимум: 2000 🪙, до 5 займов. Доступно через Mini App → 💳 Долги"
            ),
            "buttons": [
                [("🏦 Банк", "bank_help"), ("🎰 Гача", "gacha_help")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "user",
        },
        "bank_help": {
            "text": (
                "🏦 <b>Банк Северного Королевства</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>бот банк</code> — открыть банк\n\n"
                "📊 <b>Планы вкладов:</b>\n"
                "  💰 3 дня — 1.5%\n"
                "  💰 7 дней — 4%\n"
                "  💰 14 дней — 10%\n\n"
                "⚠️ Досрочное снятие: теряешь ВСЕ проценты + 1% суммы"
            ),
            "buttons": [[("🔙 Назад", "economy")]],
            "min_rank": "user",
        },
        "gacha_help": {
            "text": (
                f"🎰 <b>Молитвы (Гача)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"<code>бот молитва</code> — x1 ({GACHA_SINGLE_PRICE} 🪙) или x10 ({GACHA_MULTI_PRICE} 🪙)\n"
                f"<code>бот инвентарь</code> — все предметы\n"
                f"<code>бот продать мусор</code> — продать весь мусор\n"
                f"<code>бот экипировать #ID</code> — легендарка в профиль\n\n"
                f"📊 <b>Шансы:</b>\n"
                f"  ⚪ 70% Мусор → продаётся за 2–5 🪙\n"
                f"  🟢 20% Обычный → разовый бонус XP/мора\n"
                f"  🟣  8% Редкий → косметика, бейджи\n"
                f"  🟡  3% Легендарный → VIP-темы, экипировка\n\n"  # РЕБАЛАНС: было 2%
                f"✨ Гарант: лега каждые 50 круток!"
            ),
            "buttons": [[("🔙 Назад", "economy")]],
            "min_rank": "user",
        },

        # ─── 🎲 Игры ─────────────────────────────────────────────────────
        "games": {
            "text": (
                "🎲 <b>Игры & Развлечения</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🪙 <b>Монетка</b>\n"
                "  <code>бот монетка N</code> — испытай удачу! ×2 или потеряй\n\n"
                "🎲 <b>Дуэль на кубиках</b>\n"
                "  <code>бот кубик @юзер N</code> — дуэль на мору\n\n"
                "🎟 <b>Лотерея</b>\n"
                "  <code>бот купить лотерею</code> — билет (10 🪙)\n"
                "  <code>бот мои билеты</code>\n\n"
                "👊 <b>Действия</b> (ответом/через @юзер)\n"
                "  <code>пни · укуси · обними · шлёпни · лизни · погладь · кинь</code>"
            ),
            "buttons": [
                [("📅 Чекин", "checkin"), ("⚔️ Босс", "boss")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "user",
        },

        # ─── 📅 Чекин ────────────────────────────────────────────────────
        "checkin": {
            "text": (
                "📅 <b>Ежедневный чекин</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🔥 <b>Команды:</b>\n"
                "  <code>бот чекин</code> — отметиться сегодня\n"
                "  <code>бот чекин стрик</code> — посмотреть стрик и календарь\n\n"
                "🎁 <b>Награды по дням:</b>\n"
                "  День 1–4: 30–35 🪙\n"
                "  День 5: 60 🪙 🏆\n"
                "  День 10: 80 🪙 🏆\n"
                "  День 15: 100 🪙 🏆\n"
                "  День 20: 150 🪙 🏆 + бесплатная молитва!\n\n"
                "💡 Пропустил день → сброс к последнему чекпоинту (5/10/15/20).\n"
                "📱 Чекин также доступен в <b>Mini App</b> → 📅 Чекин"
            ),
            "buttons": [[("🔙 Назад", "games")]],
            "min_rank": "user",
        },

        # ─── ⚔️ Босс ─────────────────────────────────────────────────────
        "boss": {
            "text": (
                "⚔️ <b>Битва с боссом</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🔥 <b>Команды:</b>\n"
                "  <code>бот босс</code> — статус и HP босса\n"
                "  <code>бот босс атака</code> — атаковать (КД 30 сек)\n\n"
                "⚔️ <b>Механика урона:</b>\n"
                "  • Базовый урон зависит от ATK предметов\n"
                "  • Шанс крита — CRIT_RATE (×1.5 к урону)\n"
                "  • Разброс: 80–120% от базы\n\n"
                "💰 <b>Награда:</b> max(5, урон ÷ 20) 🪙 за атаку\n\n"
                "🏆 <b>Лидерборд урона:</b>\n"
                "  В Mini App → 🏆 Топ → ⚔️ Урон\n\n"
                "📱 Атака также доступна в <b>Mini App</b> → ⚔️ Босс"
            ),
            "buttons": [[("🔙 Назад", "games")]],
            "min_rank": "user",
        },

        # ─── 🐾 Питомцы ──────────────────────────────────────────────────
        "pets": {
            "text": (
                f"🐾 <b>Питомцы & Экспедиции</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🐾 <b>Питомец</b>\n"
                f"  <code>бот питомец</code> — посмотреть\n"
                f"  <code>бот завести питомца</code> — завести ({PET_MORA_SKIP_PRICE} 🪙 скипнуть ожидание)\n"
                f"  <code>бот назвать питомца [имя]</code> — {PET_RENAME_PRICE} 🪙 после первого раза\n\n"
                f"🧭 <b>Экспедиции</b>\n"
                f"  <code>бот экспедиция</code> — отправить за добычей\n"
                f"  ⏱ 2ч (бесплатно) · 4ч (5 🪙) · 8ч (10 🪙)\n\n"
                f"📋 <b>Задания</b>\n"
                f"  <code>бот задание</code> — ежедневное задание\n"
                f"  <code>бот перебросить задание</code> — сменить ({QUEST_REROLL_PRICE} 🪙)"
            ),
            "buttons": [[("🔙 Назад", "main")]],
            "min_rank": "user",
        },

        # ─── 💍 Отношения ────────────────────────────────────────────────
        "relations": {
            "text": (
                "💍 <b>Отношения & Подарки</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "💕 <b>Пара:</b>\n"
                "  <code>бот брак @юзер</code> — предложить руку и сердце\n"
                "  <code>бот пара</code> — инфо о текущей паре\n"
                "  <code>бот развод</code> — расторгнуть брак\n\n"
                "🎁 <b>Подарки партнёру:</b>\n"
                "  <code>бот подарки</code> — витрина подарков\n"
                "  <i>Подарки с баффами усиливают добычу моры</i>\n\n"
                "👨‍👩‍👧 <b>Семья:</b>\n"
                "  <code>бот семейный кошелёк</code> — общий счёт\n"
                "  <code>бот пополнить семью N</code> · <code>бот снять семью N</code>"
            ),
            "buttons": [[("🔙 Назад", "main")]],
            "min_rank": "user",
        },

        # ─── 👤 Профиль ──────────────────────────────────────────────────
        "profile": {
            "text": (
                "👤 <b>Профиль & Репутация</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "📊 <b>Просмотр</b>\n"
                "  <code>бот я</code> — профиль с темой и бейджами\n"
                "  <code>бот инфо [@юзер]</code> — краткая справка\n"
                "  <code>бот досье [@юзер]</code> — полное досье\n\n"
                "✏️ <b>Кастомизация</b>\n"
                "  <code>бот тема</code> — выбрать тему профиля\n"
                "  <code>бот обо мне [текст]</code> — биография\n"
                "  <code>бот инвентарь</code> — предметы из гачи\n"
                "  <code>бот экипировать #ID</code> — лего в профиль\n\n"
                "⭐ <b>Репутация & XP</b>\n"
                "  <code>+</code> ответом — +1 репутация\n"
                "  <code>бот уровень</code> · <code>бот репутация</code>\n"
                "  <code>бот топ</code> — рейтинги активности"
            ),
            "buttons": [[("🔙 Назад", "main")]],
            "min_rank": "user",
        },

        # ─── 📋 Инфо ─────────────────────────────────────────────────────
        "info": {
            "text": (
                "📋 <b>Инфо & чат</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🏆 <b>Рейтинги</b>\n"
                "  <code>бот топ</code> · <code>бот топ день</code> · <code>бот топ неделя</code>\n\n"
                "📌 <b>Полезное</b>\n"
                "  <code>бот правила</code> — правила чата\n"
                "  <code>бот время [город]</code> — текущее время\n"
                "  <code>бот наши ссылки</code> — соцсети\n"
                "  <code>#название</code> — заметка\n\n"
                "💬 <b>Чат</b>\n"
                "  <code>бот чат</code> · <code>бот айди</code> · <code>бот автор</code>\n\n"
                "🚨 <b>Жалобы</b>\n"
                "  <code>бот жалоба [причина]</code> ответом на нарушителя"
            ),
            "buttons": [[("🔙 Назад", "main")]],
            "min_rank": "user",
        },

        # ─── 👮 Модерация [👮 Модер+] ────────────────────────────────────
        "moderation": {
            "text": (
                "👮 <b>Модерация</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Выбери подраздел 👇"
            ),
            "buttons": [
                [("⚠️ Мут & варны [⚡АдминМл+]", "s_warns")],
                [("🔨 Бан & управление [👑СоВлад+]", "s_mod")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "admin_junior",
        },
        "s_warns": {
            "text": (
                f"⚠️ <b>Мут & варны</b>  <code>[⚡ АдминМл+]</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🔴 <b>Предупреждения</b>\n"
                f"  <code>бот варн [@юзер] [причина]</code>\n"
                f"  <i>└ {MAX_WARNS} варнов → уведомление админам</i>\n"
                f"  <code>бот предупреждения [@юзер]</code> · <code>бот снять варн</code>\n"
                f"  <code>бот варнлист</code> — список участников с варнами\n\n"
                f"🔇 <b>Мут</b>\n"
                f"  <code>бот мут [@юзер] [30с|10м|2ч|1д]</code>\n"
                f"  <code>бот размут [@юзер]</code>"
            ),
            "buttons": [[("🔙 Назад", "moderation")]],
            "min_rank": "admin_junior",
        },
        "s_mod": {
            "text": (
                "🔨 <b>Бан & модерация</b>  <code>[� СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🚫 <code>бот бан · разбан · баны · кик</code>\n\n"
                "📌 <code>бот закрепить · открепить · очистить N</code>\n\n"
                "📒 <code>бот заметка [имя] [текст]</code> · <code>бот заметки</code>\n"
                "🔁 <code>бот автоответ [фраза] | [ответ]</code>\n"
                "🚷 <code>бот блок · разблок · чс</code>\n"
                "🚪 <code>бот ушли [N]</code>\n\n"
                "🚷 <b>ID-бан:</b>\n"
                "  <code>бот юзбан · юзразбан · юзбаны</code>"
            ),
            "buttons": [[("🔙 Назад", "moderation")]],
            "min_rank": "co_owner",
        },

        # ─── ⚙️ Настройки [⚡ Админ+] ────────────────────────────────────
        "settings": {
            "text": (
                "⚙️ <b>Настройки чата</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Выбери подраздел 👇"
            ),
            "buttons": [
                [("👥 Персонал", "s_staff"), ("💬 Правила", "s_rules")],
                [("🔒 Замки", "s_locks"), ("🛡 Антифлуд", "s_flood")],
                [("📥 Импорт", "s_import"), ("🔗 Соцсети", "s_social")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "co_owner",
        },
        "s_staff": {
            "text": (
                "👥 <b>Персонал & роли</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🏅 <code>бот ранг [ранг] [@юзер]</code>\n"
                "  <i>user · moderator · admin_junior · admin_senior · co_owner · owner</i>\n"
                "<code>бот состав</code> · <code>бот статистика</code>\n\n"
                "🎭 <code>бот выдать роль · снять роль · роли · мои роли</code>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "co_owner",
        },
        "s_rules": {
            "text": (
                "💬 <b>Правила & приветствие</b>  <code>[⚡ АдминСт+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "📜 <code>бот правила установить [текст]</code>\n\n"
                "👋 <code>бот приветствие [текст]</code>\n"
                "  <i>Переменные: {name} · {username} · {chat}</i>\n"
                "<code>бот прощание [текст]</code>\n"
                "<code>бот тег входа [вкл/выкл]</code>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "admin_senior",
        },
        "s_locks": {
            "text": (
                "🔒 <b>Замки контента</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>бот замок [тип]</code> · <code>бот открыть [тип]</code> · <code>бот замки</code>\n\n"
                "<i>Типы: links · stickers · gifs · forwards · voice · video · photo · audio</i>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "co_owner",
        },
        "s_flood": {
            "text": (
                "🛡 <b>Антифлуд & чистка</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🌊 <code>бот антифлуд N [Xс]</code> · <code>бот антифлуд выкл</code>\n"
                "<code>бот фильтрмат [вкл/выкл]</code>\n\n"
                "🧹 <code>бот чистка [N]</code> · <code>бот чистка открыть</code>\n"
                "<code>бот чистка порог N</code> · <code>бот чистка дата</code>\n\n"
                "😴 <code>бот отдых @user [дней]</code> · <code>бот отдых снять</code> · <code>бот отдых список</code>\n"
                "🔕 <code>бот неактив</code>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "co_owner",
        },
        "s_import": {
            "text": (
                "📥 <b>Импорт данных</b>  <code>[🛠 Дев]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "💬 <code>бот загрузить данные</code> — JSON-импорт сообщений\n"
                "💍 <code>бот загрузить браки</code> — JSON-импорт пар\n\n"
                "<i>Данные привяжутся при первом сообщении юзера.</i>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "developer",
        },
        "s_social": {
            "text": (
                "🔗 <b>Соцсети</b>  <code>[👑 СоВлад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>бот соцсети tiktok|youtube|instagram [URL]</code>\n"
                "<code>бот наши ссылки</code>\n"
                "<code>бот история чата</code>"
            ),
            "buttons": [[("🔙 Назад", "settings")]],
            "min_rank": "co_owner",
        },

        # ─── 👑 Управление [👑 Влад+ / 🛠 Дев] ──────────────────────────
        "management": {
            "text": (
                "👑 <b>Управление</b>  <code>[👑 Влад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Выбери подраздел 👇"
            ),
            "buttons": [
                [("🔱 Владелец", "s_owner"), ("🛠 Разработчик", "s_dev")],
                [("🎉 Ивенты [АдминСт+]", "s_events")],
                [("🔙 Назад", "main")],
            ],
            "min_rank": "owner",
        },
        "s_owner": {
            "text": (
                "🔱 <b>Владелец+</b>  <code>[👑 Влад+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "👑 <code>бот совладелец [@юзер]</code>\n"
                "🎭 <code>бот добавить роль · убрать роль · сменить роль</code>\n\n"
                "📣 <b>Рассылка:</b>\n"
                "  <code>бот колл [#все|#юзеры|#стафф|#модеры|#админы] [текст]</code>\n\n"
                "💰 <b>Казна (выдача только из казны):</b>\n"
                "  <code>бот казна</code> — баланс казны\n"
                "  <code>бот казна дать @user N</code> — выдать игроку из казны\n"
                "  <code>бот казна забрать @user N</code> — вернуть в казну\n"
                "  <code>бот выдать xp [N] @user [причина]</code> — начислить XP\n\n"
                "🔔 <b>Чат администрации (уведомления):</b>\n"
                "  1️⃣ В осн. чате: <code>бот привязать</code>\n"
                "  2️⃣ В чате администрации: <code>бот принять -100XXXX</code>\n"
                "  • <code>бот привязка</code> — текущая привязка\n"
                "  • <code>бот отвязать</code> — удалить привязку"
            ),
            "buttons": [[("🔙 Назад", "management")]],
            "min_rank": "owner",
        },
        "s_events": {
            "text": (
                "🎉 <b>Ивенты</b>  <code>[⚡ АдминСт+]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🎁 <b>Сундук</b> (по пятницам авто, или вручную):\n"
                "  <code>бот сундук</code> — запустить Rich Chest\n\n"
                "🚚 <b>Дилижанс</b> (по пятницам 20:00 Zurich):\n"
                "  <code>бот дилижанс</code> — запустить вручную\n\n"
                "🧑‍💼 <b>Торговец</b> (раз в 3 дня):\n"
                "  <code>бот торговец</code> — запустить вручную\n\n"
                "🏦 <b>Казна</b>:\n"
                "  <code>бот казна</code> — текущее состояние казны\n\n"
                "🛠 <b>Developer-only:</b>\n"
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
                "🧑‍💻 <code>бот разработчик · скан · сетюзер · прибавитьxp · сеттитул</code>\n"
                "🕐 <code>бот таймзона [tz]</code>\n"
                "📡 <code>бот канал правила|основной &lt;id&gt;</code> · <code>бот каналы</code>\n"
                " <code>бот админгруппа · удадмингруппу · админгруппы</code>\n\n"
                "🧪 <b>Тестовые чаты (изоляция):</b>\n"
                "  <code>бот тестчат [chat_id]</code> · <code>бот удтестчат</code> · <code>бот тестчаты</code>\n\n"
                "🔗 <b>Привязки чатов администрации:</b>\n"
                "  <code>бот привязки</code> — список всех привязок\n"
                "  <code>бот снятьнадмин [chat_id]</code> — принудительно удалить\n\n"
                "🎮 <b>Принудительный запуск ивентов:</b>\n"
                "  <code>бот эвент сундук</code> · <code>бот эвент дилижанс</code>\n"
                "  <code>бот эвент торговец</code>\n\n"
                "💰 <b>Эмиссия (только разработчик, без казны):</b>\n"
                "  <code>бот выдать [N] @user [причина]</code> — начислить мору напрямую\n"
                "  <code>бот сетбаланс [сумма] [@user]</code> — установить баланс"
            ),
            "buttons": [[("🔙 Назад", "management")]],
            "min_rank": "developer",
        },
    }


def _build_help_kb(page_id: str, uid: int, lvl: int, chat_id: int = 0) -> InlineKeyboardMarkup:
    """Построить Inline-клавиатуру для страницы справки."""
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
                # Override Mini App URL to include startapp chat context
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
        from config import PROFILE_THEMES, BADGE_DEFINITIONS
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
            BADGE_DEFINITIONS[bk]["emoji"] for bk in badge_keys if bk in BADGE_DEFINITIONS
        )
        equipped = await get_equipped_legendary(uid, chat_id)

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
            lines.append(f"⚔️ Экипировка: {equipped['item_name']}")
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
        from config import BADGE_DEFINITIONS
        chat_id = callback.message.chat.id
        badge_keys = await get_user_badges(uid, chat_id)
        lines = ["🏅 <b>Бейджи</b>\n━━━━━━━━━━━━━━━━━━━━\n"]
        if badge_keys:
            for bk in badge_keys:
                bd = BADGE_DEFINITIONS.get(bk)
                if bd:
                    lines.append(f"{bd['emoji']} <b>{bd['name']}</b> — <i>{bd['desc']}</i>")
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
    from config import DEVELOPER_ID, PROFILE_THEMES, BADGE_DEFINITIONS
    from handlers.economy import TOP_FRAMES, _frame_emoji
    uid = message.from_user.id
    chat_id = message.chat.id
    is_group = message.chat.type in ("group", "supergroup")

    user = await get_user(uid)
    if not user:
        await message.answer("❌ Тебя ещё нет в базе. Напиши любое сообщение в чат.")
        return

    stats = await get_user_stats(uid, chat_id)
    rank    = stats["rank"]         if stats else "user"
    if DEVELOPER_ID and uid == DEVELOPER_ID:
        rank = "developer"
    warns_n = stats["warns"]        if stats else 0
    xp      = stats["xp"]          if stats else 0
    lvl     = stats["level"]        if stats else 1
    rep     = stats["reputation"]   if stats else 0
    bio     = stats["bio"]          if stats else None
    msgs    = stats["message_count"] if stats else 0
    banned  = stats["is_banned"]    if stats else 0
    title   = stats["custom_title"] if stats else None

    mora_row = await get_mora(uid, chat_id) if is_group else None
    vip       = (mora_row["vip"] or 0)     if mora_row else 0
    mora_bal  = (mora_row["balance"] or 0) if mora_row else 0
    frame_key = mora_row["top_frame"]       if mora_row else None
    boost_active = await get_xp_boost_active(uid, chat_id) if is_group else False

    # ── Тема профиля ──────────────────────────────────────────────────────
    theme_key = await get_active_theme(uid, chat_id) if is_group else "default"
    theme = PROFILE_THEMES.get(theme_key, PROFILE_THEMES["default"])

    # ── Бейджи ────────────────────────────────────────────────────────────
    badge_keys = await get_user_badges(uid, chat_id) if is_group else []
    badges_str = " ".join(
        BADGE_DEFINITIONS[bk]["emoji"] for bk in badge_keys if bk in BADGE_DEFINITIONS
    )

    # ── Экипированный легендарный предмет из гачи ────────────────────────
    equipped = await get_equipped_legendary(uid, chat_id) if is_group else None

    # ── XP-бар ────────────────────────────────────────────────────────────
    from database.db import xp_for_level
    from config import MAX_WARNS
    next_xp = xp_for_level(lvl + 1)
    bar_filled = min(10, int((xp - xp_for_level(lvl)) / max(1, next_xp - xp_for_level(lvl)) * 10))
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    status = "🔴 Заблокирован" if banned else "🟢 Активен"
    warns_line = "⚠️" * warns_n + f"({warns_n}/{MAX_WARNS})" if warns_n else "нет"
    vip_tag = " 💎" if vip else ""

    # ── Сборка текста по теме ─────────────────────────────────────────────
    sep = theme["separator"]
    lines = [
        f"{theme['header']}{vip_tag}",
        sep,
        "",
    ]
    if badges_str:
        lines.append(f"🏅 {badges_str}")
    lines += [
        f"🏷 {html.escape(user['full_name'])}",
        f"🎖 {rank_name(rank, title)}",
        f"🌟 Ур. <b>{lvl}</b>  [{bar}]  {xp}/{next_xp}",
        f"⭐ Репутация: <b>{rep:+d}</b>",
        f"💬 Сообщений: {msgs}",
    ]
    if not is_group:
        lines.append(f"🪙 Мора: <b>{mora_bal}</b> 🪙")
    if theme_key != "default":
        from config import COSMETIC_TIER_LABELS
        tier_label = COSMETIC_TIER_LABELS.get(theme.get("tier", "common"), "")
        lines.append(f"🎨 Тема: {theme['name']} [{tier_label}]")
    if equipped:
        lines.append(f"⚔️ Экипировка: {equipped['item_name']}")
    if frame_key:
        frame_label = next((f[2] for f in TOP_FRAMES if f[0] == frame_key), None)
        if frame_label:
            lines.append(f"🖼 Рамка: {_frame_emoji(frame_key)} {frame_label}")
    if boost_active:
        lines.append("⚡ <b>XP x2 активен</b>")

    # Щит новичка
    if is_group and stats:
        _shield_until = stats.get("newbie_shield_until")
        if _shield_until:
            if hasattr(_shield_until, 'tzinfo'):
                _su = _shield_until if _shield_until.tzinfo else _shield_until.replace(tzinfo=timezone.utc)
            else:
                try:
                    _su = datetime.fromisoformat(str(_shield_until))
                    if _su.tzinfo is None:
                        _su = _su.replace(tzinfo=timezone.utc)
                except Exception:
                    _su = None
            if _su and _su > datetime.now(timezone.utc):
                _delta = _su - datetime.now(timezone.utc)
                _days_left  = _delta.days
                _hours_left = _delta.seconds // 3600
                lines.append(f"🛡 Щит новичка: ещё {_days_left}д {_hours_left}ч")

    lines += [
        "",
        sep,
        f"⚠️ Варны: {warns_line}  |  📊 {status}",
    ]
    if bio:
        lines.append(f"\n📝 <i>{html.escape(bio)}</i>")

    # Community roles (tags)
    if is_group:
        try:
            from database.db import get_user_community_roles
            c_roles = await get_user_community_roles(uid)
            if c_roles:
                roles_str = "  ".join(
                    f"{r.get('emoji', '')} {html.escape(r['name'])}".strip()
                    for r in c_roles
                )
                lines.append(f"🎭 Роль: {roles_str}")
        except Exception as _e:
            _log.debug("%s", _e)
    # Брак
    if is_group:
        marriage = await get_marriage(uid, chat_id)
        if marriage:
            partner = await get_user(marriage["partner_id"])
            partner_name = html.escape(partner["full_name"]) if partner else "?"
            lines.append(f"💍 Партнёр: {user_mention(marriage['partner_id'], partner_name)}")
            received = await get_received_gifts(uid, chat_id)
            if received:
                gifts_str = ", ".join(
                    f"{g['gift_name']}×{g['cnt']}" if g["cnt"] > 1 else g["gift_name"]
                    for g in received
                )
                lines.append(f"🎁 Подарки: {gifts_str}")

    # Active potion buffs — визуальное отображение с реальными характеристиками
    if is_group:
        from database.db import get_active_buffs
        from datetime import timezone as _tz
        active_buffs = await get_active_buffs(uid, chat_id)
        if active_buffs:
            # Map buff_type → (emoji, label, stat_value)
            _BUFF_MAP = {
                "atk":           ("⚔️", "ATK",         "+15"),
                "def":           ("🛡️", "DEF",         "+20"),
                "hp":            ("❤️", "HP",           "+50"),
                "mora_boost_10": ("🪙", "Мора",         "+10%"),
                "mora_boost_15": ("🪙", "Мора",         "+15%"),
                "mora_boost_20": ("🪙", "Мора",         "+20%"),
            }
            now_utc = datetime.now(timezone.utc)
            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("💫 <b>Активные эффекты</b>")
            for buff in active_buffs:
                btype = buff.get("buff_type") or buff.get("type", "")
                exp = buff.get("expires_at")
                mins_left = 0
                if exp:
                    try:
                        exp_dt = exp if hasattr(exp, "tzinfo") else datetime.fromisoformat(str(exp))
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        mins_left = max(0, int((exp_dt - now_utc).total_seconds() / 60))
                    except Exception as _e:
                        _log.debug("%s", _e)
                emoji, label, val = _BUFF_MAP.get(btype, ("✨", btype, ""))
                time_str = f"{mins_left // 60}ч {mins_left % 60}м" if mins_left >= 60 else f"{mins_left}м"
                lines.append(f"  {emoji} {label}: <b>{val}</b>  ⏱ {time_str}")

    # Talent summary — показываем активные бонусы из талантов
    if is_group:
        try:
            from database.db import get_user_talents
            from shared_prices import TALENT_TREE
            tal_data = await get_user_talents(uid)
            _invested = tal_data.get("talents", {})
            _tp_left  = tal_data.get("talent_points", 0)
            _talent_lines = []
            _TALENT_STAT_LABELS = {
                "mora_drop_chance":    ("🌾", "Мора дроп",     "%"),
                "drop_luck_pct":       ("🍀", "Удача дропа",   "%"),
                "atk_bonus":           ("⚔️", "ATK",           ""),
                "free_potion_chance":  ("🧪", "Зелье бесплатно", "%"),
                "hp_potion_bonus":     ("❤️", "HP от зелья",   ""),
                "gacha_pity_reduction":("🎴", "Гача пити",     "−"),
                "coinflip_win_pct":    ("🎲", "Монетка шанс",  "%"),
                "expedition_cd_minutes":("🗺️","Экспедиция",  " мин"),
                "rep_cd_hours":        ("⭐", "Репа кулдаун",  " ч"),
                "craft_shard_discount":("⚒️", "Крафт −осколок",""),
                "gacha_shard_bonus":   ("💎", "Гача +шарды",   ""),
            }
            effect_totals: dict[str, int] = {}
            for tid, t in TALENT_TREE.items():
                lvl = _invested.get(tid, 0)
                if lvl > 0:
                    ek = t["effect_key"]
                    effect_totals[ek] = effect_totals.get(ek, 0) + lvl * t["effect_per_level"]
            if effect_totals:
                for ek, total in effect_totals.items():
                    if ek == "shield_renewal":
                        continue
                    info = _TALENT_STAT_LABELS.get(ek)
                    if not info:
                        continue
                    em, lab, unit = info
                    if unit == "−":
                        _talent_lines.append(f"  {em} {lab}: <b>−{total}</b>")
                    elif unit.startswith(" "):
                        _talent_lines.append(f"  {em} {lab}: <b>−{total}{unit}</b>")
                    else:
                        _talent_lines.append(f"  {em} {lab}: <b>+{total}{unit}</b>")
            if _talent_lines or _tp_left > 0:
                lines.append("")
                lines.append("━━━━━━━━━━━━━━━━━━━━")
                tp_note = f"  <i>({_tp_left} очков доступно)</i>" if _tp_left > 0 else ""
                lines.append(f"🎯 <b>Таланты</b>{tp_note}")
                lines.extend(_talent_lines)
                if not _talent_lines:
                    lines.append("  <i>Таланты не прокачаны — открой Mini App</i>")
        except Exception as _e:
            _log.debug("%s", _e)
    # Pet walk status
    if is_group:
        from database.db import get_pet
        pet_for_walk = await get_pet(uid, chat_id)
        if pet_for_walk and pet_for_walk.get("walk_end_at"):
            try:
                end_dt = datetime.fromisoformat(str(pet_for_walk["walk_end_at"]))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                mins = int((end_dt - datetime.now(timezone.utc)).total_seconds() / 60)
                if mins > 0:
                    pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet_for_walk.get("pet_type", ""), "🐾")
                    lines.append(f"{pet_emoji} На прогулке (осталось {mins} мин)")
            except Exception as _e:
                _log.debug("%s", _e)
    if theme["footer"]:
        lines.append(f"\n{theme['footer']}")

    # web_app= only works in private chats.
    # In groups, use t.me Mini App link with startapp=abs(chat_id) so the app knows which chat.
    if message.chat.type == "private":
        miniapp_row = [
            InlineKeyboardButton(text="📱 Mini App", web_app=WebAppInfo(url=_MINI_APP_URL)),
            InlineKeyboardButton(
                text="📋 История кошелька",
                web_app=WebAppInfo(url=f"{_MINI_APP_URL}?open=wallet_history"),
            ),
        ]
    else:
        abs_cid = abs(message.chat.id)
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
    equipped_t = await get_equipped_legendary(uid, message.chat.id) if is_group_w else None
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
        lines.append(f"⚔️ Экипировка: {equipped_t['item_name']}")
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

