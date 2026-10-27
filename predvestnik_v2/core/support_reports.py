"""Limits and safe, allowlisted diagnostics for player-initiated reports."""
import re
from uuid import UUID

WINDOW_SECONDS = 3600
MAX_EVENTS = 3000
MAX_BODY_BYTES = 1024 * 1024
MAX_COMMENT = 2000
REPORTS_PER_HOUR = 6
RETENTION_DAYS = 30


class ReportQuotaExceeded(ValueError):
    """A new report exceeds the authenticated author's hourly quota."""


STATUSES = ("new", "investigating", "resolved")
CATEGORIES = {"avatar": "Не видно фото", "mafia": "Мафия и чат", "games": "Другие игры",
              "purchase": "Покупка или награда", "display": "Внешний вид", "other": "Другая проблема"}
EVENT_KINDS = {"request", "runtime", "resource", "navigation", "connection", "lifecycle", "avatar", "websocket"}
ENV_TEXT = {"user_agent", "platform", "model", "os_version", "architecture", "browser_version", "language",
            "languages", "locale_region", "timezone", "telegram_platform", "telegram_api_version", "color_scheme",
            "app_version", "page", "orientation", "connection_type", "service_worker", "capture_started"}
ENV_NUMBERS = {"screen_width", "screen_height", "viewport_width", "viewport_height", "pixel_ratio", "touch_points",
               "cpu_threads", "device_memory_gb", "rtt_ms", "downlink_mbps", "timezone_offset", "storage_quota_mb"}
ENV_BOOLS = {"online", "save_data", "reduced_motion", "no_fx", "mobile", "tg_photo_available", "fullscreen",
             "storage_available", "secure_context"}
EVENT_TEXT = {"method", "route", "request_id", "error_kind", "page", "state", "source", "stage", "outcome"}
EVENT_NUMBERS = {"status", "duration_ms", "line", "column", "code", "count"}
EVENT_BOOLS = {"vip", "has_avatar", "photo_available", "cached"}
SEGMENTS = frozenset("profile me avatar mafia-online mafia-v1 minesweeper-v2 rhythm-v2 league-v1 api hub leaderboard "
                     "leaderboards top stats rooms room match matches state action actions chat messages history settings "
                     "join leave start stop ready vote send read players seats table events account restore deleted "
                     "skins-v3 appearance cosmetics marks-v1 pets-v1 pets-v2 inventory-v1 inventory shop-v1 gifts-v2 "
                     "payments wallet vip analytics presence-v1 notifications quests-v1 achievements-v1 chests-v1 "
                     "season-pass star-dust player-exchange-v1 coin-market-v2 purge-v1 public-profile-v3 public u "
                     "easy normal hard casual ranked status sync daily home games more help looks family pass "
                     "connection open close hidden visible page online offline photo photos file download cache "
                     "webapp botapi hit miss empty no_token invalid_image timeout error loaded failed unsupported "
                     "active inactive resume pause connect closed transport auth request received no-vip "
                     "GET POST PUT PATCH DELETE HEAD OPTIONS".split())
_SECRET = re.compile(r"(?:\b\d{5,}:[A-Za-z0-9_-]{12,}|\bBearer\s+\S+|\beyJ[A-Za-z0-9_.-]{20,}|"
                     r"(?:tgWebAppData|initData|x-init-data|x-session-token|authorization|password|token)\s*[=:]\s*\S+)", re.I)
_URL = re.compile(r"(?:https?|wss?)://[^\s<>\"']+", re.I)


def safe_text(value, limit: int = 120) -> str:
    text = str(value or "")[:max(limit * 4, 2048)]
    text = _SECRET.sub("[скрыто]", text)
    text = _URL.sub("[ссылка]", text)
    return "".join(c for c in text if c >= " " or c in "\n\t")[:limit]


def safe_route(value) -> str:
    path = str(value or "").split("?", 1)[0].split("#", 1)[0]
    if "://" in path:
        return "/external"
    parts = path.strip("/").split("/")[:8]
    return "/" + "/".join(p if p in SEGMENTS or re.fullmatch(r"\{[a-z_]{1,40}\}", p) else ":value" for p in parts if p)


def environment(value) -> dict:
    if not isinstance(value, dict):
        return {}
    out = {k: safe_text(v, 512 if k == "user_agent" else 120) for k,v in value.items() if k in ENV_TEXT and isinstance(v,str)}
    out.update({k: v for k,v in value.items() if k in ENV_NUMBERS and type(v) in (int,float) and abs(v) <= 10**8})
    out.update({k: v for k,v in value.items() if k in ENV_BOOLS and isinstance(v,bool)})
    if "page" in out:
        out["page"] = safe_route(out["page"])
    return out


def event_data(value) -> dict:
    if not isinstance(value, dict):
        return {}
    out = {k: safe_text(v, 120) for k,v in value.items() if k in EVENT_TEXT and isinstance(v,str)}
    if "route" in out:
        out["route"] = safe_route(out["route"])
    if "request_id" in out and not re.fullmatch(r"[a-f0-9-]{16,36}", out["request_id"]):
        out.pop("request_id")
    if "error_kind" in out and not re.fullmatch(r"[A-Za-z]{1,40}", out["error_kind"]):
        out["error_kind"] = "Error"
    out.update({k: v for k,v in value.items() if k in EVENT_NUMBERS and type(v) in (int,float) and abs(v) <= 10**8})
    out.update({k: v for k,v in value.items() if k in EVENT_BOOLS and isinstance(v,bool)})
    if isinstance(value.get("frames"), list):
        out["frames"] = [v for v in value["frames"][:8] if isinstance(v,str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}:\d{1,8}:\d{1,8}",v)]
    return out


def normalize(payload: dict) -> dict:
    if not isinstance(payload,dict):
        raise ValueError("Некорректный отчёт.")
    try:
        report_id = str(UUID(str(payload.get("client_report_id", ""))))
        captured = int(payload["captured_at"])
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise ValueError("Не удалось прочитать отчёт. Открой форму заново.") from error
    if not 1577836800000 <= captured <= 4102444800000:
        raise ValueError("Проверь дату и время на устройстве.")
    category = payload.get("category", "other")
    if not isinstance(category,str) or category not in CATEGORIES:
        raise ValueError("Выбери вид проблемы.")
    include = payload.get("include_diagnostics", True) is True
    events = payload.get("events", [])
    if not isinstance(events,list) or len(events) > MAX_EVENTS:
        raise ValueError("Отчёт слишком большой. Открой форму заново.")
    cleaned = []
    if include:
        for entry in events:
            if not isinstance(entry,dict) or not isinstance(entry.get("kind"),str) or entry["kind"] not in EVENT_KINDS:
                continue
            at = entry.get("at")
            if type(at) not in (int,float) or not 0 <= captured-at <= WINDOW_SECONDS*1000:
                continue
            cleaned.append({"at":int(at),"kind":entry["kind"],"data":event_data(entry.get("data"))})
    try:
        dropped = max(0,min(int(payload.get("dropped_events") or 0),10**7))
    except (ValueError,TypeError,OverflowError) as error:
        raise ValueError("Некорректный счётчик событий.") from error
    return {"client_report_id":report_id,"captured_at":captured,"category":category,
            "comment":safe_text(payload.get("comment"),MAX_COMMENT),"include_diagnostics":include,
            "environment":environment(payload.get("environment")) if include else {},"events":cleaned,
            "dropped_events":dropped}
