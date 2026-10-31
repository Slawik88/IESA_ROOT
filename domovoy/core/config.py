"""
core/config.py
Конфигурация «Домового» из окружения. Читается один раз при импорте.

Прогрессcwd при запуске — каталог domovoy/ (python -m bot), .env лежит рядом.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")

# Каталог для sqlite и рантайм-данных; создаётся сразу, чтобы БД могла открыться.
_DATA_DIR = _BASE_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

BOT_TOKEN = os.environ.get("DOMOVOY_BOT_TOKEN", "").strip()

def database_url() -> str:
    """Строка подключения: PostgreSQL, а без неё — sqlite в data/ (разработка)."""
    return (os.environ.get("DOMOVOY_DATABASE_URL", "").strip()
            or f"sqlite://{_DATA_DIR / 'domovoy.db'}")

def superadmin_tg_ids() -> frozenset[int]:
    raw = os.environ.get("DOMOVOY_SUPERADMIN_TG_IDS", "")
    ids = {int(part.strip()) for part in raw.split(",") if part.strip().isdigit()}
    return frozenset(ids)

def is_superadmin(tg_id: int) -> bool:
    return tg_id in superadmin_tg_ids()

LOG_LEVEL = os.environ.get("DOMOVOY_LOG_LEVEL", "INFO").strip().upper()
