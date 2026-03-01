#!/usr/bin/env python3
"""
RoleAgentBot - Orquestador principal
Arranca el bot de Discord principal y lanza cada rol como subproceso
según el intervalo configurado en agent_config.json.
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from agent_logging import get_logger

logger = get_logger('run')

# ── Rutas ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "agent_config.json"
PYTHON     = sys.executable   # mismo intérprete del venv activo

ACTIVE_SERVER_FILE = BASE_DIR / ".active_server"

# ── Configuración ─────────────────────────────────────────────────────────────

def cargar_config() -> dict:
    if not CONFIG_FILE.exists():
        logger.error(f"[run] ❌ No se encontró {CONFIG_FILE}")
        sys.exit(1)
    with CONFIG_FILE.open(encoding="utf-8") as f:
        config = json.load(f)
        logger.info(f"[run] 📋 Configuración cargada exitosamente")
        return config

# ── Lanzador de subprocesos ───────────────────────────────────────────────────

async def lanzar_rol(nombre: str, script_rel: str):
    """Ejecuta el script del rol como subproceso y espera a que termine."""
    script = BASE_DIR / script_rel
    if not script.exists():
        logger.warning(f"[run] ⚠️  Script no encontrado para '{nombre}': {script}")
        return

    logger.info(f"[run] 🚀 Ejecutando rol '{nombre}' → {script.name}")
    try:
        env = os.environ.copy()
        env["ROLE_AGENT_PROCESS"] = "1"

        # Propagar servidor activo al subproceso si existe
        try:
            if ACTIVE_SERVER_FILE.exists():
                active_server = ACTIVE_SERVER_FILE.read_text(encoding="utf-8").strip()
                if active_server:
                    env["ACTIVE_SERVER_NAME"] = active_server
        except Exception:
            pass

        proc = await asyncio.create_subprocess_exec(
            PYTHON, str(script),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
            env=env,
        )
        stdout, _ = await proc.communicate()
        salida = stdout.decode(errors="replace").strip()
        if salida:
            for linea in salida.splitlines():
                # Eliminar duplicación de fecha para cualquier línea que tenga formato de timestamp
                import re
                # Patrón para detectar y eliminar fecha al inicio
                match = re.match(r'^\s*\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}\s+(.+)$', linea.strip())
                if match:
                    # Tiene fecha - eliminarla
                    linea_limpia = match.group(1)
                    logger.info(f"  [{nombre}] {linea_limpia}")
                else:
                    # No tiene fecha - mostrarla tal cual
                    logger.info(f"  [{nombre}] {linea.strip()}")
        codigo = proc.returncode
        estado = "✅" if codigo == 0 else f"⚠️  (código {codigo})"
        logger.info(f"[run] {estado} Rol '{nombre}' finalizado")
    except Exception as e:
        logger.error(f"[run] ❌ Error lanzando '{nombre}': {e}")

# ── Planificador de roles ─────────────────────────────────────────────────────

async def planificador(config: dict):
    """
    Bucle principal que lanza cada rol activo según su intervalo.
    Ejecuta todos los roles habilitados al inicio, luego respeta el intervalo.
    """
    roles_cfg = config.get("roles", {})
    logger.info(f"[run] 📋 Iniciando planificador con {len(roles_cfg)} roles configurados")

    # Estado: próxima ejecución de cada rol
    proxima: dict[str, datetime] = {}
    ahora = datetime.now()

    for nombre, cfg in roles_cfg.items():
        # Verificar si el rol está activado (prioridad a ACTIVE_ROLES, luego variables individuales)
        active_roles = os.getenv("ACTIVE_ROLES", "").split(",")
        active_roles = [r.strip() for r in active_roles if r.strip()]
        
        if active_roles:  # Si ACTIVE_ROLES está definido, usarlo
            enabled = nombre in active_roles
            logger.info(f"[run] 🔍 ACTIVE_ROLES='{os.getenv('ACTIVE_ROLES', '')}' → '{nombre}' {'✅' if enabled else '❌'}")
        else:  # Sistema antiguo: variables de entorno individuales
            env_enabled = os.getenv(f"{nombre.upper()}_ENABLED", "").lower()
            if env_enabled:
                enabled = env_enabled == "true"
                logger.info(f"[run] 🔍 {nombre.upper()}_ENABLED='{env_enabled}' → '{nombre}' {'✅' if enabled else '❌'}")
            else:
                enabled = cfg.get("enabled", False)
                logger.info(f"[run] 🔍 Config enabled={enabled} → '{nombre}' {'✅' if enabled else '❌'}")
            
        if enabled:
            # Primera ejecución inmediata al arrancar
            proxima[nombre] = ahora
            logger.info(f"[run] 📋 Rol '{nombre}' activado — cada {cfg['interval_hours']}h")
        else:
            logger.info(f"[run] 💤 Rol '{nombre}' desactivado")

    if not proxima:
        logger.info("[run] ℹ️  Ningún rol activo. Solo corre el bot principal.")

    # Esperar a que el bot principal publique el servidor activo, para que los roles
    # escriban en databases/<servidor>/... y logs/<servidor>/...
    if proxima:
        for _ in range(60):  # ~60s
            if ACTIVE_SERVER_FILE.exists() and ACTIVE_SERVER_FILE.stat().st_size > 0:
                break
            await asyncio.sleep(1)

    while True:
        ahora = datetime.now()
        pendientes = [
            nombre for nombre, t in proxima.items() if ahora >= t
        ]

        # Lanzar roles pendientes en paralelo
        if pendientes:
            await asyncio.gather(*[
                lanzar_rol(nombre, roles_cfg[nombre]["script"])
                for nombre in pendientes
            ])
            # Reprogramar tras la ejecución
            for nombre in pendientes:
                horas = roles_cfg[nombre]["interval_hours"]
                proxima[nombre] = datetime.now() + timedelta(hours=horas)
                logger.info(f"[run] ⏳ '{nombre}' próxima ejecución: {proxima[nombre]:%H:%M:%S}")

        await asyncio.sleep(30)   # revisamos cada 30 s

# ── Bot principal de Discord ──────────────────────────────────────────────────

async def bot_discord():
    """
    Mantiene el bot principal (agent_discord.py) vivo como subproceso.
    Si muere, lo relanza automáticamente tras 10 s.
    Solo se usa cuando platform == "discord".
    """
    script = BASE_DIR / "agent_discord.py"
    while True:
        logger.info("[run] 🤖 Arrancando bot principal de Discord…")
        proc = await asyncio.create_subprocess_exec(
            PYTHON, str(script),
            cwd=str(BASE_DIR),
        )
        codigo = await proc.wait()
        if codigo == 0:
            logger.info("[run] 👋 Bot principal terminó limpiamente.")
            break
        logger.warning(f"[run] ⚠️  Bot principal terminó con código {codigo}. Relanzando en 10 s…")
        await asyncio.sleep(10)

# ── Punto de entrada ──────────────────────────────────────────────────────────

async def main():
    config   = cargar_config()
    platform = config.get("platform", "discord")

    logger.info(f"[run] 🌐 Plataforma: {platform}")
    logger.info(f"[run] 📋 Configuración cargada desde: {CONFIG_FILE}")
    logger.info(f"[run] 🤖 Directorio base: {BASE_DIR}")

    tareas = []

    if platform == "discord":
        tareas.append(bot_discord())
        tareas.append(planificador(config))
    elif platform == "telegram":
        # TODO: añadir bot_telegram() cuando esté implementado
        logger.info("[run] ℹ️  Telegram seleccionado — bot principal pendiente de implementar")
    else:
        logger.error(f"[run] ❌ Plataforma desconocida: {platform}")
        sys.exit(1)

    await asyncio.gather(*tareas)

if __name__ == "__main__":
    try:
        logger.info("[run] 🚀 Iniciando RoleAgentBot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n[run] 🛑 Detenido por el usuario.")
