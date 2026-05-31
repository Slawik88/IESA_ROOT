import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    developer_id: int
    timezone_offset: str  # PostgreSQL INTERVAL modifier, e.g. "+3 hours"


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Required env var '{key}' is not set. Check {BASE_DIR / '.env'}"
        )
    return value


config = Config(
    bot_token=_require("BOT_TOKEN"),
    database_url=_require("DATABASE_URL"),
    developer_id=int(os.getenv("DEVELOPER_ID", "0")),
    timezone_offset=os.getenv("TIMEZONE_OFFSET", "+3 hours"),
)
