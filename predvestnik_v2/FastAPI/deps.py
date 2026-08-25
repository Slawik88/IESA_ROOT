"""FastAPI/deps.py — dependency injection: database connection + Telegram auth.

Two auth flows are supported:
  x-init-data      — Telegram WebApp (opened inside Telegram)
  x-session-token  — Login Widget session (opened in a regular browser)
"""
import asyncio
import json
import time
from urllib.parse import unquote

from fastapi import Depends, Header, HTTPException, Request
from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from FastAPI.auth import verify_webapp_data, verify_session_token, hash_signal
from infrastructure.preprod import require_preprod_user


async def get_db():
    """Yield a PGAdapter-wrapped DB connection from the shared pool.

    If the shared pool has not been initialized yet, create it lazily.
    This protects FastAPI requests that arrive before the bot process finishes
    its startup sequence and global DB initialization.
    """
    await create_pool()
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
    await create_pool()
    from services.global_moderation import is_user_banned
    async with get_pool().acquire() as conn:
        banned = await is_user_banned(PGAdapter(conn), user_id)
    if len(_BAN_CACHE) > 5000:   # страховка от разрастания
        _BAN_CACHE.clear()
    _BAN_CACHE[user_id] = (banned, now + _BAN_CACHE_TTL)
    return banned


async def require_tg_user_base(
    request: Request,
    x_init_data: str = Header(default=""),
    x_session_token: str = Header(default=""),
    x_client_fp: str = Header(default=""),
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
    if not require_preprod_user(int(user["id"])):
        # A Quick Tunnel is public by design; only explicitly listed test
        # accounts may mutate the isolated preprod database.
        raise HTTPException(status_code=403, detail="Тестовый стенд закрыт для этого аккаунта.")
    _fire_and_forget(_capture_signals(int(user["id"]), request, x_client_fp))
    return user


# ── Твинк-детект (dev-console, диагностика без наказаний) ───────────────────────
# Пишем солёные HMAC-хэши IP/отпечатка устройства (не сырые значения — auth.hash_signal),
# с троттлингом в памяти, иначе десятки API-запросов на загрузку страницы = столько же
# INSERT'ов на каждого юзера. См. services/twin_detection.py — сам скоринг пар.
_SIGNAL_SEEN: dict[tuple, float] = {}
_SIGNAL_SEEN_TTL = 1800.0  # 30 минут между записями одного и того же сигнала
_BG_TASKS: set = set()


def _fire_and_forget(coro) -> None:
    """asyncio.create_task без хранения ссылки рискует потерять задачу к GC —
    держим её в сете до завершения."""
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


async def _capture_signals(user_id: int, request: Request, client_fp: str) -> None:
    try:
        now = time.monotonic()
        raw_pairs = []
        ip = _client_ip(request)
        if ip:
            raw_pairs.append(("ip", hash_signal(ip)))
        if client_fp:
            raw_pairs.append(("fp", hash_signal(client_fp)))
        to_write = []
        for kind, vhash in raw_pairs:
            if not vhash:
                continue
            key = (user_id, kind, vhash)
            hit = _SIGNAL_SEEN.get(key)
            if hit and hit > now:
                continue
            _SIGNAL_SEEN[key] = now + _SIGNAL_SEEN_TTL
            to_write.append((kind, vhash))
        if not to_write:
            return
        if len(_SIGNAL_SEEN) > 50000:   # страховка от разрастания
            _SIGNAL_SEEN.clear()
        await create_pool()
        from infrastructure.repositories import twin_signals
        async with get_pool().acquire() as conn:
            db = PGAdapter(conn)
            for kind, vhash in to_write:
                await twin_signals.record(db, user_id, kind, vhash)
    except Exception:
        pass


async def require_tg_user(user=Depends(require_tg_user_base)):
    """Auth + гейт глобального бана (БЛОК 21.4): 403 на весь игровой API."""
    if await _is_banned_cached(int(user["id"])):
        raise HTTPException(
            status_code=403,
            detail="GLOBAL_BAN: доступ закрыт — активный глобальный бан. "
                   "Оспорить: «бот апелляция, текст» в ЛС бота или прямо здесь.",
        )
    return user


# ── БЛОК 21.2: гибкие права глобальных рангов ────────────────────────────────
# Реестр функций — core/admin_permissions.py; эффективные наборы (дефолты +
# БД-оверрайды) — services/global_permissions.py. Ранг 3 всегда имеет всё.
import os as _os

_DEV_ID = int(_os.getenv("DEVELOPER_ID", "0") or 0)


async def _actor_global_rank(db, user_id: int) -> int:
    from infrastructure.repositories.users import get_global_rank
    rank = await get_global_rank(db, user_id) or 0
    # Страховка: DEVELOPER_ID — ранг 3 даже если строка users ещё не проставлена
    # бот-middleware (веб-процесс мог стартовать первым).
    if _DEV_ID and user_id == _DEV_ID:
        rank = max(rank, 3)
    return rank


async def check_global_perm(db, user_id: int, perm: str) -> int:
    """403, если у global_rank юзера нет права `perm`. Возвращает ранг."""
    from services import global_permissions as gperm
    from core.admin_permissions import ADMIN_PERMISSIONS
    rank = await _actor_global_rank(db, user_id)
    if not await gperm.has_perm(db, rank, perm):
        label = ADMIN_PERMISSIONS.get(perm, {}).get("label", perm)
        raise HTTPException(403, f"Нет права: {label}")
    return rank


async def check_global_perm_any(db, user_id: int, perms: list[str]) -> int:
    """403, если нет НИ ОДНОГО из прав (для эндпоинтов, питающих несколько экранов)."""
    from services import global_permissions as gperm
    rank = await _actor_global_rank(db, user_id)
    for p in perms:
        if await gperm.has_perm(db, rank, p):
            return rank
    raise HTTPException(403, "Нет права на этот раздел консоли.")


def require_module(module_key: str):
    """FastAPI dependency factory: checks per-chat and global module toggles.

    chat_id source (priority order):
      1. initData 'chat' field (Telegram-signed, present only when opened from a group)
      2. x-chat-id header (fallback for Login Widget browser sessions)

    Skips per-chat check when no chat_id is known.
    Always performs the global check via global_module_toggles.

    DEVELOPER_ID обходит любой тумблер (страховка та же, что в _actor_global_rank
    выше) — иначе разработчик не может зайти и проверить/включить обратно
    раздел, который сам же выключил для теста (жалоба владельца 2026-07-29:
    "почему разделы отключаются и для разработчика")."""
    async def _check(
        x_init_data: str = Header(default=""),
        x_chat_id: int = Header(default=0),
        db=Depends(get_db),
        user=Depends(require_tg_user_base),
    ):
        if _DEV_ID and int(user["id"]) == _DEV_ID:
            return
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


def require_tab_enabled(flag_key: str):
    """FastAPI dependency factory для GLOBAL-ONLY флагов из system_flags
    (админка «Глобальные модули», infrastructure/repositories/system_flags.py).

    Отдельно от require_module() выше: тот читает global_module_toggles/
    chat_settings (per-chat + отдельная global-таблица), этот — system_flags
    (только global, ключи tab_*). Раньше system_flags использовался ТОЛЬКО как
    UI-хинт (profile.py отдаёт его фронту, чтобы спрятать вкладку) — сам тумблер
    ничего на бэке не блокировал. Баг 2026-07-29: владелец выключил
    "Косметика/Образы" в админке, а /cosmetics/buy продолжал молча принимать
    покупки — вкладка пропадала из меню, но прямой запрос к API проходил.

    DEVELOPER_ID обходит тумблер — та же страховка, что в require_module()."""
    from infrastructure.repositories import system_flags as _flags_repo

    async def _check(db=Depends(get_db), user=Depends(require_tg_user_base)):
        if _DEV_ID and int(user["id"]) == _DEV_ID:
            return
        if not await _flags_repo.is_enabled(db, flag_key):
            raise HTTPException(403, "🔧 Этот раздел временно отключён.")

    return _check
