from decimal import Decimal

import pytest

from models import Order, OrderSide, OrderType, OrderStatus
from order_book import OrderBook
from wallet_manager import WalletManager
from order_manager import OrderManager
from matching_engine import MatchingEngine
from quote_service import QuoteService
from exchange_service import ExchangeService


def setup_atomic_exchange():
    wallets = WalletManager()
    orders = OrderManager()
    book = OrderBook("BTCUSDT")

    engine = MatchingEngine(book, wallets, orders)
    quotes = QuoteService(book)
    exchange = ExchangeService(engine, quotes)

    return wallets, orders, book, engine, exchange


def test_second_trade_failure_rolls_back_everything(monkeypatch):
    wallets, orders, book, engine, exchange = (
        setup_atomic_exchange()
    )

    seller1 = wallets.get_wallet("seller1")
    seller2 = wallets.get_wallet("seller2")
    buyer = wallets.get_wallet("buyer")

    seller1.deposit("BTC", Decimal("0.4"))
    seller2.deposit("BTC", Decimal("0.6"))
    buyer.deposit("USDT", Decimal("50000"))

    sell1 = Order(
        user_id="seller1",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.4"),
    )

    sell2 = Order(
        user_id="seller2",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30100"),
        quantity=Decimal("0.6"),
    )

    exchange.submit_order(sell1)
    exchange.submit_order(sell2)

    quote = exchange.request_quote(
        user_id="buyer",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
    )

    original_settle = engine._settle_trade
    settlement_calls = 0

    def failing_settlement(*args, **kwargs):
        nonlocal settlement_calls

        settlement_calls += 1

        if settlement_calls == 2:
            raise RuntimeError("Simulated settlement failure")

        return original_settle(*args, **kwargs)

    monkeypatch.setattr(
        engine,
        "_settle_trade",
        failing_settlement,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated settlement failure",
    ):
        exchange.accept_quote(
            quote.id,
            "buyer",
        )

    assert settlement_calls == 2

    # No trade from the failed operation remains.
    assert len(engine.trades) == 0

    # Original resting orders are restored.
    assert sell1.status == OrderStatus.OPEN
    assert sell2.status == OrderStatus.OPEN

    assert sell1.filled_quantity == Decimal("0")
    assert sell2.filled_quantity == Decimal("0")

    assert book.contains_order(sell1)
    assert book.contains_order(sell2)

    assert book.best_ask() == Decimal("30000")

    # Buyer has not lost any USDT or received BTC.
    assert buyer.get_balance("USDT").available == Decimal("50000")
    assert buyer.get_balance("USDT").locked == Decimal("0")
    assert buyer.get_balance("BTC").available == Decimal("0")

    # Seller funds remain reserved against resting orders.
    assert seller1.get_balance("BTC").locked == Decimal("0.4")
    assert seller2.get_balance("BTC").locked == Decimal("0.6")

    assert seller1.get_balance("USDT").available == Decimal("0")
    assert seller2.get_balance("USDT").available == Decimal("0")

    # The quote was not consumed.
    assert quote.id not in exchange.quote_service.used_quote_ids

    # A failed incoming order should not remain registered.
    assert len(orders.orders) == 2

    assert engine.validate_state() is True

def test_validation_failure_rolls_back_trade(monkeypatch):
    wallets, orders, book, engine, exchange = (
        setup_atomic_exchange()
    )

    seller = wallets.get_wallet("seller")
    buyer = wallets.get_wallet("buyer")

    seller.deposit("BTC", Decimal("1"))
    buyer.deposit("USDT", Decimal("50000"))

    sell = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(sell)

    quote = exchange.request_quote(
        "buyer",
        OrderSide.BUY,
        Decimal("1"),
    )

    original_validate = engine.validate_state
    validation_calls = 0

    def failing_validation():
        nonlocal validation_calls
        validation_calls += 1

        # The engine may already validate during submit_order.
        # Force the first validation during accepted execution
        # to fail after the trade has been processed.
        raise RuntimeError("Simulated invariant failure")

    monkeypatch.setattr(
        engine,
        "validate_state",
        failing_validation,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated invariant failure",
    ):
        exchange.accept_quote(
            quote.id,
            "buyer",
        )

    assert validation_calls >= 1

    # A successful settlement must have been undone.
    assert len(engine.trades) == 0

    assert sell.status == OrderStatus.OPEN
    assert sell.filled_quantity == Decimal("0")

    assert book.contains_order(sell)

    assert seller.get_balance("BTC").locked == Decimal("1")
    assert seller.get_balance("USDT").available == Decimal("0")

    assert buyer.get_balance("USDT").available == Decimal("50000")
    assert buyer.get_balance("USDT").locked == Decimal("0")
    assert buyer.get_balance("BTC").available == Decimal("0")

    assert quote.id not in exchange.quote_service.used_quote_ids

    # Restore validation before checking the restored state.
    monkeypatch.setattr(
        engine,
        "validate_state",
        original_validate,
    )

    assert engine.validate_state() is True