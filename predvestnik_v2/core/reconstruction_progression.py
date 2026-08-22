"""Pure progression and branch content for Reconstruction starter units."""
from __future__ import annotations

from typing import Any, Final, Mapping

from core.economy_v3 import UNIT_BRANCH_LEVELS, UNIT_LEVEL_CAP, unit_level_progress
from core.reconstruction import STARTER_UNITS


PROGRESSION_VERSION: Final = "reconstruction-units-v1"
IMPLEMENTED_BRANCH_LEVELS: Final = (5,)

# A branch must change a player decision and pay for that advantage.  These are
# content contracts, not passive +X% stat nodes.  The combat/UI implementation
# consumes ``mechanic`` only after its mastery challenge is proven.
UNIT_BRANCHES: Final[dict[str, dict[int, tuple[dict[str, Any], ...]]]] = {
    "r_oath_bell": {
        5: (
            {
                "id": "bell_broken_vow",
                "name": "Нарушенная клятва",
                "decision": "После первой ошибки решить: сохранить половину Импульса или отпустить заряд.",
                "mechanic": {"kind": "mistake_recovery_choice", "retain_charge_ratio": 0.5},
                "tradeoff": "Сохранение заряда сужает следующее окно сигнала на 0,18 с.",
                "counter_scenario": "На быстрой волне безопаснее добровольно потерять заряд.",
                "mobile_control": "Одна компактная кнопка решения появляется рядом с Импульсом.",
                "mastery_challenge": "bell_recover_three_clean",
                "telemetry": ("recovery_offered", "recovery_kept", "next_signal_result"),
            },
            {
                "id": "bell_silent_release",
                "name": "Безмолвный разряд",
                "decision": "При полном Импульсе самому выбрать один из следующих двух сигналов для Разряда.",
                "mechanic": {"kind": "armed_manual_discharge", "choice_signals": 2},
                "tradeoff": "Если не выбрать вовремя, половина Импульса исчезает без урона.",
                "counter_scenario": "На хаотичной волне автоматический Разряд надёжнее ручного окна.",
                "mobile_control": "Импульс становится одной кнопкой; отдельная панель не нужна.",
                "mastery_challenge": "bell_hold_and_release",
                "telemetry": ("discharge_armed", "discharge_released", "discharge_expired"),
            },
        ),
    },
    "r_red_seam": {
        5: (
            {
                "id": "seam_cross_stitch",
                "name": "Перекрёстный шов",
                "decision": "Золотое попадание запоминает позицию; разорвать шов нужно точным знаком в другой позиции.",
                "mechanic": {"kind": "stored_seam", "requires_different_slot": True},
                "tradeoff": "Повтор исходной позиции снимает шов без дополнительного урона.",
                "counter_scenario": "Предсказуемые повторяющиеся позиции делают ветку рискованной.",
                "mobile_control": "Запомненная позиция отмечается тонкой нитью, без новой кнопки.",
                "mastery_challenge": "seam_break_three_positions",
                "telemetry": ("seam_stored", "seam_broken", "seam_wasted"),
            },
            {
                "id": "seam_forbidden_repeat",
                "name": "Запретный стежок",
                "decision": "После точного знака добровольно запретить повтор той же позиции до следующего успеха.",
                "mechanic": {"kind": "forbidden_last_slot", "reward": "combo_step"},
                "tradeoff": "Если правильный ответ пришёл в запрещённую позицию, серию приходится отпустить.",
                "counter_scenario": "Игрок выбирает стабильность базовой Швеи против высокого потолка серии.",
                "mobile_control": "Запрещённая руна приглушена, но остаётся читаемой и доступной.",
                "mastery_challenge": "seam_no_repeat_chain",
                "telemetry": ("slot_forbidden", "forbidden_respected", "forced_break"),
            },
        ),
    },
    "r_tide_cartographer": {
        5: (
            {
                "id": "tide_hidden_swap",
                "name": "Сдвиг течения",
                "decision": "Один раз за волну перемешать позиции уже открытых рун, не меняя правильный знак.",
                "mechanic": {"kind": "reroll_option_positions", "uses_per_wave": 1},
                "tradeoff": "Срок сигнала не продлевается, а после сдвига таймер скрывается.",
                "counter_scenario": "Переносит ответ под удобный палец, но съедает время и может ухудшить раскладку.",
                "mobile_control": "Короткое нажатие по ядру сдвигает руны; отдельная панель не появляется.",
                "mastery_challenge": "tide_swap_without_miss",
                "telemetry": ("swap_started", "swap_committed", "swapped_signal_result"),
            },
            {
                "id": "tide_early_chart",
                "name": "Ранняя карта",
                "decision": "До открытия сигнала увидеть его семейство и заранее выбрать темп ответа.",
                "mechanic": {"kind": "early_family_preview", "lead_ms": 420},
                "tradeoff": "Пока подсказка открыта, пассивный урон Картографа останавливается.",
                "counter_scenario": "На простой волне информация стоит дороже потерянного темпа.",
                "mobile_control": "Семейство показано одним знаком над ядром, без текста и модалки.",
                "mastery_challenge": "tide_forecast_three_families",
                "telemetry": ("family_previewed", "preview_followed", "preview_ignored"),
            },
        ),
    },
}


def branch_by_id(branch_id: str) -> tuple[str, int, Mapping[str, Any]] | None:
    for unit_id, milestones in UNIT_BRANCHES.items():
        for level, branches in milestones.items():
            for branch in branches:
                if branch["id"] == branch_id:
                    return unit_id, level, branch
    return None


def unit_progress_view(
    unit_id: str,
    total_xp: int,
    branch_choices: Mapping[str | int, str] | None = None,
) -> dict[str, Any]:
    if unit_id not in STARTER_UNITS:
        raise ValueError("Unknown Reconstruction unit.")
    progress = unit_level_progress(total_xp)
    normalized: dict[str, str] = {}
    for raw_level, branch_id in (branch_choices or {}).items():
        try:
            level = int(raw_level)
        except (TypeError, ValueError) as exc:
            raise ValueError("Branch milestone must be an integer level.") from exc
        found = branch_by_id(str(branch_id))
        if not found or found[0] != unit_id or found[1] != level:
            raise ValueError("Branch choice does not belong to this unit milestone.")
        if level > progress.level:
            raise ValueError("Branch choice is locked by unit level.")
        normalized[str(level)] = str(branch_id)
    pending = [
        level for level in IMPLEMENTED_BRANCH_LEVELS
        if level <= progress.level and str(level) not in normalized
    ]
    next_branch = pending[0] if pending else next(
        (level for level in UNIT_BRANCH_LEVELS if level > progress.level), None
    )
    return {
        "unit_id": unit_id,
        "progression_version": PROGRESSION_VERSION,
        "level": progress.level,
        "total_xp": progress.total_xp,
        "xp_in_level": progress.xp_in_level,
        "xp_to_next": progress.xp_to_next,
        "mastery_after_cap": progress.mastery_after_cap,
        "branch_choices": normalized,
        "next_branch_level": next_branch,
    }


def public_progression_manifest() -> dict[str, Any]:
    return {
        "version": PROGRESSION_VERSION,
        "level_cap": UNIT_LEVEL_CAP,
        "branch_levels": list(UNIT_BRANCH_LEVELS),
        "implemented_branch_levels": list(IMPLEMENTED_BRANCH_LEVELS),
        "paid_xp_allowed": False,
        "ranked_normalization": True,
        "branches": {
            unit_id: {
                str(level): [dict(branch) for branch in branches]
                for level, branches in milestones.items()
            }
            for unit_id, milestones in UNIT_BRANCHES.items()
        },
    }


def validate_progression_content() -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    required = {
        "id", "name", "decision", "mechanic", "tradeoff", "counter_scenario",
        "mobile_control", "mastery_challenge", "telemetry",
    }
    for unit_id in STARTER_UNITS:
        milestones = UNIT_BRANCHES.get(unit_id, {})
        for level in IMPLEMENTED_BRANCH_LEVELS:
            branches = milestones.get(level, ())
            if len(branches) != 2:
                errors.append(f"{unit_id}@{level}: expected exactly two branches")
            for branch in branches:
                missing = required - branch.keys()
                if missing:
                    errors.append(f"{unit_id}@{level}: missing {sorted(missing)}")
                branch_id = str(branch.get("id") or "")
                if branch_id in ids:
                    errors.append(f"duplicate branch id {branch_id}")
                ids.add(branch_id)
                if not branch.get("tradeoff") or not branch.get("counter_scenario"):
                    errors.append(f"{branch_id}: branch has no real cost/counterplay")
                if len(tuple(branch.get("telemetry") or ())) < 3:
                    errors.append(f"{branch_id}: telemetry cannot compare the decision")
    return errors


_CONTENT_ERRORS = validate_progression_content()
if _CONTENT_ERRORS:
    raise RuntimeError("Invalid Reconstruction progression: " + "; ".join(_CONTENT_ERRORS))
