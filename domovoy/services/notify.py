"""
services/notify.py — доставка уведомлений по персональным настройкам.

Каждый участник сам выбрал канал для каждого события (личка / чат дома / выкл).
Недоступная личка и незапривязанный чат — не ошибка: деградация с записью в лог.
"""
from loguru import logger

from core import settings_registry as reg
from infrastructure import repositories as repo
from core.money import format_amount


async def _resolve_targets(house, event_key: str, tg_ids: list[int]) -> tuple[list[int], list[int]]:
    """Получатели в личке и в чате; выключенные уведомления не доставляются."""
    private_ids: list[int] = []
    chat_ids: list[int] = []
    for tg_id in tg_ids:
        raw = await repo.settings.notify_settings_all(house["id"], tg_id)
        definition = reg.NOTIFY_SETTING_BY_KEY.get(event_key)
        channel = raw.get(event_key, definition.default if definition else reg.NOTIFY_OFF)
        if channel == reg.NOTIFY_PRIVATE:
            private_ids.append(tg_id)
        elif channel == reg.NOTIFY_CHAT:
            chat_ids.append(tg_id)
    if chat_ids and house["chat_id"] is None:
        # Чат не привязан — тихо падаем в личку, уведомление не теряется.
        for tg_id in chat_ids:
            if tg_id not in private_ids:
                private_ids.append(tg_id)
        chat_ids = []
    return private_ids, chat_ids


async def deliver(
    bot, house, event_key: str,
    texts_by_tg: dict[int, str],
    chat_text: str | None = None,
    markup=None,
) -> None:
    """Разослать уведомление о событии тем, кто его включил."""
    private_ids, chat_ids = await _resolve_targets(house, event_key, list(texts_by_tg))
    for tg_id in private_ids:
        try:
            await bot.send_message(tg_id, texts_by_tg[tg_id], reply_markup=markup)
        except Exception as exc:  # личка недоступна: пользователь не стартовал бот или заблокировал
            logger.warning(f"✉️ Личка {tg_id} недоступна ({event_key}): {exc}")
    if chat_ids and chat_text is not None:
        try:
            await bot.send_message(house["chat_id"], chat_text)
        except Exception as exc:
            logger.warning(f"✉️ Чат {house['chat_id']} недоступен ({event_key}): {exc}")
    elif chat_ids:
        # Персональные события без общего текста тоже доставляются в выбранный чат.
        for text in dict.fromkeys(texts_by_tg[tg_id] for tg_id in chat_ids):
            try:
                await bot.send_message(house["chat_id"], text, reply_markup=markup)
            except Exception as exc:
                logger.warning(f"✉️ Чат {house['chat_id']} недоступен ({event_key}): {exc}")


async def broadcast(
    bot, house, event_key: str, text: str,
    exclude_tg_ids: set[int] = frozenset(),
) -> None:
    """Одно и то же сообщение всем участникам дома (по их настройкам)."""
    members = await repo.houses.list_active_members(house["id"])
    texts = {m["tg_id"]: text for m in members if m["tg_id"] not in exclude_tg_ids}
    await deliver(bot, house, event_key, texts, chat_text=text if texts else None)


async def contribution_declared(bot, house, contribution, currency: str, markup=None) -> None:
    from services import households

    member = await households.membership(house["id"], contribution["tg_id"])
    who = member["display_name"] if member else "Жилец"
    texts = {}
    for recipient in await households.members(house["id"]):
        if await households.can(house["id"], recipient["tg_id"], "confirm_contributions"):
            texts[recipient["tg_id"]] = (
                f"💸 {who} заявил взнос {format_amount(contribution['amount_kop'], currency)} "
                f"за {contribution['month']}. Подтверждаете?"
            )
    if texts:
        await deliver(bot, house, "contribution_declared", texts, markup=markup)
