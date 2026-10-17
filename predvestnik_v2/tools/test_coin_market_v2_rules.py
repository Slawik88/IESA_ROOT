"""Candidate economy: adversarial invariants, not a production integration test."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.coin_market_v2 import (
    MORA,
    TOKEN,
    TOTAL_UNITS,
    Book,
    Coin,
    MarketError,
    PriceState,
    buy,
    ceildiv,
    close_short,
    fee,
    next_price,
    open_short,
    personal_genesis,
    sell,
)


class Rules(unittest.TestCase):
    def setUp(self):
        self.coin = Coin("NOVA", 20_000)
        self.book = Book(20_000 * MORA, insurance=10_000 * MORA)
        self.secret = b"simulation-only-not-a-production-secret"

    def test_budget_includes_fee_and_refunds_rounding(self):
        for price in (self.coin.floor, self.coin.base, self.coin.ceiling):
            result = buy(self.coin, self.book, price, 10 * MORA)
            self.assertLessEqual(-result.flow.wallet, 10 * MORA)
            self.assertGreater(result.units, 0)
            self.assertEqual(result.book.held, result.units)

    def test_exit_all_even_when_new_entries_blocked(self):
        coin = Coin("LOW", 1_000_000)
        book = Book(150 * MORA, held=100 * TOKEN)
        with self.assertRaises(MarketError):
            buy(coin, book, coin.floor, 100 * MORA)
        result = sell(coin, book, coin.ceiling, book.held)
        self.assertEqual(result.book.held, 0)
        self.assertGreater(result.flow.wallet, 0)
        result.book.validate(coin)

    def test_full_exit_rounding_multiple_owners(self):
        units = [1_001, 2_003, 7_007]
        coin = self.coin
        total = sum(units)
        book = Book(ceildiv(total * coin.ceiling, TOKEN), held=total)
        for quantity in units:
            book = sell(coin, book, coin.ceiling, quantity).book
        self.assertEqual(book.held, 0)
        self.assertGreaterEqual(book.reserve, 0)

    def test_dust_exit_is_not_subject_to_ten_mora_entry_minimum(self):
        book = Book(MORA, held=TOKEN)
        result = sell(self.coin, book, self.coin.base, TOKEN)
        self.assertGreater(result.flow.wallet, 0)
        self.assertLess(result.flow.wallet, MORA)

    def test_microscopic_remainder_can_exit_across_the_entire_price_band(self):
        genesis = personal_genesis("dust", 1000 * MORA, 1000)
        coin = genesis.coin
        for price in range(coin.floor, coin.ceiling + 1):
            partial = sell(coin, genesis.book, price, genesis.creator_units - 1)
            final = sell(coin, partial.book, price, 1)
            self.assertEqual(final.flow.wallet, 0)
            self.assertEqual(final.book.held, 0)
            final.book.validate(coin)

    def test_gap_to_absolute_max_is_prefunded(self):
        opened = open_short(self.coin, self.book, self.coin.floor, 100 * MORA)
        self.assertGreater(opened.position.coverage, 0)
        closed = close_short(self.coin, opened.book, self.coin.ceiling, opened.position)
        self.assertEqual(closed.payout, 0)
        self.assertTrue(closed.liquidated)
        self.assertEqual(closed.book.borrowed, 0)
        closed.book.validate(self.coin)
        self.assertGreaterEqual(closed.book.insurance, 0)

    def test_insurance_exhaustion_rejects_new_short(self):
        with self.assertRaises(MarketError):
            open_short(self.coin, replace(self.book, insurance=0), self.coin.floor, 100 * MORA)

    def test_borrow_pool_cannot_be_issued_twice(self):
        coin = Coin("SMALL", 1_000_000, supply=1_000 * TOKEN, loan_pool=10 * TOKEN)
        book = Book(10_000 * MORA, borrowed=10 * TOKEN, insurance=1_000 * MORA)
        with self.assertRaises(MarketError):
            open_short(coin, book, coin.base, 10 * MORA)

    def test_short_profit_is_cash_conserving(self):
        opened = open_short(self.coin, self.book, self.coin.base, 100 * MORA)
        closed = close_short(self.coin, opened.book, self.coin.floor, opened.position)
        self.assertGreater(closed.payout, opened.position.collateral)
        before = self.book.reserve + self.book.insurance
        after = closed.book.reserve + closed.book.insurance
        self.assertEqual(before - after,
                         opened.flow.wallet + closed.flow.wallet + opened.flow.burned + closed.flow.burned)

    def test_liquidation_penalty_cannot_create_debt(self):
        opened = open_short(self.coin, self.book, self.coin.base, 100 * MORA)
        closed = close_short(self.coin, opened.book, self.coin.ceiling, opened.position)
        self.assertGreaterEqual(closed.payout, 0)
        self.assertLessEqual(closed.penalty, max(0, opened.position.escrow -
                            ceildiv(opened.position.units * self.coin.ceiling, TOKEN) -
                            fee(ceildiv(opened.position.units * self.coin.ceiling, TOKEN))))

    def test_creation_zarniki_influence_price_with_no_synthetic_mora(self):
        low = personal_genesis("LOW", 1_000 * MORA, 1_000)
        high = personal_genesis("HIGH", 1_000 * MORA, 5_000)
        self.assertGreater(high.coin.base, low.coin.base)
        self.assertEqual(low.coin.base, 1_000)
        self.assertEqual(high.coin.base, 1_200)
        self.assertEqual(high.book.reserve, low.book.reserve)
        for genesis in (low, high):
            result = sell(genesis.coin, genesis.book, genesis.coin.base, genesis.creator_units)
            self.assertLess(result.flow.wallet, 1_000 * MORA)
            self.assertEqual(genesis.coin.supply, TOTAL_UNITS)

    def test_all_creation_tiers_are_covered_at_maximum_exit_price(self):
        for zarniki in (1_000, 2_500, 5_000):
            for deposit in (1_000, 10_000, 100_000):
                genesis = personal_genesis("GEN", deposit * MORA, zarniki)
                sold = sell(genesis.coin, genesis.book, genesis.coin.ceiling, genesis.creator_units)
                self.assertLess(sold.flow.wallet, deposit * MORA)
                sold.book.validate(genesis.coin)

    def test_inputs_and_foreign_positions_fail_closed(self):
        for amount in (True, 0, -1, 1.2, "10", 10**25):
            with self.assertRaises(MarketError):
                buy(self.coin, self.book, self.coin.base, amount)
        with self.assertRaises(MarketError):
            sell(self.coin, self.book, self.coin.base, 1)
        opened = open_short(self.coin, self.book, self.coin.base, 10 * MORA)
        with self.assertRaises(MarketError):
            close_short(Coin("OTHER", 20_000), opened.book, self.coin.base, opened.position)

    def test_restart_and_visits_cannot_advance_server_history(self):
        state = PriceState(0, self.coin.base)
        history = []
        for _ in range(576):
            history.append(state)
            state = next_price(self.coin, state, secret=self.secret, character="storm", group="north")
        restart = PriceState(**vars(history[288]))
        for _ in range(288):
            restart = next_price(self.coin, restart, secret=self.secret, character="storm", group="north")
        self.assertEqual(state, restart)
        self.assertEqual(history[0], PriceState(0, self.coin.base))

    def test_price_path_is_trade_independent_and_strictly_capped(self):
        left = right = PriceState(0, self.coin.base)
        book = self.book
        for _ in range(1_000):
            prior = left.price
            left = next_price(self.coin, left, secret=self.secret, character="tide", group="north")
            right = next_price(self.coin, right, secret=self.secret, character="tide", group="north")
            self.assertEqual(left, right)
            self.assertLessEqual(abs(left.price - prior) * 10_000, prior * 250)
            trade = buy(self.coin, book, left.price, 10 * MORA)
            book = sell(self.coin, trade.book, left.price, trade.units).book


if __name__ == "__main__":
    unittest.main()
