from decimal import Decimal

from models import Order, OrderSide, OrderType
from order_book import OrderBook
from wallet_manager import WalletManager
from settlement_service import SettlementService


def test_limit_buy_reservation_and_release():
    wallets = WalletManager()
    settlement = SettlementService(wallets)
    book = OrderBook("BTCUSDT")

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

    settlement.reserve_funds(order, book)

    assert buyer.get_balance("USDT").available == Decimal("20000")
    assert buyer.get_balance("USDT").locked == Decimal("30000")

    settlement.release_order_funds(order)

    assert buyer.get_balance("USDT").available == Decimal("50000")
    assert buyer.get_balance("USDT").locked == Decimal("0")


def test_trade_settlement_and_price_improvement():
    wallets = WalletManager()
    settlement = SettlementService(wallets)
    book = OrderBook("BTCUSDT")

    buyer = wallets.get_wallet("buyer")
    seller = wallets.get_wallet("seller")

    buyer.deposit("USDT", Decimal("50000"))
    seller.deposit("BTC", Decimal("1"))

    buy_order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("31000"),
        quantity=Decimal("0.5"),
    )

    sell_order = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.5"),
    )

    settlement.reserve_funds(buy_order, book)
    settlement.reserve_funds(sell_order, book)

    settlement.settle_trade(
        buy_order,
        sell_order,
        Decimal("30000"),
        Decimal("0.5")
    )

    # Buyer initially reserved 15,500 USDT
    # but paid 15,000, so gets 500 back.
    assert buyer.get_balance("USDT").available == Decimal("35000")
    assert buyer.get_balance("USDT").locked == Decimal("0")
    assert buyer.get_balance("BTC").available == Decimal("0.5")

    assert seller.get_balance("BTC").locked == Decimal("0")
    assert seller.get_balance("USDT").available == Decimal("15000")


def test_market_sell_remainder_is_unlocked():
    wallets = WalletManager()
    settlement = SettlementService(wallets)
    book = OrderBook("BTCUSDT")

    seller = wallets.get_wallet("seller")
    seller.deposit("BTC", Decimal("1"))

    order = Order(
        user_id="seller",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("1"),
    )

    settlement.reserve_funds(order, book)

    # Simulate that 0.4 BTC has been sold.
    seller.consume_locked("BTC", Decimal("0.4"))
    order.filled_quantity = Decimal("0.4")

    settlement.release_market_remainder(order)

    assert seller.get_balance("BTC").available == Decimal("0.6")
    assert seller.get_balance("BTC").locked == Decimal("0")