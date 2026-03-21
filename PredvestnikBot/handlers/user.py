from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from datetime import datetime
from zoneinfo import ZoneInfo
import html

from config import REPORT_NOTIFY_RANK
from database.db import (
    get_daily_top, get_marriage, get_staff_in_chat, get_top_by_messages_in_chat,
    get_top_by_xp_in_chat, get_user, get_user_stats, get_weekly_top, set_bio_in_chat,
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


# ─── Inline-помощь (Вариант K) ────────────────────────────────────────────────

# Разделы справки: (id, emoji, label, min_rank, текст)
def _help_sections() -> list[tuple[str, str, str, str, str]]:
    from config import MAX_WARNS
    return [
        (
            "profile", "👤", "Профиль", "user",
            "👤 <b>Профиль</b>\n\n"
            "  <code>бот я</code> — свой профиль (уровень, XP, репа, bio)\n"
            "  <code>бот инфо [@юзер|ответ]</code> — краткая инфо о пользователе\n"
            "  <code>бот досье [@юзер|ответ]</code> — полная анкета\n"
            "  <code>бот айди [@юзер|ответ]</code> — Telegram ID\n"
            "  <code>бот обо мне [текст]</code> — задать биографию в этом чате\n"
            "  <code>бот жалоба [причина]</code> — анонимная жалоба (ответом на сообщение)",
        ),
        (
            "xp", "⭐", "Репутация & XP", "user",
            "⭐ <b>Репутация & XP</b>\n\n"
            "  <code>+</code> ответом — дать +1 репутацию (раз в 24 ч)\n"
            "  <code>бот репутация [@юзер]</code> — посмотреть репутацию\n"
            "  <code>бот топ репутация</code> — топ-10 по репутации\n"
            "  <code>бот уровень [@юзер]</code> — текущий уровень и XP\n"
            "  <code>бот топ уровень</code> — топ-10 по уровням\n"
            "  <code>бот задание</code> — ежедневное задание (+XP за выполнение)",
        ),
        (
            "fun", "🎉", "Развлечения", "user",
            "🎉 <b>Развлечения</b>\n\n"
            "👊 <b>Действия</b> (ответом или <code>бот пни @юзер</code>)\n"
            "  <code>пни · укуси · обними · шлёпни</code>\n"
            "  <code>лизни · погладь · кинь</code>\n\n"
            "💍 <b>Отношения</b>\n"
            "  <code>бот брак @юзер</code> — предложить пожениться\n"
            "  <code>бот пара</code> — показать партнёра и стаж\n"
            "  <code>бот развод</code> — расторгнуть брак",
        ),
        (
            "info", "📋", "Инфо & чат", "user",
            "📋 <b>Инфо & чат</b>\n\n"
            "  <code>бот топ</code> — топ-10 активных за всё время\n"
            "  <code>бот правила</code> — правила чата\n"
            "  <code>бот время [город]</code> — текущее время\n"
            "  <i>└ Москва, Берлин, Лондон, Нью-Йорк, Токио, Дубай…</i>\n"
            "  <code>бот наши ссылки</code> — соцсети чата (TikTok, YouTube…)\n"
            "  <code>#название</code> — показать сохранённую заметку\n"
            "  <code>бот автор</code> — создатель этого бота",
        ),
        (
            "limits", "⚠️", "Мут & варны", "moderator",
            f"⚠️ <b>Мут & варны</b>\n\n"
            f"  <code>бот варн [@юзер|ответ] [причина]</code> — выдать предупреждение\n"
            f"  <i>└ {MAX_WARNS} варнов подряд → уведомление администраторов</i>\n"
            f"  <code>бот предупреждения [@юзер|ответ]</code> — посмотреть варны\n"
            f"  <code>бот снять варн [@юзер|ответ]</code> — снять 1 предупреждение\n\n"
            f"  <code>бот мут [@юзер|ответ] [время] [причина]</code> — заглушить\n"
            f"  <i>└ время: <code>30с</code> · <code>10м</code> · <code>2ч</code> · <code>1д</code> — по умолч. 5 мин.</i>\n"
            f"  <code>бот размут [@юзер|ответ]</code> — снять мут",
        ),
        (
            "mod", "🔨", "Модерация", "moderator",
            "🔨 <b>Модерация</b>\n\n"
            "🚫 <b>Блокировки & кик</b>\n"
            "  <code>бот бан [@юзер|ответ] [причина]</code> — заблокировать в чате\n"
            "  <code>бот разбан [@юзер|ответ]</code> — снять бан\n"
            "  <code>бот кик [@юзер|ответ] [причина]</code> — выгнать (может вернуться)\n"
            "  <code>бот баны</code> — список забаненных\n\n"
            "📌 <b>Сообщения</b>\n"
            "  <code>бот закрепить</code> (ответом) — закрепить сообщение\n"
            "  <code>бот открепить</code> — открепить последнее\n"
            "  <code>бот очистить N</code> — удалить N последних сообщений\n"
            "  <i>└ или ответом — удалит всё от той точки до команды</i>\n\n"
            "📒 <b>Заметки & автоответы</b>\n"
            "  <code>бот заметка [имя] [текст]</code> — сохранить заметку\n"
            "  <code>бот убрать заметку [имя]</code> — удалить заметку\n"
            "  <code>бот автоответ [фраза] | [ответ]</code> — авто-ответ на фразу\n"
            "  <code>бот убрать ответ [фраза]</code> — удалить авто-ответ\n"
            "  <code>бот блок [слово]</code> — запретить слово\n"
            "  <code>бот разблок [слово]</code> — разрешить слово\n"
            "  <code>бот чс</code> — просмотр и управление чёрным списком слов\n"
            "  <code>бот ушли [N]</code> — последние N участников, покинувших чат\n\n"
            "🚷 <b>ЧС по ID пользователя</b>\n"
            "  <i>└ при выходе/кике бот предложит добавить участника в ID-бан\n"
            "     при попытке зайти — автоматический кик + уведомление владельцев</i>\n"
            "  <code>бот юзбан [ID]</code> — добавить ID в ЧС\n"
            "  <code>бот юзразбан [ID]</code> — убрать ID из ЧС\n"
            "  <code>бот юзбаны</code> — список забаненных по ID",
        ),
        (
            "settings", "⚙️", "Настройки", "admin_junior",
            "⚙️ <b>Настройки чата</b>\n\n"
            "👥 <b>Персонал</b>\n"
            "  <code>бот ранг [ранг] [@юзер|ответ]</code> — выдать ранг\n"
            "  <i>└ user · moderator · admin_junior · admin_senior · co_owner · owner</i>\n"
            "  <code>бот состав</code> — список администрации\n"
            "  <code>бот статистика</code> — статистика чата\n\n"
            "🎭 <b>Роли сообщества</b>\n"
            "  <code>бот выдать роль [@юзер|ответ] [роль]</code> — выдать роль\n"
            "  <code>бот снять роль [@юзер|ответ] [роль]</code> — снять роль\n"
            "  <code>бот роли</code> — список всех ролей\n"
            "  <code>бот мои роли</code> — твои текущие роли\n\n"
            "💬 <b>Приветствие & правила</b>\n"
            "  <code>бот правила установить [текст]</code> — задать правила\n"
            "  <code>бот приветствие [текст]</code> — авто-приветствие новых\n"
            "  <i>└ переменные: {name} · {username} · {chat}</i>\n"
            "  <code>бот прощание [текст]</code> — авто-прощание при выходе\n"
            "  <code>бот тег входа [вкл/выкл]</code> — тегать всех при входе\n\n"
            "🔒 <b>Замки контента</b>\n"
            "  <code>бот замок [тип]</code> — заблокировать тип контента\n"
            "  <code>бот открыть [тип]</code> — разрешить тип контента\n"
            "  <code>бот замки</code> — посмотреть все замки\n"
            "  <i>└ links · stickers · gifs · forwards · voice · video · photo · audio</i>\n\n"
            "🛡 <b>Антифлуд & чистка</b>\n"
            "  <code>бот антифлуд N</code> — макс. N сообщений за 5 сек.\n"
            "  <code>бот антифлуд выкл</code> — отключить\n"
            "  <code>бот чистка [N]</code> — заблокировать чат + отчёт активности\n"
            "  <code>бот чистка открыть</code> — разблокировать чат\n"
            "  <code>бот чистка порог N</code> — порог мин. сообщений в неделю\n"
            "  <code>бот отдых @user [дней]</code> — освобождение от чистки (7 дней)\n"
            "  <code>бот отдых снять @user</code> — убрать с отдыха\n"
            "  <code>бот отдых список</code> — кто сейчас на отдыхе\n"
            "  <code>бот фильтрмат [вкл/выкл]</code> — авто-удаление мата\n\n"
            "🔗 <b>Соцсети</b>\n"
            "  <code>бот соцсети tiktok [URL]</code> — ссылка на TikTok\n"
            "  <code>бот соцсети youtube [URL]</code> — ссылка на YouTube\n"
            "  <code>бот соцсети instagram [URL]</code> — ссылка на Instagram\n"
            "  <code>бот история чата</code> — как включить историю для новых",
        ),
        (
            "owner", "🔱", "Владелец", "owner",
            "🔱 <b>Владелец+</b>\n\n"
            "  <code>бот совладелец [@юзер|ответ]</code> — назначить со-владельца\n\n"
            "🎭 <b>Управление ролями</b>\n"
            "  <code>бот добавить роль [эмодзи] название [описание]</code> — создать роль\n"
            "  <code>бот убрать роль название</code> — удалить роль\n"
            "  <code>бот сменить роль [@юзер|ответ] роль</code> — принудительно сменить роль\n"
            "  <i>└ освобождает старую роль, занимает новую; требует co_owner+</i>\n\n"
            "📣 <b>Рассылка</b>\n"
            "  <code>бот колл [текст]</code> — тегнуть всех участников\n"
            "  <code>бот колл #все [текст]</code> — то же самое\n"
            "  <code>бот колл #юзеры [текст]</code> — только обычные участники\n"
            "  <code>бот колл #стафф [текст]</code> — только стафф\n"
            "  <code>бот колл #модеры [текст]</code> — модераторы+\n"
            "  <code>бот колл #админы [текст]</code> — администраторы+",
        ),
        (
            "dev", "🛠", "Разработчик", "developer",
            "🛠 <b>Разработчик</b>\n\n"
            "  <code>бот разработчик</code> — панель разработчика\n"
            "  <code>бот сетюзер @user поле значение</code> — редактор данных\n"
            "  <code>бот прибавитьxp @user N</code> — добавить XP\n"
            "  <code>бот сеттитул @user титул</code> — кастомный титул\n\n"
            "📡 <b>Типы каналов</b>\n"
            "  <code>бот канал правила [chat_id]</code> — канал с правилами и ролями\n"
            "  <code>бот канал основной [chat_id]</code> — основной чат сообщества\n"
            "  <code>бот канал удалить правила|основной</code> — убрать тип\n"
            "  <code>бот каналы</code> — все настроенные каналы\n\n"
            "🔐 <b>Белый список групп</b>\n"
            "  <code>бот разрешить [chat_id]</code> — добавить группу в список\n"
            "  <code>бот запретить [chat_id]</code> — убрать из списка\n"
            "  <code>бот группы</code> — показать все разрешённые группы\n"
            "  <i>└ пустой список = бот работает во всех чатах</i>\n\n"
            "📣 <b>Админ-группы (уведомления)</b>\n"
            "  <code>бот админгруппа [chat_id]</code> — добавить группу для уведомлений\n"
            "  <code>бот удадмингруппу [chat_id]</code> — удалить админ-группу\n"
            "  <code>бот админгруппы</code> — показать все админ-группы\n"
            "  <i>└ репорты, варны, авто-кик и пр. пойдут в эти группы</i>",
        ),
    ]


def _help_menu_text(rank: str) -> str:
    rn = rank_name(rank)
    return (
        f"📖 <b>Справка по боту</b>  ·  ранг: {rn}\n\n"
        "Выбери раздел 👇\n\n"
        "<i>ℹ️ Команды вводятся без «/» — просто текстом в чат.\n"
        "💬 Таргет: [@юзер] или ответом на сообщение.</i>"
    )


def _help_keyboard(user_id: int, lvl: int) -> InlineKeyboardMarkup:
    sections = _help_sections()
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for sid, emoji, label, min_rank, _text in sections:
        if lvl < rank_level(min_rank):
            continue
        row.append(InlineKeyboardButton(
            text=f"{emoji} {label}",
            callback_data=f"h:{sid}:{user_id}:{lvl}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        text="❌ Закрыть",
        callback_data=f"h:close:{user_id}:{lvl}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _back_keyboard(user_id: int, lvl: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️ Меню", callback_data=f"h:menu:{user_id}:{lvl}"),
            InlineKeyboardButton(text="❌ Закрыть", callback_data=f"h:close:{user_id}:{lvl}"),
        ],
    ])


def _top_keyboard(active: str) -> InlineKeyboardMarkup:
    periods = [("📅 День", "d"), ("📆 Неделя", "w"), ("🏆 Всё время", "a")]
    buttons = []
    for label, code in periods:
        text = f"· {label} ·" if code == active else label
        buttons.append(InlineKeyboardButton(text=text, callback_data=f"top:{code}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


@router.message(BotCommand("помощь", "help", "команды", "справка"))
async def cmd_help(message: Message, cmd_args: str):
    from config import DEVELOPER_ID
    stats = await get_user_stats(message.from_user.id, message.chat.id)
    rank = stats["rank"] if stats else "user"
    if DEVELOPER_ID and message.from_user.id == DEVELOPER_ID:
        rank = "developer"
    lvl = rank_level(rank)
    uid = message.from_user.id

    text = _help_menu_text(rank)
    kb = _help_keyboard(uid, lvl)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("h:"))
async def cb_help(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer()
        return
    section, owner_id_str, lvl_str = parts[1], parts[2], parts[3]

    try:
        owner_id = int(owner_id_str)
        lvl = int(lvl_str)
    except ValueError:
        await callback.answer()
        return

    # Только автор может нажимать кнопки
    if callback.from_user.id != owner_id:
        await callback.answer("🚫 Эта справка не твоя. Напиши «бот помощь».", show_alert=True)
        return

    if section == "close":
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()
        return

    if section == "menu":
        # Определяем ранг по lvl для отображения
        rank_names_by_lvl = {
            rank_level(r): r
            for r in ("user", "moderator", "admin_junior", "admin_senior", "co_owner", "owner", "developer")
        }
        rank = rank_names_by_lvl.get(lvl, "user")
        text = _help_menu_text(rank)
        kb = _help_keyboard(owner_id, lvl)
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        await callback.answer()
        return

    # Ищем раздел
    sections = _help_sections()
    for sid, _emoji, _label, min_rank, section_text in sections:
        if sid == section:
            if lvl < rank_level(min_rank):
                await callback.answer("🚫 Нет доступа.", show_alert=True)
                return
            kb = _back_keyboard(owner_id, lvl)
            try:
                await callback.message.edit_text(section_text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
            await callback.answer()
            return

    await callback.answer()


@router.callback_query(F.data.startswith("top:"))
async def cb_top(callback: CallbackQuery):
    period = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    from config import TOP_LIMIT

    if period == "d":
        top = await get_daily_top(chat_id, TOP_LIMIT)
        title = "📅 <b>Топ активных за сегодня:</b>"
        count_field = "dc"
    elif period == "w":
        top = await get_weekly_top(chat_id, TOP_LIMIT)
        title = "📆 <b>Топ активных за неделю:</b>"
        count_field = "wc"
    else:
        top = await get_top_by_messages_in_chat(chat_id, TOP_LIMIT)
        title = "🏆 <b>Топ 10 активных за всё время:</b>"
        count_field = "message_count"

    if not top:
        try:
            await callback.message.edit_text(
                "📊 Статистика пока пуста.",
                reply_markup=_top_keyboard(period),
            )
        except Exception:
            pass
        await callback.answer()
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = [title, ""]
    for i, u in enumerate(top):
        place = medals[i] if i < 3 else f"{i + 1}."
        count = u[count_field] if count_field in u.keys() else 0
        lines.append(f"{place} <b>{html.escape(u['full_name'])}</b> — {count} сообщений")

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=_top_keyboard(period),
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("pn:"))
async def cb_profile_nav(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[1]
    uid = int(parts[2])

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
        stats = await get_user_stats(uid, callback.message.chat.id)
        rank    = stats["rank"]         if stats else "user"
        xp      = stats["xp"]          if stats else 0
        lvl_val = stats["level"]        if stats else 1
        rep     = stats["reputation"]   if stats else 0
        msgs    = stats["message_count"] if stats else 0
        bio     = stats["bio"]          if stats else None
        lines = [
            f"👤 <b>Профиль</b>\n",
            f"🏷 Имя: {html.escape(user['full_name'])}",
            f"🆔 ID: <code>{user['user_id']}</code>",
            f"🎖 Ранг: {rank_name(rank)}",
            f"💬 Сообщений: {msgs}",
            f"⭐ Репутация: <b>{rep:+d}</b>",
            f"🌟 Уровень: <b>{lvl_val}</b>",
        ]
        if bio:
            lines.append(f"\n📝 Bio: <i>{html.escape(bio)}</i>")
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏆 Топ чата", callback_data="top:a"),
            InlineKeyboardButton(text="⭐ Репутация", callback_data=f"pn:rep:{uid}"),
        ]])
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
    from config import DEVELOPER_ID
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Тебя ещё нет в базе. Напиши любое сообщение в чат.")
        return

    stats = await get_user_stats(message.from_user.id, message.chat.id)
    rank    = stats["rank"]         if stats else "user"
    # Разработчик всегда получает свой ранг независимо от чата
    if DEVELOPER_ID and message.from_user.id == DEVELOPER_ID:
        rank = "developer"
    warns_n = stats["warns"]        if stats else 0
    xp      = stats["xp"]          if stats else 0
    lvl     = stats["level"]        if stats else 1
    rep     = stats["reputation"]   if stats else 0
    bio     = stats["bio"]          if stats else None
    msgs    = stats["message_count"] if stats else 0
    banned  = stats["is_banned"]    if stats else 0
    title   = stats["custom_title"] if stats else None

    status = "🔴 Заблокирован" if banned else "🟢 Активен"
    from config import MAX_WARNS
    warns_line = "⚠️" * warns_n + f"({warns_n}/{MAX_WARNS})" if warns_n else "нет"

    from database.db import xp_for_level
    next_xp = xp_for_level(lvl + 1)
    bar_filled = min(10, int((xp - xp_for_level(lvl)) / max(1, next_xp - xp_for_level(lvl)) * 10))
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    lines = [
        f"👤 <b>Профиль</b>\n",
        f"🏷 Имя: {html.escape(user['full_name'])}",
        f"📛 Username: @{user['username'] or 'скрыт'}",
        f"🆔 ID: <code>{user['user_id']}</code>",
        f"🎖 Ранг: {rank_name(rank, title)}",
        f"💬 Сообщений: {msgs}",
        f"⭐ Репутация: <b>{rep:+d}</b>",
        f"🌟 Уровень: <b>{lvl}</b>  [{bar}]  {xp}/{next_xp} XP",
        f"⚠️ Предупреждения: {warns_line}",
        f"📊 Статус: {status}",
        f"🟢 Первая активность: {_fmt_dt(stats['first_active'] if stats else None)}",
        f"🔵 Последняя активность: {_fmt_dt(stats['last_active'] if stats else None)}",
    ]
    if bio:
        lines.append(f"\n📝 Bio: <i>{html.escape(bio)}</i>")

    # Брак
    if message.chat.type in ("group", "supergroup"):
        marriage = await get_marriage(message.from_user.id, message.chat.id)
        if marriage:
            partner = await get_user(marriage["partner_id"])
            partner_name = html.escape(partner["full_name"]) if partner else "?"
            lines.append(f"💍 Партнёр: {user_mention(marriage['partner_id'], partner_name)}")

    me_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏆 Топ чата", callback_data="top:a"),
            InlineKeyboardButton(text="⭐ Репутация", callback_data=f"pn:rep:{message.from_user.id}"),
        ],
    ])
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=me_kb)


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
    from config import TOP_LIMIT
    arg = (cmd_args or "").strip().lower()

    if arg in ("день", "day", "д"):
        top = await get_daily_top(message.chat.id, TOP_LIMIT)
        title = "📅 <b>Топ активных за сегодня:</b>"
        count_field = "dc"
        count_label = "сообщений"
    elif arg in ("неделя", "week", "н"):
        top = await get_weekly_top(message.chat.id, TOP_LIMIT)
        title = "📆 <b>Топ активных за неделю:</b>"
        count_field = "wc"
        count_label = "сообщений"
    else:
        top = await get_top_by_messages_in_chat(message.chat.id, TOP_LIMIT)
        title = "🏆 <b>Топ 10 активных за всё время:</b>"
        count_field = "message_count"
        count_label = "сообщений"

    if not top:
        await message.answer("📊 Статистика пока пуста.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = [title, ""]
    for i, u in enumerate(top):
        place = medals[i] if i < 3 else f"{i + 1}."
        count = u[count_field] if count_field in u.keys() else 0
        lines.append(f"{place} <b>{html.escape(u['full_name'])}</b> — {count} {count_label}")

    period_code = "d" if arg in ("день", "day", "д") else ("w" if arg in ("неделя", "week", "н") else "a")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=_top_keyboard(period_code))


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
async def cmd_creator(message: Message, cmd_args: str):
    """Показать информацию о создателе бота."""
    from config import DEVELOPER_ID, BOT_CREATOR_NAME, BOT_CREATOR_USERNAME
    name = html.escape(BOT_CREATOR_NAME or "Разработчик")
    if BOT_CREATOR_USERNAME:
        contact = f"@{BOT_CREATOR_USERNAME}"
    else:
        contact = f"<a href='tg://user?id={DEVELOPER_ID}'>{name}</a>"
    await message.answer(
        f"🛠 <b>Создатель бота</b>\n\n"
        f"👤 {contact}\n"
        f"🆆 Telegram ID: <code>{DEVELOPER_ID}</code>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

