"""
bot/backup.py
SQLite ↔ DigitalOcean Spaces backup/restore.

Activated only when SPACES_KEY, SPACES_SECRET, SPACES_BUCKET are set.
Falls back silently (local DB only) when credentials are absent — safe for dev.
"""
import asyncio
import os
from pathlib import Path

from loguru import logger

_SPACES_KEY = os.getenv("SPACES_KEY", "")
_SPACES_SECRET = os.getenv("SPACES_SECRET", "")
_SPACES_BUCKET = os.getenv("SPACES_BUCKET", "")
_SPACES_ENDPOINT = os.getenv("SPACES_ENDPOINT", "").strip()
_REMOTE_KEY = "predvestnik-bot/db.sqlite3"

BACKUP_ENABLED = bool(_SPACES_KEY and _SPACES_SECRET and _SPACES_BUCKET and _SPACES_ENDPOINT)


def _client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=_SPACES_ENDPOINT,
        aws_access_key_id=_SPACES_KEY,
        aws_secret_access_key=_SPACES_SECRET,
    )


def restore_db(db_path: str) -> bool:
    """Download db from Spaces to db_path. Returns True if file was found."""
    if not BACKUP_ENABLED:
        return False
    try:
        client = _client()
        client.download_file(_SPACES_BUCKET, _REMOTE_KEY, db_path)
        size_kb = Path(db_path).stat().st_size // 1024
        logger.info(f"✅ БД восстановлена из Spaces ({size_kb} KB)")
        return True
    except Exception as e:
        err = str(e)
        if "404" in err or "NoSuchKey" in err or "Not Found" in err:
            logger.info("ℹ️ БД в Spaces не найдена — создаём новую.")
        else:
            logger.warning(f"⚠️ Ошибка загрузки БД из Spaces: {e}")
        return False


def save_db(db_path: str) -> bool:
    """Upload db_path to Spaces. Returns True on success."""
    if not BACKUP_ENABLED:
        return False
    if not Path(db_path).exists():
        logger.warning("⚠️ Бэкап пропущен — файл БД не найден.")
        return False
    try:
        size_kb = Path(db_path).stat().st_size // 1024
        _client().upload_file(db_path, _SPACES_BUCKET, _REMOTE_KEY)
        logger.info(f"✅ БД сохранена в Spaces ({size_kb} KB)")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения БД в Spaces: {e}")
        return False


async def periodic_backup(db_path: str, interval_seconds: int = 1800):
    """Background task: upload DB to Spaces every `interval_seconds`."""
    if not BACKUP_ENABLED:
        return
    logger.info(f"🔄 Автобэкап БД запущен (каждые {interval_seconds // 60} мин).")
    while True:
        await asyncio.sleep(interval_seconds)
        await asyncio.get_event_loop().run_in_executor(None, save_db, db_path)
