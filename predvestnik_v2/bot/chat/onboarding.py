"""Подключение бота к чату за руку: как добавить, какие права выдать, кого назначить модераторами.

Два места, один набор экранов:
 - личка с ботом (/start, /setup, «бот настройка»): главный экран, «как добавить», «мои чаты», настройка выбранного чата;
 - сам чат: когда бота добавили, он пишет чек-лист «что уже есть и чего не хватает», сам обновляет его, как только выдали права,
   и зовёт продолжить в личке (кнопка-ссылка). Человеку, который добавил бота, чек-лист приходит в личку сам, если он уже писал боту.
Новичку в личке: приветствие картинкой по имени, «Как подключить» (3 шага на картинке), «Я просто играю» (что есть на сайте)
и короткая подсказка в ответ на «привет»; картинки рисует services/welcome_images.py и показывает не чаще раза в 6 часов.
Логика проверки чата, журнал шагов и напоминания — services/chat_setup.py; здесь тексты, кнопки и обработчики."""
from __future__ import annotations

import html
import time

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from bot.chat import ranks
from bot.chat.access import is_developer
from bot.chat.framework import Ctx, registry
from bot.chat.style import quote
from services import chat_setup as cs

router = Router(name="chat_onboarding")

Screen = tuple[str, InlineKeyboardMarkup]
RIGHT_DELETE = "Удаление сообщений"        # так пункты называются в правах администратора Telegram
RIGHT_RESTRICT = "Блокировка пользователей"


class OnbCB(CallbackData, prefix="onb"):
    a: str       # действие: home, add, play, my, chat, chk, rights, trouble, staff, staffok, adm, admcode, guide
    c: int = 0   # чат, к которому относится кнопка (0 — ни к какому)


def _e(value) -> str:
    return html.escape(str(value))


def _btn(text: str, action: str, chat: int = 0) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=OnbCB(a=action, c=chat).pack())


def _url(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def setup_link(username: str, chat_id: int) -> str:
    """Ссылка «продолжить в личке»: бот открывается сразу на настройке этого чата."""
    return f"https://t.me/{username}?start=setup_{chat_id}"


# ── Чек-лист ────────────────────────────────────────────────────────────────

def missing_rights(s: cs.Setup) -> list[str]:
    out = []
    if not s.can_delete:
        out.append(RIGHT_DELETE)
    if not s.can_restrict:
        out.append(RIGHT_RESTRICT)
    return out


def checklist(s: cs.Setup, with_check: bool = False) -> str:
    """Короткий список «что уже есть» для сообщения в чате. with_check добавляет строку про первую команду."""
    mark = lambda ok: "✅" if ok else "❌"
    lines = [
        f"{mark(s.present)} Я в чате",
        f"{mark(s.admin)} Я администратор",
        f"{mark(s.can_delete)} {RIGHT_DELETE}",
        f"{mark(s.can_restrict)} {RIGHT_RESTRICT}",
    ]
    if with_check and s.ready:
        lines.append("✅ Отвечаю на команды" if s.verified else "⏳ Жду первую команду в чате")
    return quote(lines)


def roadmap(s: cs.Setup) -> str:
    """Весь путь настройки одним списком: что пройдено (✅), где сейчас (👉), что потом (▫️). Два последних шага по желанию."""
    if s.ready:
        rights = "Права администратора"
    elif s.present and s.admin:
        rights = "Права администратора: включите " + " и ".join(f"«{r.lower()}»" for r in missing_rights(s))
    else:
        rights = "Права администратора"
    steps = [   # (пройден, текст, по желанию)
        (s.present, "Бот в чате", False),
        (s.ready, rights, False),
        (s.ready and s.verified, "Проверка: бот отвечает на команды" if s.ready and s.verified
         else "Проверка: напишите в чате «бот помощь»", False),
        (s.staff > 0, f"Модераторы: назначены {s.staff}" if s.staff else "Модераторы (по желанию)", True),
        (bool(s.admin_chat), f"Админ-чат «{_e(s.admin_chat['title'])}»" if s.admin_chat else "Админ-чат (по желанию)", True),
    ]
    todo = [i for i, (done, _, optional) in enumerate(steps) if not done and not optional] or \
           [i for i, (done, _, _) in enumerate(steps) if not done]
    current = todo[0] if todo else -1
    lines = [f"{'✅' if done else '👉' if i == current else '▫️'} {i + 1}. {text}" for i, (done, text, _) in enumerate(steps)]
    return quote(lines)


def grant_steps(s: cs.Setup, username: str) -> str:
    """Что нажать, чтобы выдать права: короткая инструкция под чек-листом."""
    missing = missing_rights(s)
    need = " и ".join(f"<b>«{r}»</b>" for r in missing)
    pick = ("пункт " if len(missing) == 1 else "пункты ") + need
    if s.admin:
        return (f"Откройте информацию о чате → <b>Изменить</b> → <b>Администраторы</b> → @{_e(username)} и включите {pick}. "
                "Сохраните галочкой ✓.")
    return (f"1. Откройте информацию о чате (нажмите на его название) → <b>Изменить</b> → <b>Администраторы</b> → "
            f"<b>Добавить администратора</b>.\n2. Выберите @{_e(username)} и включите {pick}.\n3. Сохраните галочкой ✓.")


def next_step(s: cs.Setup) -> str:
    """Одно действие, которое нужно сделать прямо сейчас."""
    if not s.present:
        return "Меня нет в этом чате. Нажмите «Добавить бота» и выберите чат."
    if not s.ready:
        if s.admin:
            return (f"Я уже администратор, осталось включить: {', '.join(missing_rights(s)).lower()}. "
                    "Кнопка «Как выдать права» покажет где, это минута.")
        return "Сделайте меня администратором: кнопка «Как выдать права» покажет по шагам, это минута."
    if not s.verified:
        return ("Откройте чат и напишите <code>бот помощь</code>. Когда я отвечу, подключение завершено. "
                "Молчу? Нажмите «Не получается».")
    if not s.staff:
        return "Назначьте модераторов, чтобы они могли выдавать варны и муты: кнопка «Модераторы». Это по желанию."
    if not s.admin_chat:
        return "Всё работает. По желанию привяжите отдельный чат для администраторов: кнопка «Админ-чат»."
    return "Всё настроено. Все команды: <code>бот помощь</code>."


# ── Экраны чата ─────────────────────────────────────────────────────────────

def group_screen(s: cs.Setup, username: str, reminder: bool = False) -> Screen:
    """Сообщение в самом чате. Правки и назначения делаются в личке: в чате только чек-лист, проверка и ссылка."""
    if s.ready:
        if s.verified:
            text = ("✅ <b>Бот подключён и отвечает</b>\n" + checklist(s, True) +
                    "\nКоманды начинаются со слова «бот». Что дальше:\n"
                    "• <code>бот помощь</code> — все команды\n"
                    "• <code>бот ранги</code> — кто с каким рангом\n"
                    "• <code>бот сайт</code> — сайт Предвестника: профиль, игры, питомцы\n"
                    "• модераторов и админ-чат удобно настроить в личке: кнопка ниже")
        else:
            text = ("✅ <b>Права получены</b>\n" + checklist(s, True) +
                    "\n<b>Последний шаг.</b> Напишите в этом чате <code>бот помощь</code>. Когда я отвечу, подключение завершено.\n"
                    "Команды начинаются со слова «бот».")
        kb = _kb([_url("📩 Продолжить в личке", setup_link(username, s.chat_id))],
                 [_btn("📖 Что умеет бот", "guide", s.chat_id)])
        return text, kb
    head = ("⏰ <b>Мне всё ещё не хватает прав.</b> Без них я почти ничего не могу в этом чате.\n" if reminder else
            "👋 <b>Я Предвестник</b>: модерация, ранги, профили, игры и чистка неактивных.\n"
            "Чтобы работать, мне нужны права администратора.\n")
    text = (head + checklist(s) +
            "\n<b>Что сделать</b> (владельцу или администратору чата):\n" + grant_steps(s, username) +
            "\n\nКак только права появятся, я сам напишу здесь. Кнопка «Проверить» обновит этот список сразу.")
    if not s.supergroup:
        text += "\n<i>Это обычная группа: теги участников в ней недоступны, остальное работает.</i>"
    kb = _kb([_btn("🔄 Проверить", "chk", s.chat_id)],
             [_url("📩 Подробно в личке", setup_link(username, s.chat_id))])
    return text, kb


def chat_screen(s: cs.Setup, username: str, intro: str = "") -> Screen:
    """Настройка чата в личке: путь из пяти шагов с отметкой «вы здесь», что делать сейчас и кнопки под текущее состояние."""
    head = f"{intro}\n\n" if intro else ""
    text = (f"{head}⚙️ <b>{_e(s.title)}</b>\n<b>Путь настройки</b>\n" + roadmap(s) +
            f"\n<b>Сейчас:</b> {next_step(s)}")
    if not s.supergroup:
        text += "\n<i>Это обычная группа: теги участников в ней недоступны, остальное работает.</i>"
    if not s.live:
        text += "\n<i>Telegram сейчас не ответил, показаны последние данные. Нажмите «Проверить» ещё раз.</i>"
    if not s.present:
        rows = [[_url("➕ Добавить бота в чат", cs.add_url(username))], [_btn("◀️ Мои чаты", "my")]]
    elif not s.ready:
        rows = [[_btn("🔑 Как выдать права", "rights", s.chat_id)],
                [_btn("🔄 Проверить", "chk", s.chat_id), _btn("🆘 Не получается", "trouble", s.chat_id)],
                [_btn("◀️ Мои чаты", "my")]]
    else:
        rows = [[_btn("👥 Модераторы", "staff", s.chat_id), _btn("🔗 Админ-чат", "adm", s.chat_id)],
                [_btn("📖 Что умеет бот", "guide", s.chat_id)]]
        if s.verified:
            rows.append([_btn("🔄 Обновить", "chk", s.chat_id), _btn("◀️ Мои чаты", "my")])
        else:
            rows.append([_btn("🔄 Проверить", "chk", s.chat_id), _btn("🆘 Не получается", "trouble", s.chat_id)])
            rows.append([_btn("◀️ Мои чаты", "my")])
    return text, _kb(*rows)


def rights_screen(s: cs.Setup, username: str) -> Screen:
    text = (f"🔑 <b>Как выдать права · {_e(s.title)}</b>\n\n"
            f"1. Откройте чат «{_e(s.title)}» и нажмите на его название вверху.\n"
            "2. <b>Изменить</b> (карандаш ✏️) → <b>Администраторы</b> → <b>Добавить администратора</b>.\n"
            f"3. Найдите и выберите @{_e(username)}.\n"
            "4. Включите два пункта:\n" +
            quote([f"✅ {RIGHT_DELETE} (Delete messages)", f"✅ {RIGHT_RESTRICT} (Ban users)"]) +
            "Остальное можно оставить выключенным.\n"
            "5. Нажмите ✓ в углу, вернитесь сюда и нажмите «Проверить».\n\n"
            "<i>Названия пунктов зависят от версии Telegram и языка: ищите про удаление сообщений и про блокировку участников. "
            "Без этих прав я не вижу обычные сообщения, не могу удалять и мутить. Выдать их может владелец чата "
            "или администратор с правом добавлять админов.</i>\n\n"
            "⚡ <b>Быстрее:</b> кнопка ниже откроет выбор чата, выберите этот, и Telegram сам предложит нужные права. "
            "Не вышло — идите по шагам выше.")
    return text, _kb([_url("⚡ Выдать права одним нажатием", cs.add_url(username))],
                     [_btn("🔄 Проверить", "chk", s.chat_id), _btn("🆘 Не получается", "trouble", s.chat_id)],
                     [_btn("◀️ Назад", "chat", s.chat_id)])


def trouble_screen(s: cs.Setup) -> Screen:
    text = ("🆘 <b>Не получается?</b>\n\n"
            "<b>Нет кнопки «Добавить администратора».</b> Админов назначает владелец чата или администратор с правом "
            "«Добавление администраторов». Перешлите ему эту инструкцию.\n\n"
            "<b>Меня нет в списке выбора.</b> Значит, я не в чате: нажмите «Добавить бота» и выберите чат.\n\n"
            "<b>Права выдал, но «Проверить» говорит, что их нет.</b> Проверьте, что включены оба пункта "
            f"(«{RIGHT_DELETE}» и «{RIGHT_RESTRICT}») и вы нажали ✓ сохранить.\n\n"
            "<b>Права есть, а на «бот помощь» я молчу.</b> Команда должна начинаться со слова «бот» и быть обычным сообщением. "
            "Если вы администратор, выключите себе «Анонимность» в правах администратора: от имени чата я не узнаю, кто пишет. "
            "Ещё проверьте, что чат не закрыт для сообщений.\n\n"
            "<b>Админ пишет, а ранг не работает.</b> Та же причина: «Анонимность» у него включена.")
    return text, _kb([_btn("🔄 Проверить", "chk", s.chat_id)], [_btn("◀️ Назад", "chat", s.chat_id)])


# Что разрешает ранг: берём реальные пороги чата (их можно менять), а не цифры из головы.
LEGEND_ACTIONS = (("warn", "варны"), ("mute", "муты"), ("kick", "кики"), ("ban", "баны"), ("close_chat", "закрытие чата"))


def rank_legend(rights: dict[str, int], rank_values: list[int]) -> str:
    """По строке на каждый предложенный ранг: что он сможет в этом чате."""
    lines = []
    for rank in sorted(set(rank_values), reverse=True):
        can = [label for key, label in LEGEND_ACTIONS if rank >= rights.get(key, 99)]
        lines.append(f"{ranks.rank_name(rank)} — " + (", ".join(can) if can else "смотреть списки санкций"))
    return quote(lines) if lines else ""


def staff_screen(s: cs.Setup, proposals: list[cs.Proposal] | None, done: str = "", legend: str = "") -> Screen:
    back = [_btn("◀️ Назад", "chat", s.chat_id)]
    if proposals is None:
        return (f"👥 <b>Модераторы · {_e(s.title)}</b>\n\nTelegram не отдал список администраторов. Попробуйте ещё раз.",
                _kb([_btn("🔄 Ещё раз", "staff", s.chat_id)], back))
    head = f"{done}\n\n" if done else ""
    if not proposals:
        return (f"{head}👥 <b>Модераторы · {_e(s.title)}</b>\n\nПредлагать больше некого: у администраторов чата ранг в боте уже есть "
                "или права у них только косметические. Выдать ранг вручную: <code>бот ранг, @ник модератор</code>. "
                "Кто есть сейчас: <code>бот ранги</code>.",
                _kb(back))
    lines = [f"{_e(('@' + p.username) if p.username else p.name)} → {_e(ranks.rank_name(p.rank))}" for p in proposals[:25]]
    more = f"\nи ещё {len(proposals) - 25}" if len(proposals) > 25 else ""
    text = (f"{head}👥 <b>Модераторы · {_e(s.title)}</b>\n\n"
            "Я вижу администраторов чата в Telegram и могу выдать им ранги в боте по их правам:\n" + quote(lines) + more +
            ("\n<b>Что это даст в вашем чате:</b>\n" + legend if legend else "") +
            "\nРанг можно поменять потом: <code>бот ранг, @ник модератор</code>. Все пороги: <code>бот права</code>.")
    return text, _kb([_btn("✅ Назначить всех", "staffok", s.chat_id)], back)


def admin_screen(s: cs.Setup, code: str | None = None) -> Screen:
    back = [_btn("◀️ Назад", "chat", s.chat_id)]
    if code:
        text = (f"🔗 <b>Админ-чат · {_e(s.title)}</b>\n\n"
                "1. Создайте группу для администраторов и добавьте туда бота.\n"
                "2. Напишите в ней в течение 10 минут (это должен сделать владелец обеих групп):\n"
                f"<blockquote><code>бот админ чат {code}</code></blockquote>"
                "Дальше жалобы, предупреждения о чистке и другие служебные сообщения будут приходить туда, а не в основной чат.")
        return text, _kb([_btn("🔑 Новый код", "admcode", s.chat_id)], back)
    if s.admin_chat:
        text = (f"🔗 <b>Админ-чат · {_e(s.title)}</b>\n\nСейчас служебные сообщения идут в «{_e(s.admin_chat['title'])}». "
                "Отвязать: <code>бот отвязать админ чат</code> (в основном чате).")
        return text, _kb([_btn("🔑 Привязать другой", "admcode", s.chat_id)], back)
    text = (f"🔗 <b>Админ-чат · {_e(s.title)}</b>\n\n"
            "Отдельный чат для администраторов. Жалобы, предупреждения о чистке и другие служебные сообщения идут туда, "
            "а основной чат остаётся чистым. Это по желанию: без него всё приходит в сам чат.")
    return text, _kb([_btn("🔑 Получить код", "admcode", s.chat_id)], back)


GUIDE = (
    "📖 <b>Что я умею</b>\n\n"
    "🛡 <b>Модерация.</b> <code>бот мут, @ник 2ч спам</code>, <code>бот варн, @ник 7д флуд</code>, "
    "<code>бот бан, @ник 5д</code>, <code>бот кик, @ник</code>. Кто что может, решает ранг: "
    "<code>бот ранг, @ник модератор</code>, список: <code>бот ранги</code>, пороги: <code>бот права</code>.\n\n"
    "🧹 <b>Чистка.</b> <code>бот чистка, 100</code>: чат закрывается, админам приходят досье на тех, кто написал меньше нормы.\n\n"
    "🔒 <b>Закрытый чат.</b> <code>бот закрыть чат</code> и <code>бот открыть чат</code>.\n\n"
    "🚩 <b>Жалобы.</b> <code>бот жалоба спам в чате</code> ответом на сообщение: модераторы получат её анонимно.\n\n"
    "🏆 <b>Профили и топ.</b> <code>бот я</code>, <code>бот топ</code>, <code>бот тег</code>.\n\n"
    "🎮 <b>Игры.</b> Мафия, Ритм, Сапёр и задания: <code>бот игры</code>, <code>бот мафия</code>, <code>бот квесты</code>.\n\n"
    "🔮 <b>Сайт Предвестника.</b> Профиль, образы, питомцы и игры открываются прямо в Telegram: <code>бот сайт</code>.\n\n"
    "Полный список с примерами: <code>бот помощь</code>."
)


def _site_btn(miniapp_url: str) -> list[InlineKeyboardButton]:
    """Кнопка сайта (мини-приложения): только в личке, в группах Telegram такие кнопки не пускает."""
    if not miniapp_url:
        return []
    from aiogram.types import WebAppInfo
    return [InlineKeyboardButton(text="🔮 Открыть сайт Предвестника", web_app=WebAppInfo(url=miniapp_url))]


def guide_screen(chat_id: int, miniapp_url: str = "") -> Screen:
    return GUIDE, _kb(_site_btn(miniapp_url), [_btn("◀️ Назад", "chat" if chat_id else "home", chat_id)])


# ── Экраны личного чата ─────────────────────────────────────────────────────

def home_screen(username: str, miniapp_url: str = "") -> Screen:
    """Первый экран лички. Главное — подключить бота к своему чату; остальное коротко и по кнопке."""
    text = ("🌘 <b>Предвестник</b> — бот для групп в Telegram\n\n"
            "Добавьте меня в свой чат: я возьму на себя порядок, топ активных, профили и игры. "
            "Подключение занимает пару минут, я веду по шагам и сам проверяю права.\n" +
            quote(["➕ <b>Добавить бота в чат</b> — сразу выбрать группу",
                   "❔ <b>Как подключить</b> — три шага на картинке",
                   "⚙️ <b>Мой чат</b> — бот уже там, проверим настройки",
                   "🎮 <b>Я просто играю</b> — профиль, игры и питомцы на сайте"]) +
            "\n<i>В чате команды начинаются со слова «бот», например: бот помощь. Здесь, в личке, можно без него: помощь.</i>")
    rows = [[_url("➕ Добавить бота в чат", cs.add_url(username))],
            [_btn("❔ Как подключить", "add"), _btn("⚙️ Мой чат", "my")],
            [_btn("🎮 Я просто играю", "play"), _btn("📖 Что умеет бот", "guide")],
            _site_btn(miniapp_url)]
    return text, _kb(*rows)


def play_screen(username: str, miniapp_url: str = "") -> Screen:
    """Для того, кто пришёл играть, а не настраивать чат: где сайт и что писать в чате."""
    site = ("1. <b>Сайт Предвестника</b> — кнопка ниже. Профиль, образы, Ритм, Сапёр, питомцы, задания и топ. "
            "Входить никуда не нужно: сайт узнаёт вас по Telegram.\n" if miniapp_url else
            "1. <b>Сайт Предвестника</b> — напишите <code>сайт</code>, я пришлю кнопку.\n")
    text = ("🎮 <b>Как играть</b>\n\n" + site +
            "2. <b>В чате с ботом</b> — напишите там <code>бот я</code>, и увидите свой профиль. "
            "Игры: <code>бот игры</code>, Мафия: <code>бот мафия</code>.\n"
            "3. <b>Нет такого чата?</b> Добавьте меня в свою группу или попросите об этом админа вашего чата.\n\n"
            "Здесь, в личке, тоже работает: <code>баланс</code> · <code>топ</code> · <code>стрик</code> · <code>помощь</code>.")
    return text, _kb(_site_btn(miniapp_url), [_url("➕ Добавить бота в свой чат", cs.add_url(username))],
                     [_btn("◀️ Назад", "home")])


def add_screen(username: str) -> Screen:
    text = ("➕ <b>Как добавить бота в чат</b>\n\n"
            "1. Нажмите «Выбрать чат» ниже и выберите группу, куда нужно меня добавить. Вы должны быть в ней владельцем "
            "или администратором.\n"
            f"2. Telegram покажет права, которые я прошу: <b>{RIGHT_DELETE}</b> и <b>{RIGHT_RESTRICT}</b>. Подтвердите.\n"
            "3. Я напишу в чате и здесь, что делать дальше.\n\n"
            "<b>Нет своей группы?</b> В Telegram нажмите ✏️ (новое сообщение) → <b>Новая группа</b>, добавьте любого друга, "
            "придумайте название и вернитесь сюда.\n"
            "<b>Вы не владелец чата?</b> Перешлите это сообщение владельцу: добавить меня должен он.\n\n"
            "<i>Без этих прав я не вижу обычные сообщения, не удаляю их и не ограничиваю участников. Если вы откажетесь от них сейчас, "
            "это можно исправить позже: в чате я подскажу как.</i>")
    return text, _kb([_url("➕ Выбрать чат", cs.add_url(username))],
                     [_btn("⚙️ Я уже добавил, проверить", "my")], [_btn("◀️ Назад", "home")])


ADD_CAPTION = ("➕ <b>Как подключить бота</b>\n\n"
               "1. Нажмите «Выбрать чат» и выберите группу. Вы должны быть в ней владельцем или администратором.\n"
               f"2. Telegram сам предложит права <b>{RIGHT_DELETE}</b> и <b>{RIGHT_RESTRICT}</b>. Подтвердите.\n"
               "3. Напишите в чате <code>бот помощь</code>. Ответил — всё готово.\n\n"
               "Я напишу в чате и здесь, если чего-то не хватит. Вы не владелец? Перешлите это сообщение владельцу.")


def add_photo_screen(username: str) -> Screen:
    """Подпись и кнопки под картинкой «3 шага» (подпись Telegram — до 1024 знаков)."""
    return ADD_CAPTION, _kb([_url("➕ Выбрать чат", cs.add_url(username))], [_btn("⚙️ Я уже добавил, проверить", "my")])


def play_photo_screen(username: str, miniapp_url: str = "") -> Screen:
    text, _ = play_screen(username, miniapp_url)
    return text, _kb(_site_btn(miniapp_url), [_url("➕ Добавить бота в свой чат", cs.add_url(username))])


def my_screen(chats: list[dict], username: str) -> Screen:
    if not chats:
        text = ("⚙️ <b>Мои чаты</b>\n\n"
                "Пока не вижу чатов, которые вы могли бы настроить.\n\n"
                "Бот уже в вашем чате? Напишите там <code>бот настройка</code> и нажмите «Подробно в личке». "
                "Ещё не добавили? Нажмите «Добавить бота в чат».")
        return text, _kb([_url("➕ Добавить бота в чат", cs.add_url(username))],
                         [_btn("❔ Как добавить", "add")], [_btn("◀️ Назад", "home")])
    rows = [[_btn(f"{'✅' if c['ready'] else '⚠️'} {c['title'][:36]}{'' if c['ready'] else ' · нужны права'}", "chat", c["id"])]
            for c in chats]
    rows.append([_url("➕ Добавить в ещё один чат", cs.add_url(username))])
    rows.append([_btn("◀️ Назад", "home")])
    text = ("⚙️ <b>Мои чаты</b>\n\nВыберите чат. ✅ — всё готово, ⚠️ — нужно выдать права или что-то доделать.")
    return text, _kb(*rows)


def denied_screen() -> Screen:
    return ("⛔ Настраивать чат могут владелец и администраторы. Попросите их нажать «Подробно в личке» под сообщением бота в чате.",
            _kb([_btn("◀️ Назад", "home")]))


# ── Доступ и отправка ───────────────────────────────────────────────────────

async def can_open(bot: Bot, db, chat_id: int, user_id: int) -> bool:
    """Кому можно открыть настройку чата: разработчику, владельцу, добавившему бота, рангу 4+ и администраторам Telegram."""
    if is_developer(user_id):
        return True
    if await ranks.get_rank(db, chat_id, user_id) >= 4:
        return True
    rec = await cs.get(db, chat_id)
    if rec and rec["inviter_id"] == user_id:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return getattr(member, "status", "") in ("administrator", "creator")


async def _username(bot: Bot) -> str:
    return (await bot.me()).username or ""


def _miniapp() -> str:
    try:
        from bot.keyboards.cta import MINIAPP_URL
        return MINIAPP_URL or ""
    except Exception:
        return ""


async def _edit(call: CallbackQuery, screen: Screen, same: str = "") -> None:
    text, kb = screen
    if getattr(call.message, "photo", None):   # под картинкой подпись короче и другие правила: следующий экран — новым сообщением
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        await call.answer()
        return
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc):
            logger.warning(f"onboarding edit failed: {exc}")
        elif same:
            await call.answer(same)   # экран не изменился: говорим об этом, а не молчим
            return
    await call.answer()


async def _commit(db) -> None:
    try:
        await db.commit()
    except Exception:   # noqa: BLE001 - соединение могло работать в автокоммите
        pass


# ── Картинки знакомства (services/welcome_images.py) ────────────────────────

PICTURE_PAUSE = 6 * 3600              # одну и ту же картинку человеку не чаще раза в 6 часов: показать, но не надоедать
_picture_shown: dict[tuple[int, str], float] = {}
_photo_ids: dict[str, str] = {}       # картинка -> file_id: Telegram хранит её у себя, второй раз не загружаем


def _picture_due(user_id: int, kind: str) -> bool:
    now = time.monotonic()
    if _picture_shown.get((user_id, kind), -PICTURE_PAUSE) + PICTURE_PAUSE > now:
        return False
    if len(_picture_shown) > 5000:
        _picture_shown.clear()
    _picture_shown[(user_id, kind)] = now
    return True


async def _send_picture(bot: Bot, chat_id: int, key: str, render, caption: str = "",
                        kb: InlineKeyboardMarkup | None = None) -> bool:
    """Отправить картинку. Не нарисовалась или Telegram отказал — False, и человек получит обычный текст."""
    import asyncio
    from aiogram.types import BufferedInputFile
    try:
        photo = _photo_ids.get(key)
        if photo is None:
            photo = BufferedInputFile(await asyncio.to_thread(render), filename=f"{key.split(':')[0]}.jpg")
        msg = await bot.send_photo(chat_id, photo, caption=caption or None, parse_mode="HTML", reply_markup=kb)
    except Exception as exc:   # noqa: BLE001 - картинка украшает, но не должна ломать знакомство
        logger.warning(f"welcome picture {key} not sent: {exc}")
        _photo_ids.pop(key, None)
        return False
    if getattr(msg, "photo", None) and len(_photo_ids) < 1000:
        _photo_ids[key] = msg.photo[-1].file_id
    return True


async def _welcome_picture(bot: Bot, user) -> None:
    from services import welcome_images as wi
    if user is None or not _picture_due(user.id, "welcome"):
        return
    name = wi.clean_name(getattr(user, "first_name", ""))
    await _send_picture(bot, user.id, f"welcome:{name}", lambda: wi.welcome(name))


async def _picture_screen(call: CallbackQuery, bot: Bot, kind: str, screen: Screen) -> bool:
    """Первое нажатие «Как подключить» / «Я просто играю»: картинка с подписью и кнопками. Повторное — обычный экран."""
    from services import welcome_images as wi
    if not _picture_due(call.from_user.id, kind):
        return False
    render = wi.connect_steps if kind == "steps" else wi.site_tour
    if not await _send_picture(bot, call.from_user.id, kind, render, *screen):
        return False
    await call.answer()
    return True


DM_HINT = ("👋 Привет! Я бот и лучше всего понимаю кнопки и команды.\n"
           "Команду со значением пишите через «бот», например: <code>бот промокод КОД</code>. Все команды: <code>помощь</code>.\n\n"
           "Чтобы подключить меня к чату или просто посмотреть, что я умею, начните отсюда 👇")
DM_HINT_PAUSE = 600.0
_dm_hint_at: dict[int, float] = {}


async def dm_hint(message: Message, bot: Bot, db) -> None:
    """Человек написал в личку что-то своё («привет», «/help», стикер): не молчим, а показываем, с чего начать. Не чаще раза в 10 минут."""
    user = message.from_user
    if user is None or user.is_bot or not (message.text or getattr(message, "sticker", None)):
        return
    now = time.monotonic()
    if _dm_hint_at.get(user.id, -DM_HINT_PAUSE) + DM_HINT_PAUSE > now:
        return
    if len(_dm_hint_at) > 5000:
        _dm_hint_at.clear()
    _dm_hint_at[user.id] = now
    _, kb = home_screen(await _username(bot), _miniapp())
    await message.answer(DM_HINT, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


# ── Вход бота в чат, смена прав, уход ───────────────────────────────────────

async def _dm(bot: Bot, db, chat_id: int, user_id: int | None, screen: Screen, event: str = "dm_sent") -> bool:
    """Написать человеку в личку. Не получилось (он ещё не запускал бота) — запомнили, чат при этом уже получил свою кнопку."""
    if not user_id:
        return False
    text, kb = screen
    try:
        await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except Exception as exc:   # noqa: BLE001 - закрытая личка — обычное дело
        logger.debug(f"onboarding dm {user_id}: {exc}")
        await cs.log_event(db, chat_id, user_id, "dm_failed")
        return False
    await cs.log_event(db, chat_id, user_id, event)
    return True


async def _send_welcome(bot: Bot, db, s: cs.Setup, inviter_id: int | None, via: str) -> None:
    username = await _username(bot)
    s.verified = False   # подключаем заново: проверка снималась до того, как запись о подключении появилась
    await cs.log_event(db, s.chat_id, inviter_id, "added", f"{via}, {'готов' if s.ready else 'без прав'}")
    if s.ready:
        await cs.log_event(db, s.chat_id, inviter_id, "rights_ok", "сразу при добавлении")
    text, kb = group_screen(s, username)
    try:
        msg = await bot.send_message(s.chat_id, text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        await cs.set_message(db, s.chat_id, msg.message_id)
    except Exception as exc:   # noqa: BLE001 - писать в чат может быть нельзя
        logger.info(f"onboarding welcome not sent to {s.chat_id}: {exc}")
        await cs.log_event(db, s.chat_id, inviter_id, "welcome_failed", str(exc)[:150])
    intro = "👋 Спасибо, что добавили меня в чат. Давайте доведём настройку до конца."
    await _dm(bot, db, s.chat_id, inviter_id, chat_screen(s, username, intro))


async def on_bot_change(event, bot: Bot, db) -> None:
    """Событие про самого бота в группе (подключено из members.on_bot_membership после записи прав в базу)."""
    chat_id = event.chat.id
    old, new = getattr(getattr(event, "old_chat_member", None), "status", None), event.new_chat_member.status
    actor = getattr(event, "from_user", None)
    actor_id = actor.id if actor and not getattr(actor, "is_bot", False) else None
    if new in ("left", "kicked"):
        await cs.mark_left(db, chat_id)
        await cs.log_event(db, chat_id, actor_id, "left", new)
        await _commit(db)
        return
    if new not in ("member", "administrator"):
        return
    s = await cs.inspect(bot, db, chat_id, persist=False)   # права из этого события members уже записал
    if old in ("left", "kicked"):
        if await cs.claim(db, chat_id, actor_id, s.ready) == "won":
            await _commit(db)
            await _send_welcome(bot, db, s, actor_id, "добавление")
    else:
        await refresh(bot, db, chat_id, s)
    await _commit(db)


async def refresh(bot: Bot, db, chat_id: int, s: cs.Setup | None = None, message: Message | None = None,
                  notify: bool = True) -> cs.Setup:
    """Права могли измениться: обновить сообщение в чате и, если права появились, сообщить тому, кто добавлял бота."""
    s = s or await cs.inspect(bot, db, chat_id)
    rec = await cs.get(db, chat_id)
    if rec is None or rec["left_at"]:
        return s
    flipped = await cs.set_ready(db, chat_id, s.ready)
    username = await _username(bot)
    text, kb = group_screen(s, username)
    msg_id = message.message_id if message is not None else rec["message_id"]
    if msg_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="HTML", reply_markup=kb,
                                        disable_web_page_preview=True)
        except TelegramBadRequest as exc:
            if "not modified" not in str(exc):
                logger.debug(f"onboarding refresh {chat_id}: {exc}")
        except Exception as exc:   # noqa: BLE001 - сообщение удалили или чат недоступен
            logger.debug(f"onboarding refresh {chat_id}: {exc}")
    if flipped and s.ready:
        await cs.log_event(db, chat_id, None, "rights_ok")
        if notify:   # тот, кто сам нажал «Проверить» в личке, и так видит новый экран
            await _dm(bot, db, chat_id, rec["inviter_id"], chat_screen(s, username, "🎉 Права получены, теперь я работаю в чате полностью."))
    elif flipped:
        await cs.log_event(db, chat_id, None, "rights_lost")
    return s


async def on_command_used(bot: Bot, db, chat_id: int) -> None:
    """Бот ответил на команду в группе. Первая команда после подключения завершает проверку: обновляем сообщение в чате."""
    if chat_id >= 0 or not await cs.note_command(db, chat_id):
        return
    await cs.log_event(db, chat_id, None, "first_command")
    await _commit(db)
    await refresh(bot, db, chat_id)
    await _commit(db)


async def on_channel_added(event, bot: Bot, db) -> None:
    """Бота добавили в канал: каналы он не ведёт, человеку сразу говорим, что делать (иначе он ждёт и не понимает, почему тишина)."""
    actor = getattr(event, "from_user", None)
    if not actor or getattr(actor, "is_bot", False):
        return
    username = await _username(bot)
    title = _e(getattr(event.chat, "title", None) or "канал")
    text = (f"📣 Вы добавили меня в канал «{title}». Каналы я не веду: я работаю в группах и супергруппах.\n\n"
            "Если у канала есть чат для обсуждения, добавьте меня туда. Нет чата? Создайте группу и добавьте меня в неё.")
    await _dm(bot, db, event.chat.id, actor.id, (text, _kb([_url("➕ Добавить в группу", cs.add_url(username))])),
              event="channel_added")
    await _commit(db)


async def group_start(message: Message, bot: Bot, db) -> None:
    """/start в группе: так Telegram приветствует бота после «добавить в группу». Рядом с входом бота это не дублируется."""
    chat, user = message.chat, message.from_user
    s = await cs.inspect(bot, db, chat.id)
    # Хозяином подключения запоминаем только администратора: /start может написать любой участник, и личку получать должен не он.
    is_admin = False
    if user:
        try:
            is_admin = (await bot.get_chat_member(chat.id, user.id)).status in ("administrator", "creator")
        except Exception:   # noqa: BLE001
            pass
    inviter = user.id if user and is_admin else None
    status = await cs.claim(db, chat.id, inviter, s.ready, restart_stale=False)
    await _commit(db)
    if status == "recent":
        return   # приветствие уже отправил обработчик входа бота
    if status == "won":
        await _send_welcome(bot, db, s, inviter, "команда /start")
        return
    text, kb = group_screen(s, await _username(bot))
    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


# ── Личка ───────────────────────────────────────────────────────────────────

async def dm_start(message: Message, bot: Bot, db, payload: str = "") -> None:
    """/start в личке: главный экран или (по ссылке из чата) настройка конкретного чата."""
    username = await _username(bot)
    if payload.startswith("setup_"):
        try:
            chat_id = int(payload.removeprefix("setup_"))
        except ValueError:
            chat_id = 0
        if chat_id < 0:
            screen = await _chat_for(bot, db, chat_id, message.from_user.id, username)
            await message.answer(screen[0], parse_mode="HTML", reply_markup=screen[1], disable_web_page_preview=True)
            return
    await _welcome_picture(bot, message.from_user)
    text, kb = home_screen(username, _miniapp())
    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    if message.from_user:
        _dm_hint_at[message.from_user.id] = time.monotonic()   # меню только что показали: «привет» следом не повторит его


async def _chat_for(bot: Bot, db, chat_id: int, user_id: int, username: str, intro: str = "") -> Screen:
    if not await can_open(bot, db, chat_id, user_id):
        await cs.log_event(db, chat_id, user_id, "denied")
        return denied_screen()
    s = await cs.inspect(bot, db, chat_id)
    await _commit(db)
    return chat_screen(s, username, intro)


async def open_setup(message: Message, bot: Bot, db) -> None:
    """/setup и «бот настройка»: в чате — чек-лист, в личке — список своих чатов."""
    username = await _username(bot)
    if message.chat.type == "private":
        chats = await cs.my_chats(db, message.from_user.id, bot=bot)
        text, kb = my_screen(chats, username)
    else:
        s = await cs.inspect(bot, db, message.chat.id)
        await _commit(db)
        text, kb = group_screen(s, username)
    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


@registry.command(
    "настройка", aliases=("настроить", "настроить бота", "setup", "подключение"), usage="бот настройка", private=True,
    section="basic", summary="Проверить, всё ли готово в чате (права бота, модераторы), и что сделать дальше.",
)
async def cmd_setup(ctx: Ctx) -> None:
    await open_setup(ctx.message, ctx.bot, ctx.db)


@router.message(Command("setup"))
async def slash_setup(message: Message, bot: Bot, db) -> None:
    await open_setup(message, bot, db)


async def _quiet(message: Message, db) -> bool:
    from bot.chat import _silent   # заблокирован в админке или бот выключен — молчим, как на остальные команды
    try:
        return await _silent(message, db)
    except Exception:   # noqa: BLE001
        return False


# Только в личке: в группе слэш-команда прошла бы мимо закрытого чата и чистки; там есть «бот помощь» и «бот сайт».
@router.message(Command("help"), F.chat.type == "private")
async def slash_help(message: Message, db) -> None:
    """/help из меню «/»: та же справка, что «бот помощь»."""
    from bot.chat import help as help_mod
    if message.from_user is None or await _quiet(message, db):
        return
    private = message.chat.type == "private"
    await message.answer(help_mod.main_text(private), parse_mode="HTML",
                         reply_markup=help_mod.main_keyboard(message.from_user.id, private))


@router.message(Command("site"), F.chat.type == "private")
async def slash_site(message: Message, bot: Bot, db) -> None:
    """/site из меню «/»: кнопка сайта Предвестника, как «бот сайт»."""
    from bot.chat.site import SITE_TEXT, site_keyboard
    if await _quiet(message, db):
        return
    kb = site_keyboard(message.chat.type, await _username(bot))
    if kb is None:
        await message.answer("🔮 Сайт сейчас недоступен. Попробуйте позже.")
        return
    await message.answer(SITE_TEXT, parse_mode="HTML", reply_markup=kb)


BOT_DESCRIPTION = ("👋 Я Предвестник — бот для групп в Telegram.\n\n"
                   "🛡 Порядок в чате: муты, варны, баны, ранги модераторов\n"
                   "🏆 Профили, топ активных, награды\n"
                   "🎮 Игры: Мафия, Ритм, Сапёр, питомцы\n"
                   "🔮 Свой сайт прямо в Telegram\n\n"
                   "Нажмите «Старт» — покажу, как за пару минут добавить меня в ваш чат.")
BOT_SHORT_DESCRIPTION = "Порядок, топ, профили и игры для вашего чата. Подключение — пара минут, веду по шагам."


async def ensure_descriptions(bot: Bot) -> None:
    """Текст, который человек видит в пустом чате с ботом до «Старт». Свой текст из BotFather не перезаписываем."""
    try:
        if not (await bot.get_my_description()).description:
            await bot.set_my_description(BOT_DESCRIPTION)
        if not (await bot.get_my_short_description()).short_description:
            await bot.set_my_short_description(BOT_SHORT_DESCRIPTION)
    except Exception as exc:   # noqa: BLE001 - без описания бот работает
        logger.warning(f"bot description not set: {exc}")


@router.callback_query(OnbCB.filter())
async def on_onboarding(call: CallbackQuery, callback_data: OnbCB, bot: Bot, db) -> None:
    a, chat_id, user_id = callback_data.a, callback_data.c, call.from_user.id
    username = await _username(bot)
    if call.message is None:
        await call.answer()
        return
    if call.message.chat.type != "private":   # в чате: только проверка и справка, это безопасно для любого участника
        await _on_group_button(call, a, chat_id, bot, db, username)
        return
    if a == "home":
        await _edit(call, home_screen(username, _miniapp()))
    elif a == "add":
        await cs.log_event(db, 0, user_id, "add_help")
        if not await _picture_screen(call, bot, "steps", add_photo_screen(username)):
            await _edit(call, add_screen(username))
    elif a == "play":
        await cs.log_event(db, 0, user_id, "play")
        if not await _picture_screen(call, bot, "site", play_photo_screen(username, _miniapp())):
            await _edit(call, play_screen(username, _miniapp()))
    elif a == "my":
        await _edit(call, my_screen(await cs.my_chats(db, user_id, bot=bot), username))
    elif a == "guide" and not chat_id:
        await cs.log_event(db, 0, user_id, "guide")
        await _edit(call, guide_screen(0, _miniapp()))
    elif chat_id >= 0:
        await call.answer()
    elif not await can_open(bot, db, chat_id, user_id):
        await cs.log_event(db, chat_id, user_id, "denied")
        await _edit(call, denied_screen())
    else:
        await _on_chat_button(call, a, chat_id, bot, db, username)


_chk_cooldown: dict[int, float] = {}   # чат -> когда «Проверить» можно нажать снова: кнопку видят все, спамить ею незачем
CHK_COOLDOWN = 3.0


async def _on_group_button(call: CallbackQuery, a: str, chat_id: int, bot: Bot, db, username: str) -> None:
    if chat_id != call.message.chat.id:
        await call.answer()
        return
    if a == "chk":
        now = time.monotonic()
        if _chk_cooldown.get(chat_id, 0.0) > now:
            await call.answer("Подождите пару секунд, я только что проверял.")
            return
        _chk_cooldown[chat_id] = now + CHK_COOLDOWN
        if len(_chk_cooldown) > 2000:
            _chk_cooldown.clear()
        await cs.log_event(db, chat_id, call.from_user.id, "check", "в чате")
        s = await refresh(bot, db, chat_id, message=call.message)
        await _commit(db)
        await call.answer(("✅ Права есть" + ("" if s.verified else ". Осталось написать «бот помощь»")) if s.ready
                          else "Прав пока не хватает: " + ", ".join(missing_rights(s)).lower())
    elif a == "guide":
        await cs.log_event(db, chat_id, call.from_user.id, "guide", "в чате")
        text, _ = guide_screen(chat_id)
        await _edit(call, (text, _kb([_btn("◀️ Назад", "chk", chat_id)])))
    else:
        await call.answer()


async def _on_chat_button(call: CallbackQuery, a: str, chat_id: int, bot: Bot, db, username: str) -> None:
    user_id = call.from_user.id
    if a in ("chat", "chk"):
        if a == "chk":
            await cs.log_event(db, chat_id, user_id, "check", "в личке")
        s = await refresh(bot, db, chat_id, notify=False) if a == "chk" else await cs.inspect(bot, db, chat_id)
        await _commit(db)
        await _edit(call, chat_screen(s, username), same="Пока без изменений: проверьте, что включили оба права и нажали ✓." if not s.ready else "Всё как было.")
        return
    s = await cs.inspect(bot, db, chat_id)
    if a == "rights":
        await cs.log_event(db, chat_id, user_id, "rights_help")
        await _edit(call, rights_screen(s, username))
    elif a == "trouble":
        await cs.log_event(db, chat_id, user_id, "trouble")
        await _edit(call, trouble_screen(s))
    elif a == "guide":
        await cs.log_event(db, chat_id, user_id, "guide")
        await _edit(call, guide_screen(chat_id))
    elif a == "staff":
        await cs.log_event(db, chat_id, user_id, "staff_preview")
        proposals = await cs.staff_proposals(bot, db, chat_id)
        await _edit(call, staff_screen(s, proposals, legend=await _legend(db, chat_id, proposals)))
    elif a == "staffok":
        await _apply_staff(call, s, bot, db)
    elif a in ("adm", "admcode"):
        await _admin_chat(call, a, s, db)
    else:
        await call.answer()


async def _legend(db, chat_id: int, proposals) -> str:
    if not proposals:
        return ""
    return rank_legend(await ranks.rights_map(db, chat_id), [p.rank for p in proposals])


async def _apply_staff(call: CallbackQuery, s: cs.Setup, bot: Bot, db) -> None:
    chat_id, user_id = s.chat_id, call.from_user.id
    if not await ranks.can(db, chat_id, user_id, "set_rank"):
        await call.answer("Выдавать ранги может владелец чата или ранг 7 и выше.", show_alert=True)
        return
    actor_rank = await ranks.get_rank(db, chat_id, user_id)
    proposals = await cs.staff_proposals(bot, db, chat_id)   # заново: админы могли измениться, пока экран висел
    if proposals is None:
        await _edit(call, staff_screen(s, None))
        return
    allowed = [p for p in proposals if ranks.check_assign(actor_rank, p.current, p.rank) is None]
    skipped = len(proposals) - len(allowed)
    done = await cs.apply_staff(db, chat_id, allowed)
    await _commit(db)
    await cs.log_event(db, chat_id, user_id, "staff_applied", f"{done}")
    s = await cs.inspect(bot, db, chat_id)
    note = f"✅ Назначено: {done}." + (f" Пропущено {skipped}: их ранг не ниже вашего." if skipped else "")
    left = await cs.staff_proposals(bot, db, chat_id)
    await _edit(call, staff_screen(s, left, done=note, legend=await _legend(db, chat_id, left)))


async def _admin_chat(call: CallbackQuery, a: str, s: cs.Setup, db) -> None:
    from bot.chat.admin_chat import new_bind_token
    chat_id, user_id = s.chat_id, call.from_user.id
    if a == "admcode":
        if not await ranks.can(db, chat_id, user_id, "admin_chat"):
            await call.answer("Привязать админ-чат может владелец чата.", show_alert=True)
            return
        code = await new_bind_token(db, chat_id, s.title)
        await cs.log_event(db, chat_id, user_id, "admin_chat_code")
        await _commit(db)
        await _edit(call, admin_screen(s, code))
        return
    await _edit(call, admin_screen(s))


# ── Напоминания ─────────────────────────────────────────────────────────────

async def send_reminders(bot: Bot, db) -> int:
    """Бота добавили, а прав так и не выдали: напомнить тому, кто добавлял (через час и через сутки). Возвращает, сколько отправлено."""
    sent = 0
    username = await _username(bot)
    for rec in await cs.reminder_candidates(db):
        chat_id = rec["chat_id"]
        try:
            s = await cs.inspect(bot, db, chat_id)
            if not s.present:   # бота убрали, пока нас не было
                await cs.mark_left(db, chat_id)
            elif s.ready:                   # права выдали, а событие потерялось
                await refresh(bot, db, chat_id, s)
            else:
                first = rec["reminders"] == 0
                intro = ("⏰ Я в чате «%s», но прав администратора у меня всё ещё нет, поэтому я почти ничего не могу."
                         if first else "⏰ Последнее напоминание: в чате «%s» мне всё ещё не хватает прав.") % _e(s.title)
                delivered = await _dm(bot, db, chat_id, rec["inviter_id"], chat_screen(s, username, intro), event="reminder")
                if not delivered and first:   # личка закрыта: один раз напоминаем в самом чате
                    text, kb = group_screen(s, username, reminder=True)
                    try:
                        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True,
                                               reply_to_message_id=rec["message_id"], allow_sending_without_reply=True)
                        await cs.log_event(db, chat_id, None, "reminder", "в чате")
                    except Exception as exc:   # noqa: BLE001
                        logger.debug(f"onboarding reminder to chat {chat_id}: {exc}")
                sent += 1
            await cs.mark_reminded(db, chat_id)
        except Exception as exc:   # noqa: BLE001 - один чат не должен останавливать остальные
            logger.warning(f"onboarding reminder for {chat_id} failed: {exc}")
        await _commit(db)
    return sent
