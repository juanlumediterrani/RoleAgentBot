"""
Commentary role - Mission commentary system.
Generates periodic comments about active missions incorporating memories and personality.
"""

from .commentary import get_commentary_system_prompt, get_commentary_task_prompt, format_commentary_response

__all__ = ['get_commentary_system_prompt', 'get_commentary_task_prompt', 'format_commentary_response']
