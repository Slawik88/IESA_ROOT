"""«бот помощь» — справка, собранная из реестра команд, разбита на блоки.

Новая команда появляется в справке сама, если у неё задан `section`.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.chat.framework import Command, Ctx, norm, registry, suggest

# Порядок и названия блоков. Блок без команд в справке не показывается.
SECTIONS: dict[str, str] = {
    "basic": "🧭 Основное",
    "stats": "📊 Статистика",
    "profile": "👤 Профиль и валюта",
    "family": "💞 Семья",
    "social": "🤗 Взаимодействия",
    "games": "🎮 Игры",
    "moderation": "🛡 Модерация",
    "purge": "🧹 Чистка",
    "settings": "⚙️ Настройки чата",
}


class HelpCB(CallbackData, prefix="help"):
    uid: int
    section: str


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _by_section(private: bool = False) -> dict[str, list[Command]]:
    """Команды по блокам. В личке только те, что там работают: модерация, варпы с адресатом и брак живут в группе."""
    out: dict[str, list[Command]] = {k: [] for k in SECTIONS}
    for c in registry.commands():
        if c.section in out and (c.private or not private):
            out[c.section].append(c)
    for v in out.values():
        v.sort(key=lambda c: c.name)
    return {k: v for k, v in out.items() if v}


def main_text(private: bool = False) -> str:
    if private:
        return (
            "📖 <b>Помощь</b> · личка с ботом\n\n"
            "Здесь слово «бот» не нужно: просто напишите команду.\n"
            "<blockquote><code>баланс</code> · <code>топ</code> · <code>стрик</code> · <code>помощь</code></blockquote>\n"
            "С значениями — через «бот»: <code>бот промокод КОД</code>.\n"
            "Модерация, варпы и всё, что нужно адресату, работает в группе: там пишите <code>бот помощь</code>.\n\n"
            "Выберите раздел 👇"
        )
    return (
        "📖 <b>Помощь</b>\n\n"
        "Команды пишутся так:\n"
        "<blockquote><code>бот команда, значения</code>\n"
        "Пример: <code>бот бан, @ник 5д</code></blockquote>\n"
        "Вместо @ника можно ответить на сообщение игрока.\n\n"
        "Выберите раздел 👇"
    )


def main_keyboard(uid: int, private: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=SECTIONS[k], callback_data=HelpCB(uid=uid, section=k).pack())
        for k in _by_section(private)
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def section_text(key: str, private: bool = False) -> str:
    cmds = _by_section(private).get(key, [])
    parts = [f"<b>{SECTIONS.get(key, key)}</b>"]
    for c in cmds:
        block = f"\n▫️ <code>бот {_esc(c.name)}</code>\n{_esc(c.summary)}"
        if c.example and c.example != f"бот {c.name}":
            block += f"\n↳ <code>{_esc(c.example)}</code>"
        if c.aliases:
            block += "\n<i>Также:</i> " + _esc(" · ".join(c.aliases))
        parts.append(block)
    return "\n".join(parts)


def command_text(c: Command, private: bool = False) -> str:
    text = f"📖 <b>бот {_esc(c.name)}</b>\n{_esc(c.summary)}"
    if private and not c.private:
        text += "\n\n⚠️ Эта команда работает только в группе."
    if c.usage:
        text += f"\n\n<blockquote><i>Формат:</i> <code>{_esc(c.usage)}</code>"
        text += (f"\n<i>Пример:</i> <code>{_esc(c.example)}</code></blockquote>" if c.example else "</blockquote>")
    elif c.example:
        text += f"\n\n<blockquote><i>Пример:</i> <code>{_esc(c.example)}</code></blockquote>"
    if c.aliases:
        text += "\n<i>Также:</i> " + ", ".join(f"<code>{_esc(a)}</code>" for a in c.aliases)
    return text


def back_keyboard(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Все разделы", callback_data=HelpCB(uid=uid, section="").pack())
    ]])


@registry.command(
    "помощь", aliases=("help", "команды"), usage="бот помощь [команда]",
    section="basic", summary="Эта справка. С названием команды — подробно о ней.",
    example="бот помощь топ",
)
async def cmd_help(ctx: Ctx) -> None:
    private = ctx.message.chat.type == "private"
    query = norm(ctx.args)
    if query:
        cmd = registry.get(query)
        if cmd is None:
            sugg = suggest(registry, query)
            cmd = registry.get(sugg[0]) if sugg else None
        if cmd is not None:
            await ctx.reply(command_text(cmd, private), reply_markup=back_keyboard(ctx.user_id))
            return
    await ctx.reply(main_text(private), reply_markup=main_keyboard(ctx.user_id, private))


router = Router(name="chat_help")


@router.callback_query(HelpCB.filter())
async def on_help(call: CallbackQuery, callback_data: HelpCB) -> None:
    if call.from_user.id != callback_data.uid:
        await call.answer("Это меню другого игрока. Откройте своё: «бот помощь».", show_alert=True)
        return
    uid = callback_data.uid
    private = call.message.chat.type == "private"
    if callback_data.section:
        text, kb = section_text(callback_data.section, private), back_keyboard(uid)
    else:
        text, kb = main_text(private), main_keyboard(uid, private)
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        pass
    await call.answer()
