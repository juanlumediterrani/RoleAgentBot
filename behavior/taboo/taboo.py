"""
Taboo behavior system - Handles forbidden word detection and responses.
"""

import asyncio
from agent_engine import PERSONALITY
from agent_mind import call_llm
from agent_logging import get_logger


def build_taboo_prompt(taboo_keyword: str, user_display_name: str, message_content: str, taboo_prompt_cfg: dict) -> str:
    """
    Build the complete taboo prompt following the specified structure.
    
    Args:
        taboo_keyword: The forbidden word that was detected
        user_display_name: Name of the user who said the word
        message_content: The full message content
        taboo_prompt_cfg: Configuration from prompts.json/behaviors/taboo
        
    Returns:
        Formatted prompt string with all components
    """
    # Get configuration with English fallbacks
    taboo_task = taboo_prompt_cfg.get("task", 
        "TASK: The human used the word {word} in a public channel, that word is sacred! Make them regret using it in vain!"
    ).format(word=taboo_keyword)
    
    taboo_golden_rules = "\n".join(taboo_prompt_cfg.get("golden_rules", [
        "[GOLDEN RULES]:",
        "1. LENGTH: 1-3 sentences (25-150 characters).",
        "2. GRAMMAR: No accents.",
        "3. Don't end sentences with single words like 'ke', 'a', 'de'.",
        "4. Don't repeat what you've already said (check interactions), be original and creative.",
        "5. You will speak in a public channel with many humans."
    ]))
    
    taboo_message_title = taboo_prompt_cfg.get("message_title", 
        "## A HUMAN CALLED {user_name} SAID THE FOLLOWING BLASPHEMY:"
    ).format(user_name=user_display_name)
    
    taboo_response_title = taboo_prompt_cfg.get("response_title", 
        "## RESPOND ONLY WITH PERSONALITY WARNING:"
    )
    
    # Build contextual user content with memory blocks
    taboo_user_message = f"{taboo_message_title}\n{message_content}\n\n{'-'*45}\n{taboo_task}\n{taboo_golden_rules}\n{taboo_response_title}"
    
    return taboo_user_message


def get_taboo_fallback_message() -> str:
    """
    Get fallback taboo message in English.
    
    Returns:
        Default taboo warning message
    """
    return "TABOO WARNING: Careful human, that word is sacred for the orcs! Only tribe members can use it. Better use it with respect or I'll smash your face!"


async def process_taboo_trigger(message, taboo_keyword: str, server_name: str) -> bool:
    """
    Process taboo word trigger and send response.
    
    Args:
        message: Discord message object
        taboo_keyword: The forbidden word that was detected
        server_name: Server name for context
        
    Returns:
        True if taboo was processed, False otherwise
    """
    logger = get_logger('taboo')
    
    try:
        # Get taboo configuration from prompts.json/behaviors/taboo
        taboo_prompt_cfg = PERSONALITY.get("behaviors", {}).get("taboo", {})
        
        # Build the complete taboo prompt using the extracted function
        taboo_user_message = build_taboo_prompt(
            taboo_keyword=taboo_keyword,
            user_display_name=message.author.display_name,
            message_content=message.content,
            taboo_prompt_cfg=taboo_prompt_cfg
        )
        
        # Use call_llm to get full memory context and generate response
        from agent_engine import _build_system_prompt
        system_instruction = _build_system_prompt(PERSONALITY)
        
        taboo_response = call_llm(
            system_instruction=system_instruction,
            prompt=taboo_user_message,
            async_mode=False,
            call_type="think",
            critical=True,
            metadata={
                "user_id": message.author.id,
                "user_name": message.author.name,
                "server_name": server_name,
                "interaction_type": "taboo",
                "is_public": True
            },
            logger=logger
        )
        
        # If LLM response is good, use it, otherwise fallback to taboo function
        if taboo_response and str(taboo_response).strip():
            await message.channel.send(str(taboo_response).strip())
        else:
            # Fallback to taboo function message
            fallback_msg = get_taboo_fallback_message()
            await message.channel.send(fallback_msg)
        
        # Register the taboo interaction in the database
        try:
            from agent_db import register_interaction
            register_interaction(
                user_id=message.author.id,
                user_name=message.author.display_name,
                server_id=server_name,
                interaction_type="TABOO",
                context=f"Taboo word detected: '{taboo_keyword}'",
                metadata={
                    "taboo_keyword": taboo_keyword,
                    "message_content": message.content,
                    "channel_id": message.channel.id,
                    "response": str(taboo_response).strip() if taboo_response else fallback_msg
                }
            )
        except Exception as e:
            logger.warning(f"Failed to register taboo interaction: {e}")
        
        return True
        
    except Exception as e:
        logger.exception(f"Error processing taboo trigger: {e}")
        return False
