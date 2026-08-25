"""Contract for the preserved, read-only achievement gallery."""

import asyncio
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.registry import ACHIEVEMENTS
from services.achievements import backfill_metric, increment_metric



async def _check_writers() -> None:
    assert await increment_metric(None, 1, "cosmetics_bought") == []
    assert await backfill_metric(None, 1, "gates_battles_won", 999) == []


def main() -> None:
    assert ACHIEVEMENTS, "saved achievement metadata must remain readable"
    asyncio.run(_check_writers())

    router = (ROOT / "FastAPI" / "routers" / "achievements.py").read_text(encoding="utf-8")
    assert '"retired": True' in router
    assert '"next_reward": None' in router
    assert "backfill_metric" not in router
    assert "grant_rewards" not in router

    print("OK: achievement history is visible and cannot mint old rewards")


if __name__ == "__main__":
    main()
