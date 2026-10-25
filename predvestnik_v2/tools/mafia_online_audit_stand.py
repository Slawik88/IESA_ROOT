"""Loopback-only visual audit fixtures backed by a disposable PostgreSQL schema.

python tools/mafia_online_audit_stand.py --port 8406
Open /scenarios for role-specific links. No production authentication or database.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from html import escape
from urllib.parse import urlparse

import uvicorn
from fastapi.responses import HTMLResponse

from test_mafia_online_ui import ROOT, build_app, html
from core import mafia_online as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from services import mafia_online as game

DSN = "postgresql://predvestnik_preprod@127.0.0.1:55439/predvestnik_preprod"
NAMES = ["Лиса", "Мартин", "Луна", "Доктор Ватсон", "Соня", "Александр", "Макс", "Лиса",
         "Капитан", "Ника", "Длинное имя участника другого чата", "Ветер", "Кот", "Тень",
         "Сова", "Артём", "Зима", "Лея", "Мира", "Тим"]
DEFINITIONS = [
    ("lobby", "Сбор · хозяин", "lobby", 6, 0),
    ("day", "День · мирный", "discussion", 8, 4),
    ("mafia", "Ночь · мафия", "night", 8, 0),
    ("doctor", "Ночь · доктор", "night", 8, 2),
    ("detective", "Ночь · детектив", "night", 8, 3),
    ("voting", "Открытое голосование", "voting", 8, 4),
    ("twenty", "Голосование · 20 игроков", "voting", 20, 9),
    ("dead", "Выбывший игрок", "discussion", 8, 5),
    ("paused", "Пауза · хозяин", "paused", 8, 0),
    ("finished", "Итоги · разговор после игры", "finished", 8, 4),
    ("cancelled", "Закрытая партия", "cancelled", 6, 0),
    ("citizen", "Ночь · мирный житель", "night", 8, 4),
    ("muted", "Разговор ограничен модератором", "discussion", 8, 4),
    ("claim", "Хозяин отсутствует", "discussion", 8, 4),
    ("postexpired", "Разговор после игры завершён", "finished", 8, 4),
]


async def seed(app):
    scenarios = []
    async with app.state.pool.acquire() as conn:
        db = PGAdapter(conn)
        for number, (key, title, phase, count, viewpoint) in enumerate(DEFINITIONS, 1):
            ids = [number * 1000 + index + 1 for index in range(count)]
            users = [{"id": uid, "first_name": NAMES[index]} for index, uid in enumerate(ids)]
            room = await game.create(db, users[0], seats=20, vote_mode="open")
            for person in users[1:]:
                await game.join(db, room, person)
            async with conn.transaction():
                state = await repo.load(db, room, lock=True)
                now = await repo.now(db)
                state.update(seats=max(8, count), phase=phase, phase_number=4, round=2,
                             phase_started=now-15, deadline=now+75, phase_deadline=now+75,
                             version=state["version"]+1, actions={}, paused="discussion", remaining=64)
                roles = ["mafia", "don", "doctor", "detective"] + ["citizen"] * (count-4)
                for index, person in enumerate(state["players"]):
                    person.update(role=None if phase == "lobby" else roles[index], seen=now)
                if key=="muted":
                    state["players"][viewpoint]["staff_muted"]=True
                if key=="claim":
                    state["players"][0]["seen"]=now-120
                if phase in ("discussion", "voting", "finished"):
                    state["players"][5]["alive"] = False
                    state["players"][3]["checks"] = [{"round": 1, "target": ids[0], "name": NAMES[0], "seat": 1, "mafia": True}]
                if phase == "night":
                    state["actions"][str(ids[1])] = {"kind":"mafia_target", "target":ids[4], "time":now-5}
                if phase == "voting":
                    state["actions"] = {str(ids[index]): {"kind":"vote", "target":ids[0] if index%2 else None, "time":now-8}
                                         for index in (0, 1, 2, 3)}
                if phase in rules.TERMINAL:
                    state.update(winner="town" if phase == "finished" else None, reason="victory" if phase == "finished" else "host",
                                 finished_at=now-1000 if key=="postexpired" else now, deadline=None)
                    await repo.release(db, room)
                await repo.save(db, state)
                if phase != "lobby":
                    await repo.message(db, room, "table", "Утро 2. Город проснулся. Пришло время обсудить подозрения.")
                conversation = [(4, "Мне кажется, вчера слишком быстро согласились с первым подозрением."),
                                (0, "Давайте по очереди. Кто менял голос в последний момент?"),
                                (6, "Я вернулся из другого чата. Что мы успели выяснить?"),
                                (7, "Смотрим на поступки, а не на одинаковые имена 🙂"),
                                (2, "Предлагаю сначала выслушать Луну."),
                                (1, "Согласен. До голосования ещё есть время.")]
                for index, text in conversation:
                    if index < count:
                        await repo.message(db, room, "table", text, user_id=ids[index], name=NAMES[index], seat=index+1)
                if phase == "night":
                    await repo.message(db, room, "mafia", "Обсудим цель. Я предлагаю место № 5.", user_id=ids[1], name=NAMES[1], seat=2)
                if phase == "discussion":
                    await repo.message(db, room, "afterlife", "Теперь наблюдаем за игрой вместе.", user_id=ids[5], name=NAMES[5], seat=6)
            scenarios.append({"key": key, "title": title, "room_id":room, "user_id":ids[viewpoint],
                              "host_id":ids[0], "users":ids, "url":f"/?user={ids[viewpoint]}&room={room}"})
    app.state.audit_scenarios = scenarios


def audit_app(dsn=DSN, live_reload=False):
    if urlparse(dsn).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Audit stand accepts a loopback PostgreSQL DSN only")
    app = build_app(dsn)
    original_lifespan = app.router.lifespan_context

    async def keep_fixtures_visible():
        while True:
            await asyncio.sleep(10)
            async with app.state.pool.acquire() as conn:
                db = PGAdapter(conn)
                async with conn.transaction():
                    now = await repo.now(db)
                    for item in app.state.audit_scenarios:
                        state = await repo.load(db, item["room_id"], lock=True)
                        if state["phase"] not in rules.TERMINAL:
                            state["deadline"] = now + 75
                            state["phase_deadline"] = now + 75
                            for person in state["players"]:
                                if item["key"]!="claim" or person["id"]!=state["host"]:
                                    person["seen"]=now
                            await repo.save(db, state, bump=False)

    @asynccontextmanager
    async def lifespan(app):
        async with original_lifespan(app):
            await seed(app)
            task = asyncio.create_task(keep_fixtures_visible())
            try:
                yield
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app.router.lifespan_context = lifespan
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", "") != "/"]

    @app.get("/")
    async def page():
        source=html()
        for name in ("app.55.js","app.56.js","mafia-online-v3.css"):
            stamp=(ROOT/"FastAPI/static"/name).stat().st_mtime_ns
            source=source.replace(f'/static/{name}"',f'/static/{name}?v={stamp}"')
        auto = """<script>addEventListener('DOMContentLoaded',()=>{const p=new URLSearchParams(location.search),r=Number(p.get('room')||0);r?moEnter(r):openMafiaOnline();});</script>"""
        if live_reload:
            auto += """<script>{let auditVersion='';setInterval(async()=>{try{const v=await(await fetch('/__qa/version',{cache:'no-store'})).text();if(auditVersion&&v!==auditVersion){moStore();location.reload();}auditVersion=v;}catch(_){}},1500);}</script>"""
        return HTMLResponse(source.replace("</body>", auto+"</body>"),headers={"Cache-Control":"no-store"})

    @app.get("/__qa/version")
    async def version():
        return {name:(ROOT/"FastAPI/static"/name).stat().st_mtime_ns for name in ("app.55.js","app.56.js","mafia-online-v3.css")}

    @app.get("/__qa/scenarios")
    async def scenario_json():
        return {"scenarios":app.state.audit_scenarios, "hub":"/?user=999001", "note":"Synthetic fixtures, real isolated online API. Fixture timers held for visual audit."}

    @app.get("/scenarios")
    async def index():
        links = "".join(f'<li><a href="{escape(row["url"])}">{escape(row["title"])}</a> · user {row["user_id"]} · room {row["room_id"]}</li>' for row in app.state.audit_scenarios)
        return HTMLResponse('<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Mafia audit scenarios</title>'
                            '<body style="background:#11131a;color:#ddd;font:18px system-ui;padding:24px;line-height:2"><h1>Мафия · сценарии аудита</h1>'
                            '<p>Изолированная локальная БД. Имена и партии тестовые. Таймеры сценариев удерживаются для осмотра.</p>'
                            '<a href="/?user=999001">Хаб · новый игрок</a><ul>'+links+'</ul></body></html>')
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=DSN)
    parser.add_argument("--port", type=int, default=8406)
    args = parser.parse_args()
    print(f"AUDIT_STAND http://127.0.0.1:{args.port}/scenarios", flush=True)
    uvicorn.run(audit_app(args.dsn, live_reload=True), host="127.0.0.1", port=args.port, log_level="warning")
