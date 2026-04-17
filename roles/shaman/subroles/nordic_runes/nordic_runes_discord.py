"""
Nordic Runes Discord Commands Module
Provides Discord interface for Nordic runes functionality with personality support.
"""

import asyncio
from typing import Any, Dict, List, Optional
from agent_logging import get_logger

try:
    import discord
except ImportError:
    discord = None

try:
    from .nordic_runes import NordicRunes
    from .nordic_runes_messages import READING_TYPES, get_message, get_reading_type, load_personality_messages
    from .nordic_runes_db import get_nordic_runes_db_instance
except ImportError:
    # Fallback for direct loading
    import sys
    import os
    runes_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, runes_dir)
    try:
        from nordic_runes import NordicRunes
        from nordic_runes_messages import READING_TYPES, get_message, get_reading_type, load_personality_messages
        from nordic_runes_db import get_nordic_runes_db_instance
    finally:
        sys.path.remove(runes_dir)

try:
    from discord_bot.discord_utils import send_dm_or_channel
except ImportError:
    send_dm_or_channel = None

logger = get_logger('nordic_runes_discord')


class NordicRunesCommands:
    """Discord commands for Nordic runes functionality."""
    
    def __init__(self, guild=None):
        """Initialize the runes commands."""
        self.runes = NordicRunes()
        self.guild = guild
        self.db = self._get_nordic_runes_db()
    
    def _get_nordic_runes_db(self):
        """Get Nordic Runes database instance for a server."""
        try:
            from agent_db import get_server_id
            if self.guild:
                server_id = str(self.guild.id)
            else:
                server_id = get_server_id()
            return get_nordic_runes_db_instance(server_id)
        except Exception as e:
            logger.error(f"Failed to get Nordic Runes database: {e}")
            from agent_db import get_server_id
            return get_nordic_runes_db_instance(get_server_id())
    
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
        elif subcommand == 'runes':
            return await self.cmd_runes_list(ctx, args[1:])
        elif subcommand == 'help':
            return await self._show_help(ctx)
        else:
            logger.info(f"No subcommand matched, treating as direct cast with args: {args}")
            return await self.cmd_runes_cast(ctx, args)
    
    async def cmd_runes_cast(self, ctx, args_or_reading_type, question: Optional[str] = None) -> str:
        """Cast runes for a reading."""
        if isinstance(args_or_reading_type, list):
            args = args_or_reading_type
            logger.info(f"cmd_runes_cast called with args: {args}")

            reading_type = 'single'
            parsed_question = ""

            if args:
                potential_type = args[0].lower()
                logger.info(f"Checking potential_type: {potential_type}")
                logger.info(f"Available types: {list(READING_TYPES.keys())}")

                if potential_type in READING_TYPES:
                    reading_type = potential_type
                    parsed_question = ' '.join(args[1:]) if len(args) > 1 else ""
                    logger.info(f"Using reading_type: {reading_type}, question: {parsed_question}")
                else:
                    parsed_question = ' '.join(args)
                    logger.info(f"No valid type found, using question: {parsed_question}")
        else:
            reading_type = str(args_or_reading_type).lower()
            parsed_question = question or ""
            logger.info(f"cmd_runes_cast called with direct values: reading_type={reading_type}, question={parsed_question}")

        if reading_type not in READING_TYPES:
            logger.info(f"Invalid reading type: {reading_type}")
            if question is None and isinstance(args_or_reading_type, list):
                return get_message('invalid_type')
            return get_message('invalid_type'), None

        if not parsed_question.strip():
            logger.info("No question provided")
            if question is None and isinstance(args_or_reading_type, list):
                return get_message('no_question')
            return get_message('no_question'), None

        logger.info(f"Final - reading_type: {reading_type}, question: '{parsed_question}'")

        try:
            # Get server ID from Discord context
            server_id = str(ctx.guild.id) if hasattr(ctx, 'guild') and ctx.guild else None
            
            reading = self.runes.get_reading(reading_type, parsed_question, server_id)

            user_id = str(ctx.author.id) if hasattr(ctx, 'author') else 'unknown'

            reading_id = self.db.save_reading(
                user_id=user_id,
                question=parsed_question,
                runes_drawn=reading['runes_drawn'],
                interpretation=reading['interpretation'],
                reading_type=reading_type
            )

            logger.info(f"Reading saved with ID: {reading_id}, question: '{parsed_question}'")

            question_label = get_message('question', server_id=server_id)
            response = f"**{question_label}:** {parsed_question}\n"
            response += "---\n"

            if 'runes_drawn' in reading and reading['runes_drawn']:
                try:
                    messages = load_personality_messages(server_id)
                    translations = messages.get('translations', {})
                    positions = messages.get('positions', {})
                except Exception:
                    translations = {}
                    positions = {}

                for rune in reading['runes_drawn']:
                    position = rune.get('position', '')
                    possible_keys = [
                        rune.get('key', ''),
                        rune.get('name', '').lower(),
                        rune.get('name', '')
                    ]

                    rune_translation = {}
                    for key in possible_keys:
                        if key and key in translations:
                            rune_translation = translations[key]
                            break

                    if not rune_translation:
                        logger.warning(f"⚠️ [TRANSLATION] No translation found for {rune['name']} (tried keys: {possible_keys})")

                    if position and reading_type != 'single':
                        translated_position = positions.get(position, position)
                        response += f"**{translated_position}:** "

                    response += f"{rune['symbol']} {rune['name']} - "
                    meaning_text = rune_translation.get('meaning', rune.get('meaning', 'Unknown'))
                    response += f"{meaning_text}\n"
                    response += "---\n"

            main_response = response
            interpretation_response = reading['interpretation']

            if len(interpretation_response) > 2000:
                split_point = interpretation_response[:2000].rfind('. ')
                if split_point == -1:
                    split_point = interpretation_response[:2000].rfind(' ')
                if split_point == -1:
                    split_point = 2000

                first_part = interpretation_response[:split_point + 1]
                second_part = interpretation_response[split_point + 1:].strip()
                return main_response, first_part, second_part

            return main_response, interpretation_response

        except Exception as e:
            logger.error(f"Error in rune casting: {e}")
            if question is None and isinstance(args_or_reading_type, list):
                return get_message('error')
            return get_message('error'), None
    
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
    
    async def cmd_runes_list(self, ctx, args: List[str]) -> str:
        """Show all runes with their complete descriptions (supports pagination)."""
        # Parse page parameter
        page = 1
        if args:
            try:
                page = max(1, min(3, int(args[0])))  # Clamp between 1 and 3
            except ValueError:
                page = 1
        
        runes_title = get_message('runes_list')
        runes_content = get_message('runes_list_content', page)
        
        response = f"{runes_title}\n\n"
        response += runes_content
        
        return response
    
    async def cmd_runes_canvas_history(self, mock_message, limit: int = 5) -> str:
        """Canvas-compatible reading history."""
        try:
            user_id = str(mock_message.author.id) if hasattr(mock_message, 'author') else 'canvas_user'
            
            readings = self.db.get_user_readings(user_id, limit)
            
            if not readings:
                return get_message('history_empty')
            
            history_title = get_message('history')
            response = history_title.format(count=len(readings)) + ("-"*45) + "\n\n"
            
            for reading in readings:
                type_info = get_reading_type(reading['reading_type'])
                history_entry = get_message('history_entry')
                
                # Extract rune names from the list of dictionaries
                rune_names = []
                for rune in reading['runes_drawn']:
                    if isinstance(rune, dict):
                        rune_names.append(f"{rune.get('symbol', '?')} {rune.get('name', 'Unknown')}")
                    else:
                        rune_names.append(str(rune))
                
                # Get reading type name with fallback
                reading_type_name = type_info.get('name', reading['reading_type'].title())
                
                response += history_entry.format(
                    id=reading['id'],
                    type=reading_type_name,
                    question=reading['question'],
                    runes=', '.join(rune_names),
                    date=reading['created_at'][:10],
                    interpretation=reading['interpretation']
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
        response += "`!runes runes` - Show all runes with descriptions\n"
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
    guild = getattr(ctx, 'guild', None)
    commands = get_nordic_runes_commands_instance()
    # Update the guild context if needed
    if hasattr(commands, 'guild') and commands.guild != guild:
        commands.guild = guild
        commands.db = commands._get_nordic_runes_db()
    return await commands.cmd_runes(ctx, args)

async def cmd_runes_cast(ctx, args):
    """Cast runes command."""
    guild = getattr(ctx, 'guild', None)
    commands = get_nordic_runes_commands_instance()
    # Update the guild context if needed
    if hasattr(commands, 'guild') and commands.guild != guild:
        commands.guild = guild
        commands.db = commands._get_nordic_runes_db()
    return await commands.cmd_runes_cast(ctx, args)

async def cmd_runes_history(ctx, args):
    """Rune history command."""
    guild = getattr(ctx, 'guild', None)
    commands = get_nordic_runes_commands_instance()
    # Update the guild context if needed
    if hasattr(commands, 'guild') and commands.guild != guild:
        commands.guild = guild
        commands.db = commands._get_nordic_runes_db()
    return await commands.cmd_runes_history(ctx, args)

async def cmd_runes_types(ctx, args):
    """Rune types command."""
    guild = getattr(ctx, 'guild', None)
    commands = get_nordic_runes_commands_instance()
    # Update the guild context if needed
    if hasattr(commands, 'guild') and commands.guild != guild:
        commands.guild = guild
        commands.db = commands._get_nordic_runes_db()
    return await commands.cmd_runes_types(ctx, args)

async def cmd_runes_list(ctx, args):
    """Rune list command."""
    guild = getattr(ctx, 'guild', None)
    commands = get_nordic_runes_commands_instance()
    # Update the guild context if needed
    if hasattr(commands, 'guild') and commands.guild != guild:
        commands.guild = guild
        commands.db = commands._get_nordic_runes_db()
    return await commands.cmd_runes_list(ctx, args)
