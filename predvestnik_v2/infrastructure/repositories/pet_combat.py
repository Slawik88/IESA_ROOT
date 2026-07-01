# infrastructure/repositories/pet_combat.py — БЛОК19 Ч.4: боевое состояние питомцев.
# HP/Stamina хранятся на pets; реконсиляция (time-based реген) — на лету.
import time

from services.pet_combat import combat_stats, reconcile


async def ensure_tables(db) -> None:
    """Идемпотентно: combat-поля питомцев + таблицы Врат/Рейдов (для веб-процесса)."""
    for stmt in (
        "ALTER TABLE pets ADD COLUMN IF NOT EXISTS hp FLOAT8",
        "ALTER TABLE pets ADD COLUMN IF NOT EXISTS hp_max FLOAT8",
        "ALTER TABLE pets ADD COLUMN IF NOT EXISTS stamina FLOAT8",
        "ALTER TABLE pets ADD COLUMN IF NOT EXISTS stamina_max FLOAT8",
        "ALTER TABLE pets ADD COLUMN IF NOT EXISTS attack INTEGER DEFAULT 0",
        "ALTER TABLE pets ADD COLUMN IF NOT EXISTS defense INTEGER DEFAULT 0",
        "ALTER TABLE pets ADD COLUMN IF NOT EXISTS combat_regen_at TIMESTAMP",
    ):
        await db.execute(stmt)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS shadow_gate_runs (
            pet_id INTEGER PRIMARY KEY, user_id BIGINT NOT NULL,
            started_at TIMESTAMP DEFAULT NOW(), last_tick_at TIMESTAMP DEFAULT NOW(),
            dark_mora FLOAT8 DEFAULT 0, hp FLOAT8 NOT NULL DEFAULT 0,
            hp_max FLOAT8 NOT NULL DEFAULT 0, rarity TEXT DEFAULT 'common',
            status TEXT DEFAULT 'active'
        )
    """)
    # Миграция: добавить колонки, которых не было в старых версиях таблицы
    for _col in (
        "ALTER TABLE shadow_gate_runs ADD COLUMN IF NOT EXISTS hp FLOAT8 NOT NULL DEFAULT 0",
        "ALTER TABLE shadow_gate_runs ADD COLUMN IF NOT EXISTS hp_max FLOAT8 NOT NULL DEFAULT 0",
        "ALTER TABLE shadow_gate_runs ADD COLUMN IF NOT EXISTS rarity TEXT DEFAULT 'common'",
    ):
        await db.execute(_col)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clan_raids (
            raid_id SERIAL PRIMARY KEY, clan_id INTEGER NOT NULL, boss_name TEXT NOT NULL,
            boss_emoji TEXT DEFAULT '👹', hp FLOAT8 NOT NULL, hp_max FLOAT8 NOT NULL,
            status TEXT DEFAULT 'active', started_at TIMESTAMP DEFAULT NOW(),
            ends_at TIMESTAMP NOT NULL, last_threshold INTEGER DEFAULT 100
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS raid_contributions (
            raid_id INTEGER NOT NULL, user_id BIGINT NOT NULL, damage FLOAT8 DEFAULT 0,
            last_attack_at TIMESTAMP, PRIMARY KEY (raid_id, user_id)
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_clan_raids_clan ON clan_raids(clan_id, status)")


_SELECT = (
    "SELECT id, owner_id, name, species_id, rarity, COALESCE(pet_level,1) AS lvl, "
    "placement, hp, hp_max, stamina, stamina_max, attack, defense, "
    "EXTRACT(EPOCH FROM combat_regen_at) AS regen_ts FROM pets WHERE id = ?"
)


def _hydrate(p: dict) -> dict:
    """Дополняем боевые поля (если NULL — инициализируем из combat_stats), реконсилим
    HP/Stamina на текущий момент. Возвращает актуальный снимок (без записи в БД)."""
    stats = combat_stats(p["rarity"], p["lvl"])
    # Максимумы/atk/def всегда пересчитываем из редкости×уровня (уровень мог вырасти).
    hp_max, st_max = stats["hp_max"], stats["stamina_max"]
    if p["hp_max"] is None:                 # ни разу не использовался как боевой
        hp, stamina, ts = hp_max, st_max, time.time()
    else:
        hp, stamina = reconcile(p["hp"] or 0, hp_max, p["stamina"] or 0, st_max,
                                p["regen_ts"] or time.time())
        ts = time.time()
    return {
        "pet_id": p["id"], "owner_id": p["owner_id"], "name": p["name"],
        "species_id": p["species_id"], "rarity": p["rarity"], "level": p["lvl"],
        "placement": p["placement"],
        "hp": round(hp, 1), "hp_max": hp_max, "stamina": round(stamina, 1),
        "stamina_max": st_max, "attack": stats["attack"], "defense": stats["defense"],
        "alive": hp > 0, "_ts": ts,
    }


async def get_state(db, pet_id: int, owner_id: int | None = None) -> dict | None:
    """Снимок боевого состояния (read-only, реконсилированный). Без блокировки/записи."""
    async with db.execute(_SELECT, (pet_id,)) as c:
        r = await c.fetchone()
    if not r:
        return None
    p = dict(r)
    if owner_id is not None and p["owner_id"] != owner_id:
        return None
    return _hydrate(p)


async def lock_state(db, pet_id: int, owner_id: int | None = None) -> dict | None:
    """То же, но под FOR UPDATE — ВЫЗЫВАТЬ ВНУТРИ ТРАНЗАКЦИИ. Состояние НЕ записано;
    после изменения hp/stamina вызвать persist()."""
    async with db.execute(_SELECT + " FOR UPDATE", (pet_id,)) as c:
        r = await c.fetchone()
    if not r:
        return None
    p = dict(r)
    if owner_id is not None and p["owner_id"] != owner_id:
        return None
    return _hydrate(p)


async def persist(db, pet_id: int, hp: float, stamina: float,
                  hp_max: float, stamina_max: float, attack: int, defense: int) -> None:
    """Записать боевое состояние (combat_regen_at = сейчас = «как от» этого hp/stamina)."""
    await db.execute(
        "UPDATE pets SET hp = ?, hp_max = ?, stamina = ?, stamina_max = ?, "
        "attack = ?, defense = ?, combat_regen_at = to_timestamp(?) WHERE id = ?",
        (max(0.0, hp), hp_max, max(0.0, stamina), stamina_max,
         int(attack), int(defense), time.time(), pet_id),
    )
