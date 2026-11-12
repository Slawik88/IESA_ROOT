"""Виджеты в личке с ботом (S30, игрокам — S30b): состояние при отправке, ответы на запросы виджета, отправка.

Модуль виджета `services/widgets/<key>.py` (ключ — из core.widgets.REGISTRY):
    SAMPLE: dict                                          самое длинное правдоподобное состояние (стенд, проверка размеров)
    async def state(db, user_id, view) -> dict            состояние экрана `view` (None у виджета без экранов):
                                                          уходит в chat_data при отправке и в ответ на `<key>:s[:<вид>]`
    async def act(db, user_id, verb, args, *, action_id) -> Reply   нажатие в виджете (необязательно)
Номер состояния `r` и подпись надетого образа `k` (у Spec.themed) дописываются здесь; сам образ вшит в HTML при отправке. Отказ игроку — `raise Refused("текст")`:
виджет покажет текст. `action_id` уникален для запроса: сервисы с квитанциями по нему не выдадут награду дважды.

Запрос виджета не несёт его состояния, поэтому каждое действие проверяется по данным игрока, а не по словам виджета.
Отвечать нужно на каждый запрос, иначе через 15 секунд виджет покажет «бот не ответил»: это делает
bot/middlewares/widget_query.py, здесь только решение, что ответить.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from loguru import logger

from core import widgets as rules
from core.widgets import skin
from infrastructure.telegram_widgets import EditMessageWidgetData, SendWidget, WidgetQuery

SWITCH_FEATURES = ["all", "group:widgets"]


@dataclass
class Reply:
    answer: dict            # что получит виджет (номер `r` и подпись образа допишутся)
    persist: bool = False   # записать и как состояние сообщения: виджет нарисует его и после перезапуска Telegram


class Refused(Exception):
    """Понятный игроку отказ: текст уходит в ответ виджету."""


def module(key: str) -> ModuleType:
    if rules.spec(key) is None:
        raise KeyError(key)
    return importlib.import_module(f"services.widgets.{key}")


async def may_use(db, spec: rules.Spec, user_id: int) -> bool:
    """Создатель — всегда; игроки — у виджетов для игроков и только при включённом флаге «Виджеты для всех»."""
    from bot.chat.access import is_developer
    if is_developer(user_id):
        return True
    if spec.audience != rules.PLAYERS:
        return False
    from infrastructure.repositories import system_flags
    return await system_flags.is_enabled(db, rules.PLAYERS_FLAG)


async def switched_off(db) -> bool:
    from services import feature_switches
    return await feature_switches.disabled(db, SWITCH_FEATURES, None) is not None


async def _dressed(db, user_id: int) -> skin.Look:
    from services.skins_v3 import own_look
    return skin.of(await own_look(db, user_id))


async def _finish(db, spec: rules.Spec, user_id: int, payload: dict, *, limit: int) -> str:
    """Подпись образа (виджет сравнит её со вшитой и предложит новое табло), подгонка строк и номер состояния."""
    if spec.themed:
        payload = {**payload, "k": (await _dressed(db, user_id)).signature}
    return rules.encode({**rules.fit(payload), "r": rules.revision()}, limit=limit)


async def initial_state(db, key: str, user_id: int, view: str | None = None) -> str:
    spec = rules.REGISTRY[key]
    payload = await module(key).state(db, user_id, rules.view_of(spec, view))
    return await _finish(db, spec, user_id, payload, limit=rules.MAX_STATE_BYTES)


async def send(bot, db, user_id: int, key: str, *, view: str | None = None, reply_markup=None):
    """Прислать виджет игроку в личку с ботом. Только личка: другого места для виджетов в проде нет."""
    spec = rules.spec(key)
    if spec is None:
        raise Refused("Такого виджета нет.")
    if not await may_use(db, spec, user_id):
        raise Refused("Этот виджет пока доступен только создателю бота.")
    if await switched_off(db):
        raise Refused("Виджеты выключены: админка → «Функции» → «Виджеты в личке».")
    dressed = await _dressed(db, user_id) if spec.themed else skin.look(None)
    skin_id, _, tier = dressed.signature.partition(":")
    source = rules.html(key, skin_id or None, tier or "D")
    if rules.size_problems(source):   # образ не влез (контракт ловит это заранее) — тот же виджет без образа, а не отказ
        logger.warning(f"widget {key}: dressed for {dressed.signature} does not fit, sending plain")
        source = rules.html(key)
    problems = rules.size_problems(source)
    if problems:
        raise ValueError(f"widget {key}: " + "; ".join(problems))
    chat_data = await initial_state(db, key, user_id, view)
    return await bot(SendWidget(chat_id=int(user_id), html=source, chat_data=chat_data,
                                caption=spec.caption[:rules.MAX_CAPTION_CHARS], allow_queries=spec.queries,
                                reply_markup=reply_markup))


async def offer(bot, db, user_id: int, key: str, *, view: str | None = None, reply_markup=None):
    """Виджет вместо текста, если можно: сообщение виджета или None — тогда вызывающий шлёт прежний текст.

    None: виджет игроку не открыт, виджеты выключены, игрок выбрал текст или Telegram отказал в отправке
    (старый клиент тут ни при чём: ему Telegram доставляет подпись и кнопки). Заблокированный бот — не повод для
    текста, его ошибка уходит вызывающему, как у обычного сообщения."""
    spec = rules.spec(key)
    if spec is None or not await may_use(db, spec, user_id) or await switched_off(db):
        return None
    from infrastructure.repositories import dm_push as prefs
    if await prefs.prefers_text_menus(db, user_id):
        return None
    try:
        return await send(bot, db, user_id, key, view=view, reply_markup=reply_markup)
    except TelegramForbiddenError:
        raise
    except (TelegramBadRequest, TelegramAPIError, Refused) as exc:
        logger.warning(f"widget {key} not sent, falling back to text: {type(exc).__name__}: {str(exc)[:160]}")
        return None


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
    spec = rules.REGISTRY[key]
    if not await may_use(db, spec, user_id):
        return rules.error("Этот виджет пока доступен только создателю бота."), None
    if await switched_off(db):
        return rules.error("Виджеты сейчас выключены. Загляни позже."), None
    from services.dm_push import player_reachable
    if not await player_reachable(db, user_id):   # аккаунт на удалении или заблокирован: ни данных, ни наград
        return rules.error("Сейчас это недоступно."), None
    widget = module(key)
    try:
        if verb == rules.SNAPSHOT_VERB:
            reply = Reply(await widget.state(db, user_id, rules.view_of(spec, args[0] if args else None)))
        else:
            act = getattr(widget, "act", None)
            if act is None:
                return rules.error("Этот виджет устарел. Попроси новый."), None
            reply = await act(db, user_id, verb, args, action_id=f"widget:{query.id}"[:96])
    except Refused as refusal:
        return rules.error(str(refusal)), None
    text = await _finish(db, spec, user_id, reply.answer, limit=min(rules.MAX_ANSWER_BYTES, rules.MAX_STATE_BYTES))
    return text, text if reply.persist else None


async def persist(bot, chat_id: int, message_id: int, state: str) -> None:
    """Новое состояние сообщения. Telegram отвечает «not modified», если оно то же самое: это не ошибка."""
    try:
        await bot(EditMessageWidgetData(chat_id=int(chat_id), message_id=int(message_id), chat_data=state))
    except TelegramBadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
