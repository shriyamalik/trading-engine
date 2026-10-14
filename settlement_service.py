from decimal import Decimal

from models import Order, OrderSide, OrderType
from order_book import OrderBook
from wallet_manager import WalletManager


class SettlementService:

    def __init__(self, wallet_manager: WalletManager):
        self.wallet_manager = wallet_manager

    # 1. Reserve funds when a new order is submitted.
    def reserve_funds(
        self,
        order: Order,
        order_book: OrderBook
    ):
        wallet = self.wallet_manager.get_wallet(
            order.user_id
        )

        # All SELL orders reserve BTC.
        if order.side == OrderSide.SELL:
            wallet.lock("BTC", order.quantity)
            return

        # LIMIT BUY reserves price * quantity in USDT.
        if order.order_type == OrderType.LIMIT:
            required_usdt = order.price * order.quantity

            wallet.lock("USDT", required_usdt)
            return

        # MARKET BUY reserves estimated execution cost.
        fills = order_book.estimate_execution(
            side=OrderSide.BUY,
            quantity=order.quantity,
            exclude_user_id=order.user_id
        )

        fillable_quantity = sum(
            (qty for price, qty in fills),
            Decimal("0")
        )

        estimated_cost = sum(
            (price * qty for price, qty in fills),
            Decimal("0")
        )

        if fillable_quantity == 0:
            raise ValueError(
                "No sell liquidity available."
            )

        wallet.lock("USDT", estimated_cost)

    # 2. Transfer assets when a trade executes.
    def settle_trade(
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

        if buy_order.order_type == OrderType.LIMIT:
            reserved_for_fill = buy_order.price * quantity
            refund = reserved_for_fill - actual_cost
        else:
            reserved_for_fill = actual_cost
            refund = Decimal("0")

        # Buyer pays USDT from reserved funds.
        buyer_wallet.consume_locked(
            "USDT",
            reserved_for_fill
        )

        # Refund any price improvement.
        if refund > 0:
            buyer_wallet.deposit("USDT", refund)

        # Buyer receives BTC.
        buyer_wallet.deposit("BTC", quantity)

        # Seller delivers BTC.
        seller_wallet.consume_locked("BTC", quantity)

        # Seller receives USDT.
        seller_wallet.deposit("USDT", actual_cost)

    # 3. Release unused funds when an order is cancelled.
    def release_order_funds(self, order: Order):
        wallet = self.wallet_manager.get_wallet(
            order.user_id
        )

        remaining = order.remaining_quantity()

        if remaining <= 0:
            return

        if order.side == OrderSide.BUY:
            wallet.unlock(
                "USDT",
                order.price * remaining
            )
        else:
            wallet.unlock("BTC", remaining)

    # 4. Release any unused market-sell reservation.
    def release_market_remainder(self, order: Order):
        if (
            order.order_type != OrderType.MARKET
            or order.side != OrderSide.SELL
        ):
            return

        remaining = order.remaining_quantity()

        if remaining > 0:
            wallet = self.wallet_manager.get_wallet(
                order.user_id
            )

            wallet.unlock("BTC", remaining)