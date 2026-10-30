"""Public table metadata and animation facts must not reveal another player's secrets."""
import asyncio
import copy
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import mafia_online as rules
from services import mafia_online_views as views
from services import mafia_online_players as presentations


def room(phase):
    roles = ["mafia", "don", "doctor", "detective", "citizen", "citizen"]
    return {
        "id": 7, "phase": phase, "host": 1, "seats": 8, "tempo": "normal",
        "round": 2, "version": 10, "phase_number": 3, "created": 100,
        "phase_started": 150, "deadline": 300, "visibility": "public",
        "vote_mode": "secret", "roles_auto": True, "roles": [], "invite": "test",
        "actions": {}, "paused": "night", "remaining": 25, "finished_at": 180,
        "players": [
            {"id": i + 1, "name": f"Игрок {i + 1}", "seat": i + 1,
             "alive": True, "seen": 190, "role": role if phase != "lobby" else None,
             "checks": [{"round": 1, "target": 1, "name": "Игрок 1", "mafia": True}]
             if role == "detective" else []}
            for i, role in enumerate(roles)
        ],
    }


async def snapshot(state, uid, channel="table"):
    with patch.object(views.repo, "now", AsyncMock(return_value=200)), \
         patch.object(views.repo, "messages", AsyncMock(return_value=[])), \
         patch.object(views.repo, "channel_latest", AsyncMock(return_value={})), \
         patch.object(views, "player_presentations", AsyncMock(return_value={})):
        return await views.snapshot(None, state, uid, channel)


async def redactions():
    count = 0
    for phase in ("lobby", "night", "discussion", "voting", "paused", "finished", "cancelled"):
        for dead in (False, True):
            state = room(phase)
            for viewer in state["players"]:
                viewer["alive"] = not dead
                for channel in rules.channels(state, viewer):
                    data = await snapshot(state, viewer["id"], channel)
                    for player in data["players"]:
                        assert {"look", "avatar", "avatar_state", "mark", "level", "is_bot"} <= player.keys()
                        assert player["look"] is player["avatar"] is None
                        assert player["avatar_state"] == "vip_only"
                        assert not player["is_bot"]
                        assert ("role" in player) == (phase in rules.TERMINAL)
                    assert data["phase_state"]["my_turn"] == data["me"]["can_act"]
                    assert data["phase_state"]["phase"] == phase
                    for event in data["events"]:
                        assert set(event) <= {"id", "kind", "phase", "phase_number", "player_id", "role", "target", "mafia", "winner", "submitted"}
                        if event["kind"] in ("role", "check"):
                            assert event["player_id"] == viewer["id"]
                    # Swap two unknown roles: the new public fields/events must stay identical.
                    other = copy.deepcopy(state)
                    unknown = [p for p in other["players"] if p["id"] != viewer["id"] and p["role"] not in ("mafia", "don")]
                    if phase not in rules.TERMINAL and len(unknown) >= 2:
                        unknown[0]["role"], unknown[1]["role"] = unknown[1]["role"], unknown[0]["role"]
                        swapped = await snapshot(other, viewer["id"], channel)
                        for key in ("players", "events", "phase_state"):
                            assert data[key] == swapped[key], (phase, viewer["id"], key)
                    count += 1
                viewer["alive"] = True
    print(f"PASS {count} authorized role/phase/channel/dead-viewer projections, hidden-role swaps and animation facts")


async def vip_decorations():
    @asynccontextmanager
    async def transaction():
        yield

    db = SimpleNamespace(connection=SimpleNamespace(fetchval=AsyncMock(return_value=True), transaction=transaction))
    people = [{"id": 1, "role": "doctor"}, {"id": 2, "role": "mafia", "is_bot": True}]
    avatar = presentations.avatar_photos.AvatarView("/profile/avatar/test", "ready")
    with patch.object(presentations, "is_vip_active_batch", AsyncMock(return_value={1})) as vip, \
         patch.object(presentations.appearance_public_v3, "nick_styles", AsyncMock(return_value={1: {"id": "void"}, 2: {"id": "hidden"}})), \
         patch.object(presentations.profiles, "ensure_references", AsyncMock(return_value={1: "test"})) as refs, \
         patch.object(presentations.avatar_photos, "views", AsyncMock(return_value={1: avatar, 2: avatar})) as photos, \
         patch.object(presentations.marks_v1, "top_mark_batch", AsyncMock(return_value={1: {"id": "staff"}})), \
         patch.object(presentations.users, "account_levels", AsyncMock(return_value={1: 4, 2: 3})):
        result = await presentations.player_presentations(db, people)
        assert result[1]["look"] == {"id": "void"} and result[1]["avatar"] == avatar.avatar
        assert result[1]["mark"] == {"id": "staff"} and result[1]["level"] == 4
        assert result[2]["look"] is result[2]["avatar"] is None
        assert result[2]["avatar_state"] == "vip_only" and result[2]["is_bot"]
        refs.assert_awaited_once_with(db, {1})
        photos.assert_awaited_once_with(db, {1: "test"})
        vip.return_value = set()
        refs.return_value = {}
        expired = await presentations.player_presentations(db, people)
        assert all(p["look"] is p["avatar"] is None for p in expired.values()), "VIP expiry applies even to the viewer's own table appearance"
    print("PASS batched public cosmetics: VIP-only photos/looks, expired VIP, public mark/level and role-independent bot identity")


async def main():
    await redactions()
    await vip_decorations()


if __name__ == "__main__":
    asyncio.run(main())
