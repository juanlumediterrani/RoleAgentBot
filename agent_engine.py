import os
import json
import random
from datetime import datetime, timedelta
from agent_logging import get_logger
from postprocessor import postprocess_response, is_blocked_response
from agent_db import get_global_db
from prompts_logger import log_system_prompt, log_agent_response, log_final_llm_prompt
from agent_runtime import increment_usage as runtime_increment_usage, get_personality_directory
from pathlib import Path
from dotenv import load_dotenv
import logging

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_AGENT_CONFIG_PATH = os.path.join(_BASE_DIR, "agent_config.json")

load_dotenv()
logger = logging.getLogger(__name__)

with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
    AGENT_CFG = json.load(f)


def _load_personality_descriptions(server_id: str = None) -> dict:
    """Load personality descriptions from descriptions.json using server-specific directory."""
    try:
        # Use server-specific personality directory
        from agent_runtime import get_personality_directory
        personality_dir = get_personality_directory(server_id)
        descriptions = {}
        
        # Load main descriptions.json
        descriptions_path = os.path.join(personality_dir, "descriptions.json")
        if os.path.exists(descriptions_path):
            with open(descriptions_path, encoding="utf-8") as f:
                descriptions = json.load(f).get("discord", {})
        
        # Load news_watcher descriptions from separate file
        news_watcher_descriptions_path = os.path.join(personality_dir, "descriptions", "news_watcher.json")
        if os.path.exists(news_watcher_descriptions_path):
            with open(news_watcher_descriptions_path, encoding="utf-8") as f:
                news_watcher_data = json.load(f)
                descriptions["news_watcher"] = news_watcher_data
        
        # Load treasure_hunter descriptions from separate file
        treasure_hunter_descriptions_path = os.path.join(personality_dir, "descriptions", "treasure_hunter.json")
        if os.path.exists(treasure_hunter_descriptions_path):
            with open(treasure_hunter_descriptions_path, encoding="utf-8") as f:
                treasure_hunter_data = json.load(f)
                descriptions["treasure_hunter"] = treasure_hunter_data
        
        # Load trickster descriptions from separate file
        trickster_descriptions_path = os.path.join(personality_dir, "descriptions", "trickster.json")
        if os.path.exists(trickster_descriptions_path):
            with open(trickster_descriptions_path, encoding="utf-8") as f:
                trickster_data = json.load(f)
                descriptions["trickster"] = trickster_data
        
        # Load banker descriptions from separate file
        banker_descriptions_path = os.path.join(personality_dir, "descriptions", "banker.json")
        if os.path.exists(banker_descriptions_path):
            with open(banker_descriptions_path, encoding="utf-8") as f:
                banker_descriptions = json.load(f)
                # Merge banker descriptions into roles_view_messages
                if "roles_view_messages" not in descriptions:
                    descriptions["roles_view_messages"] = {}
                descriptions["roles_view_messages"]["banker"] = banker_descriptions
        
        # Load mc descriptions from separate file
        mc_descriptions_path = os.path.join(personality_dir, "descriptions", "mc.json")
        if os.path.exists(mc_descriptions_path):
            with open(mc_descriptions_path, encoding="utf-8") as f:
                mc_descriptions = json.load(f)
                # Merge mc descriptions into roles_view_messages
                if "roles_view_messages" not in descriptions:
                    descriptions["roles_view_messages"] = {}
                descriptions["roles_view_messages"]["mc"] = mc_descriptions
        
        return descriptions
    except Exception as e:
        logger.warning(f"Could not load personality descriptions.json: {e}")
    return {}

# --- MC CONFIGURATION FUNCTIONS ---
def get_mc_mode():
    """Get MC execution mode from config."""
    mc_config = AGENT_CFG.get("roles", {}).get("mc", {})
    return mc_config.get("mode", "integrated")  # default: integrated

def is_mc_enabled():
    """Check if MC is enabled."""
    mc_config = AGENT_CFG.get("roles", {}).get("mc", {})
    return mc_config.get("enabled", False)

def get_mc_config():
    """Get complete MC configuration."""
    return AGENT_CFG.get("roles", {}).get("mc", {})

def get_mc_feature(feature_name):
    """Get specific MC feature."""
    mc_config = get_mc_config()
    features = mc_config.get("features", {})
    return features.get(feature_name, False)

def get_mc_voice_settings():
    """Get MC voice configuration."""
    mc_config = get_mc_config()
    return mc_config.get("voice_settings", {})

def get_mc_audio_quality():
    """Get MC audio quality configuration."""
    mc_config = get_mc_config()
    return mc_config.get("audio_quality", {})

def _get_subrole_frequency_from_config(subrole_name: str) -> int:
    """Get subrole frequency from agent_config.json."""
    try:
        # Load agent_config.json
        with open(_AGENT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Navigate to subrole frequency
        roles_cfg = config.get("roles", {})
        trickster_cfg = roles_cfg.get("trickster", {})
        subroles_cfg = trickster_cfg.get("subroles", {})
        subrole_cfg = subroles_cfg.get(subrole_name, {})
        
        return subrole_cfg.get("frequency_hours", 12)  # Default to 12 hours
        
    except Exception as e:
        logger.warning(f"Could not get frequency for {subrole_name} from config: {e}")
        return 12  # Default fallback

def _cargar_personalidad(server_id: str = None) -> dict:
    logger.info(f"🧬 [PERSONALITY] _cargar_personalidad called with server_id={server_id}")
    # First check for server-specific personality configuration
    personality_rel = None
    language = "en-US"  # Default language
    active_personality_name = None  # Track the personality name for server-dir lookup
    if server_id:
        try:
            server_config_path = os.path.join(_BASE_DIR, "databases", server_id, "server_config.json")
            if os.path.exists(server_config_path):
                with open(server_config_path, encoding="utf-8") as f:
                    server_cfg = json.load(f)
                active_personality = server_cfg.get("active_personality")
                if active_personality:
                    # Get language from server config, default to en-US
                    language = server_cfg.get("language", "en-US")
                    active_personality_name = active_personality
                    # New structure: personalities/<name>/<language>/personality.json
                    personality_rel = f"personalities/{active_personality}/{language}/personality.json"
                    logger.debug(f"🧬 [PERSONALITY] Using server-specific personality: {active_personality} ({language})")
        except Exception as e:
            logger.debug(f"Could not load server config for personality: {e}")
    
    # Fall back to global config if no server-specific config
    if not personality_rel:
        with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        # Use new fields: default_personality and default_language
        default_personality = agent_cfg.get("default_personality", "rab")
        default_language = agent_cfg.get("default_language", "en-US")
        active_personality_name = default_personality
        # Construct path with language subdirectory
        personality_rel = f"personalities/{default_personality}/{default_language}/personality.json"
        logger.debug(f"🧬 [PERSONALITY] Using default personality from agent_config.json: {default_personality} ({default_language})")
    
    personality_path = os.path.join(_BASE_DIR, personality_rel)
    
    # Base personality directory (legacy/template source)
    base_personality_dir = os.path.dirname(personality_path)
    personality_dir = base_personality_dir
    
    # Check for server-specific personality directory: databases/<server_id>/<personality_name>/
    # NOTE: active_personality_name must be used here — NOT os.path.basename(base_personality_dir)
    # which would return the language code (e.g. "es-ES") instead of the personality name.
    logger.info(f"🧬 [PERSONALITY] server_id={server_id}, active_personality_name={active_personality_name}")
    logger.info(f"🧬 [PERSONALITY] base_personality_dir={base_personality_dir}")
    if server_id and active_personality_name:
        try:
            server_personality_dir = os.path.join(_BASE_DIR, "databases", server_id, active_personality_name)
            server_personality_json = os.path.join(server_personality_dir, 'personality.json')
            logger.info(f"🧬 [PERSONALITY] server_personality_dir={server_personality_dir}")
            logger.info(f"🧬 [PERSONALITY] server_personality_json exists={os.path.exists(server_personality_json)}")
            
            # If server directory doesn't exist, create it
            if not os.path.exists(server_personality_dir):
                os.makedirs(server_personality_dir, exist_ok=True)
                logger.info(f"🧬 [PERSONALITY] Created server personality directory: {server_personality_dir}")
            
            # If personality.json doesn't exist in server directory, copy from base
            if not os.path.exists(server_personality_json):
                logger.info(f"🧬 [PERSONALITY] Copying personality files from {base_personality_dir} to {server_personality_dir}")
                import shutil
                # Copy all JSON files from base personality to server directory
                for json_file in ['personality.json', 'prompts.json', 'descriptions.json']:
                    src_file = os.path.join(base_personality_dir, json_file)
                    dst_file = os.path.join(server_personality_dir, json_file)
                    if os.path.exists(src_file):
                        shutil.copy2(src_file, dst_file)
                        logger.debug(f"  Copied: {json_file}")
                # Copy descriptions subdirectory if exists
                src_desc_dir = os.path.join(base_personality_dir, 'descriptions')
                dst_desc_dir = os.path.join(server_personality_dir, 'descriptions')
                if os.path.exists(src_desc_dir) and os.path.isdir(src_desc_dir):
                    if os.path.exists(dst_desc_dir):
                        shutil.rmtree(dst_desc_dir)
                    shutil.copytree(src_desc_dir, dst_desc_dir)
                    logger.debug(f"  Copied: descriptions/ directory")
            
            # Now use server directory if files exist
            if os.path.exists(server_personality_json):
                personality_dir = server_personality_dir
                logger.info(f"🧬 [PERSONALITY] Using server-local personality from {server_personality_dir}")
            else:
                logger.warning(f"🧬 [PERSONALITY] Could not copy personality to server directory, using base: {base_personality_dir}")
        except Exception as e:
            logger.warning(f"Could not get server personality directory: {e}")
    
    # Load personality from selected directory (server or base)
    merged_personality = {}
    
    if os.path.exists(os.path.join(personality_dir, 'personality.json')) and \
       os.path.exists(os.path.join(personality_dir, 'prompts.json')):
        # Load split files
        personality_file = os.path.join(personality_dir, 'personality.json')
        with open(personality_file, encoding="utf-8") as f:
            merged_personality.update(json.load(f))
        
        prompts_file = os.path.join(personality_dir, 'prompts.json')
        with open(prompts_file, encoding="utf-8") as f:
            merged_personality.update(json.load(f))
        
        descriptions_file = os.path.join(personality_dir, 'descriptions.json')
        if os.path.exists(descriptions_file):
            with open(descriptions_file, encoding="utf-8") as f:
                descriptions_data = json.load(f)
                if 'discord' not in merged_personality:
                    merged_personality['discord'] = {}
                merged_personality['discord'].update(descriptions_data.get('discord', {}))
                merged_personality['descriptions'] = descriptions_data.get('discord', {})
        
        return merged_personality
    
    else:
        # Load single file structure
        with open(personality_path, encoding="utf-8") as f:
            return json.load(f)


# Dynamic personality loading with server-specific cache
# Cache is now a dict keyed by server_id
_personality_cache = {}

def _get_personality(server_id: str = None) -> dict:
    """
    Get personality with server-specific caching.
    
    This function dynamically loads personality based on the active server,
    caching the result to avoid repeated file reads for the same server.
    
    The cache is validated against server_config.json to detect personality
    changes made by other processes (e.g. Discord Canvas changing personality
    while the scheduler process still has the old personality cached).
    
    Args:
        server_id: Optional server ID to load specific server personality
        
    Returns:
        dict: Personality configuration
    """
    global _personality_cache
    
    # Normalize server_id (None means global/default)
    cache_key = server_id or "global"
    
    # Validate cached personality still matches server_config.json
    # This is critical because personality can change in a different process
    # (Discord bot subprocess) while this process (scheduler) keeps stale cache
    needs_reload = cache_key not in _personality_cache
    if not needs_reload and server_id:
        try:
            server_config_path = os.path.join(_BASE_DIR, "databases", server_id, "server_config.json")
            if os.path.exists(server_config_path):
                with open(server_config_path, encoding="utf-8") as f:
                    server_cfg = json.load(f)
                expected_personality = server_cfg.get("active_personality", "").lower()
                cached_name = _personality_cache[cache_key].get("name", "").lower()
                if expected_personality and cached_name != expected_personality:
                    logger.info(
                        f"🎭 [PERSONALITY] Cache stale for server {server_id}: "
                        f"cached={cached_name}, expected={expected_personality}. Reloading."
                    )
                    needs_reload = True
        except Exception as e:
            logger.debug(f"🎭 [PERSONALITY] Could not validate cache for server {server_id}: {e}")
    
    if needs_reload:
        _personality_cache[cache_key] = _cargar_personalidad(server_id)
        if os.getenv('ROLE_AGENT_PROCESS') != '1':
            logger.info(f"🎭 [PERSONALITY] Loaded: {_personality_cache[cache_key].get('name', 'Unknown')} (server: {server_id})")
    
    return _personality_cache[cache_key]

# Create dynamic PERSONALITY property
class _PersonalityProxy:
    """
    Proxy for dynamic personality loading.
    
    WARNING: This global proxy returns the DEFAULT personality from agent_config.json.
    In multi-server deployments, this may NOT be the correct personality for a specific server.
    Use _get_personality(server_id) instead to get the server-specific personality.
    """
    _warning_logged = False  # Class-level flag to warn only once
    
    def _log_warning_once(self):
        """Log a warning about using global PERSONALITY in multi-server context."""
        if not _PersonalityProxy._warning_logged and os.getenv('ROLE_AGENT_PROCESS') != '1':
            logger.warning(
                "🎭 [PERSONALITY] Using global PERSONALITY proxy. "
                "In multi-server setups, use _get_personality(server_id) for correct server-specific personality. "
                "Global proxy returns DEFAULT personality from agent_config.json, which may cause personality mixing."
            )
            _PersonalityProxy._warning_logged = True
    
    def __getitem__(self, key):
        self._log_warning_once()
        return _get_personality().get(key)
    
    def get(self, key, default=None):
        self._log_warning_once()
        return _get_personality().get(key, default)
    
    def __contains__(self, key):
        self._log_warning_once()
        return key in _get_personality()
    
    def keys(self):
        self._log_warning_once()
        return _get_personality().keys()
    
    def values(self):
        self._log_warning_once()
        return _get_personality().values()
    
    def items(self):
        self._log_warning_once()
        return _get_personality().items()
    
    def __repr__(self):
        self._log_warning_once()
        return repr(_get_personality())

PERSONALITY = _PersonalityProxy()


def reload_personality(server_id: str = None):
    """
    Force reload of personality cache.
    
    Call this when the active server changes to ensure the correct
    server-specific personality is loaded.
    
    Args:
        server_id: Optional specific server ID to reload, or None to clear all cache
    """
    global _personality_cache, _personality_descriptions_cache
    if server_id:
        cache_key = server_id
        if cache_key in _personality_cache:
            del _personality_cache[cache_key]
            logger.info(f"🎭 [PERSONALITY] Cache cleared for server: {server_id}")
        if cache_key in _personality_descriptions_cache:
            del _personality_descriptions_cache[cache_key]
            logger.info(f"📝 [DESCRIPTIONS] Cache cleared for server: {server_id}")
    else:
        _personality_cache = {}
        _personality_descriptions_cache = {}
        logger.info("🎭 [PERSONALITY] All cache cleared")
    # Force reload on next access
    _get_personality(server_id)


# Dynamic personality descriptions with server-specific cache
_personality_descriptions_cache = {}

def _get_personality_descriptions(server_id: str = None) -> dict:
    """
    Get personality descriptions with server-specific caching.
    
    This function dynamically loads descriptions based on the active server,
    caching the result to avoid repeated file reads for the same server.
    
    Args:
        server_id: Optional server ID to load specific server descriptions
        
    Returns:
        dict: Personality descriptions
    """
    global _personality_descriptions_cache
    
    # Normalize server_id (None means global/default)
    cache_key = server_id or "global"
    
    # Check if we need to reload (not in cache)
    if cache_key not in _personality_descriptions_cache:
        _personality_descriptions_cache[cache_key] = _load_personality_descriptions(server_id)
        if os.getenv('ROLE_AGENT_PROCESS') != '1':
            logger.info(f"📝 [DESCRIPTIONS] Loaded for server: {server_id}")
    
    return _personality_descriptions_cache[cache_key]


# Create dynamic _personality_descriptions proxy
class _PersonalityDescriptionsProxy:
    """Proxy for dynamic personality descriptions loading."""
    def __getitem__(self, key):
        return _get_personality_descriptions().get(key)
    
    def get(self, key, default=None):
        return _get_personality_descriptions().get(key, default)
    
    def __contains__(self, key):
        return key in _get_personality_descriptions()
    
    def keys(self):
        return _get_personality_descriptions().keys()
    
    def values(self):
        return _get_personality_descriptions().values()
    
    def items(self):
        return _get_personality_descriptions().items()
    
    def __repr__(self):
        return repr(_get_personality_descriptions())

_personality_descriptions = _PersonalityDescriptionsProxy()


def get_discord_token():
    """Get Discord token specific for active personality."""
    personality_name = PERSONALITY.get("name", "").upper()
    specific_token = os.getenv(f"DISCORD_TOKEN_{personality_name}")
    if specific_token:
        logger.info(f"🔑 Using specific token: DISCORD_TOKEN_{personality_name}")
        return specific_token
    # Fallback to generic token
    fallback_token = os.getenv("DISCORD_TOKEN")
    if fallback_token:
        logger.info(f"🔑 Using generic token: DISCORD_TOKEN")
    else:
        logger.warning("⚠️ No Discord token found (neither specific nor generic)")
    return fallback_token


# Cache to avoid multiple role verifications
_roles_verified = False
_active_tasks_cache = []

def _get_role_prompt_catalog() -> dict:
    role_system_prompts = PERSONALITY.get("roles", {})
    if not isinstance(role_system_prompts, dict):
        return {}
    return role_system_prompts


def _get_active_duty_text(config: dict, server_id: str = None, subrole_name: str = None) -> str:
    if not isinstance(config, dict):
        return ""
    
    duty_text = str(config.get("active_duty") or config.get("mission_active") or "").strip()
    
    # Handle ring subrole special case: replace <accusated_user> placeholder
    if subrole_name == "ring" and server_id and "<accusated_user>" in duty_text:
        try:
            from roles.trickster.subroles.ring.ring_discord import _get_ring_state
            ring_state = _get_ring_state(server_id)
            target_user_name = ring_state.get("target_user_name", "Unknown bearer")
            duty_text = duty_text.replace("<accusated_user>", target_user_name)
            logger.debug(f"🎭 [RING] Replaced <accusated_user> with '{target_user_name}' in system prompt")
        except Exception as e:
            logger.warning(f"🎭 [RING] Failed to replace <accusated_user> placeholder: {e}")
            # Fallback to a generic name if ring state is not available
            duty_text = duty_text.replace("<accusated_user>", "el usuario sospechoso")
    
    # Handle beggar subrole special case: always append current reason regardless of format
    if subrole_name == "beggar" and server_id:
        try:
            from roles.trickster.subroles.beggar.beggar_config import get_beggar_config
            beggar_config = get_beggar_config(server_id)
            
            if beggar_config.is_enabled():
                current_reason = beggar_config.get_current_reason()
                if current_reason:
                    # Always append the reason, regardless of whether duty_text ends with colon
                    if duty_text.strip():
                        # If duty_text ends with colon, append directly, otherwise add separator
                        if duty_text.rstrip().endswith(":"):
                            duty_text = duty_text + " " + current_reason
                        else:
                            duty_text = duty_text + ": " + current_reason
                    else:
                        # If duty_text is empty, just use the reason
                        duty_text = current_reason
                    
                    logger.debug(f"🎭 [BEGGAR] Injected current reason '{current_reason}' in system prompt")
                else:
                    logger.debug("🎭 [BEGGAR] No current reason available, leaving base line unchanged")
            else:
                logger.debug("🎭 [BEGGAR] Beggar not enabled, leaving base line unchanged")
        except Exception as e:
            logger.debug(f"🎭 [BEGGAR] Failed to inject current reason: {e}")
    
    return duty_text


def _get_role_display_name(role_name: str, server_id: str = None) -> str:
    """Get display name from role description files with fallback to technical name.
    
    Args:
        role_name: Technical role name (e.g., "news_watcher")
        server_id: Optional server ID to load from server-specific directory (databases/<server_id>/<personality>/descriptions/)
    
    Returns:
        Display title from descriptions file, or role_name if not found
    """
    try:
        from pathlib import Path
        import json
        import os
        
        def _get_personality_dir():
            """Get the personality directory, prioritizing server-specific copy."""
            try:
                # First try server-specific directory if server_id provided
                if server_id:
                    try:
                        from discord_bot.db_init import get_server_personality_dir
                        server_dir = get_server_personality_dir(server_id)
                        if server_dir:
                            return Path(server_dir)
                    except:
                        pass
                
                # Try to get from agent_runtime (may also use server-specific)
                try:
                    from agent_runtime import get_personality_directory
                    runtime_dir = get_personality_directory(server_id)
                    if runtime_dir:
                        return Path(runtime_dir)
                except:
                    pass
                
                # Fall back to global personality directory
                default_personality = AGENT_CFG.get("default_personality", "rab")
                default_language = AGENT_CFG.get("default_language", "en-US")
                personality_rel = f"personalities/{default_personality}/{default_language}/personality.json"
                personality_path = Path(__file__).parent / personality_rel
                return personality_path.parent
            except:
                # Fallback to putre if something goes wrong
                return Path(__file__).parent / "personalities" / "putre"
        
        personality_dir = _get_personality_dir()
        descriptions_dir = personality_dir / "descriptions"
        
        # Map role names to their description file names
        role_file_map = {
            "news_watcher": "news_watcher.json",
            "treasure_hunter": "treasure_hunter.json",
            "trickster": "trickster.json",
            "banker": "banker.json",
            "mc": "mc.json",
        }
        
        # For main roles, load from individual description files
        if role_name in role_file_map:
            role_desc_path = descriptions_dir / role_file_map[role_name]
            if role_desc_path.exists():
                role_desc = json.loads(role_desc_path.read_text(encoding='utf-8'))
                title = role_desc.get("title", "").replace("**", "").strip()
                if title:
                    return title
        
        # For subroles, load from trickster.json
        subrole_names = {"beggar", "nordic_runes", "dice_game", "ring"}
        if role_name in subrole_names:
            trickster_path = descriptions_dir / "trickster.json"
            if trickster_path.exists():
                trickster_desc = json.loads(trickster_path.read_text(encoding='utf-8'))
                
                # Try to get title from subrole-specific section first
                subrole_section = trickster_desc.get(role_name, {})
                if isinstance(subrole_section, dict):
                    title = subrole_section.get("title", "").replace("**", "").strip()
                    if title:
                        return title
                
                # Fallback to canvas_trickster_subrole_descriptions
                subrole_descriptions = trickster_desc.get("canvas_trickster_subrole_descriptions", {})
                if role_name in subrole_descriptions:
                    # Parse format like "🙏 **Transferencia Kármica** - description"
                    desc_text = subrole_descriptions[role_name]
                    # Extract text between ** **
                    if "**" in desc_text:
                        parts = desc_text.split("**")
                        if len(parts) >= 3:
                            title = parts[1].strip()
                            if title:
                                return title
                    # Fallback: take everything before "-" and clean up
                    title = desc_text.split("-")[0].replace("🙏", "").replace("🔮", "").replace("🎲", "").replace("👁️", "").strip()
                    if title:
                        return title
                        
    except Exception:
        pass  # Silently fall back to technical name if anything fails
    
    # Fallback to technical name
    return role_name


def _get_active_roles_section(server_id: str = None) -> str:
    # Use server-specific personality if server_id provided
    if server_id:
        try:
            personality = _get_personality(server_id)
        except Exception:
            personality = PERSONALITY
    else:
        personality = PERSONALITY
    
    roles = (AGENT_CFG or {}).get("roles", {})
    section_cfg = personality.get("active_roles_section", {})
    role_sections = personality.get("roles", {})

    if not isinstance(role_sections, dict):
        role_sections = {}
    if not isinstance(section_cfg, dict):
        section_cfg = {}

    section_label = str(section_cfg.get("label") or "[ACTIVE ROLES IN THE SERVER]").strip()
    empty_message = str(section_cfg.get("empty") or "- No active role duties are configured right now.").strip()
    line_template = str(section_cfg.get("line_template") or "- {scope}: {duty}").strip()

    lines: list[str] = []
    for role_name, role_cfg in roles.items():
        if not isinstance(role_cfg, dict) or not role_cfg.get("enabled", False):
            continue

        role_prompt_cfg = role_sections.get(role_name, {})
        role_duty = _get_active_duty_text(role_prompt_cfg)
        if role_duty:
            role_display = _get_role_display_name(role_name, server_id)
            lines.append(line_template.format(scope=role_display, duty=role_duty))

        subroles = role_cfg.get("subroles", {})
        role_subroles_cfg = role_prompt_cfg.get("subroles", {}) if isinstance(role_prompt_cfg, dict) else {}
        if not isinstance(subroles, dict):
            continue
        if not isinstance(role_subroles_cfg, dict):
            role_subroles_cfg = {}

        for subrole_name, subrole_cfg in subroles.items():
            if not isinstance(subrole_cfg, dict) or not subrole_cfg.get("enabled", False):
                continue
            subrole_prompt_cfg = role_subroles_cfg.get(subrole_name, {})
            
            subrole_duty = _get_active_duty_text(subrole_prompt_cfg, server_id, subrole_name)
            
            if subrole_duty:
                subrole_display = _get_role_display_name(subrole_name, server_id)
                lines.append(line_template.format(scope=f"{_get_role_display_name(role_name, server_id)}/{subrole_display}", duty=subrole_duty))

    if not lines:
        return f"{section_label}\n{empty_message}"
    return f"{section_label}\n" + "\n".join(lines)

def _load_active_tasks_system_additions() -> list[str]:
    global _roles_verified, _active_tasks_cache
    
    # If already verified, return cache
    if _roles_verified:
        return _active_tasks_cache

    is_role_process = os.getenv('ROLE_AGENT_PROCESS') == '1'
    
    roles = (AGENT_CFG or {}).get("roles", {})
    additions: list[str] = []
    
    if not is_role_process:
        logger.info("🎭 [ROLES] Verifying configured roles...")
    enabled_roles = []

    for role_name, role_cfg in roles.items():
        if not isinstance(role_cfg, dict):
            continue
        if not role_cfg.get("enabled", False):
            if not is_role_process:
                logger.info(f"   💤 [Role] '{role_name}' - disabled")
            continue

        enabled_roles.append(role_name)
        if not is_role_process:
            logger.info(f"   ✅ [Role] '{role_name}' - active (every {role_cfg.get('interval_hours', '?')}h)")

        # Skip subroles (beggar, ring) - they will be loaded from JSON
        if role_name in ["beggar", "ring"]:
            continue

        # Search for mission configuration directly in Python file
        script_path = role_cfg.get("script", "")
        if not script_path:
            # Skip roles without script (e.g., integrated roles like mc)
            if not is_role_process:
                logger.info(f"   📋 [ROL] '{role_name}' - integrated mode (no script)")
            continue
            
        role_script_path = os.path.join(_BASE_DIR, script_path)
        if not os.path.exists(role_script_path):
            if not is_role_process:
                logger.warning(f"   ⚠️ [Role] Script not found: {role_script_path}")
                logger.warning(f"   ⚠️ [ROL] Script not found: {role_script_path}")
            continue
        
        try:
            # Read file and extract MISSION_CONFIG with regex to avoid importing
            with open(role_script_path, encoding="utf-8") as f:
                content = f.read()
            
            # Search for MISSION_CONFIG in code
            import re
            mission_match = re.search(r'MISSION_CONFIG\s*=\s*{([^}]+)}', content, re.DOTALL)
            if mission_match:
                # Extract system_prompt_addition from dictionary (handle escaped quotes)
                addition_match = re.search(r'"system_prompt_addition"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', mission_match.group(1))
                if addition_match:
                    addition = addition_match.group(1).strip()
                    # Unescape quotes and backslashes
                    addition = addition.replace('\\"', '"').replace('\\\\', '\\')
                    if addition:
                        # Only inject beggar and ring subroles for gold/ring detection
                        # All other roles should not contaminate global conversations
                        if role_name in ["beggar", "ring"]:
                            additions.append(addition)
                            if not is_role_process:
                                logger.info(f"   📋 [ROL] '{role_name}' - mission loaded: {addition[:50]}...")
                        else:
                            if not is_role_process:
                                logger.info(f"   🔄 [ROL] '{role_name}' - contextual context (not global): {addition[:50]}...")
                        continue
            
            if not is_role_process:
                logger.warning(f"⚠️ No valid MISSION_CONFIG found in {role_name}")
        except Exception as e:
            if not is_role_process:
                logger.warning(f"⚠️ Could not load MISSION_CONFIG from {role_name}: {e}")
        
        # Process enabled subroles (except beggar and ring which are loaded from JSON)
        subroles = role_cfg.get("subroles", {})
        if isinstance(subroles, dict):
            for subrole_name, subrole_cfg in subroles.items():
                if not isinstance(subrole_cfg, dict):
                    continue
                if not subrole_cfg.get("enabled", False):
                    continue
                
                # Skip beggar and ring - loaded from JSON
                if subrole_name in ["beggar", "ring"]:
                    continue
                
                subrole_script_path = subrole_cfg.get("script", "")
                if not subrole_script_path:
                    continue
                
                full_subrole_path = os.path.join(_BASE_DIR, subrole_script_path)
                if not os.path.exists(full_subrole_path):
                    if not is_role_process:
                        logger.warning(f"   ⚠️ [Subrole] Script not found: {full_subrole_path}")
                    continue
                
                try:
                    with open(full_subrole_path, encoding="utf-8") as f:
                        subrole_content = f.read()
                    
                    import re
                    subrole_mission_match = re.search(r'MISSION_CONFIG\s*=\s*{([^}]+)}', subrole_content, re.DOTALL)
                    if subrole_mission_match:
                        addition_match = re.search(r'"system_prompt_addition"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', subrole_mission_match.group(1))
                        if addition_match:
                            addition = addition_match.group(1).strip()
                            addition = addition.replace('\\"', '"').replace('\\\\', '\\')
                            if addition:
                                if not is_role_process:
                                    logger.info(f"   🔄 [Subrole] '{subrole_name}' - contextual context (not global): {addition[:50]}...")
                except Exception as e:
                    if not is_role_process:
                        logger.warning(f"⚠️ Could not load MISSION_CONFIG from subrole {subrole_name}: {e}")

    # Load beggar and ring prompts from JSON
    json_additions = _load_subrole_prompts_from_json()
    additions.extend(json_additions)

    if not is_role_process:
        if enabled_roles:
            logger.info(f"🎭 [ROLES] Total active: {len(enabled_roles)} - {', '.join(enabled_roles)}")
        else:
            logger.info("🎭 [ROLES] No active roles configured")
    
    # Mark as verified and save cache
    _roles_verified = True
    _active_tasks_cache = additions
    
    return additions

def increment_usage():
    return runtime_increment_usage(PERSONALITY.get("name", "unknown"))


def _fallback_response():
    """Emergency response defined in personality."""
    fallbacks = PERSONALITY.get("emergency_fallbacks", [])
    if fallbacks:
        return random.choice(fallbacks)
    return PERSONALITY.get("emergency_fallback", "...")


def _get_readme_response_rules_lines() -> list[str]:
    template = _get_user_prompt_template()
    rules = template.get("readme_response_rules", [])
    if isinstance(rules, list) and rules:
        return [str(rule).strip() for rule in rules if str(rule).strip()]
    return [
        "1. OBJECTIVE: Answer the user's question using the provided documentation.",
        "2. COMMANDS: Do not reply only with README. Explain the relevant command directly.",
        "3. LENGTH: 3-7 short useful sentences.",
        "4. CONTENT: Explain purpose, usage, and a small example when helpful.",
        "5. STYLE: Stay in character and be clear."
    ]


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _get_user_prompt_template() -> dict:
    template = PERSONALITY.get("user_prompt_template", {})
    return template if isinstance(template, dict) else {}


def _get_response_rules_lines() -> list[str]:
    template = _get_user_prompt_template()
    rules = template.get("response_rules", [])
    if isinstance(rules, list) and rules:
        return [str(rule).strip() for rule in rules if str(rule).strip()]
    return [
        "1. LENGTH: 1-3 sentences (25-150 characters). Be brief and direct.",
        "2. COMMANDS: If human asks for help with commands or functions, respond ONLY with: README",
        "3. GRAMMAR: No accent marks.",
        "4. Don't end sentences with single words like 'the', 'a', in'.",
    ]


from agent_mind import (
    call_llm,
    generate_daily_memory_summary,
    generate_recent_memory_summary,
    generate_user_relationship_memory_summary,
    refresh_due_recent_memories,
    refresh_due_relationship_memories,
)


def _build_system_prompt(personalidad: dict, server_id: str = None) -> str:
    """Assemble system prompt from structured personality sections."""
    template = personalidad.get("system_prompt_template", {})
    if isinstance(template, dict) and template:
        sections = []
        identity_title = str(template.get("identity_title", "")).strip()
        identity_body = template.get("identity_body", [])
        style_title = str(template.get("style_title", "")).strip()
        style_body = template.get("style_body", [])
        examples_title = str(template.get("examples_title", "")).strip()
        examples_body = template.get("examples_body", [])

        if identity_title and isinstance(identity_body, list) and identity_body:
            identity_text = "\n".join([str(line).strip() for line in identity_body if str(line).strip()])
            sections.append(f"## {identity_title}\n{identity_text}")
        if style_title and isinstance(style_body, list) and style_body:
            style_text = "\n".join([str(line).strip() for line in style_body if str(line).strip()])
            sections.append(f"## {style_title}\n{style_text}")
        if examples_title and isinstance(examples_body, list) and examples_body:
            examples_text = "\n".join([str(line).strip() for line in examples_body if str(line).strip()])
            sections.append(f"## {examples_title}\n{examples_text}")
        active_roles_section = _get_active_roles_section(server_id)
        if active_roles_section:
            sections.append(active_roles_section)
        if sections:
            return "\n\n".join(sections)

# ============================================================================
# SUBROLE INTERNAL TASKS SYSTEM
# ============================================================================

import random
from datetime import datetime, timedelta

def get_active_subroles(server_id: str = None):
    """Get active subroles from personality prompts.json."""
    try:
        # Use server-specific personality if server_id provided
        if server_id:
            try:
                personality = _get_personality(server_id)
                subroles = personality.get("roles", {}).get("trickster", {}).get("subroles", {})
            except Exception:
                # Fall back to global personality
                personality = PERSONALITY
                subroles = personality.get("roles", {}).get("trickster", {}).get("subroles", {})
        else:
            # Use global personality
            subroles = PERSONALITY.get("roles", {}).get("trickster", {}).get("subroles", {})
        
        active_subroles = {}
        
        for subrole_name, subrole_config in subroles.items():
            if "internal_task" in subrole_config:
                active_subroles[subrole_name] = subrole_config
                
        return active_subroles
    except Exception as e:
        logger.error(f"Error loading subroles: {e}")
        return {}

def should_execute_subrole_task(subrole_name: str, frequency_hours: int, server_id: str = None) -> bool:
    """Check if subrole task should execute based on next_run_at persisted in roles_config."""
    try:
        from agent_roles_db import RolesDatabase
        if server_id is None:
            from agent_db import get_server_id
            server_id = get_server_id()
        db = RolesDatabase(server_id)
        next_run = db.get_subrole_next_run(subrole_name)
        now = datetime.now()
        if next_run is None or now >= next_run:
            return True
        return False
    except Exception as e:
        logger.warning(f"Could not check next_run_at for {subrole_name}, allowing execution: {e}")
        return True


def mark_subrole_executed(subrole_name: str, next_run: datetime, server_id: str = None) -> None:
    """Persist next_run_at for a subrole after execution."""
    try:
        from agent_roles_db import RolesDatabase
        if server_id is None:
            from agent_db import get_server_id
            server_id = get_server_id()
        db = RolesDatabase(server_id)
        db.set_subrole_next_run(subrole_name, next_run)
        logger.info(f"🎭 [SUBROLE] {subrole_name} next run scheduled for {next_run:%Y-%m-%d %H:%M:%S}")
    except Exception as e:
        logger.error(f"Failed to persist next_run_at for {subrole_name}: {e}")

async def execute_subrole_internal_task(subrole_name, subrole_config, bot_instance=None, server_id: str = None):
    """Execute internal task for a subrole."""
    try:
        logger.info(f"🎭 [SUBROLE] Executing internal task: {subrole_name} (server: {server_id})")
        
        # Get system prompt and base mission prompt (server-specific personality)
        if server_id is None:
            from agent_db import get_server_id
            server_id = get_server_id()
        server_personality = _get_personality(server_id) if server_id else PERSONALITY
        system_instruction = _build_system_prompt(server_personality, server_id)
        
        # Get subrole_config from server-specific personality to ensure correct language
        subroles = server_personality.get("roles", {}).get("trickster", {}).get("subroles", {})
        server_subrole_config = subroles.get(subrole_name, subrole_config)
        
        mission_prompt = _get_active_duty_text(server_subrole_config, server_id, subrole_name)
        
        # Build the complete prompt with task and reasons at the end
        base_task_prompt = server_subrole_config.get("internal_task", {}).get("prompt", "")
        
        # Add specific reasons/methods at the end
        task_details = ""
        if subrole_name == "beggar":
            from roles.trickster.subroles.beggar.beggar_task import execute_beggar_task
            try:
                success = await execute_beggar_task(server_id=server_id, bot_instance=bot_instance)
                if success:
                    logger.info(f"🎭 [BEGGAR] Task executed successfully")
                else:
                    logger.warning(f"🎭 [BEGGAR] Task execution failed")
            except Exception as e:
                logger.error(f"🎭 [BEGGAR] Error in task execution: {e}")

            # Frequency: roles_config DB first, fallback to agent_config.json
            frequency = None
            try:
                from agent_roles_db import RolesDatabase
                _srv = server_id
                _rdb = RolesDatabase(_srv)
                _cfg = _rdb.get_role_config('beggar')
                _cd = json.loads(_cfg.get('config_data') or '{}')
                frequency = _cd.get('frequency_hours')
                if frequency is None:
                    # Seed from agent_config.json so it's available next time
                    frequency = _get_subrole_frequency_from_config('beggar')
                    _cd['frequency_hours'] = frequency
                    _rdb.save_role_config('beggar', _cfg.get('enabled', True), json.dumps(_cd))
                    logger.info(f"🎭 [BEGGAR] Seeded frequency_hours={frequency} into roles_config")
            except Exception as e:
                logger.warning(f"🎭 [BEGGAR] Could not read frequency from roles_config: {e}")
                frequency = _get_subrole_frequency_from_config('beggar')
            mark_subrole_executed(subrole_name, datetime.now() + timedelta(hours=frequency), server_id=_srv)
            return
        elif subrole_name == "ring":
            from roles.trickster.subroles.ring.ring_discord import (
                _get_ring_state, execute_ring_accusation,
                _calculate_next_frequency, _auto_reset_ring_accusation
            )
            from roles.trickster.subroles.ring.ring_db import RingDB
            _RING_IGNORED_LIMIT = 5
            _RING_IGNORED_MIN_FREQ = 1
            try:
                from agent_db import AgentDatabase
                server_name = server_id
                if not server_name:
                    logger.warning(f"🎭 [RING] No active server found")
                    return

                ring_state = _get_ring_state(server_name, force_refresh=True)

                # Skip entirely if ring is not enabled
                if not ring_state.get('enabled', False):
                    logger.info(f"🎭 [RING] Ring is disabled, skipping")
                    return

                target_user_id = ring_state.get('target_user_id', '')
                target_user_name = ring_state.get('target_user_name', '')

                # No target configured — do nothing
                if not target_user_id:
                    logger.info(f"🎭 [RING] No target configured, skipping")
                    return

                # --- Ignored limit check ---
                # If we're at minimum frequency (1h) and target has been sent the
                # configured limit of unanswered DMs, auto-reset to a new target.
                unanswered = ring_state.get('unanswered_dm_count', 0)
                current_freq = ring_state.get('current_frequency_hours', 24)
                if current_freq <= _RING_IGNORED_MIN_FREQ and unanswered >= _RING_IGNORED_LIMIT:
                    logger.info(f"🔄 [RING] {target_user_name} ignored {unanswered} messages at {current_freq}h freq — auto-resetting")
                    db_agent = AgentDatabase(server_name)
                    import sqlite3
                    conn = sqlite3.connect(db_agent.db_path)
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT DISTINCT usuario_id, usuario_nombre
                        FROM interacciones
                        WHERE servidor_id IS NOT NULL
                        AND usuario_id != ?
                        AND fecha > datetime('now', '-48 hours')
                        ORDER BY fecha DESC
                        LIMIT 10
                    ''', (target_user_id,))
                    candidates = [(r[0], r[1]) for r in cursor.fetchall()]
                    conn.close()
                    new_target = _auto_reset_ring_accusation(server_name, candidates)
                    if new_target:
                        ring_state = _get_ring_state(server_name, force_refresh=True)
                        target_user_id = ring_state['target_user_id']
                        target_user_name = ring_state['target_user_name']
                        logger.info(f"🔄 [RING] New target after auto-reset: {target_user_name}")
                    else:
                        logger.warning(f"🎭 [RING] Auto-reset failed: no candidates, staying idle")
                        base_freq = ring_state.get('base_frequency_hours', 24)
                        mark_subrole_executed(subrole_name, datetime.now() + timedelta(hours=base_freq), server_id=server_name)
                        return

                # --- Build accusation and send ---
                db_agent = AgentDatabase(server_name)
                import sqlite3
                conn = sqlite3.connect(db_agent.db_path)
                cursor = conn.cursor()

                accuser_name = "a user"
                try:
                    ring_db = RingDB(server_name)
                    accusations = ring_db.get_accusations(limit=1)
                    if accusations:
                        accuser_id = accusations[0].get('accuser_id')
                        if accuser_id:
                            cursor.execute('''
                                SELECT usuario_nombre FROM interacciones
                                WHERE usuario_id = ? ORDER BY fecha DESC LIMIT 1
                            ''', (accuser_id,))
                            result = cursor.fetchone()
                            if result:
                                accuser_name = result[0]
                            elif isinstance(accuser_id, str) and not accuser_id.isdigit():
                                accuser_name = accuser_id
                except Exception as e:
                    logger.warning(f"Could not get original accuser: {e}")

                accusation = await execute_ring_accusation(None, target_user_id, target_user_name, user_name=accuser_name)
                logger.info(f"🎭 [RING] Accusation generated for {target_user_name}: {accusation[:100]}...")

                # Find most active channel in last 24h
                cursor.execute('''
                    SELECT canal_id, COUNT(*) as cnt
                    FROM interacciones
                    WHERE servidor_id IS NOT NULL
                    AND fecha > datetime('now', '-24 hours')
                    AND canal_id IS NOT NULL
                    GROUP BY canal_id ORDER BY cnt DESC LIMIT 1
                ''')
                channel_result = cursor.fetchone()
                conn.close()

                dm_sent = False
                try:
                    from discord_bot.agent_discord import get_bot_instance
                    bot = get_bot_instance()
                    if bot:
                        target_user = bot.get_user(int(target_user_id))
                        if target_user:
                            await target_user.send(f"👁️ **RING ACCUSATION**\n{accusation}")
                            logger.info(f"🎭 [RING] Accusation sent via DM to {target_user_name}")
                            dm_sent = True
                        else:
                            logger.warning(f"🎭 [RING] Could not find target user {target_user_id} in cache")
                    else:
                        logger.warning(f"🎭 [RING] Bot instance not available")
                except Exception as dm_error:
                    logger.error(f"🎭 [RING] Error sending DM: {dm_error}")

                if not dm_sent and channel_result:
                    try:
                        from discord_bot.agent_discord import get_bot_instance
                        bot = get_bot_instance()
                        if bot:
                            channel = bot.get_channel(int(channel_result[0]))
                            if channel:
                                await channel.send(f"⚠️ **RING INVESTIGATION** (DM failed)\n{accusation}")
                                logger.info(f"🎭 [RING] Accusation sent to channel as fallback")
                    except Exception as ch_err:
                        logger.error(f"🎭 [RING] Channel fallback failed: {ch_err}")

                # Increment unanswered counter and persist
                ring_state = _get_ring_state(server_name, force_refresh=True)
                ring_state['unanswered_dm_count'] = ring_state.get('unanswered_dm_count', 0) + 1
                from roles.trickster.subroles.ring.ring_discord import _save_ring_state
                _save_ring_state(server_name, "scheduler_accusation")

                # Schedule next run via hot-potato
                next_freq = _calculate_next_frequency(server_name)
                mark_subrole_executed(subrole_name, datetime.now() + timedelta(hours=next_freq), server_id=server_name)

            except Exception as e:
                logger.error(f"🎭 [RING] Error in ring execution: {e}")
            return
        
        # Construct complete prompt: mission + task + details
        complete_prompt = f"{mission_prompt}\n\n{base_task_prompt}{task_details}\n\nRespond only with what the bot would say, without additional explanations."
        
        # Call LLM (use server-specific personality)
        server_personality_for_call = _get_personality(server_id) if server_id else PERSONALITY
        response = call_llm(
            system_instruction=_build_system_prompt(server_personality_for_call, server_id),
            prompt=complete_prompt,
            async_mode=True,
            call_type="subrole_async",
            temperature=0.95,
            max_tokens=1024,
            critical=False,
            metadata={"subrole": subrole_name, "server_id": server_id}
        )
        
        if response and len(response) > 10:
            logger.info(f"🎭 [{subrole_name.upper()}] Task executed successfully")
        else:
            logger.warning(f"🎭 [{subrole_name.upper()}] Empty or short response: {response}")

        frequency = _get_subrole_frequency_from_config(subrole_name)
        mark_subrole_executed(subrole_name, datetime.now() + timedelta(hours=frequency), server_id=server_id)

    except Exception as e:
        logger.error(f"🎭 [SUBROLE] Error executing task {subrole_name}: {e}")
