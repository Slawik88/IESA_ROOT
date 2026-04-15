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

from aiogram import Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import MINI_APP_TG_URL
from database.db import add_boss_damage, get_boss_leaderboard, get_boss_my_damage
from filters.bot_command import BotCommand

from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())

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
_flush_lock: asyncio.Lock | None = None  # инициализуется при первом вызове


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
    global _last_flush, _flush_lock
    if _flush_lock is None:
        _flush_lock = asyncio.Lock()
    if _flush_lock.locked():
        return  # предыдущий флаш ещё не завершён — пропустить
    async with _flush_lock:
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
    """Мировой Босс — только в Mini App."""
    abs_cid = abs(message.chat.id) if message.chat.type != "private" else 0
    btn = InlineKeyboardButton(
        text="⚔️ Открыть Босса в Mini App",
        url=f"{MINI_APP_TG_URL}?startapp={abs_cid}_boss",
    )
    await message.answer(
        "👹 <b>Мировой Босс</b>\n\n"
        "Атаки на Босса, лидерборд и статус HP — в <b>Mini App</b>!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
    )
