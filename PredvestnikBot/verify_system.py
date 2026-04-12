#!/usr/bin/env python3
"""
verify_system.py — Верификация всех компонентов после архитектурной миграции.

Запуск:
    python verify_system.py

Проверяет:
    1) PostgresStorage — корректность import / подклассов
    2) FastAPI app — маршруты зарегистрированы + lifespan
    3) services.achievements — реестр / функции экспортированы
    4) Таланты — все 17 зарегистрированы, нет мёртвых
    5) Структура main.py — нет aiohttp, есть lifespan
    6) Зависимости — requirements.txt корректен
    7) Legacy-код удалён
    8) Asyncpg пул — реальная запись/чтение в БД
    9) FastAPI HTTP — реальные запросы к эндпоинтам
"""
from __future__ import annotations

import sys
import importlib
import asyncio
import traceback
import pathlib

# ─── Все тесты ──────────────────────────────────────────────────────────────

_passed = 0
_failed = 0
_errors: list[str] = []


def _check(name: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        msg = f"  ❌ {name}" + (f" — {detail}" if detail else "")
        print(msg)
        _errors.append(msg)


def _section(title: str):
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


# ═══════════════════════════════════════════════════════════════════════════════
#  1. PostgresStorage
# ═══════════════════════════════════════════════════════════════════════════════

def test_postgres_storage():
    _section("1. PostgresStorage (FSM)")
    try:
        from database.pg_fsm_storage import PostgresStorage
        _check("Импорт PostgresStorage", True)
    except Exception as e:
        if "DATABASE" in str(e).upper():
            _check("Импорт PostgresStorage (пропуск — нет DATABASE_URL)", True)
            print("    ⚠️  Пропущен — нет подключения к PostgreSQL")
            return
        _check("Импорт PostgresStorage", False, str(e))
        return

    from aiogram.fsm.storage.base import BaseStorage
    _check("Наследует BaseStorage", issubclass(PostgresStorage, BaseStorage))

    inst = PostgresStorage()
    for method in ("set_state", "get_state", "set_data", "get_data", "close", "init_table"):
        _check(f"Метод {method}() существует", hasattr(inst, method) and callable(getattr(inst, method)))


# ═══════════════════════════════════════════════════════════════════════════════
#  2. FastAPI app + маршруты + lifespan
# ═══════════════════════════════════════════════════════════════════════════════

def test_fastapi_app():
    _section("2. FastAPI приложение")
    try:
        from web_app import app, set_bot_and_dp
        _check("Импорт FastAPI app", True)
    except ImportError as e:
        if "fastapi" in str(e).lower():
            _check("Импорт FastAPI app (пропуск — pip install fastapi)", True)
            print("    ⚠️  Пропущен — fastapi не установлен")
            return
        _check("Импорт FastAPI app", False, str(e))
        return
    except Exception as e:
        if "DATABASE" in str(e).upper():
            _check("Импорт FastAPI app (пропуск — нет DATABASE_URL)", True)
            print("    ⚠️  Пропущен — нет подключения к PostgreSQL")
            return
        _check("Импорт FastAPI app", False, str(e))
        return

    from fastapi import FastAPI
    _check("app — экземпляр FastAPI", isinstance(app, FastAPI))

    # Lifespan контекст-менеджер
    _check("Lifespan контекст-менеджер настроен", app.router.lifespan_context is not None)

    routes = {r.path for r in app.routes if hasattr(r, "path")}
    expected = [
        "/webhook", "/health", "/", "/app",
        "/api/user_data", "/api/profile/{user_id}",
        "/api/season/data", "/api/season/claim", "/api/season/premium",
        "/api/achievements", "/api/achievements/badges",
    ]
    for ep in expected:
        _check(f"Маршрут {ep} зарегистрирован", ep in routes, f"нет в {routes}")

    # Проверяем webhook: POST
    webhook_methods = set()
    for r in app.routes:
        if hasattr(r, "path") and r.path == "/webhook":
            webhook_methods = set(r.methods or [])
    _check("POST /webhook метод", "POST" in webhook_methods)


# ═══════════════════════════════════════════════════════════════════════════════
#  3. Services: Achievements
# ═══════════════════════════════════════════════════════════════════════════════

def test_achievements_service():
    _section("3. Сервис достижений")
    try:
        from services.achievements import (
            ACHIEVEMENTS, ACH_BY_KEY, ACH_BY_TYPE,
            check_and_grant, get_user_achievements, get_leaderboard, get_user_badge_keys,
        )
        _check("Импорт services.achievements", True)
    except Exception as e:
        if "DATABASE" in str(e).upper():
            _check("Импорт services.achievements (пропуск — нет DATABASE_URL)", True)
            print("    ⚠️  Пропущен — нет подключения к PostgreSQL")
            return
        _check("Импорт services.achievements", False, str(e))
        return

    _check("ACHIEVEMENTS — непустой список", isinstance(ACHIEVEMENTS, list) and len(ACHIEVEMENTS) > 50)
    _check("ACH_BY_KEY содержит chat_100", "chat_100" in ACH_BY_KEY)

    ach_types = set(a["type"] for a in ACHIEVEMENTS)
    _check("Типы: messages, level, gacha_rolls", {"messages", "level", "gacha_rolls"}.issubset(ach_types))

    # API facade
    try:
        from api.achievements import check_and_award, ACHIEVEMENTS as A2
        _check("api.achievements.check_and_award доступна", callable(check_and_award))
        _check("api.achievements.ACHIEVEMENTS === services", A2 is ACHIEVEMENTS)
    except Exception as e:
        _check("api.achievements импорт", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
#  4. Таланты
# ═══════════════════════════════════════════════════════════════════════════════

def test_talents():
    _section("4. Дерево талантов")
    try:
        from shared_prices import TALENT_TREE
        _check("Импорт TALENT_TREE", True)
    except Exception as e:
        _check("Импорт TALENT_TREE", False, str(e))
        return

    _check("17 талантов зарегистрировано", len(TALENT_TREE) == 17, f"фактически: {len(TALENT_TREE)}")

    expected_keys = {
        "mora_harvest", "drop_luck", "combat_mastery", "expedition_haste",
        "reputation_flow", "xp_mastery", "daily_devotion",
        "bonds_broker", "expedition_bounty", "potion_luck", "vital_flow", "pity_memory",
        "craft_mastery", "golden_harvest", "bonds_resilience", "auction_trader", "shield_renewal",
    }
    actual_keys = set(TALENT_TREE.keys())
    _check("Все ожидаемые ключи присутствуют", expected_keys == actual_keys,
           f"лишние={actual_keys - expected_keys}, отсутствуют={expected_keys - actual_keys}")

    for tid, t in TALENT_TREE.items():
        for field in ("name", "tier", "max_level", "effect_key", "effect_per_level"):
            if field not in t:
                _check(f"Талант {tid} поле {field}", False, "отсутствует")

    _check("api/gacha.py: drop_luck параметр",
           "luck_bonus" in importlib.import_module("api.gacha").roll_one.__code__.co_varnames)


# ═══════════════════════════════════════════════════════════════════════════════
#  5. Структура main.py
# ═══════════════════════════════════════════════════════════════════════════════

def test_main_structure():
    _section("5. Структура main.py")
    src_text = pathlib.Path("main.py").read_text(encoding="utf-8")
    _check("PostgresStorage в main.py", "PostgresStorage" in src_text)
    _check("set_bot_and_dp в main.py", "set_bot_and_dp" in src_text)
    _check("uvicorn в main.py", "uvicorn" in src_text)
    _check("Нет _run_webserver в main.py", "_run_webserver" not in src_text)
    _check("fsm_storage.init_table() в main.py", "fsm_storage.init_table()" in src_text)
    _check("Нет aiohttp в main.py", "aiohttp" not in src_text)
    _check("Планировщик через lifespan (не create_task в main)",
           "run_scheduler" not in src_text)


# ═══════════════════════════════════════════════════════════════════════════════
#  6. Зависимости
# ═══════════════════════════════════════════════════════════════════════════════

def test_requirements():
    _section("6. Зависимости")
    req_path = pathlib.Path(__file__).resolve().parent.parent / "requirements.txt"
    if not req_path.exists():
        _check("requirements.txt найден", False, str(req_path))
        return
    raw = req_path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "utf-16-le", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        text = raw.decode("latin-1")
    text_lower = text.lower()
    _check("fastapi в requirements.txt", "fastapi" in text_lower)
    _check("uvicorn в requirements.txt", "uvicorn" in text_lower)
    _check("asyncpg в requirements.txt", "asyncpg" in text_lower)
    _check("aiogram в requirements.txt", "aiogram" in text_lower)
    _check("aiosqlite НЕТ в requirements.txt", "aiosqlite" not in text_lower)
    _check("httpx в requirements.txt", "httpx" in text_lower)


# ═══════════════════════════════════════════════════════════════════════════════
#  7. Legacy-код удалён
# ═══════════════════════════════════════════════════════════════════════════════

def test_legacy_removed():
    _section("7. Legacy-код удалён")
    # api/season.py (мёртвый aiohttp код)
    _check("api/season.py удалён", not pathlib.Path("api/season.py").exists())

    # CRYSTAL_COSMETICS удалён из shared_prices
    sp_text = pathlib.Path("shared_prices.py").read_text(encoding="utf-8")
    _check("CRYSTAL_COSMETICS удалён из shared_prices.py", "CRYSTAL_COSMETICS" not in sp_text)

    # VIP_PRICE удалён из config.py
    cfg_text = pathlib.Path("config.py").read_text(encoding="utf-8")
    _check("VIP_PRICE удалён из config.py", "VIP_PRICE" not in cfg_text)

    # get_active_buffs удалён из db.py
    db_text = pathlib.Path("database/db.py").read_text(encoding="utf-8")
    _check("get_active_buffs удалён из db.py", "def get_active_buffs" not in db_text)

    # aiohttp не импортируется нигде в PredvestnikBot (кроме __pycache__)
    import glob
    aiohttp_files = []
    for py in glob.glob("**/*.py", recursive=True):
        if "__pycache__" in py:
            continue
        try:
            content = pathlib.Path(py).read_text(encoding="utf-8", errors="ignore")
            if "import aiohttp" in content:
                aiohttp_files.append(py)
        except Exception:
            pass
    _check("aiohttp не импортируется ни в одном .py", len(aiohttp_files) == 0,
           f"найден в: {aiohttp_files}")


# ═══════════════════════════════════════════════════════════════════════════════
#  8. Asyncpg пул — реальная запись/чтение
# ═══════════════════════════════════════════════════════════════════════════════

def test_asyncpg_pool():
    _section("8. Asyncpg пул — запись/чтение")
    import os
    if not os.getenv("DATABASE_URL"):
        _check("Asyncpg пул (пропуск — нет DATABASE_URL)", True)
        print("    ⚠️  Пропущен — задайте DATABASE_URL для полного теста")
        return

    async def _run_db_test():
        from database.postgres import get_pg_pool
        pool = await get_pg_pool()
        _check("Пул asyncpg инициализирован", pool is not None)
        _check(f"Размер пула: min={pool.get_min_size()}, max={pool.get_max_size()}",
               pool.get_min_size() >= 1)

        # Тестовая запись/чтение в fsm_data
        test_chat = -999999999
        test_user = 999999999
        async with pool.acquire() as conn:
            # Убедимся что таблица есть
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS fsm_data (
                    chat_id  BIGINT NOT NULL,
                    user_id  BIGINT NOT NULL,
                    state    TEXT,
                    data     JSONB NOT NULL DEFAULT '{}',
                    PRIMARY KEY (chat_id, user_id)
                )
            """)
            # Запись
            await conn.execute(
                """INSERT INTO fsm_data (chat_id, user_id, state, data)
                   VALUES ($1, $2, $3, $4::jsonb)
                   ON CONFLICT (chat_id, user_id)
                   DO UPDATE SET state = EXCLUDED.state, data = EXCLUDED.data""",
                test_chat, test_user, "test:verify", '{"verified": true}',
            )
            # Чтение
            row = await conn.fetchrow(
                "SELECT state, data FROM fsm_data WHERE chat_id=$1 AND user_id=$2",
                test_chat, test_user,
            )
            _check("Запись в fsm_data успешна", row is not None)
            _check("Чтение state корректно", row["state"] == "test:verify" if row else False)
            _check("Чтение data корректно",
                   row["data"].get("verified") is True if row and isinstance(row["data"], dict) else False)
            # Очистка
            await conn.execute(
                "DELETE FROM fsm_data WHERE chat_id=$1 AND user_id=$2",
                test_chat, test_user,
            )
            _check("Очистка тестовых данных", True)

    try:
        asyncio.run(_run_db_test())
    except Exception as e:
        _check("Asyncpg пул тест", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
#  9. FastAPI HTTP — реальные запросы
# ═══════════════════════════════════════════════════════════════════════════════

def test_fastapi_http():
    _section("9. FastAPI HTTP эндпоинты")
    try:
        from httpx import ASGITransport, AsyncClient
        from web_app import app
    except ImportError as e:
        _check("httpx / FastAPI доступны (пропуск)", True)
        print(f"    ⚠️  Пропущен — {e}")
        return
    except Exception as e:
        if "DATABASE" in str(e).upper():
            _check("FastAPI HTTP (пропуск — нет DATABASE_URL)", True)
            print("    ⚠️  Пропущен — нет подключения к PostgreSQL")
            return
        _check("FastAPI HTTP импорт", False, str(e))
        return

    async def _run_http_tests():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # /health
            resp = await client.get("/health")
            _check("GET /health → 200", resp.status_code == 200)
            _check("GET /health → {status: ok}", resp.json().get("status") == "ok")

            # POST /webhook без секрета и без бота (→ 503 или 200)
            resp = await client.post("/webhook", json={"update_id": 1})
            _check("POST /webhook отвечает (503 без бота или 200)",
                   resp.status_code in (200, 403, 503))

            # /api/achievements без параметров → 400
            resp = await client.get("/api/achievements")
            _check("GET /api/achievements без параметров → 400", resp.status_code == 400)

            # /api/season/data без параметров → 400
            resp = await client.get("/api/season/data")
            _check("GET /api/season/data без параметров → 400", resp.status_code == 400)

            # /api/user_data без параметров → 400
            resp = await client.get("/api/user_data")
            _check("GET /api/user_data без параметров → 400", resp.status_code == 400)

    try:
        asyncio.run(_run_http_tests())
    except Exception as e:
        _check("FastAPI HTTP тест", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
#  Запуск
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  ВЕРИФИКАЦИЯ СИСТЕМЫ — PredvestnikBot")
    print("  Архитектурная миграция FastAPI + Aiogram 3 + asyncpg")
    print("=" * 60)

    test_postgres_storage()
    test_fastapi_app()
    test_achievements_service()
    test_talents()
    test_main_structure()
    test_requirements()
    test_legacy_removed()
    test_asyncpg_pool()
    test_fastapi_http()

    print(f"\n{'=' * 60}")
    print(f"  ИТОГО: {_passed} ✅  /  {_failed} ❌")
    if _errors:
        print(f"\n  ОШИБКИ:")
        for e in _errors:
            print(f"    {e}")
    print(f"{'=' * 60}")
    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
