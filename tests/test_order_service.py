from decimal import Decimal

import pytest

from models import Order, OrderSide, OrderType, OrderStatus
from order_book import OrderBook
from wallet_manager import WalletManager
from order_manager import OrderManager
from matching_engine import MatchingEngine
from quote_service import QuoteService
from exchange_service import ExchangeService


def setup_exchange():
    wallets = WalletManager()
    orders = OrderManager()
    book = OrderBook("BTCUSDT")

    engine = MatchingEngine(book, wallets, orders)
    exchange = ExchangeService(
        engine,
        QuoteService(book)
    )

    return wallets, orders, book, engine, exchange


def test_submit_and_lookup_order():
    wallets, orders, book, engine, exchange = setup_exchange()

    buyer = wallets.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("50000"))

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(order)

    stored = exchange.get_order(order.id, "buyer")

    assert stored is order
    assert stored.status == OrderStatus.OPEN
    assert book.contains_order(order)


def test_another_user_cannot_lookup_order():
    wallets, orders, book, engine, exchange = setup_exchange()

    wallets.get_wallet("alice").deposit(
        "USDT", Decimal("50000")
    )

    order = Order(
        user_id="alice",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(order)

    with pytest.raises(ValueError, match="does not own"):
        exchange.get_order(order.id, "bob")


def test_order_service_cancellation():
    wallets, orders, book, engine, exchange = setup_exchange()

    buyer = wallets.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("50000"))

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(order)

    exchange.cancel_order_by_id(
        order.id,
        user_id="buyer"
    )

    assert order.status == OrderStatus.CANCELLED
    assert buyer.get_balance("USDT").locked == Decimal("0")
    assert not book.contains_order(order)
    assert engine.validate_state() is True


def test_order_service_replacement():
    wallets, orders, book, engine, exchange = setup_exchange()

    buyer = wallets.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("50000"))

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("29000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(order)

    replacement = exchange.replace_order(
        order.id,
        user_id="buyer",
        new_price=Decimal("30000")
    )

    assert order.status == OrderStatus.CANCELLED
    assert replacement.id != order.id
    assert replacement.price == Decimal("30000")

    assert book.contains_order(replacement)
    assert not book.contains_order(order)

    assert buyer.get_balance("USDT").locked == Decimal("30000")
    assert engine.validate_state() is True

def test_invalid_replacement_preserves_original():
    wallets, orders, book, engine, exchange = (
        setup_exchange()
    )

    buyer = wallets.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("50000"))

    original = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("29000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(original)

    with pytest.raises(
        ValueError,
        match="quantity must be positive"
    ):
        exchange.replace_order(
            original.id,
            user_id="buyer",
            new_quantity=Decimal("-1"),
        )

    assert original.status == OrderStatus.OPEN
    assert book.contains_order(original)
    assert buyer.get_balance("USDT").locked == Decimal("29000")
    assert engine.validate_state() is True

def test_failed_replacement_rolls_back():
    wallets, orders, book, engine, exchange = (
        setup_exchange()
    )

    buyer = wallets.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("30000"))

    original = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("29000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(original)

    with pytest.raises(
        ValueError,
        match="Insufficient USDT balance"
    ):
        exchange.replace_order(
            original.id,
            user_id="buyer",
            new_price=Decimal("31000"),
        )

    # The original order still exists unchanged.
    assert original.status == OrderStatus.OPEN
    assert original.price == Decimal("29000")
    assert book.contains_order(original)

    # Locked funds are restored.
    assert buyer.get_balance("USDT").available == Decimal("1000")
    assert buyer.get_balance("USDT").locked == Decimal("29000")

    # Failed replacement is removed from order history.
    assert len(orders.orders) == 1

    assert engine.validate_state() is True

def test_other_user_cannot_replace_order():
    wallets, orders, book, engine, exchange = (
        setup_exchange()
    )

    alice = wallets.get_wallet("alice")
    alice.deposit("USDT", Decimal("50000"))

    order = Order(
        user_id="alice",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(order)

    with pytest.raises(ValueError, match="does not own"):
        exchange.replace_order(
            order.id,
            user_id="bob",
            new_price=Decimal("31000"),
        )

    assert order.status == OrderStatus.OPEN
    assert book.contains_order(order)
    assert engine.validate_state() is True