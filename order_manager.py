from typing import Optional

from models import Order, OrderStatus

class OrderManager:
    def __init__(self):
        self.orders: dict[str, Order] = {}

    def register_order(self, order: Order):
        if order.id in self.orders:
            raise ValueError("Order has already been submitted.")

        self.orders[order.id] = order

    def get_order(self, order_id: str) -> Order:
        if order_id not in self.orders:
            raise ValueError("Order not found.")

        return self.orders[order_id]

    def get_user_orders(self, user_id: Optional[str]) -> list[Order]:
        return [
            order
            for order in self.orders.values()
            if order.user_id == user_id
        ]

    def get_active_orders(
        self,
        user_id: Optional[str] = None
    ) -> list[Order]:

        active_statuses = {
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
        }

        orders = [
            order
            for order in self.orders.values()
            if order.status in active_statuses
        ]

        if user_id is not None:
            orders = [
                order
                for order in orders
                if order.user_id == user_id
            ]

        return orders