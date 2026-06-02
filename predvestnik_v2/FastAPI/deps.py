"""FastAPI/deps.py — dependency injection: database connection + Telegram auth.

Two auth flows are supported:
  x-init-data      — Telegram WebApp (opened inside Telegram)
  x-session-token  — Login Widget session (opened in a regular browser)
"""
from fastapi import Header, HTTPException
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from FastAPI.auth import verify_webapp_data, verify_session_token


async def get_db():
    """Yield a PGAdapter-wrapped DB connection from the shared pool."""
    async with get_pool().acquire() as conn:
        yield PGAdapter(conn)


async def require_tg_user(
    x_init_data: str = Header(default=""),
    x_session_token: str = Header(default=""),
):
    """Accept either WebApp initData or a Login-Widget session token.
    Returns a minimal user dict with at least {id: int}."""
    # 1. Telegram WebApp (in-Telegram button)
    if x_init_data:
        user = verify_webapp_data(x_init_data)
        if user:
            return user

    # 2. Login Widget session (browser)
    if x_session_token:
        user_id = verify_session_token(x_session_token)
        if user_id:
            return {"id": user_id}

    raise HTTPException(
        status_code=401,
        detail="Требуется авторизация через Telegram.",
    )
