"""Виджеты в личке с ботом (S30): состояние при отправке, ответы на запросы виджета, отправка из админки.

Модуль виджета `services/widgets/<key>.py` (ключ — из core.widgets.REGISTRY):
    SAMPLE: dict                                   самое длинное правдоподобное состояние (стенд, проверка размеров)
    async def state(db, user_id) -> dict           состояние: уходит в chat_data при отправке и в ответ на `<key>:s`
    async def act(db, user_id, verb, args) -> Reply   нажатие в виджете (необязательно)
Номер состояния `r` дописывается здесь. Отказ игроку — `raise Refused("текст")`: виджет покажет текст.

Запрос виджета не несёт его состояния, поэтому каждое действие проверяется по данным игрока, а не по словам виджета.
Отвечать нужно на каждый запрос, иначе через 15 секунд виджет покажет «бот не ответил»: это делает
bot/middlewares/widget_query.py, здесь только решение, что ответить.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType

from aiogram.exceptions import TelegramBadRequest

from core import widgets as rules
from infrastructure.telegram_widgets import EditMessageWidgetData, SendWidget, WidgetQuery

SWITCH_FEATURES = ["all", "group:widgets"]


@dataclass
class Reply:
    answer: dict            # что получит виджет (номер `r` допишется)
    persist: bool = False   # записать и как состояние сообщения: виджет нарисует его и после перезапуска Telegram


class Refused(Exception):
    """Понятный игроку отказ: текст уходит в ответ виджету."""


def module(key: str) -> ModuleType:
    if rules.spec(key) is None:
        raise KeyError(key)
    return importlib.import_module(f"services.widgets.{key}")


def may_use(spec: rules.Spec, user_id: int) -> bool:
    if spec.audience == rules.PLAYERS:
        return True
    from bot.chat.access import is_developer
    return is_developer(user_id)


async def switched_off(db) -> bool:
    from services import feature_switches
    return await feature_switches.disabled(db, SWITCH_FEATURES, None) is not None


def _stamp(payload: dict, *, limit: int) -> str:
    return rules.encode({**payload, "r": rules.revision()}, limit=limit)


async def initial_state(db, key: str, user_id: int) -> str:
    return _stamp(await module(key).state(db, user_id), limit=rules.MAX_STATE_BYTES)


async def send(bot, db, user_id: int, key: str):
    """Прислать виджет игроку в личку с ботом. Только личка: другого места для виджетов в проде нет."""
    spec = rules.spec(key)
    if spec is None:
        raise Refused("Такого виджета нет.")
    if not may_use(spec, user_id):
        raise Refused("Этот виджет пока доступен только создателю бота.")
    if await switched_off(db):
        raise Refused("Виджеты выключены: админка → «Функции» → «Виджеты в личке».")
    source = rules.html(key)
    problems = rules.size_problems(source)
    if problems:
        raise ValueError(f"widget {key}: " + "; ".join(problems))
    chat_data = await initial_state(db, key, user_id)
    return await bot(SendWidget(chat_id=int(user_id), html=source, chat_data=chat_data,
                                caption=spec.caption[:rules.MAX_CAPTION_CHARS], allow_queries=spec.queries))


async def answer(db, query: WidgetQuery) -> tuple[str, str | None]:
    """(ответ виджету, новое состояние сообщения или None). Ошибки кода летят наружу: их ловит приёмник запросов."""
    if not query.in_own_dm:
        return rules.error("Этот виджет работает только в личке с ботом."), None
    if query.type.type != "data":
        return rules.error("Оплата и подписи кошельком в виджетах пока не работают."), None
    parsed = rules.parse_query(query.data)
    if parsed is None:
        return rules.error("Этот виджет устарел. Попроси новый."), None
    key, verb, args = parsed
    user_id = query.sender.id
    if not may_use(rules.REGISTRY[key], user_id):
        return rules.error("Этот виджет пока доступен только создателю бота."), None
    if await switched_off(db):
        return rules.error("Виджеты сейчас выключены. Загляни позже."), None
    widget = module(key)
    try:
        if verb == rules.SNAPSHOT_VERB:
            reply = Reply(await widget.state(db, user_id))
        else:
            act = getattr(widget, "act", None)
            if act is None:
                return rules.error("Этот виджет устарел. Попроси новый."), None
            reply = await act(db, user_id, verb, args)
    except Refused as refusal:
        return rules.error(str(refusal)), None
    text = _stamp(reply.answer, limit=min(rules.MAX_ANSWER_BYTES, rules.MAX_STATE_BYTES))
    return text, text if reply.persist else None


async def persist(bot, chat_id: int, message_id: int, state: str) -> None:
    """Новое состояние сообщения. Telegram отвечает «not modified», если оно то же самое: это не ошибка."""
    try:
        await bot(EditMessageWidgetData(chat_id=int(chat_id), message_id=int(message_id), chat_data=state))
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
