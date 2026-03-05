"""
Simple premises manager for News Watcher.
Uses personality injection with English fallback.
"""

from agent_logging import get_logger
from agent_engine import PERSONALIDAD

logger = get_logger('premises_manager')

# English fallback premises
DEFAULT_PREMISES = [
    "Outbreak of a war or nuclear escalation",
    "Bankruptcy of a country or large corporation",
    "Global magnitude catastrophe"
]

class PremisesManager:
    """Manages key premises for AI news analysis."""
    
    def __init__(self, server_name: str = "default"):
        self.server_name = server_name
    
    def get_active_premises(self) -> list:
        """Get all active premises from personality or fallback."""
        try:
            premises = PERSONALIDAD.get("watcher_premises", {})
            return premises.get("premises", DEFAULT_PREMISES)
        except Exception:
            return DEFAULT_PREMISES
    
    def build_premises_prompt(self) -> str:
        """Build premises text to inject into the prompt."""
        premises = self.get_active_premises()
        if not premises:
            return ""
        
        premises_text = "A news item is CRITICAL only if it meets ANY of these premises:\n"
        for i, premise in enumerate(premises, 1):
            premises_text += f"{i}. {premise}\n"
        
        return premises_text
    
    def add_premise(self, text: str) -> bool:
        """Add a new premise (Note: This only modifies runtime, not personality file)."""
        try:
            premises = PERSONALIDAD.get("watcher_premises", {})
            current_premises = premises.get("premises", DEFAULT_PREMISES.copy())
            
            if text not in current_premises:
                current_premises.append(text)
                logger.info(f"✅ Premise added: {text}")
                return True
            return False
        except Exception:
            logger.warning("Could not add premise - using fallback")
            return False
    
    def remove_premise(self, text: str) -> bool:
        """Remove a premise (Note: This only modifies runtime, not personality file)."""
        try:
            premises = PERSONALIDAD.get("watcher_premises", {})
            current_premises = premises.get("premises", DEFAULT_PREMISES.copy())
            
            if text in current_premises:
                current_premises.remove(text)
                logger.info(f"✅ Premise removed: {text}")
                return True
            return False
        except Exception:
            logger.warning("Could not remove premise - using fallback")
            return False


# Global instance by server
_premises_instances = {}

def get_premises_manager(server_name: str = "default") -> PremisesManager:
    """Get or create a premises manager instance."""
    if server_name not in _premises_instances:
        _premises_instances[server_name] = PremisesManager(server_name)
    return _premises_instances[server_name]
