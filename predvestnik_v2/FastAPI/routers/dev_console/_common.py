"""dev_console/_common.py — общие хелперы и гейт разработчика."""
import os
import httpx
from fastapi import HTTPException
from core.themes import THEMES
from services.profile_render import build_profile_text

DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0") or 0)

def _require_dev(user: dict) -> None:
    if not DEVELOPER_ID or user["id"] != DEVELOPER_ID:
        raise HTTPException(403, "Консоль разработчика доступна только Разработчику.")


async def _tg_call(method: str, **kwargs) -> dict:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return {"ok": False, "error": "no token"}
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/{method}", json=kwargs)
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _classify_chat_links(db, items: list[dict], id_key: str) -> None:
    """In-place разметка чатов по chat_links (Основная↔Админ группа):
    проставляет role (main/admin/plain), group_key (id основного чата группы),
    linked_title (название связанного чата). items[i] должен иметь items[i][id_key]
    (chat id) и items[i]['admin_chat_id'] (из LEFT JOIN chat_links по main_chat_id)."""
    ids = [it[id_key] for it in items]
    serves: dict = {}   # admin_chat_id -> main_chat_id (чаты, которые сами являются админками)
    if ids:
        ph = ",".join("?" * len(ids))
        async with db.execute(
            f"SELECT main_chat_id, admin_chat_id FROM chat_links WHERE admin_chat_id IN ({ph})",
            tuple(ids),
        ) as c:
            for lk in await c.fetchall():
                serves[lk["admin_chat_id"]] = lk["main_chat_id"]
    linked = {it["admin_chat_id"] for it in items if it.get("admin_chat_id")} | set(serves.values())
    titles: dict = {}
    if linked:
        ph = ",".join("?" * len(linked))
        async with db.execute(
            f"SELECT chat_id, chat_title FROM chat_settings WHERE chat_id IN ({ph})",
            tuple(linked),
        ) as c:
            titles = {x["chat_id"]: (x["chat_title"] or str(x["chat_id"])) for x in await c.fetchall()}
    for it in items:
        cid = it[id_key]
        if cid in serves:                       # это админ-чат для основной группы
            it["role"] = "admin"; it["group_key"] = serves[cid]
            it["linked_title"] = titles.get(serves[cid])
        elif it.get("admin_chat_id"):           # это основная группа с привязанным админ-чатом
            it["role"] = "main"; it["group_key"] = cid
            it["linked_title"] = titles.get(it["admin_chat_id"])
        else:
            it["role"] = "plain"; it["group_key"] = cid
            it["linked_title"] = None


async def _send_admin_gift(db, user_id: int, gifts: list[dict], reason: str = "") -> None:
    """Доставить «подарок от Администрации» (БЛОК 3.4): WS если игрок онлайн, иначе
    сохранить в web_notifications — коробка покажется при входе на сайт.
    gifts: [{"label": str, "amount": number}]. Только положительные начисления."""
    if not gifts:
        return
    payload = {"type": "admin_gift", "reason": (reason or "").strip(), "gifts": gifts}
    try:
        from FastAPI.notifications import notify as _ws_notify
        delivered = await _ws_notify(user_id, payload)
    except Exception:
        delivered = False
    if not delivered:
        try:
            from infrastructure.repositories import web_notifications as _wn
            await _wn.add(db, user_id, payload)
        except Exception:
            pass


# ── 9. Theme Lab — кастомные raw-шаблоны премиум-тем (правки без деплоя) ──────────
def _premium_template_list() -> list[dict]:
    out = []
    for theme_id, t in THEMES.items():
        tpl = t.get("premium_template")
        if tpl:
            out.append({"template_id": tpl, "theme_id": theme_id, "name": t.get("name", tpl), "kind": "premium"})
        else:
            out.append({"template_id": theme_id, "theme_id": theme_id, "name": t.get("name", theme_id), "kind": "basic"})
    return out


def _theme_id_for_template(template_id: str) -> str | None:
    theme_id = next((tid for tid, t in THEMES.items() if t.get("premium_template") == template_id), None)
    if theme_id:
        return theme_id
    return template_id if template_id in THEMES else None


async def _render_theme_preview(db, user_id: int, theme_id: str, raw_text: str) -> str:
    async with db.execute(
        "SELECT chat_tg_id FROM user_chat_stats WHERE user_tg_id = ? "
        "ORDER BY user_messages_count_all_time DESC LIMIT 1",
        (user_id,),
    ) as c:
        _cr = await c.fetchone()
    chat_id = _cr[0] if _cr else 0
    return await build_profile_text(db, user_id, chat_id, theme_id_override=theme_id,
                                     raw_template_override=raw_text)
