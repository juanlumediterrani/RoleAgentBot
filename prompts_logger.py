"""
Dedicated logging module for prompts sent to the agent.
Provides clear separation and formatting for prompt tracking.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import json
import os

# Base directory for personality loading
_BASE_DIR = Path(__file__).parent

# Fallback messages (English)
_FALLBACK_LOGGING_MESSAGES = {
    "readme_enhanced_header": "📖 README ENHANCED PROMPT",
    "original_question_label": "📝 ORIGINAL USER QUESTION:",
    "enhanced_prompt_label": "🤖 ENHANCED PROMPT SENT TO LLM:",
    "complete_prompt_label": "🔧 COMPLETE PROMPT SENT TO LLM:",
    "readme_separator": "🔖=============================================================================="
}

def _get_logging_messages():
    """Load logging messages from personality or return fallbacks."""
    try:
        # Try to get personality from agent_engine
        try:
            from agent_engine import PERSONALITY
            personality_name = PERSONALITY.get("name", "").lower()
        except ImportError:
            # Fallback: try to determine personality from config
            import json
            config_path = _BASE_DIR / "agent_config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    personality_rel = config.get("personality", "personalities/default.json")
                    personality_name = Path(personality_rel).stem
            else:
                personality_name = "default"
        
        # Load prompts.json from personality directory
        prompts_path = _BASE_DIR / "personalities" / personality_name / "prompts.json"
        if prompts_path.exists():
            with open(prompts_path, 'r', encoding='utf-8') as f:
                prompts_data = json.load(f)
                logging_messages = prompts_data.get("logging_messages", {})
                # Merge with fallbacks for any missing keys
                return {**_FALLBACK_LOGGING_MESSAGES, **logging_messages}
    except Exception as e:
        # If anything fails, return fallbacks
        pass
    
    return _FALLBACK_LOGGING_MESSAGES

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
    prompts_log_file = LOG_DIR / 'prompt.log'
    
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

def log_final_llm_prompt(provider, call_type, system_instruction, user_prompt, role=None, server=None, metadata=None):
    logger = get_prompts_logger()
    separator = "=" * 80

    final_metadata = {
        "provider": provider,
        "call_type": call_type,
    }
    if role:
        final_metadata["role"] = role
    if server:
        final_metadata["server"] = server
    if metadata:
        final_metadata.update(metadata)

    log_lines = [
        separator,
        f"FINAL PROMPT SENT TO LLM [{str(provider).upper()} | {str(call_type).upper()}]",
        f"TIMESTAMP: {datetime.now().isoformat()}",
        "METADATA:",
    ]

    for key, value in final_metadata.items():
        log_lines.append(f"  {key}: {value}")

    log_lines.extend([
        separator,
        "SYSTEM INSTRUCTION:",
        system_instruction or "",
        "",
        "USER PROMPT:",
        user_prompt or "",
        separator,
        "",
    ])

    logger.info("\n".join(log_lines))

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

def log_readme_enhanced_prompt(original_question, readme_content, enhanced_prompt, system_instruction=None, role=None, server=None):
    metadata = {
        "readme_length": len(readme_content or ""),
        "original_question": original_question or "",
    }
    log_final_llm_prompt(
        provider="readme",
        call_type="documentation_second_pass",
        system_instruction=system_instruction or "",
        user_prompt=enhanced_prompt,
        role=role,
        server=server,
        metadata=metadata,
    )

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
