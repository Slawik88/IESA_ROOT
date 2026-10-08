"""Opaque, minimal public-player projection shared by social game surfaces.

Telegram identifiers and chat-local nicknames never belong in a global ranking
DTO.  This repository owns the durable opaque reference used by a public
profile link and the deliberately small display projection used by games.
"""
from __future__ import annotations

import secrets
from collections.abc import Iterable
from infrastructure.schema_readiness import ensure_read_schema


async def ensure_tables(db) -> None:
    await ensure_read_schema(db, install=_install_tables, name='public-profile-v1', tables=('public_profile_v1_refs',))


async def _install_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS public_profile_v1_refs (
            user_id BIGINT PRIMARY KEY,
            profile_ref TEXT NOT NULL UNIQUE
                CHECK (profile_ref ~ '^[A-Za-z0-9_-]{16,64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def fallback_name(profile_ref: str) -> str:
    """A stable, non-identifying label for an account without @username."""
    return f"Игрок {str(profile_ref)[:5].upper()}"


def display_name(username: object, profile_ref: str) -> str:
    name = str(username or "").strip().lstrip("@")
    return f"@{name}" if name else fallback_name(profile_ref)


async def ensure_reference(db, *, user_id: int) -> str:
    """Return the winning opaque reference, including under concurrent inserts."""
    return (await ensure_references(db, [int(user_id)]))[int(user_id)]


async def ensure_references(db, user_ids: Iterable[int]) -> dict[int, str]:
    ids = list(dict.fromkeys(int(value) for value in user_ids))
    if not ids:
        return {}
    await ensure_tables(db)
    async with db.execute(
        "SELECT user_id,profile_ref FROM public_profile_v1_refs WHERE user_id=ANY(?::bigint[])",
        (ids,),
    ) as cursor:
        refs = {int(row["user_id"]): str(row["profile_ref"]) for row in await cursor.fetchall()}
    # Both existing and first-time players are batched. DO NOTHING handles a
    # random-reference collision too, without aborting the caller's transaction.
    for _ in range(5):
        missing = [user_id for user_id in ids if user_id not in refs]
        if not missing:
            return refs
        await db.execute(
            "INSERT INTO public_profile_v1_refs(user_id,profile_ref) "
            "SELECT * FROM unnest(?::bigint[],?::text[]) ON CONFLICT DO NOTHING",
            (missing, [secrets.token_urlsafe(18) for _ in missing]),
        )
        async with db.execute(
            "SELECT user_id,profile_ref FROM public_profile_v1_refs WHERE user_id=ANY(?::bigint[])",
            (missing,),
        ) as cursor:
            refs.update({int(row["user_id"]): str(row["profile_ref"]) for row in await cursor.fetchall()})
    if len(refs) != len(ids):
        raise RuntimeError("could not allocate public profile references")
    return refs


async def resolve_reference(db, *, profile_ref: str) -> int | None:
    ref = str(profile_ref or "")
    if not 16 <= len(ref) <= 64 or not all(char.isascii() and (char.isalnum() or char in "-_") for char in ref):
        return None
    await ensure_tables(db)
    async with db.execute(
        "SELECT user_id FROM public_profile_v1_refs WHERE profile_ref=?", (ref,)
    ) as cursor:
        row = await cursor.fetchone()
    return int(row["user_id"]) if row else None


async def player_projection(db, *, user_ids: Iterable[int]) -> dict[int, dict]:
    """Return only fields permitted in a global leaderboard response."""
    ids = tuple(dict.fromkeys(int(value) for value in user_ids))
    if not ids:
        return {}
    refs = await ensure_references(db, ids)
    placeholders = ",".join("?" for _ in ids)
    async with db.execute(
        "SELECT r.user_id,r.profile_ref,u.user_tg_username "
        "FROM public_profile_v1_refs r "
        "LEFT JOIN users u ON u.user_tg_id=r.user_id "
        f"WHERE r.user_id IN ({placeholders})",
        ids,
    ) as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]
    result = {
        int(row["user_id"]): {
            "profile_ref": str(row["profile_ref"]),
            "display_name": display_name(row.get("user_tg_username"), str(row["profile_ref"])),
        }
        for row in rows
    }
    # Test-only game receipts can exist without a users row; their references
    # remain opaque and never expose the synthetic numeric ID.
    for user_id, ref in refs.items():
        result.setdefault(user_id, {"profile_ref": ref, "display_name": fallback_name(ref)})
    return result
