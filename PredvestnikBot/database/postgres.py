"""
🐘 Прямая работа с PostgreSQL без слоя совместимости
После миграции этот модуль заменит sql_compat.py для всех операций с БД.
"""

import asyncpg
from typing import Any, List, Dict
from config import DATABASE_PATH


# ═══════════════════════════════════════════════════════════════════════════════
#  🔧 Подключение к PostgreSQL
# ═══════════════════════════════════════════════════════════════════════════════

_pg_pool: asyncpg.Pool | None = None


async def get_pg_pool() -> asyncpg.Pool:
    """Получить пул подключений к PostgreSQL"""
    global _pg_pool
    
    if _pg_pool is None:
        if not DATABASE_PATH.startswith(('postgresql://', 'postgres://')):
            raise RuntimeError(
                f"❌ DATABASE_PATH должен быть PostgreSQL DSN, получен: {DATABASE_PATH}"
            )
        
        _pg_pool = await asyncpg.create_pool(
            DATABASE_PATH,
            min_size=2,
            max_size=20,
            server_settings={
                'application_name': 'PredvestnikBot',
                'timezone': 'UTC'
            }
        )
    
    return _pg_pool


async def close_pg_pool():
    """Закрыть пул подключений"""
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None


# ═══════════════════════════════════════════════════════════════════════════════
#  🎭 Контекстный менеджер подключения
# ═══════════════════════════════════════════════════════════════════════════════

class PostgresConnection:
    """Контекстный менеджер для работы с PostgreSQL соединением"""
    
    def __init__(self):
        self._conn: asyncpg.Connection | None = None
        self._tx: asyncpg.Transaction | None = None
        
    async def __aenter__(self) -> 'PostgresConnection':
        pool = await get_pg_pool()
        self._conn = await pool.acquire()
        # Автоматически стартуем транзакцию для совместимости с прежним API
        self._tx = self._conn.transaction()
        await self._tx.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._tx:
            if exc_type is None:
                await self._tx.commit()
            else:
                await self._tx.rollback()
            self._tx = None
            
        if self._conn:
            pool = await get_pg_pool()
            await pool.release(self._conn)
            self._conn = None

    # ─────────────────────────────────────────────────────────────────────────
    #  🔹 Методы выполнения запросов (API совместимый с aiosqlite)
    # ─────────────────────────────────────────────────────────────────────────
    
    async def execute(self, sql: str, params=None) -> Any:
        """Выполнить SQL запрос (INSERT, UPDATE, DELETE)"""
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        
        if params is None:
            params = []
        elif isinstance(params, dict):
            # Преобразуем именованные параметры в позиционные
            params = list(params.values())
            
        return await self._conn.execute(sql, *params)
    
    async def fetch(self, sql: str, params=None) -> List[asyncpg.Record]:
        """Выполнить SELECT и получить все результаты"""
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
            
        if params is None:
            params = []
        elif isinstance(params, dict):
            params = list(params.values())
            
        return await self._conn.fetch(sql, *params)
    
    async def fetchone(self, sql: str, params=None) -> asyncpg.Record | None:
        """Выполнить SELECT и получить первый результат"""
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
            
        if params is None:
            params = []
        elif isinstance(params, dict):
            params = list(params.values())
            
        return await self._conn.fetchrow(sql, *params)
    
    async def fetchval(self, sql: str, params=None) -> Any:
        """Выполнить SELECT и получить единственное значение"""
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
            
        if params is None:
            params = []
        elif isinstance(params, dict):
            params = list(params.values())
            
        return await self._conn.fetchval(sql, *params)
    
    async def executemany(self, sql: str, params_list: List[Any]) -> None:
        """Выполнить SQL запрос множество раз с разными параметрами"""
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        
        for params in params_list:
            if isinstance(params, dict):
                params = list(params.values())
            await self._conn.execute(sql, *params)
    
    # Legacy методы для совместимости с существующим кодом
    async def commit(self):
        """Коммит транзакции (для совместимости, транзакция коммитится автоматически)"""
        pass  # Транзакция автоматически коммитится в __aexit__
    
    async def rollback(self):
        """Откат транзакции"""
        if self._tx:
            await self._tx.rollback()


# ═══════════════════════════════════════════════════════════════════════════════
#  🚀 Простое API для быстрых запросов
# ═══════════════════════════════════════════════════════════════════════════════

async def execute_query(sql: str, *params) -> Any:
    """Быстро выполнить запрос без транзакции"""
    async with PostgresConnection() as db:
        return await db.execute(sql, params)


async def fetch_all(sql: str, *params) -> List[asyncpg.Record]:
    """Быстро получить все результаты SELECT"""
    async with PostgresConnection() as db:
        return await db.fetch(sql, params)


async def fetch_one(sql: str, *params) -> asyncpg.Record | None:
    """Быстро получить первый результат SELECT"""
    async with PostgresConnection() as db:
        return await db.fetchone(sql, params)


async def fetch_value(sql: str, *params) -> Any:
    """Быстро получить единственное значение"""
    async with PostgresConnection() as db:
        return await db.fetchval(sql, params)


# Псевдоним для совместимости с существующим кодом
connect = PostgresConnection


# ═══════════════════════════════════════════════════════════════════════════════
#  📋 Row-совместимость для плавного перехода
# ═══════════════════════════════════════════════════════════════════════════════

# asyncpg.Record уже работает как dict и как tuple,
# так что дополнительных оберток не нужно
Row = asyncpg.Record