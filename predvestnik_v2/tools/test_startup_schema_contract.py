"""Production runs FastAPI co-hosted with the bot and lifespan="off" (bot/__main__.py): the ensure_tables list in FastAPI/main.py lifespan does NOT run there.
Whatever the first profile request reads must therefore be created by the bot's own start-up step, otherwise the first player after a release gets a
"relation ... does not exist" (it did: skins_v3_equipped, release of 2026-10-08)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
boot = (ROOT / "bot/__main__.py").read_text(encoding="utf-8")
profile = (ROOT / "FastAPI/routers/profile.py").read_text(encoding="utf-8")

assert re.search(r'lifespan="off"', boot), "the premise of this test: the bot hosts FastAPI without lifespan"
startup = boot.split("async with pool.acquire() as _startup_connection:", 1)[1].split('logger.info("✅ База данных готова!")', 1)[0]
for repo in ("skins_v3", "marks_v1", "presence_v1", "vip_v2", "public_profiles_v1", "achievements_v1"):
    assert re.search(rf"await {repo}_repo\.ensure_tables\(_startup_db\)", startup), f"{repo} tables must be created by the bot start-up step"

# The profile read of the worn look creates the tables itself before reading (belt and braces for a stand or a database that missed the start-up step).
own_look = profile.split("async def _own_look(", 1)[1].split("async def ", 1)[0]
assert "skins_v3_repo.ensure_tables(db)" in own_look and own_look.index("ensure_tables") < own_look.index("own_look(db")
print("OK: start-up creates the tables the first profile request reads")
