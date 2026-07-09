# services/membership.py — сверка реального членства в чате с БД (is_left).
#
# Почему ghost-участники вообще появляются: Telegram шлёт push-апдейт chat_member
# (кто-то вышел/кикнут) боту ТОЛЬКО если бот — администратор этого чата. В чатах,
# где бот обычный участник, уходы проходят мимо бота полностью — is_left годами
# остаётся FALSE, и ушедший игрок вечно висит в топах/списках чата.
#
# Фикс — не полагаться только на push: перед выводом любого списка «кто в чате»
# (топ, чистка, список ресты и т.п.) сверяем РЕАЛЬНОЕ членство через getChatMember
# (pull, работает для бота в любом статусе — не только для админов) для узкого
# набора кандидатов, которые и так уже отобраны к показу. Найденных беглецов
# помечаем is_left=TRUE — фикс самозакрепляется, повторно спрашивать Telegram
# про них уже не придётся.
import os
import asyncio

import httpx

from infrastructure.repositories.moderation import set_user_left_status

_API_URL = "https://api.telegram.org/bot{token}/{method}"


def bot_tg_id() -> int | None:
    """Собственный Telegram ID бота — вычисляется из BOT_TOKEN (формат <id>:<secret>,
    так же его получает aiogram в Bot.id). Бот физически является строкой в
    user_chat_stats/users (Telegram видит его как обычного участника чата), поэтому
    места, что строят списки «кто в чате» (чистка, топы), должны сами исключать
    этот ID — push/middleware-фильтры ловят только НОВЫЕ события, а не старые строки,
    заведённые до них."""
    token = os.getenv("BOT_TOKEN", "")
    if not token or ":" not in token:
        return None
    try:
        return int(token.split(":", 1)[0])
    except ValueError:
        return None


async def check_chat_members(
    chat_id: int, user_ids: list[int], concurrency: int = 8
) -> dict[int, bool]:
    """{user_id: сейчас_в_чате}. User_id пропускается из результата (не False!),
    если Telegram не смог ответить однозначно (сеть/рейт-лимит/деактивирован) —
    вызывающий код не должен трактовать отсутствие как «ушёл»."""
    token = os.getenv("BOT_TOKEN", "")
    ids = list(dict.fromkeys(user_ids))  # dedupe, сохраняя порядок
    if not token or not ids:
        return {}

    result: dict[int, bool] = {}
    sem = asyncio.Semaphore(concurrency)

    async def _check(client: httpx.AsyncClient, uid: int) -> None:
        async with sem:
            try:
                r = await client.post(
                    _API_URL.format(token=token, method="getChatMember"),
                    json={"chat_id": chat_id, "user_id": uid},
                )
                data = r.json()
            except Exception:
                return
            if data.get("ok"):
                status = data["result"]["status"]
                result[uid] = status not in ("left", "kicked")

    async with httpx.AsyncClient(timeout=8) as client:
        await asyncio.gather(*(_check(client, uid) for uid in ids))
    return result


async def prune_ghosts(db, chat_id: int, user_ids: list[int]) -> set[int]:
    """Сверяет кандидатов с Telegram и помечает реально ушедших is_left=TRUE.
    Возвращает set user_id, которых нужно убрать из уже полученной выборки
    (сама выборка была сделана ДО сверки и ghost'ов ещё содержит)."""
    membership = await check_chat_members(chat_id, user_ids)
    left_ids = {uid for uid, present in membership.items() if not present}
    for uid in left_ids:
        await set_user_left_status(db, chat_id, uid, True)
    return left_ids
