from decimal import Decimal
from typing import Optional

from models import Order, OrderSide, OrderStatus, OrderType, Trade
from order_book import OrderBook
from wallet_manager import WalletManager
from order_manager import OrderManager

class MatchingEngine:
    def __init__(
        self,
        order_book: OrderBook,
        wallet_manager: WalletManager,
        order_manager: Optional[OrderManager] = None,
    ):
        self.order_book = order_book
        self.wallet_manager = wallet_manager
        self.order_manager = order_manager or OrderManager()
        self.trades: list[Trade] = []

    def validate_state(self):
        expected_locks: dict[str, dict[str, Decimal]] = {}

        # ---------------------------------
        # CALCULATE EXPECTED LOCKED FUNDS
        # ---------------------------------

        for order in self.order_book.get_active_orders():

            if order.order_type != OrderType.LIMIT:
                raise RuntimeError(
                    "Market order found resting in order book."
                )

            if order.status not in {
                OrderStatus.OPEN,
                OrderStatus.PARTIALLY_FILLED,
            }:
                raise RuntimeError(
                    f"Inactive order {order.id} found in order book."
                )

            if order.remaining_quantity() <= 0:
                raise RuntimeError(
                    f"Order {order.id} has no remaining quantity."
                )

            if order.user_id not in expected_locks:
                expected_locks[order.user_id] = {
                    "BTC": Decimal("0"),
                    "USDT": Decimal("0"),
                }

            if order.side == OrderSide.BUY:
                expected_locks[order.user_id]["USDT"] += (
                    order.price * order.remaining_quantity()
                )

            else:
                expected_locks[order.user_id]["BTC"] += (
                    order.remaining_quantity()
                )

        # ---------------------------------
        # CHECK ACTUAL WALLET BALANCES
        # ---------------------------------

        for user_id, wallet in self.wallet_manager.wallets.items():

            wallet.validate_balances()

            expected = expected_locks.get(
                user_id,
                {
                    "BTC": Decimal("0"),
                    "USDT": Decimal("0"),
                }
            )

            btc_locked = (
                wallet.balances.get("BTC").locked
                if "BTC" in wallet.balances
                else Decimal("0")
            )

            usdt_locked = (
                wallet.balances.get("USDT").locked
                if "USDT" in wallet.balances
                else Decimal("0")
            )

            if btc_locked != expected["BTC"]:
                raise RuntimeError(
                    f"BTC lock mismatch for {user_id}: "
                    f"expected {expected['BTC']}, "
                    f"actual {btc_locked}"
                )

            if usdt_locked != expected["USDT"]:
                raise RuntimeError(
                    f"USDT lock mismatch for {user_id}: "
                    f"expected {expected['USDT']}, "
                    f"actual {usdt_locked}"
                )

        return True

    def submit_order(self, incoming_order: Order):

        self.order_manager.register_order(incoming_order)

        try:
            incoming_order.validate()

            if incoming_order.symbol != self.order_book.symbol:
                raise ValueError("Order symbol does not match this order book.")

            self._reserve_funds(incoming_order)
            
        except (ValueError, TypeError):
            incoming_order.set_status(OrderStatus.REJECTED)
            raise

        if incoming_order.side == OrderSide.BUY:
            self._match_buy_order(incoming_order)

        else:
            self._match_sell_order(incoming_order)

        # LIMIT orders that are not fully filled should be added to the order book
        if (
            incoming_order.remaining_quantity() > 0
            and incoming_order.order_type == OrderType.LIMIT
        ):
            self.order_book.add_order(incoming_order)

        # MARKET orders remainders should be marked as EXPIRED
        if (incoming_order.order_type == OrderType.MARKET and incoming_order.remaining_quantity() > 0):
            wallet = self.wallet_manager.get_wallet(incoming_order.user_id)

            remaining = incoming_order.remaining_quantity()

            if incoming_order.side == OrderSide.SELL:
                wallet.unlock(
                    "BTC",
                    remaining
                )

            incoming_order.set_status(OrderStatus.EXPIRED)

        self.validate_state()

        return incoming_order

    def _match_buy_order(self, incoming_order: Order):
        while incoming_order.remaining_quantity() > 0:

            best_sell = self.order_book.get_best_ask_order()

            if best_sell is None:
                break

            if best_sell.user_id == incoming_order.user_id:
                self.cancel_order(best_sell, validate_after=False)
                continue

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

            if best_buy.user_id == incoming_order.user_id:
                self.cancel_order(best_buy, validate_after=False)
                continue

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
            order.set_status(OrderStatus.FILLED)

        elif order.filled_quantity > 0:
            order.set_status(OrderStatus.PARTIALLY_FILLED)

        else:
            order.set_status(OrderStatus.OPEN)

    def _reserve_funds(self, order: Order):
        wallet = self.wallet_manager.get_wallet(
            order.user_id
        )

        if order.side == OrderSide.SELL:
            wallet.lock(
                "BTC",
                order.quantity
            )
            return

        # BUY LIMIT
        if order.order_type == OrderType.LIMIT:
            required_usdt = (
                order.price * order.quantity
            )

            wallet.lock(
                "USDT",
                required_usdt
            )

            return

        # BUY MARKET
        estimated_cost, fillable_quantity = (
            self.order_book.estimate_market_buy_cost(
                order.quantity
            )
        )
    
        if fillable_quantity == 0:
            raise ValueError(
                "No sell liquidity available."
            )

        wallet.lock(
            "USDT",
            estimated_cost
        )
    
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

        if buy_order.order_type == OrderType.LIMIT:
            reserved_for_fill = (
                buy_order.price * quantity
        )

            refund = reserved_for_fill - actual_cost

        else:
            # Market BUY was reserved using
            # actual order-book prices
            reserved_for_fill = actual_cost
            refund = Decimal("0")
    
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

    def cancel_order(self, order: Order, validate_after: bool = True):

        terminal_states = {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
            OrderStatus.REJECTED,
        }

        if order.status in terminal_states:
            raise ValueError(
                f"{order.status.value} orders cannot be cancelled."
            )

        if not self.order_book.contains_order(order):
            raise ValueError(
                "Order is not currently active in the order book."
            )

        wallet = self.wallet_manager.get_wallet(order.user_id)

        remaining = order.remaining_quantity()

        if order.side == OrderSide.BUY:
            amount_to_unlock = order.price * remaining
            wallet.unlock("USDT", amount_to_unlock)
        else:
            wallet.unlock("BTC", remaining)

        self.order_book.remove_order(order)

        order.set_status(OrderStatus.CANCELLED)

        if validate_after:
            self.validate_state()

        return order

    def cancel_order_by_id(
        self,
        order_id: str,
        user_id: Optional[str] = None
    ):
        order = self.order_manager.get_order(
            order_id
        )

        if (
            user_id is not None
            and order.user_id != user_id
        ):
            raise ValueError(
                "User does not own this order."
            )

        return self.cancel_order(order)

    def replace_order(
        self,
        order_id: str,
        new_price: Optional[Decimal] = None,
        new_quantity: Optional[Decimal] = None,
        user_id: Optional[str] = None,
    ):
        old_order = self.order_manager.get_order(
            order_id
        )

        if (
            user_id is not None
            and old_order.user_id != user_id
        ):
            raise ValueError(
                "User does not own this order."
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

        # Cancel first:
        # removes from book and unlocks remaining funds
        self.cancel_order(old_order)

        replacement_order = Order(
            user_id=old_order.user_id,
            symbol=old_order.symbol,
            side=old_order.side,
            order_type=OrderType.LIMIT,
            price=replacement_price,
            quantity=replacement_quantity,
        )

        self.submit_order(
            replacement_order
        )

        return replacement_order
