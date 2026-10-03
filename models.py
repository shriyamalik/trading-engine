# defines the structure of an order and all its attributes. It has validations methods and updations metrics

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4
from typing import Optional


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(str, Enum):
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Order:
    user_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None

    id: str = field(default_factory=lambda: str(uuid4()))
    filled_quantity: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.OPEN
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def validation(self) -> str:
        if self.order_type == OrderType.LIMIT and self.price is None:
            return "Limit order must have a price."
        if self.order_type == OrderType.MARKET and self.price is not None:
            return "Market order should not have a price."
        if self.quantity <= 0:
            return "Order quantity must be positive."
        return "Order is valid."

    def remaining_quantity(self) -> Decimal:
        return self.quantity - self.filled_quantity

@dataclass
class Trade:
    buy_order_id: str
    sell_order_id: str
    symbol: str
    price: Decimal
    quantity: Decimal

    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
