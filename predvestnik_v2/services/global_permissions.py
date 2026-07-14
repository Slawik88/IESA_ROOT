# services/global_permissions.py
# Эффективные права глобальных рангов (БЛОК 21.2): реестр-дефолты из
# core/admin_permissions.py + БД-оверрайды. Единая точка проверки для бота И сайта.
# Без bot.* / FastAPI.* импортов.

import time

from core.admin_permissions import ADMIN_PERMISSIONS, PERMISSION_GROUPS, default_perms_for_rank
from infrastructure.repositories import global_permissions as perm_repo

# Кэш эффективных наборов по рангам: консоль дёргает API пачками, а оверрайды
# меняются редко. TTL короткий, чтобы правка прав применялась быстро и во
# втором процессе (бот и веб — разные процессы с разными кэшами).
_CACHE_TTL = 20.0
_cache: dict[int, tuple[set[str], float]] = {}
_table_ready = False


async def _ensure(db) -> None:
    global _table_ready
    if not _table_ready:
        await perm_repo.ensure_table(db)
        _table_ready = True


def invalidate_cache() -> None:
    _cache.clear()


async def effective_perms(db, rank: int) -> set[str]:
    """Права ранга: дефолты реестра + оверрайды БД. Ранг 3 — всегда всё."""
    rank = rank or 0
    if rank >= 3:
        return set(ADMIN_PERMISSIONS)
    if rank < 1:
        return set()
    hit = _cache.get(rank)
    now = time.monotonic()
    if hit and hit[1] > now:
        return set(hit[0])
    await _ensure(db)
    perms = default_perms_for_rank(rank)
    for key, allowed in (await perm_repo.get_overrides(db, rank)).items():
        meta = ADMIN_PERMISSIONS.get(key)
        if not meta or meta.get("locked"):
            continue   # неизвестные/запертые ключи в БД игнорируем
        (perms.add if allowed else perms.discard)(key)
    _cache[rank] = (set(perms), now + _CACHE_TTL)
    return perms


async def has_perm(db, rank: int, key: str) -> bool:
    return key in await effective_perms(db, rank)


async def can_sanction(db, actor_rank: int, target_type: str, sanction_type: str,
                       target_global_rank: int = 0) -> bool:
    """Замена roles.can_issue_global_sanction с настраиваемыми правами.
    Антипир незыблем: нельзя тронуть цель с global_rank >= своего
    (в т.ч. Разработчик иммунен сам к себе — желаемый побочный эффект)."""
    if target_type == "user" and target_global_rank >= actor_rank:
        return False
    return await has_perm(db, actor_rank, f"sanction_{sanction_type}_{target_type}")


async def set_rank_perm(db, rank: int, key: str, allowed) -> tuple[bool, str]:
    """Оверрайд права ранга. allowed: True/False, None = сброс к дефолту.
    Возвращает (ok, message)."""
    if rank not in (1, 2):
        return False, "Настраиваются только ранги 1 (Хелпер) и 2 (Ст. хелпер)."
    meta = ADMIN_PERMISSIONS.get(key)
    if not meta:
        return False, f"Неизвестное право: {key}"
    if meta.get("locked"):
        return False, f"«{meta['label']}» — только у Разработчика, не настраивается."
    await _ensure(db)
    if allowed is None:
        await perm_repo.clear_override(db, rank, key)
    else:
        await perm_repo.set_override(db, rank, key, bool(allowed))
    invalidate_cache()
    return True, "OK"


async def registry_with_effective(db) -> dict:
    """Для UI матрицы прав: реестр (группы/ярлыки/дефолты/locked) + эффективные
    наборы рангов 1 и 2 + отметка, где стоит оверрайд."""
    await _ensure(db)
    overrides = await perm_repo.get_all_overrides(db)
    eff = {1: await effective_perms(db, 1), 2: await effective_perms(db, 2)}
    items = []
    for key, meta in ADMIN_PERMISSIONS.items():
        items.append({
            "key": key, "label": meta["label"], "group": meta["group"],
            "default": meta["default"], "locked": bool(meta.get("locked")),
            "rank1": key in eff[1], "rank2": key in eff[2],
            "rank1_override": key in overrides.get(1, {}),
            "rank2_override": key in overrides.get(2, {}),
        })
    return {"groups": PERMISSION_GROUPS, "items": items}
