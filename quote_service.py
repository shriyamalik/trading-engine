from decimal import Decimal

from models import OrderSide
from order_book import OrderBook
from quote import Quote


class QuoteService:

    def __init__(self, order_book: OrderBook):
        self.order_book = order_book

        # Quotes issued by this exchange instance.
        self.quotes = {}

        # Successfully executed quote IDs.
        self.used_quote_ids = set()

        self.invalidated_quote_ids = set()

    def get_quote(
            self,
            user_id: str,
            side: OrderSide,
            quantity: Decimal
        ) -> Quote:

        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("Invalid user ID.")

        if not isinstance(side, OrderSide):
            raise ValueError("Invalid quote side.")

        if (
            not isinstance(quantity, Decimal)
            or not quantity.is_finite()
            or quantity <= 0
        ):
            raise ValueError(
                "Quote quantity must be a positive finite Decimal."
            )

        fills = self.order_book.estimate_execution(
            side=side,
            quantity=quantity,
            exclude_user_id=user_id,
        )

        fillable_quantity = sum(
            (qty for price, qty in fills),
            Decimal("0")
        )

        estimated_total = sum(
            (price * qty for price, qty in fills),
            Decimal("0")
        )

        if fillable_quantity > 0:
            average_price = (
                estimated_total / fillable_quantity
            )
            worst_price = fills[-1][0]

        else:
            average_price = None
            worst_price = None

        quote = Quote(
            user_id=user_id,
            symbol=self.order_book.symbol,
            side=side,
            requested_quantity=quantity,
            fillable_quantity=fillable_quantity,
            estimated_total=estimated_total,
            average_price=average_price,
            worst_price=worst_price,
            fills=fills,
        )

        self.quotes[quote.id] = quote

        return quote

    def get_quote_by_id(self, quote_id: str) -> Quote:
        quote = self.quotes.get(quote_id)

        if quote is None:
            raise ValueError("Quote not found.")

        return quote

    def is_quote_used(self, quote_id: str) -> bool:
        return quote_id in self.used_quote_ids

    def mark_quote_used(self, quote_id: str):
        if self.is_quote_used(quote_id):
            raise ValueError("Quote already used.")

        self.used_quote_ids.add(quote_id)

    def invalidate_quote(self, quote_id: str):
        if quote_id not in self.quotes:
            raise ValueError("Quote not found.")

        self.invalidated_quote_ids.add(quote_id)


    def is_quote_invalidated(self, quote_id: str) -> bool:
        return quote_id in self.invalidated_quote_ids