from wallet import Wallet


class WalletManager:
    def __init__(self):
        self.wallets: dict[str, Wallet] = {}

    def get_wallet(self, user_id: str) -> Wallet:
        if user_id not in self.wallets:
            self.wallets[user_id] = Wallet(user_id)

        return self.wallets[user_id]