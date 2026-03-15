"""
Behavior management system for server-specific behavior settings.
Handles greetings, welcome, commentary, and other behavior states with persistence.
"""

from .db_behavior import get_behavior_db_instance

__all__ = ['get_behavior_db_instance']
