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

import bot.chat  # noqa: E402  реальный реестр
from bot.chat import help as chat_help  # noqa: E402
from bot.chat.framework import registry as real  # noqa: E402
assert parse(real, "бот помощь топ").command.name == "помощь"
assert parse(real, "бот сайт").command.name == "сайт"
assert "бот топ" in chat_help.section_text("stats")
assert chat_help.main_keyboard(1).inline_keyboard
print("OK: help")

from bot.chat import ranks  # noqa: E402
assert ranks.find_rank("модератор") == 4 and ranks.find_rank("ст. модератор") == 5
assert ranks.find_rank("мл модератор") == 3 and ranks.find_rank("7") == 7 and ranks.find_rank("10") is None
assert ranks.legacy_rank(1) == 4 and ranks.legacy_rank(5) == 8 and ranks.legacy_rank(None) == 0
assert ranks.check_assign(7, 2, 9) is not None          # владельца не выдать командой
assert ranks.check_assign(6, 6, 2) is not None          # равному нельзя
assert ranks.check_assign(6, 2, 6) is not None          # свой ранг выдать нельзя
assert ranks.check_assign(6, 2, 5) is None
assert ranks.check_assign(ranks.DEV_LEVEL, 8, 8) is None  # разработчик может всё, кроме владельца
assert parse(real, "бот снять ранг, @user").command.name == "снять ранг"
assert parse(real, "бот ранг @user 4").command.name == "ранг"
print("OK: ranks")
