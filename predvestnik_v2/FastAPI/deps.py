"""FastAPI/deps.py — dependency injection: database connection + Telegram auth."""
from fastapi import Header, HTTPException
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from FastAPI.auth import verify_webapp_data


async def get_db():
    """Yield a PGAdapter-wrapped DB connection from the shared pool."""
    async with get_pool().acquire() as conn:
        yield PGAdapter(conn)


async def require_tg_user(x_init_data: str = Header(default="")):
    """Verify Telegram WebApp initData and return the parsed user dict.
    Raises 401 if the signature is invalid or missing."""
    user = verify_webapp_data(x_init_data)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Требуется авторизация через Telegram Mini App.",
        )
    return user
