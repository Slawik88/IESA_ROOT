#!/usr/bin/env python3
"""Regression boundary: retired CP wagers cannot re-enter the live economy."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
service = (ROOT / "services/duel.py").read_text(encoding="utf-8")
router = (ROOT / "FastAPI/routers/duels.py").read_text(encoding="utf-8")
client = (ROOT / "FastAPI/static/app.04.js").read_text(encoding="utf-8")

create = service[service.index("async def create_challenge("):service.index("async def accept_duel(")]
decline = service[service.index("async def decline_duel("):]
visible_duel_ui = client[client.index("function loadDuels()"):client.index("function declineDuel(")]

assert "return False, LEGACY_DUEL_CLOSED_MESSAGE" in create
for forbidden in ("db.execute", "add_balance", "create_duel", "_add_reserve"):
    assert forbidden not in create
assert "FOR UPDATE" in decline
assert "GREATEST(0, reserved_mora - ?)" in decline
assert 'set_duel_status(db, duel_id, "declined")' in decline
assert "duel_win" not in service and "duel_loss" not in service

assert '@router.post("/challenge", status_code=410)' in router
assert '@router.post("/accept", status_code=410)' in router
assert "create_challenge" not in router and "accept_duel" not in router
assert "challenger_id = ? OR challenged_id = ?" in router

assert "Вызвать игрока на дуэль" not in visible_duel_ui
assert visible_duel_ui.count("Освободить ставку") == 2
assert "Новые бои проходят во вкладке «Игра»" in visible_duel_ui
for retired_client_entry in ("function acceptDuel(", "function openDuelChallenge(",
                             "function submitDuelChallenge(", "/duels/challenge"):
    assert retired_client_entry not in client

print("legacy duel retirement contract: OK")
