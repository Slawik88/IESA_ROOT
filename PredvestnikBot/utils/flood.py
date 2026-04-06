import time
from collections import defaultdict
from dataclasses import dataclass, field

from config import (
    TRUST_NEWCOMER_THRESHOLD, TRUST_TRUSTED_THRESHOLD,
    AF2_NEWCOMER_TEXT_LIMIT, AF2_NEWCOMER_TEXT_WINDOW, AF2_NEWCOMER_TEXT_MUTE,
    AF2_NEWCOMER_MEDIA_LIMIT, AF2_NEWCOMER_MEDIA_WINDOW, AF2_NEWCOMER_MEDIA_MUTE,
    AF2_NEWCOMER_STICKER_LIMIT, AF2_NEWCOMER_STICKER_WINDOW, AF2_NEWCOMER_STICKER_MUTE,
    AF2_NEWCOMER_MIXED_LIMIT, AF2_NEWCOMER_MIXED_WINDOW, AF2_NEWCOMER_MIXED_MUTE,
    AF2_TRUSTED_STICKER_LIMIT, AF2_TRUSTED_STICKER_WINDOW, AF2_TRUSTED_STICKER_MUTE,
    AF2_TRUSTED_MEDIA_LIMIT, AF2_TRUSTED_MEDIA_WINDOW, AF2_TRUSTED_MEDIA_MUTE,
    AF2_REGULAR_STICKER_LIMIT, AF2_REGULAR_STICKER_WINDOW, AF2_REGULAR_STICKER_MUTE,
    AF2_DELETE_WINDOW, AF2_ENABLED, AF2_ANTISPAM_ENABLED,
)

# ── Dynamic AF2 config per chat (overrides from miniapp dev panel, stored in DB) ─
_af2_cfg: dict[int, dict] = {}       # chat_id → {key: float value}
_af2_cfg_ts: dict[int, float] = {}   # chat_id → last refresh (monotonic)
_AF2_CFG_TTL = 30.0                  # seconds between DB refreshes


def _af2(key: str, default, chat_id: int = 0):
    """Return AF2 metric for a chat: DB override if present, else config constant."""
    v = _af2_cfg.get(chat_id, {}).get(key)
    return type(default)(v) if v is not None else default


def set_af2_cfg(chat_id: int, cfg: dict) -> None:
    """Update in-memory AF2 config for a specific chat (called by middleware after DB read)."""
    _af2_cfg[chat_id] = {k: float(v) for k, v in cfg.items() if v is not None}
    _af2_cfg_ts[chat_id] = time.monotonic()


def is_af2_cfg_stale(chat_id: int) -> bool:
    """True when in-memory config for this chat is older than TTL."""
    return time.monotonic() - _af2_cfg_ts.get(chat_id, 0.0) > _AF2_CFG_TTL


def get_af2_flag(key: str, default, chat_id: int = 0):
    """Public helper — read a single AF2 config flag for a chat (used from middleware)."""
    return _af2(key, default, chat_id)

# ── Legacy stores (kept for backward compat with check_spam / check_flood) ───

# Раздельные словари для спам-детекции и настраиваемого антифлуда,
# чтобы не было двойного подсчёта при двух проверках на сообщение.
_flood_spam: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
_flood_antiflood: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))


def _check(store: dict, chat_id: int, user_id: int, limit: int, window: float) -> bool:
    now = time.monotonic()
    msgs = store[chat_id][user_id]
    # Очистка устаревших записей + ограничение размера
    store[chat_id][user_id] = filtered = [t for t in msgs if now - t < window]
    filtered.append(now)
    return len(filtered) > limit


def check_spam(chat_id: int, user_id: int, limit: int, window: float = 1.0) -> bool:
    """Проверка авто-спама (жёсткая, всегда включена)."""
    return _check(_flood_spam, chat_id, user_id, limit, window)


def check_flood(chat_id: int, user_id: int, limit: int, window: float = 5.0) -> bool:
    """Проверка настраиваемого антифлуда."""
    return _check(_flood_antiflood, chat_id, user_id, limit, window)


def reset_flood(chat_id: int, user_id: int):
    _flood_spam[chat_id][user_id] = []
    _flood_antiflood[chat_id][user_id] = []


def cleanup_flood_data():
    """Периодическая очистка устаревших данных (вызывать раз в ~час)."""
    now = time.monotonic()
    for store in (_flood_spam, _flood_antiflood):
        empty_chats = []
        for cid, users in store.items():
            empty_users = [uid for uid, ts in users.items() if not ts or now - ts[-1] > 300]
            for uid in empty_users:
                del users[uid]
            if not users:
                empty_chats.append(cid)
        for cid in empty_chats:
            del store[cid]
    # Also cleanup smart antiflood
    _cleanup_smart_data()


# ══════════════════════════════════════════════════════════════════════════════
#  Умный Антифлуд 2.0
# ══════════════════════════════════════════════════════════════════════════════


def get_trust_level(message_count: int, chat_id: int = 0) -> str:
    """Return 'newcomer', 'regular', or 'trusted' based on message count.
    Uses dynamic thresholds from AF2 DB config if set, otherwise falls back to config constants."""
    newcomer_thresh = int(_af2("newcomer_threshold", TRUST_NEWCOMER_THRESHOLD, chat_id))
    trusted_thresh  = int(_af2("trusted_threshold",  TRUST_TRUSTED_THRESHOLD,  chat_id))
    if message_count < newcomer_thresh:
        return "newcomer"
    if message_count >= trusted_thresh:
        return "trusted"
    return "regular"


# ── Per-user event tracking for Smart Antiflood ──────────────────────────────

@dataclass
class _UserFloodState:
    """Tracks message timestamps by type for one user in one chat."""
    text_ts: list[float] = field(default_factory=list)
    media_ts: list[float] = field(default_factory=list)
    sticker_ts: list[float] = field(default_factory=list)   # stickers + GIFs/animations
    all_ts: list[float] = field(default_factory=list)
    seen_albums: dict[str, float] = field(default_factory=dict)  # media_group_id → first_seen
    recent_msgs: list[tuple[int, float]] = field(default_factory=list)  # (msg_id, monotonic_ts) for bulk delete
    last_activity: float = 0.0


# chat_id → user_id → state
_smart_state: dict[int, dict[int, _UserFloodState]] = defaultdict(dict)


def _get_state(chat_id: int, user_id: int) -> _UserFloodState:
    users = _smart_state[chat_id]
    if user_id not in users:
        users[user_id] = _UserFloodState()
    return users[user_id]


def _prune(timestamps: list[float], window: float, now: float) -> list[float]:
    """Remove entries older than *window* seconds."""
    cutoff = now - window
    return [t for t in timestamps if t > cutoff]


@dataclass
class FloodVerdict:
    """What the middleware should do after smart antiflood check."""
    action: str = "allow"   # allow | warn | delete | mute
    mute_seconds: int = 0   # 0 = permanent (until manual unmute)
    delete_all: bool = False # delete all recent messages from user
    delete_msg_ids: list[int] = field(default_factory=list)
    notify_admins: bool = False
    reason: str = ""
    trust: str = "regular"
    is_album: bool = False   # message is part of album (may skip counting)


def _count_in_window(timestamps: list[float], window: float, now: float) -> int:
    cutoff = now - window
    return sum(1 for t in timestamps if t > cutoff)


def check_smart_flood(
    chat_id: int,
    user_id: int,
    message_count: int,
    *,
    message_id: int = 0,
    is_text: bool = False,
    is_media: bool = False,
    is_sticker: bool = False,
    is_animation: bool = False,   # GIFs — treated same as stickers (raid vector)
    media_group_id: str | None = None,
) -> FloodVerdict:
    """Smart Antiflood 2.0 — trust-level-aware flood detection.

    Returns a FloodVerdict telling the middleware what action to take.
    """
    now = time.monotonic()
    state = _get_state(chat_id, user_id)
    state.last_activity = now

    # Per-chat config helper — uses this chat's DB overrides, falls back to constants
    _a = lambda k, d: _af2(k, d, chat_id)  # noqa: E731

    # Fast path: AF2 completely disabled for this chat
    if not int(_a("af2_enabled", AF2_ENABLED)):
        return FloodVerdict(trust=get_trust_level(message_count, chat_id))

    trust = get_trust_level(message_count, chat_id)
    verdict = FloodVerdict(trust=trust)

    # Dynamic overrides (from DB miniapp panel; fall back to config constants)
    _N_MIXED_LIM  = int(_a("newcomer_mixed_limit",    AF2_NEWCOMER_MIXED_LIMIT))
    _N_MIXED_WIN  =     _a("newcomer_mixed_window",   AF2_NEWCOMER_MIXED_WINDOW)
    _N_MIXED_MUT  = int(_a("newcomer_mixed_mute",     AF2_NEWCOMER_MIXED_MUTE))
    _N_MEDIA_LIM  = int(_a("newcomer_media_limit",    AF2_NEWCOMER_MEDIA_LIMIT))
    _N_MEDIA_WIN  =     _a("newcomer_media_window",   AF2_NEWCOMER_MEDIA_WINDOW)
    _N_MEDIA_MUT  = int(_a("newcomer_media_mute",     AF2_NEWCOMER_MEDIA_MUTE))
    _N_STICK_LIM  = int(_a("newcomer_sticker_limit",  AF2_NEWCOMER_STICKER_LIMIT))
    _N_STICK_WIN  =     _a("newcomer_sticker_window", AF2_NEWCOMER_STICKER_WINDOW)
    _N_STICK_MUT  = int(_a("newcomer_sticker_mute",   AF2_NEWCOMER_STICKER_MUTE))
    _N_TEXT_LIM   = int(_a("newcomer_text_limit",     AF2_NEWCOMER_TEXT_LIMIT))
    _N_TEXT_WIN   =     _a("newcomer_text_window",    AF2_NEWCOMER_TEXT_WINDOW)
    _N_TEXT_MUT   = int(_a("newcomer_text_mute",      AF2_NEWCOMER_TEXT_MUTE))
    _T_MEDIA_LIM  = int(_a("trusted_media_limit",     AF2_TRUSTED_MEDIA_LIMIT))
    _T_MEDIA_WIN  =     _a("trusted_media_window",    AF2_TRUSTED_MEDIA_WINDOW)
    _T_MEDIA_MUT  = int(_a("trusted_media_mute",      AF2_TRUSTED_MEDIA_MUTE))
    _T_STICK_LIM  = int(_a("trusted_sticker_limit",   AF2_TRUSTED_STICKER_LIMIT))
    _T_STICK_WIN  =     _a("trusted_sticker_window",  AF2_TRUSTED_STICKER_WINDOW)
    _T_STICK_MUT  = int(_a("trusted_sticker_mute",    AF2_TRUSTED_STICKER_MUTE))
    _R_STICK_LIM  = int(_a("regular_sticker_limit",   AF2_REGULAR_STICKER_LIMIT))
    _R_STICK_WIN  =     _a("regular_sticker_window",  AF2_REGULAR_STICKER_WINDOW)
    _R_STICK_MUT  = int(_a("regular_sticker_mute",    AF2_REGULAR_STICKER_MUTE))
    _DELETE_WIN   = float(_a("delete_window",          AF2_DELETE_WINDOW))

    def _ids_for_delete() -> list[int]:
        """Return msg IDs from the rolling buffer that fall within the delete window."""
        cutoff = now - _DELETE_WIN
        return [mid for mid, ts in state.recent_msgs if ts >= cutoff]

    # Track message ID (with timestamp) for potential bulk delete
    if message_id:
        state.recent_msgs.append((message_id, now))
        if len(state.recent_msgs) > 200:
            state.recent_msgs = state.recent_msgs[-200:]

    # ── Album deduplication ──────────────────────────────────────────────
    if media_group_id:
        # Clean old album IDs (> 30 seconds)
        state.seen_albums = {
            k: v for k, v in state.seen_albums.items() if now - v < 30
        }
        if media_group_id in state.seen_albums:
            # Already counted this album — skip entirely
            verdict.is_album = True
            return verdict
        state.seen_albums[media_group_id] = now

    # ── Record timestamp by type ─────────────────────────────────────────
    max_window = 15.0  # keep up to 15s of history
    state.all_ts = _prune(state.all_ts, max_window, now)
    state.all_ts.append(now)

    if is_text:
        state.text_ts = _prune(state.text_ts, max_window, now)
        state.text_ts.append(now)
    if is_media:
        state.media_ts = _prune(state.media_ts, max_window, now)
        state.media_ts.append(now)
    if is_sticker or is_animation:  # GIFs tracked alongside stickers — both are raid vectors
        state.sticker_ts = _prune(state.sticker_ts, max_window, now)
        state.sticker_ts.append(now)

    # ── Newcomer checks (strict) ─────────────────────────────────────────
    if trust == "newcomer":
        # Mixed attack: text + media together
        mixed_count = _count_in_window(state.all_ts, _N_MIXED_WIN, now)
        has_text = _count_in_window(state.text_ts, _N_MIXED_WIN, now) > 0
        has_media = _count_in_window(state.media_ts, _N_MIXED_WIN, now) > 0
        if mixed_count >= _N_MIXED_LIM and has_text and has_media:
            verdict.action = "mute"
            verdict.mute_seconds = _N_MIXED_MUT
            verdict.delete_all = True
            verdict.delete_msg_ids = _ids_for_delete()
            verdict.notify_admins = True
            verdict.reason = "mixed_attack"
            state.recent_msgs.clear()
            return verdict

        # Media raid
        media_count = _count_in_window(state.media_ts, _N_MEDIA_WIN, now)
        if media_count >= _N_MEDIA_LIM:
            verdict.action = "mute"
            verdict.mute_seconds = _N_MEDIA_MUT
            verdict.delete_all = True
            verdict.delete_msg_ids = _ids_for_delete()
            verdict.notify_admins = True
            verdict.reason = "media_raid"
            state.recent_msgs.clear()
            return verdict

        # Sticker/GIF raid (newcomers cannot burst stickers)
        sticker_count = _count_in_window(state.sticker_ts, _N_STICK_WIN, now)
        if sticker_count >= _N_STICK_LIM:
            verdict.action = "mute"
            verdict.mute_seconds = _N_STICK_MUT
            verdict.delete_all = True
            verdict.delete_msg_ids = _ids_for_delete()
            verdict.notify_admins = True
            verdict.reason = "media_raid"
            state.recent_msgs.clear()
            return verdict

        # Text spam
        text_count = _count_in_window(state.text_ts, _N_TEXT_WIN, now)
        if text_count >= _N_TEXT_LIM:
            verdict.action = "mute"
            verdict.mute_seconds = _N_TEXT_MUT
            verdict.delete_all = True
            verdict.delete_msg_ids = _ids_for_delete()
            verdict.notify_admins = True
            verdict.reason = "text_spam"
            state.recent_msgs.clear()
            return verdict

    # ── Trusted checks (relaxed) ─────────────────────────────────────────
    elif trust == "trusted":
        # Suspected hack / compromised account
        media_count = _count_in_window(state.media_ts, _T_MEDIA_WIN, now)
        if media_count >= _T_MEDIA_LIM:
            verdict.action = "mute"
            verdict.mute_seconds = _T_MEDIA_MUT
            verdict.delete_all = True
            verdict.delete_msg_ids = _ids_for_delete()
            verdict.notify_admins = True
            verdict.reason = "suspected_hack"
            state.recent_msgs.clear()
            return verdict

        # Sticker/GIF raid — now mutes + notifies admins (raiders exploit this)
        sticker_count = _count_in_window(state.sticker_ts, _T_STICK_WIN, now)
        if sticker_count >= _T_STICK_LIM:
            verdict.action = "mute"
            verdict.mute_seconds = _T_STICK_MUT
            verdict.delete_all = True
            verdict.delete_msg_ids = _ids_for_delete()
            verdict.notify_admins = True
            verdict.reason = "sticker_gif_raid"
            state.recent_msgs.clear()
            return verdict

    # ── Regular users — sticker/GIF raid check + legacy antiflood ────────
    else:  # trust == "regular"
        sticker_count = _count_in_window(state.sticker_ts, _R_STICK_WIN, now)
        if sticker_count >= _R_STICK_LIM:
            verdict.action = "mute"
            verdict.mute_seconds = _R_STICK_MUT
            verdict.delete_all = True
            verdict.delete_msg_ids = _ids_for_delete()
            verdict.notify_admins = True
            verdict.reason = "sticker_gif_raid"
            state.recent_msgs.clear()
            return verdict
        # Fallback: middleware will apply legacy check_flood()

    return verdict


def reset_smart_flood(chat_id: int, user_id: int):
    """Clear smart flood state for a user (e.g. on unmute)."""
    if chat_id in _smart_state:
        _smart_state[chat_id].pop(user_id, None)


def _cleanup_smart_data():
    """Remove stale smart antiflood entries (> 5 min idle)."""
    now = time.monotonic()
    empty_chats = []
    for cid, users in _smart_state.items():
        stale = [uid for uid, st in users.items() if now - st.last_activity > 300]
        for uid in stale:
            del users[uid]
        if not users:
            empty_chats.append(cid)
    for cid in empty_chats:
        del _smart_state[cid]
