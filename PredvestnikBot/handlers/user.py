from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from datetime import datetime
from zoneinfo import ZoneInfo
import html

from config import REPORT_NOTIFY_RANK
from database.db import (
    get_active_theme, get_daily_top, get_equipped_legendary, get_marriage, get_mora,
    get_prev_weekly_top, get_received_gifts, get_staff_in_chat, get_top_by_messages_in_chat,
    get_top_by_xp_in_chat, get_user, get_user_badges, get_user_stats,
    get_user_themes, get_weekly_top, get_yesterday_top, set_bio_in_chat,
    get_xp_boost_active, add_user_theme, set_active_theme,
)
from filters.bot_command import BotCommand
from utils.helpers import resolve_target, user_mention
from utils.ranks import rank_level, rank_name

router = Router()

def _fmt_dt(iso_str: str | None) -> str:
    """Format ISO datetime as dd.mm.yyyy HH:MM or 'нет данных'."""
    if not iso_str:
        return "нет данных"
    try:
        dt = datetime.fromisoformat(iso_str)
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
                "<i>💡 Команды пишутся текстом — без «/»\n"
                "🎯 Таргет — @юзер или ответ на сообщение</i>"
            ),
            "buttons": [
                [("👤 Профиль", "profile"), ("💍 Отношения", "relations")],
                [("🐾 Питомцы", "pets"), ("🎲 Игры", "games")],
                [("💰 Экономика", "economy"), ("📋 Инфо", "info")],
                [("👮 Модерация", "moderation"), ("⚙️ Настройки", "settings")],
                [("👑 Управление", "management")],
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
                f"  <code>бот семейный кошелёк</code> · <code>бот пополнить семью N</code> · <code>бот снять семью N</code>"
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
                f"  🟡  2% Легендарный → VIP-темы, экипировка\n\n"
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
                "  <code>бот монетка N</code> — 50/50, ×2 или потеряй\n\n"
                "🎲 <b>Дуэль на кубиках</b>\n"
                "  <code>бот кубик @юзер N</code> — дуэль на мору\n\n"
                "🎟 <b>Лотерея</b>\n"
                "  <code>бот купить лотерею</code> — билет (10 🪙)\n"
                "  <code>бот мои билеты</code>\n\n"
                "👊 <b>Действия</b> (ответом/через @юзер)\n"
                "  <code>пни · укуси · обними · шлёпни · лизни · погладь · кинь</code>"
            ),
            "buttons": [[("🔙 Назад", "main")]],
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
                f"  ⏱ 2ч (бесплатно) · 4ч (10 🪙) · 8ч (25 🪙)\n\n"
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
                f"  <code>бот предупреждения [@юзер]</code> · <code>бот снять варн</code>\n\n"
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
                "💰 <b>Эмиссия:</b>\n"
                "  <code>бот выдать [N] @user [причина]</code> — начислить мору\n"
                "  <code>бот выдать xp [N] @user [причина]</code> — начислить XP"
            ),
            "buttons": [[("🔙 Назад", "management")]],
            "min_rank": "owner",
        },
        "s_dev": {
            "text": (
                "🛠 <b>Разработчик</b>  <code>[🛠 Дев]</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "🧑‍💻 <code>бот разработчик · скан · сетюзер · прибавитьxp · сеттитул</code>\n"
                "🕐 <code>бот таймзона [tz]</code>\n"
                "📡 <code>бот канал правила|основной &lt;id&gt;</code> · <code>бот каналы</code>\n"
                "🔐 <code>бот разрешить · запретить · группы</code>\n"
                "📣 <code>бот админгруппа · удадмингруппу · админгруппы</code>\n\n"
                "🎁 <b>Сундуки (отладка):</b>\n"
                "  <code>бот сундук</code> — создать сундук в текущем чате\n"
                "  <code>бот групчаты</code> — список активных групповых чатов"
            ),
            "buttons": [[("🔙 Назад", "management")]],
            "min_rank": "developer",
        },
    }


def _build_help_kb(page_id: str, uid: int, lvl: int) -> InlineKeyboardMarkup:
    """Построить Inline-клавиатуру для страницы справки."""
    pages = _help_pages()
    page = pages.get(page_id)
    if not page:
        return InlineKeyboardMarkup(inline_keyboard=[])
    rows: list[list[InlineKeyboardButton]] = []
    for btn_row in page["buttons"]:
        row: list[InlineKeyboardButton] = []
        for label, target in btn_row:
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
    kb = _build_help_kb("main", uid, lvl)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


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

    if callback.from_user.id != owner_id:
        await callback.answer("🚫 Это меню не твоё. Напиши «бот помощь».", show_alert=True)
        return

    if page_id == "close":
        try:
            await callback.message.delete()
        except Exception:
            pass
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

    kb = _build_help_kb(page_id, owner_id, lvl)
    try:
        await callback.message.edit_text(page["text"], parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


_TOP_MEDALS = ["🥇", "🥈", "🥉", "🎖", "🎗"]


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
    if callback.from_user.id != owner_id:
        await callback.answer("🚫 Это меню не твоё. Напиши «бот топ».", show_alert=True)
        return
    chat_id = callback.message.chat.id

    if period == "close":
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()
        return

    if period == "d":
        top = await get_daily_top(chat_id, 500)
        title = "📅 <b>Рейтинг активных за сегодня:</b>"
        count_field = "dc"
    elif period == "w":
        top = await get_weekly_top(chat_id, 500)
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
        except Exception:
            pass
        await callback.answer()
        return

    lines = [title, ""]
    for i, u in enumerate(top):
        place = _TOP_MEDALS[i] if i < 5 else f"{i + 1}."
        count = u[count_field] if count_field in u.keys() else 0
        # VIP badge + frame
        uid_top = u["user_id"] if "user_id" in u.keys() else None
        mora_row = await get_mora(uid_top, chat_id) if uid_top else None
        vip_badge  = " 💎" if (mora_row and mora_row["vip"])  else ""
        frame_e    = ""
        if mora_row and mora_row["top_frame"]:
            from handlers.economy import _frame_emoji
            frame_e = _frame_emoji(mora_row["top_frame"]) + " "
        lines.append(f"{frame_e}{place}{vip_badge} <b>{html.escape(u['full_name'])}</b> — {count} сообщений")

    text = "\n".join(lines)
    if len(text) > 3800:
        lines = [title, ""]
        for i, u in enumerate(top):
            place = _TOP_MEDALS[i] if i < 5 else f"{i + 1}."
            count = u[count_field] if count_field in u.keys() else 0
            uid_top = u["user_id"] if "user_id" in u.keys() else None
            mora_row = await get_mora(uid_top, chat_id) if uid_top else None
            vip_badge  = " 💎" if (mora_row and mora_row["vip"])  else ""
            frame_e    = ""
            if mora_row and mora_row["top_frame"]:
                from handlers.economy import _frame_emoji
                frame_e = _frame_emoji(mora_row["top_frame"]) + " "
            new_line = f"{frame_e}{place}{vip_badge} <b>{html.escape(u['full_name'])}</b> — {count} сообщений"
            if len("\n".join(lines + [new_line])) > 3700:
                lines.append(f"<i>...и ещё {len(top) - i} участников</i>")
                break
            lines.append(new_line)
        text = "\n".join(lines)

    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=_top_keyboard(period, owner_id),
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("pn:"))
async def cb_profile_nav(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    uid = int(parts[2])

    if callback.from_user.id != uid:
        await callback.answer("🚫 Это меню не твоё. Напиши «бот профиль».", show_alert=True)
        return

    if action == "close":
        try:
            await callback.message.delete()
        except Exception:
            pass
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
        except Exception:
            pass

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
        except Exception:
            pass

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
            f"🪙 Мора: <b>{mora_bal}</b> 🪙",
        ]
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

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎨 Тема", callback_data=f"pn:themes:{uid}"),
                InlineKeyboardButton(text="🏅 Бейджи", callback_data=f"pn:badges:{uid}"),
            ],
            [
                InlineKeyboardButton(text="🏆 Топ чата", callback_data=f"top:{uid}:a"),
                InlineKeyboardButton(text="⭐ Репутация", callback_data=f"pn:rep:{uid}"),
            ],
            [
                InlineKeyboardButton(text="❌ Закрыть", callback_data=f"pn:close:{uid}"),
            ],
        ])
        try:
            await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

    elif action == "themes":
        from config import PROFILE_THEMES, COSMETIC_TIER_LABELS
        chat_id = callback.message.chat.id
        if callback.from_user.id != uid:
            await callback.answer("🚫 Не твоё меню.", show_alert=True)
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
        except Exception:
            pass

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
        except Exception:
            pass

    await callback.answer()


@router.message(BotCommand("айди", "id", "мой айди", "chatid"))
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
    """Show detailed info about the current chat — useful for whitelist management."""
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
    if is_group:
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

    lines += [
        "",
        sep,
        f"⚠️ Варны: {warns_line}  |  📊 {status}",
    ]
    if bio:
        lines.append(f"\n📝 <i>{html.escape(bio)}</i>")

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

    if theme["footer"]:
        lines.append(f"\n{theme['footer']}")

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
    if callback.from_user.id != uid:
        await callback.answer("🚫 Не твоё меню.", show_alert=True)
        return
    await set_active_theme(uid, callback.message.chat.id, key)
    await callback.answer(f"✅ Тема «{key}» активирована!")
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("theme_buy:"))
async def cb_theme_buy(callback: CallbackQuery):
    from config import PROFILE_THEMES
    from database.db import deduct_mora as _deduct
    parts = callback.data.split(":")
    uid, key = int(parts[1]), parts[2]
    if callback.from_user.id != uid:
        await callback.answer("🚫 Не твоё меню.", show_alert=True)
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
    ok, new_bal = await _deduct(uid, chat_id, price)
    if not ok:
        await callback.answer("❌ Не удалось списать Мору.", show_alert=True)
        return
    await add_user_theme(uid, chat_id, key, "shop")
    await set_active_theme(uid, chat_id, key)
    await callback.answer(f"✅ Тема «{theme['name']}» куплена и активирована!")
    try:
        await callback.message.delete()
    except Exception:
        pass


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


@router.message(BotCommand("инфо", "info", "кто это"))
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

    status = "🔴 Заблокирован" if banned else "🟢 Активен"
    warns_line = f"{warns_n}/{MAX_WARNS}" if warns_n else "нет"

    from database.db import xp_for_level
    next_xp = xp_for_level(lvl + 1)

    lines = [
        f"🔍 <b>Кто это?</b>\n",
        f"🏷 Имя: {user_mention(user['user_id'], user['full_name'])}",
        f"📛 Username: @{user['username'] or 'скрыт'}",
        f"🆔 ID: <code>{user['user_id']}</code>",
        f"🎖 Ранг: {rank_name(rank, title)}",
        f"💬 Сообщений: {msgs}",
        f"⭐ Репутация: <b>{rep:+d}</b>",
        f"🌟 Уровень: <b>{lvl}</b>  |  {xp}/{next_xp} XP",
        f"⚠️ Предупреждения: {warns_line}",
        f"📊 Статус: {status}",
        f"🟢 Первая активность: {_fmt_dt(stats['first_active'] if stats else None)}",
        f"🔵 Последняя активность: {_fmt_dt(stats['last_active'] if stats else None)}",
    ]
    if bio:
        lines.append(f"\n📝 Bio: <i>{html.escape(bio)}</i>")

    # Брак
    if message.chat.type in ("group", "supergroup"):
        marriage = await get_marriage(uid, message.chat.id)
        if marriage:
            partner = await get_user(marriage["partner_id"])
            partner_name = html.escape(partner["full_name"]) if partner else "?"
            lines.append(f"💍 Партнёр: {user_mention(marriage['partner_id'], partner_name)}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(BotCommand("топ", "top", "активность"))
async def cmd_top(message: Message, cmd_args: str):
    arg = (cmd_args or "").strip().lower()

    if arg in ("день", "day", "д"):
        top = await get_daily_top(message.chat.id, 500)
        title = "📅 <b>Рейтинг активных за сегодня:</b>"
        count_field = "dc"
        count_label = "сообщений"
    elif arg in ("неделя", "week", "н"):
        top = await get_weekly_top(message.chat.id, 500)
        title = "📆 <b>Рейтинг активных за неделю:</b>"
        count_field = "wc"
        count_label = "сообщений"
    else:
        top = await get_top_by_messages_in_chat(message.chat.id, 500)
        title = "🏆 <b>Рейтинг активных за всё время:</b>"
        count_field = "message_count"
        count_label = "сообщений"

    if not top:
        await message.answer("📊 Статистика пока пуста.")
        return

    lines: list[str] = [title, ""]
    for i, u in enumerate(top):
        place = _TOP_MEDALS[i] if i < 5 else f"{i + 1}."
        count = u[count_field] if count_field in u.keys() else 0
        uid_top = u["user_id"] if "user_id" in u.keys() else None
        mora_row = await get_mora(uid_top, message.chat.id) if uid_top else None
        vip_badge = " 💎" if (mora_row and mora_row["vip"]) else ""
        frame_e = ""
        if mora_row and mora_row["top_frame"]:
            from handlers.economy import _frame_emoji
            frame_e = _frame_emoji(mora_row["top_frame"]) + " "
        lines.append(f"{frame_e}{place}{vip_badge} <b>{html.escape(u['full_name'])}</b> — {count} {count_label}")

    period_code = "d" if arg in ("день", "day", "д") else ("w" if arg in ("неделя", "week", "н") else "a")
    text = "\n".join(lines)
    if len(text) > 3800:
        lines = [title, ""]
        for i, u in enumerate(top):
            place = _TOP_MEDALS[i] if i < 5 else f"{i + 1}."
            count = u[count_field] if count_field in u.keys() else 0
            uid_top2 = u["user_id"] if "user_id" in u.keys() else None
            mora_row2 = await get_mora(uid_top2, message.chat.id) if uid_top2 else None
            vip_badge2 = " 💎" if (mora_row2 and mora_row2["vip"]) else ""
            frame_e2 = ""
            if mora_row2 and mora_row2["top_frame"]:
                from handlers.economy import _frame_emoji
                frame_e2 = _frame_emoji(mora_row2["top_frame"]) + " "
            new_line = f"{frame_e2}{place}{vip_badge2} <b>{html.escape(u['full_name'])}</b> — {count} {count_label}"
            if len("\n".join(lines + [new_line])) > 3700:
                lines.append(f"<i>...и ещё {len(top) - i} участников</i>")
                break
            lines.append(new_line)
        text = "\n".join(lines)
    await message.answer(text, parse_mode="HTML", reply_markup=_top_keyboard(period_code, message.from_user.id))


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
    except Exception:
        pass

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

