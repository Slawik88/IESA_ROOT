#!/usr/bin/env python3
"""Watch a whole Mafia game without a real group or real players.

Seven players sit in a chat of forty; the rest chat freely.  The script plays the game through
buttons exactly like people would and prints what everybody sees.  Needs the loopback dev database:

    PYTHONPATH=. python tools/mafia_dev_sandbox.py --dsn postgresql://predvestnik_preprod@127.0.0.1:55432/predvestnik_preprod
    ... --watch Игрок2,Игрок4     # whose private chats to show (default: the mafioso, the detective, a citizen)
    ... --out docs/mafia_sample_game.md
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DECK = ["citizen", "mafia", "citizen", "doctor", "detective", "citizen", "citizen"]


def _note(h, text: str) -> None:
    h.world.calls.append(("NOTE", {"text": text}))


async def play(h) -> tuple:
    from tools.mafia_sim.table import Table
    t = await Table.create(h, 7, names=["Анна", "Борис", "Вера", "Глеб", "Дина", "Егор", "Жанна"], command="бот мафия")
    crowd = [t.add_bystander(f"Зритель{i}") for i in range(1, 34)]  # 7 players + 33 onlookers = a chat of 40
    guest = t.users[6]
    h.world.dm_open.discard(guest.id)
    _note(h, "Анна пишет «бот мафия» в общем чате — появляется лобби")
    for user in t.users[1:6]:
        _note(h, f"{user.name} нажимает «Войти»")
        await h.click(user, t.chat, t.lobby(), "Войти")
    _note(h, "Жанна ни разу не открывала бота: «Войти» ведёт её по ссылке в бота")
    await h.click(guest, t.chat, t.lobby(), "Войти")
    h.world.dm_open.add(guest.id)
    match_id = (await t.match())["id"]
    _note(h, "Жанна нажала Start у бота (ссылка mj…) — её записало в лобби само")
    await h.say(guest, guest.id, f"/start mj{match_id}")
    _note(h, "Зрители болтают — лобби всплывает снова, если его закопали (раз в 90 секунд, не чаще)")
    for i in range(26):
        await h.say(crowd[i % len(crowd)], t.chat, f"флуд {i}")
    _note(h, "Анна нажимает «Начать» — роли уходят в личные сообщения")
    with t.fixed_deck(DECK):
        await t.start()
    await _round_one(h, t, crowd)
    return t, crowd


async def _round_one(h, t, crowd) -> None:
    u = t.users
    _note(h, "Ночь 1: мафия (Борис) выбирает Веру, доктор (Глеб) лечит Анну, детектив (Дина) проверяет Бориса")
    await t.pick(u[1], u[2]); await t.pick(u[3], u[0]); await t.pick(u[4], u[1])
    await t.next_phase()
    _note(h, "Утро. Живые игроки и зрители пишут свободно, а выбывшая Вера — нет (её сообщение удаляется)")
    await h.say(u[0], t.chat, "Борис странно молчал"); await h.say(crowd[0], t.chat, "а мы смотрим, ставим на мирных"); await h.say(u[2], t.chat, "я тоже хочу сказать")
    _note(h, "Анна (хозяйка) нажимает «К голосованию» — карточка голосования появляется внизу, игроки получают бюллетени в личку")
    await t.press(t.host, "К голосованию", "ОБСУЖДЕНИЕ")
    _note(h, "Анна голосует в чате, Дина — кнопкой в личке, остальные в чате")
    await t.vote(u[0], u[1])
    await h.click(u[4], u[4].id, t.action_message(u[4]), "#2 Борис")
    for voter in (u[3], u[5], u[6]):
        await t.vote(voter, u[1])
    await t.vote(u[1], u[0])
    await t.next_phase()


async def main_async(args) -> int:
    from tools.mafia_sim.harness import Harness
    from tools.mafia_sim.transcript import render
    h = await Harness().open()
    try:
        t, _ = await play(h)
        names = {u.id: u.name for u in t.users}
        roles = await t.roles()
        watch_names = [n for n in args.watch.split(",") if n]
        watch = {u.id for u in t.users if u.name in watch_names} or {t.users[1].id, t.users[4].id, t.users[0].id}
        from core.mafia_v1 import public_role_name
        text = ("# Пробная партия Мафии (симуляция)\n\nРоли: " + ", ".join(f"{names[i]} — {public_role_name(r)}" for i, r in roles.items()) + "\n\n```\n"
                + render(h.world, group=t.chat, names=names, watch=watch) + "\n```\n")
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(text)
            print(f"written {args.out}")
        else:
            print(text)
    finally:
        await h.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--watch", default="")
    parser.add_argument("--out", default="")
    arguments = parser.parse_args()
    os.environ.setdefault("BOT_TOKEN", "123456:SIM-TOKEN")
    from tools.mafia_sim.harness import assert_dev_dsn
    assert_dev_dsn(arguments.dsn)
    os.environ["DATABASE_URL"] = arguments.dsn
    raise SystemExit(asyncio.run(main_async(arguments)))
