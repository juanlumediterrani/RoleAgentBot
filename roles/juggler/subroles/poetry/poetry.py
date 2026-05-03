"""
Poetry Subrole for Juggler
Allows users to request personalized poems dedicated to other users.
"""

from agent_logging import get_logger

logger = get_logger('juggler_poetry')

# Poetry subrole configuration
POETRY_SUBROLE_NAME = "poetry"
POETRY_MAX_DEDICATION_LENGTH = 150
POETRY_CONFIRMATION_TIMEOUT = 300  # 5 minutes in seconds
