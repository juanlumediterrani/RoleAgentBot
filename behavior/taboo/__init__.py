"""
Taboo role - Server-specific forbidden words management.
Detects and responds to inappropriate language with customizable warnings.
"""

from .db_taboo import get_taboo_db_instance

__all__ = ['get_taboo_db_instance']
