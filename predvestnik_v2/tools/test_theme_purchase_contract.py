#!/usr/bin/env python3
"""Fast offline boundary checks for the atomic paid-theme purchase path."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    service = read("services/themes.py")
    web = read("FastAPI/routers/themes.py")
    client = read("FastAPI/static/app.10.js")
    bot = read("bot/handlers/themes.py")
    preview = read("tools/preview_server.mjs")
    verifier = read("tools/verify_preview_theme_purchase.mjs")

    assert "async def purchase_direct_theme(" in service
    assert "async with db.connection.transaction():" in service
    assert "await _lock_theme_user(db, user_id)" in service
    assert "find_reference_replay(" in service
    assert "INSERT INTO user_themes (user_id, theme_id) VALUES (?, ?)" in service
    assert "DO NOTHING RETURNING theme_id" in service
    assert service.index("DO NOTHING RETURNING theme_id") < service.index("await apply_balance_change(")
    assert 'reason_code="theme_purchase"' in service
    assert 'source_type="themes"' in service
    assert 'reference_type="profile_theme"' in service
    assert '"price": str(amount)' in service
    assert "grant_theme" not in service

    assert 'Header(default=None, alias="Idempotency-Key")' in web
    assert "purchase_direct_theme(" in web
    assert "WEB_DIRECT_THEME_SOURCES" in web
    assert "grant_theme" not in web
    assert "add_balance" not in web
    assert "spend_dark_mora" not in web

    assert "_looksThemePurchaseKeys" in client
    assert "'Idempotency-Key':requestKey" in client
    assert "_looksThemePurchaseKeys.get(tid)" in client
    assert "_looksThemePurchaseKeys.delete(tid)" in client
    assert "purchase_direct_theme(" in bot
    assert 'idempotency_key=f"theme:callback:{query.id}"' in bot
    assert "spend_dark_mora" not in bot

    assert "PREVIEW_THEME_PURCHASES" in preview
    assert "Idempotency-Key должен содержать 1–180 символов." in preview
    assert "replayed: true" in preview
    assert "already_owned: true" in preview
    assert "headers: {'Idempotency-Key': requestKey}" in verifier
    assert "Purchase retry must replay without a second debit" in verifier
    assert "A purchase key may not be rebound" in verifier

    print("theme purchase contract: atomic service + replay-safe adapters OK")


if __name__ == "__main__":
    main()
