#!/usr/bin/env python3
"""Offline contract tests for Telegram Stars delivery and recovery.

No Telegram request or real database is used: the fakes exercise the exact
handler functions, invoice arguments, transaction-history recovery and ledger
idempotency keys that production depends on.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BOT_TOKEN", "123456:offline-payment-contract-token")
os.environ.setdefault("DATABASE_URL", "postgresql://offline-test")

from bot.handlers import payments  # noqa: E402
from FastAPI.routers import payments as web_payments  # noqa: E402
from core import payment_contract  # noqa: E402


class FakeMessage:
    def __init__(self, *, chat_type="private", text=None, payment=None, user_id=701, message_id=9):
        self.chat = SimpleNamespace(type=chat_type)
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.message_id = message_id
        self.successful_payment = payment
        self.reply_to_message = None
        self.answers: list[tuple[str, dict]] = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class FakeBot:
    def __init__(self, history=None):
        self.invoices: list[dict] = []
        self.messages: list[tuple[int, str, dict]] = []
        self.history = list(history or [])
        self.history_calls: list[tuple[int, int]] = []

    async def send_invoice(self, **kwargs):
        self.invoices.append(kwargs)

    async def send_message(self, user_id, text, **kwargs):
        self.messages.append((user_id, text, kwargs))

    async def get_star_transactions(self, *, offset, limit):
        self.history_calls.append((offset, limit))
        return SimpleNamespace(transactions=self.history[offset:offset + limit])


class FakePreCheckout:
    def __init__(self, payload, currency, total_amount):
        self.invoice_payload = payload
        self.currency = currency
        self.total_amount = total_amount
        self.answers: list[dict] = []

    async def answer(self, **kwargs):
        self.answers.append(kwargs)


class FakeQuery:
    def __init__(self, *, chat_type="private", user_id=701):
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakeMessage(chat_type=chat_type, user_id=user_id)
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _payment(*, payload, currency="XTR", total=20, charge="charge-1"):
    return SimpleNamespace(
        invoice_payload=payload,
        currency=currency,
        total_amount=total,
        telegram_payment_charge_id=charge,
        provider_payment_charge_id="provider-does-not-identify-stars",
    )


def _star_transaction(*, payload, amount=20, charge="charge-history", user_id=701):
    return SimpleNamespace(
        id=charge,
        amount=amount,
        source=SimpleNamespace(
            transaction_type="invoice_payment",
            invoice_payload=payload,
            user=SimpleNamespace(id=user_id),
        ),
    )


async def _run() -> None:
    assert payment_contract.is_stars_amount(True) is False
    assert payment_contract.is_stars_amount(0) is False
    assert payment_contract.is_stars_amount(100_001) is False
    package = payments._package_quote(20)
    custom = payments._custom_quote(20)
    assert package and package.zarniki == 215
    assert custom and custom.zarniki == 200
    assert payment_contract.is_issuable_v1_quote(package)
    assert payment_contract.is_issuable_v1_quote(custom)
    assert not payment_contract.is_issuable_v1_quote(
        payment_contract.ZarnikiQuote(100, 1100, "unknown", "v1")
    )
    assert not payment_contract.is_issuable_v1_quote(
        payment_contract.ZarnikiQuote(100, 1100, "p", "v2")
    )
    assert payments._invoice_payload(package) == "zarniki:v1:p:20:215"
    assert payments._invoice_payload(custom) == "zarniki:v1:c:20:200"

    valid = (
        ("zarniki:v1:p:20:215", "XTR", 20, 215),
        ("zarniki:v1:c:20:200", "XTR", 20, 200),
        ("zarniki:215", "XTR", 20, 215),       # deployed package invoice
        ("zarniki:200", "XTR", 20, 200),       # deployed custom invoice
    )
    for payload, currency, total, zarniki in valid:
        quote = payments._quote_from_paid_invoice(payload, currency, total)
        assert quote and quote.zarniki == zarniki, (payload, quote)

    # An already-open v1 invoice is priced by its frozen version contract, not
    # by whatever a future live menu happens to advertise.
    original_packages = payment_contract.STARS_PACKAGES
    payment_contract.STARS_PACKAGES = [(20, 200, 20)]
    try:
        historical_quote = payments._quote_from_paid_invoice("zarniki:v1:p:20:215", "XTR", 20)
        assert historical_quote and historical_quote.zarniki == 215
        assert payments._package_quote(20).zarniki == 220
        assert payments._is_issuable_v1_quote(payments._package_quote(20)) is False
    finally:
        payment_contract.STARS_PACKAGES = original_packages

    invalid = (
        ("zarniki:", "XTR", 20),
        ("zarniki:abc", "XTR", 20),
        ("zarniki:200:extra", "XTR", 20),
        ("zarniki:-200", "XTR", 20),
        ("zarniki:v1:p:20:200", "XTR", 20),
        ("zarniki:v1:c:20:215", "XTR", 20),
        ("zarniki:v1:p:20:215", "USD", 20),
        ("zarniki:v1:p:20:215", "XTR", 50),
        ("zarniki:v1:p:100001:1000010", "XTR", 100001),
    )
    for payload, currency, total in invalid:
        assert payments._quote_from_paid_invoice(payload, currency, total) is None, payload
        checkout = FakePreCheckout(payload, currency, total)
        await payments.process_pre_checkout(checkout)
        assert checkout.answers == [{"ok": False, "error_message": "Параметры платежа не прошли проверку. Откройте покупку заново."}]

    checkout = FakePreCheckout("zarniki:v1:p:20:215", "XTR", 20)
    await payments.process_pre_checkout(checkout)
    assert checkout.answers == [{"ok": True}]

    invoice_bot = FakeBot()
    package_query = FakeQuery()
    await payments.cb_buy_package(package_query, payments.BuyZarnikiCB(stars=20), invoice_bot)
    await payments.msg_custom_zarniki_amount(FakeMessage(text="17"), invoice_bot)
    assert len(invoice_bot.invoices) == 2
    assert invoice_bot.invoices[0]["payload"] == "zarniki:v1:p:20:215"
    assert invoice_bot.invoices[1]["payload"] == "zarniki:v1:c:17:170"
    for invoice in invoice_bot.invoices:
        assert invoice["currency"] == "XTR"
        assert invoice["provider_token"] == ""
        assert len(invoice["prices"]) == 1

    # Mini App must issue exactly the same frozen contract as the chat bot;
    # this is a transport test, not a real Telegram request.
    original_tg_call = web_payments._tg_call
    web_calls: list[tuple[str, dict]] = []

    async def fake_tg_call(method, **kwargs):
        web_calls.append((method, kwargs))
        return {"ok": True, "result": "https://t.me/$offline-invoice"}

    web_payments._tg_call = fake_tg_call
    try:
        package_invoice = await web_payments.zarniki_invoice(
            web_payments.InvoiceRequest(stars=20), user={"id": 701})
        custom_invoice = await web_payments.zarniki_invoice(
            web_payments.InvoiceRequest(stars=17), user={"id": 701})
        assert package_invoice == {"link": "https://t.me/$offline-invoice", "stars": 20, "zarniki": 215}
        assert custom_invoice == {"link": "https://t.me/$offline-invoice", "stars": 17, "zarniki": 170}
        assert [call[1]["payload"] for call in web_calls] == [
            "zarniki:v1:p:20:215", "zarniki:v1:c:17:170",
        ]
        for _method, call in web_calls:
            assert call["currency"] == "XTR" and call["provider_token"] == ""
            assert call["prices"][0]["amount"] in {20, 17}

        # A future tariff cannot create a Mini App invoice that the bot rejects.
        payment_contract.STARS_PACKAGES = [(20, 200, 20)]
        prior_calls = len(web_calls)
        try:
            await web_payments.zarniki_invoice(web_payments.InvoiceRequest(stars=20), user={"id": 701})
        except Exception as error:
            assert getattr(error, "status_code", None) == 503
        else:
            raise AssertionError("Mini App must fail closed when live tariff diverges from frozen v1.")
        assert len(web_calls) == prior_calls
    finally:
        payment_contract.STARS_PACKAGES = original_packages
        web_payments._tg_call = original_tg_call

    # The group entry path must not issue an impossible private invoice.
    group = FakeMessage(chat_type="group", text="донат")
    await payments.cmd_buy_zarniki(group)
    assert "личном чате" in group.answers[0][0]
    group_query = FakeQuery(chat_type="group")
    await payments.cb_buy_package(group_query, payments.BuyZarnikiCB(stars=20), invoice_bot)
    assert len(invoice_bot.invoices) == 2
    assert "личном чате" in group_query.message.answers[0][0]

    original_add_balance = payments.eco_db.add_balance
    credits: dict[str, dict] = {}

    async def idempotent_add_balance(_db, user_id, **kwargs):
        key = kwargs["idempotency_key"]
        if key in credits:
            return SimpleNamespace(applied=False)
        credits[key] = {"user_id": user_id, **kwargs}
        return SimpleNamespace(applied=True)

    payments.eco_db.add_balance = idempotent_add_balance
    try:
        purchase_message = FakeMessage(payment=_payment(payload="zarniki:v1:p:20:215"))
        await payments.on_successful_payment(purchase_message, object(), invoice_bot)
        await payments.on_successful_payment(purchase_message, object(), invoice_bot)
        assert list(credits) == ["stars_purchase:charge-1"]
        assert credits["stars_purchase:charge-1"]["zarniki"] == 215
        assert "уже был обработан" in purchase_message.answers[-1][0]

        invalid_message = FakeMessage(payment=_payment(payload="zarniki:215:extra", charge="invalid"))
        await payments.on_successful_payment(invalid_message, object(), invoice_bot)
        assert "stars_purchase:invalid" not in credits
        assert "Не оплачивайте повторно" in invalid_message.answers[0][0]

        # Simulate a database outage after Telegram has delivered the update.
        failed_message = FakeMessage(payment=_payment(payload="zarniki:v1:c:20:200", charge="recover-me"))
        attempts = 0

        async def fail_once(_db, user_id, **kwargs):
            nonlocal attempts
            attempts += 1
            raise RuntimeError("temporary database outage")

        payments.eco_db.add_balance = fail_once
        try:
            await payments.on_successful_payment(failed_message, object(), invoice_bot)
        except RuntimeError:
            pass
        else:
            raise AssertionError("A failed ledger write must remain visible to recovery")

        payments.eco_db.add_balance = idempotent_add_balance
        recovery_bot = FakeBot([_star_transaction(payload="zarniki:v1:c:20:200", charge="recover-me")])
        first_recovery = await payments.reconcile_star_payments(recovery_bot, object(), max_pages=1)
        second_recovery = await payments.reconcile_star_payments(recovery_bot, object(), max_pages=1)
        assert first_recovery.credited == 1 and first_recovery.failed == 0
        assert second_recovery.replayed == 1 and second_recovery.credited == 0
        assert credits["stars_purchase:recover-me"]["zarniki"] == 200
        assert len(recovery_bot.messages) == 1
    finally:
        payments.eco_db.add_balance = original_add_balance

    startup_source = (ROOT / "bot" / "__main__.py").read_text(encoding="utf-8")
    assert "delete_webhook(drop_pending_updates=True)" not in startup_source
    assert "delete_webhook(drop_pending_updates=False)" in startup_source
    assert "star_payment_reconciliation_task(bot, pool)" in startup_source

    preview_source = (ROOT / "tools" / "preview_server.mjs").read_text(encoding="utf-8")
    assert f"per_star: {payment_contract.ZARNIKI_PER_STAR}" in preview_source
    assert f"custom_min: 1, custom_max: {payment_contract.MAX_STARS}" in preview_source
    for stars, base, bonus in payment_contract.STARS_PACKAGES:
        total = base + bonus
        expected = (
            f"{{ stars: {stars}, zarniki: {base}, bonus: {bonus}, total: {total}, "
            f"popular: {str(stars == payments.STARS_MOST_POPULAR).lower()} }}"
        )
        assert expected in preview_source, expected


if __name__ == "__main__":
    asyncio.run(_run())
    print("OK: Stars invoice, validation, idempotent delivery and recovery contract")
