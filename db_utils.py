"""
Utilidades para gestión de bases de datos por servidor.
Implementa el esquema: databases/nombredelservidor/basededatos.db
"""

import os
import sqlite3
from pathlib import Path
from agent_logging import get_logger

logger = get_logger('db_utils')

def get_server_db_path(server_name: str, db_name: str) -> Path:
    """
    Genera ruta de base de datos para un servidor específico.
    
    Args:
        server_name: Nombre del servidor (sanitizado)
        db_name: Nombre del archivo de base de datos
    
    Returns:
        Path: Ruta completa a la base de datos
    """
    # Sanitizar nombre del servidor
    server_sanitized = server_name.lower().replace(' ', '_').replace('-', '_')
    server_sanitized = ''.join(c for c in server_sanitized if c.isalnum() or c == '_')
    
    # Directorio base
    base_dir = Path(__file__).parent
    server_dir = base_dir / "databases" / server_sanitized
    
    # Crear directorio si no existe
    server_dir.mkdir(parents=True, exist_ok=True)
    
    return server_dir / db_name

def get_server_db_path_fallback(server_name: str, db_name: str) -> Path:
    """
    Versión con fallback para entornos Docker o permisos restringidos.
    """
    # Intentar ruta local primero
    local_path = get_server_db_path(server_name, db_name)
    
    try:
        # Probar si podemos escribir
        conn = sqlite3.connect(str(local_path))
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS __test_write (id INTEGER)')
        conn.commit()
        cursor.execute('DROP TABLE IF EXISTS __test_write')
        conn.commit()
        conn.close()
        return local_path
    except (PermissionError, OSError) as e:
        logger.warning(f"⚠️ No write access a {local_path}: {e}. Usando fallback en home directory.")
        
        # Fallback en home directory
        server_sanitized = server_name.lower().replace(' ', '_').replace('-', '_')
        server_sanitized = ''.join(c for c in server_sanitized if c.isalnum() or c == '_')
        
        fallback_dir = Path.home() / '.roleagentbot' / 'databases' / server_sanitized
        fallback_dir.mkdir(parents=True, exist_ok=True)
        
        fallback_path = fallback_dir / db_name
        logger.info(f"ℹ️ BD reubicada a {fallback_path}")
        return fallback_path

def get_personality_name():
    """Obtiene nombre de la personalidad desde variable de entorno o configuración."""
    # Primero intentar desde variable de entorno (prioridad en Docker)
    env_personality = os.getenv('PERSONALITY')
    if env_personality:
        return env_personality.lower()
    
    # Sino intentar desde agent_engine
    try:
        from agent_engine import PERSONALIDAD
        return PERSONALIDAD.get("name", "agent").lower()
    except:
        return "agent"
