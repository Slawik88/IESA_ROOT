"""Legacy cosmetic chest endpoints must not leak old prices or odds."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from FastAPI.deps import get_db, require_tg_user
from FastAPI.routers import cosmetics


async def fake_db():
    return object()


async def fake_user():
    return {"id": 991001}


app = FastAPI()
app.include_router(cosmetics.router)
app.dependency_overrides[get_db] = fake_db
app.dependency_overrides[require_tg_user] = fake_user
for dependency in cosmetics.router.dependencies:
    app.dependency_overrides[dependency.dependency] = lambda: True

client = TestClient(app)
catalog = client.get("/cosmetics/chests")
assert catalog.status_code == 410
assert "odds" not in catalog.text and "zarniki" not in catalog.text
opened = client.post("/cosmetics/chest/open", json={"chest_id": "legacy"})
assert opened.status_code == 410

print("OK: authenticated legacy cosmetic chest catalog/open stay retired")
