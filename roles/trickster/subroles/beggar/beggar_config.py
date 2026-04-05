"""
Beggar Subrole Configuration Manager
Centralized configuration management using roles.db/roles_config
"""

import json
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from agent_logging import get_logger
from agent_roles_db import get_roles_db_instance
from agent_engine import PERSONALITY

logger = get_logger('beggar_config')


class BeggarConfig:
    """Centralized beggar configuration manager."""
    
    def __init__(self, server_id: str):
        self.server_id = server_id
        self.roles_db = get_roles_db_instance(server_id)
        self.roles_db.migrate_legacy_beggar_data(server_id)
        self._reasons_cache = None
    
    def get_default_reasons(self) -> List[str]:
        """Get reasons from prompts.json dynamically."""
        if self._reasons_cache is None:
            try:
                # Look in the correct location: roles -> trickster -> subroles -> beggar -> reasons
                roles_config = PERSONALITY.get('roles', {})
                trickster_config = roles_config.get('trickster', {})
                beggar_subrole = trickster_config.get('subroles', {}).get('beggar', {})
                self._reasons_cache = beggar_subrole.get('reasons', [])
                
                if not self._reasons_cache:
                    logger.warning("No reasons found in prompts.json for beggar")
                    self._reasons_cache = ["default reason"]
                    
            except Exception as e:
                logger.error(f"Error loading reasons from prompts.json: {e}")
                self._reasons_cache = ["default reason"]
        
        return self._reasons_cache
    
    def get_config(self) -> Dict[str, Any]:
        """Get beggar configuration from roles_config."""
        try:
            config = self.roles_db.get_role_config('beggar')
            
            if config and config.get('config_data'):
                config_data = json.loads(config['config_data'])
            else:
                config_data = {}
            
            # Ensure defaults
            return {
                'enabled': config.get('enabled', False),
                'frequency_hours': config_data.get('frequency_hours', 24),
                'current_reason': config_data.get('current_reason', ''),
                'reason_started': config_data.get('reason_started', None),
                'last_reason_change': config_data.get('last_reason_change', None),
                'target_channel_id': config_data.get('target_channel_id', None),
                'target_gold': config_data.get('target_gold', 0),
                'auto_channel_selection': config_data.get('auto_channel_selection', True),
                'minigame_enabled': config_data.get('minigame_enabled', True),
                'relationship_improvements': config_data.get('relationship_improvements', True)
            }
            
        except Exception as e:
            logger.error(f"Error getting beggar config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            'enabled': False,
            'frequency_hours': 24,
            'current_reason': '',
            'reason_started': None,
            'last_reason_change': None,
            'target_channel_id': None,
            'target_gold': 0,
            'auto_channel_selection': True,
            'minigame_enabled': True,
            'relationship_improvements': True
        }
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """Save beggar configuration to roles_config."""
        try:
            # Extract config data (everything except enabled)
            config_data = {k: v for k, v in config.items() if k != 'enabled'}
            
            success = self.roles_db.save_role_config(
                'beggar', 
                config.get('enabled', False),
                json.dumps(config_data)
            )
            
            if success:
                logger.info(f"Saved beggar config for server {self.server_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error saving beggar config: {e}")
            return False
    
    def is_enabled(self) -> bool:
        """Check if beggar is enabled."""
        config = self.get_config()
        return config.get('enabled', False)
    
    def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable beggar."""
        config = self.get_config()
        config['enabled'] = enabled
        return self.save_config(config)
    
    def get_frequency_hours(self) -> int:
        """Get task execution frequency in hours."""
        config = self.get_config()
        return config.get('frequency_hours', 24)
    
    def set_frequency_hours(self, hours: int) -> bool:
        """Set task execution frequency in hours."""
        config = self.get_config()
        config['frequency_hours'] = max(1, hours)  # Minimum 1 hour
        return self.save_config(config)
    
    def get_current_reason(self) -> str:
        """Get current begging reason."""
        config = self.get_config()
        return config.get('current_reason', '')
    
    def set_current_reason(self, reason: str) -> bool:
        """Set current begging reason and track when it started."""
        config = self.get_config()
        old_reason = config.get('current_reason', '')
        
        config['current_reason'] = reason
        config['reason_started'] = datetime.now().isoformat()
        config['last_reason_change'] = datetime.now().isoformat()
        
        success = self.save_config(config)
        
        if success and old_reason != reason:
            logger.info(f"Beggar reason changed from '{old_reason}' to '{reason}'")
            # Trigger minigame check if reason actually changed
            self._check_reason_change(old_reason, reason)
        
        return success
    
    def should_change_reason(self) -> bool:
        """Check if it's time to change the reason (weekly cycle)."""
        config = self.get_config()
        reason_started = config.get('reason_started')
        
        if not reason_started:
            return True
        
        try:
            started = datetime.fromisoformat(reason_started)
            # Change reason every 7 days
            return datetime.now() >= started + timedelta(days=7)
        except Exception:
            return True
    
    def select_new_reason(self) -> str:
        """Select a new random reason from defaults."""
        current_reason = self.get_current_reason()
        default_reasons = self.get_default_reasons()
        
        logger.info(f"Available reasons: {default_reasons}")
        logger.info(f"Current reason: '{current_reason}'")
        
        # Try to get a different reason
        available_reasons = [r for r in default_reasons if r != current_reason]
        
        logger.info(f"Available reasons after filtering: {available_reasons}")
        
        if not available_reasons:
            # If only current reason exists, pick from all
            available_reasons = default_reasons
            logger.warning("Only one reason available, selecting from all reasons")
        
        new_reason = random.choice(available_reasons)
        logger.info(f"Selected new reason: '{new_reason}'")
        
        self.set_current_reason(new_reason)
        
        return new_reason
    
    def get_target_channel_id(self) -> Optional[str]:
        """Get target channel ID for public messages."""
        config = self.get_config()
        return config.get('target_channel_id')
    
    def set_target_channel_id(self, channel_id: str) -> bool:
        """Set target channel ID for public messages."""
        config = self.get_config()
        config['target_channel_id'] = channel_id
        config['auto_channel_selection'] = False
        return self.save_config(config)
    
    def get_target_gold(self) -> int:
        """Get the current beggar target amount."""
        config = self.get_config()
        return int(config.get('target_gold', 0) or 0)
    
    def set_target_gold(self, amount: int) -> bool:
        """Set the current beggar target amount."""
        config = self.get_config()
        config['target_gold'] = max(0, int(amount))
        return self.save_config(config)
    
    def is_auto_channel_selection(self) -> bool:
        """Check if auto channel selection is enabled."""
        config = self.get_config()
        return config.get('auto_channel_selection', True)
    
    def set_auto_channel_selection(self, enabled: bool) -> bool:
        """Enable or disable auto channel selection."""
        config = self.get_config()
        config['auto_channel_selection'] = enabled
        if enabled:
            config['target_channel_id'] = None
        return self.save_config(config)
    
    def is_minigame_enabled(self) -> bool:
        """Check if minigame on reason change is enabled."""
        config = self.get_config()
        return config.get('minigame_enabled', True)
    
    def set_minigame_enabled(self, enabled: bool) -> bool:
        """Enable or disable minigame on reason change."""
        config = self.get_config()
        config['minigame_enabled'] = enabled
        return self.save_config(config)
    
    def is_relationship_improvements_enabled(self) -> bool:
        """Check if relationship improvements are enabled."""
        config = self.get_config()
        return config.get('relationship_improvements', True)
    
    def set_relationship_improvements_enabled(self, enabled: bool) -> bool:
        """Enable or disable relationship improvements."""
        config = self.get_config()
        config['relationship_improvements'] = enabled
        return self.save_config(config)
    
    def get_reason_status(self) -> Dict[str, Any]:
        """Get detailed status about current reason."""
        config = self.get_config()
        reason_started = config.get('reason_started')
        
        status = {
            'current_reason': config.get('current_reason', ''),
            'reason_started': reason_started,
            'days_active': 0,
            'should_change': self.should_change_reason()
        }
        
        if reason_started:
            try:
                started = datetime.fromisoformat(reason_started)
                status['days_active'] = (datetime.now() - started).days
            except Exception:
                pass
        
        return status
    
    def _check_reason_change(self, old_reason: str, new_reason: str) -> None:
        """Check if we should trigger minigame on reason change."""
        if not self.is_minigame_enabled():
            return
        
        if not old_reason or old_reason == new_reason:
            return
        
        logger.info(f"Reason changed from '{old_reason}' to '{new_reason}', triggering minigame check")
        
        # Import here to avoid circular imports
        try:
            import asyncio
            from .beggar_minigame import BeggarMinigame
            
            # Create background task to avoid blocking
            async def _trigger_minigame_background():
                try:
                    minigame = BeggarMinigame(self.server_id)
                    await minigame.trigger_reason_change_minigame(old_reason, new_reason)
                except Exception as e:
                    logger.error(f"Error in background minigame task: {e}")
            
            # Schedule background task
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(_trigger_minigame_background())
                else:
                    # If no loop running, run it in a new thread
                    import threading
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        new_loop.run_until_complete(_trigger_minigame_background())
                        new_loop.close()
                    
                    thread = threading.Thread(target=run_in_thread)
                    thread.daemon = True
                    thread.start()
            except Exception as e:
                logger.error(f"Error scheduling background minigame task: {e}")
                
        except ImportError:
            logger.warning("Beggar minigame module not available")
        except Exception as e:
            logger.error(f"Error triggering reason change minigame: {e}")


# Global instance cache
_config_instances: Dict[str, BeggarConfig] = {}


def get_beggar_config(server_id: str) -> BeggarConfig:
    """Get beggar configuration instance for a server."""
    if server_id not in _config_instances:
        _config_instances[server_id] = BeggarConfig(server_id)
    return _config_instances[server_id]
