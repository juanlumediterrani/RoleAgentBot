import os
import time
import queue
import threading
import logging
from datetime import date, datetime
import httpx
from typing import Any

try:
    import google.genai as genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from agent_logging import get_logger
from agent_db import get_active_server_name, get_global_db
from agent_runtime import is_simulation_mode, increment_usage as runtime_increment_usage
from postprocessor import postprocess_response, is_blocked_response
from prompts_logger import log_agent_response, log_final_llm_prompt

logger = get_logger('agent_mind')


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
            # Insert format components after the complete FORMATO line
            processed.extend([
                memory_title,
                memory_placeholder,
                recollection_title,
                recollection_placeholder
            ])
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
                lines.append(f'[{timestamp}] Putre: "{bot}"')
            else:
                lines.append(f'Putre: "{bot}"')
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
            lines.append(f"Putre: {response}")
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
        fallback_closing="Return only the final recent-memory paragraph.",
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
                lines.append(f'Putre: "{bot}"')
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


def generate_recent_memory_summary(server_name: str | None = None, target_date: str | None = None, force: bool = False) -> str:
    engine = _engine()
    resolved_server = server_name or get_active_server_name()
    if not resolved_server:
        logger.warning("🧠 [RECENT_MEMORY] No server context available, skipping summary generation")
        return ""
    resolved_date = target_date or date.today().isoformat()
    db_instance = get_global_db(server_name=resolved_server)
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
        critical=False
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


def refresh_due_recent_memories(server_name: str | None = None) -> int:
    resolved_server = server_name or get_active_server_name()
    if not resolved_server:
        logger.warning("🧠 [RECENT_MEMORY] No server context available, skipping refresh")
        return 0
    db_instance = get_global_db(server_name=resolved_server)
    due_refreshes = db_instance.get_due_pending_recent_memory_refreshes()
    if not due_refreshes:
        return 0
    existing_record = db_instance.get_recent_memory_record(memory_date=date.today().isoformat())
    last_interaction_at = (existing_record or {}).get("last_interaction_at")
    new_interactions = db_instance.get_daily_interactions_since(
        since_iso=last_interaction_at,
        limit=100,
        target_date=date.today().isoformat(),
    )
    if not new_interactions:
        db_instance.mark_recent_memory_refresh_completed()
        return 0
    generate_recent_memory_summary(server_name=resolved_server)
    return 1


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
    fallback_patterns = [
        rf"{re.escape(memory_title)}\s*(.*?)(?:\n---|\Z)",
        rf"{re.escape(memory_title_en)}\s*(.*?)(?:\n---|\Z)"
    ]
    
    for pattern in fallback_patterns:
        match = re.search(pattern, summary_response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip(), None
    
    # Last resort: return cleaned response (remove any markers and get content)
    # Split by markers and get the first substantial content
    content_parts = re.split(r"---[A-Z_]+---\s*", summary_response)
    for part in content_parts:
        cleaned = part.strip()
        if cleaned and len(cleaned) > 10:  # Only return if substantial content
            return cleaned, None
    
    return "", None


def generate_daily_memory_summary(server_name: str | None = None, target_date: str | None = None, force: bool = False) -> str:
    engine = _engine()
    resolved_server = server_name or get_active_server_name()
    if not resolved_server:
        logger.warning("🧠 [DAILY_MEMORY] No server context available, skipping summary generation")
        return ""
    resolved_date = target_date or date.today().isoformat()
    db_instance = get_global_db(server_name=resolved_server)
    existing_record = db_instance.get_daily_memory_record(memory_date=resolved_date)
    previous_summary = (existing_record or {}).get("summary", "").strip()
    recent_record = db_instance.get_recent_memory_record(memory_date=resolved_date)
    recent_summary = (recent_record or {}).get("summary", "").strip()
    if not recent_summary:
        if previous_summary:
            return previous_summary
        # No recent summary and no previous daily summary - try to find the most recent existing daily summary
        try:
            with db_instance._lock:
                import sqlite3
                conn = sqlite3.connect(db_instance.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT summary FROM daily_memory 
                    WHERE summary IS NOT NULL AND summary != '' 
                    ORDER BY updated_at DESC LIMIT 1
                """)
                result = cursor.fetchone()
                conn.close()
                
                if result and result[0] and result[0].strip():
                    # Found existing summary, use it without saving
                    existing_summary = result[0].strip()
                    logger.info(f"🧠 [DAILY_MEMORY] No recent memory, using existing daily summary from history")
                    return existing_summary
        except Exception as e:
            logger.debug(f"Could not retrieve existing daily memory: {e}")
        
        # No existing summary found, use fallback but don't save it
        fallback = _get_daily_memory_fallback()
        logger.info(f"🧠 [DAILY_MEMORY] No recent memory and no existing summary, using fallback without saving")
        return fallback
    
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
        critical=False
    )
    
    # Extract new memory (no extraction for daily memory now)
    llm_response = (summary_response or "").strip()
    
    # Only update if LLM successfully generated new content (not error messages)
    if llm_response and llm_response != "[Error in internal task]":
        # LLM succeeded, use the new memory
        summary_text = llm_response
        
        db_instance.upsert_daily_memory(
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
        logger.info(f"🧠 [DAILY_MEMORY] Updated summary for {resolved_server} on {resolved_date} (recollections: {recollection_count}, dreaming: {bool(dreaming_recollection)})")
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
    server_name: str | None = None,
    target_date: str | None = None,
    force: bool = False,
) -> str:
    import datetime
    engine = _engine()
    resolved_server = server_name or get_active_server_name()
    if not resolved_server:
        logger.warning(f"🧠 [RELATIONSHIP_MEMORY] No server context available for user={user_id}")
        return ""
    resolved_date = target_date or date.today().isoformat()
    db_instance = get_global_db(server_name=resolved_server)
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
        if previous_summary:
            return previous_summary
        fallback = _get_relationship_memory_fallback(user_name)
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
        critical=False
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
        # LLM failed or returned error, keep existing summary unchanged
        summary_text = previous_summary or _get_relationship_memory_fallback(user_name)
        logger.info(f"🧠 [RELATIONSHIP_MEMORY] LLM failed, keeping existing summary for user={user_id} server={resolved_server}")
    
    return summary_text


def refresh_due_relationship_memories(server_name: str | None = None) -> int:
    resolved_server = server_name or get_active_server_name()
    if not resolved_server:
        logger.warning("🧠 [RELATIONSHIP_MEMORY] No server context available, skipping refresh")
        return 0
    db_instance = get_global_db(server_name=resolved_server)
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
                server_name=resolved_server,
            )
            processed += 1
        except Exception as e:
            logger.warning(f"⚠️ [RELATIONSHIP_MEMORY] Scheduled refresh failed for user={user_id}: {e}")
    deleted = db_instance.clear_stale_relationship_memory_states()
    if deleted:
        logger.info(f"🧠 [RELATIONSHIP_MEMORY] Cleared {deleted} stale temporary states for server={resolved_server}")
    return processed


def _refresh_relationship_memory_if_due(db_instance, user_id, user_name, recent_dialogue: list[dict]) -> str:
    relationship_state = db_instance.get_user_relationship_memory(user_id)
    daily_record = db_instance.get_user_relationship_daily_memory(user_id)
    summary = relationship_state.get("summary", "").strip()
    if summary:
        return summary
    if daily_record and daily_record.get("summary", "").strip():
        summary = daily_record["summary"].strip()
        db_instance.upsert_user_relationship_memory(
            user_id,
            summary,
            last_interaction_at=relationship_state.get("last_interaction_at"),
            metadata={"user_name": user_name or "", "source": "daily_snapshot_restore"},
        )
        return summary
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
                "## REGLAS DE ORO DE ESTA RESPUESTA:",
                "MISION ACTIVA - BEGGAR",
                "DETECCIÓN EN CHARLA - BEGGAR"
            ],
            "description": "News Watcher has its own golden rules"
        },
        # Add more roles here as needed
        # "## BANKER RULES": {
        #     "skip_patterns": ["## REGLAS DE ORO DE ESTA RESPUESTA:", "OTHER_MISSION"],
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
    server_name = server or get_active_server_name()
    if not server_name:
        logger.warning("🧠 [MIND] No server context available, skipping memory-backed prompt enrichment")
        server_name = None
    db_instance = get_global_db(server_name=server_name) if server_name else None
    
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
    server_name = server or get_active_server_name()
    db_instance = get_global_db(server_name=server_name) if server_name else None
    
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
    server_name = server or get_active_server_name()
    db_instance = get_global_db(server_name=server_name) if server_name else None
    
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
            "2. GRAMMAR: No accents. End statements with '!' and questions with '?'.",
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
    server_name = server or get_active_server_name()
    db_instance = get_global_db(server_name=server_name) if server_name else None
    
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


def _build_prompt_channel_messages_block(
    channel_id: str,
    server: str | None = None,
):
    """
    Build only the CHANNEL MESSAGES block with recent channel interactions.
    This function is now focused solely on channel messages construction.
    """
    server_name = server or get_active_server_name()
    db_instance = get_global_db(server_name=server_name) if server_name else None
    
    if not db_instance or not channel_id:
        return ""
    
    logger.info(f"🧠 [MIND] Loading recent messages from channel {channel_id}")
    channel_messages = db_instance.get_recent_channel_interactions(channel_id, within_minutes=60, max_interactions=10)
    logger.info(f"🧠 [MIND] Found {len(channel_messages)} messages from channel")
    
    if not channel_messages:
        logger.info(f"🧠 [MIND] No channel messages found for channel {channel_id}")
        return ""
    
    # Get label from prompts.json or fallback to English
    engine = _engine()
    channel_label = engine.PERSONALITY.get("synthesis_paragraphs", {}).get("recent_interactions_from_channel_label", "MENSAJES RECIENTES EN EL CANAL:")
    
    # Build channel messages block
    channel_block = [channel_label]
    
    # Format channel messages (exclude commands, include bot responses)
    bot_name = engine.PERSONALITY.get("name", "Bot")
    for message in channel_messages:
        # Skip if it's a command (starts with !)
        if message['content'].strip().startswith('!'):
            continue
            
        message_text = f"{message['user_name']}: {message['content']}"
        if message['response']:
            message_text += f"\n{bot_name}: {message['response']}"
        channel_block.append(message_text)
    
    return "\n".join(channel_block)


def _build_conversation_channel_prompt(
    user_content: str = "",
    server: str | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
    channel_id: str | None = None,
) -> str:
    """
    Build a contextual user prompt for channel conversations.
    This function handles channel-specific context and mentions.
    """
    engine = _engine()
    bot_name = engine.PERSONALITY.get("name", "Bot")
    content = (user_content or "").strip()
    server_name = server or get_active_server_name()
    if not server_name:
        logger.warning("🧠 [MIND] No server context available, skipping memory-backed prompt enrichment")
        server_name = None
    db_instance = get_global_db(server_name=server_name) if server_name else None
    
    # Build the contextual prompt sections
    prompt_sections = []
    
    memories_block = _build_prompt_memory_block(server=server)
    relationship_block = _build_prompt_relationship_block(user_id, user_name, server)
    # Add memories block if available
    prompt_sections.append(memories_block)
    prompt_sections.append(relationship_block)
    
    # Add recent channel messages block
    if channel_id:
        channel_messages_block = _build_prompt_channel_messages_block(channel_id=channel_id, server=server)
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
            "2. GRAMMAR: No accents. End statements with '!' and questions with '?'.",
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
    max_tokens: int = 1024,
    critical: bool = True,
    metadata: dict | None = None,
    logger: logging.Logger | None = None,
    user_id: str = None,
    user_name: str = None
) -> str:
    """
    Unified LLM call function that can operate in sync or async mode.
    
    Args:
        system_instruction: System prompt for the LLM
        prompt: User prompt for the LLM
        async_mode: If True, use threading (for background tasks)
        call_type: Type of call for logging ("think", "subrole_async", "daily_memory", etc.)
        temperature: Temperature override (auto-detected if None)
        max_tokens: Maximum tokens (default 1024)
        critical: Whether errors should break execution
        metadata: Additional context for logging
        logger: Logger instance (auto-detected if None)
        user_id: User ID for fatigue tracking (optional)
        user_name: User name for fatigue tracking (optional)
    
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
    
    # Log based on criticality
    log_prefix = "🤖 [CRITICAL]" if critical else "🤖 [BACKGROUND]"
    
    # Log the prompt once at the beginning
    log_final_llm_prompt(
        provider="gemini" if not is_simulation_mode() and GEMINI_AVAILABLE else "groq",
        call_type=call_type,
        system_instruction=system_instruction,
        user_prompt=prompt,
        metadata=metadata
    )
    
    try:
        if not is_simulation_mode():
            logger.info(f"{log_prefix} Starting call to gemini-2.5-flash-lite")
            logger.info(f"   └─ Temp: {temperature} | Max tokens: {max_tokens}")
            logger.info("   └─ Top-p: 0.95")

            if not GEMINI_AVAILABLE:
                logger.info(f"{log_prefix} Gemini not available, skipping to fallback")
                if critical:
                    logger.warning(f"Gemini unavailable for critical call, using fallback")
            else:
                client_gemini = genai.Client(
                    api_key=os.getenv("GEMINI_API_KEY"),
                    http_options=genai.types.HttpOptions(
                        httpx_client=httpx.Client(timeout=30.0)
                    )
                )
                
                if async_mode:
                    try:
                        result = _call_gemini_async(
                            client_gemini, system_instruction, prompt, temperature, 
                            max_tokens, start_time, call_type, critical, logger, user_id, user_name
                        )
                        if result is not None:
                            return result
                    except Exception as e:
                        logger.info(f"{log_prefix} Gemini async call failed, fallback to Groq: {e}")
                        # Fall through to Groq fallback for all calls (critical and non-critical)
                else:
                    try:
                        result = _call_gemini_sync(
                            client_gemini, system_instruction, prompt, temperature,
                            max_tokens, start_time, call_type, critical, logger, user_id, user_name
                        )
                        if result is not None:
                            return result
                    except Exception as e:
                        logger.info(f"{log_prefix} Gemini sync call failed, fallback to Groq: {e}")
                        # Fall through to Groq fallback for all calls (critical and non-critical)
        else:
            logger.info(f"{log_prefix} Simulation mode, using Groq")
    except ImportError as e:
        logger.info(f"{log_prefix} Gemini import failed, fallback to Groq: {e}")
    except Exception as e:
        logger.info(f"{log_prefix} Gemini failed, fallback to Groq: {e}")
    
    # Fallback to Groq
    return _call_groq_fallback(
        system_instruction, prompt, temperature, max_tokens, start_time,
        call_type, critical, logger, user_id, user_name
    )


def _call_gemini_sync(
    client_gemini, system_instruction: str, prompt: str, temperature: float,
    max_tokens: int, start_time: float, call_type: str, critical: bool, logger,
    user_id: str = None, user_name: str = None
) -> str:
    """Synchronous Gemini call (for critical operations)"""
    result_queue = queue.Queue()
    exception_queue = queue.Queue()

    def call_gemini():
        try:
            res = client_gemini.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    top_p=0.95,
                    safety_settings=[types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE")]
                )
            )
            result_queue.put(res)
        except Exception as e:
            exception_queue.put(e)

    gemini_thread = threading.Thread(target=call_gemini)
    gemini_thread.start()
    gemini_thread.join(timeout=5.0)

    if gemini_thread.is_alive():
        logger.error("🤖 [SYNC] Gemini call timed out after 5 seconds")
        if critical:
            raise TimeoutError("Gemini API call timed out")
        else:
            return None

    if not exception_queue.empty():
        e = exception_queue.get()
        logger.error(f"🤖 [SYNC] Gemini call failed: {e}")
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
            logger.info(f"🏁 [SYNC] Gemini completed in {(total_time - start_time):.2f}s: {len(postprocessed)} chars")
            
            # Log the response
            try:
                server_name = get_active_server_name()
                log_agent_response(postprocessed, role=call_type, server=server_name, response_length=len(postprocessed))
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
            logger.warning("🤖 [SYNC] Gemini returned empty or too short response")
            if critical:
                return _get_fallback_response(critical)
            else:
                return None
            
    except Exception as e:
        logger.error(f"🤖 [SYNC] Failed to process Gemini response: {e}")
        if critical:
            raise
        else:
            return None

def _call_gemini_async(
    client_gemini, system_instruction: str, prompt: str, temperature: float,
    max_tokens: int, start_time: float, call_type: str, critical: bool, logger,
    user_id: str = None, user_name: str = None
) -> str:
    """Asynchronous Gemini call with threading (for _call_llm_async behavior)"""
    result_queue = queue.Queue()
    exception_queue = queue.Queue()

    def call_gemini():
        try:
            res = client_gemini.models.generate_content(
                model='gemini-3.1-flash-lite-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    top_p=0.95,
                    safety_settings=[types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE")]
                )
            )
            result_queue.put(res)
        except Exception as e:
            exception_queue.put(e)

    gemini_thread = threading.Thread(target=call_gemini)
    gemini_thread.start()
    gemini_thread.join(timeout=60.0)

    if not gemini_thread.is_alive() and exception_queue.empty():
        res = result_queue.get()
        text = res.text
        if text and len(text.strip()) > 5:
            postprocessed = postprocess_response(text)
            total_time = time.time()
            logger.info(f"🏁 [ASYNC] Gemini completed in {(total_time - start_time):.2f}s: {len(postprocessed)} chars")
            
            # Log the response
            try:
                server_name = get_active_server_name()
                log_agent_response(postprocessed, role="subrole", server=server_name, response_length=len(postprocessed))
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
            logger.warning("🤖 [ASYNC] Gemini returned empty or too short response")
            if critical:
                return _get_fallback_response(critical)
            else:
                return None
    else:
        # Check if there's an exception
        if not exception_queue.empty():
            exception = exception_queue.get()
            logger.error(f"🤖 [ASYNC] Gemini exception: {exception}")
            logger.info("🤖 [ASYNC] Gemini timeout/error, fallback to Groq")
        else:
            logger.info("🤖 [ASYNC] Gemini timeout (thread still alive), fallback to Groq")
        return _call_groq_fallback(
            system_instruction, prompt, temperature, max_tokens, start_time,
            call_type, critical, logger, user_id, user_name
        )

def _call_groq_fallback(
    system_instruction: str, prompt: str, temperature: float,
    max_tokens: int, start_time: float, call_type: str, critical: bool, logger,
    user_id: str = None, user_name: str = None
) -> str:
    """Fallback to Groq when Gemini fails, with Mistral as second fallback"""
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
            max_tokens=600,
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
            server_name = get_active_server_name()
            log_agent_response(postprocessed, role="subrole", server=server_name, response_length=len(postprocessed))
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
            call_type, critical, logger, user_id, user_name
        )


def _call_mistral_fallback(
    system_instruction: str, prompt: str, temperature: float,
    max_tokens: int, start_time: float, call_type: str, critical: bool, logger,
    user_id: str = None, user_name: str = None
) -> str:
    """Second fallback to Mistral when both Gemini and Groq fail"""
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
            server_name = get_active_server_name()
            log_agent_response(postprocessed, role="subrole", server=server_name, response_length=len(postprocessed))
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
        logger.error(f"🤖 [FALLBACK2] All LLMs failed (Gemini, Groq, Mistral): {e}")
        if critical:
            raise
        return _get_fallback_response(critical)


def _get_fallback_response(critical: bool) -> str:
    """Get appropriate fallback response based on criticality"""
    if critical:
        raise Exception("Critical LLM call failed and no fallback available")
    return "[Error in internal task]"









