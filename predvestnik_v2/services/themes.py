"""Theme catalog and direct-purchase domain service.

Effective metadata is ``core/themes.py`` plus an optional DB override.  Direct
theme acquisition is deliberately owned here, rather than by a web or Telegram
adapter: the ownership claim and the ledger debit must either both commit or
both roll back.

No bot.*/FastAPI.* imports.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from core.economy_contract import EconomyContractError, IdempotencyConflict, InsufficientBalance
from core.themes import THEMES
from infrastructure.repositories.economy_ledger import (
    apply_balance_change,
    find_reference_replay,
)
from infrastructure.repositories import theme_meta as meta_repo

_PRICE_FIELDS = ("name", "rarity", "source", "price_mora", "price_diamonds",
                 "price_zarniki", "price_dark")

# Direct source → immutable debit currency and the only price field that may be
# read for it.  An adapter still chooses which sources it exposes; this mapping
# prevents a client from selecting a price or currency.
DIRECT_THEME_PRICES = {
    "shop_mora": ("mora", "price_mora"),
    "shop_diamond": ("diamonds", "price_diamonds"),
    "zarniki": ("zarniki", "price_zarniki"),
    "dark": ("dark_mora", "price_dark"),
}
WEB_DIRECT_THEME_SOURCES = frozenset({"zarniki", "dark"})


class ThemePurchaseError(ValueError):
    """A player-safe rejection for a direct theme purchase."""


@dataclass(frozen=True, slots=True)
class ThemePurchaseResult:
    theme_id: str
    theme_name: str
    applied: bool
    replayed: bool = False
    already_owned: bool = False


def _merge(base: dict, override: dict | None) -> dict:
    if not override:
        return base
    merged = dict(base)
    for f in _PRICE_FIELDS:
        if override.get(f) is not None:
            merged[f] = override[f]
    if override.get("obtainable_bp") is not None:
        merged["obtainable_bp"] = bool(override["obtainable_bp"])
    if override.get("description"):
        merged["desc"] = override["description"]
    return merged


async def get_effective_theme(db, theme_id: str) -> dict | None:
    """THEMES[theme_id] с ценой/редкостью/описанием, перекрытыми DB-оверрайдом (если есть)."""
    base = THEMES.get(theme_id)
    if not base:
        return None
    override = await meta_repo.get_override(db, theme_id)
    return _merge(base, override)


async def get_all_effective_themes(db) -> dict[str, dict]:
    """Все темы из THEMES с применёнными DB-оверрайдами — для каталога/витрины."""
    overrides = await meta_repo.get_all_overrides(db)
    return {tid: _merge(t, overrides.get(tid)) for tid, t in THEMES.items()}


def _direct_theme_quote(theme: dict) -> tuple[str, Decimal, str]:
    """Return the server-owned (currency, amount, source) for one direct theme."""
    source = str(theme.get("source") or "")
    price_spec = DIRECT_THEME_PRICES.get(source)
    if not price_spec:
        raise ThemePurchaseError(
            "Эта тема не продаётся напрямую. Получите её через событие или другой источник."
        )
    currency, price_field = price_spec
    try:
        amount = Decimal(str(theme.get(price_field)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ThemePurchaseError("У темы не задана корректная цена.") from exc
    if not amount.is_finite() or amount <= 0:
        raise ThemePurchaseError("У темы не задана корректная цена.")
    return currency, amount, source


async def _lock_theme_user(db, user_id: int) -> None:
    """Serialize a paid claim with every other durable player-state writer."""
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
    )
    async with db.execute(
        "SELECT 1 FROM users WHERE user_tg_id = ? FOR UPDATE", (user_id,)
    ) as cursor:
        await cursor.fetchone()


async def purchase_direct_theme(
    db,
    user_id: int,
    theme_id: str,
    *,
    idempotency_key: str,
    allowed_sources: frozenset[str] | set[str] | None = None,
) -> ThemePurchaseResult:
    """Atomically claim one directly sold theme and debit its server price.

    The ownership insert intentionally happens before the debit in one outer
    transaction.  A concurrent reward or second purchase can therefore win the
    claim without charging twice; any debit failure rolls the claim back.
    """
    theme = await get_effective_theme(db, theme_id)
    if not theme:
        raise ThemePurchaseError("Тема не найдена.")
    currency, amount, source = _direct_theme_quote(theme)
    if allowed_sources is not None and source not in allowed_sources:
        raise ThemePurchaseError(
            "Этот каталог закрыт. Уже полученные темы сохранены в коллекции."
        )

    deltas = {currency: -amount}
    metadata = {
        "theme_id": theme_id,
        "theme_name": str(theme.get("name") or theme_id),
        "source": source,
        "currency": currency,
        "price": str(amount),
    }
    try:
        async with db.connection.transaction():
            await _lock_theme_user(db, user_id)
            replay = await find_reference_replay(
                db,
                user_id,
                reason_code="theme_purchase",
                idempotency_key=idempotency_key,
                source_type="themes",
                reference_type="profile_theme",
                reference_id=theme_id,
            )
            if replay is not None:
                return ThemePurchaseResult(
                    theme_id=theme_id,
                    theme_name=str(theme.get("name") or theme_id),
                    applied=False,
                    replayed=True,
                )

            async with db.execute(
                "INSERT INTO user_themes (user_id, theme_id) VALUES (?, ?) "
                "ON CONFLICT (user_id, theme_id) DO NOTHING RETURNING theme_id",
                (user_id, theme_id),
            ) as cursor:
                claimed = await cursor.fetchone()
            if not claimed:
                return ThemePurchaseResult(
                    theme_id=theme_id,
                    theme_name=str(theme.get("name") or theme_id),
                    applied=False,
                    already_owned=True,
                )

            await apply_balance_change(
                db,
                user_id,
                deltas,
                reason_code="theme_purchase",
                idempotency_key=idempotency_key,
                source_type="themes",
                reference_type="profile_theme",
                reference_id=theme_id,
                metadata=metadata,
                note=theme_id,
            )
    except InsufficientBalance as exc:
        raise ThemePurchaseError("Недостаточно средств для этой темы.") from exc
    except IdempotencyConflict as exc:
        raise ThemePurchaseError("Этот запрос уже использован для другой покупки.") from exc
    except EconomyContractError as exc:
        raise ThemePurchaseError("Параметры покупки не прошли проверку. Откройте тему заново.") from exc

    return ThemePurchaseResult(
        theme_id=theme_id,
        theme_name=str(theme.get("name") or theme_id),
        applied=True,
    )
