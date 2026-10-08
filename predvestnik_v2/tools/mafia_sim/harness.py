"""Drive the production Dispatcher (real routers + middlewares) with virtual players."""
from __future__ import annotations

import importlib
import itertools
import pkgutil
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from tools.mafia_sim.world import BOT_ID, FakeSession, StoredMessage, World

DEV_DB = "predvestnik_preprod"
CHAT_BASE = -1_009_000_000_000  # simulator chats are CHAT_BASE-1, CHAT_BASE-2, …


def assert_dev_dsn(dsn: str) -> None:
    """Refuse anything but the throw-away loopback database."""
    parsed = urlparse(dsn)
    ok = parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.path.lstrip("/") == DEV_DB
    if not ok:
        raise SystemExit(f"simulator runs only on a loopback database named {DEV_DB}")


@dataclass(frozen=True)
class SimUser:
    id: int
    name: str

    @property
    def username(self) -> str:
        return f"sim{self.id}"

    def json(self) -> dict:
        return {"id": self.id, "is_bot": False, "first_name": self.name, "username": self.username}


@dataclass
class Click:
    """What the player saw after pressing a button."""

    text: str
    alert: bool
    url: str | None
    answered: bool


class Harness:
    def __init__(self) -> None:
        self.world = World()
        self.bot = None
        self.dp = None
        self._ids = itertools.count(1)
        self._users = itertools.count(990_100_001)
        self._chats = itertools.count(1)
        self.chats: list[int] = []

    # ── lifecycle ───────────────────────────────────────────────────────────
    async def open(self) -> "Harness":
        from aiogram import Bot, Dispatcher
        from bot.handlers import main_router
        from bot.middlewares.config_mw import config_middleware
        from bot.middlewares.db import db_middleware
        from bot.middlewares.global_sanctions_mw import global_sanctions_middleware
        from bot.middlewares.preprod_gate_mw import preprod_gate_middleware
        from bot.middlewares.purge_gate_mw import purge_gate_middleware
        from infrastructure.database import create_pool

        await create_pool()
        await self._bootstrap_schema()
        await self._purge([CHAT_BASE - n for n in range(1, 2001)])  # leftovers of an aborted earlier run
        self.bot = Bot(token=f"{BOT_ID}:SIM-TOKEN", session=FakeSession(self.world))
        self.dp = Dispatcher()
        for middleware in (config_middleware, preprod_gate_middleware, db_middleware,
                           global_sanctions_middleware, purge_gate_middleware):
            self.dp.update.middleware(middleware)
        self.dp.include_router(main_router)
        return self

    async def _bootstrap_schema(self) -> None:
        import infrastructure.repositories as repos
        from bot.core.database import init_db
        from infrastructure.database import get_pool
        from infrastructure.pg_adapter import PGAdapter

        await init_db()
        fns = []
        for info in pkgutil.iter_modules(repos.__path__):
            module = importlib.import_module(f"infrastructure.repositories.{info.name}")
            fn = getattr(module, "ensure_tables", None) or getattr(module, "ensure_table", None)
            if fn:
                fns.append(fn)
        for _ in range(3):  # tables reference each other; a second pass resolves ordering
            fns = [fn for fn in fns if not await self._try(fn, get_pool(), PGAdapter)]
        async with get_pool().acquire() as conn:
            await conn.execute(
                "UPDATE predvestnik.system_flags SET enabled=1 "
                "WHERE key IN ('game_mafia_v1','game_rhythm_v2','game_minesweeper_v2')")

    @staticmethod
    async def _try(fn, pool, adapter) -> bool:
        try:
            async with pool.acquire() as conn:
                await fn(adapter(conn))
            return True
        except Exception:  # noqa: BLE001 - retried on the next pass
            return False

    async def close(self) -> None:
        from infrastructure.database import get_pool
        await self.cleanup()
        await get_pool().close()

    async def cleanup(self) -> None:
        """Remove every match the simulator created (children first: FKs are RESTRICT)."""
        await self._purge(self.chats)

    @staticmethod
    async def _purge(chats: list[int]) -> None:
        from infrastructure.database import get_pool
        if not chats:
            return
        async with get_pool().acquire() as conn:
            ids = "SELECT id FROM predvestnik.mafia_v1_matches WHERE chat_id = ANY($1::bigint[])"
            for table in ("mafia_v1_dm_prompts", "mafia_v1_actions", "mafia_v1_audit_events", "mafia_v1_players"):
                await conn.execute(f"DELETE FROM predvestnik.{table} WHERE match_id IN ({ids})", chats)
            await conn.execute("DELETE FROM predvestnik.mafia_v1_matches WHERE chat_id = ANY($1::bigint[])", chats)

    # ── world building ──────────────────────────────────────────────────────
    def user(self, name: str, *, dm: bool = True) -> SimUser:
        user = SimUser(next(self._users), name)
        if dm:
            self.world.dm_open.add(user.id)
        return user

    def new_chat(self, members: list[SimUser], *, bot_can_delete: bool = True, admins: list[SimUser] = ()) -> int:
        chat_id = CHAT_BASE - next(self._chats)
        self.chats.append(chat_id)
        self.world.set_member(chat_id, BOT_ID, "administrator", can_delete_messages=bot_can_delete, can_manage_chat=True)
        for user in members:
            self.world.set_member(chat_id, user.id, "member")
        for user in admins:
            self.world.set_member(chat_id, user.id, "administrator", can_delete_messages=True, can_manage_chat=True)
        return chat_id

    # ── input ───────────────────────────────────────────────────────────────
    def _chat_json(self, chat_id: int, user: SimUser) -> dict:
        if chat_id > 0:
            return {"id": chat_id, "type": "private", "first_name": user.name}
        return {"id": chat_id, "type": "supergroup", "title": "Sim"}

    async def _feed(self, payload: dict) -> None:
        from aiogram.types import Update
        update = Update.model_validate({"update_id": next(self._ids), **payload}, context={"bot": self.bot})
        await self.dp.feed_update(self.bot, update)

    async def say(self, user: SimUser, chat_id: int, text: str, *, topic: int | None = None,
                  forum: bool = True, anonymous: bool = False) -> int:
        """A player writes ``text``.  ``topic`` set + ``forum`` False models a plain reply thread;
        ``anonymous`` is an admin posting «as the group» (Telegram shows GroupAnonymousBot)."""
        message_id = self.world.next_id = self.world.next_id + 1
        message = {"message_id": message_id, "date": int(time.time()), "chat": self._chat_json(chat_id, user),
                   "from": user.json(), "text": text}
        if anonymous:
            message["from"] = {"id": 1087968824, "is_bot": True, "first_name": "Group", "username": "GroupAnonymousBot"}
            message["sender_chat"] = self._chat_json(chat_id, user)
        if topic:
            message["message_thread_id"] = topic
            if forum:
                message["is_topic_message"] = True
        self.world.messages[(chat_id, message_id)] = StoredMessage(chat_id, message_id, text, None, html=text)
        self.world.set_member(chat_id, user.id, self.world.statuses.get((chat_id, user.id), {}).get("status", "member"))
        await self._feed({"message": message})
        return message_id

    def is_deleted(self, chat_id: int, message_id: int) -> bool:
        return self.world.messages[(chat_id, message_id)].deleted

    async def click(self, user: SimUser, chat_id: int, message: StoredMessage | None, contains: str = "",
                    *, data_prefix: str = "", index: int = 0) -> Click:
        """Press a button whose label contains ``contains`` (or whose data starts with ``data_prefix``).

        ``index`` picks among several matches (e.g. a random vote button)."""
        assert message is not None, "no message to click on"
        buttons = [b for b in message.buttons()
                   if contains in b.get("text", "") and b.get("callback_data", "").startswith(data_prefix)]
        if not buttons:
            labels = [b.get("text") for b in message.buttons()]
            raise AssertionError(f"no button {contains!r}/{data_prefix!r} on message; buttons: {labels}")
        buttons = buttons[index:index + 1] if index < len(buttons) else buttons[:1]
        before = len(self.world.answers)
        msg_json = self.world._message_json(message)
        msg_json["chat"] = self._chat_json(chat_id, user)
        await self._feed({"callback_query": {"id": str(next(self._ids)), "from": user.json(), "chat_instance": "sim",
                                             "message": msg_json, "data": buttons[0]["callback_data"]}})
        got = self.world.answers[before:]
        last = got[-1] if got else {"text": "", "alert": False, "url": None}
        return Click(last["text"], last["alert"], last.get("url"), bool(got))

    def dm(self, user: SimUser) -> list[StoredMessage]:
        return self.world.live(user.id)

    # ── time & scheduler ────────────────────────────────────────────────────
    async def tick(self) -> None:
        from services.scheduler import mafia_tick
        await mafia_tick(self.bot)

    async def sql(self, query: str, *args):
        from infrastructure.database import get_pool
        async with get_pool().acquire() as conn:
            return await conn.fetch(query, *args)

    async def match_row(self, chat_id: int):
        rows = await self.sql("SELECT * FROM predvestnik.mafia_v1_matches WHERE chat_id=$1 ORDER BY id DESC LIMIT 1", chat_id)
        return dict(rows[0]) if rows else None

    async def expire(self, chat_id: int) -> None:
        """Pretend the current phase timer ran out."""
        await self.sql(
            "UPDATE predvestnik.mafia_v1_matches SET phase_deadline=CLOCK_TIMESTAMP()-INTERVAL '1 second' "
            "WHERE chat_id=$1 AND phase_deadline IS NOT NULL", chat_id)
