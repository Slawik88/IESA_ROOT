"""Transactional v2 authority. The client never supplies a payout or book state."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from core import coin_market_v2 as rules
from core.economy_contract import IdempotencyConflict
from infrastructure.repositories import coin_market_v2 as repo
from infrastructure.repositories import economy_ledger, star_payments_v1, system_flags


class Unavailable(rules.MarketError):
    pass


class Requote(rules.MarketError):
    pass


def configuration():
    secret = os.getenv("COIN_MARKET_V2_SECRET", "").encode()
    if len(secret) < 32:
        raise Unavailable("Биржа пока не настроена.")
    return secret, hashlib.sha256(secret).hexdigest()[:16]


def money(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,12}(?:\.\d{1,6})?", value):
        raise rules.MarketError(
            "Введите сумму Моры, не больше шести знаков после запятой."
        )
    try:
        amount = Decimal(value) * rules.MORA
    except InvalidOperation as exc:
        raise rules.MarketError("Некорректная сумма.") from exc
    return rules.integer(int(amount), minimum=1)


def shown(value):
    return format(Decimal(value) / rules.MORA, "f")


def action(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", value):
        raise rules.MarketError("Некорректный идентификатор операции.")
    return value


def fingerprint(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def replay(db, user_id, action_id, signature):
    receipt = await repo.replay(db, user_id, action_id)
    if not receipt:
        return None
    if receipt["fingerprint"] != signature:
        raise IdempotencyConflict("Этот запрос уже использован с другими условиями.")
    return {**repo.decode(receipt["response"]), "replayed": True}


async def require(db, *, new=True, shorts=False):
    if not await repo.ready(db):
        raise Unavailable("Биржа ещё не открыта.")
    if new and not await system_flags.is_enabled(db, "coin_market_v2"):
        raise Unavailable("Новые сделки пока закрыты.")
    if (
        new
        and shorts
        and not await system_flags.is_enabled(db, "coin_market_v2_shorts")
    ):
        raise Unavailable("Позиции на падение пока закрыты.")
    configuration()


def checked(row):
    if not row:
        raise rules.MarketError("Монета не найдена.")
    secret, key = configuration()
    if row["rules"] != rules.RULES_VERSION or row["secret_id"] != key:
        raise Unavailable("Рынок обновляется. Попробуйте позже.")
    coin, book, state = repo.unpack(row)
    book.validate(coin)
    return coin, book, state, secret


async def wallet(db, user_id, delta, action_id, coin_id, *, extra=None):
    deltas = dict(extra or {})
    if delta:
        deltas["mora"] = Decimal(delta) / rules.MORA
    if not deltas:
        return None
    mutation = await economy_ledger.apply_balance_change(
        db,
        user_id,
        deltas,
        reason_code="coin_market_v2",
        idempotency_key="cm2:" + action_id,
        source_type="coin_market_v2",
        reference_type="coin",
        reference_id=coin_id,
    )
    return mutation.operation_id


async def settle_short(db, row, book, state, position_row, *, automatic=False):
    user_id = int(position_row["user_id"])
    await repo.user_lock(db, user_id)
    coin, _, _, _ = checked(row)
    result = rules.close_short(
        coin, book, state.price, repo.short_payload(position_row)
    )
    action_id = (
        f"liquidate:{position_row['id']}:{state.tick}"
        if automatic
        else position_row["action_id"]
    )
    signature = (
        fingerprint({"automatic": position_row["id"], "tick": state.tick})
        if automatic
        else position_row["signature"]
    )
    op = await wallet(db, user_id, result.payout, action_id, coin.key)
    response = {
        "ok": True,
        "side": "close_short",
        "coin_id": coin.key,
        "position_id": position_row["id"],
        "received": shown(result.payout),
        "commission": shown(result.commission),
        "penalty": shown(result.penalty),
        "liquidated": result.liquidated,
        "price": shown(state.price),
        "tick": state.tick,
    }
    await repo.finish_short(db, position_row["id"], state.tick)
    await repo.receipt(
        db, user_id, action_id, signature, response, op, coin.key, result.flow
    )
    return result.book, response


async def advance(db, coin_id, *, target_tick=None, limit=288):
    """Coin lock serializes ticks/maintenance/manual trades across all workers."""
    async with db.connection.transaction():
        row = await repo.load(db, coin_id, lock=True)
        coin, book, state, secret = checked(row)
        await repo.reconcile(db, row, book)
        target = await repo.current_tick(db) if target_tick is None else target_tick
        for _ in range(min(limit, max(0, target - state.tick))):
            state = rules.next_price(
                coin,
                state,
                secret=secret,
                character=row["character"],
                group=row["group_key"],
            )
            for position in await repo.active_shorts(db, coin_id):
                p = repo.short_payload(position)
                cost = rules.ceildiv(p.units * state.price, rules.TOKEN)
                if (p.escrow - cost - rules.fee(cost)) * 5 <= p.collateral:
                    book, _ = await settle_short(
                        db, row, book, state, position, automatic=True
                    )
            await repo.save(db, coin_id, book, state)
            await repo.append_tick(db, coin_id, state)
        await repo.reconcile(db, row, book)
        return state.tick == target


async def maintenance(db):
    if not await repo.ready(db):
        return
    # Runs even with entry flags off: existing positions retain maintenance.
    for coin_id in await repo.maintenance_coin_ids(db):
        await advance(db, coin_id)


def public_coin(row):
    coin, _book, state, _ = checked(row)
    units, cost = int(row.get("user_units", 0)), int(row.get("user_cost", 0))
    gross = units * state.price // rules.TOKEN
    net = max(0, gross - rules.fee(gross))
    return {
        "id": coin.key,
        "name": row["name"],
        "ticker": row["ticker"],
        "icon": row["icon"],
        "character": row["character"],
        "group": row["group_key"],
        "personal": row["owner_id"] is not None,
        "price": shown(state.price),
        "tick": state.tick,
        "units": str(units),
        "cost": shown(cost),
        "sell_value": shown(net),
        "result": shown(net - cost),
        "favorite": bool(row.get("favorite", False)),
        "base": shown(coin.base),
        "max": shown(coin.ceiling),
        "min": shown(coin.floor),
        "description":row.get('description',''),
    }


async def market(db, user_id, *, visit=False):
    await require(db, new=False)
    enabled = await system_flags.is_enabled(db, "coin_market_v2")
    rows = await repo.rows(db, user_id)
    positions = await repo.user_shorts(db, user_id)
    owns = any(int(r["user_units"]) or r["owner_id"] == user_id for r in rows) or bool(
        positions
    )
    if not enabled and not owns:
        raise Unavailable("Биржа ещё не открыта.")
    tick = await repo.current_tick(db)
    coins = []
    for row in rows:
        public = public_coin(row)
        public["owned"] = row["owner_id"] == user_id
        previous = await repo.history(db, row["id"], max(0, tick - 288))
        start = (
            int(previous[0]["price"])
            if previous
            else int(repo.decode(row["price_state"])["price"])
        )
        public["change_24h"] = round(
            (float(public["price"]) * rules.MORA / start - 1) * 100, 2
        )
        public["change_period"] = (
            "24ч" if previous and previous[0]["tick"] <= tick - 288 else "с запуска"
        )
        public["fresh"] = public["tick"] == tick
        coins.append(public)
    coin_map = {row["id"]: row for row in rows}
    short_list = []
    for row in positions:
        position = repo.short_payload(row)
        coin, book, state, _ = checked(coin_map[row["coin_id"]])
        result = rules.close_short(coin, book, state.price, position)
        short_list.append(
            {
                "id": row["id"],
                "coin_id": coin.key,
                "collateral": shown(position.collateral),
                "received": shown(result.payout),
                "result": shown(result.payout - position.collateral),
                "liquidation_price": shown(
                    position.escrow
                    * rules.TOKEN
                    * rules.BPS
                    // (position.units * (rules.BPS + rules.FEE_BPS))
                    - rules.ceildiv(
                        position.collateral * rules.TOKEN * rules.BPS,
                        5 * position.units * (rules.BPS + rules.FEE_BPS),
                    )
                ),
            }
        )
    news = []
    if visit:
        snapshot = {c["id"]: c["price"] for c in coins}
        async with db.connection.transaction():
            old = await repo.visit(db, user_id, snapshot)
        if old:
            for c in coins:
                if c["id"] in old and (
                    int(next(r for r in rows if r["id"] == c["id"])["user_units"])
                    or c["favorite"]
                ):
                    change = (Decimal(c["price"]) / Decimal(old[c["id"]]) - 1) * 100
                    if abs(change) >= 1:
                        news.append(
                            {
                                "coin_id": c["id"],
                                "text": f"{c['ticker']}: {change:+.1f}% с прошлого визита",
                            }
                        )
        else:
            news = [
                {
                    "coin_id": None,
                    "text": "Выберите монету и сумму Моры для первой покупки.",
                }
            ]
    return {
        "enabled": enabled,
        "shorts_enabled": enabled
        and await system_flags.is_enabled(db, "coin_market_v2_shorts"),
        "coins": coins,
        "shorts": short_list,
        "news": news[:3],
        "rules": rules.RULES_VERSION,
        "balances": await repo.balances(db, user_id),
        "user_id": user_id,
    }


async def availability(db, user_id):
    if not await repo.ready(db):
        return {"visible": False}
    if await system_flags.is_enabled(db, "coin_market_v2"):
        return {"visible": True}
    rows = await repo.rows(db, user_id)
    return {
        "visible": any(int(r["user_units"]) or r["owner_id"] == user_id for r in rows)
        or bool(await repo.user_shorts(db, user_id))
    }


def quote_result(coin, book, state, side, amount, units, position=None):
    if side == "buy":
        result = rules.buy(coin, book, state.price, amount)
        return result, {
            "spent": shown(-result.flow.wallet),
            "received_units": str(result.units),
            "commission": shown(result.commission),
        }
    if side == "sell":
        result = rules.sell(coin, book, state.price, units)
        return result, {
            "received": shown(result.flow.wallet),
            "sold_units": str(units),
            "zero_payout": result.flow.wallet == 0,
            "commission": shown(result.commission),
        }
    if side == "short":
        result = rules.open_short(coin, book, state.price, amount)
        p = result.position
        price_limit = (
            (p.escrow - p.collateral // 5)
            * rules.TOKEN
            * rules.BPS
            // (p.units * (rules.BPS + rules.FEE_BPS))
        )
        return result, {
            "spent": shown(amount),
            "collateral": shown(amount),
            "commission": shown(result.commission),
            "max_loss": shown(amount),
            "liquidation_price": shown(price_limit),
        }
    if side == "close_short" and position:
        result = rules.close_short(
            coin, book, state.price, repo.short_payload(position)
        )
        return result, {
            "received": shown(result.payout),
            "commission": shown(result.commission),
            "penalty": shown(result.penalty),
        }
    raise rules.MarketError("Неизвестное действие.")


async def quote(db, user_id, coin_id, side, *, amount=0, units=0, position_id=None):
    await require(db, new=side in ("buy", "short"), shorts=side == "short")
    if not await advance(db, coin_id):
        raise Unavailable("Рынок обновляется.")
    row = await repo.load(db, coin_id)
    coin, book, state, _ = checked(row)
    held, _ = await repo.account(db, coin_id, user_id)
    if side == "sell" and units > held:
        raise rules.MarketError("Недостаточно ваших монет.")
    position = next(
        (
            p
            for p in await repo.active_shorts(db, coin_id)
            if p["id"] == position_id and p["user_id"] == user_id
        ),
        None,
    )
    result, preview = quote_result(coin, book, state, side, amount, units, position)
    if side in ('buy','short'):
        available=await repo.balances(db,user_id)
        if Decimal(available.get('mora','0'))*rules.MORA < -result.flow.wallet:
            raise rules.MarketError('Недостаточно свободной Моры.')
    if side=='short' and any(p['user_id']==user_id for p in await repo.active_shorts(db,coin_id)):
        raise rules.MarketError('У вас уже есть позиция на падение этой монеты.')
    return {
        **preview,
        "coin_id": coin_id,
        "side": side,
        "price": shown(state.price),
        "tick": state.tick,
        "expires_at": (state.tick + 1) * rules.TICK_SECONDS,
    }


async def trade(
    db,
    user_id,
    coin_id,
    side,
    *,
    action_id,
    tick,
    price,
    amount=0,
    units=0,
    position_id=None,
):
    action(action_id)
    signature = fingerprint(
        {
            "coin": coin_id,
            "side": side,
            "tick": tick,
            "price": price,
            "amount": amount,
            "units": units,
            "position": position_id,
        }
    )
    await require(db, new=False)
    previous = await replay(db, user_id, action_id, signature)
    if previous:
        return previous
    await require(db, new=side in ("buy", "short"), shorts=side == "short")
    if not await advance(db, coin_id):
        raise Unavailable("Рынок обновляется.")
    async with db.connection.transaction():
        row = await repo.load(db, coin_id, lock=True)
        coin, book, state, _ = checked(row)
        await repo.user_lock(db, user_id)
        previous = await replay(db, user_id, action_id, signature)
        if previous:
            return previous
        await require(db, new=side in ("buy", "short"), shorts=side == "short")
        if side in ("buy", "short"):
            await repo.require_active(db, user_id)
        if (
            state.tick != tick
            or state.price != price
            or state.tick != await repo.current_tick(db)
        ):
            raise Requote("Цена обновилась. Проверьте новые условия.")
        await repo.reconcile(db, row, book)
        held, cost = await repo.account(db, coin_id, user_id)
        if side == "sell" and units > held:
            raise rules.MarketError("Недостаточно ваших монет.")
        positions = await repo.active_shorts(db, coin_id)
        position = next(
            (
                p
                for p in positions
                if p["id"] == position_id and p["user_id"] == user_id
            ),
            None,
        )
        if side == "close_short":
            if not position:
                raise rules.MarketError(
                    "Позиция уже закрыта или принадлежит другому игроку."
                )
            book, response = await settle_short(
                db,
                row,
                book,
                state,
                {**position, "action_id": action_id, "signature": signature},
            )
        else:
            if side == "short" and any(p["user_id"] == user_id for p in positions):
                raise rules.MarketError(
                    "У вас уже есть позиция на падение этой монеты."
                )
            result, preview = quote_result(coin, book, state, side, amount, units)
            op = await wallet(db, user_id, result.flow.wallet, action_id, coin_id)
            response = {
                "ok": True,
                **preview,
                "side": side,
                "coin_id": coin_id,
                "price": shown(state.price),
                "tick": state.tick,
            }
            if side == "buy":
                await repo.put_account(
                    db, coin_id, user_id, held + result.units, cost - result.flow.wallet
                )
            elif side == "sell":
                allocated = cost if units == held else cost * units // held
                await repo.put_account(
                    db, coin_id, user_id, held - units, cost - allocated
                )
                response["realized_result"] = shown(result.flow.wallet - allocated)
            else:
                pid = uuid4().hex
                await repo.put_short(
                    db,
                    position_id=pid,
                    coin_id=coin_id,
                    user_id=user_id,
                    position=result.position,
                    tick=state.tick,
                )
                response["position_id"] = pid
            book = result.book
            await repo.receipt(
                db, user_id, action_id, signature, response, op, coin_id, result.flow
            )
        await repo.save(db, coin_id, book, state)
        await repo.reconcile(db, row, book)
        return response


def creation_terms(name, zarniki, deposit):
    if not isinstance(name, str):
        raise rules.MarketError("Введите название монеты.")
    name = " ".join(unicodedata.normalize("NFKC", name).split())
    if not 3 <= len(name) <= 24 or any(
        unicodedata.category(ch).startswith("C") for ch in name
    ):
        raise rules.MarketError(
            "Название — от 3 до 24 символов без управляющих знаков."
        )
    if any(
        word in name.casefold()
        for word in ("predvestnik", "предвестник", "официальн", "системн")
    ):
        raise rules.MarketError("Это название зарезервировано.")
    genesis = rules.personal_genesis("preview", deposit, zarniki)
    return name, genesis


async def creation_quote(db,user_id, *, name,zarniki,deposit,diamonds=False):
    await require(db)
    name,g=creation_terms(name,zarniki,deposit)
    rows=await repo.rows(db,user_id)
    if any(r['owner_id']==user_id for r in rows):
        raise rules.MarketError('У вас уже есть своя монета.')
    if any(r['name_key']==name.casefold() for r in rows):
        raise rules.MarketError('Название уже занято.')
    balances=await repo.balances(db,user_id)
    if Decimal(balances.get('zarniki','0'))<zarniki:
        raise rules.MarketError('Недостаточно Зарников на создание.')
    if diamonds:
        fund=await repo.peek_fund(db)
        if not fund or int(fund['mora'])<deposit or deposit%(10*rules.MORA):
            raise rules.MarketError('Вклад алмазами сейчас недоступен. Выберите Мору.')
        if Decimal(balances.get('diamonds','0'))<Decimal(deposit)/(1000*rules.MORA):
            raise rules.MarketError('Недостаточно алмазов.')
    elif Decimal(balances.get('mora','0'))<Decimal(deposit)/rules.MORA:
        raise rules.MarketError('Недостаточно Моры для вклада.')
    if await star_payments_v1.has_open_premium_hold(db,user_id):
        raise rules.MarketError('Создание временно недоступно: платёж проверяется.')
    return {'name':name,'price':shown(g.coin.base),'creator_units':str(g.creator_units),
            'zarniki':zarniki,'deposit':shown(deposit),'diamonds':diamonds}


async def create_coin(
    db, user_id, *, name, zarniki, deposit, diamonds=False, action_id, icon='coin'
):
    action(action_id)
    name, _ = creation_terms(name, zarniki, deposit)
    if icon not in ('coin','star','wave','leaf'):
        raise rules.MarketError('Выберите значок из каталога.')
    signature = fingerprint(
        {"create": name, "zarniki": zarniki, "deposit": deposit, "diamonds": diamonds,'icon':icon}
    )
    await require(db, new=False)
    async with db.connection.transaction():
        await repo.user_lock(db, user_id)
        old = await replay(db, user_id, action_id, signature)
        if old:
            return old
        await require(db)
        await repo.require_active(db, user_id)
        await repo.catalogue_lock(db)
        if await repo.coin_count(db) >= 500:
            raise rules.MarketError("Сейчас достигнут лимит монет биржи.")
        if await star_payments_v1.has_open_premium_hold(db, user_id):
            raise rules.MarketError("Создание временно недоступно: платёж проверяется.")
        if any(r["owner_id"] == user_id for r in await repo.rows(db, user_id)):
            raise rules.MarketError("У вас уже есть своя монета.")
        if any(r["name_key"] == name.casefold() for r in await repo.rows(db, user_id)):
            raise rules.MarketError("Название уже занято.")
        extra = {"zarniki": -zarniki}
        if diamonds:
            fund = await repo.lock_fund(db)
            if not fund or int(fund["mora"]) < deposit or deposit % (10 * rules.MORA):
                raise rules.MarketError(
                    "Вклад алмазами сейчас недоступен. Выберите Мору."
                )
            hundredths = deposit // (10 * rules.MORA)
            extra["diamonds"] = -Decimal(hundredths) / 100
            await repo.convert_deposit(db, deposit, hundredths)
        key = uuid4().hex
        genesis = rules.personal_genesis(key, deposit, zarniki)
        _, secret_id = configuration()
        tick = await repo.current_tick(db)
        state = rules.PriceState(tick, genesis.coin.base)
        await repo.insert_coin(
            db,
            coin=genesis.coin,
            book=genesis.book,
            state=state,
            owner_id=user_id,
            name=name,
            ticker="P" + key[:6].upper(),
            icon=icon,
            character="flow",
            group="personal-" + str(int(key[:2], 16) % 3),
            rules=rules.RULES_VERSION,
            secret_id=secret_id,
        )
        await repo.put_account(db, key, user_id, genesis.creator_units, 0)
        op = await wallet(
            db, user_id, 0 if diamonds else -deposit, action_id, key, extra=extra
        )
        response = {
            "ok": True,
            "coin_id": key,
            "name": name,
            "price": shown(genesis.coin.base),
            "creator_units": str(genesis.creator_units),
            "zarniki_spent": zarniki,
            "deposit": shown(deposit),
            "diamonds": diamonds,
        }
        flow = rules.Flow(
            0 if diamonds else -deposit,
            deposit,
            0,
            0,
            0,
            treasury=-deposit if diamonds else 0,
        )
        await repo.receipt(db, user_id, action_id, signature, response, op, key, flow)
        await repo.reconcile(db, {"id": key}, genesis.book)
        return response


async def edit_metadata(db,user_id,coin_id,icon,description):
    if icon not in ('coin','star','wave','leaf') or not isinstance(description,str) or len(description)>160:
        raise rules.MarketError('Значок из каталога, описание — не длиннее 160 символов.')
    if any(unicodedata.category(ch).startswith('C') for ch in description):
        raise rules.MarketError('Описание содержит недопустимые символы.')
    await require(db,new=False)
    async with db.connection.transaction():
        row=await repo.load(db,coin_id,lock=True)
        if not row or row['owner_id']!=user_id:
            raise rules.MarketError('Изменять оформление может только создатель монеты.')
        await repo.user_lock(db,user_id)
        await repo.require_active(db,user_id)
        await repo.edit_metadata(db,coin_id,icon,description.strip())
    return {'ok':True}


SYSTEM_COINS = (
    ("orb", "Орбита", "ORB", "flow", "sky"),
    ("isk", "Искра", "ISK", "storm", "earth"),
    ("ine", "Иней", "INE", "calm", "earth"),
    ("veg", "Вега", "VEG", "tide", "sky"),
    ("may", "Маяк", "MAY", "calm", "horizon"),
    ("rif", "Риф", "RIF", "flow", "horizon"),
)


async def bootstrap(db, *, source):
    """Explicit offline release operation, never a startup or public endpoint."""
    if await system_flags.is_enabled(db, "coin_market_v2"):
        raise rules.MarketError("Закройте вход в биржу перед начальной настройкой.")
    _, key = configuration()
    return await repo.bootstrap(
        db,
        SYSTEM_COINS,
        key,
        rules.RULES_VERSION,
        await repo.current_tick(db),
        source=source,
    )
