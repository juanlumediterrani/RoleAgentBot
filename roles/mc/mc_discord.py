"""
Discord commands for the MC (Master of Ceremonies / Music).
Registers: !mc (group with subcommands play, skip, stop, etc.)
"""

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


def register_mc_commands(bot, personality, agent_config):
    """Register MC commands according to configured mode."""
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

        @bot.command(name="mc")
        async def mc_unavailable(ctx):
            await ctx.send("🎵 MC is not available (requires `yt-dlp` and `PyNaCl`).")
        return

    mc_commands_instance = MCCommands(bot)

    @bot.group(name="mc")
    async def mc_group(ctx):
        """MC commands (music)."""
        if is_duplicate_command(ctx, "mc"):
            return
        if ctx.invoked_subcommand is None:
            music_help = personality.get("discord", {}).get("role_messages", {}).get(
                "music_help", "🎵 Usa `!mc help` para ver los comandos disponibles"
            )
            await ctx.send(music_help)

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
                    mc_group.command(name=cmd_name)(make_mc_command(cmd_name, COMANDOS_MC[cmd_name]))
                    logger.info(f"🎵 MC command {cmd_name} registered")
                except Exception as e:
                    logger.error(f"Error registering MC command {cmd_name}: {e}")

    # Register help (always available)
    try:
        mc_group.command(name="help")(make_mc_command("help", MCCommands.cmd_help))
        mc_group.command(name="commands")(make_mc_command("commands", MCCommands.cmd_help))
        logger.info("🎵 MC help command registered")
    except Exception as e:
        logger.error(f"Error registering MC help command: {e}")

    # Register queue management
    if get_mc_feature("queue_management"):
        queue_cmds = ["queue", "clear", "add"]
        for cmd_name in queue_cmds:
            if cmd_name in COMANDOS_MC:
                try:
                    mc_group.command(name=cmd_name)(make_mc_command(cmd_name, COMANDOS_MC[cmd_name]))
                    logger.info(f"🎵 MC command {cmd_name} registered")
                except Exception as e:
                    logger.error(f"Error registering MC command {cmd_name}: {e}")

    logger.info(f"🎵 MC integrated registered with {len(mc_group.commands)} commands")
