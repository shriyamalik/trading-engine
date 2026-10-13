from decimal import Decimal

import pytest

from models import Order, OrderSide, OrderStatus, OrderType
from order_book import OrderBook
from matching_engine import MatchingEngine
from wallet_manager import WalletManager
from order_manager import OrderManager

def setup_exchange():
    wallet_manager = WalletManager()
    order_manager = OrderManager()
    book = OrderBook("BTCUSDT")
    engine = MatchingEngine(book, wallet_manager, order_manager)

    return wallet_manager, order_manager, book, engine


def test_full_fill():
    wallet_manager, order_manager, book, engine = setup_exchange()

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
    wallet_manager, order_manager, book, engine = setup_exchange()

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
    wallet_manager, order_manager, book, engine = setup_exchange()

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
    wallet_manager, order_manager, book, engine = setup_exchange()

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
    wallet_manager, order_manager, book, engine = setup_exchange()

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
    wallet_manager, order_manager, book, engine = setup_exchange()

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
    wallet_manager, order_manager, book, engine = setup_exchange()

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


# def test_market_order_rejected_for_now():
#     wallet_manager, book, engine = setup_exchange()

#     buyer = wallet_manager.get_wallet("buyer")
#     buyer.deposit("USDT", Decimal("50000"))

#     order = Order(
#         user_id="buyer",
#         symbol="BTCUSDT",
#         side=OrderSide.BUY,
#         order_type=OrderType.MARKET,
#         quantity=Decimal("1"),
#     )

#     with pytest.raises(
#         NotImplementedError,
#         match="Market orders are not supported yet",
#     ):
#         engine.submit_order(order)

def test_multiple_price_levels():
    wallet_manager, order_manager, book, engine = setup_exchange()

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

def test_cancel_buy_order():
    wallet_manager, order_manager, book, engine =setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("50000"))

    buy_order = Order(
        user_id= "buyer",
        symbol= "BTCUSDT",
        side= OrderSide.BUY,
        order_type= OrderType.LIMIT,
        price = Decimal("30000"),
        quantity= Decimal("1"),
    )

    engine.submit_order(buy_order)

    assert buyer.get_balance("USDT").available == Decimal("20000")
    assert buyer.get_balance("USDT").locked == Decimal("30000")

    engine.cancel_order(buy_order)

    assert buy_order.status == OrderStatus.CANCELLED
    assert buyer.get_balance("USDT").available == Decimal("50000")
    assert buyer.get_balance("USDT").locked == Decimal("0")

    assert not book.contains_order(buy_order)

def test_cancel_partially_filled_buy_order():
    wallet_manager, order_manager, book, engine = setup_exchange()

    seller = wallet_manager.get_wallet("seller")
    seller.deposit("BTC", Decimal("0.4"))

    buyer = wallet_manager.get_wallet("buyer")
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
        quantity=Decimal("1"),
    )

    engine.submit_order(sell_order)
    engine.submit_order(buy_order)

    assert buy_order.remaining_quantity() == Decimal("0.6")
    assert buyer.get_balance("USDT").locked == Decimal("18000")

    engine.cancel_order(buy_order)

    assert buy_order.status == OrderStatus.CANCELLED

    assert buyer.get_balance("USDT").locked == Decimal("0")
    assert buyer.get_balance("USDT").available == Decimal("38000")
    assert buyer.get_balance("BTC").available == Decimal("0.4")
    

def test_market_buy_partial_fill():
    wallet_manager, order_manager, book, engine = setup_exchange()

    seller1 = wallet_manager.get_wallet("seller1")
    seller2 = wallet_manager.get_wallet("seller2")
    buyer = wallet_manager.get_wallet("buyer")

    seller1.deposit("BTC", Decimal("0.2"))
    seller2.deposit("BTC", Decimal("0.4"))
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
        quantity=Decimal("0.4"),
    )

    engine.submit_order(sell1)
    engine.submit_order(sell2)

    market_buy = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )

    engine.submit_order(market_buy)

    assert market_buy.filled_quantity == Decimal("0.6")
    assert market_buy.remaining_quantity() == Decimal("0.4")

    assert market_buy.status == OrderStatus.EXPIRED

    assert buyer.get_balance("BTC").available == Decimal("0.6")

    # 0.2 * 30000 = 6000
    # 0.4 * 30100 = 12040
    # total = 18040

    assert buyer.get_balance("USDT").available == Decimal("31960")
    assert buyer.get_balance("USDT").locked == Decimal("0")

    assert len(engine.trades) == 2

    assert engine.trades[0].price == Decimal("30000")
    assert engine.trades[0].quantity == Decimal("0.2")

    assert engine.trades[1].price == Decimal("30100")
    assert engine.trades[1].quantity == Decimal("0.4")

    assert book.best_ask() is None

def test_full_market_buy():
    wallet_manager, order_manager, book, engine = setup_exchange()

    seller1 = wallet_manager.get_wallet("seller1")
    seller2 = wallet_manager.get_wallet("seller2")
    buyer = wallet_manager.get_wallet("buyer")

    seller1.deposit("BTC", Decimal("0.3"))
    seller2.deposit("BTC", Decimal("0.4"))
    buyer.deposit("USDT", Decimal("50000"))

    sell1 = Order(
        user_id="seller1",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.3"),
    )

    sell2 = Order(
        user_id="seller2",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30100"),
        quantity=Decimal("0.4"),
    )

    engine.submit_order(sell1)
    engine.submit_order(sell2)

    market_buy = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.5"),
    )

    engine.submit_order(market_buy)

    assert market_buy.status == OrderStatus.FILLED
    assert market_buy.filled_quantity == Decimal("0.5")
    assert market_buy.remaining_quantity() == Decimal("0")

    assert buyer.get_balance("BTC").available == Decimal("0.5")
    assert buyer.get_balance("USDT").locked == Decimal("0")

    # 0.3 * 30000 = 9000
    # 0.2 * 30100 = 6020
    # total spend = 15020

    assert buyer.get_balance("USDT").available == Decimal("34980")

    assert len(engine.trades) == 2

    assert engine.trades[0].price == Decimal("30000")
    assert engine.trades[0].quantity == Decimal("0.3")

    assert engine.trades[1].price == Decimal("30100")
    assert engine.trades[1].quantity == Decimal("0.2")

    # 0.2 BTC should remain from seller2
    assert book.best_ask() == Decimal("30100")
    assert book.get_best_ask_order().remaining_quantity() == Decimal("0.2")

def test_partial_market_sell():
    wallet_manager, order_manager, book, engine = setup_exchange()

    buyer1 = wallet_manager.get_wallet("buyer1")
    buyer2 = wallet_manager.get_wallet("buyer2")
    seller = wallet_manager.get_wallet("seller")

    buyer1.deposit("USDT", Decimal("20000"))
    buyer2.deposit("USDT", Decimal("20000"))
    seller.deposit("BTC", Decimal("1"))

    buy1 = Order(
        user_id="buyer1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.2"),
    )

    buy2 = Order(
        user_id="buyer2",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("29900"),
        quantity=Decimal("0.3"),
    )

    engine.submit_order(buy1)
    engine.submit_order(buy2)

    market_sell = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )

    engine.submit_order(market_sell)

    assert market_sell.filled_quantity == Decimal("0.5")
    assert market_sell.remaining_quantity() == Decimal("0.5")
    assert market_sell.status == OrderStatus.EXPIRED

    # Seller sold only 0.5 BTC
    assert seller.get_balance("BTC").available == Decimal("0.5")
    assert seller.get_balance("BTC").locked == Decimal("0")

    # 0.2 * 30000 = 6000
    # 0.3 * 29900 = 8970
    # total proceeds = 14970

    assert seller.get_balance("USDT").available == Decimal("14970")

    assert len(engine.trades) == 2

    assert engine.trades[0].price == Decimal("30000")
    assert engine.trades[0].quantity == Decimal("0.2")

    assert engine.trades[1].price == Decimal("29900")
    assert engine.trades[1].quantity == Decimal("0.3")

    assert book.best_bid() is None

def test_market_buy_with_empty_book():
    wallet_manager, order_manager, book, engine = setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("50000"))

    market_buy = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )

    with pytest.raises(
        ValueError,
        match="No sell liquidity available"
    ):
        engine.submit_order(market_buy)

    # Nothing should have been locked or spent
    assert buyer.get_balance("USDT").available == Decimal("50000")
    assert buyer.get_balance("USDT").locked == Decimal("0")

    assert buyer.get_balance("BTC").available == Decimal("0")

    assert len(engine.trades) == 0

# Testing cases for rejected orders

def test_duplicate_order_submission_rejected():
    wallet_manager, order_manager, book, engine = setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("50000"))

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    engine.submit_order(order)

    with pytest.raises(
        ValueError,
        match="Order has already been submitted"
    ):
        engine.submit_order(order)

    # Should only have been locked once
    assert buyer.get_balance("USDT").available == Decimal("20000")
    assert buyer.get_balance("USDT").locked == Decimal("30000")

def test_invalid_order_becomes_rejected():
    wallet_manager, order_manager, book, engine = setup_exchange()

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("-1"),
    )

    with pytest.raises(ValueError):
        engine.submit_order(order)

    assert order.status == OrderStatus.REJECTED

def test_insufficient_funds_rejects_order():
    wallet_manager, order_manager, book, engine = setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")
    buyer.deposit("USDT", Decimal("100"))

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    with pytest.raises(ValueError):
        engine.submit_order(order)

    assert order.status == OrderStatus.REJECTED

    assert buyer.get_balance("USDT").available == Decimal("100")
    assert buyer.get_balance("USDT").locked == Decimal("0")

def test_filled_order_cannot_be_cancelled():
    wallet_manager, order_manager, book, engine = setup_exchange()

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
        quantity=Decimal("0.5"),
    )

    buy_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.5"),
    )

    engine.submit_order(sell_order)
    engine.submit_order(buy_order)

    assert sell_order.status == OrderStatus.FILLED

    with pytest.raises(
        ValueError,
        match="FILLED orders cannot be cancelled"
    ):
        engine.cancel_order(sell_order)

def test_updated_at_changes_after_fill():
    wallet_manager, order_manager, book, engine = setup_exchange()

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
        quantity=Decimal("0.5"),
    )

    engine.submit_order(sell_order)

    original_updated_at = sell_order.updated_at

    buy_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.5"),
    )

    engine.submit_order(buy_order)

    assert sell_order.updated_at > original_updated_at

def test_multiple_active_orders_have_correct_locked_balance():
    wallet_manager, order_manager, book, engine = setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")

    buyer.deposit(
        "USDT",
        Decimal("100000")
    )

    order1 = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    order2 = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("29000"),
        quantity=Decimal("0.5"),
    )

    engine.submit_order(order1)
    engine.submit_order(order2)

    expected_locked = Decimal("44500")

    assert (
        buyer.get_balance("USDT").locked
        == expected_locked
    )

    assert engine.validate_state() is True

def test_state_validation_detects_wrong_locked_balance():
    wallet_manager, order_manager, book, engine = setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")

    buyer.deposit(
        "USDT",
        Decimal("50000")
    )

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    engine.submit_order(order)

    # Deliberately corrupt state
    buyer.get_balance("USDT").locked = Decimal("25000")

    with pytest.raises(
        RuntimeError,
        match="USDT lock mismatch"
    ):
        engine.validate_state()

def test_self_trade_cancels_resting_order():
    wallet_manager, order_manager, book, engine = setup_exchange()

    alice = wallet_manager.get_wallet("alice")
    bob = wallet_manager.get_wallet("bob")

    alice.deposit("BTC", Decimal("1"))
    alice.deposit("USDT", Decimal("50000"))

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

    engine.submit_order(alice_sell)
    engine.submit_order(bob_sell)

    alice_buy = Order(
        user_id="alice",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30100"),
        quantity=Decimal("0.5"),
    )

    engine.submit_order(alice_buy)

    # Alice's own resting sell was removed
    assert alice_sell.status == OrderStatus.CANCELLED

    # Alice should trade with Bob instead
    assert bob_sell.status == OrderStatus.FILLED
    assert alice_buy.status == OrderStatus.FILLED

    assert len(engine.trades) == 1

    assert engine.trades[0].sell_order_id == bob_sell.id
    assert engine.trades[0].buy_order_id == alice_buy.id

    assert engine.validate_state() is True

def test_order_can_be_found_by_id():
    (
        wallet_manager,
        order_manager,
        book,
        engine,
    ) = setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")
    buyer.deposit(
        "USDT",
        Decimal("50000")
    )

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    engine.submit_order(order)

    stored_order = order_manager.get_order(
        order.id
    )

    assert stored_order is order

def test_cancel_order_by_id():
    (
        wallet_manager,
        order_manager,
        book,
        engine,
    ) = setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")
    buyer.deposit(
        "USDT",
        Decimal("50000")
    )

    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    engine.submit_order(order)

    engine.cancel_order_by_id(
        order.id,
        user_id="buyer"
    )

    assert order.status == OrderStatus.CANCELLED

    assert (
        buyer.get_balance("USDT").locked
        == Decimal("0")
    )

def test_replace_order():
    (
        wallet_manager,
        order_manager,
        book,
        engine,
    ) = setup_exchange()

    buyer = wallet_manager.get_wallet("buyer")

    buyer.deposit(
        "USDT",
        Decimal("50000")
    )

    old_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("29000"),
        quantity=Decimal("1"),
    )

    engine.submit_order(old_order)

    replacement = engine.replace_order(
        old_order.id,
        new_price=Decimal("30000"),
    )

    assert old_order.status == OrderStatus.CANCELLED

    assert replacement.id != old_order.id

    assert replacement.price == Decimal("30000")

    assert replacement.quantity == Decimal("1")

    assert replacement.status == OrderStatus.OPEN

    assert order_manager.get_order(
        old_order.id
    ) is old_order

    assert order_manager.get_order(
        replacement.id
    ) is replacement

    assert book.contains_order(
        old_order
    ) is False

    assert book.contains_order(
        replacement
    ) is True

    assert (
        buyer.get_balance("USDT").locked
        == Decimal("30000")
    )