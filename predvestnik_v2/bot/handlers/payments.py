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
import hashlib
import json
import os
from uuid import uuid4

from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandStart, CommandObject, BaseFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.types import LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from bot.filters.text_commands import TextCmd
from bot.keyboards.cta import dm_cta_kb
from infrastructure.repositories import economy as eco_db
from infrastructure.repositories import star_payments_v1 as payment_repo
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
from core.supporter_cosmetics_v1 import OFFER_BY_ID as SUPPORTER_OFFERS, parse_invoice_payload as _parse_cosmetic_payload
from services import supporter_cosmetics_v1
from services import supporter_refunds_v1
from infrastructure.repositories import supporter_cosmetics_v1 as supporter_repo
from infrastructure.preprod import direct_stars_cosmetics_allowed, is_preprod, stars_invoice_issuance_allowed

router = Router(name="payments_router")
_CUSTOM_AMOUNT_MARKER = "✏️ Введите количество ⭐ для покупки Зарников"
_PAY_SUPPORT_MARKER = "🧾 ОПИШИТЕ ПРОБЛЕМУ С ПЛАТЕЖОМ"
_RECONCILIATION_PAGE_SIZE = 100
_RECONCILIATION_INITIAL_MAX_PAGES = 100
_RECONCILIATION_PERIODIC_MAX_PAGES = 3
_RECONCILIATION_PERIOD_SECONDS = 5 * 60
@dataclass(frozen=True, slots=True)
class StarReconciliationResult:
    scanned: int = 0
    credited: int = 0
    refunded: int = 0
    reviewed: int = 0
    replayed: int = 0
    invalid: int = 0
    failed: int = 0
    exhausted: bool = True


class BuyZarnikiCB(CallbackData, prefix="buyzar"):
    stars: int  # 0 = "своя сумма"


@router.message(Command("paysupport"))
async def cmd_pay_support(message: types.Message, db):
    """Telegram-required private support entry for Stars payment disputes."""
    if getattr(message.chat, "type", None) != "private":
        username = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
        suffix = f" Откройте @{username} в личном чате." if username else " Напишите боту в личном чате."
        await message.answer("Платёжные обращения нельзя разбирать публично." + suffix)
        return
    receipts = await payment_repo.latest_for_user(db, int(message.from_user.id), limit=5)
    direct_orders = await supporter_repo.latest_orders(db, int(message.from_user.id), limit=5)
    lines = [
        "💳 <b>ПОДДЕРЖКА ПЛАТЕЖЕЙ</b>",
        "",
        "Не оплачивайте покупку повторно. Ответьте на это сообщение и опишите: что покупали, когда и что произошло.",
        "Заявка не означает автоматический возврат: её вручную рассматривает владелец по Telegram charge ID и истории выдачи. После траты или перевода Зарников возврат обычно невозможен.",
    ]
    if receipts:
        lines += ["", "Последние сохранённые платежи:"]
        labels = {"credited": "зачислен", "refund_requested": "возврат проверяется",
                  "refunded": "возвращён", "review": "нужна проверка"}
        for item in receipts:
            ref = str(item["telegram_charge_id"])[-8:]
            lines.append(
                f"• {int(item['stars_amount'])}⭐ → {int(item['zarniki_amount'])}✨ · "
                f"{labels.get(str(item['status']), 'проверяется')} · …{ref}"
            )
    else:
        lines += ["", "Сохранённых Stars-платежей у аккаунта пока нет."]
    if direct_orders:
        lines += ["", "Прямые покупки косметики:"]
        for order in direct_orders:
            lines.append(
                f"• {int(order['stars_amount'])}⭐ · {order['status']} · заказ …{str(order['order_id'])[-8:]}"
            )
    lines += ["", _PAY_SUPPORT_MARKER]
    await message.answer("\n".join(lines), parse_mode="HTML")


class _PaySupportReply(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        reply = message.reply_to_message
        return bool(
            getattr(message.chat, "type", None) == "private"
            and reply and reply.text and _PAY_SUPPORT_MARKER in reply.text
            and message.text and message.text.strip()
        )


@router.message(_PaySupportReply())
async def msg_pay_support(message: types.Message, bot: Bot, developer_id: int = 0):
    if not developer_id:
        await message.answer("⚠️ Канал поддержки временно недоступен. Напишите @Buy_me_Acoffee или @Kovid2004.")
        return
    text = message.text.strip()[:3000]
    await bot.send_message(
        int(developer_id),
        f"💳 PAY SUPPORT\nuser_id={int(message.from_user.id)}\n\n{text}",
    )
    await message.answer("✅ Обращение передано владельцу. Не повторяйте оплату: решение по возврату или восстановлению выдачи принимается после ручной проверки.")


@router.message(Command("refundstars"))
async def cmd_refund_stars(message: types.Message, bot: Bot, db, developer_id: int = 0):
    """Owner-only execution of a prepared direct-cosmetic Stars refund."""
    if not developer_id or int(message.from_user.id) != int(developer_id):
        return
    if is_preprod():
        await message.answer("Тестовый стенд не вызывает Telegram refundStarPayment.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Формат: /refundstars <полный order_id>")
        return
    try:
        result = await supporter_refunds_v1.refund(bot, db, parts[1].strip())
    except Exception:
        logger.exception("Direct cosmetic refund failed for order={}", parts[1].strip())
        await message.answer("⚠️ Возврат не подтверждён. Право заморожено; проверьте outbox перед повтором.")
        return
    await message.answer(
        "✅ Stars возвращены, связанная косметическая печать отозвана."
        if not result.get("replayed") else "✅ Этот возврат уже был завершён ранее."
    )


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
    username = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
    builder = InlineKeyboardBuilder()
    if username:
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
    if not stars_invoice_issuance_allowed():
        return await message.answer(
            "🛡 <b>Покупки Stars временно закрыты.</b>\n\n"
            "Мы завершаем безопасный учёт постоянной косметики и возвратов. "
            "Существующие Зарники и покупки сохранены. По вопросам оплаты: /paysupport.",
            parse_mode="HTML",
        )
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
        "Я — бот для сообществ: модерация, профиль и игры.\n\n"
        "Куда дальше — два пути:\n"
        "➕ <b>Добавь меня в группу</b> — игра идёт там. Команды пишутся словом "
        "«бот»: <code>бот помощь</code>\n"
        "🌐 <b>Открой мини-апп</b> — профиль, внешний вид и игры\n\n"
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
async def process_pre_checkout(pre_checkout_query: types.PreCheckoutQuery, db):
    if is_preprod():
        await pre_checkout_query.answer(
            ok=False,
            error_message="Покупки Stars отключены на тестовом стенде.",
        )
        return
    cosmetic = _parse_cosmetic_payload(pre_checkout_query.invoice_payload)
    if cosmetic:
        # Release flags gate *new invoice issuance*. A frozen order already
        # accepted by Telegram must stay payable and fulfillable after a kill
        # switch, otherwise a legitimate in-flight invoice becomes stranded.
        if not await supporter_repo.schema_ready(db):
            await pre_checkout_query.answer(ok=False, error_message="Покупка временно приостановлена. Stars не списаны.")
            return
        try:
            await supporter_cosmetics_v1.validate_precheckout(
                db, payer_user_id=int(pre_checkout_query.from_user.id),
                payload=pre_checkout_query.invoice_payload,
                currency=pre_checkout_query.currency,
                amount=pre_checkout_query.total_amount,
                query_id=str(pre_checkout_query.id),
            )
        except Exception:
            await pre_checkout_query.answer(
                ok=False, error_message="Заказ косметики устарел или уже обработан. Откройте витрину заново."
            )
        else:
            await pre_checkout_query.answer(ok=True)
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
    async with db.connection.transaction():
        mutation = await eco_db.add_balance(
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
        if mutation is None:
            raise RuntimeError("Stars credit created no ledger operation")
        await payment_repo.record_credit(
            db, charge_id=payment_charge_id, user_id=user_id,
            stars=quote.stars, zarniki=quote.zarniki, payload=payload,
            payload_version=quote.version, operation_id=mutation.operation_id,
        )
        return mutation


async def _record_history_problem(db, transaction, *, disposition: str, detail: str) -> None:
    """Persist an operator-readable record for a row recovery could not settle."""
    if not hasattr(db, "execute"):
        return  # Offline handler contract tests deliberately use no SQL adapter.
    charge_id = getattr(transaction, "id", None)
    amount = getattr(transaction, "amount", None)
    if not isinstance(charge_id, str) or not charge_id or not isinstance(amount, int) or isinstance(amount, bool):
        return
    source = getattr(transaction, "source", None)
    receiver = getattr(transaction, "receiver", None)
    source_user = getattr(getattr(source, "user", None), "id", None)
    receiver_user = getattr(getattr(receiver, "user", None), "id", None)
    payload = getattr(source, "invoice_payload", None)
    event_kind = "outgoing_refund" if amount < 0 and receiver is not None else "incoming_payment"
    material = {
        "id": charge_id, "kind": event_kind, "amount": amount,
        "date": str(getattr(transaction, "date", None)), "source_user": source_user,
        "receiver_user": receiver_user, "payload": payload,
        "source_type": getattr(source, "transaction_type", None),
        "receiver_type": getattr(receiver, "transaction_type", None),
    }
    fingerprint = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    try:
        await payment_repo.record_reconciliation_observation(
            db, charge_id=charge_id, event_kind=event_kind, amount=amount,
            telegram_date=getattr(transaction, "date", None),
            source_user_id=source_user if isinstance(source_user, int) and not isinstance(source_user, bool) else None,
            receiver_user_id=receiver_user if isinstance(receiver_user, int) and not isinstance(receiver_user, bool) else None,
            invoice_payload=payload if isinstance(payload, str) else None, fingerprint=fingerprint,
            disposition=disposition, failure_detail=detail,
        )
    except Exception:
        logger.exception("Could not journal unresolved Stars history row: charge={}", charge_id)


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

    scanned = credited = refunded = reviewed = replayed = invalid = failed = 0
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
            receiver = getattr(transaction, "receiver", None)
            refund_user = getattr(receiver, "user", None)
            refund_user_id = getattr(refund_user, "id", None)
            charge_id = getattr(transaction, "id", None)
            amount = getattr(transaction, "amount", None)
            if (receiver is not None and getattr(receiver, "transaction_type", None) == "invoice_payment"
                    and isinstance(refund_user_id, int) and not isinstance(refund_user_id, bool)
                    and isinstance(charge_id, str) and charge_id
                    and isinstance(amount, int) and not isinstance(amount, bool) and amount < 0):
                try:
                    reconciled = await supporter_refunds_v1.reconcile_authoritative_refund(
                        db, charge_id=charge_id, user_id=refund_user_id, amount=amount,
                    )
                except Exception:
                    failed += 1
                    logger.exception("Invalid direct cosmetic refund history row: charge={}", charge_id)
                    await _record_history_problem(db, transaction, disposition="failed", detail="direct cosmetic refund reconciliation failed")
                    continue
                if reconciled is not None:
                    if reconciled[1]:
                        refunded += 1
                    else:
                        replayed += 1
                    continue
                try:
                    receipt_review = await payment_repo.reconcile_authoritative_refund_review(
                        db, charge_id=charge_id, user_id=refund_user_id, amount=amount,
                    )
                except Exception:
                    failed += 1
                    logger.exception("Invalid Zarniki Stars refund history row: charge={}", charge_id)
                    await _record_history_problem(db, transaction, disposition="failed", detail="Zarniki refund custody review failed")
                    continue
                if receipt_review is not None:
                    if receipt_review[1]:
                        reviewed += 1
                        logger.warning(
                            "Zarniki Stars refund requires custody review: charge={} user={}",
                            charge_id, refund_user_id,
                        )
                        await _record_history_problem(db, transaction, disposition="review", detail="Zarniki custody review required")
                    else:
                        replayed += 1
                    continue
            source = getattr(transaction, "source", None)
            payload = getattr(source, "invoice_payload", None)
            cosmetic_invoice = _parse_cosmetic_payload(payload)
            if cosmetic_invoice:
                transaction_type = getattr(source, "transaction_type", None)
                user = getattr(source, "user", None)
                user_id = getattr(user, "id", None)
                charge_id = getattr(transaction, "id", None)
                amount = getattr(transaction, "amount", None)
                if (transaction_type != "invoice_payment" or not isinstance(user_id, int)
                        or isinstance(user_id, bool) or not isinstance(charge_id, str)
                        or not charge_id or not isinstance(amount, int) or isinstance(amount, bool)):
                    invalid += 1
                    logger.critical("Invalid direct cosmetic Stars history row: order={} charge={}", cosmetic_invoice.order_id, charge_id)
                    await _record_history_problem(db, transaction, disposition="invalid", detail="invalid direct cosmetic transaction contract")
                    continue
                try:
                    order, applied = await supporter_cosmetics_v1.grant_paid(
                        db, payer_user_id=user_id, payload=payload, currency="XTR",
                        amount=amount, charge_id=charge_id,
                    )
                except Exception:
                    failed += 1
                    logger.exception("Could not reconcile direct cosmetic order={} charge={}", cosmetic_invoice.order_id, charge_id)
                    await _record_history_problem(db, transaction, disposition="failed", detail="direct cosmetic entitlement reconciliation failed")
                    continue
                if applied:
                    credited += 1
                    try:
                        offer = SUPPORTER_OFFERS[str(order["offer_id"])]
                        await bot.send_message(user_id, f"✅ Восстановлена печать {offer['icon']} <b>{offer['name']}</b>.", parse_mode="HTML")
                    except Exception:
                        logger.warning("Could not notify recovered cosmetic order={}", cosmetic_invoice.order_id)
                else:
                    replayed += 1
                continue
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
                await _record_history_problem(db, transaction, disposition="invalid", detail="invalid Zarniki transaction contract")
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
                await _record_history_problem(db, transaction, disposition="failed", detail="Zarniki ledger credit failed")
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
        refunded=refunded,
        reviewed=reviewed,
        replayed=replayed,
        invalid=invalid,
        failed=failed,
        exhausted=exhausted,
    )


async def _run_star_history_scan(bot: Bot, db, *, max_pages: int) -> StarReconciliationResult | None:
    """Run one leased scan and durably finish it even when Telegram fails."""
    await payment_repo.ensure_tables(db)
    lease_token = uuid4().hex
    if not await payment_repo.acquire_reconciliation_lease(db, lease_token):
        logger.warning("Stars reconciliation skipped: another worker owns the lease")
        return None
    result: StarReconciliationResult | None = None
    try:
        before = await bot.get_star_transactions(offset=0, limit=1)
        before_head = next(iter(getattr(before, "transactions", ()) or ()), None)
        before_head_id = getattr(before_head, "id", None)
        result = await reconcile_star_payments(bot, db, max_pages=max_pages)
        after = await bot.get_star_transactions(offset=0, limit=1)
        after_head = next(iter(getattr(after, "transactions", ()) or ()), None)
        after_head_id = getattr(after_head, "id", None)
        stable_head = before_head_id == after_head_id
        detail = None
        if not result.exhausted:
            detail = "page limit reached before a terminal short page"
        elif result.failed or result.invalid:
            detail = f"unresolved history rows: failed={result.failed}, invalid={result.invalid}"
        elif not stable_head:
            detail = "Telegram history head changed during scan; a fresh full pass is required"
        if detail:
            await payment_repo.upsert_reconciliation_alert(
                db, key="stars-history-recovery-unhealthy", severity="critical", detail=detail,
            )
        else:
            await payment_repo.resolve_reconciliation_alert(db, "stars-history-recovery-unhealthy")
        if not await payment_repo.finish_reconciliation_run(
            db, token=lease_token, complete=result.exhausted, stable_head=stable_head,
            head_id=after_head_id if isinstance(after_head_id, str) else None,
            scanned=result.scanned, detail=detail,
        ):
            raise RuntimeError("Stars reconciliation lease was lost before finalization")
        return result
    except asyncio.CancelledError:
        raise
    except Exception as error:
        detail = f"scan error: {type(error).__name__}: {error}"
        try:
            await payment_repo.upsert_reconciliation_alert(
                db, key="stars-history-recovery-unhealthy", severity="critical", detail=detail,
            )
            await payment_repo.finish_reconciliation_run(
                db, token=lease_token, complete=False, stable_head=False,
                head_id=None, scanned=result.scanned if result else 0, detail=detail,
            )
        except Exception:
            logger.exception("Could not persist Stars recovery failure; lease expires fail-closed")
        raise


async def star_payment_reconciliation_task(bot: Bot, pool) -> None:
    """Keep retrying authoritative Stars history without blocking update polling."""
    from infrastructure.pg_adapter import PGAdapter

    if is_preprod():
        logger.warning("Stars reconciliation is disabled on the isolated preprod stand.")
        return
    logger.info("Stars payment reconciliation task started.")
    run_number = 0
    while True:
        max_pages = (_RECONCILIATION_INITIAL_MAX_PAGES if run_number == 0 or run_number % 72 == 0
                     else _RECONCILIATION_PERIODIC_MAX_PAGES)
        try:
            async with pool.acquire() as connection:
                adapter = PGAdapter(connection)
                result = await _run_star_history_scan(bot, adapter, max_pages=max_pages)
                if result:
                    for order_id in await supporter_repo.pending_refund_order_ids(adapter):
                        try:
                            await supporter_refunds_v1.refund(bot, adapter, order_id)
                        except Exception:
                            logger.exception("Pending Stars cosmetic refund remains unresolved: order={}", order_id)
            if result and (result.credited or result.refunded or result.reviewed or result.failed or not result.exhausted):
                logger.info("Stars reconciliation result: {}", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Stars reconciliation pass failed")
        run_number += 1
        await asyncio.sleep(_RECONCILIATION_PERIOD_SECONDS)


@router.message(F.successful_payment)
async def on_successful_payment(message: types.Message, db, bot: Bot):
    if is_preprod():
        logger.critical(
            "Preprod refused successful_payment mutation for user={}",
            getattr(message.from_user, "id", None),
        )
        await message.answer(
            "⚠️ Тестовый стенд не обрабатывает платежи Stars. "
            "Не повторяйте оплату и сообщите разработчику."
        )
        return

    payment = message.successful_payment
    cosmetic = _parse_cosmetic_payload(payment.invoice_payload)
    if cosmetic:
        charge_id = payment.telegram_payment_charge_id
        if not isinstance(charge_id, str) or not charge_id:
            logger.critical("Paid cosmetic has no Telegram charge id: user={} order={}", message.from_user.id, cosmetic.order_id)
            await message.answer("⚠️ Платёж получен без идентификатора. Не повторяйте оплату; используйте /paysupport.")
            return
        try:
            order, applied = await supporter_cosmetics_v1.grant_paid(
                db, payer_user_id=int(message.from_user.id), payload=payment.invoice_payload,
                currency=payment.currency, amount=payment.total_amount, charge_id=charge_id,
            )
        except Exception:
            logger.exception("Could not grant direct Stars cosmetic order={} charge={}", cosmetic.order_id, charge_id)
            await message.answer("⚠️ Платёж получен, но право требует проверки. Не оплачивайте повторно; используйте /paysupport.")
            raise
        offer = SUPPORTER_OFFERS[str(order["offer_id"])]
        await message.answer(
            (f"✅ Постоянная печать <b>{offer['icon']} {offer['name']}</b> добавлена в профиль."
             if applied else "✅ Этот платёж уже обработан; повторной выдачи не произошло."),
            parse_mode="HTML",
        )
        return
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
