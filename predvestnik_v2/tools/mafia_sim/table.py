"""A virtual Mafia table: lobby → game, played only through buttons and DMs like real people."""
from __future__ import annotations

import re
from contextlib import contextmanager
from unittest import mock

from tools.mafia_sim.harness import Click, Harness, SimUser
from tools.mafia_sim.world import StoredMessage


class Table:
    def __init__(self, h: Harness, users: list[SimUser], chat: int, topic: int | None = None) -> None:
        self.h, self.users, self.chat, self.topic = h, users, chat, topic

    @classmethod
    async def create(cls, h: Harness, size: int = 4, *, command: str = "бот мафия", topic: int | None = None,
                     names: list[str] | None = None, forum: bool = True) -> "Table":
        names = names or [f"Игрок{i}" for i in range(1, size + 1)]
        users = [h.user(name) for name in names[:size]]
        chat = h.new_chat(users)
        table = cls(h, users, chat, topic)
        await h.say(users[0], chat, command, topic=topic, forum=forum)
        return table

    def add_bystander(self, name: str, *, dm: bool = True) -> SimUser:
        """Somebody in the chat who does not play (the other 33 members of a 40-person chat)."""
        user = self.h.user(name, dm=dm)
        self.h.world.set_member(self.chat, user.id, "member")
        return user

    @contextmanager
    def fixed_deck(self, roles_in_join_order: list[str]):
        """Deal exactly these roles (by lobby seat) instead of a random shuffle."""
        class _Rng:
            def shuffle(self, deck):
                deck[:] = roles_in_join_order

        with mock.patch("services.mafia_v1.secrets.SystemRandom", lambda: _Rng()):
            yield

    async def start_with_roles(self, roles_in_join_order: list[str]) -> Click:
        await self.join_all()
        with self.fixed_deck(roles_in_join_order):
            click = await self.start()
        assert "Роли отправлены" in click.text, f"start failed: {click.text}"
        return click

    # ── lobby ───────────────────────────────────────────────────────────────
    @property
    def host(self) -> SimUser:
        return self.users[0]

    def lobby(self) -> StoredMessage | None:
        """The lobby card, whichever screen (lobby / settings) it currently shows."""
        cards = [m for m in self.h.world.live(self.chat)
                 if any(b.get("callback_data", "").startswith(("mf:", "mfs:")) for b in m.buttons())]
        return cards[-1] if cards else None

    async def join_all(self) -> None:
        for user in self.users[1:]:
            await self.h.click(user, self.chat, self.lobby(), "Войти")

    async def start(self, by: SimUser | None = None) -> Click:
        return await self.h.click(by or self.host, self.chat, self.lobby(), "Начать")

    async def ready(self, size: int | None = None) -> "Table":
        """Join everybody and start; leaves the game in night 1."""
        await self.join_all()
        click = await self.start()
        assert "Роли отправлены" in click.text, f"start failed: {click.text}"
        return self

    # ── facts read straight from the database (what the bot knows) ──────────
    async def match(self) -> dict:
        return await self.h.match_row(self.chat)

    async def roles(self) -> dict[int, str]:
        rows = await self.h.sql(
            "SELECT user_id, role FROM predvestnik.mafia_v1_players WHERE match_id=$1", (await self.match())["id"])
        return {int(r["user_id"]): r["role"] for r in rows}

    async def alive(self) -> list[int]:
        rows = await self.h.sql(
            "SELECT user_id FROM predvestnik.mafia_v1_players WHERE match_id=$1 AND alive ORDER BY join_order",
            (await self.match())["id"])
        return [int(r["user_id"]) for r in rows]

    def user(self, user_id: int) -> SimUser:
        return next(u for u in self.users if u.id == user_id)

    async def by_role(self, *wanted: str) -> list[SimUser]:
        return [self.user(uid) for uid, role in (await self.roles()).items() if role in wanted]

    # ── acting through the interface ────────────────────────────────────────
    def action_message(self, user: SimUser) -> StoredMessage | None:
        """The newest DM that still carries move buttons."""
        found = [m for m in self.h.dm(user) if any(b.get("callback_data", "").startswith("mfa:") for b in m.buttons())]
        return found[-1] if found else None

    async def pick(self, user: SimUser, target: SimUser) -> Click:
        """Press «#n Name» for ``target`` on the user's own DM keyboard."""
        number = self.users.index(target) + 1
        return await self.h.click(user, user.id, self.action_message(user), f"#{number} {target.name}")

    async def vote(self, voter: SimUser, target: SimUser | None) -> Click:
        card = self.h.world.last(self.chat, "ГОЛОСОВАНИЕ")
        label = "Никого" if target is None else f"{self.users.index(target) + 1}. {target.name}"
        return await self.h.click(voter, self.chat, card, label)

    async def press(self, user: SimUser, label: str, contains: str = "") -> Click:
        card = self.h.world.last(self.chat, contains) if contains else self.h.world.live(self.chat)[-1]
        return await self.h.click(user, self.chat, card, label)

    # ── time ────────────────────────────────────────────────────────────────
    async def next_phase(self) -> None:
        """Let the current timer run out and let the scheduler process everything."""
        await self.h.expire(self.chat)
        await self.h.tick()

    async def phase(self) -> str:
        return (await self.match())["phase"]

    def group_texts(self) -> list[str]:
        return [m.text for m in self.h.world.live(self.chat)]

    def card_text(self) -> str:
        cards = [m for m in self.h.world.live(self.chat) if re.search(r"НОЧЬ|ОБСУЖДЕНИЕ|ГОЛОСОВАНИЕ|ПАУЗЕ|ОКОНЧЕНА|остановлена", m.text)]
        return cards[-1].text if cards else ""
