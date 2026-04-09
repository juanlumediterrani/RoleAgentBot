"""
Discord commands for the MC (Master of Ceremonies / Music).
Registers: !mc (group with subcommands play, skip, stop, etc.)
"""

import json
import os

from agent_logging import get_logger
from discord_bot.discord_utils import is_duplicate_command

logger = get_logger('mc_discord')

# Availability flags
MC_COMMANDS_AVAILABLE = False
MCCommands = None
COMANDOS_MC = None

try:
    from roles.mc.mc_commands import MCCommands as _MCCommands
    MC_COMMANDS_AVAILABLE = True
    MCCommands = _MCCommands
    COMANDOS_MC = {
        "play": _MCCommands.cmd_play,
        "skip": _MCCommands.cmd_skip,
        "stop": _MCCommands.cmd_stop,
        "pause": _MCCommands.cmd_pause,
        "resume": _MCCommands.cmd_resume,
        "volume": _MCCommands.cmd_volume,
        "nowplaying": _MCCommands.cmd_nowplaying,
        "np": _MCCommands.cmd_nowplaying,
        "history": _MCCommands.cmd_history,
        "leave": _MCCommands.cmd_leave,
        "disconnect": _MCCommands.cmd_leave,
        "queue": _MCCommands.cmd_queue,
        "clear": _MCCommands.cmd_clear,
        "add": _MCCommands.cmd_play,
        "help": _MCCommands.cmd_help,
        "commands": _MCCommands.cmd_help,
    }
except ImportError as e:
    logger.warning(f"MC commands not available: {e}")

# Global instance accessor
_mc_commands_instance = None


def _get_mc_description_text(key: str, fallback: str) -> str:
    try:
        from agent_runtime import get_personality_file_path
        descriptions_path = get_personality_file_path("descriptions.json")
        with open(descriptions_path, encoding="utf-8") as f:
            descriptions = json.load(f).get("discord", {}).get("role_messages", {})
        value = descriptions.get(key)
        return str(value) if value else fallback
    except Exception:
        return fallback

def get_mc_commands_instance():
    """Get the global MC commands instance."""
    return _mc_commands_instance


def register_mc_commands(bot, personality, agent_config):
    """Register MC commands with the bot."""
    from agent_engine import is_mc_enabled, get_mc_mode, get_mc_feature

    if not is_mc_enabled():
        logger.info("🎵 MC disabled in configuration")
        return

    mc_mode = get_mc_mode()
    logger.info(f"🎵 MC mode: '{mc_mode}'")

    if mc_mode == "integrated":
        _register_mc_integrated(bot, personality)
    elif mc_mode == "standalone":
        logger.info("🎵 MC standalone mode - delegating to separate process")
    else:
        logger.warning(f"🎵 MC mode '{mc_mode}' not recognized")


def _register_mc_integrated(bot, personality):
    """Register MC commands integrated in the main bot."""
    from agent_engine import get_mc_feature

    if not MC_COMMANDS_AVAILABLE:
        logger.warning("🎵 MC integrated requires yt-dlp and PyNaCl")
        
        # Check if mc command already exists before registering
        if bot.get_command("mc") is None:
            @bot.command(name="mc")
            async def mc_unavailable(ctx):
                await ctx.send("🎵 MC is not available (requires `yt-dlp` and `PyNaCl`).")
        return

    mc_commands_instance = MCCommands(bot)
    
    # Store global instance for Canvas access
    global _mc_commands_instance
    _mc_commands_instance = mc_commands_instance

    # Get or create mc group
    mc_group = bot.get_command("mc")
    if mc_group is None:
        @bot.group(name="mc")
        async def mc_group(ctx):
            """MC commands (music)."""
            if is_duplicate_command(ctx, "mc"):
                return
            if ctx.invoked_subcommand is None:
                music_help = _get_mc_description_text("music_help", "🎵 Usa `!mc help` para ver los comandos disponibles")
                await ctx.send(music_help)
        logger.info("🎵 MC group command registered")
    else:
        logger.info("🎵 MC group command already exists, using existing group")

    def make_mc_command(name, func):
        async def command(ctx, *args):
            if is_duplicate_command(ctx, f"mc_{name}"):
                return
            return await func(mc_commands_instance, ctx.message, list(args))
        return command

    # Register voice commands
    if get_mc_feature("voice_commands"):
        voice_cmds = ["play", "skip", "stop", "pause", "resume", "volume",
                       "nowplaying", "np", "history", "leave", "disconnect"]
        for cmd_name in voice_cmds:
            if cmd_name in COMANDOS_MC:
                try:
                    # Check if subcommand already exists
                    if mc_group.get_command(cmd_name) is None:
                        mc_group.command(name=cmd_name)(make_mc_command(cmd_name, COMANDOS_MC[cmd_name]))
                        logger.info(f"🎵 MC command {cmd_name} registered")
                    else:
                        logger.info(f"🎵 MC command {cmd_name} already exists, skipping")
                except Exception as e:
                    logger.error(f"Error registering MC command {cmd_name}: {e}")

    # Register help (always available)
    try:
        # Check if help subcommands already exist
        if mc_group.get_command("help") is None:
            mc_group.command(name="help")(make_mc_command("help", MCCommands.cmd_help))
            logger.info("🎵 MC help command registered")
        else:
            logger.info("🎵 MC help command already exists, skipping")
            
        if mc_group.get_command("commands") is None:
            mc_group.command(name="commands")(make_mc_command("commands", MCCommands.cmd_help))
            logger.info("🎵 MC commands command registered")
        else:
            logger.info("🎵 MC commands command already exists, skipping")
    except Exception as e:
        logger.error(f"Error registering MC help command: {e}")

    # Register queue management
    if get_mc_feature("queue_management"):
        queue_cmds = ["queue", "clear", "add"]
        for cmd_name in queue_cmds:
            if cmd_name in COMANDOS_MC:
                try:
                    # Check if subcommand already exists
                    if mc_group.get_command(cmd_name) is None:
                        mc_group.command(name=cmd_name)(make_mc_command(cmd_name, COMANDOS_MC[cmd_name]))
                        logger.info(f"🎵 MC command {cmd_name} registered")
                    else:
                        logger.info(f"🎵 MC command {cmd_name} already exists, skipping")
                except Exception as e:
                    logger.error(f"Error registering MC command {cmd_name}: {e}")

    logger.info(f"🎵 MC integrated registered with {len(mc_group.commands)} commands")
