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
    EXPIRED = "EXPIRED"


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


    def validate(self):
        if self.quantity <= 0:
           raise ValueError("Order quantity must be positive.")

        if self.order_type == OrderType.LIMIT:
            if self.price is None or self.price <= 0:
                raise ValueError(
                    "Limit order must have a positive price."
                )

        if self.order_type == OrderType.MARKET:
            if self.price is not None:
                raise ValueError(
                    "Market order should not have a price."
                )

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
