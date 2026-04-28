"""
Banker Database Module — Dedicated per-server banker database.
Uses roles/banker/db_banker_core.py (isolated from roles.db).
"""

from typing import List, Dict, Optional, Any
from agent_logging import get_logger
from roles.banker.db_banker_core import get_banker_core_db

logger = get_logger('banker_roles_db')


class BankerRolesDB:
    """Database handler for banker using dedicated per-server banker.db."""

    def __init__(self, server_id: str = None):
        """Initialize database connection using dedicated banker.db."""
        if server_id is None:
            from agent_db import get_server_id
            server_id = get_server_id()
        self.server_id = server_id
        self._core = get_banker_core_db(server_id)
        self.db_path = self._core.db_path
    
    def is_enabled(self) -> bool:
        """Check if banker role is enabled for this server."""
        # Role enabled state lives in server_config (NoSQL), not in banker.db
        from discord_bot.canvas.server_config import is_role_enabled
        return is_role_enabled(self.server_id, "banker", default_enabled=True)

    def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable banker role for this server."""
        from discord_bot.canvas.server_config import set_role_config
        return set_role_config(self.server_id, "banker", enabled)
    
    def create_wallet(self, wallet_id: str, user_name: str, wallet_type: str = 'user') -> bool:
        """Create a new wallet with opening bonus (10x TAE) for user wallets."""
        try:
            # Check if wallet already exists
            existing = self._core.get_wallet(wallet_id)
            if existing:
                # If wallet exists but has 0 balance, apply opening bonus only for dice game pot
                if wallet_id == "dice_game_pot" and existing.get('balance', 0) == 0:
                    tae = self.get_tae(self.server_id)
                    initial_balance = tae * 10
                    if initial_balance > 0:
                        logger.info(f"🎲 Applying retroactive pot initialization of {initial_balance} coins (10x TAE={tae}) to existing dice_game_pot")
                        # Add the opening bonus
                        success = self.add_balance(wallet_id, initial_balance)
                        if success:
                            # Record bonus transaction
                            self._core.save_transaction(
                                "system", wallet_id, initial_balance, "opening_bonus",
                                f"Retroactive pot initialization (10x TAE) for existing dice_game_pot", "system"
                            )
                            return success
                else:
                    logger.info(f"Wallet {wallet_id} already exists with balance {existing.get('balance', 0)}")
                    return True
            
            # Calculate opening bonus (10x TAE) for user wallets and dice game pot
            initial_balance = 0
            if wallet_type == 'user':
                tae = self.get_tae(self.server_id)
                initial_balance = tae * 10
                logger.info(f"💰 Applying opening bonus of {initial_balance} coins (10x TAE={tae}) to new wallet {wallet_id}")
            elif wallet_id == "dice_game_pot":
                tae = self.get_tae(self.server_id)
                initial_balance = tae * 10
                logger.info(f"🎲 Initializing dice game pot with {initial_balance} coins (10x TAE={tae})")
            
            # Create wallet with initial balance
            success = self._core.save_wallet(
                wallet_id, user_name, initial_balance, wallet_type
            )

            if success and initial_balance > 0:
                # Record bonus transaction
                self._core.save_transaction(
                    "system", wallet_id, initial_balance, "opening_bonus",
                    f"Opening bonus (10x TAE) for new {wallet_type} wallet", "system"
                )
            
            return success
        except Exception as e:
            logger.error(f"Failed to create wallet: {e}")
            return False
    
    def get_balance(self, wallet_id: str) -> int:
        """Get wallet balance."""
        try:
            wallet = self._core.get_wallet(wallet_id)
            return wallet['balance'] if wallet else 0
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0
    
    def set_balance(self, wallet_id: str, balance: int) -> bool:
        """Set wallet balance."""
        try:
            return self._core.update_balance(wallet_id, balance)
        except Exception as e:
            logger.error(f"Failed to set balance: {e}")
            return False
    
    def add_balance(self, wallet_id: str, amount: int) -> bool:
        """Add amount to wallet balance."""
        try:
            current_balance = self.get_balance(wallet_id)
            new_balance = current_balance + amount
            return self.set_balance(wallet_id, new_balance)
        except Exception as e:
            logger.error(f"Failed to add balance: {e}")
            return False
    
    def subtract_balance(self, wallet_id: str, amount: int) -> bool:
        """Subtract amount from wallet balance."""
        try:
            current_balance = self.get_balance(wallet_id)
            if current_balance < amount:
                return False
            new_balance = current_balance - amount
            return self.set_balance(wallet_id, new_balance)
        except Exception as e:
            logger.error(f"Failed to subtract balance: {e}")
            return False
    
    def transfer(self, from_wallet: str, to_wallet: str, amount: int, description: str = None, created_by: str = None) -> bool:
        """Transfer amount between wallets."""
        try:
            # Check if from_wallet has sufficient balance
            if not self.subtract_balance(from_wallet, amount):
                return False
            
            # Add to to_wallet
            if not self.add_balance(to_wallet, amount):
                # Rollback if failed
                self.add_balance(from_wallet, amount)
                return False
            
            # Record transaction
            self._core.save_transaction(
                from_wallet, to_wallet, amount, 'transfer',
                description, created_by
            )
            
            return True
        except Exception as e:
            logger.error(f"Failed to transfer: {e}")
            return False
    
    def obtener_todas_wallets(self) -> List[tuple]:
        """Get all wallets (for compatibility with original interface)."""
        try:
            wallets = self._core.get_all_wallets()
            return [
                (w['wallet_id'], w['user_name'], w['wallet_type'])
                for w in wallets
            ]
        except Exception as e:
            logger.error(f"Failed to get all wallets: {e}")
            return []
    
    def get_tae(self, server_id: str) -> int:
        """Get TAE (interest rate) from role config."""
        try:
            from discord_bot.canvas.server_config import get_role_config_value
            tae = get_role_config_value(server_id, "banker", "config.tae", default=1)
            return tae
        except Exception as e:
            logger.error(f"Failed to get TAE: {e}")
            return 1
    
    def set_tae(self, server_id: str, tae: int) -> bool:
        """Set TAE (interest rate) in role config."""
        try:
            from discord_bot.canvas.server_config import set_role_config_value
            return set_role_config_value(server_id, "banker", "config.tae", tae)
        except Exception as e:
            logger.error(f"Failed to set TAE: {e}")
            return False
    
    def get_transaction_history(self, wallet_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get transaction history."""
        try:
            return self._core.get_transactions(wallet_id, limit)
        except Exception as e:
            logger.error(f"Failed to get transaction history: {e}")
            return []
    
    def update_balance(self, wallet_id: str, user_name: str, 
                      amount: int, transaction_type: str, description: str, 
                      category: str = "general", created_by: str = "system") -> bool:
        """Update wallet balance with transaction recording."""
        try:
            # Get current balance
            current_balance = self.get_balance(wallet_id)
            new_balance = current_balance + amount
            
            # Check for insufficient funds
            if new_balance < 0:
                return False
            
            # Update balance
            if self.set_balance(wallet_id, new_balance):
                # Record transaction
                self._core.save_transaction(
                    wallet_id if amount < 0 else "system",
                    wallet_id if amount > 0 else wallet_id,
                    abs(amount), transaction_type, description, created_by
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update balance: {e}")
            return False


# Global database instance
def get_banker_roles_db_instance(server_id: str) -> BankerRolesDB:
    """Get the banker database instance using centralized roles.db.
    
    Args:
        server_id: Server ID (required, no default to prevent roles_agent.db creation)
    """
    if not server_id:
        logger.error("get_banker_roles_db_instance called without server_id, this will create roles_agent.db")
        raise ValueError("server_id is required for get_banker_roles_db_instance")
    return BankerRolesDB(server_id)
