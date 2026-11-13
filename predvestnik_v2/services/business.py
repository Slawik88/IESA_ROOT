"""Бот в личных переписках игрока (Telegram Business, S24): кто может командовать, где бот включён, повторы.

Правила здесь, а не в боте. Главное правило безопасности: команду выполняет только **владелец связи** — игрок, который
подключил бота к своему аккаунту. Сообщения собеседника не разбираются вовсе: он не может ни включить бота, ни потратить
деньги игрока. Деньги из переписки не списываются никогда: перевод только создаёт заявку, подтверждает её владелец
кнопкой в личке с ботом (обычный перевод, те же проверки).
"""
from __future__ import annotations

from core import business as rules
from core import business_settings as features
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
        from loguru import logger
        from services import pair_games   # сначала вернуть замороженные жетоны открытых партий, потом стереть связь
        try:
            await pair_games.cancel_for_connection(db, connection_id)
        except Exception as exc:   # жетоны всё равно вернёт обслуживание через сутки; связь стираем в любом случае
            logger.warning(f"pair games refund on disconnect failed: {type(exc).__name__}: {exc}")
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
    if found[0] not in rules.ALWAYS and not await repo.chat_enabled(db, connection["id"], chat_id):
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


# ── S29a: настройки, пульт, отказы собеседника ──────────────────────────────

async def global_settings(db, user_id: int) -> dict[str, bool]:
    """Общие настройки игрока: по каждой функции итоговое значение (с учётом умолчаний)."""
    stored = await repo.settings(db, user_id)
    return {key: features.resolve(key, None, stored.get(key)) for key in features.ORDER}


async def chat_overrides(db, connection_id: str, chat_id: int) -> dict[str, bool]:
    """Что игрок выставил отдельно для этой переписки (без строки — «как в общих»)."""
    return await repo.chat_settings(db, connection_id, chat_id)


async def feature_on(db, connection: dict, chat_id: int, key: str) -> bool:
    """Включена ли функция в этой переписке: переписка → общие → по умолчанию; и не выключена ли администрацией."""
    from services import feature_switches
    admin_key = features.ADMIN_SWITCHES.get(key)
    if admin_key and await feature_switches.disabled(db, [admin_key], None) is not None:
        return False
    chat = (await repo.chat_settings(db, connection["id"], chat_id)).get(key)
    return features.resolve(key, chat, (await repo.settings(db, connection["user_id"])).get(key))


async def toggle_global(db, user_id: int, key: str) -> bool:
    if key not in features.FEATURES:
        raise KeyError(key)
    value = not (await global_settings(db, user_id))[key]
    await repo.set_setting(db, user_id, key, value)
    return value


async def cycle_chat(db, connection_id: str, chat_id: int, key: str) -> bool | None:
    if key not in features.FEATURES:
        raise KeyError(key)
    value = features.next_chat_value((await repo.chat_settings(db, connection_id, chat_id)).get(key))
    await repo.set_chat_setting(db, connection_id, chat_id, key, value)
    return value


async def remote_for(db, connection_id: str, chat_id: int, partner_name: str) -> int:
    return await repo.remote_id(db, connection_id, chat_id, partner_name)


async def remote(db, remote_id: int, user_id: int) -> dict | None:
    """Пульт переписки — только для владельца связи (кнопки пульта лежат в его личке)."""
    found = await repo.remote(db, remote_id)
    return found if found and found["connection"]["user_id"] == int(user_id) else None


async def action_order(db, user_id: int, actions: list[str]) -> list[str]:
    return features.order_by_use(actions, await repo.usage(db, user_id))


async def count_use(db, user_id: int, action: str) -> None:
    await repo.count_use(db, user_id, action)


async def partner_declines_offers(db, user_id: int) -> bool:
    """Собеседник нажал «🙅 Не предлагать мне»: игры, приглашения и совместимость ему не отправляются ни от кого."""
    return await repo.partner_opted_out(db, user_id)


async def set_partner_optout(db, user_id: int, opted_out: bool) -> bool:
    return await repo.set_partner_optout(db, user_id, opted_out)


async def is_player(db, user_id: int) -> bool:
    found = await repo.known_player(db, user_id)
    return bool(found and not found["deleting"])
