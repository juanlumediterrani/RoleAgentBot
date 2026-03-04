"""
Carga dinámica de comandos de Discord para roles.
Cada rol expone una función register_*_commands(bot, personality) en su archivo *_discord.py.
"""

import importlib
import os
from agent_logging import get_logger
from discord_utils import is_role_enabled_check

logger = get_logger('role_loader')

# Registro de módulos de roles y sus funciones de registro
ROLE_REGISTRY = {
    "vigia_noticias": ("roles.vigia_noticias.vigia_discord", "register_vigia_commands"),
    "buscador_tesoros": ("roles.buscador_tesoros.poe2_discord", "register_poe2_commands"),
    "trilero": ("roles.trilero.trilero_discord", "register_trilero_commands"),
    "buscar_anillo": ("roles.buscar_anillo.anillo_discord", "register_anillo_commands"),
    "banquero": ("roles.banquero.banquero_discord", "register_banquero_commands"),
}

# MC se registra siempre (no depende de enabled en el mismo sentido)
MC_REGISTRY = ("roles.mc.mc_discord", "register_mc_commands")


def _try_register_role(bot, module_path, func_name, personality, agent_config):
    """Intenta importar y registrar un rol. Retorna True si tuvo éxito."""
    try:
        module = importlib.import_module(module_path)
        register_func = getattr(module, func_name)
        register_func(bot, personality, agent_config)
        return True
    except ImportError as e:
        logger.warning(f"Módulo {module_path} no disponible: {e}")
        return False
    except Exception as e:
        logger.error(f"Error registrando {module_path}: {e}")
        return False


async def register_all_role_commands(bot, agent_config, personality):
    """Registra comandos para todos los roles activados en agent_config.json."""
    logger.info("Verificando roles activados para registro de comandos")

    # MC siempre se registra primero
    mc_module, mc_func = MC_REGISTRY
    if _try_register_role(bot, mc_module, mc_func, personality, agent_config):
        logger.info("🎵 MC registrado correctamente")
    else:
        logger.warning("🎵 MC no disponible")

    # Registrar roles habilitados
    registered = []
    for role_name, (module_path, func_name) in ROLE_REGISTRY.items():
        if is_role_enabled_check(role_name, agent_config):
            logger.info(f"🎭 Rol {role_name} activado, registrando comandos...")
            if _try_register_role(bot, module_path, func_name, personality, agent_config):
                registered.append(role_name)
            else:
                logger.warning(f"🎭 Rol {role_name} activado pero no se pudieron registrar comandos")
        else:
            logger.info(f"💤 Rol {role_name} desactivado")

    logger.info(f"Registro completado: {len(registered)} roles activos — {', '.join(registered) if registered else 'ninguno'}")


async def register_single_role(bot, role_name, agent_config, personality):
    """Registra comandos de un rol específico (para activación dinámica)."""
    if role_name not in ROLE_REGISTRY:
        logger.warning(f"Rol {role_name} no tiene registro de comandos Discord")
        return False

    module_path, func_name = ROLE_REGISTRY[role_name]
    if _try_register_role(bot, module_path, func_name, personality, agent_config):
        logger.info(f"🎭 Comandos de {role_name} registrados dinámicamente")
        return True
    return False
