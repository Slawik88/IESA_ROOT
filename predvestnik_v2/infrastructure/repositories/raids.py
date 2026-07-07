# infrastructure/repositories/raids.py — БЛОК19 Ч.6: клановые рейды (замена PvP).
# Лидер запускает рейд (босс с HP). Участники бьют боевыми питомцами: питомец наносит
# урон боссу и получает контр-урон (теряет HP). Победа → награды по доле урона + клан-XP.
import random
import time

from core.constants import (
    RAID_BOSS_HP_PER_MEMBER, RAID_BOSS_COUNTER_FRAC, RAID_DURATION_HOURS,
    RAID_ATTACK_COOLDOWN_MIN,
)
from infrastructure.repositories import pet_combat as combat_repo
from infrastructure.repositories import clans as clans_repo

_BOSSES = [
    ("Пожиратель Бездны", "👹"), ("Тень Древних", "👁"),
    ("Кровавый Левиафан", "🐙"), ("Колосс Пустоты", "🗿"), ("Багровый Жнец", "💀"),
]


async def close_expired(db) -> int:
    """Просроченные рейды (окно 48ч истекло, босс жив) → status='expired', наград нет.
    Раньше такие рейды зависали 'active' навсегда и блокировали запуск нового
    («У клана уже идёт рейд» без возможности отменить) — БЛОК 36.4."""
    async with db.execute(
        "UPDATE clan_raids SET status = 'expired' "
        "WHERE status = 'active' AND ends_at <= NOW() RETURNING raid_id"
    ) as c:
        rows = await c.fetchall()
    return len(rows)


async def _clan_id(db, user_id):
    clan = await clans_repo.get_user_clan(db, user_id)
    return clan["clan_id"] if clan else None, clan


async def get_active(db, user_id: int) -> dict | None:
    cid, clan = await _clan_id(db, user_id)
    if not cid:
        return None
    async with db.execute(
        "SELECT raid_id, boss_name, boss_emoji, hp, hp_max, status, "
        "EXTRACT(EPOCH FROM ends_at)::float8 AS ends_ts FROM clan_raids "
        "WHERE clan_id = ? AND status = 'active' ORDER BY raid_id DESC LIMIT 1",
        (cid,),
    ) as c:
        r = await c.fetchone()
    if not r:
        return {"clan": clan, "raid": None, "is_leader": clan["role"] == "owner"}
    raid = dict(r)
    async with db.execute(
        "SELECT rc.user_id, rc.damage, u.user_tg_username AS username "
        "FROM raid_contributions rc LEFT JOIN users u ON u.user_tg_id = rc.user_id "
        "WHERE rc.raid_id = ? ORDER BY rc.damage DESC LIMIT 15",
        (raid["raid_id"],),
    ) as c:
        contribs = [dict(x) for x in await c.fetchall()]
    return {"clan": clan, "raid": raid, "contribs": contribs,
            "is_leader": clan["role"] == "owner",
            "ends_in": max(0, int(raid["ends_ts"] - time.time()))}


async def start(db, user_id: int) -> tuple[bool, str]:
    try:
        async with db.connection.transaction():
            cid, clan = await _clan_id(db, user_id)
            if not cid:
                return False, "Ты не в клане."
            if clan["role"] != "owner":
                return False, "Запустить рейд может только лидер клана."
            async with db.execute(
                "SELECT 1 FROM clan_raids WHERE clan_id = ? AND status = 'active'", (cid,)
            ) as c:
                if await c.fetchone():
                    return False, "У клана уже идёт рейд."
            async with db.execute(
                "SELECT COUNT(*) FROM clan_members WHERE clan_id = ?", (cid,)
            ) as c:
                members = (await c.fetchone())[0] or 1
            hp = float(RAID_BOSS_HP_PER_MEMBER * members)
            name, emoji = random.choice(_BOSSES)
            await db.execute(
                "INSERT INTO clan_raids (clan_id, boss_name, boss_emoji, hp, hp_max, ends_at) "
                "VALUES (?, ?, ?, ?, ?, NOW() + (? || ' hours')::interval)",
                (cid, name, emoji, hp, hp, str(RAID_DURATION_HOURS)),
            )
        return True, f"{emoji} Рейд начат! Босс «{name}» — {hp:.0f} HP. Зовите клан в бой!"
    except Exception as e:
        return False, f"Ошибка: {e}"


async def attack(db, user_id: int, pet_id: int) -> tuple[bool, str]:
    try:
        async with db.connection.transaction():
            cid, clan = await _clan_id(db, user_id)
            if not cid:
                return False, "Ты не в клане."
            async with db.execute(
                "SELECT raid_id, boss_name, hp, hp_max FROM clan_raids "
                "WHERE clan_id = ? AND status = 'active' FOR UPDATE", (cid,)
            ) as c:
                raid = await c.fetchone()
            if not raid:
                return False, "Нет активного рейда."
            rid, boss_name, boss_hp, boss_hp_max = raid[0], raid[1], float(raid[2]), float(raid[3])
            # КД атаки
            async with db.execute(
                "SELECT EXTRACT(EPOCH FROM last_attack_at) FROM raid_contributions "
                "WHERE raid_id = ? AND user_id = ?", (rid, user_id)
            ) as c:
                lr = await c.fetchone()
            now = time.time()
            if lr and lr[0] and (now - lr[0]) < RAID_ATTACK_COOLDOWN_MIN * 60:
                left = int((RAID_ATTACK_COOLDOWN_MIN * 60 - (now - lr[0])) / 60) + 1
                return False, f"Питомец переводит дух. До следующей атаки ~{left} мин."
            # питомец (не во Вратах/экспедиции)
            async with db.execute("SELECT 1 FROM shadow_gate_runs WHERE pet_id = ?", (pet_id,)) as c:
                if await c.fetchone():
                    return False, "Питомец во Вратах."
            async with db.execute("SELECT 1 FROM active_expeditions WHERE pet_id = ?", (pet_id,)) as c:
                if await c.fetchone():
                    return False, "Питомец в экспедиции."
            st = await combat_repo.lock_state(db, pet_id, owner_id=user_id)
            if not st:
                return False, "Питомец не найден."
            if st["hp"] <= 0:
                return False, "У питомца 0 HP — вылечи его."
            dmg = float(st["attack"])
            counter = max(1.0, dmg * RAID_BOSS_COUNTER_FRAC - st["defense"] * 0.5)
            new_boss = max(0.0, boss_hp - dmg)
            new_pet_hp = max(0.0, st["hp"] - counter)
            await combat_repo.persist(db, pet_id, new_pet_hp, st["stamina"], st["hp_max"],
                                      st["stamina_max"], st["attack"], st["defense"])
            await db.execute("UPDATE clan_raids SET hp = ? WHERE raid_id = ?", (new_boss, rid))
            await db.execute(
                "INSERT INTO raid_contributions (raid_id, user_id, damage, last_attack_at) "
                "VALUES (?, ?, ?, to_timestamp(?)) "
                "ON CONFLICT (raid_id, user_id) DO UPDATE SET "
                "damage = raid_contributions.damage + ?, last_attack_at = to_timestamp(?)",
                (rid, user_id, dmg, now, dmg, now),
            )
            await db.execute(
                "UPDATE clans SET total_xp = total_xp + ? WHERE clan_id = ?",
                (int(dmg / 10), cid),
            )
            if new_boss <= 0:
                reward = await _defeat(db, rid, boss_hp_max)
                return True, f"💥 Урон {dmg:.0f}. БОСС «{boss_name}» ПОВЕРЖЕН! Награды розданы (твоя: +{reward:.0f} 🪙). Питомцу −{counter:.0f} HP."
            pct = int(new_boss / boss_hp_max * 100)
            return True, f"💥 Урон {dmg:.0f}! Босс: {new_boss:.0f}/{boss_hp_max:.0f} ({pct}%). Питомцу −{counter:.0f} HP."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def _defeat(db, raid_id: int, boss_hp_max: float) -> float:
    """Босс повержен: статус done, награды контрибьюторам по доле урона. → награда автора-вызова (для сообщения)."""
    await db.execute("UPDATE clan_raids SET status = 'done', hp = 0 WHERE raid_id = ?", (raid_id,))
    async with db.execute(
        "SELECT user_id, damage FROM raid_contributions WHERE raid_id = ?", (raid_id,)
    ) as c:
        contribs = [(r[0], float(r[1])) for r in await c.fetchall()]
    total = sum(d for _, d in contribs) or 1.0
    pool = boss_hp_max * 0.6  # пул Моры
    my_reward = 0.0
    for uid, dmg in contribs:
        reward = round(pool * (dmg / total), 0)
        if reward > 0:
            await db.execute(
                "UPDATE users SET user_balance_mora = user_balance_mora + ? WHERE user_tg_id = ?",
                (reward, uid),
            )
        my_reward = reward  # последнее значение — для бьющего (он точно в списке)
    return my_reward
