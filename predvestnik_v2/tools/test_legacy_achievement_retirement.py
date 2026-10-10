"""Contract test: legacy achievements are read-only profile history."""
import ast
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent


service = (ROOT / "services/achievements.py").read_text(encoding="utf-8")
tree = ast.parse(service, filename="services/achievements.py")
assert "add_balance" not in service
assert "upsert_achievement" not in service
assert "battle_pass" not in service
for name in ("increment_metric", "backfill_metric"):
    fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    assert not any(isinstance(n, ast.Call) for n in ast.walk(fn)), f"{name} touches runtime state"

api = (ROOT / "FastAPI/routers/achievements.py").read_text(encoding="utf-8")
assert "backfill_metric" not in api
assert '"retired": True' in api
assert '"next_reward": None' in api

ui = (ROOT / "FastAPI/static/app.02.js").read_text(encoding="utf-8")
assert "Крутите гачу" not in ui
assert "Пишите сообщения в чатах с ботом" not in ui
assert "openFeatModal" not in ui and "openAchModal" not in ui and "'/achievements/'" not in ui, "the old achievements screen is gone from the client"

print("OK: Chronicle is separate; legacy history is frozen server-side and the client no longer ships its old screen")
