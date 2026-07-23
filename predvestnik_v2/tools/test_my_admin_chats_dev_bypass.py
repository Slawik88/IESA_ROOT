"""Регресс-тест: разработчик (DEVELOPER_ID) не видел на сайте свой собственный
чат в свитчере «мои чаты», если бот там ни разу не выдавал ему явный
local_rank командой (просто состоит как обычный участник/владелец группы в
самом Telegram). Root cause: my_admin_chats() фильтровал строго
`ucs.local_rank >= 1` без байпаса, хотя _get_actor_rank() уже давал
DEVELOPER_ID ранг 6 в ЛЮБОМ чате. Фикс: FastAPI/routers/admin.py::my_admin_chats
теперь снимает фильтр по рангу для DEVELOPER_ID и подставляет фактический
ранг (6) в ответ, как и в _get_actor_rank."""
import sys
import pathlib
import asyncio

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from FastAPI.routers import admin


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeDB:
    """Один юзер, 2 чата: A — состоит, но local_rank=0 (бот ни разу не выдавал
    ранг, как раз кейс владельца из репорта), B — обычный назначенный админ."""
    ROWS = [
        {"chat_tg_id": -100, "chat_title": "Чат A (без явного ранга)", "local_rank": 0, "admin_chat_id": None},
        {"chat_tg_id": -200, "chat_title": "Чат B (обычный админ)", "local_rank": 3, "admin_chat_id": None},
    ]

    def execute(self, sql, args=()):
        if "FROM user_chat_stats ucs" in sql:
            bypass = "1=1" in sql
            rows = self.ROWS if bypass else [r for r in self.ROWS if r["local_rank"] >= 1]
            return _FakeCursor(rows)
        return _FakeCursor([])  # chat_links / chat_settings подзапросы — пусто в тесте


async def main():
    admin.DEVELOPER_ID = 999

    # Обычный юзер: чат без явного ранга не должен быть виден
    r = await admin.my_admin_chats(db=FakeDB(), user={"id": 111})
    ids = {c["chat_tg_id"] for c in r["chats"]}
    assert ids == {-200}, f"FAIL: обычный юзер должен видеть только чат с рангом, получил {ids}"

    # Разработчик: должен видеть ОБА чата, включая тот, где нет явного ранга
    r = await admin.my_admin_chats(db=FakeDB(), user={"id": 999})
    ids = {c["chat_tg_id"] for c in r["chats"]}
    assert ids == {-100, -200}, f"FAIL: разработчик должен видеть все свои чаты, получил {ids}"

    # Ранг в чате A (в БД local_rank=0) должен отдаваться как 6 (Владелец) —
    # фронт (app.07.js:27) рисует метку по сырому local_rank из ответа, не по rank_name.
    chat_a = next(c for c in r["chats"] if c["chat_tg_id"] == -100)
    assert chat_a["local_rank"] == 6, f"FAIL: ранг разработчика должен быть 6, получили {chat_a['local_rank']}"
    assert chat_a["rank_name"] == "👑 Владелец", f"FAIL: rank_name={chat_a['rank_name']!r}"

    print("OK: разработчик видит любой свой чат под верным рангом; обычный админ — "
          "только чаты, где ему явно выдан ранг")


asyncio.run(main())
