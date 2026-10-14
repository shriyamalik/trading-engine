from decimal import Decimal
from threading import RLock

from models import Order, OrderSide, OrderType, OrderStatus
from exchange_transaction import ExchangeTransaction
from order_service import OrderService

class ExchangeService:

    def __init__(self, engine, quote_service):
        self.engine = engine
        self.quote_service = quote_service
        self.order_service = OrderService(engine, engine.order_manager)

        # Protects the check-then-execute sequence.
        self._lock = RLock()

    def request_quote(self, user_id, side, quantity):
        with self._lock:
            return self.quote_service.get_quote(
                user_id=user_id,
                side=side,
                quantity=quantity,
            )

    def submit_order(self, order):
        with self._lock:
            return self.order_service.submit_order(order)

    def cancel_order_by_id(self, order_id, user_id):
        with self._lock:
            return self.order_service.cancel_order(
                order_id,
                user_id=user_id,
            )

    def replace_order(self, order_id, user_id, **changes):
        with self._lock:

            with ExchangeTransaction(
                self.engine,
                self.quote_service,
            ):
                return self.order_service.replace_order(
                    order_id,
                    user_id,
                    **changes,
                )

    def accept_quote(
        self,
        quote_id,
        user_id,
        slippage_tolerance=Decimal("0.002"),
    ):
        with self._lock:

            if not isinstance(slippage_tolerance, Decimal):
                slippage_tolerance = Decimal(
                    str(slippage_tolerance)
                )

            if (
                not slippage_tolerance.is_finite()
                or slippage_tolerance < 0
                or slippage_tolerance > Decimal("1")
            ):
                raise ValueError("Invalid slippage tolerance.")

            # STEP 1: Retrieve the ORIGINAL quote.
            quote = self.quote_service.get_quote_by_id(
                quote_id
            )

            if quote.user_id != user_id:
                raise ValueError(
                    "Quote belongs to another user."
                )

            if self.quote_service.is_quote_used(quote_id):
                raise ValueError(
                    "Quote already used."
                )
            if self.quote_service.is_quote_invalidated(quote_id):
                raise ValueError(
                    "Quote is no longer valid. Please use the latest quote."
                )
            # STEP 2: Check expiry.
            if quote.is_expired:
                return self._requote(
                    quote,
                    "Quote has expired.",
                )

            # STEP 3: Recalculate using the current book.
            current_quote = self.quote_service.get_quote(
                user_id=user_id,
                side=quote.side,
                quantity=quote.requested_quantity,
            )

            # Protected orders require complete liquidity.
            if (
                not quote.can_fully_fill
                or not current_quote.can_fully_fill
            ):
                return self._requote(
                    quote,
                    "Insufficient liquidity.",
                    current_quote,
                )

            # STEP 4: Check acceptable execution cost.
            if quote.side == OrderSide.BUY:

                maximum_cost = (
                    quote.estimated_total
                    * (
                        Decimal("1")
                        + slippage_tolerance
                    )
                )

                within_tolerance = (
                    current_quote.estimated_total
                    <= maximum_cost
                )

            elif quote.side == OrderSide.SELL:

                minimum_proceeds = (
                    quote.estimated_total
                    * (
                        Decimal("1")
                        - slippage_tolerance
                    )
                )

                within_tolerance = (
                    current_quote.estimated_total
                    >= minimum_proceeds
                )

            else:
                raise ValueError("Invalid order side.")

            if not within_tolerance:
                return self._requote(
                    quote,
                    "Slippage tolerance exceeded.",
                    current_quote,
                )

            # STEP 5: Ensure funds are sufficient before
            # submitting the order.
            wallet = self.engine.wallet_manager.get_wallet(
                user_id
            )

            if quote.side == OrderSide.BUY:
                required_asset = "USDT"
                required_amount = current_quote.estimated_total
            else:
                required_asset = "BTC"
                required_amount = quote.requested_quantity

            if (
                wallet.get_balance(required_asset).available
                < required_amount
            ):
                raise ValueError(
                    f"Insufficient {required_asset} balance."
                )

            # STEP 6: Create actual MARKET order.
            market_order = Order(
                user_id=user_id,
                symbol=quote.symbol,
                side=quote.side,
                order_type=OrderType.MARKET,
                quantity=quote.requested_quantity,
            )

            # Everything in this block must either succeed
            # completely or be rolled back.
            with ExchangeTransaction(
                self.engine,
                self.quote_service,
            ):
                executed_order = self.order_service.submit_order(
                    market_order
                )

                # A protected quote requires the full quantity.
                if executed_order.remaining_quantity() != 0:
                    raise RuntimeError(
                        "Protected order did not fully execute."
                    )

                if executed_order.status != OrderStatus.FILLED:
                    raise RuntimeError(
                        "Protected order has an invalid final status."
                    )

                # Check wallet/order-book consistency.
                self.engine.validate_state()

                # Mark this quote as consumed.
                self.quote_service.mark_quote_used(
                    quote_id
                )

            # Leaving the block successfully commits the changes.
            return {
                "status": "EXECUTED",
                "quote_id": quote_id,
                "order": executed_order,
            }

    def _requote(self, old_quote, reason, new_quote=None):

        if new_quote is None:
            new_quote = self.quote_service.get_quote(
                user_id=old_quote.user_id,
                side=old_quote.side,
                quantity=old_quote.requested_quantity,
            )

        self.quote_service.invalidate_quote(old_quote.id)

        return {
            "status": "REQUOTE_REQUIRED",
            "reason": reason,
            "original_quote_id": old_quote.id,
            "new_quote": new_quote,
        }

    def get_order(self, order_id, user_id):
        with self._lock:
            order = self.order_service.get_order(order_id)

            if order.user_id != user_id:
                raise ValueError("User does not own this order.")

            return order


    def get_user_orders(self, user_id):
        with self._lock:
            return self.order_service.get_user_orders(user_id)