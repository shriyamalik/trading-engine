from decimal import Decimal

from models import Order, OrderSide, OrderType
from order_book import OrderBook
from matching_engine import MatchingEngine
from wallet_manager import WalletManager

wallet_manager = WalletManager()
book = OrderBook("BTCUSDT")
engine = MatchingEngine(book, wallet_manager)

alice_wallet = wallet_manager.get_wallet("alice")
bob_wallet = wallet_manager.get_wallet("bob")
charlie_wallet = wallet_manager.get_wallet("charlie")

alice_wallet.deposit("BTC", Decimal("1"))
bob_wallet.deposit("BTC", Decimal("1"))
charlie_wallet.deposit("USDT", Decimal("50000"))

sell1 = Order(
    user_id="alice",
    symbol="BTCUSDT",
    side=OrderSide.SELL,
    order_type=OrderType.LIMIT,
    price=Decimal("30000"),
    quantity=Decimal("0.4")
)

sell2 = Order(
    user_id="bob",
    symbol="BTCUSDT",
    side=OrderSide.SELL,
    order_type=OrderType.LIMIT,
    price=Decimal("30100"),
    quantity=Decimal("0.5")
)


engine.submit_order(sell1)
engine.submit_order(sell2)

book.print_book()


buy = Order(
    user_id="charlie",
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    price=Decimal("30100"),
    quantity=Decimal("0.6")
)

engine.submit_order(buy)

book.print_book()


print("\nTRADES")

for trade in engine.trades:
    print(
        trade.quantity,
        "BTC @",
        trade.price
    )