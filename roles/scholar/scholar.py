import os
import sys

# Ensure project root imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from agent_logging import get_logger
from agent_engine import PERSONALITY, _get_personality
from agent_db import get_server_id
from agent_mind import (
    generate_daily_memory_summary,
    generate_recent_memory_summary,
    generate_user_relationship_memory_summary,
    _get_daily_memory_fallback,
    _get_recent_memory_fallback,
    _get_relationship_memory_fallback,
)
from .wikipedia_fetcher import fetch_wikipedia_extract

logger = get_logger('scholar')

def get_scholar_system_prompt(server_id: str = None) -> str:
    """Get scholar system prompt from personality or fallback to English."""
    try:
        from agent_engine import _get_personality, _build_system_prompt
        personality = _get_personality(server_id) if server_id else PERSONALITY
        # Use the full system prompt builder which includes active_duties section
        return _build_system_prompt(personality, server_id)
    except Exception:
        return "CURRENT DUTY - SCHOLAR: You are the Scholar, an erudite who shares knowledge from your vast library."

def get_scholar_prompt(server_id: str = None) -> str:
    """Get scholar prompt from personality or fallback to English."""
    try:
        from agent_engine import _get_personality
        personality = _get_personality(server_id) if server_id else PERSONALITY
        role_prompts = personality.get("roles", {})
        return role_prompts.get("scholar", {}).get(
            "prompt",
            "You are a scholar with vast knowledge. Answer questions with wisdom and insight."
        )
    except Exception:
        return "You are a scholar. Answer questions with your vast knowledge."

def get_scholar_golden_rules(server_id: str = None) -> list:
    """Get scholar golden rules from personality or fallback to English."""
    try:
        from agent_engine import _get_personality
        personality = _get_personality(server_id) if server_id else PERSONALITY
        role_prompts = personality.get("roles", {})
        return role_prompts.get("scholar", {}).get(
            "golden_rules",
            [
                "1. Be concise and accurate.",
                "2. Stay in character.",
                "3. Do not act as a generic assistant."
            ]
        )
    except Exception:
        return [
            "1. Be concise and accurate.",
            "2. Stay in character.",
            "3. Do not act as a generic assistant."
        ]

def get_personality_language(server_id: str = None) -> str:
    """Get the language code from personality directory (en, es, zh, etc.)."""
    try:
        from pathlib import Path
        from agent_engine import AGENT_CFG
        
        # Try to get language from personality directory path
        if server_id:
            try:
                from discord_bot.db_init import get_server_personality_dir
                server_dir = get_server_personality_dir(server_id)
                if server_dir:
                    # Extract language from path like .../personalities/hans/es-ES/
                    path_parts = Path(server_dir).parts
                    if len(path_parts) >= 2:
                        lang_code = path_parts[-2]  # Second to last part is the language
                        # Map to Wikipedia language codes
                        lang_map = {
                            "en-US": "en",
                            "es-ES": "es",
                            "zh-CN": "zh",
                            "zh-CH": "zh"
                        }
                        return lang_map.get(lang_code, "en")
            except:
                pass
        
        # Fallback to agent_config default_language
        default_lang = AGENT_CFG.get("default_language", "en-US")
        lang_map = {
            "en-US": "en",
            "es-ES": "es",
            "zh-CN": "zh",
            "zh-CH": "zh"
        }
        return lang_map.get(default_lang, "en")
    except Exception:
        return "en"

async def answer_question(question: str, user_id: str = None, user_name: str = None, server_id: str = None) -> tuple | str:
    """Answer a question using the LLM's pre-trained knowledge.
    
    Args:
        question: The user's question
        user_id: The user's Discord ID
        user_name: The user's name
        server_id: Server ID for server-specific personality
        
    Returns:
        The scholar's response, or (response, wikipedia_url) tuple if Wikipedia was used
    """
    from agent_mind import call_llm
    
    # Get server-specific personality
    try:
        from agent_engine import _get_personality
        personality = _get_personality(server_id) if server_id else PERSONALITY
    except Exception:
        personality = PERSONALITY
    
    # Get system prompt using build_system_prompt
    system_prompt = get_scholar_system_prompt(server_id)
    
    # Get scholar-specific prompt and golden rules
    scholar_prompt = get_scholar_prompt(server_id)
    golden_rules = get_scholar_golden_rules(server_id)
    
    # Get memory sections
    daily_memory = ""
    recent_memory = ""
    relationship_memory = ""
    
    if server_id:
        try:
            daily_memory = await asyncio.to_thread(generate_daily_memory_summary, server_id)
        except Exception as e:
            logger.warning(f"Could not get daily memory: {e}")
            daily_memory = _get_daily_memory_fallback(server_id)
        
        try:
            recent_memory = await asyncio.to_thread(generate_recent_memory_summary, server_id)
        except Exception as e:
            logger.warning(f"Could not get recent memory: {e}")
            recent_memory = _get_recent_memory_fallback(server_id)
        
        if user_id:
            try:
                relationship_memory = await asyncio.to_thread(
                    generate_user_relationship_memory_summary,
                    user_id,
                    user_name,
                    server_id
                )
            except Exception as e:
                logger.warning(f"Could not get relationship memory: {e}")
                relationship_memory = _get_relationship_memory_fallback(user_name, server_id)
    
    # Build the user prompt with memory sections, scholar task, question, and golden rules
    prompt_sections = []
    
    # Memory sections
    if daily_memory:
        prompt_sections.append(f"DAILY MEMORY:\n{daily_memory}")
    if recent_memory:
        prompt_sections.append(f"RECENT MEMORY:\n{recent_memory}")
    if relationship_memory:
        prompt_sections.append(f"RELATIONSHIP MEMORY:\n{relationship_memory}")
    
    # Scholar task
    prompt_sections.append(f"SCHOLAR TASK:\n{scholar_prompt}")
    
    # User question
    prompt_sections.append(f"QUESTION:\n{question}")
    
    # Golden rules
    if golden_rules:
        prompt_sections.append(f"GOLDEN RULES:\n" + "\n".join(golden_rules))
    
    prompt = "\n\n".join(prompt_sections)
    
    try:
        response = call_llm(
            system_instruction=system_prompt,
            prompt=prompt,
            background=True,
            call_type="scholar",
            critical=False,
            server_id=server_id,
            user_id=user_id,
            user_name=user_name
        )
        
        if response and len(response.strip()) > 0:
            response = response.strip()
            
            # Check if LLM responded with WIKIPEDIA <topic>
            if response.startswith("WIKIPEDIA "):
                # Extract topic (remove "WIKIPEDIA " prefix)
                topic = response[10:].strip()
                # Get language from personality
                lang = get_personality_language(server_id)
                # Fetch Wikipedia extract
                logger.info(f"Fetching Wikipedia for topic: {topic} (lang: {lang})")
                wiki_result = await fetch_wikipedia_extract(topic, lang)
                
                if wiki_result:
                    wiki_extract, wiki_url = wiki_result
                    logger.info(f"Successfully fetched Wikipedia extract for {topic}")
                    
                    # Remove wiki/wikipedia trigger words from original question
                    import re
                    clean_question = re.sub(r'\bwiki\b|\bwikipedia\b', '', question, flags=re.IGNORECASE).strip()
                    clean_question = re.sub(r'\s+', ' ', clean_question)  # Clean up extra spaces
                    
                    # Build second prompt with Wikipedia context after golden rules
                    prompt_sections_2 = []
                    
                    # Memory sections
                    if daily_memory:
                        prompt_sections_2.append(f"DAILY MEMORY:\n{daily_memory}")
                    if recent_memory:
                        prompt_sections_2.append(f"RECENT MEMORY:\n{recent_memory}")
                    if relationship_memory:
                        prompt_sections_2.append(f"RELATIONSHIP MEMORY:\n{relationship_memory}")
                    
                    # Scholar task
                    prompt_sections_2.append(f"SCHOLAR TASK:\n{scholar_prompt}")
                    
                    # Clean question (without wiki/wikipedia trigger)
                    prompt_sections_2.append(f"QUESTION:\n{clean_question}")
                    
                    # Golden rules
                    if golden_rules:
                        prompt_sections_2.append(f"GOLDEN RULES:\n" + "\n".join(golden_rules))
                    
                    # Wikipedia context (after golden rules)
                    prompt_sections_2.append(f"WIKIPEDIA CONTEXT:\n{wiki_extract}")
                    
                    prompt_2 = "\n\n".join(prompt_sections_2)
                    
                    # Second LLM call with Wikipedia context
                    response_2 = call_llm(
                        system_instruction=system_prompt,
                        prompt=prompt_2,
                        background=True,
                        call_type="scholar",
                        critical=False,
                        server_id=server_id,
                        user_id=user_id,
                        user_name=user_name
                    )
                    
                    if response_2 and len(response_2.strip()) > 0:
                        logger.info(f"📚 Scholar answered with Wikipedia context: {clean_question[:50]}...")
                        return (response_2.strip(), wiki_url)
                    else:
                        logger.warning("⚠️ Scholar could not generate response with Wikipedia context")
                        return (f"WIKIPEDIA:\n{wiki_extract}", wiki_url)
                else:
                    logger.debug(f"No Wikipedia extract found for {topic}")
                    return f"Could not find Wikipedia article for: {topic}"
            
            logger.info(f"📚 Scholar answered: {question[:50]}...")
            return response
        else:
            logger.warning("⚠️ Scholar could not generate a response")
            return "The archives are silent on this matter, pilgrim."
            
    except Exception as e:
        logger.exception(f"Error in scholar answer: {e}")
        return "My core processors struggle with this query. The archives may be incomplete."

async def scholar_task():
    """Execute scholar role tasks (placeholder for future background tasks)."""
    logger.info("📚 Scholar role tasks...")
    # Scholar is primarily interactive, no background tasks currently
    logger.info("✅ Scholar role tasks completed")
