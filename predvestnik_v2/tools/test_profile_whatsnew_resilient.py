"""Guard прод-инцидента 2026-07-23: /profile/me отдавал 500 «column
u.whatsnew_seen_id does not exist».

Первопричина: на проде FastAPI стартует с lifespan="off" (bot/__main__.py), поэтому
users.ensure_account_columns из веб-lifespan НЕ выполняется — новые колонки users
создаёт ТОЛЬКО bot init_db, а combat_tutorial_done/whatsnew_seen_id туда не добавили.
Плюс основной SELECT профиля жёстко ссылался на колонку → падал весь запрос.

Тест сторожит оба фикса статически (без БД):
1. основной SELECT профиля НЕ содержит whatsnew_seen_id (иначе снова 500 без колонки);
2. колонка достаётся отдельным запросом (мягкая деградация в None);
3. init_db создаёт ОБЕ новые колонки (единственное место на проде)."""
import re
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent

src = (ROOT / "FastAPI" / "routers" / "profile.py").read_text(encoding="utf-8")

main_q = re.search(r'"SELECT u\.user_tg_id.*?WHERE u\.user_tg_id = \?"', src, re.S)
assert main_q, "не нашёл основной SELECT профиля в profile.py"
assert "whatsnew_seen_id" not in main_q.group(0), (
    "whatsnew_seen_id вернулся в ОСНОВНОЙ SELECT профиля — отсутствие колонки снова "
    "уронит весь /profile/me в 500")

assert "SELECT whatsnew_seen_id FROM users" in src, (
    "нет отдельного запроса whatsnew_seen_id — колонка должна доставаться отдельно "
    "с try/except, а не в основном запросе")

db_src = (ROOT / "bot" / "core" / "database.py").read_text(encoding="utf-8")
for col in ("combat_tutorial_done", "whatsnew_seen_id"):
    assert f"ADD COLUMN IF NOT EXISTS {col}" in db_src, (
        f"init_db не создаёт колонку {col} — на проде её никто не создаст "
        f"(FastAPI lifespan='off', ensure_account_columns не выполняется)")

print("OK: whatsnew_seen_id вне основного SELECT + отдельный запрос; "
      "init_db создаёт combat_tutorial_done и whatsnew_seen_id")
