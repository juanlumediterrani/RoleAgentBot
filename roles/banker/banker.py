import os
import sys

# Ensure project root imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from agent_logging import get_logger
from agent_engine import PERSONALITY
from roles.banker.db_role_banker import get_banker_db_instance
from agent_db import get_active_server_name, set_current_server

logger = get_logger('banker')

# Mission configuration
MISSION_CONFIG = {
    "name": "banker",
    "system_prompt_addition": "ACTIVE ROLE - BANKER: You are the Banker of the server, the gold economy manager. Your mission is to manage user wallets, record transactions and distribute daily TAE. You are a serious and responsible financier who keeps accurate records of all economic operations."
}

def get_banker_system_prompt():
    """Get system prompt from personality or fallback to English."""
    try:
        role_prompts = PERSONALITY.get("role_system_prompts", {})
        return role_prompts.get("banker", "ACTIVE MISSION - BANKER: You are the Banker of the server, the gold economy manager. Your mission is to manage user wallets, record transactions and distribute daily TAE. You are a serious and responsible financier who keeps accurate records of all economic operations.")
    except Exception:
        return "ACTIVE MISSION - BANKER: You are the Banker of the server, the gold economy manager. Your mission is to manage user wallets, record transactions and distribute daily TAE. You are a serious and responsible financier who keeps accurate records of all economic operations."

# English fallback role description
BANKER_ROLE_ENGLISH = (
    "You are the Banker of the server, the administrator of the gold economy. Your mission is to manage user wallets, "
    "record all transactions and maintain the economic balance of the server. You are a professional, serious and reliable financier. "
    "You manage the daily distribution of TAE (Annual Equivalent Rate) and keep accurate records of all operations. "
    "You speak with formality and precision, using appropriate financial terms. You use money and finance emojis 💰🏦📊. "
    "Your main objective is to maintain economic stability and ensure that all transactions are recorded correctly."
)


async def create_wallets_for_all_server_members():
    """Create wallets for all server members who don't have one."""
    logger.info("💰 Starting wallet creation for all server members...")
    
    # Get active server from environment or fallback
    server_name = get_active_server_name()
    if not server_name:
        logger.warning("💰 No active server found, skipping wallet creation")
        return
    
    try:
        db_banker = get_banker_db_instance(server_name)
        
        # This function would need Discord bot access to get all server members
        # For now, we'll focus on the existing logic and ensure dice_game accounts
        # The wallet creation for new members happens when they first use !banker balance
        
        logger.info("💰 Wallet creation completed - new members will get wallets on first interaction")
        
    except Exception as e:
        logger.exception(f"💰 Error in wallet creation: {e}")


async def distribute_daily_tae():
    """Distribute daily TAE to all users with wallets."""
    logger.info("💰 Starting daily TAE distribution...")
    
    # Get active server from environment or fallback
    server_name = get_active_server_name()
    if not server_name:
        logger.warning("💰 No active server found, skipping TAE distribution")
        return
    
    try:
        db_banker = get_banker_db_instance(server_name)
        
        # Get current TAE configuration
        tae_amount = db_banker.obtener_tae("server")  # Use server ID as key
        if tae_amount <= 0:
            logger.info("💰 TAE not configured or set to 0, skipping distribution")
            return
        
        # Get all users with wallets
        wallets = db_banker.obtener_todas_wallets()
        if not wallets:
            logger.info("💰 No wallets found, skipping TAE distribution")
            return
        
        distributed_count = 0
        total_distributed = 0
        
        for user_id, user_name, server_id, server_name in wallets:
            try:
                # Skip dice_game_pot for TAE distribution
                if user_id == "dice_game_pot":
                    continue
                    
                # Distribute TAE
                success = db_banker.update_balance(
                    user_id=user_id,
                    user_name=user_name,
                    server_id=server_id,
                    server_name=server_name,
                    amount=tae_amount,
                    type="TAE_DAILY",
                    description="Daily TAE distribution"
                )
                
                if success:
                    distributed_count += 1
                    total_distributed += tae_amount
                    
            except Exception as e:
                logger.error(f"💰 Error distributing TAE to user {user_name}: {e}")
        
        logger.info(f"💰 TAE distribution completed: {distributed_count} users, {total_distributed:,} total coins")
        
    except Exception as e:
        logger.exception(f"💰 Error in TAE distribution: {e}")


async def initialize_dice_game_accounts():
    """Initialize dice game accounts for all existing users."""
    logger.info("💰 Starting dice game account initialization for existing users...")
    
    # Get active server from environment or fallback
    server_name = get_active_server_name()
    if not server_name:
        logger.warning("💰 No active server found, skipping dice game account initialization")
        return
    
    try:
        db_banker = get_banker_db_instance(server_name)
        
        # Get all users with wallets
        wallets = db_banker.obtener_todas_wallets()
        if not wallets:
            logger.info("💰 No wallets found, skipping dice game account initialization")
            return
        
        # Try to get dice game database
        try:
            from roles.trickster.subroles.dice_game.db_dice_game import get_dice_game_db_instance
            db_dice_game = get_dice_game_db_instance(server_name)
            
            if not db_dice_game:
                logger.info("💰 Dice game database not available, skipping account initialization")
                return
        except ImportError:
            logger.info("💰 Dice game module not available, skipping account initialization")
            return
        
        initialized_count = 0
        
        for user_id, user_name, server_id, server_name in wallets:
            try:
                # Skip system accounts like dice_game_pot
                if user_id == "dice_game_pot":
                    continue
                    
                # Check if user already has dice game stats
                stats = db_dice_game.get_player_stats(user_id, server_id)
                
                if stats.get('total_plays', 0) == 0:
                    # User doesn't have dice game account yet
                    # The account will be automatically created on first play
                    logger.info(f"💰 Dice game account ready for existing user: {user_name}")
                    initialized_count += 1
                    
            except Exception as e:
                logger.error(f"💰 Error checking dice game account for {user_name}: {e}")
        
        logger.info(f"💰 Dice game account initialization completed: {initialized_count} users ready")
        
    except Exception as e:
        logger.exception(f"💰 Error in dice game account initialization: {e}")


async def initialize_dice_game_pot():
    """Initialize dice game pot account if it doesn't exist."""
    logger.info("💰 Starting dice game pot initialization...")
    
    # Get active server from environment or fallback
    server_name = get_active_server_name()
    if not server_name:
        logger.warning("💰 No active server found, skipping dice game pot initialization")
        return
    
    try:
        db_banker = get_banker_db_instance(server_name)
        
        # Get all servers to initialize pot for each
        wallets = db_banker.obtener_todas_wallets()
        if not wallets:
            logger.info("💰 No wallets found, cannot determine server for dice game pot")
            return
        
        # Get unique server IDs from wallets
        server_ids = set()
        for user_id, user_name, server_id, server_name in wallets:
            server_ids.add((server_id, server_name))
        
        for server_id, server_name in server_ids:
            try:
                # Check if dice game pot wallet exists
                pot_balance = db_banker.get_balance("dice_game_pot", server_id)
                
                if pot_balance == 0:
                    # Create pot wallet (it will get opening bonus if configured)
                    was_created, initial_balance = db_banker.create_wallet(
                        "dice_game_pot", "Dice Game Pot", server_id, server_name
                    )
                    
                    if was_created:
                        logger.info(f"💰 Dice game pot created for {server_name} with {initial_balance} coins")
                    else:
                        logger.info(f"💰 Dice game pot already exists for {server_name}")
                else:
                    logger.info(f"💰 Dice game pot already exists for {server_name} with {pot_balance} coins")
                    
            except Exception as e:
                logger.error(f"💰 Error initializing dice game pot for {server_name}: {e}")
        
        logger.info("💰 Dice game pot initialization completed")
        
    except Exception as e:
        logger.exception(f"💰 Error in dice game pot initialization: {e}")


async def banker_task():
    """Execute banker role tasks."""
    logger.info("💰 Starting banker role tasks...")
    
    # Initialize dice game pot first
    await initialize_dice_game_pot()
    
    # Initialize dice game accounts for existing users
    await initialize_dice_game_accounts()
    
    # Main banker task: distribute daily TAE
    await distribute_daily_tae()
    
    logger.info("✅ Banker role tasks completed")


async def main():
    logger.info("💰 Banker started...")
    await banker_task()


if __name__ == "__main__":
    asyncio.run(main())
