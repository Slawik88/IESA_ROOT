"""Safety boundary for the isolated local pre-production environment.

This module is deliberately small and dependency-free: it is imported before a
database pool is created, so a configuration typo cannot silently fall through
to a production ``DATABASE_URL``.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlparse


PREPROD_ENV = "preprod"
PREPROD_DATABASE = "predvestnik_preprod"
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
# This is an intentionally artificial identity.  It is never a Telegram user,
# never listed in PREPROD_ALLOWED_TG_IDS and is accepted only from the separate
# loopback-only browser-auth listener below.
PREPROD_BROWSER_TEST_USER_ID = 990_000_001


def is_preprod(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return source.get("PREDVESTNIK_ENV", "").strip().lower() == PREPROD_ENV


def assert_preprod_environment(env: Mapping[str, str] | None = None) -> None:
    """Reject every database configuration except the dedicated loopback DB.

    Call only when ``PREDVESTNIK_ENV=preprod`` is intentional.  The launcher
    starts from ``env -i`` and this second check protects direct/manual starts.
    No DSN is included in exception messages, avoiding credential disclosure.
    """
    source = os.environ if env is None else env
    if not is_preprod(source):
        raise RuntimeError("Preprod guard requires PREDVESTNIK_ENV=preprod.")
    if source.get("PREDVESTNIK_DATABASE_URL", "").strip():
        raise RuntimeError("Preprod forbids PREDVESTNIK_DATABASE_URL fallback.")

    dsn = source.get("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("Preprod requires an explicit local DATABASE_URL.")
    parsed = urlparse(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("Preprod DATABASE_URL must use PostgreSQL.")
    if (parsed.hostname or "").lower() not in _LOOPBACK_HOSTS:
        raise RuntimeError("Preprod DATABASE_URL must target loopback only.")
    if parsed.path.lstrip("/") != PREPROD_DATABASE:
        raise RuntimeError(
            f"Preprod DATABASE_URL must use database '{PREPROD_DATABASE}'."
        )
    if not source.get("PREPROD_ALLOWED_TG_IDS", "").strip():
        raise RuntimeError("Preprod requires PREPROD_ALLOWED_TG_IDS.")


def require_preprod_user(user_id: int, env: Mapping[str, str] | None = None) -> bool:
    """Return whether a signed Telegram user may use the public test tunnel."""
    source = os.environ if env is None else env
    if not is_preprod(source):
        return True
    allowed: set[int] = set()
    for raw_id in source.get("PREPROD_ALLOWED_TG_IDS", "").split(","):
        try:
            allowed.add(int(raw_id.strip()))
        except ValueError:
            continue
    return user_id in allowed


def is_preprod_browser_test_user(user_id: int, env: Mapping[str, str] | None = None) -> bool:
    """Whether this is the one synthetic user permitted by local test auth."""
    return is_preprod(env) and int(user_id) == PREPROD_BROWSER_TEST_USER_ID


def stars_invoice_issuance_allowed(env: Mapping[str, str] | None = None) -> bool:
    """Allow the frozen v1 Stars→Zarniki contract only in production.

    Isolated pre-production must never call Telegram's real payment API. The
    production quote and callback validators remain versioned and immutable.
    """
    return not is_preprod(env)


def direct_stars_cosmetics_allowed(env: Mapping[str, str] | None = None) -> bool:
    """New direct-Stars cosmetic invoices are permanently retired.

    The released product sells digital goods for Zarniki only.  Existing
    direct-Stars orders remain readable and deliverable by their frozen payload
    handlers so an already paid invoice is never stranded, but no environment
    flag may reopen new direct-Star cosmetic sales.
    """
    return False
