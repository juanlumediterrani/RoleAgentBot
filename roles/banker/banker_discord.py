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
    from roles.banker.db_role_banker import (
        DatabaseRoleBanker,
        get_banker_db_instance,
    )
    BANKER_DB_AVAILABLE = True
except ImportError:
    BANKER_DB_AVAILABLE = False
    get_banker_db_instance = None


def _get_banker_db(guild):
    """Get banker database instance for a server."""
    if not BANKER_DB_AVAILABLE or get_banker_db_instance is None:
        return None
    try:
        id_key = str(guild.id)
        return get_banker_db_instance(id_key)
    except Exception:
        return get_banker_db_instance(str(guild.id))


def _get_dice_game_db(guild):
    """Get dice game database instance for a server."""
    try:
        from roles.trickster.subroles.dice_game.db_dice_game import get_dice_game_db_instance
        id_key = str(guild.id)
        return get_dice_game_db_instance(id_key)
    except ImportError:
        return None


def _initialize_dice_game_account(user_id: str, user_name: str, server_id: str, server_key: str, legacy_server_name: str):
    try:
        db_dice_game = _get_dice_game_db_by_key(server_key, legacy_server_name)
        if db_dice_game:
            if hasattr(db_dice_game, "ensure_player_stats"):
                ok = db_dice_game.ensure_player_stats(user_id, server_id)
                if ok:
                    logger.info(f"🎲 Dice game account initialized for {user_name}")
                return bool(ok)
            stats = db_dice_game.obtener_estadisticas_jugador(user_id, server_id)
            if stats.get('total_plays', 0) == 0:
                logger.info(f"🎲 Dice game account ready for {user_name} (will be created on first play)")
                return True
    except Exception as e:
        logger.warning(f"Could not initialize dice game account for {user_name}: {e}")
    return False


def _get_dice_game_db_by_key(server_key: str, legacy_server_name: str):
    """Get dice game database instance by server key, with legacy name fallback."""
    try:
        from roles.trickster.subroles.dice_game.db_dice_game import get_dice_game_db_instance
        return get_dice_game_db_instance(server_key)
    except ImportError:
        return None


def _build_banker_help_embed():
    """Build banker help embed (reused in help and no args)."""
    embed = discord.Embed(
        title=get_message("help_title"),
        description=get_message("help_description"),
        color=discord.Color.gold()
    )
    embed.add_field(
        name=get_message("ver_saldo"),
        value=get_message("ver_saldo_desc"),
        inline=False
    )
    embed.add_field(
        name=get_message("configurar_tae"),
        value=get_message("configurar_tae_desc"),
        inline=False
    )
    embed.add_field(
        name=get_message("configurar_bono"),
        value=get_message("configurar_bono_desc"),
        inline=False
    )
    embed.add_field(
        name=get_message("informacion"),
        value=get_message("informacion_desc"),
        inline=False
    )
    embed.set_footer(text=get_message("help_footer"))
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
        server_name = ctx.guild.name

        # No args or "help" → show help
        if not args or (args and args[0].lower() == "help"):
            embed = _build_banker_help_embed()
            confirm = get_message("help_sent")
            await send_embed_dm_or_channel(ctx, embed, confirm)
            return

        subcommand = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []

        if subcommand == "balance":
            await _cmd_banker_balance(ctx, db_banker, server_id, server_name)
        elif subcommand == "tae":
            await _cmd_banker_tae(ctx, db_banker, server_id, server_name, subargs)
        elif subcommand == "bonus":
            await _cmd_banker_bonus(ctx, db_banker, server_id, server_name, subargs)
        else:
            await ctx.send(get_message("command_not_recognized", subcommand=subcommand))

    logger.info("💰 Banker commands registered")


# --- SUBCOMMANDS ---

async def _cmd_banker_balance(ctx, db_banker, server_id, server_name):
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
            db_banker.create_wallet(member_id, member_name, server_id, server_name)

        db_dice_game = _get_dice_game_db(ctx.guild)
        if db_dice_game is not None:
            db_banker.create_wallet("dice_game_pot", "Dice Game Pot", server_id, server_name)
            for member in getattr(ctx.guild, "members", []) or []:
                if getattr(member, "bot", False):
                    continue
                _initialize_dice_game_account(str(member.id), member.display_name, server_id, server_key, server_name)
    except Exception as e:
        logger.warning(f"Bulk initialization failed: {e}")
    
    # Create wallet if it doesn't exist (with opening bonus)
    was_created, initial_balance = db_banker.create_wallet(user_id, user_name, server_id, server_name)
    
    # Initialize dice game account for new and existing users
    dice_game_initialized = _initialize_dice_game_account(user_id, user_name, server_id, server_key, server_name)
    
    balance = db_banker.get_balance(user_id, server_id)
    history = db_banker.get_transaction_history(user_id, server_id, limit=5)
    
    embed = discord.Embed(
        title=_get_banker_description_text("balance_title", get_message("balance_title")),
        description=get_message("saldo_description"),
        color=discord.Color.gold()
    )
    embed.add_field(name=_get_banker_description_text("current_balance", get_message("saldo_actual")), value=f"{balance:,} gold coins", inline=False)
    embed.add_field(name=_get_banker_description_text("account_holder", get_message("titular")), value=user_name, inline=True)
    embed.add_field(name=_get_banker_description_text("bank", get_message("banco")), value=server_name, inline=True)

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
            embed.add_field(name=_get_banker_description_text("recent_transactions", get_message("transacciones_recientes")), value=history_text[:1024], inline=False)

    embed.set_footer(text=get_message("help_footer"))
    embed.set_thumbnail(url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)

    confirm = get_message("saldo_enviado")
    await send_embed_dm_or_channel(ctx, embed, confirm)


async def _cmd_banker_tae(ctx, db_banker, server_id, server_name, subargs):
    """Configure or view TAE (admins only)."""
    if not is_admin(ctx):
        await ctx.send(get_message("error_no_admin_tae"))
        return

    if not subargs:
        # Show current TAE
        current_tae = db_banker.obtener_tae(server_id)
        last_distribution = db_banker.obtener_ultima_distribucion(server_id)

        embed = discord.Embed(
            title=_get_banker_description_text("daily_allowance_config_title", get_message("daily_allowance_config_title")),
            description=get_message("tae_description"),
            color=discord.Color.blue()
        )
        embed.add_field(name=get_message("tae_actual"), value=f"{current_tae:,} coins", inline=True)
        embed.add_field(name=_get_banker_description_text("last_distribution", get_message("ultima_distribucion")), value=last_distribution[:10] if last_distribution else "Never", inline=True)

        if current_tae == 0:
            embed.add_field(name=get_message("tae_no_configurada"), value="Use !banker tae <amount> to configure", inline=False)
        else:
            embed.add_field(name=get_message("tae_info"), value=f"Each user will receive {current_tae:,} coins daily", inline=False)

        embed.set_footer(text=get_message("tae_footer"))
        await ctx.send(embed=embed)
    else:
        # Set new TAE
        try:
            amount = int(subargs[0])
            if amount < 0 or amount > 1000:
                await ctx.send(get_message("error_tae_rango"))
                return

            admin_id = str(ctx.author.id)
            if db_banker.configurar_tae(server_id, server_name, amount, admin_id):
                embed = discord.Embed(
                    title=get_message("tae_configurada"),
                    description=get_message("tae_actualizada"),
                    color=discord.Color.green()
                )
                embed.add_field(name=_get_banker_description_text("new_daily_allowance", get_message("nueva_tae")), value=f"{amount:,} coins per day", inline=True)
                embed.add_field(name=_get_banker_description_text("administrator", get_message("administrador")), value=ctx.author.display_name, inline=True)
                embed.add_field(name=_get_banker_description_text("server", get_message("servidor")), value=server_name, inline=True)
                
                if amount > 0:
                    embed.add_field(name=_get_banker_description_text("next_distribution", get_message("proxima_distribucion")), value="Will be distributed automatically every day", inline=False)
                embed.set_footer(text=get_message("help_footer"))
                await ctx.send(embed=embed)
            else:
                await ctx.send(get_message("error_configurar_tae"))
        except ValueError:
            await ctx.send(get_message("error_numero_invalido"))


async def _cmd_banker_bonus(ctx, db_banker, server_id, server_name, subargs):
    """Configure or view opening bonus (admins only)."""
    if not is_admin(ctx):
        await ctx.send(get_message("error_no_admin_bono"))
        return

    if not subargs:
        # Show current bonus
        current_bonus = db_banker.obtener_bono(server_id)

        embed = discord.Embed(
            title=_get_banker_description_text("bonus_config_title", get_message("bonus_config_title")),
            description=get_message("bono_description"),
            color=discord.Color.green()
        )
        embed.add_field(name=_get_banker_description_text("current_bonus", get_message("bono_actual")), value=f"{current_bonus:,} coins", inline=True)
        embed.add_field(name=_get_banker_description_text("server", get_message("servidor")), value=server_name, inline=True)
        embed.add_field(name=_get_banker_description_text("bonus_info", get_message("bono_info")), value=f"Each new account will receive {current_bonus:,} coins automatically", inline=False)
        embed.set_footer(text=_get_banker_description_text("bonus_footer", get_message("bono_footer")))
        await ctx.send(embed=embed)
    else:
        # Set new bonus
        try:
            amount = int(subargs[0])
            if amount < 0 or amount > 10000:
                await ctx.send(get_message("error_bono_rango"))
                return

            admin_id = str(ctx.author.id)
            if db_banker.configurar_bono(server_id, server_name, amount, admin_id):
                embed = discord.Embed(
                    title=get_message("bono_configurado"),
                    description=get_message("bono_actualizado"),
                    color=discord.Color.green()
                )
                embed.add_field(name=_get_banker_description_text("new_bonus", get_message("nuevo_bono")), value=f"{amount:,} coins", inline=True)
                embed.add_field(name=_get_banker_description_text("administrator", get_message("administrador")), value=ctx.author.display_name, inline=True)
                embed.add_field(name=_get_banker_description_text("server", get_message("servidor")), value=server_name, inline=True)
                embed.add_field(name=get_message("aplicacion"), value="Next new accounts will receive this bonus", inline=False)
                embed.set_footer(text=get_message("help_footer"))
                await ctx.send(embed=embed)
            else:
                await ctx.send(get_message("error_configurar_bono"))
        except ValueError:
            await ctx.send(get_message("error_numero_invalido"))
