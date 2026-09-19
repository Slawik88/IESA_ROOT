"""Contract test: the retired streak has no runtime middleware or writer."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
startup = (ROOT / "bot/__main__.py").read_text(encoding="utf-8")
handler_source = (ROOT / "bot/handlers/streak.py").read_text(encoding="utf-8")

assert not (ROOT / "bot/middlewares/streak_mw.py").exists()
assert "streak_middleware" not in startup

for marker in ("add_balance", "spend_balance", "spin_token", "UPDATE users"):
    assert marker not in handler_source, f"handler contains retired writer: {marker}"

ui_source = (ROOT / "FastAPI/static/app.02.js").read_text(encoding="utf-8")
for stale_copy in ("Следующая награда", "бот стрик восстановить", "Алмазы из стрика"):
    assert stale_copy not in ui_source, f"UI still promises retired streak reward: {stale_copy}"
assert "число сообщений не усиливает награду" in ui_source
assert "сохранённый рекорд старой системы" in ui_source

print("OK: legacy streak is read-only and has no runtime middleware")
