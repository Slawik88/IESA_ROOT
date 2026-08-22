"""Contract test for read-only quests and earned-only legacy BP claims."""
import ast
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def function_node(path: str, name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(read(path), filename=path)
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing {path}:{name}")


def call_names(node: ast.AST) -> set[str]:
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            fn = child.func
            if isinstance(fn, ast.Name):
                names.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                names.add(fn.attr)
    return names


quests = read("services/quests.py")
assert "add_balance" not in quests
assert "upsert_quest" not in quests
assert "increment_quest_progress" not in quests
assert "_bp_add_xp" not in quests
assert not call_names(function_node("services/quests.py", "increment_metric"))

bp = read("services/battle_pass.py")
for fn in ("add_xp", "buy_next_level"):
    assert not call_names(function_node("services/battle_pass.py", fn)), f"{fn} still mutates state"
assert "INSERT INTO battle_pass_progress" not in bp
claim = ast.get_source_segment(bp, function_node("services/battle_pass.py", "claim_reward")) or ""
assert 'progress.get("exists")' in claim
assert "if not row:" in claim and "Награда не выдана" in claim
assert 'source="battle_pass_reward"' in claim, "earned legacy claims must remain payable"

quest_api = read("FastAPI/routers/quests.py")
bp_api = read("FastAPI/routers/battle_pass.py")
quest_ui = read("FastAPI/static/app.04.js")
bp_ui = read("FastAPI/static/app.03.js")
assert '"retired": True' in quest_api and '"retired": True' in bp_api
assert "Архив заданий" in quest_ui
assert "Архив сезона" in bp_ui
assert "r.retired?null:r.bonus" in quest_ui
assert "!d.paid_track_open&&!d.retired" in bp_ui
assert "d.buy_next&&!d.frozen" in bp_ui  # old renderer remains guarded; API always sends null

print("OK: quests are read-only; BP cannot progress/buy; earned claims remain guarded")
