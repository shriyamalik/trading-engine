from decimal import Decimal

from models import Order, OrderSide, OrderType, OrderStatus
from order_book import OrderBook
from order_manager import OrderManager
from wallet_manager import WalletManager
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


def total_asset(wallet_manager, asset):
    total = Decimal("0")

    for wallet in wallet_manager.wallets.values():
        balance = wallet.get_balance(asset)

        total += balance.available
        total += balance.locked

    return total

def test_full_trading_lifecycle_preserves_assets():
    wallets, orders, book, engine, exchange = setup_exchange()

    alice = wallets.get_wallet("alice")
    bob = wallets.get_wallet("bob")
    charlie = wallets.get_wallet("charlie")

    alice.deposit("BTC", Decimal("2"))
    bob.deposit("BTC", Decimal("1"))
    charlie.deposit("USDT", Decimal("100000"))

    initial_btc = total_asset(wallets, "BTC")
    initial_usdt = total_asset(wallets, "USDT")

    # Alice posts a sell order.
    alice_sell = Order(
        user_id="alice",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("1"),
    )

    exchange.submit_order(alice_sell)

    # Charlie buys 0.4 BTC, leaving a partially filled sell.
    charlie_buy = Order(
        user_id="charlie",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("30000"),
        quantity=Decimal("0.4"),
    )

    exchange.submit_order(charlie_buy)

    assert alice_sell.status == OrderStatus.PARTIALLY_FILLED
    assert charlie_buy.status == OrderStatus.FILLED

    # Alice cancels her remaining sell quantity.
    exchange.cancel_order_by_id(
        alice_sell.id,
        user_id="alice",
    )

    assert alice_sell.status == OrderStatus.CANCELLED

    # Bob posts another sell order.
    bob_sell = Order(
        user_id="bob",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        price=Decimal("31000"),
        quantity=Decimal("0.5"),
    )

    exchange.submit_order(bob_sell)

    # Charlie buys Bob's BTC.
    second_buy = Order(
        user_id="charlie",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=Decimal("31000"),
        quantity=Decimal("0.5"),
    )

    exchange.submit_order(second_buy)

    assert second_buy.status == OrderStatus.FILLED

    # No BTC or USDT should have been created or destroyed.
    assert total_asset(wallets, "BTC") == initial_btc
    assert total_asset(wallets, "USDT") == initial_usdt

    # Existing internal consistency checks still pass.
    assert engine.validate_state() is True