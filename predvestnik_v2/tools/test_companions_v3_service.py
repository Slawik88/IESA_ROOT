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


async def main():
    fake = FakeRepo()
    original = service.repo
    service.repo = fake
    try:
        db = DB()
        initial = await service.overview(db, 7)
        assert initial["active_pet_id"] == 11 and initial["pets"][0]["legacy"]["level"] == 8
        assert initial["pets"][0]["legacy"]["duplicates"] == 14
        assert initial["role_slots"] == 1 and not initial["expeditions"]["start_enabled"]

        first = await service.select_role(db, 7, "navigator")
        assert first["selected_role_id"] == "navigator"
        try:
            await service.select_role(db, 7, "guardian")
        except service.CompanionConflict:
            pass
        else:
            raise AssertionError("Second role unlocked before meaningful day 5")
        fake.meaningful_days = 5
        second = await service.select_role(db, 7, "guardian")
        assert second["unlocked_roles"] == ["navigator", "guardian"]

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
    finally:
        service.repo = original

    repository_source = (ROOT / "infrastructure/repositories/companions_v3.py").read_text()
    service_source = (ROOT / "services/companions_v3.py").read_text()
    assert "UPDATE pets" not in repository_source and "DELETE FROM pets" not in repository_source
    assert "active_expeditions e" in repository_source
    assert "add_balance" not in service_source and "spend_mora" not in service_source
    print("companions_v3_service: ownership+roles+care idempotency+legacy isolation  OK")


asyncio.run(main())
