"""«Проверка связи»: виджет спрашивает бота и меряет отклик; кнопка «Пример отказа» показывает, как выглядит отказ."""
from __future__ import annotations

import time

from services.widgets import Refused, Reply

SAMPLE = {"t": 1_762_862_400_000}


async def state(db, user_id: int, view: str | None = None) -> dict:
    return {"t": int(time.time() * 1000)}


async def act(db, user_id: int, verb: str, args: list[str], *, action_id: str = "") -> Reply:
    if verb == "x":
        raise Refused("Так выглядит отказ бота: текст приходит прямо в виджет.")
    raise Refused("Этот виджет устарел. Попроси новый.")
