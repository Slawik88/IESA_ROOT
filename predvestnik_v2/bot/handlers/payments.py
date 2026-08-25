# bot/handlers/payments.py
"""Покупка ✨ Зарников за Telegram Stars (XTR).

The invoice payload is an accounting contract, not just a display hint.  It is
validated again when Telegram asks to confirm a payment, when it reports a
successful payment, and while recovering missed updates from the Stars
transaction history.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os

from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, CommandObject, BaseFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.types import LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from bot.filters.text_commands import TextCmd
from bot.keyboards.cta import dm_cta_kb
from infrastructure.repositories import economy as eco_db
from core.constants import STARS_PACKAGES, STARS_MOST_POPULAR
from core.payment_contract import (
    MAX_STARS as _MAX_STARS,
    STARS_CURRENCY as _STARS_CURRENCY,
    ZarnikiQuote,
    custom_quote as _custom_quote,
    invoice_payload as _invoice_payload,
    is_issuable_v1_quote as _is_issuable_v1_quote,
    package_quote as _package_quote,
    quote_from_paid_invoice as _quote_from_paid_invoice,
)
from infrastructure.preprod import is_preprod, stars_invoice_issuance_allowed

router = Router(name="payments_router")
_CUSTOM_AMOUNT_MARKER = "✏️ Введите количество ⭐ для покупки Зарников"
_RECONCILIATION_PAGE_SIZE = 100
_RECONCILIATION_INITIAL_MAX_PAGES = 100
_RECONCILIATION_PERIODIC_MAX_PAGES = 3
_RECONCILIATION_PERIOD_SECONDS = 5 * 60
@dataclass(frozen=True, slots=True)
class StarReconciliationResult:
    scanned: int = 0
    credited: int = 0
    replayed: int = 0
    invalid: int = 0
    failed: int = 0
    exhausted: bool = True


class BuyZarnikiCB(CallbackData, prefix="buyzar"):
    stars: int  # 0 = "своя сумма"


async def _send_zarniki_invoice(bot: Bot, user_id: int, quote: ZarnikiQuote) -> bool:
    """Send one Stars invoice using the same contract the receiver validates."""
    if not stars_invoice_issuance_allowed():
        logger.warning("Preprod blocked Stars invoice issuance for user {}", user_id)
        return False
    await bot.send_invoice(
        chat_id=user_id,
        title="Зарники ✨",
        description=f"{quote.zarniki}✨ Зарников для Предвестника",
        payload=_invoice_payload(quote),
        # Telegram's current Bot API explicitly requires an empty provider
        # token for Stars rather than an omitted third-party provider token.
        provider_token="",
        currency=_STARS_CURRENCY,
        prices=[LabeledPrice(label=f"{quote.zarniki}✨ Зарников", amount=quote.stars)],
    )
    return True


def _purchase_in_dm_keyboard():
    username = os.getenv("BOT_USERNAME", "IIIPredvestnikIIIBot")
    builder = InlineKeyboardBuilder()
    builder.button(text="✨ Купить Зарники в личном чате", url=f"https://t.me/{username}?start=buyzarniki")
    return builder.as_markup()


async def _redirect_purchase_to_dm(message: types.Message) -> None:
    await message.answer(
        "✨ Покупка Зарников доступна только в личном чате с ботом — "
        "так Telegram надёжно привяжет оплату к вашему аккаунту.",
        reply_markup=_purchase_in_dm_keyboard(),
    )


def _packages_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for stars, base, bonus in STARS_PACKAGES:
        total = base + bonus
        popular_mark = " 🔥" if stars == STARS_MOST_POPULAR else ""
        builder.button(
            text=f"{stars}⭐ → {total}✨{popular_mark}",
            callback_data=BuyZarnikiCB(stars=stars),
        )
    builder.button(text="✏️ Своя сумма", callback_data=BuyZarnikiCB(stars=0))
    builder.adjust(2)
    return builder


async def _send_packages_menu(message: types.Message):
    if getattr(message.chat, "type", None) != "private":
        return await _redirect_purchase_to_dm(message)
    lines = ["✨ <b>ЗАРНИКИ</b> — донат-валюта Предвестника\n"]
    for stars, base, bonus in STARS_PACKAGES:
        total = base + bonus
        popular = " — <b>самое популярное!</b> 🔥" if stars == STARS_MOST_POPULAR else ""
        lines.append(f"├ {stars}⭐ = {base} + {bonus} бонус = <b>{total}✨</b>{popular}")
    lines.append("\n💡 Своя сумма: 1⭐ = 10✨ (без бонуса)")
    text = "\n".join(lines)
    await message.answer(text, reply_markup=_packages_keyboard().as_markup(), parse_mode="HTML")


@router.message(TextCmd(["купить зарники", "донат"]))
async def cmd_buy_zarniki(message: types.Message):
    await _send_packages_menu(message)


@router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, db, bot: Bot):
    if command.args == "buyzarniki":
        return await _send_packages_menu(message)

    # UX_AUDIT Б1: первый экран бота — с действиями, а не голым текстом.
    await message.answer(
        "🌘 <b>Предвестник услышал тебя.</b>\n\n"
        "Я — бот для сообществ: модерация, профиль, экономика и Разлом колокола.\n\n"
        "Куда дальше — два пути:\n"
        "➕ <b>Добавь меня в группу</b> — игра идёт там. Команды пишутся словом "
        "«бот»: <code>бот помощь</code>\n"
        "🌐 <b>Открой мини-апп</b> — профиль, внешний вид и Разлом колокола\n\n"
        "🛠 <i>Предвестник находится в активной разработке: "
        "мы постепенно добавляем и улучшаем механики.</i>",
        reply_markup=dm_cta_kb(),
        parse_mode="HTML",
    )


@router.message(TextCmd(["рефералка", "пригласить друга", "реферальная ссылка"]))
async def cmd_referral_link(message: types.Message):
    """Explain the retired program without promising an unavailable reward."""
    await message.answer(
        "🤝 <b>Реферальная программа закрыта.</b>\n\n"
        "Новые приглашения не начисляют валюту, VIP или комиссию. "
        "Промокоды продолжают работать отдельно.",
        parse_mode="HTML",
    )


@router.callback_query(BuyZarnikiCB.filter())
async def cb_buy_package(query: types.CallbackQuery, callback_data: BuyZarnikiCB, bot: Bot):
    stars = callback_data.stars

    # Buttons created by an earlier version may still be present in a group.
    # A bot cannot start a private conversation itself, so guide the player to
    # the only deterministic purchase context instead of letting sendInvoice
    # fail after the checkout flow has begun.
    if getattr(getattr(query.message, "chat", None), "type", None) != "private":
        await _redirect_purchase_to_dm(query.message)
        await query.answer("Откройте покупку в личном чате с ботом.", show_alert=True)
        return

    if stars == 0:
        await query.message.answer(
            f"{_CUSTOM_AMOUNT_MARKER}\n\n"
            f"Ответьте на это сообщение количеством ⭐ (от 1 до {_MAX_STARS})."
        )
        return await query.answer()

    quote = _package_quote(stars)
    if not quote:
        # Callback data can outlive a package-list change.  Never turn an
        # unknown stale button into an unreviewed custom invoice.
        await query.answer("Этот пакет больше недоступен. Откройте список заново.", show_alert=True)
        return
    if not _is_issuable_v1_quote(quote):
        logger.critical("Current package tariff differs from frozen v1: stars={}, zarniki={}", stars, quote.zarniki)
        await query.answer("Покупка временно обновляется. Попробуйте чуть позже.", show_alert=True)
        return
    if not await _send_zarniki_invoice(bot, query.from_user.id, quote):
        await query.answer("Покупки Stars отключены на тестовом стенде.", show_alert=True)
        return
    await query.answer()


class _ZarnikiAmountReply(BaseFilter):
    """Реплай числом ⭐ на сообщение-маркер кастомной суммы.
    Возвращает False (passthrough) для любых других реплаев."""

    async def __call__(self, message: types.Message) -> bool:
        if getattr(message.chat, "type", None) != "private":
            return False
        reply = message.reply_to_message
        if not reply or not reply.text or _CUSTOM_AMOUNT_MARKER not in reply.text:
            return False
        return bool(message.text and message.text.strip().isdigit())


@router.message(_ZarnikiAmountReply())
async def msg_custom_zarniki_amount(message: types.Message, bot: Bot):
    if getattr(message.chat, "type", None) != "private":
        return await _redirect_purchase_to_dm(message)
    stars = int(message.text.strip())
    if not (1 <= stars <= _MAX_STARS):
        return await message.answer(f"⚠️ Введите число от 1 до {_MAX_STARS}.")

    quote = _custom_quote(stars)
    if not quote:  # defensive: the range check above is intentionally explicit for UX
        return await message.answer("⚠️ Не удалось определить сумму. Откройте покупку заново.")
    if not _is_issuable_v1_quote(quote):
        logger.critical("Current custom Stars tariff differs from frozen v1: stars={}, zarniki={}", stars, quote.zarniki)
        return await message.answer("⚠️ Покупка временно обновляется. Попробуйте чуть позже.")
    if not await _send_zarniki_invoice(bot, message.from_user.id, quote):
        return await message.answer("⚠️ Покупки Stars отключены на тестовом стенде.")


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    if is_preprod():
        await pre_checkout_query.answer(
            ok=False,
            error_message="Покупки Stars отключены на тестовом стенде.",
        )
        return
    quote = _quote_from_paid_invoice(
        pre_checkout_query.invoice_payload,
        pre_checkout_query.currency,
        pre_checkout_query.total_amount,
    )
    if quote:
        await pre_checkout_query.answer(ok=True)
    else:
        await pre_checkout_query.answer(
            ok=False,
            error_message="Параметры платежа не прошли проверку. Откройте покупку заново.",
        )


async def _credit_zarniki_payment(
    db,
    *,
    user_id: int,
    quote: ZarnikiQuote,
    payment_charge_id: str,
    payload: str,
    recovery: bool,
):
    """Record a valid Stars purchase exactly once in the canonical ledger."""
    return await eco_db.add_balance(
        db,
        user_id,
        zarniki=quote.zarniki,
        source="stars_purchase",
        note=f"{quote.stars}⭐",
        source_type="payment",
        idempotency_key=f"stars_purchase:{payment_charge_id}",
        reference_type="stars_payment",
        reference_id=payment_charge_id,
        metadata={
            "currency": _STARS_CURRENCY,
            "total_amount": quote.stars,
            "invoice_payload": payload,
            "payload_version": quote.version,
            "tariff_kind": quote.kind,
            "recovered_from_star_history": recovery,
        },
    )


async def reconcile_star_payments(
    bot: Bot,
    db,
    *,
    max_pages: int = _RECONCILIATION_INITIAL_MAX_PAGES,
) -> StarReconciliationResult:
    """Recover valid incoming Stars purchases absent from the local ledger.

    Telegram identifies an incoming transaction with the same id exposed in a
    ``SuccessfulPayment`` update.  Reusing that id as the ledger idempotency
    key means the normal update handler and this recovery pass may race safely:
    at most one of them can credit the player.

    ``getStarTransactions`` has offset pagination but no cursor.  A bounded
    pass protects process startup; hitting the bound is deliberately loud so
    operations can enlarge it before the history gap becomes invisible.
    """
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")

    scanned = credited = replayed = invalid = failed = 0
    offset = 0
    exhausted = True
    for _page in range(max_pages):
        history = await bot.get_star_transactions(
            offset=offset,
            limit=_RECONCILIATION_PAGE_SIZE,
        )
        transactions = list(getattr(history, "transactions", ()) or ())
        for transaction in transactions:
            scanned += 1
            source = getattr(transaction, "source", None)
            payload = getattr(source, "invoice_payload", None)
            if not isinstance(payload, str) or not payload.startswith("zarniki"):
                continue

            transaction_type = getattr(source, "transaction_type", None)
            user = getattr(source, "user", None)
            user_id = getattr(user, "id", None)
            charge_id = getattr(transaction, "id", None)
            quote = _quote_from_paid_invoice(
                payload,
                _STARS_CURRENCY,  # getStarTransactions contains Stars only
                getattr(transaction, "amount", None),
            )
            if (
                transaction_type != "invoice_payment"
                or not isinstance(user_id, int)
                or isinstance(user_id, bool)
                or not isinstance(charge_id, str)
                or not charge_id
                or not quote
            ):
                invalid += 1
                logger.critical(
                    "Stars history has an uncreditable zarniki transaction: id={}, user={}, "
                    "type={!r}, payload={!r}, amount={!r}",
                    charge_id,
                    user_id,
                    transaction_type,
                    payload,
                    getattr(transaction, "amount", None),
                )
                continue

            try:
                mutation = await _credit_zarniki_payment(
                    db,
                    user_id=user_id,
                    quote=quote,
                    payment_charge_id=charge_id,
                    payload=payload,
                    recovery=True,
                )
            except Exception:
                failed += 1
                logger.exception(
                    "Could not reconcile Stars transaction id={} for user={}", charge_id, user_id
                )
                continue

            if mutation and not mutation.applied:
                replayed += 1
                continue

            credited += 1
            try:
                await bot.send_message(
                    user_id,
                    f"✅ Автоматически восстановлено начисление <b>{quote.zarniki}✨</b> Зарников "
                    "по подтверждённой покупке Stars.",
                    parse_mode="HTML",
                )
            except Exception:
                logger.warning(
                    "Stars recovery credited charge={} but could not notify user={}", charge_id, user_id
                )

        if len(transactions) < _RECONCILIATION_PAGE_SIZE:
            break
        offset += len(transactions)
    else:
        exhausted = False
        logger.critical(
            "Stars reconciliation hit its {}-page safety limit; history may contain older "
            "unprocessed transactions. Increase the limit and inspect the ledger.",
            max_pages,
        )

    return StarReconciliationResult(
        scanned=scanned,
        credited=credited,
        replayed=replayed,
        invalid=invalid,
        failed=failed,
        exhausted=exhausted,
    )


async def star_payment_reconciliation_task(bot: Bot, pool) -> None:
    """Keep retrying authoritative Stars history without blocking update polling."""
    from infrastructure.pg_adapter import PGAdapter

    if is_preprod():
        logger.warning("Stars reconciliation is disabled on the isolated preprod stand.")
        return
    logger.info("Stars payment reconciliation task started.")
    run_number = 0
    while True:
        # The first and then every 72nd run performs a deep pass.  Intervening
        # passes cheaply cover the newest 300 transactions after a transient
        # database or worker failure.
        max_pages = (
            _RECONCILIATION_INITIAL_MAX_PAGES
            if run_number == 0 or run_number % 72 == 0
            else _RECONCILIATION_PERIODIC_MAX_PAGES
        )
        try:
            async with pool.acquire() as connection:
                result = await reconcile_star_payments(
                    bot,
                    PGAdapter(connection),
                    max_pages=max_pages,
                )
            if result.credited or result.failed or not result.exhausted:
                logger.info("Stars reconciliation result: {}", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Stars reconciliation pass failed")

        run_number += 1
        await asyncio.sleep(_RECONCILIATION_PERIOD_SECONDS)


@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message, db, bot: Bot):
    payment = message.successful_payment
    quote = _quote_from_paid_invoice(
        payment.invoice_payload,
        payment.currency,
        payment.total_amount,
    )
    if not quote:
        logger.critical(
            "Refused successful Stars payment with invalid contract: user={}, charge={}, payload={!r}, "
            "currency={!r}, total={!r}",
            getattr(message.from_user, "id", None),
            getattr(payment, "telegram_payment_charge_id", None),
            payment.invoice_payload,
            payment.currency,
            payment.total_amount,
        )
        await message.answer(
            "⚠️ Платёж получен, но его параметры не прошли автоматическую проверку. "
            "Зарники не начислены автоматически. Не оплачивайте повторно."
        )
        return

    purchase_id = payment.telegram_payment_charge_id
    if not isinstance(purchase_id, str) or not purchase_id:
        logger.critical("Successful Stars payment has no Telegram charge id: user={}", message.from_user.id)
        await message.answer(
            "⚠️ Платёж получен, но не содержит идентификатор операции. "
            "Зарники не начислены автоматически. Не оплачивайте повторно."
        )
        return

    # Let a storage error reach aiogram's error logging.  The background
    # reconciler below will then recover the Telegram-authoritative transaction
    # by this same idempotency key; swallowing it here would hide a loss.
    mutation = await _credit_zarniki_payment(
        db,
        user_id=message.from_user.id,
        quote=quote,
        payment_charge_id=purchase_id,
        payload=payment.invoice_payload,
        recovery=False,
    )
    replayed = bool(mutation and not mutation.applied)
    try:
        if replayed:
            await message.answer(
                "✅ Этот платёж уже был обработан — повторного списания или начисления не произошло."
            )
        else:
            await message.answer(
                f"✅ Начислено <b>{quote.zarniki}✨</b> Зарников! Спасибо за поддержку проекта 💜",
                parse_mode="HTML",
            )
    except Exception:
        # The accounting transaction is already durable.  A notification fault
        # must not make the delivery path look failed or cause a retry storm.
        logger.warning("Could not send Stars purchase confirmation: charge={}", purchase_id)
