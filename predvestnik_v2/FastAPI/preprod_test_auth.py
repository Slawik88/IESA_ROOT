"""Local-only browser authentication for repeatable isolated-preprod UI tests.

This ASGI app is bound to 127.0.0.1 on a different port.  It is deliberately
not mounted in the public Mini App, so a Cloudflare quick tunnel cannot issue a
test session.  The cookie is host-only for 127.0.0.1 and is accepted by the
main API only while PREDVESTNIK_ENV=preprod.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from FastAPI.auth import create_preprod_browser_ticket
from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.preprod import PREPROD_BROWSER_TEST_USER_ID, is_preprod
from core.cosmetics import COSMETICS
from services.cosmetics import ensure_tables as ensure_cosmetic_tables
from infrastructure.repositories import global_skins_v1 as global_skins_repo


TEST_AUTH_PORT = 8404
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


async def _ensure_test_persona() -> None:
    """Create the loopback persona and its complete test-only wardrobe."""
    await create_pool()
    async with get_pool().acquire() as connection:
        db = PGAdapter(connection)
        await db.execute(
            "INSERT INTO users (user_tg_id,user_tg_username,onboarded,ai_hint_shown) "
            "VALUES (?,? ,TRUE,FALSE) "
            "ON CONFLICT(user_tg_id) DO UPDATE SET user_tg_username=EXCLUDED.user_tg_username, onboarded=TRUE",
            (PREPROD_BROWSER_TEST_USER_ID, "codex_test"),
        )
        await ensure_cosmetic_tables(db)
        await global_skins_repo.ensure_tables(db)
        await global_skins_repo.grant(
            db, PREPROD_BROWSER_TEST_USER_ID, "lunar_archive", source="loopback_test_persona"
        )
        await connection.executemany(
            "INSERT INTO user_cosmetics(user_id,cosmetic_id) VALUES($1,$2) "
            "ON CONFLICT(user_id,cosmetic_id) DO NOTHING",
            [(PREPROD_BROWSER_TEST_USER_ID, cosmetic_id) for cosmetic_id in COSMETICS],
        )


@app.get("/__preprod/login")
async def login() -> RedirectResponse:
    if not is_preprod():
        # The launcher never starts this server outside preprod.  Keep this
        # fail-closed check too, so importing the module cannot weaken prod.
        raise HTTPException(404, "not found")
    await _ensure_test_persona()
    main_port = int(os.getenv("PORT", "8403"))
    # The browser-control surface used for UI checks does not reliably retain a
    # host cookie across ports.  Hand off with a distinct 120-second signed
    # ticket so the Mini App origin itself can set its own HttpOnly cookie.
    # This listener stays loopback-only; the public tunnel cannot mint tickets.
    ticket = create_preprod_browser_ticket(PREPROD_BROWSER_TEST_USER_ID)
    return RedirectResponse(
        f"http://127.0.0.1:{main_port}/predvestnik/__preprod/activate?ticket={ticket}",
        status_code=303,
    )
