from decimal import Decimal

from models import Order, OrderSide, OrderType
from order_book import OrderBook
from quote_service import QuoteService


def add_limit_order(book, user_id, side, price, quantity):
    order = Order(
        user_id=user_id,
        symbol="BTCUSDT",
        side=side,
        order_type=OrderType.LIMIT,
        price=Decimal(price),
        quantity=Decimal(quantity),
    )

    # Test fixture: add a resting order directly.
    # Production orders should still go through the engine.
    book.add_order(order)

    return order


def test_market_buy_quote():
    book = OrderBook("BTCUSDT")
    quote_service = QuoteService(book)

    add_limit_order(
        book, "alice", OrderSide.SELL, "30000", "0.2"
    )
    add_limit_order(
        book, "bob", OrderSide.SELL, "30100", "0.3"
    )
    add_limit_order(
        book, "charlie", OrderSide.SELL, "30200", "0.5"
    )

    quote = quote_service.get_quote(
        user_id="buyer",
        side=OrderSide.BUY,
        quantity=Decimal("0.6")
    )

    assert quote.fillable_quantity == Decimal("0.6")
    assert quote.can_fully_fill is True

    assert quote.estimated_total == Decimal("18050")

    assert quote.average_price == (
        Decimal("18050") / Decimal("0.6")
    )

    assert quote.worst_price == Decimal("30200")

    assert quote.fills == [
        (Decimal("30000"), Decimal("0.2")),
        (Decimal("30100"), Decimal("0.3")),
        (Decimal("30200"), Decimal("0.1")),
    ]

    # Quote generation doesn't modify resting orders.
    assert book.best_ask() == Decimal("30000")


def test_partial_market_sell_quote():
    book = OrderBook("BTCUSDT")
    quote_service = QuoteService(book)

    add_limit_order(
        book, "buyer",
        OrderSide.BUY,
        "30000",
        "0.5"
    )

    quote = quote_service.get_quote(
        user_id="seller",
        side=OrderSide.SELL,
        quantity=Decimal("1")
    )

    assert quote.fillable_quantity == Decimal("0.5")
    assert quote.remaining_quantity == Decimal("0.5")
    assert quote.can_fully_fill is False

    assert quote.estimated_total == Decimal("15000")
    assert quote.average_price == Decimal("30000")


def test_empty_book_quote():
    book = OrderBook("BTCUSDT")
    quote_service = QuoteService(book)

    quote = quote_service.get_quote(
        user_id="buyer",
        side=OrderSide.BUY,
        quantity=Decimal("1")
    )

    assert quote.fillable_quantity == Decimal("0")
    assert quote.estimated_total == Decimal("0")

    assert quote.average_price is None
    assert quote.worst_price is None

    assert quote.can_fully_fill is False
    assert quote.fills == []
    