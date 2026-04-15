"""
Discord commands for the Banker role (English version).
Registers: !banker (balance, tae, bonus, help)
"""

import discord
import json
import os
from agent_logging import get_logger
from .banker_messages import get_messages
from discord_bot.discord_utils import is_admin, send_embed_dm_or_channel

logger = get_logger('banker_discord')

# Availability flags
try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None


def _get_server_db_path(guild) -> str:
    """Get the server-specific database path for banker messages."""
    try:
        from agent_engine import _get_personality
        server_id = str(guild.id)
        personality = _get_personality(server_id)
        personality_name = personality.get("name", "putre")
        return os.path.join("databases", server_id, personality_name)
    except Exception:
        return os.path.join("databases", str(guild.id), "putre")


def _get_banker_db(guild):
    """Get banker database instance for a server."""
    try:
        id_key = str(guild.id)
        return get_roles_db_instance(id_key)
    except Exception:
        return get_roles_db_instance(str(guild.id))


def _get_dice_game_db(guild):
    """Get dice game database instance for a server."""
    try:
        from agent_roles_db import get_roles_db_instance
        id_key = str(guild.id)
        return get_roles_db_instance(id_key)
    except ImportError:
        return None


def _initialize_dice_game_account(user_id: str, user_name: str, server_id: str, server_key: str):
    try:
        from agent_roles_db import get_roles_db_instance

        roles_db = get_roles_db_instance(server_key)
        if roles_db:
            ok = roles_db.save_dice_game_stats(user_id, 0, 0, 0, 0, 0, None)
            if ok:
                logger.info(f"🎲 Dice game account initialized for {user_name}")
            return bool(ok)
    except Exception as e:
        logger.warning(f"Could not initialize dice game account for {user_name}: {e}")
    return False




# --- HELPER FUNCTIONS (for Canvas UI) ---

async def _cmd_banker_balance(ctx, db_banker, server_id):
    """Show user's gold balance."""
    user_id = str(ctx.author.id)
    user_name = ctx.author.display_name
    server_key = str(ctx.guild.id)
    server_db_path = _get_server_db_path(ctx.guild)

    try:
        for member in getattr(ctx.guild, "members", []) or []:
            if getattr(member, "bot", False):
                continue
            member_id = str(member.id)
            member_name = member.display_name
            db_banker.create_wallet(member_id, member_name)

        db_dice_game = _get_dice_game_db(ctx.guild)
        if db_dice_game is not None:
            db_banker.create_wallet("dice_game_pot", "Dice Game Pot", wallet_type='system')
            for member in getattr(ctx.guild, "members", []) or []:
                if getattr(member, "bot", False):
                    continue
                _initialize_dice_game_account(str(member.id), member.display_name, server_id, server_key)
    except Exception as e:
        logger.warning(f"Bulk initialization failed: {e}")

    # Create wallet if it doesn't exist (with opening bonus)
    was_created = db_banker.create_wallet(user_id, user_name)

    # Initialize dice game account for new and existing users
    dice_game_initialized = _initialize_dice_game_account(user_id, user_name, server_id, server_key)

    balance = db_banker.get_balance(user_id)
    history = db_banker.get_transaction_history(user_id, limit=5)

    embed = discord.Embed(
        title=_get_banker_description_text("balance_title", get_messages(server_db_path, "balance_title")),
        description=get_messages(server_db_path, "balance_description"),
        color=discord.Color.gold()
    )
    embed.add_field(name=_get_banker_description_text("current_balance", get_messages(server_db_path, "current_balance")), value=f"{balance:,} gold coins", inline=False)
    embed.add_field(name=_get_banker_description_text("account_holder", get_messages(server_db_path, "account_holder")), value=user_name, inline=True)
    embed.add_field(name=_get_banker_description_text("bank", get_messages(server_db_path, "bank")), value=server_id, inline=True)

    # Add dice game status information
    if dice_game_initialized:
        embed.add_field(name="🎲 Dice Game", value="Account ready for play!", inline=False)

    if history:
        history_text = ""
        for trans in history:
            trans_type, amount, balance_before, balance_after, description, date, admin = trans
            emoji = "📥" if amount > 0 else "📤"
            history_text += f"{emoji} {amount:,} ({trans_type})\n"
        if history_text:
            embed.add_field(name=_get_banker_description_text("recent_transactions", get_messages(server_db_path, "recent_transactions")), value=history_text[:1024], inline=False)

    embed.set_footer(text=get_messages(server_db_path, "help_footer"))
    embed.set_thumbnail(url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)

    confirm = get_messages(server_db_path, "balance_sent")
    await send_embed_dm_or_channel(ctx, embed, confirm)


async def _cmd_banker_tae(ctx, db_banker, server_id, subargs):
    """Configure or view TAE (admins only)."""
    server_db_path = _get_server_db_path(ctx.guild)
    if not is_admin(ctx):
        await ctx.send(get_messages(server_db_path, "error_admin_daily_gold"))
        return

    if not subargs:
        # Show current TAE
        current_tae = db_banker.get_tae(server_id)

        embed = discord.Embed(
            title=_get_banker_description_text("daily_allowance_config_title", get_messages(server_db_path, "daily_allowance_config_title")),
            description=get_messages(server_db_path, "daily_allowance_description"),
            color=discord.Color.blue()
        )
        embed.add_field(name=get_messages(server_db_path, "current_daily_gold"), value=f"{current_tae:,} coins", inline=True)
        embed.add_field(name=_get_banker_description_text("opening_bonus", "Opening Bonus"), value=f"{current_tae * 10:,} coins (10x TAE)", inline=True)

        if current_tae == 0:
            embed.add_field(name=get_messages(server_db_path, "daily_gold_not_configured"), value="Use !banker tae <amount> to configure", inline=False)
        else:
            embed.add_field(name=get_messages(server_db_path, "daily_gold_info"), value=f"Each user will receive {current_tae:,} coins daily", inline=False)

        embed.set_footer(text=get_messages(server_db_path, "daily_gold_footer"))
        await ctx.send(embed=embed)
    else:
        # Set new TAE
        try:
            amount = int(subargs[0])
            if amount < 0 or amount > 1000:
                await ctx.send(get_messages(server_db_path, "error_daily_gold_range"))
                return

            admin_id = str(ctx.author.id)
            if db_banker.set_tae(server_id, amount):
                embed = discord.Embed(
                    title=get_messages(server_db_path, "daily_gold_configured"),
                    description=get_messages(server_db_path, "daily_gold_updated"),
                    color=discord.Color.green()
                )
                embed.add_field(name=_get_banker_description_text("new_daily_gold", get_messages(server_db_path, "new_daily_gold")), value=f"{amount:,} coins per day", inline=True)
                embed.add_field(name=_get_banker_description_text("administrator", get_messages(server_db_path, "administrator")), value=ctx.author.display_name, inline=True)
                embed.add_field(name=_get_banker_description_text("server", get_messages(server_db_path, "server")), value=server_id, inline=True)

                if amount > 0:
                    embed.add_field(name=_get_banker_description_text("next_distribution", get_messages(server_db_path, "next_distribution")), value="Will be distributed automatically every day", inline=False)
                embed.set_footer(text=get_messages(server_db_path, "help_footer"))
                await ctx.send(embed=embed)
            else:
                await ctx.send(get_messages(server_db_path, "error_configuring_daily_gold"))
        except ValueError:
            await ctx.send(get_messages(server_db_path, "error_invalid_amount"))


async def _cmd_banker_bonus(ctx, db_banker, server_id, subargs):
    """Show opening bonus information (calculated as 10x TAE)."""
    server_db_path = _get_server_db_path(ctx.guild)
    if not is_admin(ctx):
        await ctx.send(get_messages(server_db_path, "error_admin_account_bonus"))
        return

    # Show current bonus calculation
    current_tae = db_banker.get_tae(server_id)
    current_bonus = current_tae * 10

    embed = discord.Embed(
        title=_get_banker_description_text("account_bonus_title", get_messages(server_db_path, "account_bonus_title")),
        description="Opening bonus is automatically calculated as 10x the TAE rate.",
        color=discord.Color.green()
    )
    embed.add_field(name="Current TAE", value=f"{current_tae:,} coins", inline=True)
    embed.add_field(name="Opening Bonus", value=f"{current_bonus:,} coins (10x TAE)", inline=True)
    embed.add_field(name=_get_banker_description_text("server", get_messages(server_db_path, "server")), value=server_id, inline=True)
    embed.add_field(name="How to change", value="Use `!banker tae <amount>` to change the TAE rate", inline=False)
    embed.set_footer(text="New accounts automatically receive 10x TAE as opening bonus")
    await ctx.send(embed=embed)
