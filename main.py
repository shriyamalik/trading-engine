# Practice an implementation of an order book 
# gives information about an order for example bid, size price etc

from decimal import Decimal

from models import Order, OrderSide, OrderType
from order_book import OrderBook


book = OrderBook("BTCUSDT")


# ----------------------
# BUY ORDERS
# ----------------------

buy1 = Order(
    user_id="alice",
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    price=Decimal("29900"),
    quantity=Decimal("0.3")
)

buy2 = Order(
    user_id="bob",
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    price=Decimal("29800"),
    quantity=Decimal("1.0")
)

buy3 = Order(
    user_id="charlie",
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    price=Decimal("29700"),
    quantity=Decimal("0.5")
)


# ----------------------
# SELL ORDERS
# ----------------------

sell1 = Order(
    user_id="david",
    symbol="BTCUSDT",
    side=OrderSide.SELL,
    order_type=OrderType.LIMIT,
    price=Decimal("30100"),
    quantity=Decimal("0.4")
)

sell2 = Order(
    user_id="emma",
    symbol="BTCUSDT",
    side=OrderSide.SELL,
    order_type=OrderType.LIMIT,
    price=Decimal("30200"),
    quantity=Decimal("0.5")
)

sell3 = Order(
    user_id="frank",
    symbol="BTCUSDT",
    side=OrderSide.SELL,
    order_type=OrderType.LIMIT,
    price=Decimal("30300"),
    quantity=Decimal("0.8")
)


book.add_order(buy1)
book.add_order(buy2)
book.add_order(buy3)

book.add_order(sell1)
book.add_order(sell2)
book.add_order(sell3)

book.print_book()