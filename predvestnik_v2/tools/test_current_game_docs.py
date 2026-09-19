"""Keep the one owner-approved game contract free of retired documents."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    plan_path = ROOT / "docs" / "PROJECT_RECONSTRUCTION_MASTER_PLAN.md"
    plan = plan_path.read_text(encoding="utf-8")
    agents = (ROOT.parent / "AGENTS.md").read_text(encoding="utf-8").strip()

    # The root workspace remains a narrow router; it must not revive old
    # eager-loader documents after the owner explicitly removed them.
    assert "predvestnik_v2/AGENTS.md" in agents
    assert "не загружать автоматически" in agents.lower()
    assert "@predvestnik_v2/BASE_PROMPT.md" not in agents

    # The current scope is deliberately small while the rest of the game is
    # redesigned: only two Mini App games and chat Mafia are active.
    for marker in (
        "Ритм и Сапёр внутри Mini App",
        "«Мафия» как групповая чатовая игра",
        "разрешены только Ритм, Сапёр и чатовая «Мафия»",
        "от 4 до 20",
    ):
        assert marker in plan, marker

    retired = (
        "GDD_REBUILD_PLAN.md", "BATTLE_REWORK_CONCEPT.md", "COMBAT_AUDIT.md",
        "PETS_REDESIGN_CONCEPT.md", "NOT_IMPLEMENTED.md", "IMPLEMENTATION_BLOCKS.md",
        "GAME_BIBLE.md", "GAME_RECONSTRUCTION_3_0.md", "BATTLE_VFX_CONCEPT.md",
    )
    for name in retired:
        assert not (ROOT / name).exists(), name
    print("current game-document contract: OK")


if __name__ == "__main__":
    main()
