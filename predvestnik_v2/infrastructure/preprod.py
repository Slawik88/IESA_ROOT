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


def stars_invoice_issuance_allowed(env: Mapping[str, str] | None = None) -> bool:
    """Preprod never calls Telegram Stars APIs that can initiate a payment."""
    return not is_preprod(env)
