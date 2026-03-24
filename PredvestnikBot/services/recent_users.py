import time


_RECENT_TTL = 6 * 60 * 60  # 6 hours
_recent_by_id: dict[int, tuple[str, str | None, float]] = {}
_recent_by_username: dict[str, tuple[int, str, float]] = {}
_last_cleanup = 0.0


def _normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    value = username.strip().lstrip("@").lower()
    return value or None


def _maybe_cleanup(now: float) -> None:
    global _last_cleanup
    if now - _last_cleanup < 300:
        return
    _last_cleanup = now
    cutoff = now - _RECENT_TTL

    stale_ids = [uid for uid, (_, _, ts) in _recent_by_id.items() if ts < cutoff]
    for uid in stale_ids:
        _recent_by_id.pop(uid, None)

    stale_usernames = [uname for uname, (_, _, ts) in _recent_by_username.items() if ts < cutoff]
    for uname in stale_usernames:
        _recent_by_username.pop(uname, None)


def remember_user(user_id: int, username: str | None, full_name: str | None) -> None:
    now = time.monotonic()
    _maybe_cleanup(now)

    normalized = _normalize_username(username)
    display_name = full_name or str(user_id)
    _recent_by_id[user_id] = (display_name, normalized, now)
    if normalized:
        _recent_by_username[normalized] = (user_id, display_name, now)


def get_recent_user(user_id: int) -> dict | None:
    now = time.monotonic()
    row = _recent_by_id.get(user_id)
    if not row:
        return None
    full_name, username, ts = row
    if now - ts > _RECENT_TTL:
        _recent_by_id.pop(user_id, None)
        return None
    return {"user_id": user_id, "full_name": full_name, "username": username}


def get_recent_user_by_username(username: str) -> dict | None:
    now = time.monotonic()
    normalized = _normalize_username(username)
    if not normalized:
        return None
    row = _recent_by_username.get(normalized)
    if not row:
        return None
    user_id, full_name, ts = row
    if now - ts > _RECENT_TTL:
        _recent_by_username.pop(normalized, None)
        return None
    return {"user_id": user_id, "full_name": full_name, "username": normalized}