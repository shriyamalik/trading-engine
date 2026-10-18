from decimal import Decimal
from typing import Optional

from models import Order, OrderSide, OrderStatus, OrderType, Trade
from order_book import OrderBook
from wallet_manager import WalletManager
from order_manager import OrderManager
from settlement_service import SettlementService

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
        self.settlement = SettlementService(wallet_manager)
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

    def _match_buy_order(self, incoming_order: Order):
        while incoming_order.remaining_quantity() > 0:

            best_sell = self.order_book.get_best_ask_order()

            if best_sell is None:
                break

            if (incoming_order.order_type == OrderType.LIMIT
                and incoming_order.price < best_sell.price
            ):
                break

            if best_sell.user_id == incoming_order.user_id:
                self.cancel_order(best_sell, validate_after=False)
                continue

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

            if best_buy.user_id == incoming_order.user_id:
                self.cancel_order(best_buy, validate_after=False)
                continue
            
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

    
    def _settle_trade(
        self,
        buy_order: Order,
        sell_order: Order,
        execution_price: Decimal,
        quantity: Decimal
    ):
        return self.settlement.settle_trade(
            buy_order,
            sell_order,
            execution_price,
            quantity
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

        self.settlement.release_order_funds(order)

        self.order_book.remove_order(order)

        order.set_status(OrderStatus.CANCELLED)

        if validate_after:
            self.validate_state()

        return order

    def match_order(self, incoming_order: Order):
        if incoming_order.side == OrderSide.BUY:
            self._match_buy_order(incoming_order)

        elif incoming_order.side == OrderSide.SELL:
            self._match_sell_order(incoming_order)

        else:
            raise ValueError("Invalid order side.")

        return incoming_order