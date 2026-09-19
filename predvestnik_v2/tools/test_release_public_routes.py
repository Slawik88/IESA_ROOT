"""Release boundary: retired player economy/game APIs must not be reachable."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from FastAPI.main import app
from fastapi.testclient import TestClient


paths = set()
for route in app.routes:
    # FastAPI 0.121 stores included routers lazily as _IncludedRouter.  Their
    # visible path is empty until request dispatch, so inspect the source
    # router instead of mistaking an unexpanded route list for an empty app.
    source_router = getattr(route, "original_router", None)
    if source_router is not None:
        paths.update(getattr(child, "path", "") for child in source_router.routes)
    else:
        paths.add(getattr(route, "path", ""))

# These used to mutate or expose the retired market, pet and Reconstruction
# systems.  A hidden front-end must never be their only protection.
for prefix in (
    "/auction", "/battle_pass", "/craft", "/dark-mora", "/duels", "/games2",
    "/exchange", "/gacha", "/inventory", "/quests", "/relics", "/shop",
    "/showcase", "/skill-games", "/themes", "/vip", "/clans", "/barracks",
):
    assert not any(path == prefix or path.startswith(prefix + "/") for path in paths), prefix

for prefix in (
    "/profile", "/marriage", "/wallet", "/payments", "/admin",
    "/rhythm-v2", "/minesweeper-v2", "/mafia-v1", "/hub",
):
    assert any(path == prefix or path.startswith(prefix + "/") for path in paths), prefix

# Numeric Telegram/database ids are never a public-profile capability.  The
# supported reader is authenticated /profile/public/{opaque profile_ref}; the
# retired legacy route used to disclose username, rank and balances anonymously.
assert "/profile/{user_id}" not in paths

# Route registration is the source of truth: a stale cached client must get a
# plain 404 before authentication or any old business logic is reached.
client = TestClient(app)
for retired_path in ("/gacha/info", "/auction/", "/exchange/crypto", "/battle_pass/status", "/games2/retire-active"):
    assert client.get(retired_path).status_code == 404, retired_path

for raw_user_id in (1, 990000001, 9223372036854775807):
    response = client.get(f"/profile/{raw_user_id}")
    assert response.status_code == 404, (raw_user_id, response.status_code, response.text)

print("OK: public Mini App routes match the approved release scope")
