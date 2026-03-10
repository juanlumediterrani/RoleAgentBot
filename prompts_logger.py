"""
Dedicated logging module for prompts sent to the agent.
Provides clear separation and formatting for prompt tracking.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import json

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

def get_prompts_logger():
    """
    Gets a dedicated logger for prompts with custom formatting.
    
    Returns:
        logging.Logger: Logger configured for prompt logging
    """
    logger = logging.getLogger('prompts')
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    logger.propagate = False
    logger.setLevel(logging.INFO)
    
    # Create prompts log file
    prompts_log_file = LOG_DIR / 'prompts.log'
    
    # Custom formatter for clear separation
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler with rotation
    try:
        file_handler = RotatingFileHandler(
            prompts_log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (PermissionError, OSError) as e:
        print(f"⚠️ Cannot create prompts log file {prompts_log_file}: {e}")
    
    return logger

def log_prompt(prompt_type, content, metadata=None):
    """
    Logs a prompt with clear separation and metadata.
    
    Args:
        prompt_type (str): Type of prompt (e.g., 'system', 'user', 'consolidated', 'subrole')
        content (str): The prompt content
        metadata (dict, optional): Additional metadata (role, server, user_id, etc.)
    """
    logger = get_prompts_logger()
    
    # Create separator
    separator = "=" * 80
    
    # Build log entry
    log_lines = [
        separator,
        f"PROMPT TYPE: {prompt_type.upper()}",
        f"TIMESTAMP: {datetime.now().isoformat()}"
    ]
    
    # Add metadata if provided
    if metadata:
        log_lines.append("METADATA:")
        for key, value in metadata.items():
            log_lines.append(f"  {key}: {value}")
    
    log_lines.extend([
        separator,
        "CONTENT:",
        content,
        separator,
        ""  # Empty line for spacing
    ])
    
    # Join and log
    log_entry = "\n".join(log_lines)
    logger.info(log_entry)

def log_system_prompt(content, role=None, server=None):
    """Convenience function to log system prompts."""
    metadata = {}
    if role:
        metadata['role'] = role
    if server:
        metadata['server'] = server
    
    log_prompt('system', content, metadata)

def log_user_prompt(content, user_id=None, server=None, role=None):
    """Convenience function to log user prompts."""
    metadata = {}
    if user_id:
        metadata['user_id'] = user_id
    if server:
        metadata['server'] = server
    if role:
        metadata['role'] = role
    
    log_prompt('user', content, metadata)

def log_consolidated_context(content, role=None, server=None, interaction_count=None):
    """Convenience function to log consolidated context prompts."""
    metadata = {}
    if role:
        metadata['role'] = role
    if server:
        metadata['server'] = server
    if interaction_count:
        metadata['interaction_count'] = interaction_count
    
    log_prompt('consolidated', content, metadata)

def log_readme_enhanced_prompt(original_question, readme_content, enhanced_prompt, role=None, server=None):
    """Convenience function to log README-enhanced prompts with special header."""
    metadata = {}
    if role:
        metadata['role'] = role
    if server:
        metadata['server'] = server
    
    # Create special README prompt log with multiple sections
    logger = get_prompts_logger()
    
    separator = "=" * 80
    readme_separator = "🔖" + "=" * 78
    
    log_lines = [
        readme_separator,
        "📖 README ENHANCED PROMPT",
        f"TIMESTAMP: {datetime.now().isoformat()}"
    ]
    
    # Add metadata if provided
    if metadata:
        log_lines.append("METADATA:")
        for key, value in metadata.items():
            log_lines.append(f"  {key}: {value}")
    
    log_lines.extend([
        readme_separator,
        "📝 ORIGINAL USER QUESTION:",
        original_question,
        readme_separator,
        "📋 README DOCUMENTATION:",
        readme_content,
        readme_separator,
        "🤖 ENHANCED PROMPT SENT TO LLM:",
        enhanced_prompt,
        readme_separator,
        ""  # Empty line for spacing
    ])
    
    # Join and log
    log_entry = "\n".join(log_lines)
    logger.info(log_entry)

def log_subrole_prompt(subrole_name, content, role=None, server=None):
    """Convenience function to log subrole prompts."""
    metadata = {
        'subrole': subrole_name
    }
    if role:
        metadata['role'] = role
    if server:
        metadata['server'] = server
    
    log_prompt('subrole', content, metadata)

def log_agent_response(content, role=None, server=None, response_length=None):
    """Convenience function to log agent responses (for completeness)."""
    metadata = {}
    if role:
        metadata['role'] = role
    if server:
        metadata['server'] = server
    if response_length:
        metadata['response_length'] = response_length
    
    log_prompt('response', content, metadata)
