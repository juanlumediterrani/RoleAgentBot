"""
Fatigue Limit System for LLM Usage Management

This module provides comprehensive fatigue tracking and limit enforcement
for LLM API calls to prevent abuse and manage resource usage effectively.
"""

import datetime
import logging
from typing import Dict, Tuple, Optional, Any
from agent_db import get_fatigue_stats, get_active_server_id, init_fatigue_db

logger = logging.getLogger(__name__)

class FatigueLimitResult:
    """Result of fatigue limit check"""
    def __init__(self, allowed: bool, reason: str = None, reset_time: str = None):
        self.allowed = allowed
        self.reason = reason
        self.reset_time = reset_time

def get_fatigue_limits() -> Dict[str, Any]:
    """Get fatigue limits from configuration"""
    try:
        import json
        import os
        
        _BASE_DIR = os.path.dirname(__file__)
        _AGENT_CONFIG_PATH = os.path.join(_BASE_DIR, "agent_config.json")
        
        with open(_AGENT_CONFIG_PATH, encoding="utf-8") as file_handle:
            config = json.load(file_handle)
        
        return config.get('fatigue_limits', {})
    except Exception as e:
        logger.warning(f"Error loading fatigue limits config: {e}")
        # Return default limits
        return {
            'user': {'daily_max': 50, 'hourly_max': 25, 'burst_max': 10},
            'server': {'daily_max': 500, 'hourly_max': 200, 'burst_max': 100},
            'exemptions': {'admin_users': [], 'critical_tasks': []},
            'behavior': {'strict_mode': False, 'grace_period': 3, 'cooldown_minutes': 15}
        }

def is_exempt_user(user_id: str, call_type: str = None) -> bool:
    """Check if user or call type is exempt from limits"""
    limits = get_fatigue_limits()
    
    # Check admin exemptions
    admin_users = limits.get('exemptions', {}).get('admin_users', [])
    if user_id in admin_users:
        return True
    
    # Check critical task exemptions
    critical_tasks = limits.get('exemptions', {}).get('critical_tasks', [])
    if call_type in critical_tasks:
        return True
    
    return False

def check_fatigue_limit(user_id: str, user_name: str = None, call_type: str = "default") -> FatigueLimitResult:
    """
    Check if user/server has exceeded fatigue limits
    
    Args:
        user_id: User ID (or server_id for server checks)
        user_name: User name (optional)
        call_type: Type of LLM call for exemption checks
        
    Returns:
        FatigueLimitResult with allowed status and details
    """
    try:
        # Check exemptions first
        if is_exempt_user(user_id, call_type):
            return FatigueLimitResult(allowed=True, reason="exempt")
        
        server_id=get_active_server_id()
        if not server_id:
            logger.warning("No active server found for fatigue check")
            return FatigueLimitResult(allowed=True, reason="no_server")
        
        # Get current stats
        stats = get_fatigue_stats(server_id, user_id)
        if not stats:
            # New user, always allowed
            return FatigueLimitResult(allowed=True, reason="new_user")
        
        limits = get_fatigue_limits()
        
        # Determine if this is a server or user check
        is_server = user_id.startswith("server_")
        limit_config = limits.get('server' if is_server else 'user', {})
        
        # Get current usage
        daily = stats.get('daily_requests', 0)
        hourly = stats.get('hourly_requests', 0)
        burst = stats.get('burst_requests', 0)
        
        # Get limits
        daily_limit = limit_config.get('daily_max', 50)
        hourly_limit = limit_config.get('hourly_max', 10)
        burst_limit = limit_config.get('burst_max', 5)
        
        # Check grace period
        grace_period = limits.get('behavior', {}).get('grace_period', 3)
        if daily <= grace_period:
            return FatigueLimitResult(allowed=True, reason="grace_period")
        
        # Check limits in order: burst -> hourly -> daily
        if burst >= burst_limit:
            return FatigueLimitResult(
                allowed=False,
                reason=f"burst_limit_exceeded",
                reset_time="5 minutes"
            )
        
        if hourly >= hourly_limit:
            return FatigueLimitResult(
                allowed=False,
                reason=f"hourly_limit_exceeded",
                reset_time="next hour"
            )
        
        if daily >= daily_limit:
            return FatigueLimitResult(
                allowed=False,
                reason=f"daily_limit_exceeded",
                reset_time="00:00 UTC"
            )
        
        # All checks passed
        return FatigueLimitResult(allowed=True, reason="within_limits")
        
    except Exception as e:
        logger.error(f"Error checking fatigue limit: {e}")
        # On error, allow the call to avoid breaking functionality
        return FatigueLimitResult(allowed=True, reason="error")

def get_hourly_usage(personality_name: str, user_id: str = None) -> int:
    """Get hourly usage from database."""
    try:
        server_id=get_active_server_id()
        if not server_id:
            return 0

        if user_id:
            # Get specific user stats
            stats = get_fatigue_stats(server_id, user_id)
            return stats.get('hourly_requests', 0)
        else:
            # Get server total stats
            server_user_id = f"server_{server_id}"
            stats = get_fatigue_stats(server_id, server_user_id)
            return stats.get('hourly_requests', 0)
    except Exception as e:
        logger.warning(f"Error getting hourly usage: {e}")
        return 0

def get_burst_usage(personality_name: str, user_id: str = None) -> int:
    """Get burst usage (last 5 minutes) from database."""
    try:
        server_id=get_active_server_id()
        if not server_id:
            return 0

        if user_id:
            # Get specific user stats
            stats = get_fatigue_stats(server_id, user_id)
            return stats.get('burst_requests', 0)
        else:
            # Get server total stats
            server_user_id = f"server_{server_id}"
            stats = get_fatigue_stats(server_id, server_user_id)
            return stats.get('burst_requests', 0)
    except Exception as e:
        logger.warning(f"Error getting burst usage: {e}")
        return 0

def format_limit_exceeded_message(result: FatigueLimitResult, user_name: str = None) -> str:
    """Format user-friendly message for limit exceeded"""
    messages = {
        "burst_limit_exceeded": f"⚡ **Burst limit reached** ({user_name or 'User'}).\n\nToo many rapid requests. Wait **{result.reset_time}** to continue.",
        "hourly_limit_exceeded": f"⏰ **Hourly limit reached** ({user_name or 'User'}).\n\nYou've reached your hourly request limit. You can continue in **{result.reset_time}**.",
        "daily_limit_exceeded": f"📅 **Daily limit reached** ({user_name or 'User'}).\n\nYou've reached your daily request limit. Counter resets at **{result.reset_time}**."
    }
    
    base_message = messages.get(result.reason, "❌ **Limit reached**. Please wait before continuing.")
    
    # Add helpful tips
    tips = "\n\n💡 **Tips:**\n• Use specific commands instead of general conversation\n• Wait for the counter to reset\n• Contact an admin if you need more requests"
    
    return base_message + tips

def get_usage_summary(user_id: str, user_name: str = None) -> Dict[str, Any]:
    """Get comprehensive usage summary for a user"""
    try:
        server_id=get_active_server_id()
        if not server_id:
            return {}
        
        stats = get_fatigue_stats(server_id, user_id)
        if not stats:
            return {
                'user_id': user_id,
                'user_name': user_name,
                'daily_requests': 0,
                'hourly_requests': 0,
                'burst_requests': 0,
                'total_requests': 0,
                'last_request_date': None
            }
        
        return {
            'user_id': stats.get('user_id', user_id),
            'user_name': stats.get('user_name', user_name),
            'daily_requests': stats.get('daily_requests', 0),
            'hourly_requests': stats.get('hourly_requests', 0),
            'burst_requests': stats.get('burst_requests', 0),
            'total_requests': stats.get('total_requests', 0),
            'last_request_date': stats.get('last_request_date'),
            'last_hour_timestamp': stats.get('last_hour_timestamp'),
            'last_burst_timestamp': stats.get('last_burst_timestamp')
        }
        
    except Exception as e:
        logger.error(f"Error getting usage summary: {e}")
        return {}
