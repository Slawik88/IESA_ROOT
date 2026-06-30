"""FastAPI/deps.py — dependency injection: database connection + Telegram auth.

Two auth flows are supported:
  x-init-data      — Telegram WebApp (opened inside Telegram)
  x-session-token  — Login Widget session (opened in a regular browser)
"""
import json
from urllib.parse import unquote

from fastapi import Depends, Header, HTTPException
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


def require_module(module_key: str):
    """FastAPI dependency factory: checks per-chat and global module toggles.

    chat_id source (priority order):
      1. initData 'chat' field (Telegram-signed, present only when opened from a group)
      2. x-chat-id header (fallback for Login Widget browser sessions)

    Skips per-chat check when no chat_id is known.
    Always performs the global check via global_module_toggles.
    """
    async def _check(
        x_init_data: str = Header(default=""),
        x_chat_id: int = Header(default=0),
        db=Depends(get_db),
    ):
        # Extract chat_id from Telegram-signed initData
        chat_id = 0
        if x_init_data:
            try:
                params: dict[str, str] = {}
                for part in x_init_data.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        params[k] = unquote(v)
                chat_str = params.get("chat", "")
                if chat_str:
                    chat_id = int(json.loads(chat_str).get("id", 0))
            except Exception:
                pass

        if not chat_id:
            chat_id = x_chat_id

        # Per-chat check
        if chat_id:
            async with db.execute(
                f"SELECT COALESCE({module_key}, 1) FROM chat_settings WHERE chat_id = ?",
                (chat_id,),
            ) as c:
                row = await c.fetchone()
            if row and row[0] == 0:
                raise HTTPException(403, "🔧 Этот раздел временно недоступен в данном чате.")

        # Global check
        async with db.execute(
            "SELECT enabled FROM global_module_toggles WHERE module_key = ?",
            (module_key,),
        ) as c:
            grow = await c.fetchone()
        if grow and grow[0] == 0:
            raise HTTPException(403, "🔧 Этот раздел временно отключён глобально.")

    return _check
