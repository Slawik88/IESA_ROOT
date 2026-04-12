"""
PostgresStorage — персистентное FSM-хранилище для aiogram 3 на asyncpg.

Заменяет MemoryStorage: состояния диалогов переживают перезапуск бота.
Таблица: fsm_data (chat_id, user_id, state, data).
Использует существующий пул asyncpg из database.postgres.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType

from database.postgres import get_pg_pool

_log = logging.getLogger("fsm.postgres")


class PostgresStorage(BaseStorage):
    """Персистентное FSM-хранилище в PostgreSQL (asyncpg)."""

    # ── Инициализация таблицы ─────────────────────────────────────────────

    async def init_table(self) -> None:
        """Создать таблицу fsm_data если не существует. Вызвать при старте бота."""
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS fsm_data (
                    chat_id  BIGINT NOT NULL,
                    user_id  BIGINT NOT NULL,
                    state    TEXT,
                    data     JSONB NOT NULL DEFAULT '{}',
                    PRIMARY KEY (chat_id, user_id)
                )
            """)
        _log.info("FSM таблица fsm_data готова")

    # ── Ключ → кортеж ────────────────────────────────────────────────────

    @staticmethod
    def _pk(key: StorageKey) -> tuple[int, int]:
        return key.chat_id, key.user_id

    # ── State ─────────────────────────────────────────────────────────────

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        chat_id, user_id = self._pk(key)
        state_str: str | None = None
        if state is not None:
            state_str = state.state if isinstance(state, State) else str(state)
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO fsm_data (chat_id, user_id, state)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (chat_id, user_id)
                   DO UPDATE SET state = EXCLUDED.state""",
                chat_id, user_id, state_str,
            )

    async def get_state(self, key: StorageKey) -> Optional[str]:
        chat_id, user_id = self._pk(key)
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state FROM fsm_data WHERE chat_id=$1 AND user_id=$2",
                chat_id, user_id,
            )
        return row["state"] if row else None

    # ── Data ──────────────────────────────────────────────────────────────

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        chat_id, user_id = self._pk(key)
        data_json = json.dumps(data, ensure_ascii=False, default=str)
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO fsm_data (chat_id, user_id, data)
                   VALUES ($1, $2, $3::jsonb)
                   ON CONFLICT (chat_id, user_id)
                   DO UPDATE SET data = EXCLUDED.data""",
                chat_id, user_id, data_json,
            )

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        chat_id, user_id = self._pk(key)
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM fsm_data WHERE chat_id=$1 AND user_id=$2",
                chat_id, user_id,
            )
        if not row or not row["data"]:
            return {}
        val = row["data"]
        if isinstance(val, str):
            return json.loads(val)
        return dict(val)

    # ── Close / очистка ───────────────────────────────────────────────────

    async def close(self) -> None:
        """Пул управляется глобально — тут ничего закрывать не нужно."""
