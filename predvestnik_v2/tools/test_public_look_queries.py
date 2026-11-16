#!/usr/bin/env python3
"""Public looks keep their VIP rules while avoiding duplicate SQL (no database needed)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import appearance_public_v3 as looks  # noqa: E402
from services import leaderboards_v1 as boards  # noqa: E402


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def fetchone(self):
        return self.rows[0]

    async def fetchall(self):
        return self.rows


class Db:
    def __init__(self):
        self.vip_ids = {1}
        self.skins = {1: ("forest", "SSS"), 2: ("void", "D")}
        self.queries = []
        self.vip_error = False

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        if "FROM vip_subscriptions" in sql:
            if self.vip_error:
                raise RuntimeError("VIP lookup unavailable")
            return Cursor([(uid,) for uid in params if uid in self.vip_ids])
        if "to_regclass" in sql:
            return Cursor([(True,)])
        if "FROM skins_v3_equipped" in sql:
            return Cursor([(uid, *self.skins[uid]) for uid in params if uid in self.skins])
        raise AssertionError(f"Unexpected query: {sql}")

    def counts(self):
        return tuple(sum(token in sql for sql, _ in self.queries)
                     for token in ("FROM vip_subscriptions", "to_regclass", "FROM skins_v3_equipped"))


class PublicLookQueries(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Db()
        self.enterContext(patch.object(boards.public_profiles, "player_projection", AsyncMock(return_value={
            uid: {"display_name": f"Player {uid}", "profile_ref": f"ref{uid}"} for uid in (1, 2)
        })))
        self.enterContext(patch.object(boards.public_profiles, "resolve_references", AsyncMock(return_value={
            "ref1": 1, "ref2": 2, "missing": None
        })))
        self.enterContext(patch.object(boards.marks_service, "top_mark_batch", AsyncMock(return_value={})))
        self.enterContext(patch.object(boards.users_repo, "account_levels", AsyncMock(return_value={})))

    async def test_game_boards_share_one_vip_read(self):
        for active in ({1}, set()):
            for kind in ("wins", "decorated"):
                with self.subTest(active=active, kind=kind):
                    self.db.vip_ids = active
                    self.db.queries.clear()
                    if kind == "wins":
                        rows = await boards._win_rows(self.db, [
                            {"user_id": 1, "wins": 8}, {"user_id": 2, "wins": 3}
                        ], 1, 1)
                    else:
                        board = {"top": [{"player": {"profile_ref": ref}} for ref in ("ref1", "ref2", "missing")]}
                        await boards.decorate_game_board(self.db, board, 1)
                        rows = [row["player"] for row in board["top"]]
                        self.assertFalse(rows[-1]["is_vip"])
                        self.assertIsNone(rows[-1]["look"])
                    self.assertEqual(self.db.counts(), (1, int(bool(active)), int(bool(active))))
                    self.assertEqual(rows[0]["is_vip"], bool(active))
                    self.assertEqual(bool(rows[0]["look"]), bool(active))
                    self.assertIsNone(rows[1]["look"])

    async def test_explicit_empty_snapshot_does_no_sql(self):
        self.assertEqual(await looks.nick_styles(self.db, [1], vip_ids=set()), {})
        self.assertEqual(self.db.queries, [])

    async def test_snapshot_only_reads_requested_players(self):
        result = await looks.nick_styles(self.db, [1, 1, 2], vip_ids={1, 999})
        self.assertEqual(set(result), {1})
        self.assertEqual(result[1]["tier"], "SSS")
        self.assertNotIn("tokens", result[1])
        self.assertEqual(self.db.counts(), (0, 1, 1))
        self.assertEqual(self.db.queries[-1][1], (1,))

    async def test_vip_is_fresh_between_calls(self):
        self.assertEqual(set(await looks.nick_styles(self.db, [1, 2])), {1})
        self.db.vip_ids.clear()
        self.db.queries.clear()
        self.assertEqual(await looks.nick_styles(self.db, [1, 2]), {})
        self.assertEqual(self.db.counts(), (1, 0, 0))

    async def test_empty_input_does_no_sql(self):
        self.assertEqual(await looks.nick_styles(self.db, [], vip_ids={1}), {})
        board = {"top": []}
        self.assertIs(await boards.decorate_game_board(self.db, board), board)
        self.assertEqual(await boards._win_rows(self.db, [], 1, 1), [])
        self.assertEqual(self.db.queries, [])

    async def test_unknown_or_missing_skin_is_omitted(self):
        self.db.skins = {1: ("removed-skin", "D")}
        self.assertEqual(await looks.nick_styles(self.db, [1, 2], vip_ids={1, 2}), {})

    async def test_vip_failure_is_not_hidden(self):
        self.db.vip_error = True
        with self.assertRaisesRegex(RuntimeError, "VIP lookup unavailable"):
            await looks.nick_styles(self.db, [1])
        self.assertEqual(self.db.counts(), (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
