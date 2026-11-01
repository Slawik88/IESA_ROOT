"""«Моя статья»: пародийный «уголовный кодекс» про самого игрока (S22).

Игрок пишет «моя статья» и получает шуточное дело: реальный номер и название
статьи из белого списка, пародийную расшифровку про быт и безобидный «приговор».
Статья стабильна на сутки (hash от user_id и даты, core/article), повторный
вызов в тот же день даёт тот же состав с новой подводкой и приговором.

Граница контента: пародия про самого игрока, без инструкций, без реальных людей;
sexual-темы в банк не входят (см. файл сессии S22 и test_article_texts).
Выключатели: «Функции» (group:article) и «бот статья вкл/выкл» (module_article,
право rights). Включено по умолчанию (решение владельца). Личного отказа нет —
функция про самого игрока.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

from bot.chat import ranks
from bot.chat.article_texts import BANK, BY_NUMBER, DESCRIPTIONS
from bot.chat.framework import Ctx, norm, registry
from core import article
from infrastructure.repositories import article_v1
from infrastructure.repositories import chat_module_audit

ON_WORDS = ("вкл", "включить", "on", "да")
OFF_WORDS = ("выкл", "выключить", "off", "нет")
WHAT = "<i>Бот пишет шуточное дело про самого игрока: номер статьи, пародийную расшифровку и безобидный «приговор».</i>"
PARODY_MARK = "<i>⚠️ Пародия и шутка, не юридическая информация.</i>"
DEFAULT_NAME = "игрок"


def _today():
    return datetime.now(timezone.utc).date()


def _display(user_id: int, username: str | None) -> str:
    """Имя игрока без пинга: ссылка t.me или текст «id…»."""
    if username:
        return f'<a href="https://t.me/{html.escape(username, quote=True)}">@{html.escape(username)}</a>'
    return f"id{int(user_id)}"


def _case(index: int) -> tuple[str, str]:
    """Номер статьи и описание по индексу описания (article_key)."""
    number, description = DESCRIPTIONS[int(index)]
    return number, description


async def _toggle_chat(ctx: Ctx, chat_id: int, want: bool) -> None:
    """«бот статья вкл/выкл»: выключатель чата для того, кто меняет права рангов."""
    if not await ranks.can(ctx.db, chat_id, ctx.user_id, "rights"):
        await ctx.reply("⚖️ Это может тот, кто настраивает права рангов в чате (обычно владелец).")
        return
    result = await chat_module_audit.set_chat_module(
        ctx.db, chat_id=chat_id, module_key=article_v1.MODULE_KEY, enabled=want,
        actor_id=ctx.user_id, source="chat_command")
    if not result["changed"]:
        await ctx.reply(f"⚖️ «Моя статья» в этом чате уже {'включена' if want else 'выключена'}.")
        return
    state = "включена" if want else "выключена"
    await ctx.reply(f"⚖️ «Моя статья» в этом чате <b>{state}</b>.\n{WHAT}")


def _case_text(user: str, number: str, description: str, *, intro: str, verdict: str) -> str:
    """Собранное дело в стиле v1: событие строкой, подробности цитатой, пометка пародии."""
    name = BY_NUMBER[number]
    return (
        f"⚖️ {intro}\n"
        f"<blockquote>Обвиняемый: {user}\n"
        f"Ст. {number} — {name}\n"
        f"{description}\n"
        f"{verdict}</blockquote>\n"
        f"{PARODY_MARK}"
    )


@registry.command("моя статья", aliases=("статья", "мою статью"), usage="моя статья",
                  bare=True, private=True, section="social", group="article",
                  summary="Пародийная «уголовная статья» про тебя: номер, шуточная расшифровка и «приговор».",
                  example="моя статья")
async def cmd_article(ctx: Ctx) -> None:
    chat_id = ctx.message.chat.id
    word = norm(ctx.args)
    if ctx.prefixed and word in ON_WORDS + OFF_WORDS:
        await _toggle_chat(ctx, chat_id, word in ON_WORDS)
        return
    if not await article_v1.chat_enabled(ctx.db, chat_id):
        await ctx.reply(BANK.pick("disabled"))
        return
    left = await article_v1.pause_left(ctx.db, chat_id, ctx.user_id)
    if left:
        await ctx.reply(BANK.pick("cooldown", sec=left))
        return
    try:
        today = _today()
        saved = await article_v1.today_key(ctx.db, chat_id, ctx.user_id, today)
        repeat = saved is not None
        if repeat:
            number, description = _case(int(saved))
        else:
            index = article.daily_description_index(ctx.user_id, today, len(DESCRIPTIONS))
            number, description = _case(index)
            await article_v1.remember(ctx.db, chat_id, ctx.user_id, str(index), today)
        commit = getattr(ctx.db, "commit", None)
        if commit:
            await commit()
    except Exception as error:
        from loguru import logger
        logger.warning("article case failed for {}: {}", ctx.user_id, error)
        await ctx.reply(BANK.pick("service"))
        return
    user = _display(ctx.user_id, ctx.message.from_user.username)
    intro = BANK.pick("repeat" if repeat else "intro")
    text = _case_text(user, number, description, intro=intro, verdict=BANK.pick("verdict"))
    # СТИЛЬ v1 (см. docs/CHAT_BOT_DESIGN_HANDOFF.md): событие строкой, подробности цитатой.
    await ctx.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
