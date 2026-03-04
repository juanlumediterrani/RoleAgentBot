"""
Comandos de Discord para Buscar Anillo.
Registra: !acusaranillo
"""

import asyncio
from agent_logging import get_logger
from agent_engine import pensar
from discord_utils import get_db_for_server

logger = get_logger('anillo_discord')


def register_anillo_commands(bot, personality, agent_config):
    """Registra comandos de Buscar Anillo (idempotente)."""

    if bot.get_command("acusaranillo") is None:
        @bot.command(name="acusaranillo")
        async def cmd_acusar_anillo(ctx, target: str = ""):
            if not target:
                await ctx.send("❌ Debes mencionar a alguien para acusar. Ejemplo: !acusaranillo @usuario")
                return

            db_instance = get_db_for_server(ctx.guild)

            mentioned_user = None
            for user in ctx.message.mentions:
                if not user.bot and user.id != ctx.author.id:
                    mentioned_user = user
                    break

            if not mentioned_user:
                await ctx.send("❌ No se encontró un usuario válido para acusar.")
                return

            accusation_prompt = f"Acusa brevemente a {mentioned_user.display_name} de tener el anillo uniko. Sé orco y directo."
            accusation = await asyncio.to_thread(pensar, accusation_prompt)

            await ctx.send(f"👁️ {mentioned_user.mention} {accusation}")

            await asyncio.to_thread(
                db_instance.registrar_interaccion,
                ctx.author.id, ctx.author.name,
                "ACUSACION_ANILLO",
                f"Acusó a {mentioned_user.name} por el anillo",
                ctx.channel.id, ctx.guild.id,
                metadata={"acusado": mentioned_user.id, "acusacion": accusation}
            )

            logger.info(f"👁️ {ctx.author.name} acusó a {mentioned_user.name} en {ctx.guild.name}")

        logger.info("👁️ Comando acusaranillo registrado")

    logger.info("👁️ Comandos de Buscar Anillo registrados")
