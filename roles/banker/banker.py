import os
import sys

# Ensure project root imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from agent_logging import get_logger
from agent_engine import PERSONALIDAD
from db_role_banker import get_banker_db_instance
from agent_db import get_active_server_name, set_current_server

logger = get_logger('banker')

# Mission configuration
MISSION_CONFIG = {
    "name": "banker"
}

def get_banker_system_prompt():
    """Get system prompt from personality or fallback to English."""
    try:
        role_prompts = PERSONALIDAD.get("role_system_prompts", {})
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
        wallets = db_banker.obtener_todas_carteras()
        if not wallets:
            logger.info("💰 No wallets found, skipping TAE distribution")
            return
        
        distributed_count = 0
        total_distributed = 0
        
        for user_id, user_name, server_id, server_name in wallets:
            try:
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


async def banker_task():
    """Execute banker role tasks."""
    logger.info("💰 Starting banker role tasks...")
    
    # Main banker task: distribute daily TAE
    await distribute_daily_tae()
    
    logger.info("✅ Banker role tasks completed")


async def main():
    logger.info("💰 Banker started...")
    await banker_task()


if __name__ == "__main__":
    asyncio.run(main())
