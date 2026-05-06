"""Manager for custom personality uploads - extraction, backup, and activation."""

import asyncio
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agent_logging import get_logger

from .validator import (
    extract_and_validate,
    extract_to_custom_directory,
    get_missing_optional_files,
    validate_personality_zip,
    ValidationError,
    SecurityError,
)
from .rate_limiter import (
    check_upload_cooldown,
    format_cooldown_time,
    get_remaining_cooldown,
    record_upload_attempt,
)
from .content_analyzer import (
    analyze_personality_directory,
    analyze_personality_directory_async,
    format_analysis_result,
)


logger = get_logger('personality_upload')


# Backup retention limit
MAX_BACKUPS = 3


def get_server_database_dir(server_id: str) -> Path:
    """Get the database directory for a server.

    Args:
        server_id: Discord server ID

    Returns:
        Path to server database directory
    """
    base_dir = Path(__file__).parent.parent.parent
    return base_dir / "databases" / server_id


def get_custom_personality_dir(server_id: str) -> Path:
    """Get the custom personality directory for a server.

    Args:
        server_id: Discord server ID

    Returns:
        Path to custom personality directory
    """
    return get_server_database_dir(server_id) / "custom"


def get_custom_backup_dir(server_id: str) -> Path:
    """Get the backup directory for custom personalities.

    Args:
        server_id: Discord server ID

    Returns:
        Path to backup directory
    """
    return get_server_database_dir(server_id) / "custom_backup"


def backup_existing_custom(server_id: str) -> Optional[Path]:
    """Backup existing custom personality before overwriting.

    Args:
        server_id: Discord server ID

    Returns:
        Path to backup directory or None if no backup needed
    """
    custom_dir = get_custom_personality_dir(server_id)

    if not custom_dir.exists():
        return None

    # Check if there are any files to backup
    has_files = any(custom_dir.iterdir())
    if not has_files:
        return None

    # Create backup directory with timestamp
    backup_dir = get_custom_backup_dir(server_id)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_subdir = backup_dir / timestamp
    backup_subdir.mkdir(exist_ok=True)

    # Copy all files from custom to backup
    for item in custom_dir.iterdir():
        if item.is_dir():
            shutil.copytree(item, backup_subdir / item.name)
        else:
            shutil.copy2(item, backup_subdir / item.name)

    # Cleanup old backups
    _cleanup_old_backups(server_id)

    return backup_subdir


def _cleanup_old_backups(server_id: str) -> None:
    """Remove old backups keeping only MAX_BACKUPS most recent.

    Args:
        server_id: Discord server ID
    """
    backup_dir = get_custom_backup_dir(server_id)

    if not backup_dir.exists():
        return

    # Get all backup subdirectories sorted by modification time
    backups = sorted(
        [d for d in backup_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True
    )

    # Remove excess backups
    for old_backup in backups[MAX_BACKUPS:]:
        try:
            shutil.rmtree(old_backup)
        except OSError:
            pass


def get_fallback_warnings(custom_dir: str | Path) -> List[str]:
    """Get list of warnings about missing optional files.

    Args:
        custom_dir: Path to custom personality directory

    Returns:
        List of warning messages
    """
    missing = get_missing_optional_files(custom_dir)

    if not missing:
        return []

    warnings = []
    for filename in missing:
        if filename == "personality.json":
            warnings.append("- personality.json (usará personalidad por defecto)")
        elif filename == "prompts.json":
            warnings.append("- prompts.json (usará prompts globales)")
        elif filename == "answers.json":
            warnings.append("- answers.json (usará respuestas por defecto)")
        elif filename == "descriptions.json":
            warnings.append("- descriptions.json (usará descripciones por defecto)")
        else:
            warnings.append(f"- {filename}")

    return warnings


def remove_previous_personality_dir(server_id: str) -> Optional[str]:
    """Remove the previous personality directory from databases/<server_id>/.

    When uploading a custom personality, we want to remove the previous
    personality directory to avoid confusion and save space. Only removes
    directories that are not 'custom' or 'custom_backup'.

    Args:
        server_id: Discord server ID

    Returns:
        Optional[str]: Name of removed personality directory, or None if nothing removed
    """
    try:
        server_config_path = get_server_database_dir(server_id) / "server_config.json"

        if not server_config_path.exists():
            return None

        with open(server_config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Read the previous personality (stored before updating to custom)
        previous_personality = config.get("previous_personality")

        # Don't remove if no previous personality or it's custom/custom_backup
        if not previous_personality:
            return None

        if previous_personality in ("custom", "custom_backup"):
            return None

        previous_dir = get_server_database_dir(server_id) / previous_personality

        if previous_dir.exists() and previous_dir.is_dir():
            shutil.rmtree(previous_dir)
            logger.info(f"Removed previous personality directory: {previous_personality} for server {server_id}")
            return previous_personality

        return None

    except Exception as e:
        logger.warning(f"Failed to remove previous personality directory for server {server_id}: {e}")
        return None


def update_server_config_for_custom(server_id: str) -> bool:
    """Update server_config.json to set active personality to 'custom'.

    Args:
        server_id: Discord server ID

    Returns:
        bool: True if updated successfully
    """
    try:
        server_config_path = get_server_database_dir(server_id) / "server_config.json"

        # Load existing config
        config = {}
        if server_config_path.exists():
            with open(server_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

        # Store previous personality for reference
        previous_personality = config.get("active_personality", "unknown")
        config["previous_personality"] = previous_personality

        # Set new active personality
        config["active_personality"] = "custom"
        config["custom_uploaded_at"] = datetime.now().isoformat()

        # Save config
        with open(server_config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        return True

    except Exception as e:
        print(f"Error updating server config: {e}")
        return False


def process_upload(
    zip_path: str | Path,
    server_id: str,
    user_id: str,
) -> Dict:
    """Full synchronous upload processing pipeline.

    Args:
        zip_path: Path to uploaded ZIP file
        server_id: Discord server ID
        user_id: Discord user ID who uploaded

    Returns:
        Dict with result information
    """
    zip_path = Path(zip_path)

    result = {
        "success": False,
        "error": None,
        "warnings": [],
        "missing_files": [],
        "backup_path": None,
        "analysis_result": None,
        "cooldown_remaining": 0,
    }

    try:
        # 1. Check rate limiting
        can_upload, cooldown_remaining = check_upload_cooldown(server_id)
        if not can_upload:
            result["cooldown_remaining"] = cooldown_remaining
            result["error"] = f"Rate limited. Wait {format_cooldown_time(cooldown_remaining)}."
            return result

        # 2. Validate ZIP
        file_hash, missing_files, uncompressed_size = validate_personality_zip(zip_path)
        result["missing_files"] = missing_files

        # 3. Create temp directory for extraction
        temp_dir = tempfile.mkdtemp(prefix="personality_upload_")

        try:
            # 4. Extract to temp
            extract_and_validate(zip_path, temp_dir)

            # 5. Content analysis
            analysis = analyze_personality_directory(temp_dir, file_hash, server_id)
            result["analysis_result"] = analysis

            if not analysis.get("safe", True):
                # Content rejected
                result["error"] = format_analysis_result(analysis)
                record_upload_attempt(server_id, success=False, file_hash=file_hash)
                return result

            # 6. Backup existing custom personality
            backup_path = backup_existing_custom(server_id)
            result["backup_path"] = backup_path

            # 7. Extract to custom directory
            custom_dir = get_custom_personality_dir(server_id)
            extract_to_custom_directory(zip_path, custom_dir, server_id)

            # 8. Update server config
            if not update_server_config_for_custom(server_id):
                result["warnings"].append("Could not update server config (non-critical)")

            # 9. Remove previous personality directory (only keep "custom")
            removed_personality = remove_previous_personality_dir(server_id)
            if removed_personality:
                result["warnings"].append(f"Removed previous personality directory: {removed_personality}")

            # 10. Get fallback warnings
            warnings = get_fallback_warnings(custom_dir)
            result["warnings"] = warnings

            # 11. Record successful upload
            record_upload_attempt(server_id, success=True, file_hash=file_hash)

            result["success"] = True

        finally:
            # Cleanup temp directory
            try:
                shutil.rmtree(temp_dir)
            except OSError:
                pass

    except SecurityError as e:
        result["error"] = f"Security check failed: {e.message}"
        record_upload_attempt(server_id, success=False)
    except ValidationError as e:
        result["error"] = f"Validation failed: {e.message}"
        record_upload_attempt(server_id, success=False)
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
        record_upload_attempt(server_id, success=False)

    return result


async def process_upload_async(
    zip_path: str | Path,
    server_id: str,
    user_id: str,
) -> Dict:
    """Full async upload processing pipeline.

    All blocking I/O operations run in background threads to avoid freezing the bot.

    Args:
        zip_path: Path to uploaded ZIP file
        server_id: Discord server ID
        user_id: Discord user ID who uploaded

    Returns:
        Dict with result information
    """
    zip_path = Path(zip_path)

    result = {
        "success": False,
        "error": None,
        "warnings": [],
        "missing_files": [],
        "backup_path": None,
        "analysis_result": None,
        "cooldown_remaining": 0,
    }

    try:
        # 1. Check rate limiting (fast, non-blocking)
        can_upload, cooldown_remaining = check_upload_cooldown(server_id)
        if not can_upload:
            result["cooldown_remaining"] = cooldown_remaining
            result["error"] = f"Rate limited. Wait {format_cooldown_time(cooldown_remaining)}."
            return result

        # 2. Validate ZIP (run in thread to avoid blocking)
        file_hash, missing_files, uncompressed_size = await asyncio.to_thread(
            validate_personality_zip, zip_path
        )
        result["missing_files"] = missing_files

        # 3. Create temp directory for extraction (run in thread)
        temp_dir = await asyncio.to_thread(tempfile.mkdtemp, prefix="personality_upload_")

        try:
            # 4. Extract to temp (run in thread)
            await asyncio.to_thread(extract_and_validate, zip_path, temp_dir)

            # 5. Content analysis (async - already non-blocking)
            analysis = await analyze_personality_directory_async(temp_dir, file_hash, server_id)
            result["analysis_result"] = analysis

            if not analysis.get("safe", True):
                # Content rejected
                result["error"] = format_analysis_result(analysis)
                await asyncio.to_thread(record_upload_attempt, server_id, False, file_hash)
                return result

            # 6. Backup existing custom personality (run in thread)
            backup_path = await asyncio.to_thread(backup_existing_custom, server_id)
            result["backup_path"] = backup_path

            # 7. Extract to custom directory (run in thread)
            custom_dir = get_custom_personality_dir(server_id)
            await asyncio.to_thread(extract_to_custom_directory, zip_path, custom_dir, server_id)

            # 8. Update server config (run in thread)
            config_updated = await asyncio.to_thread(update_server_config_for_custom, server_id)
            if not config_updated:
                result["warnings"].append("Could not update server config (non-critical)")

            # 9. Remove previous personality directory (run in thread)
            removed_personality = await asyncio.to_thread(remove_previous_personality_dir, server_id)
            if removed_personality:
                result["warnings"].append(f"Removed previous personality directory: {removed_personality}")

            # 10. Get fallback warnings (run in thread)
            warnings = await asyncio.to_thread(get_fallback_warnings, custom_dir)
            result["warnings"] = warnings

            # 11. Record successful upload (run in thread)
            await asyncio.to_thread(record_upload_attempt, server_id, True, file_hash)

            result["success"] = True

        finally:
            # Cleanup temp directory (run in thread)
            async def cleanup_temp():
                try:
                    await asyncio.to_thread(shutil.rmtree, temp_dir)
                except OSError:
                    pass
            # Run cleanup as background task (don't wait for it)
            asyncio.create_task(cleanup_temp())

    except SecurityError as e:
        result["error"] = f"Security check failed: {e.message}"
        await asyncio.to_thread(record_upload_attempt, server_id, False)
    except ValidationError as e:
        result["error"] = f"Validation failed: {e.message}"
        await asyncio.to_thread(record_upload_attempt, server_id, False)
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
        await asyncio.to_thread(record_upload_attempt, server_id, False)

    return result


def get_personality_descriptions(server_id: str) -> Dict:
    """Load personality descriptions from active personality's descriptions.json.

    Args:
        server_id: Discord server ID

    Returns:
        Dict with personality descriptions (empty if not found)
    """
    try:
        # Get server config to find active personality
        server_config_path = get_server_database_dir(server_id) / "server_config.json"
        if not server_config_path.exists():
            return {}

        with open(server_config_path, 'r', encoding='utf-8') as f:
            server_config = json.load(f)

        active_personality = server_config.get("active_personality")
        if not active_personality:
            return {}

        # Try to load descriptions from server-specific personality directory
        personality_dir = get_server_database_dir(server_id) / active_personality
        descriptions_path = personality_dir / "descriptions.json"

        # Fallback to global personalities directory
        if not descriptions_path.exists():
            base_dir = Path(__file__).parent.parent.parent
            language = server_config.get("language", "en-US")
            personality_dir = base_dir / "personalities" / active_personality / language
            descriptions_path = personality_dir / "descriptions.json"

            # Fallback without language subdirectory
            if not descriptions_path.exists():
                personality_dir = base_dir / "personalities" / active_personality
                descriptions_path = personality_dir / "descriptions.json"

        if not descriptions_path.exists():
            return {}

        with open(descriptions_path, 'r', encoding='utf-8') as f:
            descriptions = json.load(f)

        return descriptions.get("discord", {}).get("behavior_messages", {}).get("personality", {})

    except Exception:
        return {}


def format_upload_result(result: Dict, server_id: str = None) -> str:
    """Format upload result for display to user.

    Args:
        result: Upload result dictionary
        server_id: Discord server ID (optional, for personality descriptions)

    Returns:
        str: Formatted message
    """
    # Load personality descriptions for localized messages
    personality_msgs = get_personality_descriptions(server_id) if server_id else {}

    # Fallback to English messages
    upload_success = personality_msgs.get("upload_success", "✅ Custom personality loaded and activated as 'custom'.")
    missing_files_title = personality_msgs.get("missing_files_title", "\n⚠️ Missing files using fallback:")
    backup_saved = personality_msgs.get("backup_saved", "📦 Backup saved: {backup_path}")
    analysis_cached = personality_msgs.get("analysis_cached", "\n📋 Analysis: Using cached result")
    cooldown_message = personality_msgs.get("cooldown_message", "\n⏱️ Next upload available in: 30 minutes")
    error_title = personality_msgs.get("error_title", "❌ Error loading personality:")

    if result["success"]:
        lines = [upload_success]

        if result["missing_files"]:
            lines.append(missing_files_title)
            for warning in result["warnings"]:
                lines.append(f"   {warning}")

        if result["backup_path"]:
            lines.append(f"\n{backup_saved.format(backup_path=result['backup_path'].name)}")

        if result["analysis_result"] and result["analysis_result"].get("cached"):
            lines.append(analysis_cached)

        lines.append(cooldown_message)

        return "\n".join(lines)

    else:
        # Error case
        if result["cooldown_remaining"] > 0:
            return f"⏱️ {result['error']}"

        lines = [f"{error_title} {result['error']}"]

        if result["analysis_result"] and not result["analysis_result"].get("safe", True):
            lines.append("\n" + format_analysis_result(result["analysis_result"]))

        return "\n".join(lines)
