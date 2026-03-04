"""
Comandos de Discord para el MC (Master of Ceremonies / Música).
Registra: !mc (group con subcomandos play, skip, stop, etc.)
"""

from agent_logging import get_logger
from discord_utils import is_duplicate_command

logger = get_logger('mc_discord')

# Flags de disponibilidad
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
    logger.warning(f"MC commands no disponibles: {e}")


def register_mc_commands(bot, personality, agent_config):
    """Registra comandos del MC según el modo configurado."""
    from agent_engine import is_mc_enabled, get_mc_mode, get_mc_feature

    if not is_mc_enabled():
        logger.info("🎵 MC desactivado en configuración")
        return

    mc_mode = get_mc_mode()
    logger.info(f"🎵 MC modo: '{mc_mode}'")

    if mc_mode == "integrated":
        _register_mc_integrated(bot, personality)
    elif mc_mode == "standalone":
        logger.info("🎵 MC modo standalone - delegando a proceso separado")
    else:
        logger.warning(f"🎵 MC modo '{mc_mode}' no reconocido")


def _register_mc_integrated(bot, personality):
    """Registra comandos MC integrados en el bot principal."""
    from agent_engine import get_mc_feature

    if not MC_COMMANDS_AVAILABLE:
        logger.warning("🎵 MC integrado requiere yt-dlp y PyNaCl")

        @bot.command(name="mc")
        async def mc_unavailable(ctx):
            await ctx.send("🎵 El MC no está disponible (requiere `yt-dlp` y `PyNaCl`).")
        return

    mc_commands_instance = MCCommands(bot)

    @bot.group(name="mc")
    async def mc_group(ctx):
        """Comandos del MC (música)."""
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

    # Registrar voice commands
    if get_mc_feature("voice_commands"):
        voice_cmds = ["play", "skip", "stop", "pause", "resume", "volume",
                       "nowplaying", "np", "history", "leave", "disconnect"]
        for cmd_name in voice_cmds:
            if cmd_name in COMANDOS_MC:
                try:
                    mc_group.command(name=cmd_name)(make_mc_command(cmd_name, COMANDOS_MC[cmd_name]))
                    logger.info(f"🎵 Comando mc {cmd_name} registrado")
                except Exception as e:
                    logger.error(f"Error registrando comando mc {cmd_name}: {e}")

    # Registrar help (siempre disponible)
    try:
        mc_group.command(name="help")(make_mc_command("help", MCCommands.cmd_help))
        mc_group.command(name="commands")(make_mc_command("commands", MCCommands.cmd_help))
        logger.info("🎵 Comando mc help registrado")
    except Exception as e:
        logger.error(f"Error registrando comando mc help: {e}")

    # Registrar queue management
    if get_mc_feature("queue_management"):
        queue_cmds = ["queue", "clear", "add"]
        for cmd_name in queue_cmds:
            if cmd_name in COMANDOS_MC:
                try:
                    mc_group.command(name=cmd_name)(make_mc_command(cmd_name, COMANDOS_MC[cmd_name]))
                    logger.info(f"🎵 Comando mc {cmd_name} registrado")
                except Exception as e:
                    logger.error(f"Error registrando comando mc {cmd_name}: {e}")

    logger.info(f"🎵 MC integrado registrado con {len(mc_group.commands)} comandos")
