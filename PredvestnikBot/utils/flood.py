import time
from collections import defaultdict

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
