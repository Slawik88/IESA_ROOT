#!/usr/bin/env python3
"""Service-level checks for isolated companion choices and care idempotency."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import copy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services import companions_v3 as service  # noqa: E402


class Connection:
    @asynccontextmanager
    async def transaction(self):
        yield


class DB:
    connection = Connection()


class FakeRepo:
    def __init__(self):
        self.pets = [{
            "id": 11, "name": "Лис", "species_id": "fox", "rarity": "epic",
            "placement": "active", "fatigue": 19, "legacy_level": 8,
            "legacy_duplicates": 14, "copy_index": 1, "created_at": None,
        }]
        self.profile = None
        self.bonds = {}
        self.actions = {}
        self.meaningful_days = 0
        self.expeditions = []
        self.claim_ready = []

    async def lock_user(self, _db, _uid): return None
    async def list_owned_pets(self, _db, _uid): return copy.deepcopy(self.pets)
    async def get_owned_pet(self, _db, _uid, pet_id):
        return next((copy.deepcopy(pet) for pet in self.pets if pet["id"] == pet_id), None)
    async def get_profile(self, _db, _uid): return copy.deepcopy(self.profile)
    async def ensure_profile(self, _db, uid, default_pet_id):
        if self.profile is None:
            self.profile = {"user_id": uid, "active_pet_id": default_pet_id,
                            "selected_role_id": None, "unlocked_roles": []}
        return copy.deepcopy(self.profile)
    async def count_meaningful_days(self, _db, _uid): return self.meaningful_days
    async def save_profile_roles(self, _db, _uid, *, selected_role_id, unlocked_roles):
        self.profile["selected_role_id"] = selected_role_id
        self.profile["unlocked_roles"] = list(unlocked_roles)
    async def save_active_pet(self, _db, _uid, pet_id): self.profile["active_pet_id"] = pet_id
    async def list_bond_states(self, _db, _uid): return [copy.deepcopy(v) for v in self.bonds.values()]
    async def get_bond_state(self, _db, uid, pet_id):
        now = datetime(2026, 8, 22, tzinfo=timezone.utc)
        return self.bonds.setdefault(pet_id, {
            "user_id": uid, "pet_id": pet_id, "bond_points": 0, "care_bank": 1,
            "bank_updated_at": now, "server_now": now, "last_care_action": None,
        })
    async def save_care(self, _db, _uid, pet_id, **values): self.bonds[pet_id].update(values)
    async def get_cached_action(self, _db, uid, action_id): return copy.deepcopy(self.actions.get((uid, action_id)))
    async def save_action(self, _db, uid, action_id, _kind, request, response):
        self.actions[(uid, action_id)] = {"request": copy.deepcopy(request), "response": copy.deepcopy(response)}
    async def list_legacy_expeditions(self, _db, _uid): return []
    async def has_second_expedition_slot(self, _db, _uid, _version, _encounter): return False
    async def list_expeditions(self, _db, _uid): return copy.deepcopy(self.expeditions)
    async def reserved_mora_last_7_days(self, _db, _uid):
        return sum(item["fixed_mora"] for item in self.expeditions if item["status"] != "cancelled")
    async def count_open_expeditions(self, _db, _uid):
        return sum(item["status"] in ("active", "ready") for item in self.expeditions)
    async def pet_has_open_expedition(self, _db, _uid, pet_id):
        return any(item["pet_id"] == pet_id and item["status"] in ("active", "ready") for item in self.expeditions)
    async def create_expedition(self, _db, **values):
        item = {"id": len(self.expeditions) + 1, **values, "status": "active",
                "starts_at": datetime(2026, 8, 22, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 8, 22, 2, tzinfo=timezone.utc),
                "claimed_at": None, "remaining_sec": 7200}
        self.expeditions.append(item)
        return copy.deepcopy(item)
    async def mark_ready_and_claim(self, _db, _uid):
        rows = copy.deepcopy(self.claim_ready)
        self.claim_ready = []
        return rows


async def main():
    fake = FakeRepo()
    original = service.repo
    service.repo = fake
    try:
        db = DB()
        initial = await service.overview(db, 7)
        assert initial["active_pet_id"] == 11 and initial["pets"][0]["legacy"]["level"] == 8
        assert initial["pets"][0]["legacy"]["duplicates"] == 14
        assert initial["role_slots"] == 1 and initial["expeditions"]["start_enabled"]
        assert initial["expeditions"]["slots"] == 1

        first = await service.select_role(db, 7, "lantern")
        assert first["selected_role_id"] == "lantern"
        assert await service.selected_role(db, 7) == "lantern"
        try:
            await service.select_role(db, 7, "navigator")
        except service.CompanionConflict:
            pass
        else:
            raise AssertionError("Unimplemented role became selectable")
        try:
            await service.select_role(db, 7, "guardian")
        except service.CompanionConflict:
            pass
        else:
            raise AssertionError("Second role unlocked before meaningful day 5")
        fake.meaningful_days = 5
        second = await service.select_role(db, 7, "guardian")
        assert second["unlocked_roles"] == ["lantern", "guardian"]
        fake.meaningful_days = 10
        third = await service.select_role(db, 7, "rhythm_keeper")
        assert third["unlocked_roles"] == ["lantern", "guardian", "rhythm_keeper"]
        fake.meaningful_days = 15
        fourth = await service.select_role(db, 7, "echo")
        assert fourth["unlocked_roles"] == ["lantern", "guardian", "rhythm_keeper", "echo"]

        cared = await service.care(db, 7, 11, "play", "care-1")
        replay = await service.care(db, 7, 11, "play", "care-1")
        assert cared["bond"]["points"] == 1 and cared["economic_reward"] is None
        assert replay["idempotent_replay"] is True and fake.bonds[11]["bond_points"] == 1
        try:
            await service.care(db, 7, 11, "feed", "care-1")
        except service.CompanionConflict:
            pass
        else:
            raise AssertionError("Conflicting care action id was accepted")

        started = await service.start_expedition(db, 7, 11, 2, "exp-1")
        started_replay = await service.start_expedition(db, 7, 11, 2, "exp-1")
        assert started["projected_mora"] == 50 and started["settled"] is False
        assert started_replay["idempotent_replay"] is True and len(fake.expeditions) == 1
        try:
            await service.start_expedition(db, 7, 11, 6, "exp-2")
        except service.CompanionConflict:
            pass
        else:
            raise AssertionError("Second expedition slot opened before Chronicle gate")
        fake.claim_ready = [{
            "id": 1, "pet_id": 11, "duration_hours": 2, "route_id": "quick_feedback",
            "fixed_mora": 50, "discovery_id": "bell_fragment", "claimed_at": None,
        }]
        claimed = await service.claim_expeditions(db, 7, "claim-1")
        claimed_replay = await service.claim_expeditions(db, 7, "claim-1")
        assert claimed["projected_mora_total"] == 50 and claimed["settled"] is False
        assert claimed_replay["idempotent_replay"] is True
    finally:
        service.repo = original

    repository_source = (ROOT / "infrastructure/repositories/companions_v3.py").read_text()
    service_source = (ROOT / "services/companions_v3.py").read_text()
    assert "UPDATE pets" not in repository_source and "DELETE FROM pets" not in repository_source
    assert "active_expeditions e" in repository_source
    assert "add_balance" not in service_source and "spend_mora" not in service_source
    print("companions_v3_service: ownership+roles+care idempotency+legacy isolation  OK")


asyncio.run(main())
