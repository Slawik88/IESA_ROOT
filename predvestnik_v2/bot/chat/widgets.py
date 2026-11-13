"""Виджеты в личке игрока (S30b): «Табло» и «Сапёр» прямо в сообщении, кнопка «Текстом», вход из группы и по ссылке.

Табло заменяет в личке текстовые «план», «квесты» и «пропуск»: команды зовут show() и, если виджет не подошёл
(не открыт игроку, выключен, игрок выбрал текст, Telegram отказал), отвечают прежним текстом. Под каждым виджетом —
«📄 Текстом» (тот же экран обычным сообщением: старый Telegram виджет не покажет) и кнопка приложения.
Решения «можно ли» и «что внутри» — в services/widgets; здесь только Telegram.
"""
from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command as SlashCommand
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from bot.chat.framework import Ctx, registry
from core import widgets as rules
from core.miniapp_links import miniapp_web_url
from infrastructure.repositories import dm_push as prefs
from services import dm_push, widgets

router = Router(name="chat_widgets")
# /mines из меню «/» — раньше общего обработчика чата, как /plan (bot/handlers/__init__.py).
slash_router = Router(name="chat_widgets_slash")

BOARD = "табло"
MINES = "сапёр"
_START = re.compile(r"^w-([a-z]{2,8})(?:-([a-z]{1,8}))?$")
TEXT_SECTION = {"day": "home", "me": "home", "q": "quests", "qw": "quests", "pass": "pass", "pets": "pets"}


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _app_row(section: str, label: str = "🔮 Приложение") -> list[InlineKeyboardButton]:
    url = miniapp_web_url(section)
    return [InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))] if url else []


def markup(key: str, view: str | None) -> InlineKeyboardMarkup:
    spec = rules.REGISTRY[key]
    row = [_btn("📄 Текстом", f"wg:t:{key}:{view or ''}"), *_app_row(TEXT_SECTION.get(view or "", spec.section))]
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def show(bot, db, user_id: int, key: str, view: str | None = None) -> bool:
    """Прислать виджет в личку игрока. False — виджет не подошёл: вызывающий отвечает прежним текстом."""
    view = rules.view_of(rules.REGISTRY[key], view)
    return await widgets.offer(bot, db, user_id, key, view=view, reply_markup=markup(key, view)) is not None


def deep_link(username: str, key: str, view: str | None = None) -> str:
    """Ссылка из группы в личку: /start w-<ключ>[-<экран>] сразу присылает виджет."""
    return f"https://t.me/{username}?start=w-{key}" + (f"-{view}" if view else "")


async def _dm_button(ctx: Ctx, label: str, key: str, view: str | None = None) -> InlineKeyboardMarkup | None:
    me = await ctx.bot.me()
    if not me.username:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, url=deep_link(me.username, key, view))]])


# ── тот же экран текстом ─────────────────────────────────────────────────────

async def text_view(db, user_id: int, key: str, view: str | None) -> tuple[str, InlineKeyboardMarkup | None]:
    """Экран виджета обычным сообщением: прежние тексты команд «план», «квесты», «пропуск», «баланс», «питомцы»."""
    if key == "track":
        from types import SimpleNamespace
        from bot.chat import pets
        if not await pets.available(db, user_id, SimpleNamespace(type="private", id=int(user_id)), {"screen": "choose", "target": "track"}):
            return "⛔ Питомцы сейчас недоступны.", None
        return await pets.render(db, user_id, int(user_id), {"screen": "choose", "target": "track"})
    if key == "mines":
        kb = InlineKeyboardMarkup(inline_keyboard=[row]) if (row := _app_row("games", "💣 Открыть Сапёр")) else None
        return ("💣 <b>Сапёр</b>\n\nОткрывай клетки и не попадись на мину: цифра на клетке — сколько мин рядом. "
                "Играть можно в приложении: вкладка «Игры» › Сапёр. За победу — опыт Пропуска."), kb
    view = rules.view_of(rules.REGISTRY["hub"], view)
    if view == "day":
        from bot.chat.notify import plan_view
        return await plan_view(db, user_id)
    app = InlineKeyboardMarkup(inline_keyboard=[row]) if (row := _app_row(TEXT_SECTION[view or "day"])) else None
    if view in ("q", "qw"):
        from bot.chat.games import render_quest_overview
        from services import dm_plan
        quests = await dm_plan.quests_state(db, user_id)
        return (render_quest_overview(quests) if quests else "Задания сейчас недоступны. Загляни чуть позже."), app
    if view == "pass":
        from bot.chat.games import render_pass
        from services import league_pass
        return render_pass(await league_pass.status(db, user_id=user_id)), app
    if view == "pets":
        from types import SimpleNamespace
        from bot.chat import pets
        from infrastructure.repositories import pet_chat
        chat = SimpleNamespace(type="private", id=int(user_id))
        if not await pets.available(db, user_id, chat, {"screen": "home"}):
            return "⛔ Питомцы сейчас недоступны.", None
        await pet_chat.expire(db, user_id)
        return await pets.render(db, user_id, int(user_id), {"screen": "home"})
    from bot.chat.profile import balances
    from bot.chat.style import quote
    return "👛 <b>Кошелёк</b>\n" + quote(await balances(db, user_id)), app


async def _send_text(message: Message, db, user_id: int, key: str, view: str | None, *, offer_text_mode: bool) -> None:
    text, kb = await text_view(db, user_id, key, view)
    if offer_text_mode and not await prefs.prefers_text_menus(db, user_id):
        rows = list(kb.inline_keyboard) if kb else []
        kb = InlineKeyboardMarkup(inline_keyboard=[*rows, [_btn("🧩 Всегда текстом", "wg:off")]])
    await message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("wg:"))
async def on_widget_button(call: CallbackQuery, db) -> None:
    msg = call.message
    if msg is None or msg.chat.type != "private" or msg.chat.id != call.from_user.id:
        await call.answer("Это работает только в личке с ботом.", show_alert=True)
        return
    uid, parts = call.from_user.id, (call.data or "").split(":")
    if not await dm_push.player_reachable(db, uid):
        await call.answer("Сейчас это недоступно.", show_alert=True)
        return
    await dm_push.confirm_contact(db, uid)
    if parts[1:2] == ["off"]:
        await prefs.set_text_menus(db, uid, True)
        await call.answer("Готово: план, задания и Пропуск будут приходить текстом. Вернуть табло — «бот табло вкл».",
                          show_alert=True)
        return
    if len(parts) == 4 and parts[1] == "t" and parts[2] in ("hub", "mines", "track"):
        await _send_text(msg, db, uid, parts[2], parts[3] or None, offer_text_mode=True)
        await call.answer()
        return
    await call.answer("Кнопка устарела. Напиши «табло».", show_alert=True)


# ── команды ─────────────────────────────────────────────────────────────────

async def open_widget(message: Message, bot, db, user_id: int, key: str, view: str | None = None) -> None:
    """Виджет, а если он не подошёл — тот же экран текстом (вход по ссылке, кнопка «Табло» на первом экране)."""
    from services.widgets import mines
    if key == "mines" and not await mines.available(db):
        await message.answer("💣 Сапёр сейчас закрыт. Загляни позже.")
        return
    if not await show(bot, db, user_id, key, view):
        await _send_text(message, db, user_id, key, view, offer_text_mode=False)


async def from_start(message: Message, bot, db, payload: str) -> bool:
    """/start w-<ключ>[-<экран>]: ссылка «в личку» из группы. False — это не ссылка на виджет."""
    found = _START.match(payload or "")
    if not found or found.group(1) not in ("hub", "mines", "track"):
        return False
    await dm_push.confirm_contact(db, message.from_user.id)
    await open_widget(message, bot, db, message.from_user.id, found.group(1), found.group(2))
    return True


@registry.command(BOARD, aliases=("моё табло", "мое табло", "табло дня"), section="basic",
                  summary="Живое табло в личке: день, задания, Пропуск, питомцы и кошелёк в цветах твоего образа.",
                  usage="бот табло [вкл | выкл]", example="бот табло")
async def cmd_board(ctx: Ctx) -> None:
    if ctx.message.chat.type != "private":
        await ctx.reply("🎛 Табло живёт в личке с ботом: там видно день, задания, Пропуск и питомцев.",
                        reply_markup=await _dm_button(ctx, "🎛 Открыть табло", "hub", "day"))
        return
    await dm_push.confirm_contact(ctx.db, ctx.user_id)
    arg = ctx.args.strip().lower()
    if arg.startswith("выкл") or arg == "off":
        await prefs.set_text_menus(ctx.db, ctx.user_id, True)
        await ctx.reply("Готово: план, задания и Пропуск будут приходить обычным текстом. Вернуть табло — «бот табло вкл».")
        return
    await prefs.set_text_menus(ctx.db, ctx.user_id, False)   # сам попросил табло — значит, хочет его, а не текст
    await open_widget(ctx.message, ctx.bot, ctx.db, ctx.user_id, "hub", "day")


@registry.command(MINES, aliases=("сапер", "сапёр в чате"), section="games",
                  summary="Сапёр прямо в личке с ботом: та же партия и тот же опыт Пропуска, что в приложении.",
                  usage="бот сапёр", example="бот сапёр")
async def cmd_mines(ctx: Ctx) -> None:
    if ctx.message.chat.type != "private":
        await ctx.reply("💣 Сапёр открывается в личке с ботом — прямо в сообщении. Или в приложении: «Игры» › Сапёр.",
                        reply_markup=await _dm_button(ctx, "💣 Играть в личке", "mines"))
        return
    await dm_push.confirm_contact(ctx.db, ctx.user_id)
    await open_widget(ctx.message, ctx.bot, ctx.db, ctx.user_id, "mines")


@slash_router.message(SlashCommand("mines"), F.chat.type == "private")
async def slash_mines(message: Message, bot, db) -> None:
    from bot.chat import _silent
    if message.from_user is None or await _silent(message, db):
        return
    await dm_push.confirm_contact(db, message.from_user.id)
    await open_widget(message, bot, db, message.from_user.id, "mines")
