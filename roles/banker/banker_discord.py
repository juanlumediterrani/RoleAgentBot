"""
Discord commands for the Banker role (English version).
Registers: !banker (balance, tae, bonus, help)
"""

import discord
import json
import os
from agent_logging import get_logger
from .banker_messages import get_message
from discord_bot.discord_utils import is_admin, send_embed_dm_or_channel

logger = get_logger('banker_discord')


def _get_banker_description_text(key: str, fallback: str) -> str:
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "agent_config.json")
        with open(config_path, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        personality_rel = agent_cfg.get("personality", "")
        descriptions_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            os.path.dirname(personality_rel),
            "descriptions.json",
        )
        with open(descriptions_path, encoding="utf-8") as f:
            descriptions = json.load(f).get("discord", {}).get("banker_messages", {})
        value = descriptions.get(key)
        return str(value) if value else fallback
    except Exception:
        return fallback

# Availability flags
try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None


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


def _build_banker_help_embed():
    """Build banker help embed (reused in help and no args)."""
    embed = discord.Embed(
        title=get_message("help_title"),
        description=get_message("help_description"),
        color=discord.Color.gold()
    )
    embed.add_field(
        name=get_message("view_balance"),
        value=get_message("view_balance_desc"),
        inline=False
    )
    embed.add_field(
        name=get_message("configure_daily_gold"),
        value=get_message("configure_daily_gold_desc"),
        inline=False
    )
    embed.add_field(
        name=get_message("configure_account_bonus"),
        value=get_message("configure_account_bonus_desc"),
        inline=False
    )
    embed.add_field(
        name=get_message("information"),
        value=get_message("information_desc"),
        inline=False
    )
    embed.set_footer(text=get_message("help_footer"))
    return embed


def register_banker_commands(bot, personality, agent_config):
    """Register banker commands (idempotent)."""

    if not get_roles_db_instance is not None:
        logger.warning("💰 Banker database not available, skipping command registration")
        return

    if bot.get_command("banker") is not None:
        logger.info("💰 Banker commands already registered")
        return

    @bot.group(name="banker")
    async def cmd_banker(ctx, *args):
        """Main Banker command for economic management."""
        logger.info(f"💰 Banker command received with args: {args}")

        if not ctx.guild:
            await ctx.send(get_message("error_banker_db"))
            return

        try:
            db_banker = _get_banker_db(ctx.guild)
            if db_banker is None:
                await ctx.send(get_message("error_banker_db"))
                return
        except Exception as e:
            logger.exception(f"Error getting banker DB: {e}")
            await ctx.send(get_message("error_banker_db"))
            return

        server_id = str(ctx.guild.id)
        server_id=ctx.guild.name

        # No args or "help" → show help
        if not args or (args and args[0].lower() == "help"):
            embed = _build_banker_help_embed()
            confirm = get_message("help_sent")
            await send_embed_dm_or_channel(ctx, embed, confirm)
            return

        subcommand = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []

        if subcommand == "balance":
            await _cmd_banker_balance(ctx, db_banker, server_id)
        elif subcommand == "tae":
            await _cmd_banker_tae(ctx, db_banker, server_id, subargs)
        elif subcommand == "bonus":
            await _cmd_banker_bonus(ctx, db_banker, server_id, subargs)
        else:
            await ctx.send(get_message("command_not_recognized", subcommand=subcommand))

    logger.info("💰 Banker commands registered")


# --- SUBCOMMANDS ---

async def _cmd_banker_balance(ctx, db_banker, server_id):
    """Show user's gold balance."""
    user_id = str(ctx.author.id)
    user_name = ctx.author.display_name
    server_key = str(ctx.guild.id)

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
        title=_get_banker_description_text("balance_title", get_message("balance_title")),
        description=get_message("balance_description"),
        color=discord.Color.gold()
    )
    embed.add_field(name=_get_banker_description_text("current_balance", get_message("current_balance")), value=f"{balance:,} gold coins", inline=False)
    embed.add_field(name=_get_banker_description_text("account_holder", get_message("account_holder")), value=user_name, inline=True)
    embed.add_field(name=_get_banker_description_text("bank", get_message("bank")), value=server_id, inline=True)

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
            embed.add_field(name=_get_banker_description_text("recent_transactions", get_message("recent_transactions")), value=history_text[:1024], inline=False)

    embed.set_footer(text=get_message("help_footer"))
    embed.set_thumbnail(url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)

    confirm = get_message("balance_sent")
    await send_embed_dm_or_channel(ctx, embed, confirm)


async def _cmd_banker_tae(ctx, db_banker, server_id, subargs):
    """Configure or view TAE (admins only)."""
    if not is_admin(ctx):
        await ctx.send(get_message("error_admin_daily_gold"))
        return

    if not subargs:
        # Show current TAE
        current_tae = db_banker.get_tae(server_id)

        embed = discord.Embed(
            title=_get_banker_description_text("daily_allowance_config_title", get_message("daily_allowance_config_title")),
            description=get_message("daily_allowance_description"),
            color=discord.Color.blue()
        )
        embed.add_field(name=get_message("current_daily_gold"), value=f"{current_tae:,} coins", inline=True)
        embed.add_field(name=_get_banker_description_text("opening_bonus", "Opening Bonus"), value=f"{current_tae * 10:,} coins (10x TAE)", inline=True)

        if current_tae == 0:
            embed.add_field(name=get_message("daily_gold_not_configured"), value="Use !banker tae <amount> to configure", inline=False)
        else:
            embed.add_field(name=get_message("daily_gold_info"), value=f"Each user will receive {current_tae:,} coins daily", inline=False)

        embed.set_footer(text=get_message("daily_gold_footer"))
        await ctx.send(embed=embed)
    else:
        # Set new TAE
        try:
            amount = int(subargs[0])
            if amount < 0 or amount > 1000:
                await ctx.send(get_message("error_daily_gold_range"))
                return

            admin_id = str(ctx.author.id)
            if db_banker.set_tae(server_id, amount):
                embed = discord.Embed(
                    title=get_message("daily_gold_configured"),
                    description=get_message("daily_gold_updated"),
                    color=discord.Color.green()
                )
                embed.add_field(name=_get_banker_description_text("new_daily_gold", get_message("new_daily_gold")), value=f"{amount:,} coins per day", inline=True)
                embed.add_field(name=_get_banker_description_text("administrator", get_message("administrator")), value=ctx.author.display_name, inline=True)
                embed.add_field(name=_get_banker_description_text("server", get_message("server")), value=server_id, inline=True)
                
                if amount > 0:
                    embed.add_field(name=_get_banker_description_text("next_distribution", get_message("next_distribution")), value="Will be distributed automatically every day", inline=False)
                embed.set_footer(text=get_message("help_footer"))
                await ctx.send(embed=embed)
            else:
                await ctx.send(get_message("error_configuring_daily_gold"))
        except ValueError:
            await ctx.send(get_message("error_invalid_amount"))


async def _cmd_banker_bonus(ctx, db_banker, server_id, subargs):
    """Show opening bonus information (calculated as 10x TAE)."""
    if not is_admin(ctx):
        await ctx.send(get_message("error_admin_account_bonus"))
        return

    # Show current bonus calculation
    current_tae = db_banker.get_tae(server_id)
    current_bonus = current_tae * 10

    embed = discord.Embed(
        title=_get_banker_description_text("account_bonus_title", get_message("account_bonus_title")),
        description="Opening bonus is automatically calculated as 10x the TAE rate.",
        color=discord.Color.green()
    )
    embed.add_field(name="Current TAE", value=f"{current_tae:,} coins", inline=True)
    embed.add_field(name="Opening Bonus", value=f"{current_bonus:,} coins (10x TAE)", inline=True)
    embed.add_field(name=_get_banker_description_text("server", get_message("server")), value=server_id, inline=True)
    embed.add_field(name="How to change", value="Use `!banker tae <amount>` to change the TAE rate", inline=False)
    embed.set_footer(text="New accounts automatically receive 10x TAE as opening bonus")
    await ctx.send(embed=embed)
