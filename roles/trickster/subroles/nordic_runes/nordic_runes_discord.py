"""
Nordic Runes Discord Commands Module
Provides Discord interface for Nordic runes functionality with personality support.
"""

import asyncio
from typing import Any, Dict, List, Optional
from agent_logging import get_logger

try:
    from .nordic_runes import NordicRunes
    from .nordic_runes_messages import READING_TYPES, get_message, get_reading_type, load_personality_messages
    from .db_nordic_runes import get_nordic_runes_db_instance
except ImportError:
    # Fallback for direct loading
    import sys
    import os
    runes_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, runes_dir)
    try:
        from nordic_runes import NordicRunes
        from nordic_runes_messages import READING_TYPES, get_message, get_reading_type, load_personality_messages
        from db_nordic_runes import get_nordic_runes_db_instance
    finally:
        sys.path.remove(runes_dir)

try:
    from discord_bot.discord_utils import send_dm_or_channel
except ImportError:
    send_dm_or_channel = None

logger = get_logger('nordic_runes_discord')


class NordicRunesCommands:
    """Discord commands for Nordic runes functionality."""
    
    def __init__(self):
        """Initialize the runes commands."""
        self.runes = NordicRunes()
        self.db = get_nordic_runes_db_instance()
    
    async def cmd_runes(self, ctx, args: List[str]) -> str:
        """Main runes command dispatcher."""
        logger.info(f"cmd_runes called with args: {args}")
        
        if not args:
            return await self._show_help(ctx)
        
        subcommand = args[0].lower()
        logger.info(f"Subcommand detected: {subcommand}")
        
        if subcommand == 'cast':
            return await self.cmd_runes_cast(ctx, args[1:])
        elif subcommand == 'history':
            return await self.cmd_runes_history(ctx, args[1:])
        elif subcommand == 'types':
            return await self.cmd_runes_types(ctx, args[1:])
        elif subcommand == 'help':
            return await self._show_help(ctx)
        else:
            logger.info(f"No subcommand matched, treating as direct cast with args: {args}")
            return await self.cmd_runes_cast(ctx, args)
    
    async def cmd_runes_cast(self, ctx, args: List[str]) -> str:
        """Cast runes for a reading."""
        # Debug logging
        logger.info(f"cmd_runes_cast called with args: {args}")
        
        # Parse reading type
        reading_type = 'single'  # default
        question = ""
        
        if args:
            # Check if first arg is a reading type
            potential_type = args[0].lower()
            logger.info(f"Checking potential_type: {potential_type}")
            logger.info(f"Available types: {list(READING_TYPES.keys())}")
            
            if potential_type in READING_TYPES:
                reading_type = potential_type
                question = ' '.join(args[1:]) if len(args) > 1 else ""
                logger.info(f"Using reading_type: {reading_type}, question: {question}")
            else:
                question = ' '.join(args)
                logger.info(f"No valid type found, using question: {question}")
        
        # Validate reading type
        if reading_type not in READING_TYPES:
            logger.info(f"Invalid reading type: {reading_type}")
            return get_message('invalid_type')
        
        # Check for question
        if not question.strip():
            logger.info("No question provided")
            return get_message('no_question')
        
        logger.info(f"Final - reading_type: {reading_type}, question: '{question}'")
        
        try:
            # Perform the reading
            reading = self.runes.get_reading(reading_type, question)
            
            # Get user and server info
            user_id = str(ctx.author.id) if hasattr(ctx, 'author') else 'unknown'
            server_id = str(ctx.guild.id) if hasattr(ctx, 'guild') and ctx.guild else None
            
            # Save to database
            reading_id = self.db.save_reading(
                user_id=user_id,
                server_id=server_id,
                question=question,
                runes_drawn=reading['runes_drawn'],
                interpretation=reading['interpretation'],
                reading_type=reading_type
            )
            
            logger.info(f"Reading saved with ID: {reading_id}, question: '{question}'")
            
            # Format response with personality
            type_info = get_reading_type(reading_type)
            cast_title = get_message(f"{reading_type}_cast")
            question_label = get_message('question')
            success_msg = get_message('success')
            saved_msg = get_message('saved')
            
            response = f"{cast_title}\n\n"
            response += f"**{question_label}:** {question}\n\n"
            
            # Add rune display
            if 'runes_drawn' in reading and reading['runes_drawn']:
                # Load translations for rune meanings
                try:
                    messages = load_personality_messages()
                    translations = messages.get('translations', {})
                except:
                    translations = {}
                
                for rune in reading['runes_drawn']:
                    position = rune.get('position', '')
                    # Try multiple possible keys for translation
                    possible_keys = [
                        rune.get('key', ''),
                        rune.get('name', '').lower(),
                        rune.get('name', '')
                    ]
                    
                    # Find the first key that has a translation
                    rune_translation = {}
                    for key in possible_keys:
                        if key and key in translations:
                            rune_translation = translations[key]
                            break
                    
                    # Only show position for multi-rune spreads, not for single rune casts
                    if position and reading_type != 'single':
                        response += f"**{position}:**\n"
                    response += f"{rune['symbol']} {rune['name']}\n\n"
                    
                    # Use translated meaning if available, otherwise English
                    meaning_text = rune_translation.get('meaning', rune.get('meaning', 'Unknown'))
                    response += f"**{get_message('meaning')}:** {meaning_text}\n"
                    
                    # Use translated keywords if available, otherwise English
                    keywords_text = rune_translation.get('keywords', ', '.join(rune.get('keywords', [])))
                    response += f"**{get_message('keywords')}:** {keywords_text}\n\n"
                    
                    # Use translated interpretation if available, otherwise English
                    interpretation_text = rune_translation.get('interpretation', rune.get('description', 'No description'))
                    response += f"**{get_message('interpretation')}:** {interpretation_text}\n\n"
                    
                    response += "---\n\n"
            
            response += reading['interpretation']
            response += f"\n\n{success_msg} {saved_msg}"
            
            return response
            
        except Exception as e:
            logger.error(f"Error in rune casting: {e}")
            return get_message('error')
    
    async def cmd_runes_history(self, ctx, args: List[str]) -> str:
        """Show user's reading history."""
        try:
            user_id = str(ctx.author.id) if hasattr(ctx, 'author') else 'unknown'
            
            # Get limit from args
            limit = 5
            if args and args[0].isdigit():
                limit = min(int(args[0]), 20)  # Max 20 readings
            
            readings = self.db.get_user_readings(user_id, limit)
            
            if not readings:
                return get_message('history_empty')
            
            history_title = get_message('history')
            response = history_title.format(count=len(readings)) + "\n\n"
            
            for reading in readings:
                type_info = get_reading_type(reading['reading_type'])
                history_entry = get_message('history_entry')
                response += history_entry.format(
                    id=reading['id'],
                    type=type_info['name'],
                    question=reading['question'],
                    runes=', '.join(reading['runes_drawn']),
                    date=reading['created_at'][:10]
                ) + "\n\n"
            
            # Get stats
            stats = self.db.get_reading_stats(user_id)
            stats_message = get_message('stats')
            response += stats_message.format(
                total=stats['total_readings'],
                favorite=stats['favorite_type'] or 'None'
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting rune history: {e}")
            return get_message('error')
    
    async def cmd_runes_types(self, ctx, args: List[str]) -> str:
        """Show available reading types."""
        types_title = get_message('types')
        types_content = get_message('types_content')
        
        response = f"{types_title}\n\n"
        response += types_content
        
        return response
    
    async def cmd_runes_canvas_cast(self, mock_message, reading_type: str, question: str) -> str:
        """Canvas-compatible rune casting."""
        try:
            # Validate reading type
            if reading_type not in READING_TYPES:
                return get_message('invalid_type')
            
            # Check for question
            if not question.strip():
                return get_message('no_question')
            
            # Perform the reading
            reading = self.runes.get_reading(reading_type, question)
            
            # Get user info from mock message
            user_id = str(mock_message.author.id) if hasattr(mock_message, 'author') else 'canvas_user'
            
            # Save to database
            reading_id = self.db.save_reading(
                user_id=user_id,
                server_id=None,  # Canvas doesn't have server context
                question=question,
                runes_drawn=reading['runes_drawn'],
                interpretation=reading['interpretation'],
                reading_type=reading_type
            )
            
            # Format response for Canvas with personality
            type_info = get_reading_type(reading_type)
            cast_title = get_message(f"{reading_type}_cast")
            question_label = get_message('question')
            response = f"{cast_title}\n\n"
            response += f"**{question_label}:** {question}\n\n"
            
            # Add rune display
            if 'runes_drawn' in reading and reading['runes_drawn']:
                # Load translations for rune meanings
                try:
                    messages = load_personality_messages()
                    translations = messages.get('translations', {})
                    logger.info(f"🔍 [TRANSLATIONS] Canvas loaded {len(translations)} translations")
                except:
                    translations = {}
                    logger.error("❌ [TRANSLATIONS] Canvas failed to load translations")
                
                for rune in reading['runes_drawn']:
                    position = rune.get('position', '')
                    # Try multiple possible keys for translation
                    possible_keys = [
                        rune.get('key', ''),
                        rune.get('name', '').lower(),
                        rune.get('name', '')
                    ]
                    
                    # Find the first key that has a translation
                    rune_translation = {}
                    for key in possible_keys:
                        if key and key in translations:
                            rune_translation = translations[key]
                            logger.info(f"✅ [TRANSLATION] Canvas found translation for {rune['name']} using key '{key}': {rune_translation.get('meaning', 'NO MEANING')}")
                            break
                    
                    if not rune_translation:
                        logger.warning(f"⚠️ [TRANSLATION] Canvas no translation found for {rune['name']} (tried keys: {possible_keys})")
                    
                    # Only show position for multi-rune spreads, not for single rune casts
                    if position and reading_type != 'single':
                        response += f"**{position}:**\n"
                    response += f"{rune['symbol']} {rune['name']}\n\n"
                    
                    # Use translated meaning if available, otherwise English
                    meaning_text = rune_translation.get('meaning', rune.get('meaning', 'Unknown'))
                    logger.info(f"🔍 [MEANING] Canvas final meaning text: {meaning_text}")
                    response += f"**{get_message('meaning')}:** {meaning_text}\n"
                    
                    # Use translated keywords if available, otherwise English
                    keywords_text = rune_translation.get('keywords', ', '.join(rune.get('keywords', [])))
                    logger.info(f"🔍 [KEYWORDS] Canvas final keywords text: {keywords_text}")
                    response += f"**{get_message('keywords')}:** {keywords_text}\n\n"
                    
                    # Use translated interpretation if available, otherwise English
                    interpretation_text = rune_translation.get('interpretation', rune.get('description', 'No description'))
                    logger.info(f"🔍 [INTERPRETATION] Canvas final interpretation text: {interpretation_text}")
                    response += f"**{get_message('interpretation')}:** {interpretation_text}\n\n"
                    
                    response += "---\n\n"
            
            response += reading['interpretation']
            
            return response
            
        except Exception as e:
            logger.error(f"Error in canvas rune casting: {e}")
            return get_message('error')
    
    async def cmd_runes_canvas_history(self, mock_message, limit: int = 5) -> str:
        """Canvas-compatible reading history."""
        try:
            user_id = str(mock_message.author.id) if hasattr(mock_message, 'author') else 'canvas_user'
            
            readings = self.db.get_user_readings(user_id, limit)
            
            if not readings:
                return get_message('history_empty')
            
            history_title = get_message('history')
            response = history_title.format(count=len(readings)) + "\n\n"
            
            for reading in readings:
                type_info = get_reading_type(reading['reading_type'])
                history_entry = get_message('history_entry')
                response += history_entry.format(
                    id=reading['id'],
                    type=type_info['name'],
                    question=reading['question'],
                    runes=', '.join(reading['runes_drawn']),
                    date=reading['created_at'][:10]
                ) + "\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting canvas rune history: {e}")
            return get_message('error')
    
    async def _show_help(self, ctx) -> str:
        """Show help information."""
        welcome = get_message('welcome')
        help_title = get_message('help')
        help_content = get_message('help_content')
        reading_types = get_message('reading_types')
        
        response = f"{welcome}\n\n"
        response += "**Commands:**\n"
        response += "`!runes cast [type] <question>` - Cast runes for guidance\n"
        response += "`!runes history [limit]` - View your reading history\n"
        response += "`!runes types` - Show available reading types\n"
        response += "`!runes help` - Show this help\n\n"
        response += reading_types
        
        return response


# Global commands instance
_commands_instance = None

def get_nordic_runes_commands_instance() -> NordicRunesCommands:
    """Get the global Nordic runes commands instance."""
    global _commands_instance
    if _commands_instance is None:
        _commands_instance = NordicRunesCommands()
    return _commands_instance

# Command functions for registration
async def cmd_runes(ctx, args):
    """Main runes command."""
    commands = get_nordic_runes_commands_instance()
    return await commands.cmd_runes(ctx, args)

async def cmd_runes_cast(ctx, args):
    """Cast runes command."""
    commands = get_nordic_runes_commands_instance()
    return await commands.cmd_runes_cast(ctx, args)

async def cmd_runes_history(ctx, args):
    """Rune history command."""
    commands = get_nordic_runes_commands_instance()
    return await commands.cmd_runes_history(ctx, args)

async def cmd_runes_types(ctx, args):
    """Rune types command."""
    commands = get_nordic_runes_commands_instance()
    return await commands.cmd_runes_types(ctx, args)
