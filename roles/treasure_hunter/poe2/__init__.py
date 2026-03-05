"""
Subrol POE2 para el Buscador de Tesoros.

Este módulo contiene toda la funcionalidad del subrol POE2:
- Base de datos para gestión de configuración y objetivos
- Lógica de análisis de precios de Path of Exile 2
- Bot de Discord para notificaciones
- Integración con el API de poe2scout
"""

from .poe2_subrole import (
    DatabaseRolePoe2,
    get_poe2_db_instance,
    Poe2SubroleBot,
    get_items_reference
)
from .poe2_subrole_manager import POE2SubroleManager, get_poe2_manager
from .poe2scout_client import Poe2ScoutClient, ResponseFormatError, APIError

__all__ = [
    'DatabaseRolePoe2',
    'get_poe2_db_instance', 
    'Poe2SubroleBot',
    'get_items_reference',
    'POE2SubroleManager',
    'get_poe2_manager',
    'Poe2ScoutClient',
    'ResponseFormatError',
    'APIError'
]

__version__ = "1.0.0"
__author__ = "RoleAgentBot"
