# services/admin_titles.py — кастом-тайтлы TG-админов чата («Владелец»/«Модератор»/свой).
# Источник — getChatAdministrators через raw HTTP (паттерн services/telegram_http.py —
# работает и из процесса бота, и из веб-процесса). TTL-кэш на чат: одна лёгкая
# API-выборка раз в 5 минут, а не на каждое упоминание имени.
import asyncio
import time

from services.telegram_http import tg_call

_CACHE: dict[int, tuple[dict[int, str], float]] = {}   # chat_id -> (uid->title, expires)
_TTL = 300.0
_TTL_FAIL = 60.0   # при ошибке API не долбим Telegram, но и не залипаем надолго


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def get_admin_titles(chat_id: int) -> dict[int, str]:
    """user_id -> тайтл (кастомный, иначе «владелец»/«админ» — как рисует сам Telegram).
    Только для групп (chat_id < 0); при ошибке API — пустая карта."""
    if not chat_id or chat_id >= 0:
        return {}
    now = time.monotonic()
    hit = _CACHE.get(chat_id)
    if hit and hit[1] > now:
        return hit[0]

    titles: dict[int, str] = {}
    r = await tg_call("getChatAdministrators", chat_id=chat_id)
    ok = bool(r.get("ok"))
    if ok:
        for m in r.get("result", []):
            u = m.get("user") or {}
            uid = u.get("id")
            if not uid or u.get("is_bot"):
                continue
            title = m.get("custom_title") or (
                "владелец" if m.get("status") == "creator" else "админ")
            titles[int(uid)] = str(title)[:16]
    _CACHE[chat_id] = (titles, now + (_TTL if ok else _TTL_FAIL))
    return titles


def suffix_of(titles: dict[int, str], user_id: int) -> str:
    """HTML-суффикс « · тайтл» к имени; пустая строка, если юзер не TG-админ.
    Для циклов: карту берём один раз через get_admin_titles, суффиксы — синхронно.
    Серые member-теги сюда не входят (их нельзя забрать одним вызовом на чат)."""
    t = titles.get(user_id)
    return f" <i>· {_esc(t)}</i>" if t else ""


# ── Серые теги обычных участников (Bot API 9.5, март 2026) ────────────────────
# У не-админа тоже может быть подпись возле ника — поле `tag` в getChatMember
# (статусы member/restricted). Списочного метода нет, поэтому пер-юзерный
# TTL-кэш; используется как фолбэк в title_suffix, когда юзер не в карте админов.
_MEMBER_CACHE: dict[tuple[int, int], tuple[str | None, float]] = {}


async def get_member_tag(chat_id: int, user_id: int) -> str | None:
    if not chat_id or chat_id >= 0:
        return None
    now = time.monotonic()
    hit = _MEMBER_CACHE.get((chat_id, user_id))
    if hit and hit[1] > now:
        return hit[0]

    tag = None
    r = await tg_call("getChatMember", chat_id=chat_id, user_id=user_id)
    ok = bool(r.get("ok"))
    if ok:
        m = r.get("result") or {}
        if m.get("status") in ("member", "restricted"):
            t = m.get("tag")
            tag = str(t)[:16] if t else None
    _MEMBER_CACHE[(chat_id, user_id)] = (tag, now + (_TTL if ok else _TTL_FAIL))
    return tag


async def title_suffix(chat_id: int, user_id: int) -> str:
    """Одиночный суффикс: админский цветной тайтл, иначе серый member-тег."""
    titles = await get_admin_titles(chat_id)
    if titles.get(user_id):
        return suffix_of(titles, user_id)
    tag = await get_member_tag(chat_id, user_id)
    return f" <i>· {_esc(tag)}</i>" if tag else ""


async def suffixes_for(chat_id: int, user_ids: list[int]) -> dict[int, str]:
    """Суффиксы для списка юзеров (топы): админ-тайтл одним вызовом на чат,
    серые member-теги — параллельно по каждому не-админу (список Telegram не даёт)."""
    if not chat_id or chat_id >= 0 or not user_ids:
        return {}
    titles = await get_admin_titles(chat_id)
    result: dict[int, str] = {}
    rest_ids = []
    for uid in user_ids:
        if titles.get(uid):
            result[uid] = suffix_of(titles, uid)
        else:
            rest_ids.append(uid)
    if rest_ids:
        tags = await asyncio.gather(*(get_member_tag(chat_id, uid) for uid in rest_ids))
        for uid, tag in zip(rest_ids, tags):
            if tag:
                result[uid] = f" <i>· {_esc(tag)}</i>"
    return result
