"""
Comandos base del bot de Discord.
Incluye: ayuda, insulta, saludos de presencia/bienvenida, test, control de roles.
"""

import os
import asyncio
from agent_logging import get_logger
from agent_engine import PERSONALIDAD, pensar, AGENT_CFG
from discord_utils import (
    is_admin, is_duplicate_command, send_dm_or_channel,
    set_greeting_enabled, get_greeting_enabled,
    is_role_enabled_check,
)

logger = get_logger('discord_core')

_discord_cfg = PERSONALIDAD.get("discord", {})
_personality_name = PERSONALIDAD.get("name", "bot").lower()
_bot_display_name = PERSONALIDAD.get("bot_display_name", PERSONALIDAD.get("name", "Bot"))
_insult_cfg = _discord_cfg.get("insult_command", {})


def register_core_commands(bot, agent_config):
    """Registra todos los comandos base del bot."""

    # --- Nombres dinámicos basados en personalidad ---
    saluda_name = f"saluda{_personality_name}"
    nosaludes_name = f"nosaludes{_personality_name}"
    bienvenida_name = f"bienvenida{_personality_name}"
    nobienvenida_name = f"nobienvenida{_personality_name}"
    insulta_name = f"insulta{_personality_name}"
    ayuda_name = f"ayuda{_personality_name}"
    role_cmd_name = f"role{_personality_name}"

    # --- SALUDOS DE PRESENCIA ---

    async def _cmd_saluda_toggle(ctx, enabled: bool):
        """Comando genérico para activar/desactivar saludos de presencia."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Solo administradores pueden modificar los saludos de presencia."))
            return

        set_greeting_enabled(ctx.guild, enabled)

        greeting_cfg = PERSONALIDAD.get("discord", {}).get("greeting_messages", {})
        mensaje_activado = greeting_cfg.get("saludos_activados", "GRRR Kronk vigilará llegada de umanos! Kronk saludar cuando umanos aparecer!")
        mensaje_desactivado = greeting_cfg.get("saludos_desactivados", "BRRR Kronk ya no vigilar umanos! Kronk dejar de saludar, demasiado trabajo!")

        mensaje = mensaje_activado if enabled else mensaje_desactivado
        await ctx.send(mensaje)

        action = "activados" if enabled else "desactivados"
        logger.info(f"{ctx.author.name} {action} los saludos de presencia en {ctx.guild.name}")

    @bot.command(name=saluda_name)
    async def cmd_saluda_enable(ctx):
        await _cmd_saluda_toggle(ctx, True)

    @bot.command(name=nosaludes_name)
    async def cmd_saluda_disable(ctx):
        await _cmd_saluda_toggle(ctx, False)

    # --- BIENVENIDA ---

    async def _cmd_bienvenida_toggle(ctx, enabled: bool):
        """Comando genérico para activar/desactivar saludos de bienvenida."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("admin_permission", "❌ Solo administradores pueden modificar los saludos de bienvenida."))
            return

        greeting_cfg = _discord_cfg.get("member_greeting", {})
        greeting_cfg["enabled"] = enabled

        greeting_messages_cfg = PERSONALIDAD.get("discord", {}).get("greeting_messages", {})
        if enabled:
            mensaje = greeting_messages_cfg.get("bienvenida_activados", "✅ Saludos de bienvenida activados en este servidor.")
        else:
            mensaje = greeting_messages_cfg.get("bienvenida_desactivados", "✅ Saludos de bienvenida desactivados en este servidor.")

        logger.info(f"{ctx.author.name} {'activó' if enabled else 'desactivó'} los saludos de bienvenida en {ctx.guild.name}")
        await ctx.send(mensaje)

    @bot.command(name=bienvenida_name)
    async def cmd_bienvenida_enable(ctx):
        await _cmd_bienvenida_toggle(ctx, True)

    @bot.command(name=nobienvenida_name)
    async def cmd_bienvenida_disable(ctx):
        await _cmd_bienvenida_toggle(ctx, False)

    # --- INSULTO ---

    async def _cmd_insulta(ctx, obj=""):
        target = obj if obj else ctx.author.mention
        if "@everyone" in target or "@here" in target:
            prompt = _insult_cfg.get("prompt_everyone", "Lanza un insulto breve a TODO EL MUNDO, maximo 1 frase")
        else:
            prompt = _insult_cfg.get("prompt_target", "Lanza un insulto breve a una persona especifica, maximo 1 frase")
        res = await asyncio.to_thread(pensar, prompt, logger=logger)
        await ctx.send(f"{target} {res}")

    bot.command(name=insulta_name)(_cmd_insulta)

    # --- TEST ---

    @bot.command(name="test")
    async def cmd_test(ctx):
        """Comando de prueba para verificar si funciona."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        logger.info(f"Comando test ejecutado por {ctx.author.name}")
        await ctx.send(role_cfg.get("test_command", "✅ Comando test funciona!"))

    # --- CONTROL DE ROLES ---

    async def _cmd_role_toggle(ctx, role_name: str, enabled: bool):
        """Comando genérico para activar/desactivar roles dinámicamente."""
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        if not is_admin(ctx):
            await ctx.send(role_cfg.get("role_no_permission", "❌ Solo administradores pueden modificar los roles."))
            return

        valid_roles = ["vigia_noticias", "buscador_tesoros", "trilero", "buscar_anillo", "banquero"]
        if role_name not in valid_roles:
            await ctx.send(role_cfg.get("role_not_found", "❌ Rol '{role}' no válido.").format(role=role_name))
            return

        env_var_name = f"{role_name.upper()}_ENABLED"
        env_value = "true" if enabled else "false"
        os.environ[env_var_name] = env_value

        if "roles" not in agent_config:
            agent_config["roles"] = {}
        if role_name not in agent_config["roles"]:
            agent_config["roles"][role_name] = {}
        agent_config["roles"][role_name]["enabled"] = enabled

        # Registrar comandos del rol si se está activando
        if enabled:
            from discord_role_loader import register_single_role
            await register_single_role(bot, role_name, agent_config, PERSONALIDAD)

        if enabled:
            await ctx.send(role_cfg.get("role_activated", "✅ Rol '{role}' activado correctamente.").format(role=role_name))
            logger.info(f"{ctx.author.name} activó el rol {role_name} en {ctx.guild.name}")
        else:
            await ctx.send(role_cfg.get("role_deactivated", "✅ Rol '{role}' desactivado correctamente.").format(role=role_name))
            logger.info(f"{ctx.author.name} desactivó el rol {role_name} en {ctx.guild.name}")

    @bot.command(name=role_cmd_name)
    async def cmd_role_control(ctx, role_name: str = "", action: str = ""):
        """Control de roles. Uso: !role<nombre> <rol> <on/off>"""
        if not role_name:
            await ctx.send(f"❌ Debes especificar un rol. Ejemplo: !{role_cmd_name} vigia_noticias on")
            return
        if not action:
            await ctx.send(f"❌ Debes especificar una acción. Ejemplo: !{role_cmd_name} vigia_noticias on")
            return

        action_lower = action.lower()
        if action_lower in ["on", "true", "1", "activar", "enable"]:
            await _cmd_role_toggle(ctx, role_name, True)
        elif action_lower in ["off", "false", "0", "desactivar", "disable"]:
            await _cmd_role_toggle(ctx, role_name, False)
        else:
            await ctx.send("❌ Acción no válida. Usa: on/off, true/false, 1/0, activar/desactivar")

    # --- AYUDA ---

    @bot.command(name=ayuda_name)
    async def cmd_ayuda(ctx):
        """Muestra todos los comandos activos para este agente."""
        if is_duplicate_command(ctx, "ayuda"):
            return

        roles_config = AGENT_CFG.get("roles", {})
        ayuda_msg = f"🤖 **Comandos disponibles para {bot.user.name}** 🤖\n\n"

        # Comandos de control
        ayuda_msg += "🎛️ **COMANDOS DE CONTROL**\n"
        ayuda_msg += f"• `!{saluda_name}` - Activar saludos de presencia (DM)\n"
        ayuda_msg += f"• `!{nosaludes_name}` - Desactivar saludos de presencia\n"
        ayuda_msg += f"• `!{bienvenida_name}` - Activar bienvenida de nuevos miembros\n"
        ayuda_msg += f"• `!{nobienvenida_name}` - Desactivar bienvenida de nuevos miembros\n"
        ayuda_msg += f"• `!{insulta_name}` - Lanzar insulto orco\n"
        ayuda_msg += f"• `!{role_cmd_name} <rol> <on/off>` - Activar/desactivar roles dinámicamente\n"
        ayuda_msg += f"• `!{ayuda_name}` - Mostrar esta ayuda\n\n"

        # Comandos disponibles por rol
        ayuda_msg += "🎭 **COMANDOS DISPONIBLES POR ROL**\n"

        if is_role_enabled_check("vigia_noticias", agent_config):
            interval = roles_config.get("vigia_noticias", {}).get("interval_hours", 1)
            ayuda_msg += f"📡 **Vigía de Noticias** - Alertas inteligentes (cada {interval}h)\n"
            ayuda_msg += " - **IMPORTANTE:** Solo puedes tener UN TIPO de suscripción activa\n"
            ayuda_msg += "  - **Ayuda:** `!vigiaayuda` (usuarios) | `!vigiacanalayuda` (admins)\n"
            ayuda_msg += "  - **Ejemplo:** `!vigia general internacional` → Noticias internacionales evaluadas con IA, con la opinión del agente personalizado\n"

        if is_role_enabled_check("buscador_tesoros", agent_config):
            interval = roles_config.get("buscador_tesoros", {}).get("interval_hours", 1)
            ayuda_msg += f"💎 **Buscador de Tesoros** - `!buscartesoros` / `!nobuscartesoros` | `!tesorosfrecuencia <h>` (cada {interval}h) | `!poe2ayuda` para ayuda específica\n"

        if is_role_enabled_check("trilero", agent_config):
            interval = roles_config.get("trilero", {}).get("interval_hours", 12)
            ayuda_msg += f"🎭 **Trilero** - `!trilero ayuda` para comandos de limosna (cada {interval}h)\n"

        if is_role_enabled_check("buscar_anillo", agent_config):
            interval = roles_config.get("buscar_anillo", {}).get("interval_hours", 24)
            ayuda_msg += f"👁️ **Buscar Anillo** - `!acusaranillo` <@usuario> | `!anillofrecuencia <h>` (cada {interval}h)\n"

        if is_role_enabled_check("banquero", agent_config):
            banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
            ayuda_msg += f"{banquero_msgs.get('banquero_help', '💰 **Banquero** - `!banquero saldo` | `!banquero tae <cantidad>` (admins) | `!banquero ayuda` para ayuda completa')}\n"

        music_help_msg = PERSONALIDAD.get("discord", {}).get("role_messages", {}).get("music_help", "🎵 **Música** - `!mc play <canción>` / `!mc queue` | `!mc help` para ayuda completa (siempre disponible)")
        ayuda_msg += f"{music_help_msg}\n\n"

        ayuda_msg += "💬 **DESCRIPCIÓN BÁSICA DE CONVERSACIÓN**\n"
        ayuda_msg += "• Menciona al bot para conversar\n"
        ayuda_msg += "• Responde usando la personalidad del agente\n"
        ayuda_msg += f"• El bot responderá como su personaje ({_bot_display_name})\n\n"

        # Roles activos y desactivados
        ayuda_msg += "🎭 **ROLES ACTIVOS Y DESACTIVADOS**\n"
        role_display = {
            "vigia_noticias": "📡 **Vigía de Noticias** - Alertas de noticias críticas",
            "buscador_tesoros": "💎 **Buscador de Tesoros** - Alertas de oportunidades de compra",
            "trilero": "🎭 **Trilero** - Subrol limosna: peticiones de donaciones y engaños",
            "buscar_anillo": "👁️ **Buscar Anillo** - Acusaciones por el anillo",
            "banquero": "💰 **Banquero** - Gestión económica y TAE diaria",
            "mc": "🎵 **Música** - Siempre disponible (no requiere activación)",
        }

        for role_name_key, role_cfg_val in roles_config.items():
            enabled = is_role_enabled_check(role_name_key, agent_config)
            if role_name_key == "mc":
                status_emoji = "✅"
            else:
                status_emoji = "✅" if enabled else "❌"
            display = role_display.get(role_name_key, f"**{role_name_key.replace('_', ' ').title()}**")
            ayuda_msg += f"• {status_emoji} {display}\n"

        # Importar get_message con fallback
        try:
            from roles.vigia_noticias.vigia_messages import get_message
            confirm_msg = get_message('ayuda_enviada_privado')
        except ImportError:
            confirm_msg = "✅ Te he enviado la ayuda por mensaje privado 📩"

        await send_dm_or_channel(ctx, ayuda_msg, confirm_msg)

    # --- Logging de comandos registrados ---
    logger.info(f"Comandos core registrados: {saluda_name}, {nosaludes_name}, {bienvenida_name}, {nobienvenida_name}, {insulta_name}, {ayuda_name}, {role_cmd_name}, test")
