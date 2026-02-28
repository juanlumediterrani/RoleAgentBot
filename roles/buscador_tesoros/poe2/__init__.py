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

__all__ = [
    'DatabaseRolePoe2',
    'get_poe2_db_instance', 
    'Poe2SubroleBot',
    'get_items_reference'
]

__version__ = "1.0.0"
__author__ = "RoleAgentBot"
