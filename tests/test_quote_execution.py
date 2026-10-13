from decimal import Decimal

import pytest

from models import Order, OrderSide, OrderType, OrderStatus
from order_book import OrderBook
from wallet_manager import WalletManager
from order_manager import OrderManager
from matching_engine import MatchingEngine
from quote_service import QuoteService
from exchange_service import ExchangeService
from datetime import datetime, timezone, timedelta


def setup_exchange_with_quotes():
    wallets = WalletManager()
    orders = OrderManager()
    book = OrderBook("BTCUSDT")

    engine = MatchingEngine(
        book,
        wallets,
        orders,
    )

    quote_service = QuoteService(book)
    exchange = ExchangeService(engine, quote_service)

    return wallets, orders, book, engine, exchange


def add_sell_order(exchange, wallets, price="30000"):
    wallets.get_wallet("seller").deposit(
        "BTC", Decimal("1")
    )

    order = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal(price),
        quantity=Decimal("1"),
    )

    exchange.submit_order(order)
    return order


def test_quote_executes_within_tolerance():
    wallets, orders, book, engine, exchange = (
        setup_exchange_with_quotes()
    )

    add_sell_order(exchange, wallets)

    buyer = wallets.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("50000"))

    quote = exchange.request_quote(
        "buyer",
        OrderSide.BUY,
        Decimal("1"),
    )

    result = exchange.accept_quote(
        quote.id,
        "buyer",
        Decimal("0.002"),
    )

    assert result["status"] == "EXECUTED"
    assert result["order"].status == OrderStatus.FILLED
    assert len(engine.trades) == 1

    assert buyer.get_balance("BTC").available == Decimal("1")
    assert buyer.get_balance("USDT").available == Decimal("20000")
    assert buyer.get_balance("USDT").locked == Decimal("0")
    assert engine.validate_state() is True


def test_price_increase_requires_requote():
    wallets, orders, book, engine, exchange = (
        setup_exchange_with_quotes()
    )

    sell = add_sell_order(exchange, wallets)

    buyer = wallets.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("50000"))

    quote = exchange.request_quote(
        "buyer",
        OrderSide.BUY,
        Decimal("1"),
    )

    assert quote.estimated_total == Decimal("30000")

    exchange.replace_order(
        sell.id,
        user_id="seller",
        new_price=Decimal("31000"),
    )

    result = exchange.accept_quote(
        quote.id,
        "buyer",
        Decimal("0.002"),
    )

    assert result["status"] == "REQUOTE_REQUIRED"
    assert result["new_quote"].estimated_total == Decimal("31000")

    # No trade took place.
    assert len(engine.trades) == 0
    assert buyer.get_balance("USDT").available == Decimal("50000")
    assert buyer.get_balance("USDT").locked == Decimal("0")
    assert engine.validate_state() is True


def test_quote_cannot_execute_twice():
    wallets, orders, book, engine, exchange = (
        setup_exchange_with_quotes()
    )

    add_sell_order(exchange, wallets)

    wallets.get_wallet("buyer").deposit(
        "USDT", Decimal("50000")
    )

    quote = exchange.request_quote(
        "buyer",
        OrderSide.BUY,
        Decimal("1"),
    )

    first = exchange.accept_quote(quote.id, "buyer")

    assert first["status"] == "EXECUTED"

    with pytest.raises(ValueError, match="already used"):
        exchange.accept_quote(quote.id, "buyer")

    assert len(engine.trades) == 1


def test_insufficient_liquidity_requires_requote():
    wallets, orders, book, engine, exchange = (
        setup_exchange_with_quotes()
    )

    sell = add_sell_order(exchange, wallets)

    wallets.get_wallet("buyer").deposit(
        "USDT", Decimal("50000")
    )

    quote = exchange.request_quote(
        "buyer",
        OrderSide.BUY,
        Decimal("1"),
    )

    # Seller removes the liquidity after quote generation.
    exchange.cancel_order_by_id(
        sell.id,
        user_id="seller",
    )

    result = exchange.accept_quote(
        quote.id,
        "buyer",
    )

    assert result["status"] == "REQUOTE_REQUIRED"
    assert result["new_quote"].fillable_quantity == Decimal("0")
    assert len(engine.trades) == 0
    assert engine.validate_state() is True

def test_expired_quote_requires_requote():
    wallets, orders, book, engine, exchange = (
        setup_exchange_with_quotes()
    )

    seller = wallets.get_wallet("seller")
    buyer = wallets.get_wallet("buyer")

    seller.deposit("BTC", Decimal("1"))
    buyer.deposit("USDT", Decimal("50000"))

    exchange.submit_order(
        Order(
            user_id="seller",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            price=Decimal("30000"),
            quantity=Decimal("1"),
        )
    )

    quote = exchange.request_quote(
        "buyer",
        OrderSide.BUY,
        Decimal("1"),
    )

    # Simulate that the quote has expired.
    quote.expires_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=1)
    )

    result = exchange.accept_quote(
        quote.id,
        "buyer",
    )

    assert result["status"] == "REQUOTE_REQUIRED"
    assert result["new_quote"].id != quote.id

    assert len(engine.trades) == 0
    assert buyer.get_balance("USDT").available == Decimal("50000")
    assert buyer.get_balance("USDT").locked == Decimal("0")

    # Old quote must not work a second time.
    with pytest.raises(ValueError, match="no longer valid"):
        exchange.accept_quote(quote.id, "buyer")

    assert engine.validate_state() is True

def test_sell_quote_slippage_protection():
    wallets, orders, book, engine, exchange = (
        setup_exchange_with_quotes()
    )

    buyer = wallets.get_wallet("buyer")
    seller = wallets.get_wallet("seller")

    buyer.deposit("USDT", Decimal("50000"))
    seller.deposit("BTC", Decimal("1"))

    buy_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(buy_order)

    quote = exchange.request_quote(
        "seller",
        OrderSide.SELL,
        Decimal("1"),
    )

    assert quote.estimated_total == Decimal("30000")

    # Buyer lowers their bid.
    exchange.replace_order(
        buy_order.id,
        user_id="buyer",
        new_price=Decimal("29000"),
    )

    result = exchange.accept_quote(
        quote.id,
        "seller",
        Decimal("0.002"),
    )

    assert result["status"] == "REQUOTE_REQUIRED"
    assert result["new_quote"].estimated_total == Decimal("29000")

    assert seller.get_balance("BTC").available == Decimal("1")
    assert seller.get_balance("BTC").locked == Decimal("0")
    assert seller.get_balance("USDT").available == Decimal("0")

    assert len(engine.trades) == 0
    assert engine.validate_state() is True

def test_quote_excludes_own_orders():
    wallets, orders, book, engine, exchange = (
        setup_exchange_with_quotes()
    )

    alice = wallets.get_wallet("alice")
    bob = wallets.get_wallet("bob")

    alice.deposit("BTC", Decimal("1"))
    bob.deposit("BTC", Decimal("1"))

    alice_sell = Order(
        user_id="alice",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.5"),
    )

    bob_sell = Order(
        user_id="bob",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30100"),
        quantity=Decimal("0.5"),
    )

    exchange.submit_order(alice_sell)
    exchange.submit_order(bob_sell)

    quote = exchange.request_quote(
        "alice",
        OrderSide.BUY,
        Decimal("0.5"),
    )

    # Alice's own cheaper ask must not appear.
    assert quote.estimated_total == Decimal("15050")
    assert quote.worst_price == Decimal("30100")

    assert quote.fills == [
        (Decimal("30100"), Decimal("0.5"))
    ]

    assert len(engine.trades) == 0

def test_old_quote_cannot_be_reused_after_requote():
    wallets, orders, book, engine, exchange = (
        setup_exchange_with_quotes()
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

    original = exchange.request_quote(
        "buyer",
        OrderSide.BUY,
        Decimal("1"),
    )

    exchange.replace_order(
        sell.id,
        user_id="seller",
        new_price=Decimal("31000"),
    )

    result = exchange.accept_quote(
        original.id,
        "buyer",
    )

    assert result["status"] == "REQUOTE_REQUIRED"

    updated = result["new_quote"]

    assert updated.id != original.id
    assert updated.estimated_total == Decimal("31000")

    with pytest.raises(ValueError, match="no longer valid"):
        exchange.accept_quote(
            original.id,
            "buyer",
        )

    assert len(engine.trades) == 0
    assert engine.validate_state() is True