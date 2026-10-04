from decimal import Decimal

from models import Order, OrderSide, OrderStatus, OrderType, Trade
from order_book import OrderBook
from wallet_manager import WalletManager


class MatchingEngine:
    def __init__(
        self,
        order_book: OrderBook,
        wallet_manager: WalletManager
):
        self.order_book = order_book
        self.wallet_manager = wallet_manager
        self.trades: list[Trade] = []

    def submit_order(self, incoming_order: Order):
        incoming_order.validate()

        if incoming_order.symbol != self.order_book.symbol:
            raise ValueError("Order symbol does not match this order book.")

        if incoming_order.order_type == OrderType.MARKET:
            raise NotImplementedError(
                "Market orders are not supported yet."
            )
        self._reserve_funds(incoming_order)
        
        if incoming_order.side == OrderSide.BUY:
            self._match_buy_order(incoming_order)

        else:
            self._match_sell_order(incoming_order)

        if (
            incoming_order.remaining_quantity() > 0
            and incoming_order.order_type == OrderType.LIMIT
        ):
            self.order_book.add_order(incoming_order)

        return incoming_order

    def _match_buy_order(self, incoming_order: Order):
        while incoming_order.remaining_quantity() > 0:

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
        while incoming_order.remaining_quantity() > 0:

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
            buy_order.remaining_quantity(),
            sell_order.remaining_quantity()
        )

        self._settle_trade(
            buy_order,
            sell_order,
            execution_price,
            trade_quantity
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

        if self.order_book.contains_order(buy_order):
            if buy_order.status == OrderStatus.FILLED:
                self.order_book.remove_order(buy_order)

        if self.order_book.contains_order(sell_order):
            if sell_order.status == OrderStatus.FILLED:
                self.order_book.remove_order(sell_order)

    def _update_order_status(self, order: Order):
        if order.remaining_quantity() == 0:
            order.status = OrderStatus.FILLED

        elif order.filled_quantity > 0:
            order.status = OrderStatus.PARTIALLY_FILLED

        else:
            order.status = OrderStatus.OPEN

    def _reserve_funds(self, order: Order):
        wallet = self.wallet_manager.get_wallet(order.user_id)

        if order.side == OrderSide.BUY:
            required_usdt = order.price * order.quantity
            wallet.lock("USDT", required_usdt)

        else:
            wallet.lock("BTC", order.quantity)

    def _settle_trade(
        self,
        buy_order: Order,
        sell_order: Order,
        execution_price: Decimal,
        quantity: Decimal
    ):
        buyer_wallet = self.wallet_manager.get_wallet(
        buy_order.user_id
        )

        seller_wallet = self.wallet_manager.get_wallet(
            sell_order.user_id
        )

        actual_cost = execution_price * quantity

        reserved_for_fill = buy_order.price * quantity

        refund = reserved_for_fill - actual_cost
    
        # Buyer:
        # Remove the amount that had been reserved for this portion
        buyer_wallet.consume_locked(
            "USDT",
            reserved_for_fill
        )

        # Return price improvement
        if refund > 0:
            buyer_wallet.deposit(
                "USDT",
                refund
            )

        # Buyer receives BTC
        buyer_wallet.deposit(
            "BTC",
            quantity
        )

        # Seller:
        # BTC was already locked when sell order was created
        seller_wallet.consume_locked(
            "BTC",
            quantity
        )

        # Seller receives actual trade value
        seller_wallet.deposit(
            "USDT",
            actual_cost 
        )