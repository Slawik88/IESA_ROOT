"""Message leaderboards for the Mini App: the compact home top and the full «бот топ» screen.

Read-only. Player names come from the public-profile projection, so the web view exposes the same
fields as other global boards. Local boards require current membership of the requested chat.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from infrastructure.repositories import public_profiles_v1 as public_profiles
from services import appearance_public_v3
from infrastructure.repositories import stats as stats_repo
from infrastructure.repositories.streak import get_chat_timezone
from services.membership import bot_tg_id

TOP_LIMIT = 5
PAGE_SIZE = 10
PERIODS = ("day", "week", "month", "all_time")
SCOPES = ("global", "chats", "local")


class NotAMember(PermissionError):
    pass


def period_bounds(now: datetime, period: str) -> tuple[str, str] | None:
    """Calendar bounds in the caller's clock; None means all time (same rules as the bot)."""
    if period == "all_time":
        return None
    day = now.date()
    if period == "day":
        return day.isoformat(), day.isoformat()
    if period == "week":
        return (day - timedelta(days=day.weekday())).isoformat(), day.isoformat()
    if period == "month":
        return day.replace(day=1).isoformat(), day.isoformat()
    raise ValueError("unsupported top period")


def week_bounds(now: datetime) -> tuple[str, str]:
    return period_bounds(now.astimezone(timezone.utc), "week")  # type: ignore[return-value]


def previous_bounds(bounds: tuple[str, str] | None) -> tuple[str, str] | None:
    if bounds is None:
        return None
    start, end = datetime.fromisoformat(bounds[0]).date(), datetime.fromisoformat(bounds[1]).date()
    prev_end = start - timedelta(days=1)
    return (prev_end - (end - start)).isoformat(), prev_end.isoformat()


async def _player_rows(db, rows: list[dict], user_id: int, first_place: int) -> list[dict]:
    ids = [int(r["user_tg_id"]) for r in rows]
    players = await public_profiles.player_projection(db, user_ids=ids)
    looks = await appearance_public_v3.nick_styles(db, ids)   # VIP owners only
    return [
        {
            "place": first_place + index,
            "name": players[int(row["user_tg_id"])]["display_name"],
            "ref": players[int(row["user_tg_id"])]["profile_ref"],
            "look": looks.get(int(row["user_tg_id"])),
            "count": int(row["msg_count"]),
            "is_vip": bool(row.get("is_vip")),
            "is_me": int(row["user_tg_id"]) == int(user_id),
        }
        for index, row in enumerate(rows)
    ]


async def message_top(db, *, user_id: int, period: str, now: datetime | None = None) -> dict:
    """Compact home board: top 5 players across all chats plus the caller's exact place."""
    if period not in ("week", "all_time"):
        raise ValueError("unsupported top period")
    bounds = period_bounds((now or datetime.now(timezone.utc)).astimezone(timezone.utc), period)
    rows = (await stats_repo.get_top_messages_global_for_dates(db, bounds[0], bounds[1], limit=TOP_LIMIT)
            if bounds else await stats_repo.get_top_messages_global_all_time(db, limit=TOP_LIMIT))
    position = await stats_repo.get_message_top_position(
        db, scope="global", entity_id=int(user_id),
        date_start=bounds[0] if bounds else None, date_end=bounds[1] if bounds else None,
    )
    return {"period": period, "top": await _player_rows(db, rows, user_id, 1),
            "personal": _personal(position)}


def _personal(position: dict | None) -> dict | None:
    if not position:
        return None
    return {"place": int(position["place"]), "count": int(position["msg_count"]), "total": int(position["total_count"])}


async def _my_chats(db, user_id: int) -> list[dict]:
    async with db.execute(
        "SELECT s.chat_tg_id AS chat_id, COALESCE(NULLIF(c.chat_title,''),'Чат') AS title "
        "FROM user_chat_stats s LEFT JOIN chat_settings c ON c.chat_id=s.chat_tg_id "
        "WHERE s.user_tg_id=? AND s.is_left=FALSE ORDER BY s.user_messages_count_all_time DESC LIMIT 20",
        (int(user_id),),
    ) as cursor:
        return [{"chat_id": int(r["chat_id"]), "title": str(r["title"])} for r in await cursor.fetchall()]


async def message_top_page(
    db, *, user_id: int, scope: str, period: str, chat_id: int | None = None, page: int = 0,
    now: datetime | None = None,
) -> dict:
    """Full board with scope, period and pages: the web twin of «бот топ»."""
    if scope not in SCOPES or period not in PERIODS:
        raise ValueError("unsupported top scope or period")
    chats = await _my_chats(db, user_id)
    if scope == "local":
        if chat_id is None or int(chat_id) not in {c["chat_id"] for c in chats}:
            raise NotAMember("local board is available to members of the chat only")
    offset_hours = await get_chat_timezone(db, int(chat_id)) if scope == "local" else 0
    bounds = period_bounds((now or datetime.now(timezone.utc)) + timedelta(hours=offset_hours), period)
    if scope == "local":
        rows = (await stats_repo.get_top_messages(db, int(chat_id), "all_time") if bounds is None
                else await stats_repo.get_top_messages_for_dates(db, int(chat_id), *bounds))
    elif scope == "global":
        rows = (await stats_repo.get_top_messages_global_all_time(db) if bounds is None
                else await stats_repo.get_top_messages_global_for_dates(db, *bounds))
    else:
        rows = (await stats_repo.get_top_chats_all_time(db) if bounds is None
                else await stats_repo.get_top_chats_for_dates(db, *bounds))
    own = bot_tg_id()
    if scope != "chats" and own is not None:
        rows = [row for row in rows if int(row["user_tg_id"]) != int(own)]
    pages = max(1, -(-len(rows) // PAGE_SIZE))
    page = max(0, min(int(page), pages - 1))
    visible = rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    offset = page * PAGE_SIZE + 1
    if scope == "chats":
        items = [{"place": offset + i, "name": str(r.get("chat_title") or "Чат"), "count": int(r["msg_count"]),
                  "users": int(r["active_users"]), "is_vip": False, "is_me": False} for i, r in enumerate(visible)]
        personal = None
    else:
        items = await _player_rows(db, visible, user_id, offset)
        kwargs = {"scope": scope, "entity_id": int(user_id), "chat_id": int(chat_id) if scope == "local" else None}
        position = await stats_repo.get_message_top_position(
            db, date_start=bounds[0] if bounds else None, date_end=bounds[1] if bounds else None,
            excluded_user_id=own, **kwargs)
        personal = _personal(position)
        previous = previous_bounds(bounds)
        if personal and previous:
            before = await stats_repo.get_message_top_position(
                db, date_start=previous[0], date_end=previous[1], excluded_user_id=own, **kwargs)
            personal["delta"] = personal["count"] - (int(before["msg_count"]) if before else 0)
    return {"scope": scope, "period": period, "chat_id": chat_id, "page": page, "pages": pages,
            "items": items, "personal": personal, "chats": chats}
