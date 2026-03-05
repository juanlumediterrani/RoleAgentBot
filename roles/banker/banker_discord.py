"""
Discord commands for the Banker role (English version).
Registers: !banker (balance, tae, bonus, help)
"""

import discord
from agent_logging import get_logger
from discord_bot.discord_utils import is_admin, send_embed_dm_or_channel

logger = get_logger('banker_discord')

# Availability flags
try:
    from roles.banker.db_role_banker import (
        DatabaseRoleBanquero as DatabaseRoleBanker,
        get_banquero_db_instance as get_banker_db_instance,
    )
    BANKER_DB_AVAILABLE = True
except ImportError:
    BANKER_DB_AVAILABLE = False
    get_banker_db_instance = None


def _get_banker_db(guild):
    """Get banker database instance for a server."""
    if not BANKER_DB_AVAILABLE or get_banker_db_instance is None:
        return None
    return get_banker_db_instance(guild.name)


def _get_banker_msgs(personality):
    """Get customized banker messages."""
    return personality.get("discord", {}).get("banker_messages", {})


def _build_banker_help_embed(personality):
    """Build banker help embed (reused in help and no args)."""
    msgs = _get_banker_msgs(personality)
    embed = discord.Embed(
        title=msgs.get("help_title", "💰 Banker - Help"),
        description=msgs.get("help_description", "Available commands to manage server economy"),
        color=discord.Color.gold()
    )
    embed.add_field(
        name=msgs.get("view_balance", "💎 View Balance"),
        value=msgs.get("view_balance_desc", "`!banker balance`\nShows your current gold balance and recent transactions.\nNew accounts receive opening bonus automatically."),
        inline=False
    )
    embed.add_field(
        name=msgs.get("configure_tae", "🏦 Configure TAE (Admins)"),
        value=msgs.get("configure_tae_desc", "`!banker tae <amount>`\nSets daily TAE (0-1000 coins).\n`!banker tae` - View current configuration."),
        inline=False
    )
    embed.add_field(
        name=msgs.get("configure_bonus", "🎁 Configure Opening Bonus (Admins)"),
        value=msgs.get("configure_bonus_desc", "`!banker bonus <amount>`\nSets opening bonus for new accounts (0-10000 coins).\n`!banker bonus` - View current configuration."),
        inline=False
    )
    embed.add_field(
        name=msgs.get("information", "ℹ️ Information"),
        value=msgs.get("information_desc", "• TAE is distributed automatically every day to all users with wallets.\n• New accounts automatically receive the configured opening bonus.\n• All transactions are recorded.\n• Only administrators can configure TAE and opening bonus."),
        inline=False
    )
    embed.set_footer(text=msgs.get("help_footer", "💼 Banker - Server Economic Management"))
    return embed


def register_banker_commands(bot, personality, agent_config):
    """Register banker commands (idempotent)."""

    if not BANKER_DB_AVAILABLE:
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
            msgs = _get_banker_msgs(personality)
            await ctx.send(msgs.get("error_banker_db", "❌ This command only works on servers."))
            return

        try:
            db_banker = _get_banker_db(ctx.guild)
            if db_banker is None:
                msgs = _get_banker_msgs(personality)
                await ctx.send(msgs.get("error_banker_db", "❌ Banker database not available."))
                return
        except Exception as e:
            logger.exception(f"Error getting banker DB: {e}")
            msgs = _get_banker_msgs(personality)
            await ctx.send(msgs.get("error_banker_db", "❌ Error accessing banker database."))
            return

        server_id = str(ctx.guild.id)
        server_name = ctx.guild.name

        # No args or "help" → show help
        if not args or (args and args[0].lower() == "help"):
            embed = _build_banker_help_embed(personality)
            confirm = _get_banker_msgs(personality).get("help_sent", "📩 Banker help sent by private message.")
            await send_embed_dm_or_channel(ctx, embed, confirm)
            return

        subcommand = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []

        if subcommand == "balance":
            await _cmd_banker_balance(ctx, db_banker, server_id, server_name, personality)
        elif subcommand == "tae":
            await _cmd_banker_tae(ctx, db_banker, server_id, server_name, subargs, personality)
        elif subcommand == "bonus":
            await _cmd_banker_bonus(ctx, db_banker, server_id, server_name, subargs, personality)
        else:
            msgs = _get_banker_msgs(personality)
            await ctx.send(msgs.get("command_not_recognized", "❌ Subcommand '{subcommand}' not recognized! Use `!banker help` to see help.").format(subcommand=subcommand))

    logger.info("💰 Banker commands registered")

    # Legacy Spanish alias with deprecation warning
    if bot.get_command("banquero") is None:
        @bot.command(name="banquero")
        async def cmd_banquero_legacy(ctx, *args):
            """Legacy command - use !banker instead."""
            await ctx.send("⚠️ `!banquero` is deprecated. Use `!banker` instead.")
            # Redirect to new command
            if args:
                await cmd_banker.invoke(ctx, args)
            else:
                await ctx.send("Use `!banker help` to see available commands.")


# --- SUBCOMMANDS ---

async def _cmd_banker_balance(ctx, db_banker, server_id, server_name, personality):
    """Show user balance."""
    user_id = str(ctx.author.id)
    user_name = ctx.author.display_name

    db_banker.crear_cartera(user_id, user_name, server_id, server_name)
    balance = db_banker.obtener_saldo(user_id, server_id)
    history = db_banker.obtener_historial_transacciones(user_id, server_id, 5)

    msgs = _get_banker_msgs(personality)
    embed = discord.Embed(
        title=msgs.get("balance_title", "💰 Banker Wallet"),
        description=msgs.get("balance_description", "Your gold wallet status"),
        color=discord.Color.gold()
    )
    embed.add_field(name=msgs.get("current_balance", "💎 Current Balance"), value=f"{balance:,} gold coins", inline=False)
    embed.add_field(name=msgs.get("holder", "👤 Holder"), value=user_name, inline=True)
    embed.add_field(name=msgs.get("bank", "🏦 Bank"), value=server_name, inline=True)

    if history:
        history_text = ""
        for trans in history:
            trans_type, amount, balance_before, balance_after, description, date, admin = trans
            emoji = "📥" if amount > 0 else "📤"
            history_text += f"{emoji} {amount:,} ({trans_type})\n"
        if history_text:
            embed.add_field(name=msgs.get("recent_transactions", "📊 Recent Transactions"), value=history_text[:1024], inline=False)

    embed.set_footer(text=msgs.get("help_footer", "💼 Banker - Server Economic Management"))
    embed.set_thumbnail(url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)

    confirm = msgs.get("balance_sent", "💰 Your wallet information sent by private message.")
    await send_embed_dm_or_channel(ctx, embed, confirm)


async def _cmd_banker_tae(ctx, db_banker, server_id, server_name, subargs, personality):
    """Configure or view TAE (admins only)."""
    if not is_admin(ctx):
        msgs = _get_banker_msgs(personality)
        await ctx.send(msgs.get("error_no_admin_tae", "❌ Only orc bosses can configure TAE!"))
        return

    msgs = _get_banker_msgs(personality)

    if not subargs:
        # Show current TAE
        current_tae = db_banker.obtener_tae(server_id)
        last_distribution = db_banker.obtener_ultima_distribucion(server_id)

        embed = discord.Embed(
            title=msgs.get("tae_config_title", "🏦 TAE Configuration"),
            description=msgs.get("tae_description", "Current Annual Equivalent Rate configuration"),
            color=discord.Color.blue()
        )
        embed.add_field(name=msgs.get("current_tae", "💰 Current Daily TAE"), value=f"{current_tae:,} coins", inline=True)
        embed.add_field(name=msgs.get("last_distribution", "📅 Last Distribution"), value=last_distribution[:10] if last_distribution else "Never", inline=True)

        if current_tae == 0:
            embed.add_field(name=msgs.get("tae_not_configured", "⚠️ Status: TAE not configured"), value="\u200b", inline=False)
        else:
            embed.add_field(name=msgs.get("tae_info", "ℹ️ Info"), value=f"Each user will receive {current_tae:,} coins daily", inline=False)

        embed.set_footer(text=msgs.get("tae_footer", "💼 Use !banker tae <amount> to configure"))
        await ctx.send(embed=embed)
    else:
        # Set new TAE
        try:
            amount = int(subargs[0])
            if amount < 0 or amount > 1000:
                await ctx.send(msgs.get("error_tae_range", "❌ TAE must be between 0 and 1000 daily coins!"))
                return

            admin_id = str(ctx.author.id)
            admin_name = ctx.author.display_name

            if db_banker.establecer_tae(server_id, amount, admin_id, admin_name):
                embed = discord.Embed(
                    title=msgs.get("tae_configured", "✅ TAE Configured"),
                    description=msgs.get("tae_updated", "The Annual Equivalent Rate has been updated"),
                    color=discord.Color.green()
                )
                embed.add_field(name=msgs.get("new_tae", "💰 New Daily TAE"), value=f"{amount:,} coins", inline=True)
                embed.add_field(name=msgs.get("administrator", "👤 Administrator"), value=admin_name, inline=True)
                embed.add_field(name=msgs.get("server", "🏦 Server"), value=server_name, inline=True)
                if amount > 0:
                    embed.add_field(name=msgs.get("next_distribution", "ℹ️ Next Distribution"), value="Will be distributed automatically every day", inline=False)
                embed.set_footer(text=msgs.get("help_footer", "💼 Banker - Economic Management"))
                await ctx.send(embed=embed)
            else:
                await ctx.send(msgs.get("error_configuring_tae", "❌ Error configuring TAE!"))
        except ValueError:
            await ctx.send(msgs.get("error_invalid_number", "❌ Invalid amount! Use an integer number!"))


async def _cmd_banker_bonus(ctx, db_banker, server_id, server_name, subargs, personality):
    """Configure or view opening bonus (admins only)."""
    if not is_admin(ctx):
        msgs = _get_banker_msgs(personality)
        await ctx.send(msgs.get("error_no_admin_bonus", "❌ Only orc bosses can configure opening bonus!"))
        return

    msgs = _get_banker_msgs(personality)

    if not subargs:
        # Show current bonus
        current_bonus = db_banker.obtener_bono_apertura(server_id)

        embed = discord.Embed(
            title=msgs.get("bonus_config_title", "🎁 Opening Bonus Configuration"),
            description=msgs.get("bonus_description", "Current opening bonus configuration for new accounts"),
            color=discord.Color.purple()
        )
        embed.add_field(name=msgs.get("current_bonus", "💰 Current Opening Bonus"), value=f"{current_bonus:,} coins", inline=True)
        embed.add_field(name=msgs.get("server", "🏦 Server"), value=server_name, inline=True)
        embed.add_field(name=msgs.get("bonus_info", "ℹ️ Info"), value=f"Each new account will receive {current_bonus:,} coins automatically", inline=False)
        embed.set_footer(text=msgs.get("bonus_footer", "💼 Use !banker bonus <amount> to configure"))
        await ctx.send(embed=embed)
    else:
        # Set new bonus
        try:
            amount = int(subargs[0])
            if amount < 0 or amount > 10000:
                await ctx.send(msgs.get("error_bonus_range", "❌ Opening bonus must be between 0 and 10000 coins!"))
                return

            admin_id = str(ctx.author.id)
            admin_name = ctx.author.display_name

            if db_banker.establecer_bono_apertura(server_id, amount, admin_id, admin_name):
                embed = discord.Embed(
                    title=msgs.get("bonus_configured", "✅ Opening Bonus Configured"),
                    description=msgs.get("bonus_updated", "The opening bonus has been updated"),
                    color=discord.Color.green()
                )
                embed.add_field(name=msgs.get("new_bonus", "💰 New Opening Bonus"), value=f"{amount:,} coins", inline=True)
                embed.add_field(name=msgs.get("administrator", "👤 Administrator"), value=admin_name, inline=True)
                embed.add_field(name=msgs.get("server", "🏦 Server"), value=server_name, inline=True)
                embed.add_field(name=msgs.get("application", "ℹ️ Application"), value="Next new accounts will receive this bonus", inline=False)
                embed.set_footer(text=msgs.get("help_footer", "💼 Banker - Economic Configuration"))
                await ctx.send(embed=embed)
            else:
                await ctx.send(msgs.get("error_configuring_bonus", "❌ Error configuring opening bonus!"))
        except ValueError:
            await ctx.send(msgs.get("error_invalid_number", "❌ Invalid amount! Use an integer number!"))
