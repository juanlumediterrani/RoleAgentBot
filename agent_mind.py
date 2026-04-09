import os
import time
import queue
import threading
import logging
from datetime import date, datetime
import httpx
from typing import Any
import json

try:
    from google import genai
    from google.genai import types as genai_types
    VERTEXAI_AVAILABLE = True
except ImportError:
    VERTEXAI_AVAILABLE = False

from agent_logging import get_logger
from agent_db import get_active_server_id, get_global_db
from agent_runtime import is_simulation_mode, increment_usage as runtime_increment_usage
from postprocessor import postprocess_response, is_blocked_response
from prompts_logger import log_agent_response, log_final_llm_prompt

logger = get_logger('agent_mind')

# Import bot display name for dynamic replacement
try:
    from discord_bot.discord_core_commands import _bot_display_name
except ImportError:
    # Fallback if discord is not available
    _bot_display_name = "Bot"

# Global cache for config
_CONFIG_CACHE = None

# Vertex AI configuration
_VERTEXAI_INITIALIZED = False
_VERTEXAI_CLIENT = None

def _get_config() -> dict:
    """Load and cache configuration from agent_config.json"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        config_path = os.path.join(os.path.dirname(__file__), 'agent_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            _CONFIG_CACHE = json.load(f)
    return _CONFIG_CACHE

def _get_max_tokens() -> int:
    """Get max_tokens from configuration or default"""
    config = _get_config()
    return config.get('llm', {}).get('max_tokens', 1024)

def _init_vertexai():
    """Initialize Vertex AI client using google-genai SDK"""
    global _VERTEXAI_INITIALIZED, _VERTEXAI_CLIENT
    if _VERTEXAI_INITIALIZED:
        return True

    # Check if Vertex AI is explicitly disabled
    vertex_ai_disabled = os.getenv('DISABLE_VERTEX_AI', '').strip().lower() in ('1', 'true', 'yes')
    if vertex_ai_disabled:
        logger.info("Vertex AI disabled by DISABLE_VERTEX_AI environment variable")
        return False

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    if not project:
        logger.warning("GOOGLE_CLOUD_PROJECT not set, Vertex AI will not be available")
        return False
    
    try:
        _VERTEXAI_CLIENT = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )
        _VERTEXAI_INITIALIZED = True
        logger.info(f"✅ Vertex AI (google-genai) initialized: project={project}, location={location}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize Vertex AI: {e}")
        return False


def _engine():
    import agent_engine
    return agent_engine


def _get_daily_memory_fallback() -> str:
    template = _engine().PERSONALITY.get("synthesis_paragraphs", {})
    fallbacks = template.get("fallbacks", {})
    fallback = fallbacks.get("daily_memory", "")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return "The character does not remember anything important from today."


def _get_recent_memory_fallback() -> str:
    template = _engine().PERSONALITY.get("synthesis_paragraphs", {})
    fallbacks = template.get("fallbacks", {})
    fallback = fallbacks.get("recent_memory", "")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return "The character feels calm, with no notable recent events."


def _get_daily_summary_task_lines() -> list[str]:
    synthesis = _engine().PERSONALITY.get("synthesis_paragraphs", {})
    task_lines = synthesis.get("daily_summary_task", [])
    if isinstance(task_lines, list) and task_lines:
        return [str(line).strip() for line in task_lines if str(line).strip()]
    return [
        "TASK: Update the long daily memory paragraph as the character's inner voice.",
        "OBJECTIVE: Merge the previous daily memory with the latest recent-memory paragraph from this day.",
        "NOTABLE MEMORY: If there's a 'NOTABLE MEMORY TO WEAVE IN' section, subtly weave that memory into the new daily memory paragraph.",
        "FORMAT: Return aproximetly a paragraph with 500 caracteres in this format:",
    ]


def _get_recent_summary_task_lines() -> list[str]:
    synthesis = _engine().PERSONALITY.get("synthesis_paragraphs", {})
    task_lines = synthesis.get("recent_memory_summary_task", [])
    if isinstance(task_lines, list) and task_lines:
        return [str(line).strip() for line in task_lines if str(line).strip()]
    return [
        "TASK: Update the short recent-memory paragraph as the character's inner voice.",
        "OBJECTIVE: Merge the previous recent-memory paragraph with the newly recorded events and interactions from the last hours.",
        "FORMAT: Return only one short paragraph, with no headings, no lists, and no quotes.",
        "STYLE: Stay fully in character and never speak as an assistant.",
    ]


def _get_relationship_summary_task_lines() -> list[str]:
    template = _engine()._get_user_prompt_template()
    task_lines = template.get("relationship_summary_task", [])
    if isinstance(task_lines, list) and task_lines:
        return [str(line).strip() for line in task_lines if str(line).strip()]
    return [
        "TASK: Update a single paragraph of internal memory about the character's relationship with this user.",
        "OBJECTIVE: Merge the previous synthesis with the new interactions and keep only the most important details.",
        "FORMAT: Return only one short paragraph, with no headings, no lists, and no quotes.",
        "STYLE: Stay fully in character and write as an inner voice.",
    ]


def _get_relationship_memory_fallback(user_name: str | None = None) -> str:
    template = _engine().PERSONALITY.get("synthesis_paragraphs", {})
    fallbacks = template.get("fallbacks", {})
    fallback = fallbacks.get("relationship_memory", "")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.replace("{user_name}", user_name or "human").strip()
    return f"The character does not yet have a clear opinion about {user_name or 'this human'}."


def _get_recent_dialogue_fallback() -> str:
    template = _engine().PERSONALITY.get("synthesis_paragraphs", {})
    fallbacks = template.get("fallbacks", {})
    fallback = fallbacks.get("recent_dialogue_fallback", "")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return "There has been no recent dialogue with this user."


def _build_configured_synthesis_prompt(
    prompt_key: str,
    fallback_instructions: list[str],
    replacements: dict[str, str],
    sections: list[tuple[str, str]],
    fallback_closing: str,
    dreaming_recollection: str | None = None,
) -> str:
    personality = _engine().PERSONALITY
    cfg = personality.get(prompt_key, {})
    instructions = cfg.get("instructions", []) if isinstance(cfg, dict) else []
    if not isinstance(instructions, list) or not instructions:
        instructions = fallback_instructions

    # Add sections FIRST (context content)
    processed = []
    for section_title, section_content in sections:
        processed.extend(["", section_title, section_content.strip()])
    
    # THEN add instructions (task) with dynamic format injection
    for i, inst in enumerate(instructions):
        line = str(inst)
        
        # Apply other replacements first
        for key, value in replacements.items():
            line = line.replace(f"{{{key}}}", str(value))
        
        # Inject format titles and placeholders after FORMATO line for recent memory summary
        if prompt_key == "prompt_recent_memory_summary" and line.strip().endswith("en este formato:"):
            # Get format components from synthesis_paragraphs with English fallbacks
            synthesis = personality.get("synthesis_paragraphs", {})
            formatting = synthesis.get("formatting", {})
            memory_title = formatting.get("memory_title", "---NEW_MEMORY---")
            memory_placeholder = formatting.get("memory_placeholder", "[new memory paragraph here]")
            recollection_title = formatting.get("recollection_title", "---EXTRACTED_MEMORY---")
            recollection_placeholder = formatting.get("recollection_placeholder", "[extracted notable phrase or NO_MEMORY]")
            
            # Replace variables in the current line too
            line = line.replace("{memory_title}", memory_title)
            line = line.replace("{memory_placeholder}", memory_placeholder)
            line = line.replace("{recollection_title}", recollection_title)
            line = line.replace("{recollection_placeholder}", recollection_placeholder)
            
            processed.append(line.strip())
            # Insert format components in compact format: ---NUEVA_MEMORIA---[placeholder]---RECUERDO_EXTRAIDO---[placeholder]
            compact_format = f"{memory_title}{memory_placeholder}{recollection_title}{recollection_placeholder}"
            processed.append(compact_format)
            continue  # Skip adding this line again
        
        processed.append(line.strip())

    closing = str(cfg.get("closing", "")).strip() if isinstance(cfg, dict) else ""
    if not closing:
        closing = fallback_closing
    if closing:
        for key, value in replacements.items():
            closing = closing.replace(f"{{{key}}}", str(value))
        processed.extend(["", closing.strip()])

    return "\n".join([line for line in processed if line])


def _build_last_dialogue_section(last_dialogue: list[dict]) -> str:
    if not last_dialogue:
        return _get_recent_dialogue_fallback()
    lines = []
    for item in last_dialogue[-10:]:
        human = str(item.get("humano", "")).strip()
        bot = str(item.get("bot", "")).strip()
        fecha = str(item.get("fecha", "")).strip()
        
        # Format timestamp to be more readable (take just the time part)
        timestamp = ""
        if fecha:
            try:
                # Parse ISO format and extract time
                from datetime import datetime
                dt = datetime.fromisoformat(fecha.replace('Z', '+00:00'))
                timestamp = dt.strftime('%H:%M')
            except:
                timestamp = fecha[:5] if len(fecha) >= 5 else fecha
        
        if human:
            if timestamp:
                lines.append(f'[{timestamp}] Umano: "{human}"')
            else:
                lines.append(f'Umano: "{human}"')
        if bot:
            if timestamp:
                lines.append(f'[{timestamp}] {_bot_display_name}: "{bot}"')
            else:
                lines.append(f'{_bot_display_name}: "{bot}"')
    return "\n".join(lines).strip() or _get_recent_dialogue_fallback()


def _format_daily_interactions_for_summary(interactions: list[dict]) -> str:
    if not interactions:
        return "No interactions were recorded for this day."
    lines = []
    for item in interactions[-25:]:
        interaction_type = str(item.get("tipo_interaccion", "")).strip() or "INTERACTION"
        user_name = str(item.get("usuario_nombre", "")).strip() or "human"
        context = str(item.get("contexto", "")).strip()
        response = str(item.get("respuesta", "")).strip()
        timestamp = str(item.get("fecha", "")).strip()
        lines.append(f"[{timestamp}] {interaction_type} | {user_name}")
        if context:
            lines.append(f"Human/Event: {context}")
        if response:
            lines.append(f"{_bot_display_name}: {response}")
        lines.append("")
    return "\n".join(lines).strip()


def _build_recent_memory_summary_prompt(previous_summary: str, interactions: list[dict], target_date: str) -> str:
    previous_block = previous_summary.strip() or _get_recent_memory_fallback()
    interactions_block = _format_daily_interactions_for_summary(interactions)
    return _build_configured_synthesis_prompt(
        prompt_key="prompt_recent_memory_summary",
        fallback_instructions=_get_recent_summary_task_lines(),
        replacements={"target_date": target_date},
        sections=[
            ("TARGET DATE:", target_date),
            ("PREVIOUS RECENT MEMORY:", previous_block),
            ("NEW EVENTS AND INTERACTIONS:", interactions_block),
        ],
        fallback_closing="",
    )


def _build_daily_summary_prompt(
    previous_summary: str,
    recent_memory: str,
    target_date: str,
    injected_memory: str | None = None,  # Kept for compatibility but will be ignored
    dreaming_recollection: str | None = None,
) -> str:
    # Get synthesis paragraph labels from personality JSON with English fallback
    synthesis_labels = _engine().PERSONALITY.get("synthesis_paragraphs", {})
    notable_memory_label = synthesis_labels.get("notable_recollection_to_weave_in", "NOTABLE RECOLLECTION TO WEAVE IN:")
    previous_daily_label = synthesis_labels.get("previous_daily_memory", "PREVIOUS DAILY MEMORY:")
    latest_recent_label = synthesis_labels.get("latest_recent_memory_of_the_day", "LATEST RECENT MEMORY OF THE DAY:")
    
    previous_block = previous_summary.strip() or _get_daily_memory_fallback()
    recent_block = recent_memory.strip() or _get_recent_memory_fallback()
    sections = [
        (previous_daily_label, previous_block),
        (latest_recent_label, recent_block),
    ]
    # Only use dreaming recollection, ignore injected_memory parameter
    if dreaming_recollection and dreaming_recollection.strip():
        sections.append((notable_memory_label, dreaming_recollection.strip()))
    return _build_configured_synthesis_prompt(
        prompt_key="prompt_daily_memory_summary",
        fallback_instructions=_get_daily_summary_task_lines(),
        replacements={"target_date": target_date},
        sections=sections,
        fallback_closing="",
        dreaming_recollection=dreaming_recollection,
    )


def _build_relationship_summary_prompt(previous_summary: str, new_interactions: list[dict], user_name: str | None, target_date: str) -> str:
    # Get synthesis paragraph labels from personality JSON with English fallback
    synthesis_labels = _engine().PERSONALITY.get("synthesis_paragraphs", {})
    target_user_label = synthesis_labels.get("target_user", "TARGET USER:")
    target_date_label = synthesis_labels.get("target_date", "TARGET DATE:")
    previous_relationship_label = synthesis_labels.get("previous_relationship_summary", "PREVIOUS RELATIONSHIP SUMMARY:")
    recent_interactions_label = synthesis_labels.get("recent_interactions", "RECENT INTERACTIONS:")
    
    previous_block = previous_summary.strip() or "No previous synthesis."
    
    # Format interactions directly (already filtered by caller)
    if not new_interactions:
        interactions_block = "There are no interactions to summarize."
    else:
        lines = []
        for item in new_interactions:
            timestamp = str(item.get("fecha", "")).strip()
            interaction_type = str(item.get("tipo_interaccion", "")).strip() or "INTERACTION"
            human = str(item.get("humano", "")).strip()
            bot = str(item.get("bot", "")).strip()
            
            # Format timestamp to be more readable
            formatted_time = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    formatted_time = dt.strftime('%H:%M')
                except:
                    formatted_time = timestamp[:5] if len(timestamp) >= 5 else timestamp
            
            lines.append(f"[{formatted_time}] {interaction_type}")
            if human:
                lines.append(f'Human: "{human}"')
            if bot:
                lines.append(f'{_bot_display_name}: "{bot}"')
            lines.append("")
        interactions_block = "\n".join(lines).strip()
    
    sections = [
        (target_user_label, user_name or "human"),
        (target_date_label, target_date),
        (previous_relationship_label, previous_block),
        (recent_interactions_label, interactions_block),
    ]
    return _build_configured_synthesis_prompt(
        prompt_key="prompt_relationship_memory_summary",
        fallback_instructions=_get_relationship_summary_task_lines(),
        replacements={"user_name": user_name or "human", "target_date": target_date},
        sections=sections,
        fallback_closing="Return only the new final relationship-memory paragraph.",
    )


def generate_recent_memory_summary(server_id: str | None = None, target_date: str | None = None, force: bool = False) -> str:
    engine = _engine()
    resolved_server = server_id or get_active_server_id()
    if not resolved_server:
        logger.warning("🧠 [RECENT_MEMORY] No server context available, skipping summary generation")
        return ""
    resolved_date = target_date or date.today().isoformat()
    db_instance = get_global_db(server_id=resolved_server)
    existing_record = db_instance.get_recent_memory_record(memory_date=resolved_date)
    previous_summary = (existing_record or {}).get("summary", "").strip()
    last_interaction_at = (existing_record or {}).get("last_interaction_at")
    interactions = db_instance.get_daily_interactions_since(
        since_iso=None if force else last_interaction_at,
        limit=100,
        target_date=resolved_date,
    )
    if not interactions:
        if previous_summary:
            return previous_summary
        # No interactions and no previous summary for today - try to find the most recent existing summary
        try:
            with db_instance._lock:
                import sqlite3
                conn = sqlite3.connect(db_instance.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT summary FROM recent_memory 
                    WHERE summary IS NOT NULL AND summary != '' 
                    ORDER BY updated_at DESC LIMIT 1
                """)
                result = cursor.fetchone()
                conn.close()
                
                if result and result[0] and result[0].strip():
                    # Found existing summary, use it without saving
                    existing_summary = result[0].strip()
                    logger.info(f"🧠 [RECENT_MEMORY] No interactions, using existing summary from history")
                    return existing_summary
        except Exception as e:
            logger.debug(f"Could not retrieve existing recent memory: {e}")
        
        # No existing summary found, use fallback but don't save it
        fallback = _get_recent_memory_fallback()
        logger.info(f"🧠 [RECENT_MEMORY] No interactions and no existing summary, using fallback without saving")
        return fallback

    system_instruction = engine._build_system_prompt(engine.PERSONALITY)
    summary_prompt = _build_recent_memory_summary_prompt(previous_summary, interactions, resolved_date)
    summary_response = call_llm(
        system_instruction=system_instruction,
        prompt=summary_prompt,
        async_mode=True,
        call_type="recent_memory",
        critical=False,
        server_id=resolved_server
    )
    
    # Extract new memory and notable recollection from response
    new_memory_text, extracted_recollection = _extract_memory_from_summary(summary_response or "")
    
    # Only update if LLM successfully generated new content (not error messages)
    if new_memory_text and new_memory_text.strip() and new_memory_text != "[Error in internal task]":
        # LLM succeeded, use the new memory
        summary_text = new_memory_text.strip()
        
        latest_interaction_at = interactions[-1].get("fecha") or last_interaction_at
        db_instance.upsert_recent_memory(
            summary_text,
            memory_date=resolved_date,
            last_interaction_at=latest_interaction_at,
            metadata={
                "source": "llm_recent_memory_summary",
                "interaction_count": len(interactions),
                "generated_at": datetime.now().isoformat(),
                "recollection_extracted": bool(extracted_recollection and extracted_recollection != "NO_MEMORY"),
            },
        )
        logger.info(f"🧠 [RECENT_MEMORY] Updated summary for {resolved_server} on {resolved_date} ({len(interactions)} interactions, extracted: {bool(extracted_recollection and extracted_recollection != 'NO_MEMORY')})")
    else:
        # LLM failed or returned error, keep existing summary unchanged
        summary_text = previous_summary or _get_recent_memory_fallback()
        logger.info(f"🧠 [RECENT_MEMORY] LLM failed, keeping existing summary for {resolved_server} on {resolved_date}")
    
    # Store extracted recollection if present (even if memory update failed)
    if extracted_recollection and extracted_recollection != "NO_MEMORY":
        recollection_id = db_instance.add_notable_recollection(
            recollection_text=extracted_recollection,
            memory_date=resolved_date,
            source_paragraph=previous_summary[:500] if previous_summary else None,  # Store first 500 chars as context
        )
        if recollection_id:
            logger.info(f"🧠 [RECENT_MEMORY] Extracted and stored notable recollection: '{extracted_recollection[:60]}...'")
    db_instance.mark_recent_memory_refresh_completed()
    
    return summary_text


def refresh_due_recent_memories(server_id: str | None = None) -> int:
    """Refresh recent memories for a server or all servers if none specified."""
    if server_id:
        # Process specific server
        resolved_server = server_id
        db_instance = get_global_db(server_id=resolved_server)
        due_refreshes = db_instance.get_due_pending_recent_memory_refreshes()
        if not due_refreshes:
            return 0
        
        # Get last synthesis to check for new interactions
        existing_record = db_instance.get_recent_memory_record(memory_date=date.today().isoformat())
        last_interaction_at = (existing_record or {}).get("last_interaction_at")
        new_interactions = db_instance.get_daily_interactions_since(
            since_iso=last_interaction_at,
            limit=100,
            target_date=date.today().isoformat(),
        )
        
        if not new_interactions:
            logger.info(f"🧠 [RECENT_MEMORY] No new interactions since last synthesis for {resolved_server}")
            db_instance.mark_recent_memory_refresh_completed()
            return 0
        
        # Execute synthesis only if there are new interactions
        logger.info(f"🧠 [RECENT_MEMORY] Processing {len(new_interactions)} new interactions for {resolved_server}")
        generate_recent_memory_summary(server_id=resolved_server)
        return 1
    else:
        # Process all servers
        from agent_db import get_all_server_ids
        server_ids = get_all_server_ids()
        total_processed = 0
        for sid in server_ids:
            total_processed += refresh_due_recent_memories(sid)
        return total_processed


def _should_trigger_dreaming(db_instance) -> bool:
    """Determine if dreaming should be triggered based on recollection count and probability.
    
    - If fewer than 5 recollections: 5% chance
    - If 5-19 recollections: 10% chance  
    - If 20+ recollections: 20% chance
    """
    import random
    recollection_count = db_instance.count_notable_recollections()
    if recollection_count == 0:
        return False
    if recollection_count < 5:
        return random.random() < 0.05  # 5% chance
    elif recollection_count < 20:
        return random.random() < 0.10  # 10% chance
    return random.random() < 0.20  # 20% chance


def _get_random_recollection_for_injection(db_instance) -> tuple[str | None, int | None]:
    """Get a random notable recollection for injection and increment its usage count.
    
    Returns:
        Tuple of (recollection_text, recollection_id) or (None, None) if no recollections exist
    """
    recollection = db_instance.get_random_notable_recollection()
    if not recollection:
        return None, None
    recollection_id = recollection.get("id")
    recollection_text = recollection.get("recollection_text")
    if recollection_id:
        db_instance.increment_recollection_usage(recollection_id)
    return recollection_text, recollection_id


def _extract_memory_from_summary(summary_response: str) -> tuple[str, str | None]:
    """Extract the new memory paragraph and notable recollection from LLM response.
    
    Uses titles from personality JSON with English fallbacks.
    Captures content AFTER each marker, not the markers themselves.
    
    Returns:
        Tuple of (new_memory_text, extracted_recollection or None)
    """
    import re
    
    if not summary_response:
        return "", None
    
    # Get titles from personality JSON with English fallbacks
    personality = _engine().PERSONALITY
    recent_cfg = personality.get("prompt_recent_memory_summary", {})
    
    # Get titles from synthesis_paragraphs or use English fallbacks
    synthesis = personality.get("synthesis_paragraphs", {})
    formatting = synthesis.get("formatting", {})
    memory_title = formatting.get("memory_title", "---NEW_MEMORY---")
    recollection_title = formatting.get("recollection_title", "---EXTRACTED_RECOLLECTION---")
    no_memory_keyword = formatting.get("no_memory_keyword", "NO_RECOLLECTION")
    
    # English fallbacks
    memory_title_en = "---NEW_MEMORY---"
    recollection_title_en = "---EXTRACTED_RECOLLECTION--"
    no_memory_keyword_en = "NO_RECOLLECTION"
    
    # Try personality format first - capture content AFTER markers
    pattern = rf"{re.escape(memory_title)}\s*(.*?)\s*{re.escape(recollection_title)}\s*(.*?)\s*(?:\n|$)"
    match = re.search(pattern, summary_response, re.DOTALL | re.IGNORECASE)
    
    if not match:
        # Try English fallback
        pattern = rf"{re.escape(memory_title_en)}\s*(.*?)\s*{re.escape(recollection_title_en)}\s*(.*?)\s*(?:\n|$)"
        match = re.search(pattern, summary_response, re.DOTALL | re.IGNORECASE)
    
    if match:
        new_memory = match.group(1).strip()
        extracted = match.group(2).strip()
        
        # Check if extracted matches no memory keyword (from JSON or fallback)
        if extracted.upper() in [no_memory_keyword.upper(), no_memory_keyword_en.upper(), "NO MEMORY", "NONE", "", "NO_MEMORIA", "NO MEMORIA", "NO_RECOLLECTION"]:
            return new_memory, None
        return new_memory, extracted
    
    # If no structured format found, try to extract content after memory title only
    # First try compact format: ---NUEVA_MEMORIA---(content)---RECUERDO_EXTRAIDO---(content)
    compact_patterns = [
        rf"{re.escape(memory_title)}\s*(.*?)\s*{re.escape(recollection_title)}\s*(.*?)(?:\n|$|\Z)",
        rf"{re.escape(memory_title_en)}\s*(.*?)\s*{re.escape(recollection_title_en)}\s*(.*?)(?:\n|$|\Z)"
    ]
    
    for pattern in compact_patterns:
        match = re.search(pattern, summary_response, re.DOTALL | re.IGNORECASE)
        if match:
            new_memory = match.group(1).strip()
            extracted = match.group(2).strip()
            
            # Clean any remaining markers within the content
            new_memory = re.sub(rf"{re.escape(memory_title)}\s*", "", new_memory, flags=re.IGNORECASE)
            new_memory = re.sub(rf"{re.escape(recollection_title)}\s*", "", new_memory, flags=re.IGNORECASE)
            new_memory = re.sub(rf"{re.escape(memory_title_en)}\s*", "", new_memory, flags=re.IGNORECASE)
            new_memory = re.sub(rf"{re.escape(recollection_title_en)}\s*", "", new_memory, flags=re.IGNORECASE)
            
            extracted = re.sub(rf"{re.escape(memory_title)}\s*", "", extracted, flags=re.IGNORECASE)
            extracted = re.sub(rf"{re.escape(recollection_title)}\s*", "", extracted, flags=re.IGNORECASE)
            extracted = re.sub(rf"{re.escape(memory_title_en)}\s*", "", extracted, flags=re.IGNORECASE)
            extracted = re.sub(rf"{re.escape(recollection_title_en)}\s*", "", extracted, flags=re.IGNORECASE)
            
            # Check if extracted matches no memory keyword
            if extracted.upper() in [no_memory_keyword.upper(), no_memory_keyword_en.upper(), "NO MEMORY", "NONE", "", "NO_MEMORIA", "NO MEMORIA", "NO_RECOLLECTION"]:
                return new_memory, None
            return new_memory, extracted
    
    # If still no match, fall back to memory-only extraction
    fallback_patterns = [
        rf"{re.escape(memory_title)}\s*(.*?)(?:\n---|\Z)",
        rf"{re.escape(memory_title_en)}\s*(.*?)(?:\n---|\Z)"
    ]
    
    for pattern in fallback_patterns:
        match = re.search(pattern, summary_response, re.DOTALL | re.IGNORECASE)
        if match:
            content = match.group(1).strip()
            # Remove any remaining markers that might be within the content
            content = re.sub(rf"{re.escape(memory_title)}\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(rf"{re.escape(recollection_title)}\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(rf"{re.escape(memory_title_en)}\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(rf"{re.escape(recollection_title_en)}\s*", "", content, flags=re.IGNORECASE)
            if content and len(content) > 10:  # Only return if substantial content
                return content.strip(), None
    
    # Last resort: return cleaned response (remove any markers and get content)
    # Split by markers and get the first substantial content
    content_parts = re.split(r"---[A-Z_]+---\s*", summary_response)
    for part in content_parts:
        cleaned = part.strip()
        if cleaned and len(cleaned) > 10:  # Only return if substantial content
            return cleaned, None
    
    return "", None


def generate_daily_memory_summary(server_id: str | None = None, target_date: str | None = None, force: bool = False) -> str:
    engine = _engine()
    resolved_server = server_id or get_active_server_id()
    if not resolved_server:
        logger.warning("🧠 [DAILY_MEMORY] No server context available, skipping summary generation")
        return ""
    resolved_date = target_date or date.today().isoformat()
    from agent_db import get_db_instance
    db_instance = get_db_instance(resolved_server)
    
    # Get the most recent daily memory (not just today's)
    most_recent_daily = db_instance.get_most_recent_daily_memory_record()
    previous_summary = (most_recent_daily or {}).get("summary", "").strip()
    
    # Get the most recent memory record (regardless of date)
    recent_record = db_instance.get_most_recent_memory_record()
    recent_summary = (recent_record or {}).get("summary", "").strip()
    
    # Apply fallback logic only for first instances
    if not previous_summary:
        previous_summary = _get_daily_memory_fallback()
        logger.info(f"🧠 [DAILY_MEMORY] First instance - no daily memory found, using daily fallback")
    else:
        logger.info(f"🧠 [DAILY_MEMORY] Using previous daily memory from {most_recent_daily.get('memory_date', 'unknown')}")
    
    if not recent_summary:
        recent_summary = _get_recent_memory_fallback()
        logger.info(f"🧠 [DAILY_MEMORY] First instance - no recent memory found, using recent fallback")
    else:
        logger.info(f"🧠 [DAILY_MEMORY] Using recent memory from {recent_record.get('memory_date', 'unknown')}")
    
    # Now we always have both memories to combine
    logger.info(f"🧠 [DAILY_MEMORY] Combining daily memory + recent memory")
    
    # Determine if we should inject a random recollection
    recollection_count = db_instance.count_notable_recollections()
    
    # Use dreaming mechanism only for recollection injection
    dreaming_recollection = None
    
    # Use proper dreaming probability logic
    if _should_trigger_dreaming(db_instance):
        # Only use database recollections for dreaming
        dreaming_recollection, _ = _get_random_recollection_for_injection(db_instance)
        if dreaming_recollection:
            logger.info(f"🧠 [DAILY_MEMORY] DREAMING TRIGGERED - Using database recollection ({recollection_count} total)")
        else:
            logger.info(f"🧠 [DAILY_MEMORY] DREAMING TRIGGERED - No recollection available in database")
    else:
        logger.info(f"🧠 [DAILY_MEMORY] No dreaming triggered (recollections: {recollection_count})")
    
    system_instruction = engine._build_system_prompt(engine.PERSONALITY)
    summary_prompt = _build_daily_summary_prompt(previous_summary, recent_summary, resolved_date, None, dreaming_recollection)
    summary_response = call_llm(
        system_instruction=system_instruction,
        prompt=summary_prompt,
        async_mode=True,
        call_type="daily_memory",
        critical=False,
        server_id=resolved_server
    )
    
    # Extract new memory (no extraction for daily memory now)
    llm_response = (summary_response or "").strip()
    
    # Only update if LLM successfully generated new content (not error messages)
    if llm_response and llm_response != "[Error in internal task]":
        # LLM succeeded, use the new memory
        summary_text = llm_response
        
        # Attempt to save to database
        save_success = db_instance.upsert_daily_memory(
            summary_text,
            memory_date=resolved_date,
            metadata={
                "source": "llm_daily_summary",
                "recent_memory_used": bool(recent_summary),
                "generated_at": datetime.now().isoformat(),
                "recollection_injected": bool(dreaming_recollection),
                "dreaming_triggered": bool(dreaming_recollection),
                "memory_extracted": False,  # Daily memory no longer extracts memories
            },
        )
        
        if save_success:
            logger.info(f"🧠 [DAILY_MEMORY] Updated summary for {resolved_server} on {resolved_date} (recollections: {recollection_count}, dreaming: {bool(dreaming_recollection)})")
        else:
            logger.error(f"🧠 [DAILY_MEMORY] FAILED to save summary for {resolved_server} on {resolved_date} - database error occurred")
    else:
        # LLM failed or returned error, keep existing summary unchanged
        if previous_summary:
            summary_text = previous_summary
        else:
            # No today's summary and LLM failed - try to find the most recent existing summary
            try:
                with db_instance._lock:
                    import sqlite3
                    conn = sqlite3.connect(db_instance.db_path)
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT summary FROM daily_memory 
                        WHERE summary IS NOT NULL AND summary != '' AND summary != '[Error in internal task]'
                        ORDER BY updated_at DESC LIMIT 1
                    """)
                    result = cursor.fetchone()
                    conn.close()
                    
                    if result and result[0] and result[0].strip():
                        # Found existing summary, use it
                        summary_text = result[0].strip()
                        logger.info(f"🧠 [DAILY_MEMORY] LLM failed, using existing daily summary from history")
                    else:
                        # No existing summary found, use fallback
                        summary_text = _get_daily_memory_fallback()
                        logger.info(f"🧠 [DAILY_MEMORY] LLM failed and no existing summary, using fallback")
            except Exception as e:
                logger.debug(f"Could not retrieve existing daily memory: {e}")
                summary_text = _get_daily_memory_fallback()
        
        logger.info(f"🧠 [DAILY_MEMORY] LLM failed, keeping existing summary for {resolved_server} on {resolved_date}")
        
        # CRITICAL FIX: Save the fallback/previous summary to database even when LLM fails
        # This ensures bootstrap processes don't fail silently
        save_success = db_instance.upsert_daily_memory(
            summary_text,
            memory_date=resolved_date,
            metadata={
                "source": "llm_failed_fallback",
                "recent_memory_used": bool(recent_summary),
                "generated_at": datetime.now().isoformat(),
                "recollection_injected": bool(dreaming_recollection),
                "dreaming_triggered": bool(dreaming_recollection),
                "memory_extracted": False,
                "llm_failed": True,
            },
        )
        
        if save_success:
            logger.info(f"🧠 [DAILY_MEMORY] Saved fallback summary for {resolved_server} on {resolved_date}")
        else:
            logger.error(f"🧠 [DAILY_MEMORY] FAILED to save fallback summary for {resolved_server} on {resolved_date} - database error occurred")
    
    return summary_text


def _build_daily_memory_text(db_instance) -> str:
    stored = db_instance.get_daily_memory().strip()
    return stored or _get_daily_memory_fallback()


def _build_recent_memory_text(db_instance) -> str:
    record = db_instance.get_recent_memory_record()
    if record and record.get("summary", "").strip():
        return record["summary"].strip()
    return _get_recent_memory_fallback()


def generate_user_relationship_memory_summary(
    user_id,
    user_name: str | None = None,
    server_id: str | None = None,
    target_date: str | None = None,
    force: bool = False,
) -> str:
    import datetime
    engine = _engine()
    resolved_server = server_id or get_active_server_id()
    if not resolved_server:
        logger.warning(f"🧠 [RELATIONSHIP_MEMORY] No server context available for user={user_id}")
        return ""
    resolved_date = target_date or date.today().isoformat()
    db_instance = get_global_db(server_id=resolved_server)
    temporary_state = db_instance.get_user_relationship_memory(user_id)
    daily_record = db_instance.get_user_relationship_daily_memory(user_id, memory_date=resolved_date)
    previous_summary = (temporary_state.get("summary") or "").strip()
    if not previous_summary and daily_record:
        previous_summary = (daily_record.get("summary") or "").strip()
    if not previous_summary:
        latest_daily = db_instance.get_latest_user_relationship_daily_memory(user_id, before_date=resolved_date)
        if latest_daily:
            previous_summary = (latest_daily.get("summary") or "").strip()

    last_interaction_at = temporary_state.get("last_interaction_at")
    new_interactions = db_instance.get_user_interactions_since(user_id, since_iso=last_interaction_at, limit=100)
    if not new_interactions and not force:
        # Check if we have any existing relationship memory (temporary or daily)
        has_existing_memory = False
        existing_summary = previous_summary
        
        # Also check the current temporary state as a backup
        if not existing_summary:
            current_temp = db_instance.get_user_relationship_memory(user_id)
            existing_summary = current_temp.get("summary", "").strip()
            if existing_summary:
                has_existing_memory = True
        
        # If we have existing memory, preserve it - don't overwrite with fallback
        if existing_summary and existing_summary.strip():
            logger.info(f"🧠 [RELATIONSHIP_MEMORY] Preserving existing memory for user={user_id} server={resolved_server}")
            # Update the temporary state to ensure it's current
            db_instance.upsert_user_relationship_memory(
                user_id,
                existing_summary,
                last_interaction_at=last_interaction_at,
                metadata={"user_name": user_name or "", "source": "preserved_existing"},
            )
            return existing_summary
        
        # Only use fallback if user truly has no relationship history
        fallback = _get_relationship_memory_fallback(user_name)
        logger.info(f"🧠 [RELATIONSHIP_MEMORY] Using fallback for new user={user_id} server={resolved_server}")
        db_instance.upsert_user_relationship_memory(
            user_id,
            fallback,
            last_interaction_at=last_interaction_at,
            metadata={"user_name": user_name or "", "source": "initial_relationship_fallback"},
        )
        return fallback

    if force and not new_interactions:
        # Get interactions from last 1 hour with max 100 pairs
        one_hour_ago = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
        new_interactions = db_instance.get_user_interactions_since(user_id, since_iso=one_hour_ago, limit=100)

    system_instruction = engine._build_system_prompt(engine.PERSONALITY)
    summary_prompt = _build_relationship_summary_prompt(previous_summary, new_interactions, user_name, resolved_date)
    summary_response = call_llm(
        system_instruction=system_instruction,
        prompt=summary_prompt,
        async_mode=True,
        call_type="relationship_memory",
        critical=False,
        server_id=resolved_server
    )
    llm_response = (summary_response or "").strip()
    
    # Only update if LLM successfully generated new content (not error messages)
    if llm_response and llm_response != "[Error in internal task]":
        # LLM succeeded, use the new memory
        summary_text = llm_response
        
        latest_interaction_at = last_interaction_at
        if new_interactions:
            latest_interaction_at = new_interactions[-1].get("fecha") or last_interaction_at

        metadata = {
            "user_name": user_name or "",
            "source": "llm_relationship_summary",
            "interaction_count": len(new_interactions),
            "generated_at": datetime.datetime.now().isoformat(),
        }
        db_instance.upsert_user_relationship_memory(
            user_id,
            summary_text,
            last_interaction_at=latest_interaction_at,
            metadata=metadata,
        )
        db_instance.upsert_user_relationship_daily_memory(
            user_id,
            summary_text,
            memory_date=resolved_date,
            metadata=metadata,
        )
        db_instance.mark_relationship_refresh_completed(user_id)
        logger.info(f"🧠 [RELATIONSHIP_MEMORY] Updated summary for user={user_id} server={resolved_server} date={resolved_date}")
    else:
        # LLM failed or returned error, preserve existing summary
        if previous_summary and previous_summary.strip():
            summary_text = previous_summary
            logger.info(f"🧠 [RELATIONSHIP_MEMORY] LLM failed, preserving existing summary for user={user_id} server={resolved_server}")
            # Update database with preserved summary to ensure Canvas can retrieve it
            db_instance.upsert_user_relationship_memory(
                user_id,
                summary_text,
                last_interaction_at=last_interaction_at,
                metadata={"user_name": user_name or "", "source": "preserved_after_llm_failure"},
            )
            db_instance.upsert_user_relationship_daily_memory(
                user_id,
                summary_text,
                memory_date=resolved_date,
                metadata={"user_name": user_name or "", "source": "preserved_after_llm_failure"},
            )
        else:
            # Only use fallback if there truly was no previous summary
            summary_text = _get_relationship_memory_fallback(user_name)
            logger.warning(f"🧠 [RELATIONSHIP_MEMORY] LLM failed and no existing summary, using fallback for user={user_id} server={resolved_server}")
            # Save fallback to database so Canvas can retrieve it
            db_instance.upsert_user_relationship_memory(
                user_id,
                summary_text,
                last_interaction_at=last_interaction_at,
                metadata={"user_name": user_name or "", "source": "fallback_after_llm_failure"},
            )
            db_instance.upsert_user_relationship_daily_memory(
                user_id,
                summary_text,
                memory_date=resolved_date,
                metadata={"user_name": user_name or "", "source": "fallback_after_llm_failure"},
            )
        db_instance.mark_relationship_refresh_completed(user_id)
    
    return summary_text


def refresh_due_relationship_memories(server_id: str | None = None) -> int:
    """Refresh relationship memories for a server or all servers if none specified."""
    if server_id:
        # Process specific server
        resolved_server = server_id
        db_instance = get_global_db(server_id=resolved_server)
        due_refreshes = db_instance.get_due_pending_relationship_refreshes()
        processed = 0
        for item in due_refreshes:
            user_id = item.get("usuario_id")
            if not user_id:
                continue
            relationship_state = db_instance.get_user_relationship_memory(user_id)
            user_name = relationship_state.get("metadata", {}).get("user_name") or None
            last_interaction_at = relationship_state.get("last_interaction_at")
            new_interactions = db_instance.get_user_interactions_since(user_id, since_iso=last_interaction_at, limit=100)
            if not new_interactions:
                db_instance.mark_relationship_refresh_completed(user_id)
                continue
            try:
                generate_user_relationship_memory_summary(
                    user_id=user_id,
                    user_name=user_name,
                    server_id=resolved_server,
                )
                processed += 1
            except Exception as e:
                logger.warning(f" [RELATIONSHIP_MEMORY] Scheduled refresh failed for user={user_id}: {e}")
        deleted = db_instance.clear_stale_relationship_memory_states()
        if deleted:
            logger.info(f" [RELATIONSHIP_MEMORY] Cleaned up {deleted} stale relationship memory states")
        return processed
    else:
        # Process all servers
        from agent_db import get_all_server_ids
        server_ids = get_all_server_ids()
        total_processed = 0
        for sid in server_ids:
            total_processed += refresh_due_relationship_memories(sid)
        return total_processed


def _refresh_relationship_memory_if_due(db_instance, user_id, user_name, recent_dialogue: list[dict]) -> str:
    relationship_state = db_instance.get_user_relationship_memory(user_id)
    daily_record = db_instance.get_user_relationship_daily_memory(user_id)
    summary = relationship_state.get("summary", "").strip()
    if summary:
        logger.debug(f"🧠 [RELATIONSHIP_MEMORY] Using existing temporary summary for user={user_id}")
        return summary
    if daily_record and daily_record.get("summary", "").strip():
        summary = daily_record["summary"].strip()
        logger.debug(f"🧠 [RELATIONSHIP_MEMORY] Restoring from daily snapshot for user={user_id}")
        db_instance.upsert_user_relationship_memory(
            user_id,
            summary,
            last_interaction_at=relationship_state.get("last_interaction_at"),
            metadata={"user_name": user_name or "", "source": "daily_snapshot_restore"},
        )
        return summary
    
    # Only use fallback if user truly has no relationship history
    logger.info(f"🧠 [RELATIONSHIP_MEMORY] No existing memory found, using fallback for new user={user_id}")
    fallback = _get_relationship_memory_fallback(user_name)
    db_instance.upsert_user_relationship_memory(
        user_id,
        fallback,
        last_interaction_at=relationship_state.get("last_interaction_at"),
        metadata={"user_name": user_name or "", "source": "initial_fallback"},
    )
    return fallback


def _apply_role_specific_content_overrides(prompt_final: str, user_message: str) -> str:
    """Apply role-specific content overrides. If role has its own rules, skip general ones.
    
    Logic:
    - If role has its own golden rules → keep role's rules, skip general ones
    - If role has no golden rules → use general rules with custom title
    - Extensible for future roles
    """
    lines = prompt_final.split('\n')
    cleaned_lines = []
    skip_section = False
    
    # Define role-specific content patterns
    role_content_config = {
        # News Watcher specific patterns
        "## NEWS WATCHER GOLDEN RULES": {
            "skip_patterns": [
                "## GOLDEN RULES OF THIS RESPONSE:",
                "ACTIVE MISSION - BEGGAR",
                "CHAT DETECTION - BEGGAR"
            ],
            "description": "News Watcher has its own golden rules"
        },
        # Add more roles here as needed
        # "## BANKER RULES": {
        #     "skip_patterns": ["## GOLDEN RULES OF THIS RESPONSE:", "OTHER_MISSION"],
        #     "description": "Banker has its own rules"
        # }
    }
    
    # Check if any role-specific pattern is present
    active_role_pattern = None
    for pattern in role_content_config.keys():
        if pattern in user_message:
            active_role_pattern = pattern
            break
    
    # If no role-specific pattern, add general response rules
    if not active_role_pattern:
        # Get custom title for general rules
        try:
            from agent_engine import PERSONALITY
            prompt_labels = PERSONALITY.get("prompt_labels", {})
            response_rules_title = prompt_labels.get("response_rules_title", "## RESPONSE RULES:")
            
            # Add general response rules at the end
            # Note: We can't access _get_response_rules_lines without the engine instance
            # This is a fallback - the rules will be added by the engine itself
        except ImportError:
            response_rules_title = "## RESPONSE RULES:"
    
    # Get the actual response rules title from JSON for dynamic matching
    try:
        from agent_engine import PERSONALITY
        prompt_labels = PERSONALITY.get("prompt_labels", {})
        actual_response_rules_title = prompt_labels.get("response_rules_title", "## RESPONSE RULES:")
    except ImportError:
        actual_response_rules_title = "## RESPONSE RULES:"
    
    for line in lines:
        should_skip = False
        
        if active_role_pattern:
            config = role_content_config[active_role_pattern]
            
            # Skip patterns defined for this role
            for skip_pattern in config["skip_patterns"]:
                if skip_pattern in line:
                    should_skip = True
                    if actual_response_rules_title in line:
                        skip_section = True
                    break
            
            # Skip response rule items when in rules section
            if skip_section and line.strip().startswith('- '):
                should_skip = True
            elif skip_section and not line.strip().startswith('- ') and line.strip():
                skip_section = False
        
        if not should_skip:
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def _build_prompt_memory_block(server=None):
    """
    Build only the MEMORIES block with daily and recent memory.
    This function is now focused solely on basic memory construction.
    """
    # Use the server parameter or get the active server
    server_id = server or get_active_server_id()
    if not server_id:
        logger.warning("🧠 [MIND] No server context available, skipping memory-backed prompt enrichment")
        return ""
    
    db_instance = get_global_db(server_id=server_id)
    
    daily_memory = ""
    recent_memory = ""
    if db_instance:
        daily_memory = _build_daily_memory_text(db_instance)
        recent_memory = _build_recent_memory_text(db_instance)
    
    # Get custom prompt labels from personality JSON
    engine = _engine()
    synthesis_labels = engine.PERSONALITY.get("synthesis_paragraphs", {})
    memory_title = synthesis_labels.get("memory_title", "MEMORY:")
    memories_label = synthesis_labels.get("memories_label", "[MEMORIES]")
    recent_memories_label = synthesis_labels.get("recent_memories_label", "[RECENT MEMORIES]")
    
    # Build MEMORIES block (only daily and recent)
    memories_block = []
    
    # Memory section
    if daily_memory:
        memories_block.append(memories_label)
        memories_block.append(memory_title)
        memories_block.append(daily_memory)
    
    # Recent memory section
    if recent_memory:
        memories_block.append(recent_memories_label)
        memories_block.append(recent_memory)
    
    return "\n".join(memories_block) if memories_block else ""


def _build_prompt_relationship_block(user_id: str, user_name: str | None = None, server: str | None = None):
    """
    Build only the RELATIONSHIP block with user relationship memory.
    This function is now focused solely on relationship construction.
    """
    server_id = server or get_active_server_id()
    db_instance = get_global_db(server_id=server_id) if server_id else None
    
    if not db_instance:
        return ""
    
    relationship_memory = _refresh_relationship_memory_if_due(db_instance, user_id, user_name, [])
    if not relationship_memory:
        return ""
    
    # Get relationship label from personality
    engine = _engine()
    relationship_title = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("relationship_title", "[RELATIONSHIP]")
    
    # Build RELATIONSHIP block
    relationship_block = [
        relationship_title,
        relationship_memory
    ]
    
    return "\n".join(relationship_block)


def _build_conversation_user_prompt(
    user_id: str,
    user_content: str = "",
    server: str | None = None,
    user_name: str | None = None,
) -> str:
    """
    Build a contextual user prompt using the specialized _build_prompt_memory_block.
    This function constructs the complete user prompt including memories, rules, and message.
    """
    # Get memories block from the focused memory function
    memories_block = _build_prompt_memory_block(server=server)
    
    # Get database instance for memory retrieval
    server_id = server or get_active_server_id()
    db_instance = get_global_db(server_id=server_id) if server_id else None
    
    # Build the complete prompt sections
    prompt_sections = []
    
    # Add memories block if available
    if memories_block:
        prompt_sections.append(memories_block)
    
    # Add relationship memory block
    relationship_block = _build_prompt_relationship_block(user_id=user_id, user_name=user_name, server=server)
    if relationship_block:
        prompt_sections.append(relationship_block)
    
    # Add recent interactions block
    recent_interactions_block = _build_prompt_last_interactions_block(user_id=user_id, server=server)
    if recent_interactions_block:
        prompt_sections.append(recent_interactions_block)
        prompt_sections.append("-" * 45)
    
    # Add golden rules from personality or fallback to English
    engine = _engine()
    golden_rules = engine.PERSONALITY.get("behaviors", {}).get("conversation", {}).get("golden_rules", [])
    if not golden_rules:
        # English fallback golden rules
        golden_rules = [
            "## RESPONSE RULES:",
            "1. LENGTH: 1-3 sentences (25-200 characters).",
            "2. GRAMMAR: No accents.",
            "3. Don't end sentences with single words like 'that', 'of', 'to'.",
            "4. Don't repeat what you've said, be original and creative, but stay an orc."
        ]
    
    # Add golden rules section
    if golden_rules:
        for rule in golden_rules:
            prompt_sections.append(str(rule).strip())
        # Add separator after golden rules
        prompt_sections.append("-" * 45)
    
    # Add user message
    message_title = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("message_title", "## A USER NAMED {user_name} TELL YOU:")
    message_title = message_title.replace("{user_name}", user_name)
    prompt_sections.append(message_title)
    prompt_sections.append(user_content or "")
    
    # Add memory retrieval if user asks about memories
    if db_instance and user_content:
        retrieved_memory = _detect_and_retrieve_memory(user_content, db_instance, user_id)
        if retrieved_memory:
            memory_retrieval_title = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("memory_retrieval_title", "[THIS REMINDS YOU THAT:]")
            prompt_sections.append(memory_retrieval_title)
            prompt_sections.append(retrieved_memory)
            prompt_sections.append("-" * 45)
    
    response_title = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("response_title", "## ANSWER WITH THE WORDS OF THE PERSONALITY:")
    prompt_sections.append(response_title)
    return "\n".join(prompt_sections)


def _build_prompt_last_interactions_block(
    user_id: str,
    server: str | None = None,
):
    """
    Build only the LAST INTERACTIONS block with user's last 15 dialogue messages.
    This function is now focused solely on last interactions construction regardless of time window.
    """
    server_id = server or get_active_server_id()
    db_instance = get_global_db(server_id=server_id) if server_id else None
    
    if not db_instance:
        return ""
    
    last_interactions = db_instance.get_last_dialogue_window(user_id, max_messages=15)
    if not last_interactions:
        return ""
    
    last_interactions_text = _build_last_dialogue_section(last_interactions)
    if not last_interactions_text:
        return ""
    
    # Get last interactions label from personality
    engine = _engine()
    last_interactions_label = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("last_interactions_label", "[RECENT INTERACTIONS]")
    
    # Build LAST INTERACTIONS block
    interactions_block = [
        last_interactions_label,
        last_interactions_text
    ]
    
    return "\n".join(interactions_block)


async def _build_prompt_channel_messages_block(
    channel_id: str,
    server: str | None = None,
    discord_channel=None,
    bot_id: str | None = None,
):
    """
    Build only the CHANNEL MESSAGES block with recent channel interactions.
    This function now fetches messages directly from Discord API.
    """
    logger.info(f"🧠 [MIND] _build_prompt_channel_messages_block called with channel_id={channel_id}, discord_channel={'provided' if discord_channel else 'None'}")
    
    # If we have a Discord channel object, fetch messages directly from Discord
    if discord_channel and hasattr(discord_channel, 'history'):
        logger.info(f"🧠 [MIND] Loading recent messages from Discord channel {channel_id}")
        logger.info(f"🧠 [MIND] Discord channel object: {type(discord_channel)}, name: {getattr(discord_channel, 'name', 'Unknown')}")
        
        try:
            # Fetch last 20 messages from Discord (more than we need to filter)
            messages = []
            message_count = 0
            logger.info(f"🧠 [MIND] Starting to fetch Discord messages from {getattr(discord_channel, 'name', 'Unknown')} channel")
            
            async for message in discord_channel.history(limit=20):
                message_count += 1
                logger.info(f"🧠 [MIND] Processing message #{message_count}: {message.author.display_name} - {message.content[:50]}...")
                
                # Only include messages from last hour
                import datetime
                message_age = (datetime.datetime.now(datetime.timezone.utc) - message.created_at).total_seconds()
                logger.info(f"🧠 [MIND] Message age: {message_age:.0f} seconds")
                if message_age > 3600:
                    logger.info(f"🧠 [MIND] Skipping message older than 1 hour")
                    continue
                    
                # Skip only commands, but include bot messages for context
                if message.content.strip().startswith('!'):
                    logger.info(f"🧠 [MIND] Skipping command message")
                    continue
                    
                logger.info(f"🧠 [MIND] Including message from {message.author.display_name} (bot: {message.author.bot})")
                    
                # Format message and clean mentions
                content = message.content
                # Replace user mentions with display names
                for mention in message.mentions:
                    content = content.replace(f"<@{mention.id}>", f"@{mention.display_name}")
                
                message_text = f"{message.author.display_name}: {content}"
                messages.append(message_text)
            
            logger.info(f"🧠 [MIND] Discord message fetch completed. Total messages processed: {message_count}, Messages included: {len(messages)}")
            
            logger.info(f"🧠 [MIND] Found {len(messages)} messages from Discord channel")
            
            if not messages:
                logger.info(f"🧠 [MIND] No Discord messages found for channel {channel_id}")
                return ""
            
            # Get label from prompts.json or fallback
            engine = _engine()
            channel_label = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("recent_interactions_from_channel_label", "RECENT MESSAGES FROM CHANNEL:")
            
            # Build channel messages block
            channel_block = [channel_label]
            channel_block.extend(messages[-10:])  # Take last 10 messages
            
            return "\n".join(channel_block)
            
        except Exception as e:
            logger.error(f"🧠 [MIND] Error fetching Discord messages: {e}")
            logger.info(f"🧠 [MIND] Discord API failed, falling back to database method")
    else:
        logger.info(f"🧠 [MIND] No Discord channel object provided, using database method")
    
    # Fallback: Use database method
    server_id = server or get_active_server_id()
    db_instance = get_global_db(server_id=server_id) if server_id else None
    
    if not db_instance or not channel_id:
        return ""
    
    logger.info(f"🧠 [MIND] Loading recent messages from database channel {channel_id}")
    channel_messages = db_instance.get_recent_channel_interactions(channel_id, within_minutes=60, max_interactions=10)
    logger.info(f"🧠 [MIND] Found {len(channel_messages)} messages from database")
    
    if not channel_messages:
        logger.info(f"🧠 [MIND] No channel messages found for channel {channel_id}")
        return ""
    
    # Get label from prompts.json or fallback to English
    engine = _engine()
    channel_label = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("recent_interactions_from_channel_label", "MENSAJES RECIENTES EN EL CANAL:")
    
    # Build channel messages block
    channel_block = [channel_label]
    
    # Format channel messages (exclude commands, include bot responses)
    # Reverse messages to show chronological order (oldest first)
    bot_name = engine.PERSONALITY.get("name", "Bot")
    for message in reversed(channel_messages):
        # Skip if it's a command (starts with !)
        if message['content'].strip().startswith('!'):
            continue
            
        # Clean mentions from content
        content = message['content']
        import re
        # Replace user mentions with actual usernames from database
        for match in re.finditer(r'<@(\d+)>', content):
            user_id = match.group(1)
            try:
                # Check if it's the bot's ID
                if bot_id and user_id == bot_id:
                    content = content.replace(f"<@{user_id}>", f"@{bot_name}")
                else:
                    # Try to get username from database
                    user_rows = db_instance.execute_query(
                        "SELECT usuario_nombre FROM interacciones WHERE usuario_id = ? LIMIT 1",
                        (user_id,)
                    )
                    if user_rows:
                        username = user_rows[0][0]
                        content = content.replace(f"<@{user_id}>", f"@{username}")
                    else:
                        # Fallback to @ID if username not found
                        content = content.replace(f"<@{user_id}>", f"@{user_id}")
            except:
                content = content.replace(f"<@{user_id}>", f"@{user_id}")
        
        message_text = f"{message['user_name']}: {content}"
        if message['response']:
            message_text += f"\n{bot_name}: {message['response']}"
        channel_block.append(message_text)
    
    return "\n".join(channel_block)


async def _build_conversation_channel_prompt(
    user_content: str = "",
    server: str | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
    channel_id: str | None = None,
    bot_id: str | None = None,
    discord_channel=None,
) -> str:
    """
    Build a contextual user prompt for channel conversations.
    This function handles channel-specific context and mentions.
    """
    engine = _engine()
    bot_name = engine.PERSONALITY.get("name", "Bot")
    content = (user_content or "").strip()
    server_id = server or get_active_server_id()
    if not server_id:
        logger.warning("🧠 [MIND] No server context available, skipping memory-backed prompt enrichment")
        server_id = None
    db_instance = get_global_db(server_id=server_id) if server_id else None
    
    # Build the contextual prompt sections
    prompt_sections = []
    
    memories_block = _build_prompt_memory_block(server=server)
    relationship_block = _build_prompt_relationship_block(user_id, user_name, server)
    # Add memories block if available
    prompt_sections.append(memories_block)
    prompt_sections.append(relationship_block)
    
    # Add recent channel messages block
    if channel_id:
        channel_messages_block = await _build_prompt_channel_messages_block(
            channel_id=channel_id, 
            server=server, 
            bot_id=bot_id,
            discord_channel=discord_channel
        )
        if channel_messages_block:
            prompt_sections.append(channel_messages_block)
    
    # Add separator if we have any context sections
    if prompt_sections:
        prompt_sections.append("-" * 45)
    
    # Add golden rules from personality or fallback to English
    golden_rules = engine.PERSONALITY.get("behaviors", {}).get("conversation", {}).get("golden_rules_channel", [])
    if not golden_rules:
        # English fallback golden rules
        golden_rules = [
            "## RESPONSE RULES:",
            "1. LENGTH: 1-3 sentences (25-200 characters).",
            "2. GRAMMAR: No accents.",
            "3. Don't end sentences with single words like 'that', 'of', 'to'.",
            "4. Don't repeat what you've said, be original and creative, but stay an orc.",
            "5. Your al talking in a channel, you can talk in plural not only with the user that metion you."
        ]
    
    # Add golden rules section
    if golden_rules:
        for rule in golden_rules:
            prompt_sections.append(str(rule).strip())
        # Add separator after golden rules
        prompt_sections.append("-" * 45)
    
    # Add user message
    message_title = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("message_title", "## MESSAGE:")
    message_title = message_title.replace("{user_name}", user_name)
    prompt_sections.append(message_title)
    prompt_sections.append(content)
    
    # Add memory retrieval if user asks about memories (for mentions)
    if db_instance and user_id and content:
        retrieved_memory = _detect_and_retrieve_memory(content, db_instance, user_id)
        if retrieved_memory:
            memory_retrieval_title = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("memory_retrieval_title", "[THIS REMINDS YOU THAT:]")
            prompt_sections.append(memory_retrieval_title)
            prompt_sections.append(retrieved_memory)
            prompt_sections.append("-" * 45)
    
    response_title = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("response_title", "## ANSWER WITH THE WORDS OF THE PERSONALITY:")
    prompt_sections.append(response_title)
    return "\n".join(prompt_sections)


def _detect_and_retrieve_memory(user_content: str, db_instance, user_id: str) -> str:
    """Detect memory questions and retrieve relevant memories from database."""
    engine = _engine()
    
    # Get memory trigger words from personality descriptions.json
    memory_triggers = engine.PERSONALITY.get("discord", {}).get("memory_detection", {}).get("memory_trigger_words", [])
    
    # English fallback if no triggers found
    if not memory_triggers:
        memory_triggers = [
            "do you remember", "remember", "recall", "do you recall",
            "do you remember that", "remember when", "do you recall",
            "do you remember", "do you recall", "recall", "remember",
            "do you remember?", "do you recall?", "remember that",
            "remember when", "does that sound familiar", "remember that"
        ]
    
    # Check if user content contains memory trigger words
    content_lower = user_content.lower()
    is_memory_question = any(trigger in content_lower for trigger in memory_triggers)
    
    if not is_memory_question:
        return ""
    
    # Search for relevant recollections in database
    try:
        # Get notable recollections for search
        notable_recollections = db_instance.get_notable_recollections_for_date()
        
        if not notable_recollections:
            return ""
        
        # Extract keywords from user content (excluding trigger words)
        content_words = set(content_lower.split())
        trigger_words_lower = set(trigger.lower() for trigger in memory_triggers)
        keywords = content_words - trigger_words_lower
        
        # Add debug logging
        logger.info(f"🧠 [MEMORY_DETECTION] User content: '{user_content}'")
        logger.info(f"🧠 [MEMORY_DETECTION] Keywords after removing triggers: {keywords}")
        logger.info(f"🧠 [MEMORY_DETECTION] Found {len(notable_recollections)} recollections in database")
        
        # Find best matching recollection with 50% similarity threshold
        best_match = ""
        best_score = 0
        
        for i, recollection in enumerate(notable_recollections):
            recollection_text = recollection.get("recollection_text", "").lower()
            logger.info(f"🧠 [MEMORY_DETECTION] Recollection {i+1}: '{recollection_text}'")
            
            # Calculate similarity score with case-insensitive matching
            recollection_words = set(recollection_text.split())
            if not keywords or not recollection_words:
                logger.info(f"🧠 [MEMORY_DETECTION] Skipping recollection {i+1}: no keywords or recollection words")
                continue
                
            # Calculate dynamic similarity scores
            intersection = keywords & recollection_words
            keyword_coverage = len(intersection) / len(keywords) if keywords else 0  # % of user keywords matched
            recollection_coverage = len(intersection) / len(recollection_words) if recollection_words else 0  # % of recollection matched
            
            # Dynamic score: prioritize keyword coverage but boost if recollection is well-covered
            base_score = keyword_coverage
            coverage_boost = recollection_coverage * 0.3  # 30% boost for good recollection coverage
            score = base_score + coverage_boost
            
            logger.info(f"🧠 [MEMORY_DETECTION] Recollection {i+1} - Keyword coverage: {keyword_coverage:.2f}, Recollection coverage: {recollection_coverage:.2f}, Final score: {score:.2f}")
            logger.info(f"🧠 [MEMORY_DETECTION] Recollection {i+1} intersection: {intersection}")
            
            # Dynamic threshold: lower base threshold but require minimum absolute matches
            min_absolute_matches = 2  # At least 2 words must match
            dynamic_threshold = 0.3  # 30% base threshold
            
            if (score > best_score and 
                len(intersection) >= min_absolute_matches and 
                score >= dynamic_threshold):
                best_score = score
                best_match = recollection.get("recollection_text", "")
                logger.info(f"🧠 [MEMORY_DETECTION] New best match found with score {best_score:.2f}")
        
        if best_match:
            logger.info(f"🧠 [MEMORY_DETECTION] Final best match: '{best_match}' with {best_score:.2f} similarity")
            return best_match
        
    except Exception as e:
        logger.warning(f"🧠 [MEMORY_DETECTION] Error retrieving recollection: {e}")
    
    return ""


def _get_keyword_injection(content: str) -> str:
    """Detect keywords from subroles and inject relevant prompts."""
    if not content:
        return ""
    engine = _engine()
    role_system_prompts = (engine.PERSONALITY or {}).get("roles", {})
    subroles_cfg = (role_system_prompts or {}).get("trickster", {}).get("subroles", {})
    for subrole_name, subrole_cfg in subroles_cfg.items():
        if not isinstance(subrole_cfg, dict):
            continue
        if not _matches_subrole_keywords(subrole_name, content):
            continue
        active_duty = str(subrole_cfg.get("active_duty") or subrole_cfg.get("mission_active") or "").strip()
        chat_detection = (subrole_cfg.get("chat_detection") or {}).get("prompt", "")
        detection_prompt = str(chat_detection).replace("{username}", "user").strip()
        parts = [part for part in [active_duty, detection_prompt] if part]
        if parts:
            return "\n".join(parts)
    return ""


def _matches_subrole_keywords(subrole_name: str, content: str) -> bool:
    """Check if content matches keywords for a specific subrole."""
    engine = _engine()
    role_system_prompts = (engine.PERSONALITY or {}).get("roles", {})
    subroles_cfg = (role_system_prompts or {}).get("trickster", {}).get("subroles", {})
    subrole_cfg = subroles_cfg.get(subrole_name, {})
    if not isinstance(subrole_cfg, dict):
        return False
    keywords = subrole_cfg.get("keywords", [])
    if not isinstance(keywords, list) or not keywords:
        return False
    content_lower = content.lower()
    return any(keyword.lower() in content_lower for keyword in keywords)


def call_llm(
    system_instruction: str,
    prompt: str,
    async_mode: bool = False,
    call_type: str = "default",
    temperature: float | None = None,
    max_tokens: int | None = None,
    critical: bool = True,
    metadata: dict | None = None,
    logger: logging.Logger | None = None,
    user_id: str = None,
    user_name: str = None,
    server_id: str = None
) -> str:
    """
    Unified LLM call function that can operate in sync or async mode.
    
    Args:
        system_instruction: System prompt for the LLM
        prompt: User prompt for the LLM
        async_mode: If True, use threading (for background tasks)
        call_type: Type of call for logging ("think", "subrole_async", "daily_memory", etc.)
        temperature: Temperature override (auto-detected if None)
        max_tokens: Maximum tokens (from config if None)
        critical: Whether errors should break execution
        metadata: Additional context for logging
        logger: Logger instance (auto-detected if None)
        user_id: User ID for fatigue tracking (optional)
        user_name: User name for fatigue tracking (optional)
        server_id: Server ID for server-specific logging (optional, uses active server if not provided)
    
    Returns:
        LLM response text
    """
    if logger is None:
        logger = get_logger('agent_engine')
    
    start_time = time.time()
    metadata = metadata or {}
    
    # Auto-detect temperature if not specified
    if temperature is None:
        if call_type == "think" and metadata.get("is_mission"):
            temperature = 0.9
        else:
            temperature = 0.95
    
    # Get max_tokens from config if not specified
    if max_tokens is None:
        max_tokens = _get_max_tokens()
    
    # Log based on criticality
    log_prefix = "🤖 [CRITICAL]" if critical else "🤖 [BACKGROUND]"
    
    # Log the prompt once at the beginning
    # Use provided server_id or get active server ID
    effective_server_id = server_id or get_active_server_id()
    log_final_llm_prompt(
        provider="vertexai" if not is_simulation_mode() and VERTEXAI_AVAILABLE else "groq",
        call_type=call_type,
        system_instruction=system_instruction,
        user_prompt=prompt,
        metadata=metadata,
        server_id=effective_server_id
    )
    
    try:
        if not is_simulation_mode():
            logger.info(f"{log_prefix} Starting call to gemini-3.1-flash-lite-preview")
            logger.info(f"   └─ Temp: {temperature} | Max tokens: {max_tokens}")
            logger.info("   └─ Top-p: 0.95")

            if not VERTEXAI_AVAILABLE:
                logger.info(f"{log_prefix} Vertex AI not available, skipping to fallback")
                if critical:
                    logger.warning(f"Vertex AI unavailable for critical call, using fallback")
            else:
                if not _init_vertexai():
                    logger.info(f"{log_prefix} Vertex AI initialization failed, skipping to fallback")
                    if critical:
                        logger.warning(f"Vertex AI initialization failed for critical call, using fallback")
                else:
                    if async_mode:
                        try:
                            result = _call_vertexai_async(
                                system_instruction, prompt, temperature,
                                max_tokens, start_time, call_type, critical, logger, user_id, user_name, server_id
                            )
                            if result is not None:
                                return result
                        except Exception as e:
                            logger.info(f"{log_prefix} Vertex AI async call failed, fallback to Groq: {e}")
                            # Fall through to Groq fallback for all calls (critical and non-critical)
                    else:
                        try:
                            result = _call_vertexai_sync(
                                system_instruction, prompt, temperature,
                                max_tokens, start_time, call_type, critical, logger, user_id, user_name, server_id
                            )
                            if result is not None:
                                return result
                        except Exception as e:
                            logger.info(f"{log_prefix} Vertex AI sync call failed, fallback to Groq: {e}")
                            # Fall through to Groq fallback for all calls (critical and non-critical)
        else:
            logger.info(f"{log_prefix} Simulation mode, using Groq")
    except ImportError as e:
        logger.info(f"{log_prefix} Vertex AI import failed, fallback to Groq: {e}")
    except Exception as e:
        logger.info(f"{log_prefix} Vertex AI failed, fallback to Groq: {e}")
    
    # Fallback to Groq
    return _call_groq_fallback(
        system_instruction, prompt, temperature, max_tokens, start_time,
        call_type, critical, logger, user_id, user_name, server_id
    )


def _call_vertexai_sync(
    system_instruction: str, prompt: str, temperature: float,
    max_tokens: int, start_time: float, call_type: str, critical: bool, logger,
    user_id: str = None, user_name: str = None, server_id: str = None
) -> str:
    """Synchronous Vertex AI call (for critical operations)"""
    result_queue = queue.Queue()
    exception_queue = queue.Queue()

    def call_vertexai():
        try:
            config = genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_tokens,
                top_p=0.95,
            )

            res = _VERTEXAI_CLIENT.models.generate_content(
                model="gemini-3.1-flash-lite",#Don't touch 3.1 its okay
                contents=prompt,
                config=config,
            )
            result_queue.put(res)
        except Exception as e:
            exception_queue.put(e)

    vertexai_thread = threading.Thread(target=call_vertexai)
    vertexai_thread.start()
    vertexai_thread.join(timeout=30.0)

    if vertexai_thread.is_alive():
        logger.error("🤖 [SYNC] Vertex AI call timed out after 30 seconds")
        if critical:
            raise TimeoutError("Vertex AI API call timed out")
        else:
            return None

    if not exception_queue.empty():
        e = exception_queue.get()
        logger.error(f"🤖 [SYNC] Vertex AI call failed: {e}")
        if critical:
            raise
        else:
            return None

    try:
        res = result_queue.get()
        text = res.text
        if text and len(text.strip()) > 5:
            postprocessed = postprocess_response(text)
            total_time = time.time()
            logger.info(f"🏁 [SYNC] Vertex AI completed in {(total_time - start_time):.2f}s: {len(postprocessed)} chars")
            
            # Log the response
            try:
                effective_server_id = server_id or get_active_server_id()
                log_agent_response(postprocessed, role=call_type, server=effective_server_id, response_length=len(postprocessed), server_id=effective_server_id)
            except Exception as log_error:
                logger.warning(f"Failed to log response: {log_error}")
            
            # Increment fatigue counter
            try:
                personality_name = _engine().PERSONALITY.get("name", "unknown")
                runtime_increment_usage(personality_name, user_id, user_name)
                logger.info(f"📊 [FATIGUE] Incremented counter for {personality_name}" + (f" (user: {user_name})" if user_name else ""))
            except Exception as fatigue_error:
                logger.warning(f"Failed to increment fatigue counter: {fatigue_error}")
            
            return postprocessed
        else:
            logger.warning("🤖 [SYNC] Vertex AI returned empty or too short response")
            if critical:
                return _get_fallback_response(critical)
            else:
                return None
            
    except Exception as e:
        logger.error(f"🤖 [SYNC] Failed to process Vertex AI response: {e}")
        if critical:
            raise
        else:
            return None

def _call_vertexai_async(
    system_instruction: str, prompt: str, temperature: float,
    max_tokens: int, start_time: float, call_type: str, critical: bool, logger,
    user_id: str = None, user_name: str = None, server_id: str = None
) -> str:
    """Asynchronous Vertex AI call with threading (for _call_llm_async behavior)"""
    result_queue = queue.Queue()
    exception_queue = queue.Queue()

    def call_vertexai():
        try:
            config = genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_tokens,
                top_p=0.95,
            )
            res = _VERTEXAI_CLIENT.models.generate_content(
                model="gemini-3.1-flash-lite",#Don't touch 3.1 its okay
                contents=prompt,
                config=config,
            )
            result_queue.put(res)
        except Exception as e:
            exception_queue.put(e)

    vertexai_thread = threading.Thread(target=call_vertexai)
    vertexai_thread.start()
    vertexai_thread.join(timeout=120.0)

    if not vertexai_thread.is_alive() and exception_queue.empty():
        res = result_queue.get()
        text = res.text
        if text and len(text.strip()) > 5:
            postprocessed = postprocess_response(text)
            total_time = time.time()
            logger.info(f"🏁 [ASYNC] Vertex AI completed in {(total_time - start_time):.2f}s: {len(postprocessed)} chars")
            
            # Log the response
            try:
                effective_server_id = server_id or get_active_server_id()
                log_agent_response(postprocessed, role="subrole", server=effective_server_id, response_length=len(postprocessed), server_id=effective_server_id)
            except Exception as log_error:
                logger.warning(f"Failed to log subrole response: {log_error}")
            
            # Increment fatigue counter
            try:
                personality_name = _engine().PERSONALITY.get("name", "unknown")
                runtime_increment_usage(personality_name, user_id, user_name)
                logger.info(f"📊 [FATIGUE] Incremented counter for {personality_name}" + (f" (user: {user_name})" if user_name else ""))
            except Exception as fatigue_error:
                logger.warning(f"Failed to increment fatigue counter: {fatigue_error}")
            
            return postprocessed
        else:
            logger.warning("🤖 [ASYNC] Vertex AI returned empty or too short response")
            if critical:
                return _get_fallback_response(critical)
            else:
                return None
    else:
        # Check if there's an exception
        if not exception_queue.empty():
            exception = exception_queue.get()
            logger.error(f"🤖 [ASYNC] Vertex AI exception: {exception}")
            logger.info("🤖 [ASYNC] Vertex AI timeout/error, fallback to Groq")
        else:
            logger.info("🤖 [ASYNC] Vertex AI timeout (thread still alive), fallback to Groq")
        return _call_groq_fallback(
            system_instruction, prompt, temperature, max_tokens, start_time,
            call_type, critical, logger, user_id, user_name
        )

def _call_groq_fallback(
    system_instruction: str, prompt: str, temperature: float,
    max_tokens: int, start_time: float, call_type: str, critical: bool, logger,
    user_id: str = None, user_name: str = None, server_id: str = None
) -> str:
    """Fallback to Groq when Vertex AI fails, with Mistral as second fallback"""
    try:
        logger.info(f"🤖 [FALLBACK] Starting call to llama-3.3-70b-versatile")

        from agent_runtime import get_groq_client
        completion = get_groq_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            temperature=1.0,
            max_tokens=max_tokens,
            top_p=1.0,
            presence_penalty=1.0,
            frequency_penalty=1.0,
        )

        response = completion.choices[0].message.content
        postprocessed = postprocess_response(response)
        total_time = time.time()
        logger.info(f"🏁 [FALLBACK] Groq completed in {(total_time - start_time):.2f}s: {len(postprocessed)} chars")
        
        # Log the response
        try:
            effective_server_id = server_id or get_active_server_id()
            log_agent_response(postprocessed, role="subrole", server=effective_server_id, response_length=len(postprocessed), server_id=effective_server_id)
        except Exception as log_error:
            logger.warning(f"Failed to log subrole response: {log_error}")
        
        # Increment fatigue counter
        try:
            personality_name = _engine().PERSONALITY.get("name", "unknown")
            runtime_increment_usage(personality_name, user_id, user_name)
            logger.info(f"📊 [FATIGUE] Incremented counter for {personality_name}" + (f" (user: {user_name})" if user_name else ""))
        except Exception as fatigue_error:
            logger.warning(f"Failed to increment fatigue counter: {fatigue_error}")
        
        return postprocessed
    except Exception as e:
        logger.error(f"🤖 [FALLBACK] Groq failed: {e}")
        logger.info(f"🤖 [FALLBACK] Trying Mistral as second fallback")
        return _call_mistral_fallback(
            system_instruction, prompt, temperature, max_tokens, start_time,
            call_type, critical, logger, user_id, user_name, server_id
        )


def _call_mistral_fallback(
    system_instruction: str, prompt: str, temperature: float,
    max_tokens: int, start_time: float, call_type: str, critical: bool, logger,
    user_id: str = None, user_name: str = None, server_id: str = None
) -> str:
    """Second fallback to Mistral when both Vertex AI and Groq fail"""
    try:
        logger.info(f"🤖 [FALLBACK2] Starting call to Mistral")

        from agent_runtime import get_mistral_client
        mistral_client = get_mistral_client()
        
        if not mistral_client:
            logger.error(f"🤖 [FALLBACK2] Mistral client not available")
            raise Exception("Mistral client not initialized")
        
        response = mistral_client.chat.complete(
            model="mistral-medium-latest",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=0.95,
        )

        response_text = response.choices[0].message.content
        postprocessed = postprocess_response(response_text)
        total_time = time.time()
        logger.info(f"🏁 [FALLBACK2] Mistral completed in {(total_time - start_time):.2f}s: {len(postprocessed)} chars")
        
        # Log the response
        try:
            effective_server_id = server_id or get_active_server_id()
            log_agent_response(postprocessed, role="subrole", server=effective_server_id, response_length=len(postprocessed), server_id=effective_server_id)
        except Exception as log_error:
            logger.warning(f"Failed to log subrole response: {log_error}")
        
        # Increment fatigue counter
        try:
            personality_name = _engine().PERSONALITY.get("name", "unknown")
            runtime_increment_usage(personality_name, user_id, user_name)
            logger.info(f"📊 [FATIGUE] Incremented counter for {personality_name}" + (f" (user: {user_name})" if user_name else ""))
        except Exception as fatigue_error:
            logger.warning(f"Failed to increment fatigue counter: {fatigue_error}")
        
        return postprocessed
    except Exception as e:
        logger.error(f"🤖 [FALLBACK2] All LLMs failed (Vertex AI, Groq, Mistral): {e}")
        if critical:
            raise
        return _get_fallback_response(critical)


def _get_fallback_response(critical: bool) -> str:
    """Get appropriate fallback response based on criticality"""
    if critical:
        raise Exception("Critical LLM call failed and no fallback available")
    return "[Error in internal task]"


# =============================================================================
# WEEKLY PERSONALITY EVOLUTION
# =============================================================================

def _get_weekly_personality_evolution_task_lines() -> list[str]:
    """Get task lines for weekly personality evolution from personality config."""
    synthesis = _engine().PERSONALITY.get("synthesis_paragraphs", {})
    task_lines = synthesis.get("weekly_personality_evolution_task", [])
    if isinstance(task_lines, list) and task_lines:
        return [str(line).strip() for line in task_lines if str(line).strip()]
    # Default fallback
    return [
        "TASK: Gently evolve the character's identity based on the week's experiences.",
        "OBJECTIVE: Review the 7 daily memory paragraphs and subtly adjust the identity_body section.",
        "IMPACT: The week's events should lightly influence the character's worldview, priorities, or attitudes.",
        "FORMAT: Return ONLY the evolved identity_body array, maintaining exact JSON structure.",
    ]


def _get_weekly_personality_evolution_rules() -> list[str]:
    """Get golden rules for weekly personality evolution."""
    synthesis = _engine().PERSONALITY.get("synthesis_paragraphs", {})
    rules = synthesis.get("weekly_personality_evolution_rules", [])
    if isinstance(rules, list) and rules:
        return [str(line).strip() for line in rules if str(line).strip()]
    # Default fallback rules
    return [
        "=== GOLDEN RULES ===",
        "1. SUBTLETY: Modify no more than 5% of the personality. Keep core identity intact.",
        "2. FORMAT: Maintain the exact same JSON array structure with string elements.",
        "3. PRESERVATION: Keep all style rules, dialect instructions, and examples unchanged.",
        "4. EVOLUTION: Only identity_body (character background, history, likes, hates) may evolve.",
        "5. COHERENCE: Changes must logically follow from the week's daily memories.",
        "6. REVERSIBILITY: If the evolution feels wrong, the system can revert to backup.",
        "7. IDENTITY: Never change the character name or fundamental nature (orc remains orc).",
    ]


def _build_weekly_personality_evolution_prompt(
    daily_memories: list[dict],
    current_identity_body: list[str],
    week_start_date: str,
    week_end_date: str,
) -> str:
    """Build the prompt for weekly personality evolution.
    
    Args:
        daily_memories: List of 7 daily memory dicts with memory_date and summary
        current_identity_body: Current identity_body array from personality.json
        week_start_date: Start date of the week (YYYY-MM-DD)
        week_end_date: End date of the week (YYYY-MM-DD)
    
    Returns:
        Formatted prompt string for the LLM
    """
    task_lines = _get_weekly_personality_evolution_task_lines()
    rules = _get_weekly_personality_evolution_rules()
    
    # Build the 7 daily memories section
    memories_lines = ["=== WEEK'S DAILY MEMORIES ===", ""]
    for i, mem in enumerate(daily_memories, 1):
        date_str = mem.get("memory_date", "unknown")
        summary = mem.get("summary", "").strip()
        memories_lines.append(f"Day {i} ({date_str}):")
        memories_lines.append(f"  {summary}")
        memories_lines.append("")
    
    # Build current identity section
    identity_lines = ['=== CURRENT IDENTITY_BODY ===', '', '[']
    for line in current_identity_body:
        escaped = line.replace('"', '\\"')
        identity_lines.append(f'  "{escaped}",')
    identity_lines.append(']')
    
    # Build the full prompt
    prompt_parts = [
        f"WEEKLY PERSONALITY EVOLUTION: {week_start_date} to {week_end_date}",
        "",
        *task_lines,
        "",
        *memories_lines,
        "",
        *identity_lines,
        "",
        *rules,
        "",
        "=== OUTPUT FORMAT ===",
        "Return ONLY the JSON array for identity_body. Example:",
        '[',
        '  "First paragraph of evolved identity...",',
        '  "Second paragraph...",',
        '  "Third paragraph..."',
        ']',
        "",
        "=== IMPORTANT ===",
        "- Do not wrap in markdown code blocks",
        "- Do not add explanations or comments",
        "- Return valid JSON array only",
        "- Each element must be a complete paragraph string",
    ]
    
    return "\n".join(prompt_parts)


def _parse_identity_body_from_llm_response(response: str) -> list[str] | None:
    """Parse the identity_body array from LLM response.
    
    Args:
        response: Raw LLM response text
        
    Returns:
        List of strings if parsing succeeds, None if fails
    """
    if not response:
        return None
    
    text = response.strip()
    
    # Try to extract JSON array from markdown code blocks first
    import re
    code_block_match = re.search(r'```(?:json)?\s*\n?(\[[\s\S]*?\])\s*\n?```', text)
    if code_block_match:
        text = code_block_match.group(1)
        logger.debug(f"🧬 [PERSONALITY_EVOLUTION] Extracted JSON from code block")
    
    # Try to find array directly if no code block
    if not text.startswith('['):
        array_match = re.search(r'(\[[\s\S]*\])', text)
        if array_match:
            text = array_match.group(1)
            logger.debug(f"🧬 [PERSONALITY_EVOLUTION] Extracted JSON array from text")
        else:
            logger.warning(f"🧬 [PERSONALITY_EVOLUTION] Could not find JSON array in response")
            logger.debug(f"🧬 [PERSONALITY_EVOLUTION] Response text (first 500 chars): {text[:500]}")
            return None
    
    # Clean the JSON text - remove potential invisible characters and normalize whitespace
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)  # Remove control characters
    text = text.strip()
    
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            # Validate all elements are strings
            if all(isinstance(item, str) for item in parsed):
                logger.info(f"🧬 [PERSONALITY_EVOLUTION] Successfully parsed JSON array with {len(parsed)} elements")
                return [item.strip() for item in parsed if item.strip()]
        logger.warning(f"⚠️ [PERSONALITY_EVOLUTION] Parsed result is not a string array: {type(parsed)}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ [PERSONALITY_EVOLUTION] Failed to parse LLM response as JSON: {e}")
        logger.debug(f"🧬 [PERSONALITY_EVOLUTION] Text being parsed (first 1000 chars):\n{text[:1000]}")
        # Try a more lenient approach: extract strings using regex if JSON parsing fails
        logger.info(f"🧬 [PERSONALITY_EVOLUTION] Attempting fallback string extraction")
        string_pattern = r'"([^"]*(?:\\.[^"]*)*)"'
        matches = re.findall(string_pattern, text)
        if matches:
            logger.info(f"🧬 [PERSONALITY_EVOLUTION] Fallback extracted {len(matches)} strings")
            # Unescape the strings
            import codecs
            unescaped = [codecs.decode(s, 'unicode_escape') for s in matches]
            return [s.strip() for s in unescaped if s.strip()]
        return None


def generate_weekly_personality_evolution(
    server_id: str | None = None,
    force: bool = False,
) -> dict:
    """Generate weekly personality evolution based on 7 days of daily memory.
    
    This function:
    1. Retrieves the last 7 days of daily memory
    2. Loads current personality.json identity_body
    3. Builds and sends evolution prompt to LLM
    4. Parses and validates the evolved identity_body
    5. Creates backup and writes evolved personality to server folder
    
    Args:
        server_id: Server ID to process (uses active server if None)
        force: Force evolution even with fewer than 7 days of memory
        
    Returns:
        Dict with success status, message, and details
    """
    import os
    from datetime import date, timedelta
    
    engine = _engine()
    resolved_server = server_id or get_active_server_id()
    
    if not resolved_server:
        logger.warning("🧬 [PERSONALITY_EVOLUTION] No server context available")
        return {"success": False, "error": "No server context available"}
    
    logger.info(f"🧬 [PERSONALITY_EVOLUTION] Starting weekly evolution for server '{resolved_server}'")
    
    # Get database instance
    from agent_db import get_db_instance
    db_instance = get_db_instance(resolved_server)
    
    # Retrieve last 7 days of daily memory
    daily_memories = db_instance.get_last_7_days_daily_memory()
    
    if not daily_memories:
        logger.warning("🧬 [PERSONALITY_EVOLUTION] No daily memories found in last 7 days")
        return {"success": False, "error": "No daily memories available", "memories_count": 0}
    
    if len(daily_memories) < 7 and not force:
        logger.info(f"🧬 [PERSONALITY_EVOLUTION] Only {len(daily_memories)} days of memory available, need 7 (use force=True to override)")
        return {
            "success": False,
            "error": f"Insufficient memory data: {len(daily_memories)}/7 days",
            "memories_count": len(daily_memories),
            "memories": daily_memories,
        }
    
    # Load current personality.json from server-specific location
    # Extract personality directory name from config path (e.g., "putre(english)")
    config_path = os.path.join(os.path.dirname(__file__), 'agent_config.json')
    with open(config_path, encoding='utf-8') as f:
        config = json.load(f)
    personality_path = config.get('personality', 'personalities/putre(english)/personality.json')
    personality_name = os.path.basename(os.path.dirname(personality_path))
    server_personality_dir = os.path.join(
        os.path.dirname(__file__), "databases", resolved_server, personality_name
    )
    server_personality_path = os.path.join(server_personality_dir, "personality.json")
    
    # Check if server personality exists (migration should have happened already)
    if not os.path.exists(server_personality_path):
        logger.error(f"🧬 [PERSONALITY_EVOLUTION] Server personality not found at {server_personality_path}")
        return {"success": False, "error": "Server personality not migrated"}
    
    logger.info(f"🧬 [PERSONALITY_EVOLUTION] Using server-specific personality")
    
    try:
        with open(server_personality_path, 'r', encoding='utf-8') as f:
            current_personality = json.load(f)
    except Exception as e:
        logger.error(f"🧬 [PERSONALITY_EVOLUTION] Failed to load personality.json: {e}")
        return {"success": False, "error": f"Failed to load personality: {e}"}
    
    # Extract current identity_body
    current_identity_body = current_personality.get("system_prompt_template", {}).get("identity_body", [])
    if not current_identity_body:
        logger.error("🧬 [PERSONALITY_EVOLUTION] No identity_body found in personality")
        return {"success": False, "error": "No identity_body in personality"}
    
    # Calculate week dates
    today = date.today()
    week_end = daily_memories[-1].get("memory_date", today.isoformat())
    week_start = daily_memories[0].get("memory_date", (today - timedelta(days=6)).isoformat())
    
    logger.info(f"🧬 [PERSONALITY_EVOLUTION] Processing week: {week_start} to {week_end} ({len(daily_memories)} days)")
    
    # Build system prompt and evolution prompt
    system_instruction = engine._build_system_prompt(engine.PERSONALITY)
    evolution_prompt = _build_weekly_personality_evolution_prompt(
        daily_memories=daily_memories,
        current_identity_body=current_identity_body,
        week_start_date=week_start,
        week_end_date=week_end,
    )
    
    # Call LLM for evolution
    logger.info(f"🧬 [PERSONALITY_EVOLUTION] Calling LLM for personality evolution...")
    llm_response = call_llm(
        system_instruction=system_instruction,
        prompt=evolution_prompt,
        async_mode=True,
        call_type="weekly_personality_evolution",
        critical=False,
        server_id=resolved_server,
    )
    
    if not llm_response or llm_response.strip() == "[Error in internal task]":
        logger.error("🧬 [PERSONALITY_EVOLUTION] LLM failed to generate evolution")
        return {"success": False, "error": "LLM generation failed"}
    
    # Parse the evolved identity_body
    evolved_identity_body = _parse_identity_body_from_llm_response(llm_response)
    
    if evolved_identity_body is None:
        logger.error("🧬 [PERSONALITY_EVOLUTION] Failed to parse LLM response as valid identity_body")
        return {
            "success": False,
            "error": "Failed to parse LLM response",
            "raw_response": llm_response[:500],
        }
    
    if not evolved_identity_body:
        logger.error("🧬 [PERSONALITY_EVOLUTION] Parsed identity_body is empty")
        return {"success": False, "error": "Empty identity_body from LLM"}
    
    logger.info(f"🧬 [PERSONALITY_EVOLUTION] Successfully parsed evolved identity_body with {len(evolved_identity_body)} paragraphs")
    
    # Create backup before evolution
    backup_path = os.path.join(
        server_personality_dir, f"personality_backup_{date.today().isoformat()}.json"
    )
    try:
        import shutil
        shutil.copy2(server_personality_path, backup_path)
        logger.info(f"🧬 [PERSONALITY_EVOLUTION] Created backup at {backup_path}")
    except Exception as e:
        logger.warning(f"⚠️ [PERSONALITY_EVOLUTION] Failed to create backup: {e}")
    
    # Update personality with evolved identity_body
    evolved_personality = current_personality.copy()
    if "system_prompt_template" not in evolved_personality:
        evolved_personality["system_prompt_template"] = {}
    evolved_personality["system_prompt_template"]["identity_body"] = evolved_identity_body
    
    # Add evolution metadata
    evolved_personality["_evolution_metadata"] = {
        "last_evolution_date": date.today().isoformat(),
        "week_start": week_start,
        "week_end": week_end,
        "memories_used": len(daily_memories),
        "previous_backup": backup_path if os.path.exists(backup_path) else None,
    }
    
    # Write evolved personality to server-specific file
    try:
        with open(server_personality_path, 'w', encoding='utf-8') as f:
            json.dump(evolved_personality, f, indent=2, ensure_ascii=False)
        logger.info(f"🧬 [PERSONALITY_EVOLUTION] Successfully wrote evolved personality to {server_personality_path}")
    except Exception as e:
        logger.error(f"🧬 [PERSONALITY_EVOLUTION] Failed to write evolved personality: {e}")
        return {"success": False, "error": f"Failed to write personality: {e}"}
    
    return {
        "success": True,
        "message": f"Personality evolved for week {week_start} to {week_end}",
        "server_id": resolved_server,
        "week_start": week_start,
        "week_end": week_end,
    }


def generate_test_personality_evolution(server_id: str | None = None) -> dict:
    """Test personality evolution with synthetic daily memories.
    
    This function uses 7 synthetic daily memory paragraphs to test the evolution
    system without requiring actual daily memory data in the database.
    
    Args:
        server_id: Discord server ID (uses active server if None)
        
    Returns:
        Dict with success status, message, prompt sent, and LLM response
    """
    import os
    from datetime import date, timedelta
    from agent_logging import get_logger
    
    test_logger = get_logger('test_evolution')
    
    engine = _engine()
    resolved_server = server_id or get_active_server_id()
    
    if not resolved_server:
        test_logger.warning("🧬 [TEST_EVOLUTION] No server context available")
        return {"success": False, "error": "No server context available"}
    
    test_logger.info(f"🧬 [TEST_EVOLUTION] Starting test evolution for server '{resolved_server}'")
    
    # Load 7 synthetic daily memories from test.json
    test_memories_path = os.path.join(os.path.dirname(__file__), "personalities", "test.json")
    try:
        with open(test_memories_path, 'r', encoding='utf-8') as f:
            test_data = json.load(f)
        test_memory_paragraphs = test_data.get("test_daily_memories", [])
    except Exception as e:
        test_logger.error(f"🧬 [TEST_EVOLUTION] Failed to load test.json: {e}")
        return {"success": False, "error": f"Failed to load test memories: {e}"}
    
    if len(test_memory_paragraphs) < 7:
        test_logger.error(f"🧬 [TEST_EVOLUTION] Insufficient test memories in test.json: {len(test_memory_paragraphs)}/7")
        return {"success": False, "error": f"Insufficient test memories: {len(test_memory_paragraphs)}/7"}
    
    # Generate daily memory entries with dates
    today = date.today()
    test_daily_memories = []
    for i in range(7):
        memory_date = (today - timedelta(days=6-i)).isoformat()
        test_daily_memories.append({
            "memory_date": memory_date,
            "summary": test_memory_paragraphs[i],
            "metadata": {},
            "updated_at": memory_date
        })
    
    # Load current personality.json from server-specific location
    # Extract personality directory name from config path (e.g., "putre(english)")
    config_path = os.path.join(os.path.dirname(__file__), 'agent_config.json')
    with open(config_path, encoding='utf-8') as f:
        config = json.load(f)
    personality_path = config.get('personality', 'personalities/putre(english)/personality.json')
    personality_name = os.path.basename(os.path.dirname(personality_path))
    server_personality_dir = os.path.join(
        os.path.dirname(__file__), "databases", resolved_server, personality_name
    )
    server_personality_path = os.path.join(server_personality_dir, "personality.json")
    
    # Check if server personality exists
    if not os.path.exists(server_personality_path):
        test_logger.error(f"🧬 [TEST_EVOLUTION] Server personality not found at {server_personality_path}")
        return {"success": False, "error": "Server personality not migrated"}
    
    test_logger.info(f"🧬 [TEST_EVOLUTION] Using server-specific personality")
    
    try:
        with open(server_personality_path, 'r', encoding='utf-8') as f:
            current_personality = json.load(f)
    except Exception as e:
        test_logger.error(f"🧬 [TEST_EVOLUTION] Failed to load personality.json: {e}")
        return {"success": False, "error": f"Failed to load personality: {e}"}
    
    # Extract current identity_body
    current_identity_body = current_personality.get("system_prompt_template", {}).get("identity_body", [])
    if not current_identity_body:
        test_logger.error("🧬 [TEST_EVOLUTION] No identity_body found in personality")
        return {"success": False, "error": "No identity_body in personality"}
    
    # Calculate week dates
    week_start = test_daily_memories[0].get("memory_date", (today - timedelta(days=6)).isoformat())
    week_end = test_daily_memories[-1].get("memory_date", today.isoformat())
    
    test_logger.info(f"🧬 [TEST_EVOLUTION] Processing test week: {week_start} to {week_end}")
    
    # Build system prompt and evolution prompt
    system_instruction = engine._build_system_prompt(engine.PERSONALITY)
    evolution_prompt = _build_weekly_personality_evolution_prompt(
        daily_memories=test_daily_memories,
        current_identity_body=current_identity_body,
        week_start_date=week_start,
        week_end_date=week_end,
    )
    
    # Log the prompt to server-specific prompt.log
    from prompts_logger import log_prompt
    log_prompt(
        prompt_type="test_personality_evolution",
        content=evolution_prompt,
        metadata={"server_id": resolved_server, "test_mode": True},
        server_id=resolved_server
    )
    test_logger.info(f"🧬 [TEST_EVOLUTION] Prompt logged to logs/{resolved_server}/prompt.log")
    
    # Call LLM for evolution
    test_logger.info(f"🧬 [TEST_EVOLUTION] Calling LLM for test personality evolution...")
    llm_response = call_llm(
        system_instruction=system_instruction,
        prompt=evolution_prompt,
        async_mode=True,
        call_type="test_weekly_personality_evolution",
        critical=False,
        server_id=resolved_server,
    )
    
    if not llm_response or llm_response.strip() == "[Error in internal task]":
        test_logger.error("🧬 [TEST_EVOLUTION] LLM failed to generate evolution")
        return {
            "success": False,
            "error": "LLM generation failed",
            "prompt_sent": evolution_prompt,
            "llm_response": llm_response,
        }
    
    # Parse the evolved identity_body
    evolved_identity_body = _parse_identity_body_from_llm_response(llm_response)
    
    if evolved_identity_body is None:
        test_logger.error("🧬 [TEST_EVOLUTION] Failed to parse LLM response as valid identity_body")
        return {
            "success": False,
            "error": "Failed to parse LLM response",
            "raw_response": llm_response[:500],
            "prompt_sent": evolution_prompt,
            "llm_response": llm_response,
        }
    
    if not evolved_identity_body:
        test_logger.error("🧬 [TEST_EVOLUTION] Parsed identity_body is empty")
        return {
            "success": False,
            "error": "Empty identity_body from LLM",
            "prompt_sent": evolution_prompt,
            "llm_response": llm_response,
        }
    
    test_logger.info(f"🧬 [TEST_EVOLUTION] Successfully parsed evolved identity_body with {len(evolved_identity_body)} paragraphs")
    
    # Create backup before evolution
    backup_path = os.path.join(
        server_personality_dir, f"personality_backup_test_{date.today().isoformat()}.json"
    )
    try:
        import shutil
        shutil.copy2(server_personality_path, backup_path)
        test_logger.info(f"🧬 [TEST_EVOLUTION] Created test backup at {backup_path}")
    except Exception as e:
        test_logger.warning(f"⚠️ [TEST_EVOLUTION] Failed to create backup: {e}")
    
    # Update personality with evolved identity_body
    evolved_personality = current_personality.copy()
    if "system_prompt_template" not in evolved_personality:
        evolved_personality["system_prompt_template"] = {}
    evolved_personality["system_prompt_template"]["identity_body"] = evolved_identity_body
    
    # Add evolution metadata
    evolved_personality["_evolution_metadata"] = {
        "last_evolution_date": date.today().isoformat(),
        "week_start": week_start,
        "week_end": week_end,
        "memories_used": 7,
        "test_mode": True,
        "previous_backup": backup_path if os.path.exists(backup_path) else None,
    }
    
    # Write evolved personality to server-specific file
    try:
        with open(server_personality_path, 'w', encoding='utf-8') as f:
            json.dump(evolved_personality, f, indent=2, ensure_ascii=False)
        test_logger.info(f"🧬 [TEST_EVOLUTION] Successfully wrote test evolved personality to {server_personality_path}")
    except Exception as e:
        test_logger.error(f"🧬 [TEST_EVOLUTION] Failed to write evolved personality: {e}")
        return {
            "success": False,
            "error": f"Failed to write personality: {e}",
            "prompt_sent": evolution_prompt,
            "llm_response": llm_response,
        }
    
    return {
        "success": True,
        "message": f"Test personality evolution completed for week {week_start} to {week_end}",
        "server_id": resolved_server,
        "week_start": week_start,
        "week_end": week_end,
        "prompt_sent": evolution_prompt,
        "llm_response": llm_response,
        "evolved_paragraphs_count": len(evolved_identity_body),
        "backup_path": backup_path,
    }




