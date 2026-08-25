"""Keep the active game documents tied to executable, current contracts."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import companions_v3, economy_v3


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def main() -> None:
    bible = _text("GAME_BIBLE.md")
    reconstruction = _text("GAME_RECONSTRUCTION_3_0.md")
    agents = (ROOT.parent / "AGENTS.md").read_text(encoding="utf-8").strip()
    expected_loader = "\n\n".join((
        "@predvestnik_v2/BASE_PROMPT.md",
        "@predvestnik_v2/AUTONOMOUS_MODE.md",
        "@predvestnik_v2/AUTONOMOUS_AGENT_POLICY.md",
    ))

    assert agents == expected_loader
    assert economy_v3.SETTLEMENT_MODE == "shadow_only"
    assert economy_v3.REAL_REWARDS_ENABLED is False
    assert economy_v3.UNIT_LEVEL_CAP_XP == 36_096
    assert economy_v3.ZARNIKI_TO_MORA_RATE == 150
    assert companions_v3.EXPEDITION_OPTIONS[12]["mora"] == 285
    for marker in (
        "`SETTLEMENT_MODE = shadow_only`",
        "36 096 XP",
        "1 Зарник = 150",
        "12 ч → 285",
        "35–60%",
        "`game_reconstruction_v1`",
    ):
        assert marker in bible, marker
    for marker in ("×0,78", "+220 мс", "−100 мс", "shadow_only"):
        assert marker in reconstruction, marker

    retired = (
        "GDD_REBUILD_PLAN.md", "BATTLE_REWORK_CONCEPT.md", "COMBAT_AUDIT.md",
        "PETS_REDESIGN_CONCEPT.md", "NOT_IMPLEMENTED.md", "IMPLEMENTATION_BLOCKS.md",
    )
    for name in retired:
        assert not (ROOT / name).exists(), name
    for name in (
        "GAME_BIBLE.md", "GAME_RECONSTRUCTION_3_0.md", "BATTLE_VFX_CONCEPT.md",
        "AUTONOMOUS_MODE.md", "AUTONOMOUS_AGENT_POLICY.md",
    ):
        assert (ROOT / name).is_file(), name
    print("OK: live game documentation matches current contracts and loader")


if __name__ == "__main__":
    main()
