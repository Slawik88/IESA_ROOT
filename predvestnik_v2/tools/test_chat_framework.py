#!/usr/bin/env python3
"""Каркас команд чата: разбор «бот [команда], значения», подсказки, права разработчика."""
import os
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://x:y@localhost/z")
os.environ["DEVELOPER_ID"] = "42"
from datetime import date

from bot.chat.access import may_sanction
from bot.chat.framework import Parsed, Registry, Unknown, parse
from bot.chat.top import period_range

async def _h(ctx): ...
reg = Registry()
reg.command("бан", bare=False)(_h)
reg.command("снять мут")(_h)
reg.command("топ", aliases=("top",))(_h)
reg.command("обнять", bare=True)(_h)

p = parse(reg, "Бот бан, @user 5д")
assert isinstance(p, Parsed) and p.command.name == "бан" and p.args == "@user 5д" and p.prefixed
p = parse(reg, "бот, снять мут @user")
assert p.command.name == "снять мут" and p.args == "@user"
assert parse(reg, "бан @user") is None            # без «бот» только bare-команды
assert parse(reg, "обнять @user").command.name == "обнять"
assert parse(reg, "привет всем") is None
u = parse(reg, "бот бтп")
assert isinstance(u, Unknown) and "топ" in u.suggestions
assert parse(reg, "бот njg").command.name == "топ"

assert period_range("d", date(2026, 10, 8)) == ("2026-10-08", "2026-10-08")
assert period_range("w", date(2026, 10, 8)) == ("2026-10-05", "2026-10-08")
assert period_range("lw", date(2026, 10, 8)) == ("2026-09-28", "2026-10-04")

assert not may_sanction(1, 42, actor_has_right=True)    # на разработчика нельзя
assert may_sanction(42, 7, actor_has_right=False)       # разработчик обходит права
assert not may_sanction(1, 7, actor_has_right=False)
print("OK: chat framework")
