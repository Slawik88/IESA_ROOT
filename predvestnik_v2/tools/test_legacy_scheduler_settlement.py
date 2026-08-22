#!/usr/bin/env python3
"""Boundary checks for retired passive faucets and legacy expedition settlement."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
scheduler = (ROOT / "services/scheduler.py").read_text(encoding="utf-8")
zoo_router = (ROOT / "FastAPI/routers/zoo.py").read_text(encoding="utf-8")
zoo_client = (ROOT / "FastAPI/static/app.03.js").read_text(encoding="utf-8")
bot_expeditions = (ROOT / "bot/handlers/expeditions.py").read_text(encoding="utf-8")
ai = (ROOT / "services/ai_assistant.py").read_text(encoding="utf-8")
bot_main = (ROOT / "bot/__main__.py").read_text(encoding="utf-8")

finish = scheduler[scheduler.index("async def _finish_expedition("):scheduler.index("async def expedition_background_task(")]
weekly = scheduler[scheduler.index("async def _run_weekly_monday_jobs("):scheduler.index("async def duel_and_auction_task(")]
anniversary = scheduler[scheduler.index("async def anniversary_task("):scheduler.index("async def shadow_merchant_task(")]

assert "UPDATE users SET user_balance" not in scheduler
assert "async with db.connection.transaction()" in finish
assert 'source="legacy_expedition_settlement"' in finish
assert 'idempotency_key=f"legacy-expedition:{settlement_ref}"' in finish
assert "DELETE FROM active_expeditions" in finish
assert "_incr_ach" not in finish and "_incr_quest" not in finish
assert "Ещё {hours}ч" not in finish
assert "e.ends_at" in scheduler

assert "return None" in weekly
assert "weekly_bank_grant" not in weekly
assert "return None" in anniversary
assert "anniversary_task(bot)" not in bot_main

assert '"new_starts_enabled": False' in zoo_router
start_route = zoo_router[zoo_router.index("async def start_expedition("):zoo_router.index("class MoveRequest")]
assert "raise HTTPException(" in start_route and "410" in start_route
assert "o.new_starts_enabled===false" in zoo_client
assert "return False, _build_expedition_list()" in bot_expeditions

tools = ai[ai.index("_TOOLS ="):ai.index("# ── Динамические темы")]
assert '"name": "propose_expedition"' not in tools
assert '"name": "propose_transfer"' not in tools

print("legacy scheduler settlement contract: OK")
