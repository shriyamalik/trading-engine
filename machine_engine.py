from models import Order, OrderSide, OrderStatus, OrderType, Trade
from order_book import OrderBook


class MatchingEngine:
    def __init__(self, order_book: OrderBook):
        self.order_book = order_book
        self.trades: list[Trade] = []

    def submit_order(self, incoming_order: Order):
        if incoming_order.side == OrderSide.BUY:
            self._match_buy_order(incoming_order)

        else:
            self._match_sell_order(incoming_order)

        if (
            incoming_order.remaining_quantity > 0
            and incoming_order.order_type == OrderType.LIMIT
        ):
            self.order_book.add_order(incoming_order)

        return incoming_order

    def _match_buy_order(self, incoming_order: Order):
        while incoming_order.remaining_quantity > 0:

            best_sell = self.order_book.get_best_ask_order()

            if best_sell is None:
                break

            if (
                incoming_order.order_type == OrderType.LIMIT
                and incoming_order.price < best_sell.price
            ):
                break

            self._execute_trade(
                buy_order=incoming_order,
                sell_order=best_sell,
                execution_price=best_sell.price
            )

    def _match_sell_order(self, incoming_order: Order):
        while incoming_order.remaining_quantity > 0:

            best_buy = self.order_book.get_best_bid_order()

            if best_buy is None:
                break

            if (
                incoming_order.order_type == OrderType.LIMIT
                and incoming_order.price > best_buy.price
            ):
                break

            self._execute_trade(
                buy_order=best_buy,
                sell_order=incoming_order,
                execution_price=best_buy.price
            )

    def _execute_trade(
        self,
        buy_order: Order,
        sell_order: Order,
        execution_price
    ):
        trade_quantity = min(
            buy_order.remaining_quantity,
            sell_order.remaining_quantity
        )

        buy_order.filled_quantity += trade_quantity
        sell_order.filled_quantity += trade_quantity

        self._update_order_status(buy_order)
        self._update_order_status(sell_order)

        trade = Trade(
            buy_order_id=buy_order.id,
            sell_order_id=sell_order.id,
            symbol=buy_order.symbol,
            price=execution_price,
            quantity=trade_quantity
        )

        self.trades.append(trade)

        if sell_order.status == OrderStatus.FILLED:
            self.order_book.remove_order(sell_order)

        if buy_order.status == OrderStatus.FILLED:
            if buy_order.price in self.order_book.bids:
                if buy_order in self.order_book.bids[buy_order.price]:
                    self.order_book.remove_order(buy_order)

    def _update_order_status(self, order: Order):
        if order.remaining_quantity == 0:
            order.status = OrderStatus.FILLED

        elif order.filled_quantity > 0:
            order.status = OrderStatus.PARTIALLY_FILLED

        else:
            order.status = OrderStatus.OPEN