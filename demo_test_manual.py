from decimal import Decimal

from exchange_transaction import ExchangeTransaction
from models import Order, OrderSide, OrderType
from order_book import OrderBook
from matching_engine import MatchingEngine
from wallet_manager import WalletManager
from quote_service import QuoteService


wallet_manager = WalletManager()
book = OrderBook("BTCUSDT")
engine = MatchingEngine(book, wallet_manager)
quote_service = QuoteService(book)
exchange = ExchangeTransaction(engine, quote_service)

# -------------------------
# SET UP USERS
# -------------------------

alice = wallet_manager.get_wallet("alice")
bob = wallet_manager.get_wallet("bob")

alice.deposit("BTC", Decimal("1"))
bob.deposit("USDT", Decimal("50000"))


print("\nINITIAL BALANCES")

print("Alice BTC:", alice.get_balance("BTC"))
print("Alice USDT:", alice.get_balance("USDT"))

print("Bob BTC:", bob.get_balance("BTC"))
print("Bob USDT:", bob.get_balance("USDT"))


# -------------------------
# ALICE PLACES SELL ORDER
# -------------------------

sell_order = Order(
    user_id="alice",
    symbol="BTCUSDT",
    side=OrderSide.SELL,
    order_type=OrderType.LIMIT,
    price=Decimal("30000"),
    quantity=Decimal("0.4")
)

exchange.submit_order(sell_order)


print("\nAFTER ALICE SELL ORDER")

print("Alice BTC:", alice.get_balance("BTC"))


# -------------------------
# BOB PLACES BUY ORDER
# -------------------------

buy_order = Order(
    user_id="bob",
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    price=Decimal("31000"),
    quantity=Decimal("0.4")
)

exchange.submit_order(buy_order)


print("\nAFTER TRADE")

print("Alice BTC:", alice.get_balance("BTC"))
print("Alice USDT:", alice.get_balance("USDT"))

print("Bob BTC:", bob.get_balance("BTC"))
print("Bob USDT:", bob.get_balance("USDT"))


print("\nTRADES")

for trade in exchange.trades:
    print(
        trade.quantity,
        "BTC @",
        trade.price
    )