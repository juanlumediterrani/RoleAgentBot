import os
import sys

# Ensure project root imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from agent_logging import get_logger
from agent_engine import PERSONALITY
from roles.banker.banker_db import get_banker_roles_db_instance
from agent_db import get_server_id

logger = get_logger('banker')

# Mission configuration
def get_banker_system_prompt():
    """Get system prompt from personality or fallback to English."""
    try:
        role_prompts = PERSONALITY.get("roles", {})
        return role_prompts.get("banker", {}).get("active_duty", "ACTIVE MISSION - BANKER: You are the Banker of the server, the gold economy manager. Your mission is to manage user wallets, record transactions and distribute daily TAE. You are a serious and responsible financier who keeps accurate records of all economic operations.")
    except Exception:
        return ""

async def create_wallets_for_all_server_members(server_id: str | None = None):
    """Create wallets for all server members who don't have one.
    
    Args:
        server_id: Server ID to use, or None to auto-detect
    """
    logger.info("💰 Starting wallet creation for all server members...")
    
    # Use provided server_id or fallback to auto-detection
    server_key = server_id or get_server_id()
    if not server_key:
        logger.warning("💰 No active server found, skipping wallet creation")
        return
    
    try:
        db_banker = get_banker_roles_db_instance(server_key)
        
        # Wait a moment for Discord bot to be fully connected
        import asyncio
        await asyncio.sleep(2)
        
        # Try to get Discord bot instance to access server members
        try:
            from discord_bot.agent_discord import get_bot_instance
            bot = get_bot_instance()
            
            if bot and bot.guilds:
                # Process all guilds the bot is in
                for guild in bot.guilds:
                    guild_id = str(guild.id)
                    guild_name = guild.name
                    
                    logger.info(f"💰 Processing guild: {guild_name} ({guild_id})")
                    
                    created_count = 0
                    existing_count = 0
                    
                    # Create wallets for all members in this guild
                    for member in guild.members:
                        if member.bot:
                            continue  # Skip bot accounts
                        
                        member_id = str(member.id)
                        member_name = member.display_name
                        
                        # Create wallet with opening bonus (10x TAE)
                        was_created = db_banker.create_wallet(
                            member_id, member_name, guild_id, wallet_type='user'
                        )
                        
                        if was_created:
                            created_count += 1
                            initial_balance = db_banker.get_balance(member_id, guild_id)
                            logger.info(f"💰 Created wallet for {member_name} with {initial_balance} coins")
                        else:
                            existing_count += 1
                    
                    logger.info(f"💰 Guild {guild_name}: {created_count} new wallets, {existing_count} existing wallets")
            else:
                logger.warning("💰 Bot instance not available or no guilds found - initializing system accounts")
                
                # Fallback: Create system accounts and ensure TAE is configured
                try:
                    # Ensure TAE is configured
                    current_tae = db_banker.get_tae(server_key)
                    if current_tae == 0:
                        # Set default TAE if not configured
                        db_banker.set_tae(server_key, 10)  # Default 10 coins per day
                        logger.info("💰 Set default TAE to 10 coins per day")
                    
                    # Create system accounts
                    was_created_pot = db_banker.create_wallet(
                        "dice_game_pot", "Dice Game Pot", wallet_type='system'
                    )
                    
                    was_created_beggar = db_banker.create_wallet(
                        "beggar_fund", "Beggar Fund", wallet_type='system'
                    )
                    
                    if was_created_pot:
                        logger.info(f"💰 Created dice game pot")
                    if was_created_beggar:
                        logger.info(f"💰 Created beggar fund")
                    
                    logger.info(f"💰 System accounts initialized. TAE set to {db_banker.get_tae(server_key)} coins")
                    
                except Exception as fallback_error:
                    logger.warning(f"💰 System account initialization failed: {fallback_error}")
                
        except ImportError:
            logger.warning("💰 Could not import bot instance, wallet creation requires Discord bot access")
        
        logger.info("💰 Wallet creation completed")
        
    except Exception as e:
        logger.exception(f"💰 Error in wallet creation: {e}")

async def distribute_daily_tae(server_id: str | None = None):
    """Distribute daily TAE to all users with wallets (once per day).
    
    Args:
        server_id: Server ID to use, or None to auto-detect
    """
    logger.info("💰 Starting daily TAE distribution...")
    
    # Use provided server_id or fallback to auto-detection
    server_key = server_id or get_server_id()
    if not server_key:
        logger.warning("💰 No active server found, skipping TAE distribution")
        return
    
    try:
        db_banker = get_banker_roles_db_instance(server_key)
        
        # Check if TAE was already distributed today
        from datetime import date
        today = date.today().isoformat()
        
        # Check last distribution timestamp (store in role config)
        config = db_banker.roles_db.get_role_config("banker", server_key)
        config_data = config.get('config_data', '{}')
        if config_data:
            import json
            data = json.loads(config_data)
        else:
            data = {}
        
        last_distribution = data.get('last_tae_distribution', '')
        if last_distribution == today:
            logger.info(f"💰 TAE already distributed today ({today}), skipping")
            return
        
        # Get current TAE configuration
        tae_amount = db_banker.get_tae(server_key)
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
        
        for wallet_id, user_name, wallet_type in wallets:
            try:
                # Skip dice_game_pot for TAE distribution
                if wallet_id == "dice_game_pot":
                    continue
                    
                # Distribute TAE
                success = db_banker.add_balance(
                    wallet_id=wallet_id,
                    amount=tae_amount
                )
                
                if success:
                    # Record transaction
                    db_banker.roles_db.save_banker_transaction(
                        "system", wallet_id, tae_amount, "TAE_DAILY", 
                        f"Daily TAE distribution for {today}", "system"
                    )
                    distributed_count += 1
                    total_distributed += tae_amount
                    
            except Exception as e:
                logger.error(f"💰 Error distributing TAE to user {user_name}: {e}")
        
        # Update last distribution timestamp
        data['last_tae_distribution'] = today
        db_banker.roles_db.save_role_config(
            "banker", True, json.dumps(data)
        )
        
        logger.info(f"💰 TAE distribution completed: {distributed_count} users, {total_distributed:,} total coins")
        
    except Exception as e:
        logger.exception(f"💰 Error in TAE distribution: {e}")

async def initialize_dice_game_accounts(server_id: str | None = None):
    """Initialize dice game accounts for all existing users.
    
    Args:
        server_id: Server ID to use, or None to auto-detect
    """
    logger.info("💰 Starting dice game account initialization for existing users...")
    
    # Use provided server_id or fallback to auto-detection
    server_key = server_id or get_server_id()
    if not server_key:
        logger.warning("💰 No active server found, skipping dice game account initialization")
        return
    
    try:
        db_banker = get_banker_roles_db_instance(server_key)
        
        # Get all users with wallets
        wallets = db_banker.obtener_todas_wallets()
        if not wallets:
            logger.info("💰 No wallets found, skipping dice game account initialization")
            return
        
        # Try to get dice game database
        try:
            from agent_roles_db import get_roles_db_instance
            roles_db = get_roles_db_instance(server_key)
            
            if not roles_db:
                logger.info("💰 Dice game database not available, skipping account initialization")
                return
        except ImportError:
            logger.info("💰 Dice game module not available, skipping account initialization")
            return
        
        initialized_count = 0
        
        for wallet_id, user_name, wallet_type in wallets:
            try:
                # Skip system accounts like dice_game_pot
                if wallet_id == "dice_game_pot":
                    continue
                    
                # Check if user already has dice game stats
                stats = roles_db.get_dice_game_stats(wallet_id)
                
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

async def initialize_dice_game_pot(server_id: str | None = None):
    """Initialize dice game pot account if it doesn't exist.
    
    Args:
        server_id: Server ID to use, or None to auto-detect
    """
    logger.info("💰 Starting dice game pot initialization...")
    
    # Use provided server_id or fallback to auto-detection
    server_key = server_id or get_server_id()
    if not server_key:
        logger.warning("💰 No active server found, skipping dice game pot initialization")
        return
    
    try:
        db_banker = get_banker_roles_db_instance(server_key)
        
        # Get all servers to initialize pot for each
        wallets = db_banker.obtener_todas_wallets()
        if not wallets:
            logger.info("💰 No wallets found, cannot determine server for dice game pot")
            return
        
        # Get unique server IDs from wallets
        server_ids = set()
        for wallet_id, user_name, wallet_type in wallets:
            # For dice game pot, we need to handle it differently since it's a system wallet
            # We'll use the active server for system wallets
            if wallet_type == 'system':
                server_ids.add((server_key, f"Server_{server_key}"))
        
        for server_id, server_name in server_ids:
            try:
                # Check if dice game pot wallet exists
                pot_balance = db_banker.get_balance("dice_game_pot")
                
                if pot_balance == 0:
                    # Create pot wallet (it will get opening bonus if configured)
                    was_created = db_banker.create_wallet(
                        "dice_game_pot", "Dice Game Pot"
                    )
                    
                    if was_created:
                        initial_balance = db_banker.get_balance("dice_game_pot")
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

async def banker_task_for_server(server_id: str):
    """Execute banker role tasks for a specific server.
    
    Args:
        server_id: Server ID to execute tasks for
    """
    logger.info(f"💰 Starting banker role tasks for server {server_id}...")
    
    try:
        # Create wallets for all server members first
        await create_wallets_for_all_server_members(server_id)
        
        # Initialize dice game pot first
        await initialize_dice_game_pot(server_id)
        
        # Initialize dice game accounts for existing users
        await initialize_dice_game_accounts(server_id)
        
        # Main banker task: distribute daily TAE
        await distribute_daily_tae(server_id)
        
        logger.info(f"✅ Banker role tasks completed for server {server_id}")
    except Exception as e:
        logger.error(f"❌ Error in banker tasks for server {server_id}: {e}")

async def banker_task():
    """Execute banker role tasks for all servers."""
    logger.info("💰 Starting banker role tasks for all servers...")
    
    # Get all server directories
    from pathlib import Path
    db_dir = Path(__file__).parent.parent.parent / "databases"
    
    if not db_dir.exists():
        logger.warning("💰 No databases directory found")
        return
    
    server_dirs = [d for d in db_dir.iterdir() if d.is_dir() and d.name.isdigit()]
    
    if not server_dirs:
        logger.warning("💰 No server databases found")
        return
    
    logger.info(f"💰 Found {len(server_dirs)} server directories")
    
    # Run tasks for each server (skip server 0 as it's for initialization only)
    for server_dir in server_dirs:
        server_id = server_dir.name
        if server_id == "0":
            continue
            
        try:
            await banker_task_for_server(server_id)
        except Exception as e:
            logger.error(f"💰 Failed to run banker tasks for server {server_id}: {e}")
            continue
    
    logger.info("💰 Banker role tasks completed for all servers")

async def main():
    logger.info("💰 Banker started...")
    await banker_task()

if __name__ == "__main__":
    asyncio.run(main())
