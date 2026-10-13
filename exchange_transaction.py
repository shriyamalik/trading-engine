from collections import defaultdict, deque
from copy import deepcopy


class ExchangeTransaction:
    """
    Snapshot and rollback support for the in-memory exchange.

    Intended to run while ExchangeService holds its lock.
    """

    def __init__(self, engine, quote_service):
        self.engine = engine
        self.quote_service = quote_service

    def __enter__(self):
        engine = self.engine
        book = engine.order_book
        wallets = engine.wallet_manager

        # 1. Snapshot wallet registry and balances.
        # Keep existing Wallet objects intact.
        self.wallet_registry = dict(wallets.wallets)

        self.wallet_balances = {
            user_id: deepcopy(wallet.balances)
            for user_id, wallet in wallets.wallets.items()
        }

        # 2. Snapshot the actual book queues, retaining
        # original Order object references.
        self.bids = {
            price: list(queue)
            for price, queue in book.bids.items()
        }

        self.asks = {
            price: list(queue)
            for price, queue in book.asks.items()
        }

        # 3. Snapshot order registry.
        manager = engine.order_manager

        self.registered_orders = dict(manager.orders)

        # Include book orders in case they are not registered.
        all_orders = {}

        for order in self.registered_orders.values():
            all_orders[id(order)] = order

        for queues in (self.bids, self.asks):
            for orders in queues.values():
                for order in orders:
                    all_orders[id(order)] = order

        # Save mutable order state without replacing objects.
        self.order_snapshots = [
            (order, deepcopy(vars(order)))
            for order in all_orders.values()
        ]

        # 4. Snapshot trade history.
        self.trades = list(engine.trades)

        # 5. Snapshot optional legacy duplicate tracking.
        self.submitted_ids = None

        if hasattr(engine, "submitted_order_ids"):
            self.submitted_ids = set(
                engine.submitted_order_ids
            )

        # 6. Snapshot consumed quote IDs.
        self.used_quote_ids = set(
            self.quote_service.used_quote_ids
        )

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            return False

        self.rollback()
        return False

    def rollback(self):
        engine = self.engine
        book = engine.order_book
        wallets = engine.wallet_manager

        # Restore wallet registry.
        # Wallets created during the failed transaction disappear.
        wallets.wallets.clear()
        wallets.wallets.update(self.wallet_registry)

        # Restore existing wallets' balances.
        for user_id, original_balances in (
            self.wallet_balances.items()
        ):
            wallet = self.wallet_registry[user_id]

            # Preserve existing Balance objects where possible.
            for asset in list(wallet.balances):
                if asset not in original_balances:
                    del wallet.balances[asset]

            for asset, saved in original_balances.items():
                if asset in wallet.balances:
                    balance = wallet.balances[asset]
                    balance.available = saved.available
                    balance.locked = saved.locked
                else:
                    wallet.balances[asset] = deepcopy(saved)

        # Restore the fields of every pre-existing order.
        for order, snapshot in self.order_snapshots:
            vars(order).clear()
            vars(order).update(deepcopy(snapshot))

        # Restore book queues in original price/FIFO order.
        book.bids.clear()
        book.bids.update({
            price: deque(orders)
            for price, orders in self.bids.items()
        })

        book.asks.clear()
        book.asks.update({
            price: deque(orders)
            for price, orders in self.asks.items()
        })

        # Restore order registry.
        engine.order_manager.orders.clear()
        engine.order_manager.orders.update(
            self.registered_orders
        )

        # Remove trades created by failed execution.
        engine.trades[:] = self.trades

        if self.submitted_ids is not None:
            engine.submitted_order_ids.clear()
            engine.submitted_order_ids.update(
                self.submitted_ids
            )

        self.quote_service.used_quote_ids.clear()
        self.quote_service.used_quote_ids.update(
            self.used_quote_ids
        )