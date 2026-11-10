"""Бот в личных переписках игрока (Telegram Business, S24): кто может командовать, где бот включён, повторы.

Правила здесь, а не в боте. Главное правило безопасности: команду выполняет только **владелец связи** — игрок, который
подключил бота к своему аккаунту. Сообщения собеседника не разбираются вовсе: он не может ни включить бота, ни потратить
деньги игрока. Деньги из переписки не списываются никогда: перевод только создаёт заявку, подтверждает её владелец
кнопкой в личке с ботом (обычный перевод, те же проверки).
"""
from __future__ import annotations

from core import business as rules
from infrastructure.repositories import business as repo


async def ensure_schema(db) -> None:
    await repo.ensure_schema(db)


async def switched_off(db) -> bool:
    """Режим выключен в «Функции» (весь бот или «Бизнес-режим»)."""
    from services import feature_switches
    return await feature_switches.disabled(db, ["all", rules.SWITCH], None) is not None


async def owner_may_act(db, user_id: int) -> bool:
    """Владелец связи может командовать: не заблокирован в админке и не удаляет аккаунт (как в чатах с ботом)."""
    from services import global_moderation
    if await global_moderation.is_blocked(db, user_id):
        return False
    found = await repo.known_player(db, user_id)
    return not (found and found["deleting"])


async def command_switched_off(db, name: str, section: str, group: str = "") -> bool:
    """Та же команда в чатах выключена в «Функции» («бот перевод», «шипирить»): в переписках она тоже не работает."""
    from services import feature_switches
    return await feature_switches.disabled(db, feature_switches.command_features(name, section, group), None) is not None


async def partner_opted_out_of_pairs(db, user_id: int) -> bool:
    """Собеседник попросил «не шипирить меня»: совместимость с ним не считаем."""
    from infrastructure.repositories import ship_v1
    return await ship_v1.opted_out(db, user_id)


async def remember_connection(db, *, connection_id: str, user_id: int, user_chat_id: int, enabled: bool, can_reply: bool) -> str:
    """Обновление связи от Telegram: 'new' — подключил впервые, 'updated' — поменял настройки, 'dropped' — отключил
    (все данные связи удалены), 'gone' — отключение уже учтено."""
    if not enabled:
        return "dropped" if await repo.drop_connection(db, connection_id) else "gone"
    return "new" if await repo.save_connection(db, connection_id, user_id, user_chat_id, can_reply) else "updated"


async def owner_of(db, connection_id: str) -> dict | None:
    return await repo.connection(db, connection_id)


async def command_for(db, *, connection: dict, sender_id: int, chat_id: int, message_id: int, text: str | None,
                      sent_by_bot: bool) -> tuple[str, str] | None:
    """Что выполнить по сообщению из переписки или None. None для всего, что не команда владельца: сообщений собеседника,
    ответов самого бота, обычного текста. Одна и та же команда выполняется один раз, даже если Telegram пришлёт её снова.
    В переписке, где бот выключен, проходит только «бот вкл» (и «бот помощь», ответ на неё уходит в личку)."""
    if sent_by_bot or int(sender_id) != int(connection["user_id"]):
        return None
    found = rules.parse(text)
    if found is None:
        return None
    if found[0] not in ("on", "help") and not await repo.chat_enabled(db, connection["id"], chat_id):
        return None
    if not await repo.mark_handled(db, connection["id"], chat_id, message_id, rules.HANDLED_KEEP_HOURS):
        return None
    return found


async def chat_enabled(db, connection_id: str, chat_id: int) -> bool:
    return await repo.chat_enabled(db, connection_id, chat_id)


async def set_chat(db, connection_id: str, chat_id: int, enabled: bool) -> bool:
    return await repo.set_chat(db, connection_id, chat_id, enabled)


async def transfer_target(db, user_id: int) -> str:
    """Можно ли переводить собеседнику: 'ok', 'stranger' (бот его не знает: он не играет) или 'deleting'."""
    found = await repo.known_player(db, user_id)
    if found is None:
        return "stranger"
    return "deleting" if found["deleting"] else "ok"

