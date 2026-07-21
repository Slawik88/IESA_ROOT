"""Онбординг боя (2026-07-21): режим скриптованного «Первого боя».

Проверяет: синтетический отряд/враги, флаг tutorial в public_state, анти-фейл
(союзник не падает ниже 1 HP), детерминизм поля по фикс-сиду и что бой реально
выигрывается за разумное число раундов при символическом уроне врага."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from services import battle3 as b3
from core.constants import GRID_W, B4_TUTORIAL_SEED, B4_ATK_AP

CTX = {"tutorial": True, "seed": B4_TUTORIAL_SEED}


def _fresh():
    return b3.new_battle_state(b3.tutorial_squad(), b3.tutorial_enemy_squad(), "tutorial", CTX)


# 1. Структура + флаг
st = _fresh()
pub = b3.public_state(st, 1)
assert pub["mode"] == "tutorial" and pub["tutorial"] is True, "флаг tutorial в public_state"
assert len(st["ally"]["units"]) == 2, "туториал-отряд из 2"
assert len(st["enemy"]["units"]) == 2, "2 туториал-врага"
assert {u["uid"] for u in st["ally"]["units"]} == {"u_salamandra", "u_ice_golem"}, "состав отряда"

# 2. Анти-фейл: огромный урон по союзнику → hp=1, но жив
ev = []
b3._apply_damage(st, "enemy", 0, "ally", 0, 999999, ev)
a0 = st["ally"]["units"][0]
assert a0["hp"] == 1 and a0["alive"], "анти-фейл: союзник не падает ниже 1 HP"

# 3. Детерминизм поля по фикс-сиду
assert _fresh()["grid"] == _fresh()["grid"], "grid туториала недетерминирован"

# 4. Прогон до победы: ставим бойцов в дальность, чистим полосы, бьём каждый ход
st = _fresh()
st["grid"][2] = [0] * GRID_W
st["grid"][3] = [0] * GRID_W
st["ally"]["units"][0]["pos"] = {"x": 4, "y": 2}   # 🦎 dd, дальность 2
st["enemy"]["units"][0]["pos"] = {"x": 6, "y": 2}
st["ally"]["units"][1]["pos"] = {"x": 5, "y": 3}   # 🧊 tank, дальность 1
st["enemy"]["units"][1]["pos"] = {"x": 6, "y": 3}


def _enemy_in_range(state, ai):
    a = state["ally"]["units"][ai]
    rng = b3._atk_range(a)
    for ti, e in enumerate(state["enemy"]["units"]):
        if not e["alive"]:
            continue
        if b3.grid_mod.chebyshev(b3._pos(a), b3._pos(e)) <= rng \
                and b3.grid_mod.line_of_sight(state["grid"], b3._pos(a), b3._pos(e)):
            return ti
    return None


rounds = 0
for rounds in range(1, 13):
    for ai, a in enumerate(st["ally"]["units"]):
        while a["alive"] and a["ap"] >= B4_ATK_AP and st["status"] == "active":
            ti = _enemy_in_range(st, ai)
            if ti is None:
                break
            res = b3.apply_action(st, {"type": "attack", "unit_i": ai, "target_i": ti})
            if not res.get("ok") or st.get("pending"):
                break
        if st["status"] != "active":
            break
    if st["status"] != "active":
        break
    b3.apply_action(st, {"type": "end_turn"})
    for a in st["ally"]["units"]:
        assert a["hp"] >= 1, "союзник упал в туториале (анти-фейл не сработал)"

assert st["status"] == "won", f"туториал не выигран за 12 раундов (статус={st['status']})"
print(f"battle_tutorial: отряд+флаг+анти-фейл+детерминизм+победа за {rounds} р.  OK")
