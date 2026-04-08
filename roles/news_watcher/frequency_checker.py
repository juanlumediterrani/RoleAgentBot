#!/usr/bin/env python3
"""
News Watcher Frequency Checker

This module handles the periodic checking of news feeds based on
configured frequency settings and sends processed news to subscribers.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import discord

from .news_processor import NewsProcessor
from .db_role_news_watcher import get_news_watcher_db_instance

logger = logging.getLogger(__name__)

class NewsFrequencyChecker:
    """Handles periodic news checking and delivery."""
    
    def __init__(self, bot_instance, server_id: str = "default"):
        self.bot = bot_instance
        self.server_id = server_id
        self.db = get_news_watcher_db_instance(server_id)
        self.processor = NewsProcessor(self.db)
        self.last_check_time: Optional[datetime] = None
        self.check_interval_hours = 4  # Default to 4 hours
        self.is_running = False
        
    async def start_frequency_checker(self):
        """Start the frequency checker loop."""
        if self.is_running:
            logger.warning("Frequency checker is already running")
            return
        
        self.is_running = True
        logger.info("🕐 Starting News Watcher frequency checker")
        
        # Load initial frequency setting
        self._update_frequency_setting()
        
        while self.is_running:
            try:
                await self._check_and_process_news()
                await asyncio.sleep(self.check_interval_hours * 3600)  # Convert to seconds
                
            except Exception as e:
                logger.exception(f"Error in frequency checker loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def stop_frequency_checker(self):
        """Stop the frequency checker loop."""
        self.is_running = False
        logger.info("🛑 Stopping News Watcher frequency checker")
    
    async def _check_and_process_news(self):
        """Check if it's time to process news and do it if needed."""
        now = datetime.now()
        
        # Update frequency setting (in case it changed)
        self._update_frequency_setting()
        
        # Check if we should process news now
        if self.last_check_time is None:
            # First run, process immediately
            should_process = True
        else:
            time_since_last = now - self.last_check_time
            should_process = time_since_last >= timedelta(hours=self.check_interval_hours)
        
        if should_process:
            logger.info(f"📡 Processing news - Interval: {self.check_interval_hours}h")
            await self._process_news_cycle()
            self.last_check_time = now
        else:
            next_check = self.last_check_time + timedelta(hours=self.check_interval_hours)
            time_until_next = next_check - now
            logger.debug(f"⏰ Next news check in {time_until_next}")
    
    async def _process_news_cycle(self):
        """Process one complete news cycle."""
        try:
            # Process all subscriptions and get messages to send
            messages_to_send = await self.processor.process_all_subscriptions(self.server_name)
            
            if not messages_to_send:
                logger.info("📭 No news to send")
                return
            
            logger.info(f"📬 Sending {len(messages_to_send)} news messages")
            
            # Group messages by delivery type for efficient processing
            user_messages = []
            channel_messages = []
            
            for recipient_id, message, delivery_type in messages_to_send:
                if delivery_type == 'user':
                    user_messages.append((recipient_id, message))
                else:  # channel
                    channel_messages.append((recipient_id, message))
            
            # Send user messages via DM
            await self._send_user_messages(user_messages)
            
            # Send channel messages
            await self._send_channel_messages(channel_messages)
            
            logger.info(f"✅ News cycle completed - Sent {len(user_messages)} DMs, {len(channel_messages)} channel messages")
            
        except Exception as e:
            logger.exception(f"Error in news processing cycle: {e}")
    
    async def _send_user_messages(self, user_messages: List[tuple]):
        """Send direct messages to users."""
        for user_id, message in user_messages:
            try:
                user = self.bot.get_user(int(user_id))
                if user:
                    # Split long messages to avoid Discord limits
                    if len(message) > 2000:
                        chunks = [message[i:i+2000] for i in range(0, len(message), 2000)]
                        for chunk in chunks:
                            await user.send(chunk)
                            await asyncio.sleep(0.5)  # Small delay between chunks
                    else:
                        await user.send(message)
                else:
                    logger.warning(f"Could not find user {user_id} for DM")
                    
            except Exception as e:
                logger.exception(f"Error sending DM to user {user_id}: {e}")
    
    async def _send_channel_messages(self, channel_messages: List[tuple]):
        """Send messages to channels."""
        for channel_id, message in channel_messages:
            try:
                channel = self.bot.get_channel(int(channel_id))
                if channel:
                    # Split long messages to avoid Discord limits
                    if len(message) > 2000:
                        chunks = [message[i:i+2000] for i in range(0, len(message), 2000)]
                        for chunk in chunks:
                            await channel.send(chunk)
                            await asyncio.sleep(0.5)  # Small delay between chunks
                    else:
                        await channel.send(message)
                else:
                    logger.warning(f"Could not find channel {channel_id}")
                    
            except Exception as e:
                logger.exception(f"Error sending message to channel {channel_id}: {e}")
    
    def _update_frequency_setting(self):
        """Update the frequency setting from database."""
        try:
            frequency = self.db.get_frequency_setting()
            if frequency and 1 <= frequency <= 24:
                self.check_interval_hours = frequency
                logger.info(f"⏱️ Updated check interval to {frequency} hours")
            else:
                logger.warning(f"Invalid frequency setting: {frequency}, using default")
                
        except Exception as e:
            logger.exception(f"Error updating frequency setting: {e}")
    
    async def force_check_now(self):
        """Force an immediate news check (for admin commands)."""
        logger.info("🚀 Forcing immediate news check")
        await self._process_news_cycle()
        self.last_check_time = datetime.now()
    
    def get_status(self) -> Dict:
        """Get current status of the frequency checker."""
        return {
            'is_running': self.is_running,
            'check_interval_hours': self.check_interval_hours,
            'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None,
            'next_check_time': (self.last_check_time + timedelta(hours=self.check_interval_hours)).isoformat() 
                             if self.last_check_time else None
        }

# Global instance for the bot
_frequency_checker_instance: Optional[NewsFrequencyChecker] = None

def get_frequency_checker(bot_instance, server_id: str = "default") -> NewsFrequencyChecker:
    """Get or create the frequency checker instance."""
    global _frequency_checker_instance
    if _frequency_checker_instance is None:
        _frequency_checker_instance = NewsFrequencyChecker(bot_instance, server_name)
    return _frequency_checker_instance