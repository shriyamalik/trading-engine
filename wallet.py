from dataclasses import dataclass
from decimal import Decimal


@dataclass
# for each asset, we will track the available and locked balances
class Balance:
    available: Decimal = Decimal("0")
    locked: Decimal = Decimal("0")

# Operations we can implement on the wallet:
class Wallet:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.balances: dict[str, Balance] = {}

    def validate_balances(self):
        for asset, balance in self.balances.items():
            if balance.available < 0:
                raise RuntimeError(
                    f"{self.user_id} has negative available {asset} balance."
                )

            if balance.locked < 0:
                raise RuntimeError(
                    f"{self.user_id} has negative locked {asset} balance."
                )

    # get balance for asset. Create new balance if it doesn't exist
    def get_balance(self, asset: str) -> Balance:
        if asset not in self.balances:
            self.balances[asset] = Balance()

        return self.balances[asset]

    # deposit funds into the wallet
    def deposit(self, asset: str, amount: Decimal):
        if amount <= 0:
            raise ValueError("Deposit amount must be positive.")

        self.get_balance(asset).available += amount

    # lock funds for an order
    def lock(self, asset: str, amount: Decimal):
        balance = self.get_balance(asset)

        if amount <= 0:
            raise ValueError("Lock amount must be positive.")

        if balance.available < amount:
            raise ValueError(f"Insufficient {asset} balance.")

        balance.available -= amount
        balance.locked += amount

    # unlock funds in case an order is cancelled
    def unlock(self, asset: str, amount: Decimal):
        if amount <= 0:
            raise ValueError("Unlock amount must be positive.")

        balance = self.get_balance(asset)

        if balance.locked < amount:
            raise ValueError(f"Insufficient locked {asset} balance.")

        balance.locked -= amount
        balance.available += amount

    # decrease funds as spent/consumed when an order is filled
    def consume_locked(self, asset: str, amount: Decimal):
        if amount <= 0:
            raise ValueError("Consume amount must be positive.")
    
        balance = self.get_balance(asset)

        if balance.locked < amount:
            raise ValueError(f"Insufficient locked {asset} balance.")

        balance.locked -= amount