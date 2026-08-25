"""Регресс прод-инцидента 2026-07-23: /profile/me отдавал 500 «column
u.whatsnew_seen_id does not exist».

Root cause: ensure_account_columns() бежит в общем lifespan-цикле FastAPI на ОДНОМ
соединении со всеми прочими ensure_*. Если предыдущий ensure оставил asyncpg-
соединение в состоянии aborted-transaction (multi-statement execute / гонка
ON CONFLICT), КАЖДЫЙ следующий ALTER падает «current transaction is aborted», а
adapter.rollback() в autocommit — no-op и это состояние не чистит. Поэтому старые
колонки users (созданы в прежние деплои) существуют, а два новейших ALTER
(combat_tutorial_done, whatsnew_seen_id) молча не выполнялись.

Тест воспроизводит «пришли с poisoned-соединения»: до фикса созданных колонок 0,
после (preemptive + on-failure ROLLBACK на сыром соединении) — все создаются."""
import re
import sys
import pathlib
import asyncio

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from infrastructure.repositories.users import ensure_account_columns

_ADD_RE = re.compile(r"ADD COLUMN IF NOT EXISTS (\w+)", re.IGNORECASE)


class FakeConn:
    """Соединение, пришедшее в aborted-transaction (как из общего lifespan-цикла).
    Пока aborted — любой стейтмент падает, кроме ROLLBACK (снимает aborted)."""
    def __init__(self, aborted: bool = True):
        self._aborted = aborted
        self.created: set[str] = set()

    def is_in_transaction(self) -> bool:
        return self._aborted

    async def execute(self, sql, *args):
        if sql.strip().upper() == "ROLLBACK":
            self._aborted = False
            return "ROLLBACK"
        if self._aborted:
            raise Exception("current transaction is aborted, "
                            "commands ignored until end of transaction block")
        m = _ADD_RE.search(sql)
        if m:
            self.created.add(m.group(1).lower())
        return "ALTER TABLE"


class FakeAdapter:
    """Мини-PGAdapter: execute() — awaitable, commit/rollback — no-op (как в
    autocommit), .connection отдаёт сырое asyncpg-соединение."""
    def __init__(self, conn: FakeConn):
        self._conn = conn

    @property
    def connection(self) -> FakeConn:
        return self._conn

    def execute(self, sql, args=()):
        conn = self._conn

        class _Ex:
            def __await__(self):
                async def _run():
                    return await conn.execute(sql)
                return _run().__await__()
        return _Ex()

    async def commit(self):
        pass

    async def rollback(self):
        pass  # no-op в autocommit — как настоящий PGAdapter без активной tx


async def main():
    conn = FakeConn(aborted=True)
    await ensure_account_columns(FakeAdapter(conn))

    for col in ("account_xp", "account_level", "combat_tutorial_done",
                "whatsnew_seen_id"):
        assert col in conn.created, (
            f"FAIL: колонка {col} не создана — соединение осталось aborted "
            f"(создано: {sorted(conn.created)})")

    # И на чистом соединении (обычный старт) всё по-прежнему работает
    conn2 = FakeConn(aborted=False)
    await ensure_account_columns(FakeAdapter(conn2))
    assert "whatsnew_seen_id" in conn2.created, "FAIL: не работает на чистом соединении"

    print("OK: ensure_account_columns создаёт все колонки даже с poisoned-соединения "
          "и не ломается на чистом")


asyncio.run(main())
