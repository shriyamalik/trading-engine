from decimal import Decimal

import pytest

from models import Order, OrderSide, OrderStatus, OrderType
from order_book import OrderBook
from matching_engine import MatchingEngine
from wallet_manager import WalletManager


def setup_exchange():
    wallet_manager = WalletManager()
    book = OrderBook("BTCUSDT")
    engine = MatchingEngine(book, wallet_manager)

    return wallet_manager, book, engine


def test_full_fill():
    wallet_manager, book, engine = setup_exchange()

    seller = wallet_manager.get_wallet("seller")
    buyer = wallet_manager.get_wallet("buyer")

    seller.deposit("BTC", Decimal("1"))
    buyer.deposit("USDT", Decimal("50000"))

    sell_order = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.4"),
    )

    buy_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.4"),
    )

    engine.submit_order(sell_order)
    engine.submit_order(buy_order)

    assert sell_order.status == OrderStatus.FILLED
    assert buy_order.status == OrderStatus.FILLED

    assert seller.get_balance("BTC").available == Decimal("0.6")
    assert seller.get_balance("BTC").locked == Decimal("0")
    assert seller.get_balance("USDT").available == Decimal("12000")

    assert buyer.get_balance("BTC").available == Decimal("0.4")
    assert buyer.get_balance("USDT").available == Decimal("38000")
    assert buyer.get_balance("USDT").locked == Decimal("0")

    assert len(engine.trades) == 1
    assert engine.trades[0].price == Decimal("30000")
    assert engine.trades[0].quantity == Decimal("0.4")


def test_partial_fill():
    wallet_manager, book, engine = setup_exchange()

    seller = wallet_manager.get_wallet("seller")
    buyer = wallet_manager.get_wallet("buyer")

    seller.deposit("BTC", Decimal("0.4"))
    buyer.deposit("USDT", Decimal("50000"))

    sell_order = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.4"),
    )

    buy_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("31000"),
        quantity=Decimal("1"),
    )

    engine.submit_order(sell_order)
    engine.submit_order(buy_order)

    assert sell_order.status == OrderStatus.FILLED
    assert buy_order.status == OrderStatus.PARTIALLY_FILLED

    assert buy_order.filled_quantity == Decimal("0.4")
    assert buy_order.remaining_quantity() == Decimal("0.6")

    assert buyer.get_balance("BTC").available == Decimal("0.4")

    assert buyer.get_balance("USDT").available == Decimal("19400")
    assert buyer.get_balance("USDT").locked == Decimal("18600")


def test_price_improvement_refund():
    wallet_manager, book, engine = setup_exchange()

    seller = wallet_manager.get_wallet("seller")
    buyer = wallet_manager.get_wallet("buyer")

    seller.deposit("BTC", Decimal("1"))
    buyer.deposit("USDT", Decimal("50000"))

    sell_order = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.4"),
    )

    buy_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("31000"),
        quantity=Decimal("0.4"),
    )

    engine.submit_order(sell_order)
    engine.submit_order(buy_order)

    # Buyer reserved 12,400 but only paid 12,000
    assert buyer.get_balance("USDT").available == Decimal("38000")
    assert buyer.get_balance("USDT").locked == Decimal("0")

    assert engine.trades[0].price == Decimal("30000")


def test_locked_balance_matches_remaining_buy_order():
    wallet_manager, book, engine = setup_exchange()

    seller = wallet_manager.get_wallet("seller")
    buyer = wallet_manager.get_wallet("buyer")

    seller.deposit("BTC", Decimal("0.4"))
    buyer.deposit("USDT", Decimal("50000"))

    sell_order = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.4"),
    )

    buy_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("31000"),
        quantity=Decimal("1"),
    )

    engine.submit_order(sell_order)
    engine.submit_order(buy_order)

    expected_locked = (
        buy_order.price * buy_order.remaining_quantity()
    )

    assert buyer.get_balance("USDT").locked == expected_locked


def test_insufficient_usdt():
    wallet_manager, book, engine = setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("1000"))

    buy_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    with pytest.raises(ValueError, match="Insufficient USDT balance"):
        engine.submit_order(buy_order)


def test_insufficient_btc():
    wallet_manager, book, engine = setup_exchange()

    seller = wallet_manager.get_wallet("seller")
    seller.deposit("BTC", Decimal("0.1"))

    sell_order = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    with pytest.raises(ValueError, match="Insufficient BTC balance"):
        engine.submit_order(sell_order)


def test_invalid_negative_quantity():
    wallet_manager, book, engine = setup_exchange()

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("-1"),
    )

    with pytest.raises(ValueError, match="Order quantity must be positive"):
        engine.submit_order(order)


def test_market_order_rejected_for_now():
    wallet_manager, book, engine = setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("50000"))

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )

    with pytest.raises(
        NotImplementedError,
        match="Market orders are not supported yet",
    ):
        engine.submit_order(order)

def test_multiple_price_levels():
    wallet_manager, book, engine = setup_exchange()

    seller1 = wallet_manager.get_wallet("seller1")
    seller2 = wallet_manager.get_wallet("seller2")
    seller3 = wallet_manager.get_wallet("seller3")
    buyer = wallet_manager.get_wallet("buyer")

    seller1.deposit("BTC", Decimal("0.2"))
    seller2.deposit("BTC", Decimal("0.3"))
    seller3.deposit("BTC", Decimal("0.5"))

    buyer.deposit("USDT", Decimal("50000"))

    sell1 = Order(
        user_id="seller1",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.2"),
    )

    sell2 = Order(
        user_id="seller2",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30100"),
        quantity=Decimal("0.3"),
    )

    sell3 = Order(
        user_id="seller3",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30200"),
        quantity=Decimal("0.5"),
    )

    engine.submit_order(sell1)
    engine.submit_order(sell2)
    engine.submit_order(sell3)

    buy_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30200"),
        quantity=Decimal("0.6"),
    )

    engine.submit_order(buy_order)

    # -------------------------
    # CHECK TRADES
    # -------------------------

    assert len(engine.trades) == 3

    assert engine.trades[0].price == Decimal("30000")
    assert engine.trades[0].quantity == Decimal("0.2")

    assert engine.trades[1].price == Decimal("30100")
    assert engine.trades[1].quantity == Decimal("0.3")

    assert engine.trades[2].price == Decimal("30200")
    assert engine.trades[2].quantity == Decimal("0.1")

    # -------------------------
    # CHECK ORDER STATUSES
    # -------------------------

    assert sell1.status == OrderStatus.FILLED
    assert sell2.status == OrderStatus.FILLED

    assert sell3.status == OrderStatus.PARTIALLY_FILLED
    assert sell3.remaining_quantity() == Decimal("0.4")

    assert buy_order.status == OrderStatus.FILLED

    # -------------------------
    # CHECK ORDER BOOK
    # -------------------------

    assert book.best_ask() == Decimal("30200")

    remaining_sell = book.get_best_ask_order()

    assert remaining_sell.user_id == "seller3"
    assert remaining_sell.remaining_quantity() == Decimal("0.4")

    # -------------------------
    # CHECK BUYER BALANCE
    # -------------------------

    assert buyer.get_balance("BTC").available == Decimal("0.6")
    assert buyer.get_balance("USDT").locked == Decimal("0")

    # Actual spend:
    # 0.2 * 30000 = 6000
    # 0.3 * 30100 = 9030
    # 0.1 * 30200 = 3020
    # Total = 18050

    assert buyer.get_balance("USDT").available == Decimal("31950")