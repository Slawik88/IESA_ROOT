"""Whole-bot scenarios: Telegram Stars payments end to end (shop → invoice → pre-checkout → paid → balance)."""
from __future__ import annotations

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import button, last_message, said, say, sim_friends
from tools.mafia_sim.world import TgError

REFUSED = "не прошли проверку"


async def _balance(h: Harness, user) -> str:
    return said(await say(h, user, user.id, "баланс"))


async def _buy(h: Harness, user, label: str) -> dict:
    """Open the shop, press a package, return the invoice the bot sent."""
    await say(h, user, user.id, "/start buyzarniki")
    click = await h.click(user, user.id, last_message(h, user.id, "ЗАРНИКИ"), label)
    ok(click.answered and not click.alert, f"pressing a package is answered quietly: {click}")
    return h.world.invoices[-1]


@bot_scenario
async def stars_purchase_success(h: Harness) -> None:
    (player,), _ = sim_friends(h, 1)
    invoice = await _buy(h, player, "50⭐")
    ok(invoice["stars"] == 50 and invoice["currency"] == "XTR" and invoice["chat_id"] == player.id, invoice)
    pre = await h.pre_checkout(player, invoice["payload"], invoice["stars"])
    ok(pre["ok"], f"a genuine invoice passes the pre-checkout: {pre}")
    paid = len(h.world.calls)
    await h.paid(player, invoice["payload"], invoice["stars"], f"sim-{h.run_tag}-success")
    thanks = said([(n, p) for n, p in h.world.calls[paid:] if n == "SendMessage"])
    ok("Начислено 660✨" in thanks, f"the player is told what they got: {thanks!r}")
    ok("Зарники: 660" in await _balance(h, player), "the balance shows the credited Zarniki")

    again = len(h.world.calls)
    await h.paid(player, invoice["payload"], invoice["stars"], f"sim-{h.run_tag}-success")   # Telegram redelivers the same payment
    replay = said([(n, p) for n, p in h.world.calls[again:] if n == "SendMessage"])
    ok("уже был обработан" in replay, f"a redelivered payment is recognised: {replay!r}")
    ok("Зарники: 660" in await _balance(h, player), "a redelivered payment never credits twice")


@bot_scenario
async def stars_purchase_rejected(h: Harness) -> None:
    (player,), _ = sim_friends(h, 1)
    invoice = await _buy(h, player, "20⭐")
    for payload, stars, currency in ((invoice["payload"], invoice["stars"] + 1, "XTR"), ("garbage", 20, "XTR"),
                                     (invoice["payload"], invoice["stars"], "USD")):
        pre = await h.pre_checkout(player, payload, stars, currency=currency)
        ok(not pre["ok"] and REFUSED in pre["error"], f"a forged or altered invoice is refused before payment: {pre}")
    mark = len(h.world.calls)
    await h.paid(player, "garbage", 20, f"sim-{h.run_tag}-forged")
    text = said([(n, p) for n, p in h.world.calls[mark:] if n == "SendMessage"])
    ok("не прошли автоматическую проверку" in text and "Не оплачивайте повторно" in text, f"a forged payment is explained: {text!r}")
    ok("Зарники: 0" in await _balance(h, player), "a payment that failed the contract credits nothing")


@bot_scenario
async def stars_custom_amount(h: Harness) -> None:
    (player,), _ = sim_friends(h, 1)
    await say(h, player, player.id, "/start buyzarniki")
    await h.click(player, player.id, last_message(h, player.id, "ЗАРНИКИ"), "Своя сумма")
    marker = last_message(h, player.id, "Введите количество")
    for bad in ("0", "999999999"):
        sent = await say(h, player, player.id, bad, reply_to=marker)
        ok("Введите число" in said(sent), f"{bad!r} is out of range: {said(sent)!r}")
    ok(not h.world.invoices, "no invoice for a bad amount")
    await say(h, player, player.id, "7", reply_to=marker)
    ok(h.world.invoices and h.world.invoices[-1]["stars"] == 7, f"an invoice for exactly 7 stars: {h.world.invoices}")
    pre = await h.pre_checkout(player, h.world.invoices[-1]["payload"], 7)
    ok(pre["ok"], f"a custom-amount invoice passes the pre-checkout: {pre}")


@bot_scenario
async def stars_shop_only_in_dm(h: Harness) -> None:
    (player,), group = sim_friends(h, 1)
    sent = await say(h, player, group, "бот купить зарники")
    ok("только в личном чате" in said(sent), f"the shop redirects a group request to the DM: {said(sent)!r}")
    url = [b.get("url") for m in [last_message(h, group, "личном чате")] for b in m.buttons()]
    ok(any(u and u.endswith("?start=buyzarniki") for u in url), f"with a link into the DM shop: {url}")
    ok(not h.world.invoices, "no invoice is ever sent into a group")


@bot_scenario
async def stars_invoice_to_blocked_player(h: Harness) -> None:
    (player,), _ = sim_friends(h, 1)
    await say(h, player, player.id, "/start buyzarniki")
    shop = last_message(h, player.id, "ЗАРНИКИ")
    h.world.fail(lambda name, params: name == "SendInvoice", TgError(403, "Forbidden: bot was blocked by the user"))
    try:
        await h.click(player, player.id, shop, "50⭐")
        outcome = "handled"
    except Exception as exc:  # noqa: BLE001 - the contract is that it is a Telegram error, not a crash of the bot
        outcome = type(exc).__name__
    ok(outcome in {"handled", "TelegramForbiddenError"}, f"a blocked player must not break the dispatcher: {outcome}")
    ok(not h.world.invoices, "nothing was invoiced while Telegram refused")
    await h.click(player, player.id, shop, "50⭐")                 # the player unblocks the bot and presses again
    ok(len(h.world.invoices) == 1 and h.world.invoices[0]["stars"] == 50, f"the next press is served normally: {h.world.invoices}")


@bot_scenario
async def stars_charge_reused_by_another_player(h: Harness) -> None:
    """One Telegram charge id belongs to one player forever: a second claim is refused and credits nothing."""
    first, second = h.user("Первый"), h.user("Второй")
    invoice = await _buy(h, first, "20⭐")
    await h.paid(first, invoice["payload"], invoice["stars"], f"sim-{h.run_tag}-shared")
    ok("Зарники: 258" in await _balance(h, first), "the genuine payer is credited")
    try:
        await h.paid(second, invoice["payload"], invoice["stars"], f"sim-{h.run_tag}-shared")
        outcome = "no error"
    except RuntimeError as exc:
        outcome = str(exc)
    ok("conflict" in outcome, f"the same charge for another player is refused loudly (fail closed): {outcome!r}")
    ok("Зарники: 0" in await _balance(h, second), "and nothing is credited to the second player")
