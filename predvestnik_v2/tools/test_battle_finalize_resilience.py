"""Регресс-тест бага 2026-07-23: бой теряет состояние посреди партии.

Корень: _finalize_if_over() в FastAPI/routers/battle.py сначала помечает бой
завершённым (bt_repo.finish — автокоммитится МГНОВЕННО, PGAdapter.commit() —
no-op без явного BEGIN, см. infrastructure/pg_adapter.py:269-273), а ПОТОМ
считает награды режима. Если начисление наград бросает исключение (в репорте
владельца — set_combat_tutorial_done() падал на отсутствующей на проде колонке
combat_tutorial_done, до рестарта DO), исключение улетает наверх необработанным:
клиент получает 500 «Сервер прилёг отдохнуть», а бой на сервере уже НАВСЕГДА
'won'/'lost' — следующее действие (атака/Сдаться/Выйти) получает 404 «бой не
найден», хотя клиент ещё показывает живого врага.

Тест: симулирует падение шага начисления наград (fake db бросает ошибку именно
на UPDATE combat_tutorial_done, как отсутствующая колонка на проде) и проверяет,
что _finalize_if_over НЕ бросает исключение наружу — статус боя в БД всё равно
корректно зафиксирован (finish() успел отработать), reward=None, ошибка видна
только в логах."""
import sys
import pathlib
import asyncio

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from FastAPI.routers import battle as battle_router


class _FakeCursor:
    async def fetchone(self):
        return None


class FakeDB:
    """Мини-эмулятор PGAdapter: execute() — сразу awaitable (как настоящий
    autocommit), фиксирует вызовы, бросает ошибку ТОЛЬКО на апдейте
    combat_tutorial_done (воспроизводит «column does not exist» на проде)."""
    def __init__(self):
        self.calls = []

    async def execute(self, sql, args=()):
        self.calls.append(sql.strip())
        if "combat_tutorial_done = TRUE" in sql:
            raise Exception('column "combat_tutorial_done" does not exist')
        return _FakeCursor()

    async def commit(self):
        pass


async def main():
    db = FakeDB()
    row = {"id": 42, "mode": "tutorial", "ref_id": 0}
    state = {"status": "won"}
    user = {"id": 1460945748, "username": "star_seeker"}

    try:
        reward = await battle_router._finalize_if_over(db, 1460945748, user, row, state)
    except Exception as e:
        print(f"FAIL: _finalize_if_over бросил исключение наружу — {e!r}")
        print("Бой останется помеченным won в БД, но клиент получит 500 и застрянет.")
        sys.exit(1)

    finish_called = any("battles" in c and "SET status" in c for c in db.calls)
    assert finish_called, "finish() не был вызван — статус боя не зафиксирован"
    assert reward is None, f"ожидали reward=None после сбоя начисления, получили {reward!r}"
    print("OK: исключение в начислении наград поймано, finish() отработал, "
          f"reward={reward!r} — клиент получит валидный ответ 'won' вместо 500/404-ловушки")


asyncio.run(main())
