from decimal import Decimal
import pytest

from models import Order, OrderSide, OrderType
from wallet import Wallet
from order_book import OrderBook
from quote_service import QuoteService


@pytest.mark.parametrize(
    "quantity",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("0"),
        Decimal("-1"),
        0.1,
    ]
)
def test_invalid_order_quantity(quantity):
    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        price=Decimal("30000")
    )

    with pytest.raises(ValueError, match="quantity"):
        order.validate()


@pytest.mark.parametrize(
    "price",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("0"),
        Decimal("-100"),
        30000.0,
    ]
)
def test_invalid_limit_price(price):
    order = Order(
        user_id="buyer",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        price=price
    )

    with pytest.raises(ValueError, match="price"):
        order.validate()


def test_invalid_wallet_deposit():
    wallet = Wallet("alice")

    for amount in [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-1"),
        Decimal("0"),
    ]:
        with pytest.raises(ValueError):
            wallet.deposit("USDT", amount)

    assert wallet.get_balance("USDT").available == Decimal("0")


def test_invalid_quote_quantity():
    book = OrderBook("BTCUSDT")
    quotes = QuoteService(book)

    with pytest.raises(ValueError):
        quotes.get_quote(
            user_id="alice",
            side=OrderSide.BUY,
            quantity=Decimal("NaN"),
        )

    assert len(quotes.quotes) == 0