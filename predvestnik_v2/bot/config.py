# bot/config.py
# Loads all secrets and runtime settings from the .env file.
# Never hardcode tokens or paths here — put them in .env.
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root is two levels above this file (bot/config.py → bot/ → predvestnik_v2/)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str
    developer_id: int
    timezone_offset: str  # SQLite strftime modifier, e.g. "+3 hours"


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            f"Check your .env file at {BASE_DIR / '.env'}"
        )
    return value


config = Config(
    bot_token=_require("BOT_TOKEN"),
    db_path=str(BASE_DIR / os.getenv("DB_PATH", "db.sqlite3")),
    developer_id=int(os.getenv("DEVELOPER_ID", "0")),
    timezone_offset=os.getenv("TIMEZONE_OFFSET", "+3 hours"),
)
