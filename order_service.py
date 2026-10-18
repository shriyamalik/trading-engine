from decimal import Decimal
from typing import Optional

from models import Order, OrderSide, OrderStatus, OrderType
from matching_engine import MatchingEngine
from order_manager import OrderManager

class OrderRejected(ValueError):
    """Expected rejection before matching begins."""
    pass

class OrderService:

    def __init__(
        self,
        matching_engine: MatchingEngine,
        order_manager: OrderManager
    ):
        self.engine = matching_engine
        self.order_manager = order_manager

    def submit_order(self, order: Order) -> Order:
        # 1. Register the order so its history is retained.
        self.order_manager.register_order(order)

        # 2. Validate the order and reserve funds.
        try:
            order.validate()

            if order.symbol != self.engine.order_book.symbol:
                raise ValueError(
                    "Order symbol does not match this order book."
                )

            self.engine.settlement.reserve_funds(
                order,
                self.engine.order_book
            )

        except (ValueError, TypeError) as exc:
            order.set_status(OrderStatus.REJECTED)
            raise OrderRejected(str(exc)) from exc

        # 3. Hand over to the matching engine.
        self.engine.match_order(order)

        # 4. Handle the unfilled remainder.
        if order.remaining_quantity() > 0:

            if order.order_type == OrderType.LIMIT:
                self.engine.order_book.add_order(order)

            elif order.order_type == OrderType.MARKET:
                self.engine.settlement.release_market_remainder(
                    order
                )
                order.set_status(OrderStatus.EXPIRED)

        # 5. Validate the final stable exchange state.
        self.engine.validate_state()

        return order

    def get_order(self, order_id: str) -> Order:
        return self.order_manager.get_order(order_id)

    def get_user_orders(self, user_id: str):
        return self.order_manager.get_user_orders(user_id)

    def get_active_orders(self, user_id: str):
        return self.order_manager.get_active_orders(user_id)

    def _get_owned_order(
        self,
        order_id: str,
        user_id: str
    ) -> Order:

        order = self.order_manager.get_order(order_id)

        if order.user_id != user_id:
            raise ValueError(
                "User does not own this order."
            )

        return order

    def cancel_order(
        self,
        order_id: str,
        user_id: str
    ) -> Order:

        order = self._get_owned_order(
            order_id,
            user_id
        )

        return self.engine.cancel_order(order)

    def replace_order(
        self,
        order_id: str,
        user_id: str,
        new_price: Optional[Decimal] = None,
        new_quantity: Optional[Decimal] = None,
    ) -> Order:

        old_order = self._get_owned_order(
            order_id,
            user_id
        )

        if old_order.order_type != OrderType.LIMIT:
            raise ValueError(
                "Only limit orders can be replaced."
            )

        if old_order.status not in {
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
        }:
            raise ValueError(
                "Only active orders can be replaced."
            )

        # The new quantity refers to the replacement's
        # total quantity, not the original order's total.
        replacement_quantity = (
            new_quantity
            if new_quantity is not None
            else old_order.remaining_quantity()
        )

        replacement_price = (
            new_price
            if new_price is not None
            else old_order.price
        )

        # Create and validate BEFORE cancelling the old order.
        replacement = Order(
            user_id=old_order.user_id,
            symbol=old_order.symbol,
            side=old_order.side,
            order_type=OrderType.LIMIT,
            price=replacement_price,
            quantity=replacement_quantity,
        )

        replacement.validate()

        # Cancel the old order, releasing its remaining funds.
        self.engine.cancel_order(old_order)

        # Submit the replacement normally.
        # This gives it a new ID and queue position.
        self.submit_order(replacement)

        return replacement