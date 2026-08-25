"""Release contract: the retired grid battle cannot re-enter the product UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "FastAPI" / "static"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    client = "\n".join(_read(STATIC / f"app.{part:02d}.js") for part in range(1, 12))
    preview = _read(ROOT / "tools" / "preview_server.mjs")
    main_py = _read(ROOT / "FastAPI" / "main.py")
    clans_transition = _read(ROOT / "FastAPI" / "routers" / "clans2.py")
    profile = _read(ROOT / "FastAPI" / "routers" / "profile.py")
    ai_assistant = _read(ROOT / "services" / "ai_assistant.py")
    redirect = _read(ROOT / "bot" / "handlers" / "web_redirect.py")
    bot_database = _read(ROOT / "bot" / "core" / "database.py")
    barracks = _read(ROOT / "FastAPI" / "routers" / "barracks.py")
    compatibility = _read(ROOT / "FastAPI" / "routers" / "legacy_combat_retirement.py")

    forbidden_client = (
        "/combat2", "_b3", "loadGates", "Клеточная тактика", "/combat/raid",
        "function loadRaid(", "function _raidStart(", "function _raidAttack(",
        "function acceptDuel(", "function openDuelChallenge(",
        "function submitDuelChallenge(", "showCpBreakdown", "cp-hero-val",
    )
    for marker in forbidden_client:
        assert marker not in client, f"retired combat marker is still shipped: {marker}"

    assert "/combat2" not in preview, "dev preview still advertises retired combat"
    assert "battle.router" not in main_py, "retired combat router is registered"
    assert "legacy_combat_retirement_router.router" in main_py
    assert "services.battle3" not in compatibility
    assert "services.barracks" not in compatibility
    assert "infrastructure.repositories" not in compatibility
    for retired_prefix in ('"/combat2/{path:path}"', '"/combat/{path:path}"'):
        assert retired_prefix in compatibility
    assert "status_code=410" in compatibility
    for startup_writer in ("ensure_combat", "ensure_battles", "ensure_clans2", "ensure_units"):
        assert startup_writer not in main_py, f"legacy web startup writer remains: {startup_writer}"
    for startup_writer in ("await _init_combat(db)", "await _ensure_battles", "await _ensure_clans2", "await _ensure_units"):
        assert startup_writer not in bot_database, f"legacy bot startup writer remains: {startup_writer}"
    assert "from services.combat_power import calculate_cp" not in profile
    assert "UPDATE users SET combat_power" not in profile
    assert '"combat_power":  None' in profile and '"gates_floor":  None' in profile
    assert "combat_power_index" not in ai_assistant
    assert '"game", "🔔 Разлом колокола"' in redirect
    assert "await barracks.get_barracks" not in barracks
    assert "raise HTTPException(410" in barracks
    assert 'status_code=410' in clans_transition
    assert "Союз доступен в Разломе" in clans_transition
    assert "openReconstructionGame()" in client

    print("OK: grid combat retired; Reconstruction is the only combat entry")


if __name__ == "__main__":
    main()
