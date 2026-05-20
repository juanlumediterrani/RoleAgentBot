"""
Loader de catalogos de Arena desde la personalidad del servidor.

Los catalogos (armas, matrices de ventajas, personalidades de combate)
viven en personalities/<nombre>/<idioma>/arena_catalog.json y se copian
a databases/<server_id>/<nombre>/arena_catalog.json durante la inicializacion.
"""

import json
import os
from typing import Dict, List

from agent_logging import get_logger

logger = get_logger("arena_catalogs")


def _get_arena_catalog_path(server_id: str) -> str | None:
    """Resuelve la ruta a arena_catalog.json para un servidor dado."""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        # Leer la personalidad activa del servidor
        server_config_path = os.path.join(base_dir, "databases", server_id, "server_config.json")
        personality_name = None
        if os.path.exists(server_config_path):
            with open(server_config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            personality_name = cfg.get("active_personality")

        if not personality_name:
            # Fallback a agent_config.json
            agent_config_path = os.path.join(base_dir, "agent_config.json")
            if os.path.exists(agent_config_path):
                with open(agent_config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
                personality_name = cfg.get("default_personality", "rab")

        server_personality_dir = os.path.join(base_dir, "databases", server_id, personality_name)
        catalog_path = os.path.join(server_personality_dir, "arena_catalog.json")

        if os.path.exists(catalog_path):
            return catalog_path

        # Fallback: buscar en el directorio global de personalidades
        global_config_path = os.path.join(base_dir, "agent_config.json")
        language = "es-ES"
        if os.path.exists(global_config_path):
            with open(global_config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            language = cfg.get("default_language", "es-ES")

        # Intentar con el server_config language si existe
        if os.path.exists(server_config_path):
            with open(server_config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            lang = cfg.get("language")
            if lang:
                language = lang

        global_catalog_path = os.path.join(base_dir, "personalities", personality_name, language, "arena_catalog.json")
        if os.path.exists(global_catalog_path):
            return global_catalog_path

        # Ultimo fallback: es-ES siempre
        global_catalog_path_es = os.path.join(base_dir, "personalities", personality_name, "es-ES", "arena_catalog.json")
        if os.path.exists(global_catalog_path_es):
            return global_catalog_path_es

        logger.warning(f"No se encontro arena_catalog.json para server {server_id}, personality {personality_name}")
        return None

    except Exception as e:
        logger.error(f"Error resolviendo catalogo de Arena: {e}")
        return None


def _load_catalog(server_id: str) -> dict:
    """Carga y cachea el catalogo de Arena para un servidor."""
    path = _get_arena_catalog_path(server_id)
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando arena_catalog.json desde {path}: {e}")
        return {}


# --- Cache simple por server_id ---
_catalog_cache: Dict[str, dict] = {}


def _get_cached_catalog(server_id: str) -> dict:
    """Obtiene el catalogo cacheado o lo carga."""
    if server_id not in _catalog_cache:
        _catalog_cache[server_id] = _load_catalog(server_id)
    return _catalog_cache.get(server_id, {})


def invalidate_catalog_cache(server_id: str) -> None:
    """Invalida la cache del catalogo para un servidor (ej. tras cambio de personalidad)."""
    _catalog_cache.pop(server_id, None)


# --- API publica ---

def get_weapons(server_id: str) -> List[dict]:
    """Devuelve la lista de armas para el servidor dado."""
    return _get_cached_catalog(server_id).get("weapons", [])


def get_weapon_by_id(server_id: str, weapon_id: str) -> dict | None:
    """Devuelve el dict de un arma por su ID."""
    for weapon in get_weapons(server_id):
        if weapon["id"] == weapon_id:
            return weapon
    return None


def get_advantage_matrix(server_id: str) -> Dict[str, Dict[str, str]]:
    """Devuelve la matriz de ventajas para el servidor dado."""
    return _get_cached_catalog(server_id).get("advantage_matrix", {})


def get_relation_between(server_id: str, weapon_a_id: str, weapon_b_id: str) -> str:
    """Devuelve la relacion entre dos armas. Default '=' si no existe."""
    matrix = get_advantage_matrix(server_id)
    return matrix.get(weapon_a_id, {}).get(weapon_b_id, "=")


def describe_relation(relation: str) -> str:
    """Convierte un codigo de relacion en descripcion legible para el prompt del LLM."""
    mapping = {
        "++": "ventaja clara en alcance/velocidad/fuerza",
        "+": "ventaja leve en alcance/velocidad/fuerza",
        "=": "parejo - ninguna ventaja significativa",
        "-": "desventaja leve en alcance/velocidad/fuerza",
        "--": "desventaja clara en alcance/velocidad/fuerza",
    }
    return mapping.get(relation, "parejo")


def get_unlocked_weapons(server_id: str, xp: float) -> List[dict]:
    """Devuelve las armas desbloqueadas para un nivel de XP dado."""
    return [w for w in get_weapons(server_id) if xp >= w.get("unlock_xp", 0.0)]


def get_default_weapon(server_id: str) -> dict | None:
    """Devuelve el arma inicial (unlock_xp == 0)."""
    for weapon in get_weapons(server_id):
        if weapon.get("unlock_xp", 0.0) == 0.0:
            return weapon
    return None


def get_fighter_personalities(server_id: str) -> List[dict]:
    """Devuelve la lista de personalidades de combate para el servidor dado."""
    return _get_cached_catalog(server_id).get("fighter_personalities", [])


def get_fighter_personality_by_id(server_id: str, personality_id: str) -> dict | None:
    """Devuelve el dict de una personalidad de combate por su ID."""
    for p in get_fighter_personalities(server_id):
        if p["id"] == personality_id:
            return p
    return None


def get_fighter_personality_by_name(server_id: str, name: str) -> dict | None:
    """Devuelve el dict de una personalidad de combate por su nombre (case-insensitive)."""
    name_upper = name.upper()
    for p in get_fighter_personalities(server_id):
        if p["name"] == name_upper:
            return p
    return None


def build_personality_prompt_block(server_id: str) -> str:
    """Construye el bloque de prompt para que el LLM escoja una personalidad de combate."""
    personalities = get_fighter_personalities(server_id)
    if not personalities:
        return ""
    lines = [
        "Ademas del resumen de relacion habitual, asigna a este usuario una de las siguientes personalidades de combate para el modulo Arena:",
        ""
    ]
    for p in personalities:
        lines.append(f"- {p['name']}: {p['desc']}")
    lines.extend([
        "",
        "Elige la que mejor encaje con el comportamiento observado del usuario. Devuelve el resultado en el formato exacto:",
        "[FIGHTER_PERSONALITY: <NOMBRE_MAYUSCULAS>]",
        "Si el modulo Arena no esta activo o no tienes suficiente informacion, devuelve [FIGHTER_PERSONALITY: NONE]."
    ])
    return "\n".join(lines)


def parse_fighter_personality(text: str) -> str | None:
    """Parsea el output del LLM buscando [FIGHTER_PERSONALITY: X]."""
    import re
    match = re.search(r"\[FIGHTER_PERSONALITY:\s*([^\]]+)\]", text, re.IGNORECASE)
    if match:
        result = match.group(1).strip().upper()
        if result == "NONE":
            return None
        return result
    return None


def get_advantage_description_for_prompt(server_id: str, weapon_a_id: str, weapon_b_id: str) -> str:
    """Genera la linea de descripcion de ventaja para incluir en el prompt del LLM."""
    relation = get_relation_between(server_id, weapon_a_id, weapon_b_id)
    weapon_a = get_weapon_by_id(server_id, weapon_a_id)
    weapon_b = get_weapon_by_id(server_id, weapon_b_id)
    if not weapon_a or not weapon_b:
        return ""
    desc = describe_relation(relation)
    return (
        f"{weapon_a['name']} vs {weapon_b['name']}: {relation} ({desc}). "
        f"Esto significa que, en la narrativa, {weapon_a['name']} {desc} contra {weapon_b['name']}."
    )


def format_matrix_for_prompt(server_id: str) -> str:
    """Formatea la matriz completa como texto para el prompt del LLM."""
    weapons = get_weapons(server_id)
    matrix = get_advantage_matrix(server_id)
    if not weapons or not matrix:
        return ""
    lines = ["Matriz de ventajas de armas:"]
    for wa in weapons:
        row_parts = []
        for wb in weapons:
            rel = matrix.get(wa["id"], {}).get(wb["id"], "=")
            row_parts.append(f"{wb['name']}={rel}")
        lines.append(f"  {wa['name']}: vs " + ", ".join(row_parts))
    return "\n".join(lines)
