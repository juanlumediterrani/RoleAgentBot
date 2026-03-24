"""
Base Role Module
Base class for all trickster subroles.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BaseRole(ABC):
    """Base class for all trickster subroles."""
    
    def __init__(self, name: str, description: str):
        """Initialize the base role."""
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"{__name__}.{name}")
    
    @abstractmethod
    def execute_task(self, task_data: Dict[str, Any]) -> str:
        """Execute the main task for this role."""
        pass
    
    @abstractmethod
    def get_help(self) -> str:
        """Get help information for this role."""
        pass
    
    def get_info(self) -> Dict[str, Any]:
        """Get role information."""
        return {
            'name': self.name,
            'description': self.description,
            'type': self.__class__.__name__
        }
    
    def validate_task_data(self, task_data: Dict[str, Any]) -> bool:
        """Validate task data for this role."""
        return True  # Default implementation
    
    def log_action(self, action: str, details: Optional[str] = None):
        """Log an action for this role."""
        message = f"[{self.name}] {action}"
        if details:
            message += f": {details}"
        self.logger.info(message)
    
    def format_response(self, message: str) -> str:
        """Format a response message."""
        return message  # Default implementation, can be overridden
