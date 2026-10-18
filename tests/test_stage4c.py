from decimal import Decimal

from models import Order, OrderSide, OrderStatus, OrderType
from order_book import OrderBook
from wallet_manager import WalletManager
from order_manager import OrderManager
from matching_engine import MatchingEngine
from quote_service import QuoteService
from exchange_service import ExchangeService
from exchange_transaction import ExchangeTransaction

import pytest


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


def test_order_service_registers_and_adds_resting_order():
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

    assert orders.get_order(order.id) is order
    assert book.contains_order(order)
    assert order.status == OrderStatus.OPEN
    assert buyer.get_balance("USDT").locked == Decimal("30000")
    assert engine.validate_state() is True


def test_matching_engine_still_executes_trades():
    wallets, orders, book, engine, exchange = setup_exchange()

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
        quantity=Decimal("0.5"),
    )

    buy = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.5"),
    )

    exchange.submit_order(sell)
    exchange.submit_order(buy)

    assert buy.status == OrderStatus.FILLED
    assert sell.status == OrderStatus.FILLED

    assert len(engine.trades) == 1
    assert buyer.get_balance("BTC").available == Decimal("0.5")
    assert seller.get_balance("USDT").available == Decimal("15000")
    assert engine.validate_state() is True


def test_market_sell_remainder_expires():
    wallets, orders, book, engine, exchange = setup_exchange()

    buyer = wallets.get_wallet("buyer")
    seller = wallets.get_wallet("seller")

    buyer.deposit("USDT", Decimal("50000"))
    seller.deposit("BTC", Decimal("1"))

    exchange.submit_order(
        Order(
            user_id="buyer",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=Decimal("30000"),
            quantity=Decimal("0.4"),
        )
    )

    market_sell = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )

    exchange.submit_order(market_sell)

    assert market_sell.status == OrderStatus.EXPIRED
    assert market_sell.filled_quantity == Decimal("0.4")

    assert seller.get_balance("BTC").available == Decimal("0.6")
    assert seller.get_balance("BTC").locked == Decimal("0")
    assert seller.get_balance("USDT").available == Decimal("12000")

    assert orders.get_order(market_sell.id) is market_sell
    assert engine.validate_state() is True

def test_rejected_order_preserved_in_history():
    wallets, orders, book, engine, exchange = setup_exchange()

    buyer = wallets.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("1000"))

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    with pytest.raises(
        ValueError,
        match="Insufficient USDT balance"
    ):
        exchange.submit_order(order)

    assert order.status == OrderStatus.REJECTED
    assert orders.get_order(order.id) is order

    assert not book.contains_order(order)

    assert buyer.get_balance("USDT").available == Decimal("1000")
    assert buyer.get_balance("USDT").locked == Decimal("0")

    assert len(engine.trades) == 0
    assert engine.validate_state() is True

def test_transaction_restores_quote_invalidation():
    wallets, orders, book, engine, exchange = setup_exchange()

    quotes = exchange.quote_service

    quote = exchange.request_quote(
        user_id="buyer",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
    )

    assert not quotes.is_quote_invalidated(quote.id)

    with pytest.raises(RuntimeError, match="Simulated failure"):
        with ExchangeTransaction(engine, quotes):
            quotes.invalidate_quote(quote.id)

            raise RuntimeError("Simulated failure")

    assert not quotes.is_quote_invalidated(quote.id)

def test_non_crossing_self_orders_are_not_cancelled():
    wallets, orders, book, engine, exchange = setup_exchange()

    alice = wallets.get_wallet("alice")
    alice.deposit("BTC", Decimal("1"))
    alice.deposit("USDT", Decimal("50000"))

    sell = Order(
        user_id="alice",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("32000"),
        quantity=Decimal("1"),
    )

    buy = Order(
        user_id="alice",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(sell)
    exchange.submit_order(buy)

    assert sell.status == OrderStatus.OPEN
    assert buy.status == OrderStatus.OPEN

    assert book.contains_order(sell)
    assert book.contains_order(buy)

    assert len(engine.trades) == 0
    assert engine.validate_state() is True