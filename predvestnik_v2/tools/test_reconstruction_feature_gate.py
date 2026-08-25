"""Release regression: Reconstruction must be fail-closed while its dev flag is off."""
from __future__ import annotations

import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.repositories import system_flags  # noqa: E402


defaults = {key: enabled for key, _label, enabled in system_flags._DEFAULTS}
assert defaults["game_reconstruction_v1"] is False
assert defaults["reconstruction_real_settlement_v1"] is False

router = (ROOT / "FastAPI/routers/reconstruction.py").read_text(encoding="utf-8")
main = (ROOT / "FastAPI/main.py").read_text(encoding="utf-8")
bot_bootstrap = (ROOT / "bot/core/database.py").read_text(encoding="utf-8")
app_navigation = (ROOT / "FastAPI/static/app.04.js").read_text(encoding="utf-8")
assert 'require_tab_enabled("game_reconstruction_v1")' in router
assert 'require_tab_enabled("game_reconstruction_v1")' in main
assert '"reconstruction_real_settlement_v1"' in bot_bootstrap
assert "_isFeatureEnabled('game_reconstruction_v1')" in app_navigation

print("reconstruction_feature_gate: UI and API are fail-closed by explicit flags  OK")
