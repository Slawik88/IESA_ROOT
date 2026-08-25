#!/usr/bin/env python3
"""Regression contract for exact, recoverable cosmetic saved looks."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.cosmetics import apply_preset, list_presets, rename_preset, save_preset  # noqa: E402


TITLE_A = "cos_title_forest_wanderer"
TITLE_B = "cos_title_thicket_child"
FRAME_A = "cos_avatar_frame_oak"
BACKGROUND_A = "cos_profile_bg_forest"


class Cursor:
    def __init__(self, row=None, rows=()):
        self.row = row
        self.rows = list(rows)

    async def fetchone(self):
        return self.row

    async def fetchall(self):
        return list(self.rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def __await__(self):
        async def resolved():
            return self
        return resolved().__await__()


class Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class Connection:
    def transaction(self):
        return Transaction()


class CosmeticDB:
    """Small in-memory PGAdapter model; records locking and exact SQL effects."""
    def __init__(self):
        self.connection = Connection()
        self.owned = {TITLE_A, TITLE_B, FRAME_A, BACKGROUND_A}
        self.loadout = {"title": TITLE_A, "profile_bg": BACKGROUND_A, "welcome": "default"}
        self.presets = {}
        self.next_preset_id = 1
        self.executed = []

    def add_preset(self, name, loadout):
        preset_id = self.next_preset_id
        self.next_preset_id += 1
        self.presets[preset_id] = (name, json.dumps(loadout), "2026-08-23")
        return preset_id

    def execute(self, sql, args=()):
        normalized = " ".join(sql.split())
        args = tuple(args)
        self.executed.append((normalized, args))
        if "SELECT 1 FROM users" in normalized:
            return Cursor((1,))
        if "SELECT slot, cosmetic_id FROM user_cosmetic_loadout" in normalized:
            return Cursor(rows=list(self.loadout.items()))
        if "SELECT cosmetic_id FROM user_cosmetics" in normalized:
            return Cursor(rows=[(cosmetic_id,) for cosmetic_id in sorted(self.owned)])
        if "SELECT id, name, loadout, created_at FROM cosmetic_presets" in normalized:
            return Cursor(rows=[(preset_id, *values) for preset_id, values in sorted(self.presets.items())])
        if "SELECT name, loadout FROM cosmetic_presets" in normalized:
            preset = self.presets.get(args[0])
            return Cursor(preset[:2] if preset else None)
        if "SELECT COUNT(*) FROM cosmetic_presets" in normalized:
            return Cursor((len(self.presets),))
        if normalized.startswith("DELETE FROM user_cosmetic_loadout"):
            user_id, *slots = args
            del user_id
            for slot in slots:
                self.loadout.pop(slot, None)
            return Cursor()
        if normalized.startswith("INSERT INTO user_cosmetic_loadout"):
            _user_id, slot, cosmetic_id, *_ = args
            self.loadout[slot] = cosmetic_id
            return Cursor()
        if normalized.startswith("INSERT INTO cosmetic_presets"):
            user_id, name, loadout_json = args
            del user_id
            preset_id = self.next_preset_id
            self.next_preset_id += 1
            self.presets[preset_id] = (name, loadout_json, "2026-08-23")
            return Cursor((preset_id,))
        if normalized.startswith("UPDATE cosmetic_presets SET name"):
            name, preset_id, _user_id = args
            preset = self.presets.get(preset_id)
            if not preset:
                return Cursor(None)
            self.presets[preset_id] = (name, preset[1], preset[2])
            return Cursor((name, preset[1]))
        if normalized.startswith("INSERT INTO users") or normalized.startswith("DELETE FROM cosmetic_presets"):
            if normalized.startswith("DELETE FROM cosmetic_presets"):
                self.presets.pop(args[0], None)
            return Cursor()
        raise AssertionError(f"Unexpected SQL: {normalized}")


def assert_writers_lock(db):
    locks = [sql for sql, _ in db.executed if "SELECT 1 FROM users" in sql and "FOR UPDATE" in sql]
    assert locks, "cosmetic writer must lock the durable user row"


async def main():
    db = CosmeticDB()

    # Rename is a user-scoped, normalized metadata change: it never writes a
    # loadout and therefore cannot accidentally equip or erase cosmetics.
    rename_id = db.add_preset("Старое имя", {"title": TITLE_A})
    ok, message, renamed = await rename_preset(db, 77, rename_id, "  Новое имя  ")
    assert ok and "Новое имя" in message
    assert renamed == {"id": rename_id, "name": "Новое имя", "loadout": {"title": TITLE_A}, "invalid": False}
    assert db.presets[rename_id][1] == json.dumps({"title": TITLE_A})
    ok, message, renamed = await rename_preset(db, 77, 999, "Не существует")
    assert not ok and renamed is None and "не найден" in message
    assert any("WHERE id = ? AND user_id = ?" in sql for sql, _ in db.executed)
    assert_writers_lock(db)

    # A partial saved look is an exact snapshot: absent wearable slots clear,
    # while welcome remains its independent preference.
    one_slot = db.add_preset("Только титул", {"title": TITLE_B})
    ok, message = await apply_preset(db, 77, one_slot)
    assert ok, message
    assert db.loadout == {"title": TITLE_B, "welcome": "default"}
    assert_writers_lock(db)

    empty = db.add_preset("Пустой", {})
    ok, message = await apply_preset(db, 77, empty)
    assert ok, message
    assert db.loadout == {"welcome": "default"}

    # Older presets may contain welcome, but it is not part of a wearable look.
    db.loadout.update({"title": TITLE_A, "welcome": "flash"})
    legacy = db.add_preset("Старый", {"welcome": "default", "title": TITLE_B})
    ok, message = await apply_preset(db, 77, legacy)
    assert ok, message
    assert db.loadout == {"title": TITLE_B, "welcome": "flash"}

    # Structurally corrupt, mismatched and no-longer-owned snapshots never make
    # a list request fail or partially alter the current appearance.
    invalid_ids = [
        db.add_preset("JSON", "not-a-dict"),
        db.add_preset("Слишком глубокий JSON", []),
        db.add_preset("Лишний слот", {"not_a_slot": TITLE_A}),
        db.add_preset("Не тот слот", {"title": FRAME_A}),
        db.add_preset("Неизвестный", {"title": "cos_title_removed"}),
        db.add_preset("Не свой", {"title": TITLE_A, "profile_bg": BACKGROUND_A}),
    ]
    db.presets[invalid_ids[0]] = ("JSON", "[", "2026-08-23")
    db.presets[invalid_ids[1]] = (
        "Слишком глубокий JSON", "[" * 10_000 + "]" * 10_000, "2026-08-23"
    )
    db.owned.remove(BACKGROUND_A)
    before = dict(db.loadout)
    listed = await list_presets(db, 77)
    listed_by_id = {item["id"]: item for item in listed}
    assert all(listed_by_id[preset_id]["invalid"] for preset_id in invalid_ids[:-1])
    assert listed_by_id[invalid_ids[-1]]["invalid"] is False
    for preset_id in invalid_ids:
        ok, message = await apply_preset(db, 77, preset_id)
        assert not ok and "не изменён" in message
        assert db.loadout == before

    # Saving captures only valid, owned wearable slots and returns the INSERTed
    # identifier rather than racing a later SELECT ... ORDER BY id DESC.
    save_db = CosmeticDB()
    save_db.loadout = {"title": TITLE_A, "avatar_frame": FRAME_A, "welcome": "flash"}
    ok, message, saved = await save_preset(save_db, 77, "Проверка")
    assert ok, message
    assert saved and saved["id"] in save_db.presets
    assert saved["loadout"] == {"title": TITLE_A, "avatar_frame": FRAME_A}
    assert any("RETURNING id" in sql for sql, _ in save_db.executed)

    # Every save is serialized before its limit check, so a real PostgreSQL
    # second request sees the first committed row rather than exceeding the cap.
    while len(save_db.presets) < 5:
        save_db.add_preset("Заполнен", {})
    ok, message, saved = await save_preset(save_db, 77, "Шестой")
    assert not ok and saved is None and "Максимум" in message
    assert len(save_db.presets) == 5
    assert_writers_lock(save_db)
    print("OK: cosmetic presets are exact, validated, recoverable and serialized")


if __name__ == "__main__":
    asyncio.run(main())
