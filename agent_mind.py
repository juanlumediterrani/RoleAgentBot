import os
import time
import queue
import threading
from datetime import date, datetime

from google import genai
from google.genai import types

from agent_logging import get_logger
from agent_db import get_active_server_name, get_global_db
from agent_runtime import get_groq_client, increment_usage as runtime_increment_usage, is_simulation_mode
from postprocessor import postprocess_response, is_blocked_response, is_help_request, is_readme_response
from prompts_logger import log_agent_response, log_final_llm_prompt, log_readme_enhanced_prompt

logger = get_logger('agent_mind')


def _engine():
    import agent_engine
    return agent_engine


def _get_daily_memory_fallback() -> str:
    template = _engine()._get_user_prompt_template()
    fallback = template.get("daily_memory_fallback", "")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return "The character does not remember anything important from today."


def _get_recent_memory_fallback() -> str:
    template = _engine()._get_user_prompt_template()
    fallback = template.get("recent_memory_fallback", "")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return "The character feels calm, with no notable recent events."


def _get_daily_summary_task_lines() -> list[str]:
    template = _engine()._get_user_prompt_template()
    task_lines = template.get("daily_summary_task", [])
    if isinstance(task_lines, list) and task_lines:
        return [str(line).strip() for line in task_lines if str(line).strip()]
    return [
        "TASK: Update the long daily memory paragraph as the character's inner voice.",
        "OBJECTIVE: Merge the previous daily memory with the latest recent-memory paragraph from this day.",
        "NOTABLE MEMORY: Read the 'NOTABLE MEMORY' section (if provided) and subtly weave it into the new daily memory.",
        "EXTRACTION: From the previous daily memory (PREVIOUS DAILY MEMORY), extract ONE short phrase (max 15 words) that is the most notable or funny. If nothing notable, respond 'NO_MEMORY'.",
        "FORMAT: Return EXACTLY in this format:",
        "---NEW_MEMORY---",
        "[new daily memory paragraph here]",
        "---EXTRACTED_MEMORY---",
        "[extracted notable phrase or NO_MEMORY]",
        "STYLE: Stay fully in character and never speak as an assistant.",
    ]


def _get_recent_summary_task_lines() -> list[str]:
    template = _engine()._get_user_prompt_template()
    task_lines = template.get("recent_memory_summary_task", [])
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
    template = _engine()._get_user_prompt_template()
    fallback = template.get("relationship_memory_fallback", "")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.replace("{user_name}", user_name or "human").strip()
    return f"The character does not yet have a clear opinion about {user_name or 'this human'}."


def _get_recent_dialogue_fallback() -> str:
    template = _engine()._get_user_prompt_template()
    fallback = template.get("recent_dialogue_fallback", "")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return "There has been no recent dialogue with this user."


def _build_configured_synthesis_prompt(
    prompt_key: str,
    fallback_instructions: list[str],
    replacements: dict[str, str],
    sections: list[tuple[str, str]],
    fallback_closing: str,
) -> str:
    personality = _engine().PERSONALIDAD
    cfg = personality.get(prompt_key, {})
    instructions = cfg.get("instructions", []) if isinstance(cfg, dict) else []
    if not isinstance(instructions, list) or not instructions:
        instructions = fallback_instructions

    processed = []
    for inst in instructions:
        line = str(inst)
        for key, value in replacements.items():
            line = line.replace(f"{{{key}}}", str(value))
        processed.append(line.strip())

    for section_title, section_content in sections:
        processed.extend(["", section_title, section_content.strip()])

    closing = str(cfg.get("closing", "")).strip() if isinstance(cfg, dict) else ""
    if not closing:
        closing = fallback_closing
    if closing:
        for key, value in replacements.items():
            closing = closing.replace(f"{{{key}}}", str(value))
        processed.extend(["", closing.strip()])

    return "\n".join([line for line in processed if line])


def _build_recent_dialogue_section(recent_dialogue: list[dict]) -> str:
    if not recent_dialogue:
        return _get_recent_dialogue_fallback()
    lines = []
    for item in recent_dialogue[-15:]:
        human = str(item.get("humano", "")).strip()
        bot = str(item.get("bot", "")).strip()
        if human:
            lines.append(f'Umano: "{human}"')
        if bot:
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
    injected_memory: str | None = None,
) -> str:
    previous_block = previous_summary.strip() or _get_daily_memory_fallback()
    recent_block = recent_memory.strip() or _get_recent_memory_fallback()
    sections: list[tuple[str, str]] = [
        ("TARGET DATE:", target_date),
        ("PREVIOUS DAILY MEMORY:", previous_block),
        ("LATEST RECENT MEMORY OF THE DAY:", recent_block),
    ]
    if injected_memory and injected_memory.strip():
        sections.append(("NOTABLE MEMORY TO WEAVE IN:", injected_memory.strip()))
    return _build_configured_synthesis_prompt(
        prompt_key="prompt_daily_memory_summary",
        fallback_instructions=_get_daily_summary_task_lines(),
        replacements={"target_date": target_date},
        sections=sections,
        fallback_closing="Return exactly in the specified format with both sections.",
    )


def _format_relationship_interactions_for_summary(interactions: list[dict]) -> str:
    if not interactions:
        return "There are no new interactions with this user."
    lines = []
    for item in interactions[-25:]:
        timestamp = str(item.get("fecha", "")).strip()
        interaction_type = str(item.get("tipo_interaccion", "")).strip() or "INTERACTION"
        human = str(item.get("humano", "")).strip()
        bot = str(item.get("bot", "")).strip()
        lines.append(f"[{timestamp}] {interaction_type}")
        if human:
            lines.append(f'Human: "{human}"')
        if bot:
            lines.append(f'Putre: "{bot}"')
        lines.append("")
    return "\n".join(lines).strip()


def _build_relationship_summary_prompt(previous_summary: str, new_interactions: list[dict], user_name: str | None, target_date: str) -> str:
    previous_block = previous_summary.strip() or "No previous synthesis."
    interactions_block = _format_relationship_interactions_for_summary(new_interactions)
    return _build_configured_synthesis_prompt(
        prompt_key="prompt_relationship_memory_summary",
        fallback_instructions=_get_relationship_summary_task_lines(),
        replacements={"user_name": user_name or "human", "target_date": target_date},
        sections=[
            ("TARGET USER:", user_name or "human"),
            ("TARGET DATE:", target_date),
            ("PREVIOUS SYNTHESIS:", previous_block),
            ("NEW INTERACTIONS SINCE THE LAST SYNTHESIS:", interactions_block),
        ],
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
        limit=25,
        target_date=resolved_date,
    )
    if not interactions:
        if previous_summary:
            return previous_summary
        fallback = _get_recent_memory_fallback()
        db_instance.upsert_recent_memory(
            fallback,
            memory_date=resolved_date,
            last_interaction_at=last_interaction_at,
            metadata={"source": "recent_memory_fallback", "interaction_count": 0},
        )
        return fallback

    system_instruction = engine._build_system_prompt(engine.PERSONALIDAD)
    summary_prompt = _build_recent_memory_summary_prompt(previous_summary, interactions, resolved_date)
    summary_response = _call_llm_async(system_instruction, summary_prompt)
    summary_text = (summary_response or "").strip() or previous_summary or _get_recent_memory_fallback()
    latest_interaction_at = interactions[-1].get("fecha") or last_interaction_at
    db_instance.upsert_recent_memory(
        summary_text,
        memory_date=resolved_date,
        last_interaction_at=latest_interaction_at,
        metadata={
            "source": "llm_recent_memory_summary",
            "interaction_count": len(interactions),
            "generated_at": datetime.now().isoformat(),
        },
    )
    logger.info(f"🧠 [RECENT_MEMORY] Stored summary for {resolved_server} on {resolved_date} ({len(interactions)} interactions)")
    return summary_text


def _should_inject_random_memory(db_instance, memory_count: int) -> bool:
    """Determine if a random memory should be injected based on count and probability.
    
    - If fewer than 10 memories: 10% chance
    - If 10 or more memories: 33% chance
    """
    import random
    if memory_count == 0:
        return False
    if memory_count < 10:
        return random.random() < 0.10  # 10% chance
    return random.random() < 0.33  # 33% chance


def _get_random_memory_for_injection(db_instance) -> tuple[str | None, int | None]:
    """Get a random notable memory for injection and increment its usage count.
    
    Returns:
        Tuple of (memory_text, memory_id) or (None, None) if no memories exist
    """
    memory = db_instance.get_random_notable_memory()
    if not memory:
        return None, None
    memory_id = memory.get("id")
    memory_text = memory.get("memory_text")
    if memory_id:
        db_instance.increment_memory_usage(memory_id)
    return memory_text, memory_id


def _extract_memory_from_summary(summary_response: str) -> tuple[str, str | None]:
    """Extract the new memory paragraph and notable memory from LLM response.
    
    Expected format:
    ---NUEVA_MEMORIA---
    [new memory paragraph]
    ---RECUERDO_EXTRAIDO---
    [extracted memory or NO_MEMORY]
    
    Or fallback format:
    ---NEW_MEMORY---
    [new memory paragraph]
    ---EXTRACTED_MEMORY---
    [extracted memory or NO_MEMORY]
    
    Returns:
        Tuple of (new_memory_text, extracted_memory or None)
    """
    import re
    
    if not summary_response:
        return "", None
    
    # Try Spanish format first
    spanish_pattern = r"---NUEVA_MEMORIA---\s*(.*?)\s*---RECUERDO_EXTRAIDO---\s*(.*?)\s*(?:\n|$)"
    english_pattern = r"---NEW_MEMORY---\s*(.*?)\s*---EXTRACTED_MEMORY---\s*(.*?)\s*(?:\n|$)"
    
    match = re.search(spanish_pattern, summary_response, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(english_pattern, summary_response, re.DOTALL | re.IGNORECASE)
    
    if match:
        new_memory = match.group(1).strip()
        extracted = match.group(2).strip()
        
        # Check if extracted is NO_MEMORY or empty
        if extracted.upper() in ["NO_MEMORY", "NO MEMORY", "NONE", "", "NO_MEMORIA", "NO MEMORIA"]:
            return new_memory, None
        return new_memory, extracted
    
    # If no structured format found, return the whole response as new memory
    return summary_response.strip(), None


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
        recent_summary = generate_recent_memory_summary(
            server_name=resolved_server,
            target_date=resolved_date,
            force=force,
        )
    if not recent_summary:
        if previous_summary:
            return previous_summary
        fallback = _get_daily_memory_fallback()
        db_instance.upsert_daily_memory(
            fallback,
            memory_date=resolved_date,
            metadata={"source": "daily_memory_fallback", "interaction_count": 0},
        )
        return fallback
    
    # Determine if we should inject a random memory
    memory_count = db_instance.count_notable_memories()
    injected_memory = None
    if _should_inject_random_memory(db_instance, memory_count):
        injected_memory, _ = _get_random_memory_for_injection(db_instance)
        if injected_memory:
            logger.info(f"🧠 [DAILY_MEMORY] Injecting random notable memory ({memory_count} total memories)")
    
    system_instruction = engine._build_system_prompt(engine.PERSONALIDAD)
    summary_prompt = _build_daily_summary_prompt(previous_summary, recent_summary, resolved_date, injected_memory)
    summary_response = _call_llm_async(system_instruction, summary_prompt)
    
    # Extract new memory and notable memory from response
    new_memory_text, extracted_memory = _extract_memory_from_summary(summary_response or "")
    
    # Use extracted memory, or fallback to previous or default
    summary_text = new_memory_text.strip() if new_memory_text else (previous_summary or _get_daily_memory_fallback())
    
    # Store extracted memory if present
    if extracted_memory:
        memory_id = db_instance.add_notable_memory(
            memory_text=extracted_memory,
            memory_date=resolved_date,
            source_paragraph=previous_summary[:500] if previous_summary else None,  # Store first 500 chars as context
        )
        if memory_id:
            logger.info(f"🧠 [DAILY_MEMORY] Extracted and stored notable memory: '{extracted_memory[:60]}...'")
    
    db_instance.upsert_daily_memory(
        summary_text,
        memory_date=resolved_date,
        metadata={
            "source": "llm_daily_summary",
            "recent_memory_used": bool(recent_summary),
            "generated_at": datetime.now().isoformat(),
            "memory_injected": bool(injected_memory),
            "memory_extracted": bool(extracted_memory),
        },
    )
    logger.info(f"🧠 [DAILY_MEMORY] Stored summary for {resolved_server} on {resolved_date} (memories: {memory_count}, injected: {bool(injected_memory)}, extracted: {bool(extracted_memory)})")
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
    new_interactions = db_instance.get_user_interactions_since(user_id, since_iso=last_interaction_at, limit=25)
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
        new_interactions = db_instance.get_user_interactions_since(user_id, since_iso=None, limit=25)

    system_instruction = engine._build_system_prompt(engine.PERSONALIDAD)
    summary_prompt = _build_relationship_summary_prompt(previous_summary, new_interactions, user_name, resolved_date)
    summary_response = _call_llm_async(system_instruction, summary_prompt)
    summary_text = (summary_response or "").strip() or previous_summary or _get_relationship_memory_fallback(user_name)

    latest_interaction_at = last_interaction_at
    if new_interactions:
        latest_interaction_at = new_interactions[-1].get("fecha") or last_interaction_at

    metadata = {
        "user_name": user_name or "",
        "source": "llm_relationship_summary",
        "interaction_count": len(new_interactions),
        "generated_at": datetime.now().isoformat(),
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
    logger.info(f"🧠 [RELATIONSHIP_MEMORY] Stored summary for user={user_id} server={resolved_server} date={resolved_date}")
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
        new_interactions = db_instance.get_user_interactions_since(user_id, since_iso=last_interaction_at, limit=25)
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
    engine = _engine()
    relationship_state = db_instance.get_user_relationship_memory(user_id)
    daily_record = db_instance.get_user_relationship_daily_memory(user_id)
    pending = db_instance.get_pending_relationship_refresh(user_id)
    should_refresh = False
    if pending and pending.get("status") == "pending":
        scheduled_for = engine._parse_iso_datetime(pending.get("scheduled_for"))
        if scheduled_for and scheduled_for <= datetime.now():
            should_refresh = True
    if should_refresh:
        try:
            generate_user_relationship_memory_summary(
                user_id=user_id,
                user_name=user_name,
                server_name=db_instance.server_name,
            )
            relationship_state = db_instance.get_user_relationship_memory(user_id)
            daily_record = db_instance.get_user_relationship_daily_memory(user_id)
        except Exception as e:
            logger.warning(f"⚠️ [RELATIONSHIP_MEMORY] Lazy refresh failed for user={user_id}: {e}")
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


def _render_user_prompt(context: dict) -> str:
    lines = [
        "## MEMORIA DE PUTRE (Lo que recuerdas):",
        "[RECUERDOS]",
        context["daily_memory"],
        "[RECUERDOS RECIENTES]",
        context["recent_memory"],
    ]
    if context.get("include_user_memory", False):
        lines.extend([
            "[SOBRE TU RELACION CON EL USUARIO]",
            context["relationship_memory"],
            "[ULTIMOS SUCCESOS/INTERACIONES DE HACE MENOS DE 1H]",
            context["recent_dialogue_text"],
        ])
    for injected_block in [context.get("keyword_injection", ""), context.get("mission_injection", "")]:
        if injected_block:
            lines.extend(["", injected_block])
    lines.extend(["", "## REGLAS DE ORO DE ESTA RESPUESTA:"])
    lines.extend(_engine()._get_response_rules_lines())
    lines.extend([
        "",
        "## MENSAJE DEL UMANO:",
        f'"{context["user_message"]}"',
        "",
        "## RESPUESTA DE PUTRE:",
    ])
    return "\n".join(lines)


def _build_prompt_context(
    role_context,
    user_content="",
    is_public=False,
    server=None,
    mission_prompt_key: str | None = None,
    user_id=None,
    user_name=None,
    interaction_type="chat",
):
    engine = _engine()
    bot_name = engine.PERSONALIDAD.get("name", "Bot")
    content = (user_content or "").strip()
    server_name = server or get_active_server_name()
    if not server_name:
        logger.warning("🧠 [MIND] No server context available, skipping memory-backed prompt enrichment")
        server_name = None
    db_instance = get_global_db(server_name=server_name) if server_name else None
    include_user_memory = interaction_type in {"chat", "mention", "greet"} and user_id is not None
    recent_dialogue = db_instance.get_recent_dialogue_window(user_id, within_minutes=60, max_pairs=15) if include_user_memory and db_instance else []
    daily_memory = _build_daily_memory_text(db_instance) if db_instance else ""
    recent_memory = _build_recent_memory_text(db_instance) if db_instance else ""
    relationship_memory = ""
    if include_user_memory and db_instance:
        relationship_memory = _refresh_relationship_memory_if_due(db_instance, user_id, user_name, recent_dialogue)
        db_instance.schedule_relationship_refresh(user_id, delay_minutes=60)
    keyword_injection = engine._get_keyword_injection(content)
    mission_injection = engine._get_mission_injection(role_context, mission_prompt_key, content)
    if not content and mission_injection:
        content = mission_injection.splitlines()[0]
    if not content:
        content = bot_name
    return {
        "bot_name": bot_name,
        "server_name": server_name,
        "is_public": is_public,
        "include_user_memory": include_user_memory,
        "daily_memory": daily_memory,
        "recent_memory": recent_memory,
        "relationship_memory": relationship_memory,
        "recent_dialogue_text": _build_recent_dialogue_section(recent_dialogue),
        "keyword_injection": keyword_injection,
        "mission_injection": mission_injection,
        "user_message": content,
    }


def _call_llm_async(system_instruction: str, prompt: str) -> str:
    engine = _engine()
    start_time = time.time()

    try:
        if not is_simulation_mode():
            logger.info("🤖 [SUBROLE] Starting call to gemini-3-flash-preview")
            log_final_llm_prompt(
                provider="gemini",
                call_type="subrole_async",
                system_instruction=system_instruction,
                user_prompt=prompt,
            )

            client_gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            result_queue = queue.Queue()
            exception_queue = queue.Queue()

            def call_gemini():
                try:
                    res = client_gemini.models.generate_content(
                        model='gemini-3.1-flash-lite-preview',
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.9,
                            max_output_tokens=1024,
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

            if not gemini_thread.is_alive() and exception_queue.empty():
                res = result_queue.get()
                text = res.text
                if text and len(text.strip()) > 5:
                    postprocessed = postprocess_response(text)
                    total_time = time.time()
                    logger.info(f"🏁 [SUBROLE] Gemini completed in {(total_time - start_time):.2f}s: {len(postprocessed)} chars")
                    return postprocessed
            else:
                logger.info("🤖 [SUBROLE] Gemini timeout/error, fallback to Groq")
        else:
            logger.info("🤖 [SUBROLE] Simulation mode, using Groq")
    except Exception as e:
        logger.info(f"🤖 [SUBROLE] Gemini failed, fallback to Groq: {e}")

    try:
        logger.info("🤖 [SUBROLE] Starting call to llama-3.3-70b-versatile")
        log_final_llm_prompt(
            provider="groq",
            call_type="subrole_async",
            system_instruction=system_instruction,
            user_prompt=prompt,
        )

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
        logger.info(f"🏁 [SUBROLE] Groq completed in {(total_time - start_time):.2f}s: {len(postprocessed)} chars")
        return postprocessed
    except Exception as e:
        logger.error(f"🤖 [SUBROLE] Both LLMs failed: {e}")
        return "[Error in internal subrole task]"


def generate_readme() -> str:
    """Generate comprehensive README documentation for all bot functions."""
    engine = _engine()
    readme_path = os.path.join(engine._BASE_DIR, "README_LLM.md")

    try:
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as file_handle:
                readme_content = file_handle.read()
            logger.info(f"📖 [README] Loaded structured README from {readme_path}")
            return readme_content
        logger.warning(f"⚠️ [README] Structured file not found: {readme_path}")
        return _generate_fallback_readme()
    except Exception as e:
        logger.error(f"❌ [README] Error reading structured file: {e}")
        return _generate_fallback_readme()


def _generate_fallback_readme() -> str:
    """Generate fallback README content when the structured file is unavailable."""
    return """# ROLEAGENTBOT - COMMAND REFERENCE

## CORE COMMANDS
- !agenthelp - Show comprehensive help
- !ping - Check bot latency
- !hello - Greet the bot
- !insult @user - Playful insult
- !test - Test bot functionality

## ROLES
- News Watcher: !watchnews, !stopnews, !newsfrequency
- Treasure Hunter: !hunteradd, !hunterdel, !hunterlist
- Trickster: !trickster help, !dice play, !accuse
- Banker: !banker balance, !banker bonus
- Music: !mc play, !mc add, !mc queue

## USAGE
- Mention bot for conversation
- Commands start with !
- Admin permissions required for some functions"""


def build_readme_enhanced_prompt(original_user_content: str, readme_content: str) -> str:
    """Build the second-pass README prompt used to answer help requests in character."""
    engine = _engine()
    try:
        personality_name = engine.PERSONALIDAD.get("name", "").lower()
        prompts_path = os.path.join(engine._BASE_DIR, "personalities", personality_name, "prompts.json")
        if os.path.exists(prompts_path):
            with open(prompts_path, "r", encoding="utf-8") as file_handle:
                prompts_config = json.load(file_handle)
            task_instruction = prompts_config.get("readme_enhanced_prompt", {}).get("task")
            if task_instruction:
                logger.info(f"📖 [README] Loaded task instruction from {personality_name}/prompts.json")
                return f"""ORIGINAL USER QUESTION: {original_user_content}

HERE IS THE COMPLETE DOCUMENTATION YOU NEED TO EXPLAIN:

{readme_content}

{task_instruction}"""
    except Exception as e:
        logger.warning(f"⚠️ [README] Could not load personality prompts.json: {e}")

    logger.info("📖 [README] Using fallback task instruction")
    return f"""ORIGINAL USER QUESTION: {original_user_content}

HERE IS THE COMPLETE DOCUMENTATION YOU NEED TO EXPLAIN:

{readme_content}

TASK: Explain the relevant parts of this documentation to answer the user's question. Keep your response SHORT, IN CHARACTER, and focused on what they specifically asked about. Do NOT copy-paste the entire documentation. Instead, explain it naturally as if you're teaching them how to use the bot.

Remember to maintain your personality and use your characteristic speech patterns."""


def _build_readme_system_prompt(personalidad: dict) -> str:
    """Build the README-specific system prompt with second-pass response rules."""
    engine = _engine()
    base_system_prompt = engine._build_system_prompt(personalidad)
    readme_rules = engine._get_readme_response_rules_lines()
    if not readme_rules:
        return base_system_prompt

    readme_rules_text = "\n".join([f"- {rule}" for rule in readme_rules])
    return f"""{base_system_prompt}

## README SECOND PASS RULES
{readme_rules_text}"""


def _call_llm_with_readme(system_instruction: str, enhanced_prompt: str, is_mission: bool = False) -> str:
    """Call the LLM for README-enhanced second-pass responses."""
    engine = _engine()
    logger.info("🤖 [README] Calling LLM with enhanced documentation prompt")

    if not is_simulation_mode():
        try:
            logger.info("🤖 [README-GEMINI] Starting call to gemini-3-flash-preview")
            log_final_llm_prompt(
                provider="gemini",
                call_type="readme_second_pass",
                system_instruction=system_instruction,
                user_prompt=enhanced_prompt,
                metadata={"is_mission": is_mission},
            )
            client_gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            result_queue = queue.Queue()
            exception_queue = queue.Queue()

            def call_gemini():
                try:
                    res = client_gemini.models.generate_content(
                        model='gemini-3.1-flash-lite-preview',
                        contents=enhanced_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.8,
                            max_output_tokens=800,
                            top_p=0.9,
                            safety_settings=[types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE")],
                        ),
                    )
                    result_queue.put(res)
                except Exception as e:
                    exception_queue.put(e)

            thread = threading.Thread(target=call_gemini)
            thread.start()
            thread.join(timeout=8.0)

            if thread.is_alive():
                logger.warning("⚠️ [README-GEMINI] Timeout, fallback to Groq")
            elif not exception_queue.empty():
                raise exception_queue.get()
            else:
                res = result_queue.get()
                if res.text:
                    text = res.text.strip()
                    if not is_blocked_response(text):
                        final_response = postprocess_response(text)
                        logger.info(f"✅ [README-GEMINI] Enhanced response: {len(final_response)} chars")
                        return final_response
        except Exception as e:
            logger.warning(f"⚠️ [README-GEMINI] Error: {e}, fallback to Groq")

    try:
        logger.info("🤖 [README-GROQ] Starting call to llama-3.3-70b-versatile")
        log_final_llm_prompt(
            provider="groq",
            call_type="readme_second_pass",
            system_instruction=system_instruction,
            user_prompt=enhanced_prompt,
            metadata={"is_mission": is_mission},
        )
        completion = get_groq_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": enhanced_prompt},
            ],
            temperature=0.8,
            top_p=0.9,
            max_tokens=800,
            presence_penalty=0.8,
            frequency_penalty=0.8,
        )
        text = completion.choices[0].message.content.strip()
        if not is_blocked_response(text):
            final_response = postprocess_response(text)
            logger.info(f"✅ [README-GROQ] Enhanced response: {len(final_response)} chars")
            return final_response
    except Exception as e:
        logger.error(f"❌ [README-GROQ] Critical error: {e}")

    logger.warning("🚫 [README] All LLM attempts failed, using basic README")
    return generate_readme()


def _process_readme_response(final_response, content, role_context, server, start_time, is_mission: bool = False):
    """Process README-only responses by running a second LLM pass over the project README."""
    if is_readme_response(final_response) and is_help_request(content):
        engine = _engine()
        logger.info("📖 [README] Help request detected, generating enhanced documentation response")
        readme_content = generate_readme()
        enhanced_prompt = build_readme_enhanced_prompt(content, readme_content)
        system_instruction = _build_readme_system_prompt(engine.PERSONALIDAD)
        log_readme_enhanced_prompt(
            content,
            readme_content,
            enhanced_prompt,
            system_instruction=system_instruction,
            role=role_context,
            server=server,
        )
        enhanced_response = _call_llm_with_readme(system_instruction, enhanced_prompt, is_mission)
        log_agent_response(enhanced_response, role=role_context, server=server, response_length=len(enhanced_response))
        total_time = time.time()
        logger.info(f"🏁 [README-ENHANCED] Process completed in {(total_time - start_time):.2f}s total")
        logger.info("=" * 60)
        return enhanced_response
    return None


def think(
    role_context,
    user_content="",
    history_list=None,
    is_public=False,
    logger=None,
    mission_prompt_key: str | None = None,
    user_id=None,
    user_name=None,
    server_name=None,
    interaction_type="chat",
):
    engine = _engine()
    start_time = time.time()

    if logger is None:
        from agent_logging import get_logger as _get_logger
        logger = _get_logger('agent_engine')

    current_usage = runtime_increment_usage(engine.PERSONALIDAD.get("name", "unknown"))
    logger.info(f"🚀 [THINK] Iniciando proceso - Uso diario: {current_usage}/20")

    content = (user_content or "").strip()
    is_mission = not bool(content)
    server = server_name or get_active_server_name()
    system_instruction, prompt_final = engine.build_prompt(
        role_context,
        content,
        is_public=is_public,
        server=server,
        mission_prompt_key=mission_prompt_key,
        user_id=user_id,
        user_name=user_name,
        interaction_type=interaction_type,
    )

    prep_time = time.time()
    logger.info(f"⚡ [THINK] Preparation completed in {(prep_time - start_time):.2f}s")
    logger.info(f"🧠 [KRONK] RESPONSE GENERATION - Daily usage: {current_usage}/20")
    logger.info(f"📝 Context: {len(system_instruction)} chars system | {len(prompt_final)} chars prompt")
    logger.info(f"💬 History: {len(history_list or [])} interactions | Public: {is_public}")
    logger.info(f"🎯 Type: {'MISSION' if is_mission else 'CHAT'}")
    logger.info(f"🎯 Role: {role_context[:80]}..." if len(role_context) > 80 else f"🎯 Role: {role_context}")
    if is_mission:
        logger.info(f"📋 Full prompt: {prompt_final[:200]}..." if len(prompt_final) > 200 else f"📋 Full prompt: {prompt_final}")
    logger.info("=" * 60)

    if not is_simulation_mode() and current_usage <= 20:
        try:
            gemini_start = time.time()
            logger.info("🤖 [GEMINI] Starting call to gemini-3-flash-preview")
            logger.info(f"   └─ Temp: {0.9 if is_mission else 0.95} | Max tokens: 1024")
            logger.info("   └─ Top-p: 0.95")
            log_final_llm_prompt(
                provider="gemini",
                call_type="think",
                system_instruction=system_instruction,
                user_prompt=prompt_final,
                role=role_context,
                server=server,
                metadata={
                    "interaction_type": interaction_type,
                    "is_public": is_public,
                    "is_mission": is_mission,
                },
            )

            client_gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            result_queue = queue.Queue()
            exception_queue = queue.Queue()

            def call_gemini():
                try:
                    thread_start = time.time()
                    logger.info("🧵 [GEMINI] Thread started")
                    res = client_gemini.models.generate_content(
                        model='gemini-3.1-flash-lite-preview',
                        contents=prompt_final,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.9 if is_mission else 0.95,
                            max_output_tokens=1024,
                            top_p=0.95,
                            safety_settings=[types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE")]
                        )
                    )
                    thread_end = time.time()
                    logger.info(f"🧵 [GEMINI] Thread completed in {(thread_end - thread_start):.2f}s")
                    result_queue.put(res)
                except Exception as e:
                    exception_queue.put(e)

            thread_launch_start = time.time()
            gemini_thread = threading.Thread(target=call_gemini)
            gemini_thread.start()
            gemini_thread.join(timeout=5.0)
            thread_launch_end = time.time()
            logger.info(f"⏱️ [GEMINI] Thread execution time: {(thread_launch_end - thread_launch_start):.2f}s")

            if gemini_thread.is_alive():
                timeout_time = time.time()
                logger.warning(f"⚠️ [GEMINI] Timeout of 5s reached in {(timeout_time - gemini_start):.2f}s total, fallback to Groq")
            elif not exception_queue.empty():
                error_time = time.time()
                exception = exception_queue.get()
                logger.error(f"❌ [GEMINI] Error en {(error_time - gemini_start):.2f}s: {exception}")
                raise exception
            else:
                success_time = time.time()
                logger.info(f"✅ [GEMINI] Response received in {(success_time - gemini_start):.2f}s total")
                res = result_queue.get()
                if res.text:
                    text = res.text.strip()
                    logger.info(f"✅ [GEMINI] Response received: {len(text)} chars")
                    logger.info(f"   └─ Preview: {text[:80]}..." if len(text) > 80 else f"   └─ Preview: {text}")

                    if is_blocked_response(text):
                        logger.warning("🚫 [GEMINI] Response blocked, using emergency fallback")
                        return engine._fallback_response()

                    if len(text) < 50:
                        logger.warning(f"⚠️ [GEMINI] Very short response ({len(text)} chars), fallback to Groq")
                    else:
                        postprocess_start = time.time()
                        final_response = postprocess_response(text)
                        postprocess_end = time.time()
                        logger.info(f"✨ [GEMINI] Post-processed in {(postprocess_end - postprocess_start):.2f}s: {len(final_response)} chars")

                        readme_result = _process_readme_response(final_response, content, role_context, server, start_time, is_mission)
                        if readme_result is not None:
                            return readme_result

                        log_agent_response(final_response, role=role_context, server=server, response_length=len(final_response))
                        total_time = time.time()
                        logger.info(f"🏁 [GEMINI] Process completed in {(total_time - start_time):.2f}s total")
                        logger.info("=" * 60)
                        return final_response
        except Exception as e:
            error_time = time.time()
            error_msg = str(e).lower()
            if "quota" in error_msg or "limit" in error_msg or "429" in error_msg:
                logger.warning(f"⚠️ [GEMINI] Token/quota limit reached in {(error_time - start_time):.2f}s: {e}")
            else:
                logger.error(f"⚠️ [GEMINI] Failure in {(error_time - start_time):.2f}s: {e}")
            logger.info("   └─ Fallback to Groq activated")

    try:
        groq_start = time.time()
        if current_usage > 20:
            logger.info(f"🤖 [GROQ] Gemini daily limit reached ({current_usage}/20)")
        logger.info("🤖 [GROQ] Starting call to llama-3.3-70b-versatile")
        logger.info(f"   └─ Temp: {0.95 if is_mission else 1.0} | Max tokens: 600")
        logger.info("   └─ Top-p: 1.0 | Presence: 1.0 | Frequency: 1.0")
        log_final_llm_prompt(
            provider="groq",
            call_type="think",
            system_instruction=system_instruction,
            user_prompt=prompt_final,
            role=role_context,
            server=server,
            metadata={
                "interaction_type": interaction_type,
                "is_public": is_public,
                "is_mission": is_mission,
            },
        )

        api_call_start = time.time()
        completion = get_groq_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt_final}
            ],
            temperature=0.95 if is_mission else 1.0,
            top_p=1.0,
            max_tokens=600,
            presence_penalty=1.0,
            frequency_penalty=1.0
        )
        api_call_end = time.time()
        logger.info(f"⚡ [GROQ] API call completed in {(api_call_end - api_call_start):.2f}s")

        text = completion.choices[0].message.content.strip()
        response_time = time.time()
        logger.info(f"✅ [GROQ] Response received in {(response_time - groq_start):.2f}s total: {len(text)} chars")
        logger.info(f"   └─ Preview: {text[:80]}..." if len(text) > 80 else f"   └─ Preview: {text}")

        if is_blocked_response(text):
            logger.warning("🚫 [GROQ] Response blocked, using emergency fallback")
            return engine._fallback_response()

        postprocess_start = time.time()
        final_response = postprocess_response(text)
        postprocess_end = time.time()
        logger.info(f"✨ [GROQ] Post-processed in {(postprocess_end - postprocess_start):.2f}s: {len(final_response)} chars")

        readme_result = _process_readme_response(final_response, content, role_context, server, start_time, is_mission)
        if readme_result is not None:
            return readme_result

        log_agent_response(final_response, role=role_context, server=server, response_length=len(final_response))
        total_time = time.time()
        logger.info(f"🏁 [GROQ] Process completed in {(total_time - start_time):.2f}s total")
        logger.info("=" * 60)
        return final_response
    except Exception as e:
        error_time = time.time()
        logger.error(f"❌ [GROQ] Critical error in {(error_time - start_time):.2f}s: {e}")
        logger.info("   └─ Using emergency fallback")
        logger.info("=" * 60)
        return engine._fallback_response()
