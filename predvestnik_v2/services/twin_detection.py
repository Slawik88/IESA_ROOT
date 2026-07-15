"""
services/twin_detection.py — БЛОК: анти-твинк детект (дев-консоль, БЕЗ наказаний).

Эвристика для РАЗРАБОТЧИКА, не система банов: мультиаккаунтинг сам по себе не
запрещён (BASE_PROMPT/politiki.md — запрещено только злоупотребление). Показывает
пары аккаунтов с признаками «один человек/устройство», с разбивкой ПОЧЕМУ —
решение остаётся за разработчиком, никаких автоматических ограничений.

Номинация пары в отчёт — только по техническим/явным сигналам (общий отпечаток
устройства, общий IP, брак, рефералка). Поведенческие сигналы (дуэли/аукцион/
общие чаты) сами по себе НЕ номинируют пару — это нормальное многопользовательское
поведение (играют/торгуют с друзьями), они лишь дополняют картину для уже
номинированных пар.

Осторожно с IP: общий Wi-Fi/мобильный интернет (CGNAT) даёт одинаковый IP у
незнакомых людей — это не доказательство, только сигнал для сортировки.

Считается по кнопке «Пересчитать» в консоли (тяжёлый запрос) — результат
кэшируется в памяти процесса до следующего пересчёта, отдельная таблица не нужна.
"""
import time

from infrastructure.repositories import twin_signals

_CACHE: dict = {"computed_at": 0.0, "pairs": []}

# Веса очков (для сортировки, НЕ проценты «уверенности» — разбивка ниже важнее самого числа)
W_SHARED_FP, CAP_SHARED_FP = 35, 2
W_SHARED_IP, CAP_SHARED_IP = 12, 3
W_BOTH_BONUS = 20          # совпали И устройство, И IP одновременно
W_REFERRAL = 15
W_MARRIAGE, CAP_MARRIAGE = 10, 2
W_AUCTION_TRADE, CAP_AUCTION_TRADE = 4, 5
W_DUEL, CAP_DUEL = 2, 5
W_SHARED_CHAT, CAP_SHARED_CHAT = 2, 5

_MAX_RESULTS = 150


def _pair_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


async def _signal_pair_counts(db, kind: str) -> dict[tuple[int, int], int]:
    rows = await twin_signals.shared_signal_pairs(db, kind)
    out: dict[tuple[int, int], int] = {}
    for a, b, _vhash, _ha, _hb in rows:
        key = _pair_key(int(a), int(b))
        out[key] = out.get(key, 0) + 1
    return out


async def _referral_pairs(db) -> set[tuple[int, int]]:
    async with db.execute(
        "SELECT user_tg_id, referred_by FROM users WHERE referred_by IS NOT NULL"
    ) as c:
        rows = await c.fetchall()
    return {_pair_key(int(r[0]), int(r[1])) for r in rows if r[1]}


async def _marriage_pairs(db) -> dict[tuple[int, int], int]:
    async with db.execute(
        "SELECT user1_id, user2_id, COUNT(*) FROM marriages "
        "WHERE user1_id IS NOT NULL AND user2_id IS NOT NULL "
        "GROUP BY user1_id, user2_id"
    ) as c:
        rows = await c.fetchall()
    out: dict[tuple[int, int], int] = {}
    for u1, u2, cnt in rows:
        key = _pair_key(int(u1), int(u2))
        out[key] = out.get(key, 0) + int(cnt)
    return out


async def _auction_trade_pairs(db, candidates: set) -> dict[tuple[int, int], int]:
    if not candidates:
        return {}
    async with db.execute("""
        SELECT seller_id, bidder_id, COUNT(*) FROM (
            SELECT DISTINCT ON (l.id) l.id, l.seller_id, b.bidder_id
            FROM auction_lots l
            JOIN auction_bids b ON b.lot_id = l.id
            WHERE l.status = 'sold' AND l.seller_id != b.bidder_id
            ORDER BY l.id, b.amount DESC
        ) winners
        GROUP BY seller_id, bidder_id
    """) as c:
        rows = await c.fetchall()
    out: dict[tuple[int, int], int] = {}
    for seller, bidder, cnt in rows:
        key = _pair_key(int(seller), int(bidder))
        if key in candidates:
            out[key] = out.get(key, 0) + int(cnt)
    return out


async def _duel_pairs(db, candidates: set) -> dict[tuple[int, int], int]:
    if not candidates:
        return {}
    async with db.execute(
        "SELECT challenger_id, challenged_id, COUNT(*) FROM duels "
        "WHERE winner_id IS NOT NULL GROUP BY challenger_id, challenged_id"
    ) as c:
        rows = await c.fetchall()
    out: dict[tuple[int, int], int] = {}
    for a, b, cnt in rows:
        key = _pair_key(int(a), int(b))
        if key in candidates:
            out[key] = out.get(key, 0) + int(cnt)
    return out


async def _shared_chat_pairs(db, candidates: set) -> dict[tuple[int, int], int]:
    """Только для уже номинированных пар (иначе self-join по большим публичным
    чатам даёт комбинаторный взрыв пар и ложный шум — 500 человек в одном чате
    не значит 500*499/2 подозрительных пар)."""
    out: dict[tuple[int, int], int] = {}
    for a, b in candidates:
        async with db.execute(
            "SELECT COUNT(*) FROM user_chat_stats x JOIN user_chat_stats y "
            "ON x.chat_tg_id = y.chat_tg_id WHERE x.user_tg_id = ? AND y.user_tg_id = ? "
            "AND x.is_left = FALSE AND y.is_left = FALSE",
            (a, b),
        ) as c:
            row = await c.fetchone()
        cnt = int(row[0]) if row else 0
        if cnt:
            out[(a, b)] = cnt
    return out


async def _usernames_for(db, candidates: set) -> dict[int, str]:
    ids = sorted({u for pair in candidates for u in pair})
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT user_tg_id, user_tg_username FROM users WHERE user_tg_id IN ({ph})",
        tuple(ids),
    ) as c:
        rows = await c.fetchall()
    return {int(r[0]): (r[1] or "") for r in rows}


async def compute(db) -> list[dict]:
    fp_pairs = await _signal_pair_counts(db, "fp")
    ip_pairs = await _signal_pair_counts(db, "ip")
    referral = await _referral_pairs(db)
    marriage = await _marriage_pairs(db)

    candidates = set(fp_pairs) | set(ip_pairs) | referral | set(marriage)
    if not candidates:
        return []

    trades = await _auction_trade_pairs(db, candidates)
    duels = await _duel_pairs(db, candidates)
    chats = await _shared_chat_pairs(db, candidates)
    usernames = await _usernames_for(db, candidates)

    results = []
    for key in candidates:
        a, b = key
        fp_n = fp_pairs.get(key, 0)
        ip_n = ip_pairs.get(key, 0)
        marr_n = marriage.get(key, 0)
        trade_n = trades.get(key, 0)
        duel_n = duels.get(key, 0)
        chat_n = chats.get(key, 0)

        score = 0
        signals = []
        if fp_n:
            pts = min(fp_n, CAP_SHARED_FP) * W_SHARED_FP
            score += pts
            signals.append({"kind": "device", "points": pts,
                             "label": f"🖥 Общий отпечаток устройства ×{fp_n}"})
        if ip_n:
            pts = min(ip_n, CAP_SHARED_IP) * W_SHARED_IP
            score += pts
            signals.append({"kind": "ip", "points": pts,
                             "label": f"🌐 Общий IP ×{ip_n}",
                             "caveat": "Может быть общий Wi-Fi/мобильный интернет (CGNAT) — само по себе не доказательство."})
        if fp_n and ip_n:
            score += W_BOTH_BONUS
            signals.append({"kind": "combo", "points": W_BOTH_BONUS,
                             "label": "🎯 Совпали И устройство, И IP"})
        if key in referral:
            score += W_REFERRAL
            signals.append({"kind": "referral", "points": W_REFERRAL,
                             "label": "🔗 Один пригласил другого (рефералка)",
                             "caveat": "Обычно это нормальный инвайт друга — весомо только вместе с другими сигналами."})
        if marr_n:
            pts = min(marr_n, CAP_MARRIAGE) * W_MARRIAGE
            score += pts
            signals.append({"kind": "marriage", "points": pts,
                             "label": f"💍 Были в браке ×{marr_n}"})
        if trade_n:
            pts = min(trade_n, CAP_AUCTION_TRADE) * W_AUCTION_TRADE
            score += pts
            signals.append({"kind": "auction", "points": pts,
                             "label": f"🏛 Сделки на аукционе между собой ×{trade_n}"})
        if duel_n:
            pts = min(duel_n, CAP_DUEL) * W_DUEL
            score += pts
            signals.append({"kind": "duel", "points": pts,
                             "label": f"⚔️ Дуэли между собой ×{duel_n}"})
        if chat_n:
            pts = min(chat_n, CAP_SHARED_CHAT) * W_SHARED_CHAT
            score += pts
            signals.append({"kind": "chats", "points": pts,
                             "label": f"💬 Общих чатов: {chat_n}"})

        signals.sort(key=lambda s: -s["points"])
        results.append({
            "user_a": a, "user_b": b,
            "username_a": usernames.get(a, ""), "username_b": usernames.get(b, ""),
            "score": score,
            "signals": signals,
        })

    results.sort(key=lambda r: -r["score"])
    return results[:_MAX_RESULTS]


def get_cached() -> dict:
    return {"pairs": _CACHE["pairs"], "computed_at": _CACHE["computed_at"]}


async def recalculate(db) -> dict:
    pairs = await compute(db)
    _CACHE["pairs"] = pairs
    _CACHE["computed_at"] = time.time()
    return get_cached()
