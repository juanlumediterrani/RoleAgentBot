"""Sentinel detection handlers for Scholar role.

This module handles detection and processing of special sentinel responses
emitted by the LLM (WIKIPEDIA, README) to keep role logic cohesive within
the roles/scholar/ directory instead of leaking into agent_discord.py.
"""

import asyncio
import re
from typing import Optional, Dict, Any

from agent_logging import get_logger

logger = get_logger(__name__)


async def process_wikipedia_sentinel(
    response: str,
    clean_content: str,
    system_instruction: str,
    server_id: str,
    message_author_id: int,
    message_author_name: str,
    is_public: bool,
    is_mention: bool,
    channel_id: Optional[int],
    call_llm_async,
    llm_semaphore,
    metadata_base: Dict[str, Any],
) -> Optional[tuple]:
    """Process WIKIPEDIA sentinel response from LLM.

    When the LLM emits "WIKIPEDIA <topic>", this function:
    1. Extracts the topic
    2. Fetches Wikipedia extract in the server's language
    3. Builds an enhanced prompt with Wikipedia context
    4. Makes a second LLM call with the context

    Args:
        response: The LLM response that starts with "WIKIPEDIA "
        clean_content: The original user message (cleaned)
        system_instruction: System instruction for the LLM
        server_id: Server ID for personality/memory lookups
        message_author_id: Discord user ID
        message_author_name: Discord user display name
        is_public: Whether this is a public channel message
        is_mention: Whether the bot was mentioned
        channel_id: Discord channel ID (if public)
        call_llm_async: The async LLM call function (from agent_mind)
        llm_semaphore: Semaphore for concurrency control
        metadata_base: Base metadata dict to extend

    Returns:
        Tuple of (enhanced_response, wikipedia_url) from the second LLM call, or None if processing fails.
    """
    if not response or not response.strip().startswith("WIKIPEDIA "):
        return None

    logger.info(f"🔍 WIKIPEDIA response detected from {message_author_name}")

    try:
        # Extract topic from response
        topic = response.strip()[10:].strip()
        logger.info(f"📚 Wikipedia topic extracted: {topic}")

        # Get language from server_config.json (not personality directory)
        from discord_bot.canvas.server_config import get_server_language
        lang_code = get_server_language(server_id)
        # Map to Wikipedia language codes
        lang_map = {
            "en-US": "en",
            "es-ES": "es",
            "zh-CN": "zh",
            "zh-CH": "zh"
        }
        lang = lang_map.get(lang_code, "en")

        # Fetch Wikipedia extract
        from roles.scholar.wikipedia_fetcher import fetch_wikipedia_extract
        wiki_result = await fetch_wikipedia_extract(topic, lang=lang)

        if wiki_result:
            wiki_extract, wiki_url = wiki_result
            logger.info(f"✅ Wikipedia extract fetched successfully for {topic} (lang: {lang})")

            # Remove wiki/wikipedia trigger words from original question
            clean_question = re.sub(r'\bwiki\b|\bwikipedia\b', '', clean_content, flags=re.IGNORECASE).strip()
            clean_question = re.sub(r'\s+', ' ', clean_question)

            # Build enhanced prompt with Wikipedia context using scholar task and rules
            from roles.scholar.scholar import get_scholar_prompt, get_scholar_golden_rules
            from agent_mind import (
                generate_daily_memory_summary,
                generate_recent_memory_summary,
                generate_user_relationship_memory_summary,
                _get_daily_memory_fallback,
                _get_recent_memory_fallback,
                _get_relationship_memory_fallback
            )

            # Get memory sections
            daily_memory = ""
            recent_memory = ""
            relationship_memory = ""

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

            try:
                relationship_memory = await asyncio.to_thread(
                    generate_user_relationship_memory_summary,
                    message_author_id,
                    message_author_name,
                    server_id
                )
            except Exception as e:
                logger.warning(f"Could not get relationship memory: {e}")
                relationship_memory = _get_relationship_memory_fallback(message_author_name, server_id)

            # Get scholar-specific prompt and golden rules
            scholar_prompt = get_scholar_prompt(server_id)
            golden_rules = get_scholar_golden_rules(server_id)

            # Build prompt sections like scholar.py does
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
            prompt_sections.append(f"QUESTION:\n{clean_question}")

            # Golden rules
            if golden_rules:
                prompt_sections.append(f"GOLDEN RULES:\n" + "\n".join(golden_rules))

            # Wikipedia context
            prompt_sections.append(f"WIKIPEDIA CONTEXT:\n{wiki_extract}")

            enhanced_prompt = "\n\n".join(prompt_sections)

            logger.info(f"📚 Making second LLM call with Wikipedia context")

            # Make second LLM call with Wikipedia context
            metadata = {
                **metadata_base,
                "wikipedia_enhanced": True,
            }
            async with llm_semaphore:
                response = await call_llm_async(
                    system_instruction=system_instruction,
                    prompt=enhanced_prompt,
                    background=False,
                    call_type="wikipedia_enhanced",
                    critical=True,
                    metadata=metadata,
                    logger=logger,
                    user_id=str(message_author_id),
                    user_name=message_author_name,
                    server_id=server_id
                )

            logger.info(f"✅ Wikipedia enhanced response generated")
            return (response, wiki_url)
        else:
            logger.warning(f"⚠️ Could not fetch Wikipedia extract for {topic} (lang: {lang})")
            return None

    except Exception as e:
        logger.exception(f"❌ Error processing Wikipedia response: {e}")
        return None
