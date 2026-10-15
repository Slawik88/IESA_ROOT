"""Промокоды глазами игрока: коды, которые ему можно показать, и его история активаций. Только чтение."""
from __future__ import annotations

from typing import Any

HISTORY_LIMIT = 50


async def offered_codes(db: Any, user_id: int) -> list[tuple]:
    """Кандидаты в «Доступно сейчас»: включённые коды нового формата без привязки к чатам, ещё не активированные игроком,
    отмеченные «показывать в Mini App» или именные с его ID (LIKE — только отсев, точную проверку списка делает сервис)."""
    async with db.execute(
        "SELECT p.code, p.valid_from, p.valid_until, p.max_activations, p.activations_count, p.allowed_users_json, "
        "p.rewards_json, COALESCE(p.show_in_app, FALSE) "
        "FROM promocodes p WHERE p.is_active = 1 AND p.rewards_json IS NOT NULL "
        "AND COALESCE(p.allowed_chats_json, '') = '' "
        "AND (COALESCE(p.show_in_app, FALSE) OR COALESCE(p.allowed_users_json, '') LIKE ?) "
        "AND NOT EXISTS (SELECT 1 FROM promocode_redemptions r WHERE r.code = p.code AND r.user_id = ?) "
        "ORDER BY p.valid_until NULLS LAST, p.created_at DESC NULLS LAST LIMIT 100",
        (f"%{int(user_id)}%", int(user_id))) as cur:
        return list(await cur.fetchall())


async def history(db: Any, user_id: int) -> list[tuple]:
    async with db.execute(
        "SELECT code, redeemed_at, rewards_json, chat_id FROM promocode_redemptions WHERE user_id = ? "
        "ORDER BY redeemed_at DESC NULLS LAST LIMIT ?", (int(user_id), HISTORY_LIMIT)) as cur:
        return list(await cur.fetchall())
