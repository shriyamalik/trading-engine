# Keep track of all the orders that are waiting to be filled. Order book keeps a collection of all the orders based on highest bidding price and lowest asking price

from collections import defaultdict, deque
from decimal import Decimal
from typing import Optional

from models import Order, OrderSide, OrderType


class OrderBook:
    def __init__(self, symbol: str):
        self.symbol = symbol

        self.bids: dict[Decimal, deque[Order]] = defaultdict(deque)
        self.asks: dict[Decimal, deque[Order]] = defaultdict(deque)

    def add_order(self, order: Order):
        if order.symbol != self.symbol:
            raise ValueError(
                f"Order symbol {order.symbol} does not match "
                f"order book symbol {self.symbol}"
            )

        if order.order_type != OrderType.LIMIT:
            raise ValueError(
                "Only LIMIT orders can currently be stored in the order book."
            )

        if order.price is None:
            raise ValueError("Limit order must have a price.")

        if order.side == OrderSide.BUY:
            self.bids[order.price].append(order)

        elif order.side == OrderSide.SELL:
            self.asks[order.price].append(order)

    def best_bid(self) -> Optional[Decimal]:
        if not self.bids:
            return None

        return max(self.bids.keys())

    def best_ask(self) -> Optional[Decimal]:
        if not self.asks:
            return None

        return min(self.asks.keys())

    def get_spread(self) -> Optional[Decimal]:
        bid = self.best_bid()
        ask = self.best_ask()

        if bid is None or ask is None:
            return None

        return ask - bid

    def print_book(self):
        print(f"\n===== {self.symbol} ORDER BOOK =====")

        print("\nASKS")
        print("-----------------------")

        for price in sorted(self.asks.keys(), reverse=True):
            quantity = sum(
                order.remaining_quantity()
                for order in self.asks[price]
            )

            print(f"{price:>10} | {quantity} BTC")

        print("\n-----------------------")

        print(f"Best Ask: {self.best_ask()}")
        print(f"Best Bid: {self.best_bid()}")
        print(f"Spread:   {self.get_spread()}")

        print("-----------------------\n")

        print("BIDS")
        print("-----------------------")

        for price in sorted(self.bids.keys(), reverse=True):
            quantity = sum(
                order.remaining_quantity()
                for order in self.bids[price]
            )

            print(f"{price:>10} | {quantity} BTC")


    def get_best_bid_order(self) -> Optional[Order]:
        best_bid_price = self.best_bid()
        if best_bid_price is None:
            return None

        return self.bids[best_bid_price][0]

    def get_best_ask_order(self) -> Optional[Order]:
        best_ask_price = self.best_ask()
        if best_ask_price is None:
            return None

        return self.asks[best_ask_price][0]

    def contains_order(self, order: Order) -> bool:
        book_side = self.bids if order.side == OrderSide.BUY else self.asks

        if order.price not in book_side:
            return False

        return order in book_side[order.price]


    def remove_order(self, order: Order):
        book_side = self.bids if order.side == OrderSide.BUY else self.asks

        if order.price not in book_side:
            return

        if order not in book_side[order.price]:
            return

        book_side[order.price].remove(order)

        if not book_side[order.price]:
            del book_side[order.price]

    def estimate_market_buy_cost(
        self,
        quantity: Decimal
    ) -> tuple[Decimal, Decimal]:

        remaining = quantity
        total_cost = Decimal("0")
        fillable_quantity = Decimal("0")

        for price in sorted(self.asks.keys()):
            for order in self.asks[price]:

                available = order.remaining_quantity()

                trade_quantity = min(
                    remaining,
                    available
                )

                total_cost += trade_quantity * price
                fillable_quantity += trade_quantity
                remaining -= trade_quantity

                if remaining == 0:
                    return total_cost, fillable_quantity

        return total_cost, fillable_quantity