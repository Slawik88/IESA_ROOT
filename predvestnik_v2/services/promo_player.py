"""Экран «Промокоды» в Mini App: что игрок может забрать прямо сейчас и что он уже активировал.

Показывается только то, что игрок и так может активировать в Mini App: код включён, срок идёт, активации не кончились,
код не привязан к чатам (в Mini App чата нет), игрок его ещё не брал. Публичные коды админ отмечает «Показывать в Mini App»;
именной код (в списке игроков есть его ID) виден только своему игроку. Остальные коды остаются секретными, как раньше.
Забирают код тем же POST /promo-v2/redeem: все проверки и выдача — в services/promo_v2.redeem.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from infrastructure.repositories import promo_player as repo
from services.promo_v2 import _ids, _when, describe


def _rewards(raw: Any) -> list:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return raw if isinstance(raw, list) else []


def _offer(row: tuple, user_id: int, now: datetime) -> dict | None:
    code, start, end, max_act, used, users_raw, rewards_raw, shown = row
    users = _ids(users_raw)
    personal = user_id in users
    if users and not personal:
        return None                       # именной код другого игрока: LIKE только отсеял кандидатов
    if not (shown or personal):
        return None
    start, end = _when(start), _when(end)
    if (start and now < start) or (end and now > end):
        return None
    left = int(max_act or 0) - int(used or 0) if max_act else None
    if left is not None and left <= 0:
        return None
    rewards = _rewards(rewards_raw)
    if not rewards:
        return None
    return {"code": str(code), "rewards": [describe(r) for r in rewards], "until": end.isoformat() if end else None,
            "left": left, "personal": personal}


async def player_view(db: Any, user_id: int) -> dict:
    now = datetime.now(timezone.utc)
    offers = [o for o in (_offer(r, user_id, now) for r in await repo.offered_codes(db, user_id)) if o]
    history = [{"code": str(r[0]), "at": r[1].isoformat() if r[1] else None, "granted": [str(x) for x in _rewards(r[2])],
                "in_chat": r[3] is not None} for r in await repo.history(db, user_id)]
    return {"available": offers, "history": history}
