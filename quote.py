from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Tuple
from uuid import uuid4

from models import OrderSide


@dataclass
class Quote:
    user_id: str
    symbol: str
    side: OrderSide

    requested_quantity: Decimal
    fillable_quantity: Decimal

    estimated_total: Decimal
    average_price: Optional[Decimal]
    worst_price: Optional[Decimal]

    fills: List[Tuple[Decimal, Decimal]]

    id: str = field(
        default_factory=lambda: str(uuid4())
    )

    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    expires_at: datetime = field(
        default_factory=lambda: (
            datetime.now(timezone.utc)
            + timedelta(seconds=5)
        )
    )

    @property
    def remaining_quantity(self):
        return (
            self.requested_quantity
            - self.fillable_quantity
        )

    @property
    def can_fully_fill(self):
        return self.remaining_quantity == 0

    @property
    def is_expired(self):
        return (
            datetime.now(timezone.utc)
            >= self.expires_at
        )