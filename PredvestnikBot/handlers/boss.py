"""
⚔️ Система Босса — глобальная битва с мировым боссом.

Команды:
  бот босс          — текущий статус босса (HP, топ урона)
  бот босс атака    — нанести удар боссу (через чат)

Эндпоинт (Mini App):
  POST /api/boss/submit_damage  — принять урон из Mini App (батч, с анти-читом)
"""

import asyncio
import html
import logging
import random
import time
from datetime import datetime, timezone

from aiogram import Router
from aiogram.types import Message

from database.db import add_boss_damage, add_mora, get_boss_leaderboard, get_boss_my_damage
from filters.bot_command import BotCommand

router = Router()
log = logging.getLogger(__name__)

# ─── In-memory состояние босса ────────────────────────────────────────────────

BOSS_MAX_HP = 500_000

# chat_id → current HP
_boss_hp: dict[int, int] = {}

# (user_id, chat_id) → last_attack_ts  (анти-флуд: 1 атака в 30 сек)
_attack_cooldown: dict[tuple, float] = {}

# In-memory buffer для батч-сохранения из Mini App
# (user_id, chat_id) → accumulated damage this window
_damage_buffer: dict[tuple, int] = {}
_last_flush = time.time()
_FLUSH_INTERVAL = 60  # секунд


def get_boss_hp(chat_id: int) -> int:
    return _boss_hp.get(chat_id, BOSS_MAX_HP)


def apply_damage(chat_id: int, damage: int) -> int:
    """Применить урон к боссу чата. Возвращает новый HP (≥ 0)."""
    current = _boss_hp.get(chat_id, BOSS_MAX_HP)
    new_hp = max(0, current - damage)
    _boss_hp[chat_id] = new_hp
    return new_hp


def _calc_damage(atk: int = 100, crit_rate: float = 0.05) -> int:
    """Рассчитать урон с учётом крита."""
    base = random.randint(int(atk * 0.8), int(atk * 1.2))
    if random.random() < crit_rate:
        base = int(base * 1.5)
    return base


def _hp_bar(current: int, max_hp: int = BOSS_MAX_HP, width: int = 20) -> str:
    pct = max(0, min(1.0, current / max_hp))
    filled = int(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {int(pct * 100)}%"


# ─── Батч-сохранение буфера (вызывается из планировщика) ─────────────────────

async def flush_damage_buffer():
    """Сохранить накопленный урон из буфера в БД (batch)."""
    global _last_flush
    if not _damage_buffer:
        _last_flush = time.time()
        return
    snapshot = dict(_damage_buffer)
    _damage_buffer.clear()
    _last_flush = time.time()
    for (uid, cid), dmg in snapshot.items():
        try:
            await add_boss_damage(uid, cid, dmg)
        except Exception as e:
            log.warning("Boss buffer flush error uid=%s cid=%s: %s", uid, cid, e)


def buffer_damage(user_id: int, chat_id: int, damage: int):
    """Добавить урон в in-memory буфер."""
    key = (user_id, chat_id)
    _damage_buffer[key] = _damage_buffer.get(key, 0) + damage


# Анти-чит: максимальный урон за одну сессию Mini App (30 сек)
_MAX_SESSION_DAMAGE = 50_000


def validate_session_damage(damage: int) -> bool:
    """Проверить что урон из Mini App не превышает лимит (анти-чит)."""
    return 0 < damage <= _MAX_SESSION_DAMAGE


# ─── бот босс ─────────────────────────────────────────────────────────────────

@router.message(BotCommand("босс", "boss", "мировой босс"))
async def cmd_boss(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("⚔️ Босс доступен только в группах!")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    arg = (cmd_args or "").strip().lower()

    current_hp = get_boss_hp(chat_id)
    pct = current_hp / BOSS_MAX_HP * 100

    # Атака
    if arg in ("атака", "атаковать", "attack", "удар"):
        now = time.time()
        cooldown_key = (uid, chat_id)
        last = _attack_cooldown.get(cooldown_key, 0)
        if now - last < 30:
            wait = int(30 - (now - last))
            await message.answer(f"⏳ Следующая атака через <b>{wait} сек.</b>", parse_mode="HTML")
            return

        dmg = _calc_damage(atk=100, crit_rate=0.05)
        new_hp = apply_damage(chat_id, dmg)
        _attack_cooldown[cooldown_key] = now

        # Сохранить в буфер
        buffer_damage(uid, chat_id, dmg)

        reward = max(5, dmg // 20)
        await add_mora(uid, chat_id, reward)

        bar = _hp_bar(new_hp)
        defeated = new_hp == 0

        lines = [
            f"⚔️ <b>Атака по Боссу!</b>",
            f"",
            f"💥 Урон: <b>{dmg}</b>",
            f"💰 Награда: <b>+{reward} 🪙</b>",
            f"",
            f"👹 <b>Мировой Босс</b>",
            f"❤️ {bar}",
            f"HP: {new_hp:,} / {BOSS_MAX_HP:,}",
        ]

        if defeated:
            lines += ["", "🎉 <b>БОСС ПОВЕРЖЕН!</b> Мора распределена среди участников!"]
            # Восстановить HP для нового раунда
            _boss_hp[chat_id] = BOSS_MAX_HP
            # Сохранить накопленный буфер
            await flush_damage_buffer()

        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    # Статус босса
    top = await get_boss_leaderboard(chat_id, limit=5)
    my_dmg = await get_boss_my_damage(uid, chat_id)
    bar = _hp_bar(current_hp)

    lines = [
        f"👹 <b>Мировой Босс</b>",
        f"",
        f"❤️ {bar}",
        f"HP: {current_hp:,} / {BOSS_MAX_HP:,}",
        f"",
        f"⚔️ Атаковать: <code>бот босс атака</code> (раз в 30 сек)",
        f"📱 Или бей в <b>Mini App</b> (30-сек сессии)",
        f"",
    ]

    if top:
        lines.append("🏆 <b>Топ урона:</b>")
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, row in enumerate(top):
            name = html.escape(row.get("full_name") or str(row["user_id"]))
            lines.append(f"  {medals[i]} {name} — {row['total_damage']:,}")

    if my_dmg:
        lines += ["", f"💪 Твой урон: <b>{my_dmg:,}</b>"]

    await message.answer("\n".join(lines), parse_mode="HTML")
