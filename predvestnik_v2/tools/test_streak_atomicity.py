"""Регресс-тест П1 BOT_AUDIT.md: стрик — награда не атомарна, потеря молча и навсегда.

Корень: upsert_global_streak() (claim дня) коммитился отдельно от add_balance()
(начисление награды) — сбой БД между ними (напр. DB TimeoutError) оставлял день
помеченным «взятым», но без награды, и внешний except: pass молча это скрывал.

Фикс: claim + начисление + жетон block-end обёрнуты в один
`async with db.connection.transaction()` — сбой любого шага откатывает всё,
включая claim; внешний except теперь логирует через logger.exception вместо pass.

Тест: симулирует сбой add_balance ПОСЛЕ успешного claim и проверяет, что
транзакция реально откатывается (не коммитится), а не просто «печатает лог,
но день уже потерян»."""
import sys
import pathlib
import asyncio

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bot.middlewares import streak_mw


class FakeTx:
    def __init__(self, tracker):
        self.tracker = tracker

    async def __aenter__(self):
        self.tracker["entered"] = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.tracker["rolled_back"] = True
        else:
            self.tracker["committed"] = True
        return False  # не подавлять исключение — должно уйти во внешний except


class FakeConnection:
    def __init__(self, tracker):
        self.tracker = tracker

    def transaction(self):
        return FakeTx(self.tracker)


class _FakeCursor:
    async def fetchone(self):
        return None


class FakeDB:
    def __init__(self, tracker):
        self.connection = FakeConnection(tracker)
        self.executed = []

    async def execute(self, sql, args=()):
        self.executed.append(sql.strip())
        return _FakeCursor()

    async def commit(self):
        pass


class FakeUser:
    id = 12345
    first_name = "Тест"


class FakeChat:
    id = -100999
    type = "supergroup"


class FakeMessage:
    chat = FakeChat()


class FakeEvent:
    message = FakeMessage()
    callback_query = None


async def main():
    tracker: dict = {}
    db = FakeDB(tracker)
    handler_calls = []

    async def handler(event, data):
        handler_calls.append(1)
        return "handled"

    data = {"db": db, "event_from_user": FakeUser(), "event_chat": FakeChat(), "bot": None}

    # Пустой streak_row = «первое сообщение вообще» → is_new_day=True (services.streak
    # чистая функция, не мокаем — проверяем реальную логику вместе с транзакцией).
    async def fake_get_global_streak(db_, user_id):
        return {}
    streak_mw.streak_repo.get_global_streak = fake_get_global_streak

    async def fake_upsert(*a, **kw):
        assert tracker.get("entered"), "upsert_global_streak вызван ВНЕ транзакции — claim не защищён"
        assert not tracker.get("committed") and not tracker.get("rolled_back"), \
            "транзакция уже закрыта до вызова upsert_global_streak"
        return True
    streak_mw.streak_repo.upsert_global_streak = fake_upsert

    async def fake_add_balance(*a, **kw):
        # Симулируем ровно сценарий из аудита: обрыв БД МЕЖДУ claim и наградой.
        raise Exception("DB TimeoutError (симуляция обрыва между claim и наградой)")
    streak_mw.eco_repo.add_balance = fake_add_balance

    await streak_mw.streak_middleware(handler, FakeEvent(), data)

    assert tracker.get("rolled_back"), \
        "FAIL (П1 не пофикшен): транзакция НЕ откатилась при сбое add_balance — день остался бы claimed без награды"
    assert not tracker.get("committed"), "FAIL: транзакция закоммитилась несмотря на исключение внутри"
    assert handler_calls, "FAIL: handler() не был вызван — сбой не должен ронять обработку сообщения"

    print("OK: сбой add_balance после claim откатывает ВСЮ транзакцию (claim тоже), "
          "handler всё равно вызван — игрок получит награду со следующего сообщения, "
          "а не потеряет день навсегда")


asyncio.run(main())
