"""HTTP contract for stale combat links; no application database is needed."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from FastAPI.routers.legacy_combat_retirement import router


def main() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    for method, url in (
        ("get", "/combat2"),
        ("post", "/combat2/gates/enter"),
        ("get", "/combat/raid"),
        ("post", "/combat/raid/attack"),
        ("get", "/combat"),
    ):
        response = getattr(client, method)(url)
        assert response.status_code == 410, (method, url, response.status_code)
        assert "Разломом колокола" in response.json()["detail"]
    print("OK: stale combat URLs are explicit non-mutating 410 boundaries")


if __name__ == "__main__":
    main()
