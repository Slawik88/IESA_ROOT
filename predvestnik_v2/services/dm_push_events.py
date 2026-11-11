"""Сборщики событий для уведомлений в личку: что случилось с игроком и пора ли ему написать.

Каждый сборщик смотрит только игроков, которые согласились на свою категорию (JOIN по user_notification_prefs),
и ставит событие через services.dm_push.enqueue: там же проверяются личка, пауза, лимиты. У события свой dedup_key,
поэтому повторный проход ничего не дублирует. Тексты — по docs/PLAYER_COPY.md: коротко, на «ты», без внутренних слов.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger

from core import dm_push as rules
from core.chests_v1 import KEY_TIER_NAMES, tier_for_source
from infrastructure.repositories import system_flags
from services import dm_push

BATCH = 500   # событий одного вида за проход; остальное подберёт следующий проход

# Только согласившиеся и те, кому сейчас вообще можно писать: иначе первые BATCH недоступных игроков занимали бы весь проход.
_READY = ("JOIN dm_push_settings ds ON ds.user_id = {alias}.user_id AND ds.dm_confirmed_at IS NOT NULL "
          "AND ds.dm_disabled_at IS NULL AND ds.paused_at IS NULL")
_CONSENT = ("JOIN user_notification_prefs np ON np.user_id = {alias}.user_id AND np.category = ? AND np.enabled = TRUE " + _READY)
# Событие уже стоит в очереди или отправлено: выборка его не повторяет.
_NEW = "NOT EXISTS (SELECT 1 FROM dm_push_outbox ob WHERE ob.user_id = {alias}.user_id AND ob.dedup_key = {key})"


async def _has_table(db, name: str) -> bool:
    async with db.execute("SELECT to_regclass(?) IS NOT NULL", (name,)) as c:
        row = await c.fetchone()
    return bool(row and row[0])


async def _pets(db, now: datetime) -> int:
    """Питомец вернулся с задания: добыча ждёт, пока её не заберут."""
    if not await _has_table(db, "pet_v2_runs") or not await system_flags.is_enabled(db, "pets_v2"):
        return 0
    async with db.execute(
        f"SELECT r.id, r.user_id FROM pet_v2_runs r {_CONSENT.format(alias='r')} "
        "WHERE r.status = 'active' AND r.ends_at <= ? AND r.ends_at > ? AND " + _NEW.format(alias="r", key="'pet_run:' || r.id")
        + " ORDER BY r.ends_at LIMIT ?",
        ("pets", now, now - rules.EVENT_TTL, BATCH),
    ) as c:
        rows = await c.fetchall()
    sent = 0
    for run_id, user_id in rows:
        sent += await dm_push.enqueue(
            db, user_id=int(user_id), category="pets", dedup_key=f"pet_run:{run_id}",
            text="🐾 <b>Питомец вернулся</b>\nДобыча ждёт тебя — забери её, пока не пропала.",
            button={"kind": "app", "section": "pets", "label": "🐾 К питомцам"},
        )
    return sent


async def _quests(db, now: datetime) -> int:
    """Начался новый день: задания дня обновились."""
    if not await _has_table(db, "user_notification_prefs"):
        return 0
    key = f"quests:daily:{now.astimezone(timezone.utc).date().isoformat()}"
    async with db.execute(
        "SELECT np.user_id FROM user_notification_prefs np " + _READY.format(alias="np") +
        " WHERE np.category = 'quests' AND np.enabled = TRUE "
        "AND NOT EXISTS (SELECT 1 FROM dm_push_outbox o WHERE o.user_id = np.user_id AND o.dedup_key = ?) "
        "ORDER BY np.user_id LIMIT ?", (key, BATCH),
    ) as c:
        rows = await c.fetchall()
    sent = 0
    for (user_id,) in rows:
        sent += await dm_push.enqueue(
            db, user_id=int(user_id), category="quests", dedup_key=key,
            text="📋 <b>Новые задания дня</b>\nВыполни их и забери награду.",
            button={"kind": "app", "section": "quests", "label": "📋 К заданиям"},
        )
    return sent


async def _market(db, now: datetime) -> int:
    """Ордер на бирже исполнен (только если биржа включена)."""
    if not await _has_table(db, "player_coin_orders_v1") or not await system_flags.is_enabled(db, "economy_player_exchange_v1"):
        return 0
    async with db.execute(
        f"SELECT o.id, o.user_id, o.side FROM player_coin_orders_v1 o {_CONSENT.format(alias='o')} "
        "WHERE o.status = 'filled' AND o.actor_kind = 'player' AND o.time_in_force = 'gtc' AND o.closed_at IS NOT NULL "
        "AND o.closed_at > ? AND " + _NEW.format(alias="o", key="'order:' || o.id") + " ORDER BY o.closed_at LIMIT ?", ("market", now - rules.EVENT_TTL, BATCH),
    ) as c:
        rows = await c.fetchall()
    sent = 0
    for order_id, user_id, side in rows:
        what = "на покупку" if side == "buy" else "на продажу"
        sent += await dm_push.enqueue(
            db, user_id=int(user_id), category="market", dedup_key=f"order:{order_id}",
            text=f"📈 <b>Ордер исполнен</b>\nТвой ордер {what} на бирже выполнен целиком.",
            button={"kind": "app", "section": "exchange", "label": "📈 На биржу"},
        )
    return sent


async def _season(db, now: datetime) -> int:
    """Игровой сезон заканчивается через трое суток или меньше: ещё можно улучшить место в рейтинге."""
    from core import seasons
    number = seasons.season_number(now)
    end = seasons.season_bounds(number)[1]
    if not (timedelta(0) < end - now <= timedelta(days=3)):
        return 0
    days = max(1, -(-int((end - now).total_seconds()) // 86400))
    word = "день" if days == 1 else "дня"
    key = f"season_end:{number}"
    async with db.execute(
        "SELECT np.user_id FROM user_notification_prefs np " + _READY.format(alias="np") +
        " WHERE np.category = 'season' AND np.enabled = TRUE "
        "AND NOT EXISTS (SELECT 1 FROM dm_push_outbox o WHERE o.user_id = np.user_id AND o.dedup_key = ?) "
        "ORDER BY np.user_id LIMIT ?", (key, BATCH),
    ) as c:
        rows = await c.fetchall()
    sent = 0
    for (user_id,) in rows:
        sent += await dm_push.enqueue(
            db, user_id=int(user_id), category="season", dedup_key=key,
            text=f"🏁 <b>Сезон скоро закончится</b>\nОсталось {days} {word}. Загляни в «Игры»: место в рейтинге ещё можно улучшить.",
            button={"kind": "app", "section": "games", "label": "🎮 В игры"},
        )
    return sent


_report_cursor: dict[int, int] = {}   # сезон → последний разобранный игрок: пустые итоги не перебираются каждый проход


async def _season_report(db, now: datetime) -> int:
    """Сезон закончился: личный итог (Пропуск, места, партии, образы) тем, кто включил «Сезон». Один раз за сезон."""
    from services import season_report
    number = season_report.due_season(now)
    if number is None:
        return 0
    key = f"season_report:{number}"
    async with db.execute(
        "SELECT np.user_id FROM user_notification_prefs np " + _READY.format(alias="np") +
        " WHERE np.category = 'season' AND np.enabled = TRUE AND np.user_id > ? "
        "AND NOT EXISTS (SELECT 1 FROM dm_push_outbox o WHERE o.user_id = np.user_id AND o.dedup_key = ?) "
        "ORDER BY np.user_id LIMIT ?", (_report_cursor.get(number, 0), key, BATCH),
    ) as c:
        rows = await c.fetchall()
    sent = 0
    for (user_id,) in rows:
        data = await season_report.report(db, int(user_id), number)
        _report_cursor[number] = int(user_id)
        if data is not None:
            sent += await dm_push.enqueue(
                db, user_id=int(user_id), category="season", dedup_key=key, text=season_report.text(data),
                button={"kind": "app", "section": "pass", "label": "🏆 Пропуск нового сезона"},
            )
    return sent


HOLIDAY_LOOKS_NOTICE = timedelta(days=3)
_HOLIDAY_ICON = {"halloween": "🎃", "new_year": "🎄", "valentine": "💞"}


async def _holiday_looks(db, now: datetime) -> int:
    """Праздничные образы уходят из магазина через трое суток или меньше, а у игрока собраны не все. Один раз за окно."""
    from core.skins_v3_catalog import SEASONS, SKINS
    from core.skins_v3_collection import season_window
    if not await _has_table(db, "skins_v3_owned"):
        return 0
    sent = 0
    for season_id, spec in SEASONS.items():
        window = season_window(season_id, now)
        end = datetime.fromisoformat(window["ends_at"])
        if not window["open"] or not (timedelta(0) < end - now <= HOLIDAY_LOOKS_NOTICE):
            continue
        looks = [k for k, s in SKINS.items() if s.get("season") == season_id and not s.get("exclusive")]
        if not looks:
            continue
        key = f"holiday_looks:{season_id}:{end.date().isoformat()}"
        days = max(1, -(-int((end - now).total_seconds()) // 86400))
        word = "день" if days == 1 else "дня"
        async with db.execute(
            "SELECT np.user_id, ARRAY(SELECT o.skin_id FROM skins_v3_owned o WHERE o.user_id = np.user_id "
            "AND o.skin_id = ANY(?::text[])) FROM user_notification_prefs np " + _READY.format(alias="np") +
            " WHERE np.category = 'events' AND np.enabled = TRUE "
            "AND NOT EXISTS (SELECT 1 FROM dm_push_outbox ob WHERE ob.user_id = np.user_id AND ob.dedup_key = ?) "
            "AND (SELECT COUNT(*) FROM skins_v3_owned o WHERE o.user_id = np.user_id AND o.skin_id = ANY(?::text[])) < ? "
            "ORDER BY np.user_id LIMIT ?", (looks, key, looks, len(looks), BATCH),
        ) as c:
            rows = await c.fetchall()
        for user_id, owned in rows:
            missing = [SKINS[k]["name"] for k in looks if k not in set(owned or [])]
            sent += await dm_push.enqueue(
                db, user_id=int(user_id), category="events", dedup_key=key,
                text=(f"{_HOLIDAY_ICON.get(season_id, '🎁')} <b>Праздничные образы скоро уйдут</b>\n"
                      f"«{spec['name']}» в магазине образов ещё {days} {word}. Пока не твои: {', '.join(missing)}.\n"
                      "Потом эти образы вернутся только через год."),
                button={"kind": "app", "section": "looks", "label": "🎨 К образам"},
            )
    return sent


async def social(db, *, user_id: int, dedup_key: str, text: str, button: dict | None = None) -> bool:
    """Событие «Люди» (перевод в чате, предложение брака, приглашение в семью): ставится сразу из обработчика.
    Никогда не роняет сам обработчик: уведомление — дополнение, действие игрока уже выполнено."""
    try:
        return await dm_push.enqueue(db, user_id=int(user_id), category="social", dedup_key=dedup_key, text=text, button=button)
    except Exception as exc:
        logger.warning(f"dm push social {dedup_key} skipped: {type(exc).__name__}: {exc}")
        return False


async def _vip(db, now: datetime) -> int:
    """VIP закончится меньше чем через 3 дня."""
    from core.constants import VIP_EXPIRY_REMINDER_DAYS
    if not await _has_table(db, "vip_subscriptions"):
        return 0
    async with db.execute(
        f"SELECT v.user_id, v.expires_at FROM vip_subscriptions v {_CONSENT.format(alias='v')} "
        "WHERE v.expires_at > ? AND v.expires_at <= ? AND "
        + _NEW.format(alias="v", key="'vip_end:' || to_char(v.expires_at, 'YYYY-MM-DD')") + " ORDER BY v.expires_at LIMIT ?",
        ("vip_expiry", now.replace(tzinfo=None), (now + timedelta(days=VIP_EXPIRY_REMINDER_DAYS)).replace(tzinfo=None), BATCH),
    ) as c:
        rows = await c.fetchall()
    sent = 0
    for user_id, expires_at in rows:
        sent += await dm_push.enqueue(
            db, user_id=int(user_id), category="vip_expiry", dedup_key=f"vip_end:{expires_at.date().isoformat()}",
            text=f"⏳ <b>VIP скоро закончится</b>\nСрок идёт до {expires_at.strftime('%d.%m')}. Продлить можно в магазине.",
            button={"kind": "app", "section": "vip", "label": "⭐ Продлить VIP"},
        )
    return sent


_PASS_EVERY = timedelta(minutes=30)   # статус Пропуска считается по каждому согласившемуся: не чаще раза в полчаса
_pass_checked: list[datetime] = []
_pass_cursor = [0]


async def ready_pass_seasons(db, user_id: int, now: datetime) -> list[int]:
    """Сезоны Пропуска, в которых есть награда, которую игрок прямо сейчас может забрать (аккаунт подходит по возрасту)."""
    from services import league_pass
    view = await league_pass.status(db, user_id=int(user_id), now=now)
    if not view.get("active") or not view.get("account", {}).get("eligible", True):
        return []
    ready = []
    for season in view.get("seasons", []):
        rows = season.get("track", [])
        has_level = any(r[t]["state"] == "ready" for r in rows for t in ("free", "vip"))
        if has_level or season.get("repeat", {}).get("ready"):
            ready.append(int(season["season"]))
    return ready


async def _pass(db, now: datetime) -> int:
    """В Пропуске есть награда, которую можно забрать: одно сообщение в сутки."""
    if _pass_checked and now - _pass_checked[0] < _PASS_EVERY:
        return 0
    _pass_checked[:] = [now]
    key = f"pass:{now.astimezone(timezone.utc).date().isoformat()}"
    async with db.execute(
        "SELECT np.user_id FROM user_notification_prefs np " + _READY.format(alias="np") +
        " WHERE np.category = 'pass' AND np.enabled = TRUE AND np.user_id > ? "
        "AND NOT EXISTS (SELECT 1 FROM dm_push_outbox o WHERE o.user_id = np.user_id AND o.dedup_key = ?) "
        "ORDER BY np.user_id LIMIT ?", (_pass_cursor[0], key, BATCH),
    ) as c:
        rows = await c.fetchall()
    # Курсор идёт по игрокам кругом: те, у кого награды нет, не должны занимать первые места навсегда.
    _pass_cursor[0] = int(rows[-1][0]) if len(rows) == BATCH else 0
    sent = 0
    for (user_id,) in rows:
        if not await ready_pass_seasons(db, int(user_id), now):
            continue
        sent += await dm_push.enqueue(
            db, user_id=int(user_id), category="pass", dedup_key=key,
            text="🏆 <b>В Пропуске есть награда</b>\nМожно забрать прямо здесь.",
            button={"kind": "cb", "data": "dn:claim:pass", "label": "🎁 Забрать награды"},
        )
    return sent


_DIGEST_LIMIT = 2000
_digest_seen: dict[str, set[tuple[int, str]]] = {}
_digest_day = [""]


async def _daily_digest(db, now, *, category, from_hour, to_hour, build_text) -> int:
    today = now.astimezone(timezone.utc).date().isoformat()
    if _digest_day[0] != today:
        _digest_seen.clear()
        _digest_day[0] = today
    seen = _digest_seen.setdefault(category, set())
    async with db.execute(
        "SELECT np.user_id, ds.tz_offset FROM user_notification_prefs np " + _READY.format(alias="np") +
        " WHERE np.category = ? AND np.enabled = TRUE "
        "AND ((EXTRACT(HOUR FROM ?::timestamp)::int + ds.tz_offset + 24) % 24) >= ? "
        "AND ((EXTRACT(HOUR FROM ?::timestamp)::int + ds.tz_offset + 24) % 24) < ? "
        "AND NOT EXISTS (SELECT 1 FROM unnest(?::bigint[], ?::text[]) AS seen(user_id, local_day) "
        "WHERE seen.user_id = np.user_id AND seen.local_day = "
        "to_char(?::timestamp + make_interval(hours => ds.tz_offset::int), 'YYYY-MM-DD')) "
        "AND NOT EXISTS (SELECT 1 FROM dm_push_outbox o WHERE o.user_id = np.user_id AND o.dedup_key = "
        "? || ':' || to_char(?::timestamp + make_interval(hours => ds.tz_offset::int), 'YYYY-MM-DD')) "
        "ORDER BY np.user_id LIMIT ?",
        (category, now, from_hour, now, to_hour, [uid for uid, _ in seen], [day for _, day in seen], now,
         category, now, _DIGEST_LIMIT),
    ) as c:
        rows = await c.fetchall()
    sent = 0
    for user_id, tz_offset in rows:
        local_day = (now.astimezone(timezone.utc) + timedelta(hours=int(tz_offset))).date().isoformat()
        text = await build_text(db, int(user_id), now)
        if text is not None:
            sent += await dm_push.enqueue(
                db, user_id=int(user_id), category=category, dedup_key=f"{category}:{local_day}", text=text,
                button={"kind": "cb", "data": "dn:plan", "label": "📋 Открыть план"},
            )
        seen.add((int(user_id), local_day))
    return sent


async def _morning(db, now: datetime) -> int:
    from services import dm_plan

    return await _daily_digest(
        db, now, category="digest", from_hour=rules.DIGEST_FROM_HOUR,
        to_hour=rules.DIGEST_TO_HOUR, build_text=dm_plan.morning_text,
    )


async def _evening(db, now: datetime) -> int:
    from services import dm_plan

    return await _daily_digest(
        db, now, category="digest_evening", from_hour=rules.EVENING_FROM_HOUR,
        to_hour=rules.EVENING_TO_HOUR, build_text=dm_plan.evening_text,
    )


async def _chests(db, now: datetime) -> int:
    if not await system_flags.is_enabled(db, "content_chests_v1") or not await _has_table(db, "chest_key_grants_v1"):
        return 0
    async with db.execute(
        f"SELECT g.id, g.user_id, g.source_kind FROM chest_key_grants_v1 g {_CONSENT.format(alias='g')} "
        "JOIN chest_key_accounts_v1 acc ON acc.user_id=g.user_id AND acc.account_epoch=g.account_epoch "
        "LEFT JOIN chest_key_allocations_v1 a ON a.grant_id=g.id "
        "LEFT JOIN chest_key_revocations_v1 v ON v.grant_id=g.id "
        "WHERE a.grant_id IS NULL AND v.grant_id IS NULL AND acc.balance > 0 "
        "AND g.created_at > (?::timestamp AT TIME ZONE 'UTC') AND " +
        _NEW.format(alias="g", key="'chest_key:' || g.id") + " ORDER BY g.created_at, g.id LIMIT ?",
        ("chests", now - rules.EVENT_TTL, BATCH),
    ) as c:
        rows = await c.fetchall()
    sent = 0
    for grant_id, user_id, source_kind in rows:
        key_name = KEY_TIER_NAMES[tier_for_source(source_kind)]
        sent += await dm_push.enqueue(
            db, user_id=int(user_id), category="chests", dedup_key=f"chest_key:{grant_id}",
            text="🎁 <b>Ключ от сундука ждёт тебя</b>\nОткрой «Сундуки», чтобы забрать награду.",
            button={"kind": "cb", "data": f"dn:chest:{grant_id}", "label": f"🎁 Открыть за 1 ключ · {key_name}"},
        )
    return sent


async def vip_daily_reminders(db, now: datetime | None = None) -> int:
    """Вечернее напоминание про VIP-поручение: идёт общей очередью (тихие часы, лимит, пауза, дайджест), и только согласившимся."""
    from services.vip import daily_reminder_candidates, record_daily_reminder_sent
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(timezone.utc).date().isoformat()
    queued = 0
    for user_id in await daily_reminder_candidates(db, now=now):
        if await dm_push.enqueue(
            db, user_id=user_id, category="vip_expiry", dedup_key=f"vip_daily:{today}",
            text="✦ <b>VIP-поручение ещё ждёт</b>\nЗаверши одну игру сегодня. Прогресс серии не сгорит, если пропустишь день.",
            button={"kind": "app", "section": "vip", "label": "⭐ К VIP"},
        ):
            await record_daily_reminder_sent(db, user_id=user_id, now=now)
            queued += 1
        await db.commit()
    return queued


COLLECTORS = (("digest", _morning), ("digest_evening", _evening), ("chests", _chests), ("pets", _pets), ("quests", _quests), ("pass", _pass),
              ("market", _market), ("season", _season), ("season_report", _season_report), ("events", _holiday_looks), ("vip_expiry", _vip))


async def collect(db, now: datetime | None = None) -> dict[str, int]:
    """Один проход всех сборщиков. Сбой одного не мешает остальным. Возвращает {категория: сколько событий поставлено}."""
    now = now or datetime.now(timezone.utc)
    result: dict[str, int] = {}
    for name, fn in COLLECTORS:
        try:
            result[name] = await fn(db, now)
            await db.commit()
        except Exception as exc:
            logger.warning(f"dm push collector {name} failed: {type(exc).__name__}: {exc}")
            result[name] = 0
            rollback = getattr(db, "rollback", None)
            if rollback:
                await rollback()
    return result
