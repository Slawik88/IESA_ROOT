"""
services/onboarding.py — стартовый набор новичка (Implementation Block 10).

Выдаётся РОВНО один раз на игрока. Защита — атомарный флаг users.onboarded:
колонка создана с DEFAULT TRUE (все существующие игроки уже «онбордингованы»
и набор НЕ получат), новые игроки вставляются с onboarded=FALSE (см.
users.update_user). Условный UPDATE ... WHERE onboarded=FALSE RETURNING делает
выдачу идемпотентной даже при гонке параллельных сообщений.
"""
import random

from core.registry import PET_SPECIES
from infrastructure.repositories import economy as eco_repo
from infrastructure.repositories.zoo import grant_duplicate

STARTER_MORA: float = 1000.0
STARTER_DIAMONDS: float = 8.0      # хватает на 1 спин алмазного режима (8 💎)
STARTER_SPIN_TOKENS: int = 1       # 1 бесплатный спин мора-режима


async def grant_starter_kit(db, user_id: int) -> dict | None:
    """Выдать стартовый набор, если игрок ещё не онбордингован.

    Возвращает dict с описанием выданного (для приветствия) или None, если
    набор уже выдавался ранее.
    """
    try:
        # Атомарный guard: переключаем FALSE→TRUE только у одного вызова.
        async with db.execute(
            "UPDATE users SET onboarded = TRUE "
            "WHERE user_tg_id = ? AND onboarded = FALSE RETURNING user_tg_id",
            (user_id,),
        ) as c:
            if not await c.fetchone():
                return None

        await eco_repo.add_balance(
            db, user_id, mora=STARTER_MORA, diamonds=STARTER_DIAMONDS,
            commit=False, source="onboarding",
        )
        await eco_repo.add_item(db, user_id, "spin_token", STARTER_SPIN_TOKENS)

        commons = [s for s, d in PET_SPECIES.items() if d.get("rarity") == "common"]
        species = random.choice(commons) if commons else "hamster"
        # initial_placement="active": игрок только что зарегистрирован, активного
        # питомца ещё нет — сразу ставим сюда, чтобы «бот поход» из справки
        # работал с первой попытки (Growth-полиш 2026-07-13, находка 02).
        await grant_duplicate(db, user_id, species, initial_placement="active")

        await db.commit()
        return {
            "mora": STARTER_MORA,
            "diamonds": STARTER_DIAMONDS,
            "spin_tokens": STARTER_SPIN_TOKENS,
            "species": species,
            "species_name": PET_SPECIES.get(species, {}).get("name", species),
        }
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        return None
