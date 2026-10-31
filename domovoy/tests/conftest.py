"""
tests/conftest.py — тестовое окружение: отдельный sqlite-файл на сессию.

env для БД задаётся ДО импорта infrastructure.db (db читает конфиг при импорте).
"""
import os
import sys
import tempfile
from pathlib import Path

# Запуск: `cd domovoy && python -m pytest tests` — корень проекта в пути.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TMP_DIR = tempfile.mkdtemp(prefix="domovoy-test-")
os.environ["DOMOVOY_DATABASE_URL"] = f"sqlite://{_TMP_DIR}\\test.db"
os.environ.setdefault("DOMOVOY_BOT_TOKEN", "test:token")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from infrastructure.db import db  # noqa: E402
from infrastructure.schema import ensure_schema  # noqa: E402


@pytest_asyncio.fixture
async def database():
    await db.connect()
    await ensure_schema()
    yield db
    await db.close()


@pytest_asyncio.fixture(autouse=True)
async def seed_users(database):
    """Тестовые пользователи: FK требует существующих жильцов."""
    from infrastructure.repositories import users as users_repo

    for tg_id, name in ((100, "Владелец"), (200, "Напарник"), (300, "Незнакомец")):
        await users_repo.upsert_user(tg_id, name, None)
    yield


@pytest.fixture
def today() -> str:
    from datetime import date

    return date.today().strftime("%Y-%m-%d")
