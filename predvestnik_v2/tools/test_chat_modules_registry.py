#!/usr/bin/env python3
"""Registry contract for chat modules: DDL, defaults, catalog, settings writes.

Держит реестр core.chat_modules единственным источником правды: колонки в БД,
дефолты в get_chat_settings, whitelist записи и «Функции чата» в UI.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "123456:offline-modules-test")
os.environ.setdefault("BOT_USERNAME", "offline_modules_test")
os.environ.setdefault("MINIAPP_URL", "https://preprod.invalid/predvestnik")
os.environ.setdefault("DATABASE_URL", "postgresql://offline@127.0.0.1:55432/offline")

ROOT = Path(__file__).resolve().parents[1]

from core.chat_modules import (
    CHAT_MODULES,
    CHAT_MODULE_GROUPS,
    CHAT_MODULE_KEYS,
    MASTER_CHAT_MODULE,
    chat_module_default,
    chat_modules_in_group,
)
from infrastructure.repositories import chat_module_audit


class FakeCursor:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        return self.row


class FakeExec:
    """aiosqlite-like handle: годится и для `await db.execute(...)`, и для `async with`."""

    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def __await__(self):
        async def _result():
            return self._cursor

        return _result().__await__()

    async def __aenter__(self):
        return self._cursor

    async def __aexit__(self, *_args):
        return None


class FakeDB:
    def __init__(self, row=None):
        self.row = row
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql, _args=()):
        self.sql.append(sql)
        return FakeExec(FakeCursor(self.row))

    async def commit(self):
        self.commits += 1


async def run() -> None:
    # 1. Реестр: ключи, группы, дефолты, мастер-стоп.
    assert CHAT_MODULE_KEYS == frozenset(CHAT_MODULES)
    assert MASTER_CHAT_MODULE in CHAT_MODULES
    assert chat_module_default(MASTER_CHAT_MODULE) is True
    for key, spec in CHAT_MODULES.items():
        assert key.startswith("module_"), key
        assert spec["group"] in CHAT_MODULE_GROUPS, key
        for field in ("icon", "name", "description"):
            assert isinstance(spec[field], str) and spec[field].strip(), (key, field)
        assert isinstance(spec["default_enabled"], bool), key
        assert chat_module_default(key) is spec["default_enabled"]
    # Каждая группа непустая, и группы покрывают реестр без остатка.
    grouped = set()
    for group in CHAT_MODULE_GROUPS:
        keys = chat_modules_in_group(group)
        assert keys, group
        grouped |= set(keys)
    assert grouped == set(CHAT_MODULES)

    # 2. Миграция: один ALTER на модуль, все ключи покрыты.
    db = FakeDB()
    await chat_module_audit.ensure_chat_module_columns(db)
    assert len(db.sql) == len(CHAT_MODULES)
    for key in CHAT_MODULES:
        assert any(f"ADD COLUMN IF NOT EXISTS {key} " in sql for sql in db.sql), key
    schema_src = (
        ROOT / "infrastructure" / "repositories" / "chat_module_audit.py"
    ).read_text(encoding="utf-8")
    assert "await ensure_chat_module_columns(db)" in schema_src

    # 3. Каталог: порядок = реестр, у каждого пункта раскрыта группа.
    catalog = chat_module_audit.catalog()
    assert [item["key"] for item in catalog] == list(CHAT_MODULES)
    for item in catalog:
        assert item["group_name"].strip() and item["group_icon"].strip(), item["key"]

    # 4. get_chat_settings: дефолты новой строки chat_settings = реестр.
    from infrastructure.repositories.moderation import (
        get_chat_settings, update_chat_settings,
    )

    settings = await get_chat_settings(FakeDB(row=None), -100700)
    for key in CHAT_MODULES:
        assert settings[key] == int(chat_module_default(key)), key

    # 5. Запись: whitelist update_chat_settings расширен всеми ключами реестра.
    for key in CHAT_MODULES:
        test_db = FakeDB()
        await update_chat_settings(test_db, -100700, **{key: 0})
        assert test_db.commits == 1, key
    try:
        await update_chat_settings(FakeDB(), -100700, hacked_column=1)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown chat setting must raise ValueError")

    # 6. Проводка по поверхностям: бот, middleware, веб, mini app.
    mw_src = (
        ROOT / "bot" / "middlewares" / "module_check_mw.py"
    ).read_text(encoding="utf-8")
    assert "bot_silence_middleware" in mw_src and "_SILENCE_TTL" in mw_src
    main_src = (ROOT / "bot" / "__main__.py").read_text(encoding="utf-8")
    assert "from bot.middlewares.module_check_mw import bot_silence_middleware" in main_src
    assert "dp.update.middleware(bot_silence_middleware)" in main_src
    settings_src = (
        ROOT / "bot" / "handlers" / "chat_settings.py"
    ).read_text(encoding="utf-8")
    assert "bot_silence_invalidate" in settings_src
    ui_src = (
        ROOT / "bot" / "handlers" / "_chat_module_ui.py"
    ).read_text(encoding="utf-8")
    assert "MASTER_CHAT_MODULE" in ui_src and "CHAT_MODULE_GROUPS" in ui_src
    web_src = (ROOT / "FastAPI" / "main.py").read_text(encoding="utf-8")
    assert "ensure_chat_module_columns" in web_src
    assert "(1, 2, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)" in web_src
    admin_src = (ROOT / "FastAPI" / "routers" / "admin.py").read_text(encoding="utf-8")
    assert "create_model(" in admin_src and "sorted(CHAT_MODULE_KEYS)" in admin_src


asyncio.run(run())
print("chat modules registry: contract OK")
