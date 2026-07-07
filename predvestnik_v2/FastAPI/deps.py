"""FastAPI/deps.py — dependency injection: database connection + Telegram auth.

Two auth flows are supported:
  x-init-data      — Telegram WebApp (opened inside Telegram)
  x-session-token  — Login Widget session (opened in a regular browser)
"""
import json
import time
from urllib.parse import unquote

from fastapi import Depends, Header, HTTPException
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from FastAPI.auth import verify_webapp_data, verify_session_token


async def get_db():
    """Yield a PGAdapter-wrapped DB connection from the shared pool."""
    async with get_pool().acquire() as conn:
        yield PGAdapter(conn)


# БЛОК 21.4: глобальный ban закрывает сайт целиком (403) — ссылку на мини-апп
# можно получить и в обход бота (переслал друг), поэтому блокируем на уровне auth-deps.
# TTL-кэш, чтобы не бить БД на каждый API-запрос (их десятки на загрузку страницы);
# 60с — приемлемая задержка вступления бана/разбана в силу для сайта.
_BAN_CACHE: dict[int, tuple[bool, float]] = {}
_BAN_CACHE_TTL = 60.0


async def _is_banned_cached(user_id: int) -> bool:
    now = time.monotonic()
    hit = _BAN_CACHE.get(user_id)
    if hit and hit[1] > now:
        return hit[0]
    from services.global_moderation import is_user_banned
    async with get_pool().acquire() as conn:
        banned = await is_user_banned(PGAdapter(conn), user_id)
    if len(_BAN_CACHE) > 5000:   # страховка от разрастания
        _BAN_CACHE.clear()
    _BAN_CACHE[user_id] = (banned, now + _BAN_CACHE_TTL)
    return banned


async def require_tg_user_base(
    x_init_data: str = Header(default=""),
    x_session_token: str = Header(default=""),
):
    """Auth БЕЗ проверки глобального бана — ТОЛЬКО для эндпоинтов, которые обязаны
    работать у забаненных (апелляции: admin_audit B1 — оспорить можно в любой
    момент и любым способом). Везде остальное — require_tg_user."""
    user = None
    # 1. Telegram WebApp (in-Telegram button)
    if x_init_data:
        user = verify_webapp_data(x_init_data)

    # 2. Login Widget session (browser)
    if not user and x_session_token:
        user_id = verify_session_token(x_session_token)
        if user_id:
            user = {"id": user_id}

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Требуется авторизация через Telegram.",
        )
    return user


async def require_tg_user(user=Depends(require_tg_user_base)):
    """Auth + гейт глобального бана (БЛОК 21.4): 403 на весь игровой API."""
    if await _is_banned_cached(int(user["id"])):
        raise HTTPException(
            status_code=403,
            detail="GLOBAL_BAN: доступ закрыт — активный глобальный бан. "
                   "Оспорить: «бот апелляция, текст» в ЛС бота или прямо здесь.",
        )
    return user


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
