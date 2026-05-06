"""Rate limiting for personality uploads to prevent abuse."""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple


# Cooldown period between uploads (30 minutes)
UPLOAD_COOLDOWN_SECONDS = 30 * 60

# Default paths
UPLOADS_DIR = "uploads"
UPLOAD_LOG_FILE = "upload_log.json"


def _get_server_uploads_dir(server_id: str, base_dir: Optional[str] = None) -> Path:
    """Get the uploads directory for a specific server.

    Args:
        server_id: Discord server ID
        base_dir: Optional base directory (defaults to project root/databases)

    Returns:
        Path to uploads directory
    """
    if base_dir:
        base = Path(base_dir)
    else:
        # Default: databases/<server_id>/uploads/
        base = Path(__file__).parent.parent.parent / "databases" / server_id / UPLOADS_DIR

    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_upload_log_path(server_id: str, base_dir: Optional[str] = None) -> Path:
    """Get the path to the upload log file.

    Args:
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        Path to upload_log.json
    """
    return _get_server_uploads_dir(server_id, base_dir) / UPLOAD_LOG_FILE


def _load_upload_log(server_id: str, base_dir: Optional[str] = None) -> Dict:
    """Load the upload log for a server.

    Args:
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        Dictionary with upload log data
    """
    log_path = _get_upload_log_path(server_id, base_dir)

    if not log_path.exists():
        return {
            "server_id": server_id,
            "uploads": [],
            "last_upload_timestamp": None,
            "last_upload_success": False
        }

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # Return fresh log if file is corrupted
        return {
            "server_id": server_id,
            "uploads": [],
            "last_upload_timestamp": None,
            "last_upload_success": False
        }


def _save_upload_log(server_id: str, log_data: Dict, base_dir: Optional[str] = None) -> bool:
    """Save the upload log for a server.

    Args:
        server_id: Discord server ID
        log_data: Dictionary with upload log data
        base_dir: Optional base directory

    Returns:
        bool: True if saved successfully
    """
    log_path = _get_upload_log_path(server_id, base_dir)

    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        return True
    except IOError as e:
        print(f"Error saving upload log for {server_id}: {e}")
        return False


def check_upload_cooldown(server_id: str, base_dir: Optional[str] = None) -> Tuple[bool, int]:
    """Check if enough time has passed since the last upload.

    Args:
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        Tuple of (can_upload, remaining_seconds)
        - can_upload: True if upload is allowed
        - remaining_seconds: Seconds until next upload allowed (0 if can_upload)
    """
    log_data = _load_upload_log(server_id, base_dir)
    last_timestamp = log_data.get("last_upload_timestamp")

    if last_timestamp is None:
        return True, 0

    # Calculate time elapsed
    last_upload_time = datetime.fromisoformat(last_timestamp)
    current_time = datetime.now()
    elapsed_seconds = (current_time - last_upload_time).total_seconds()

    if elapsed_seconds >= UPLOAD_COOLDOWN_SECONDS:
        return True, 0

    remaining_seconds = int(UPLOAD_COOLDOWN_SECONDS - elapsed_seconds)
    return False, remaining_seconds


def get_remaining_cooldown(server_id: str, base_dir: Optional[str] = None) -> int:
    """Get the remaining cooldown time in seconds.

    Args:
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        int: Seconds remaining until next upload allowed (0 if no cooldown)
    """
    _, remaining = check_upload_cooldown(server_id, base_dir)
    return remaining


def format_cooldown_time(remaining_seconds: int) -> str:
    """Format remaining cooldown time in a human-readable way.

    Args:
        remaining_seconds: Seconds remaining

    Returns:
        str: Formatted time string (e.g., "15 minutes 30 seconds")
    """
    if remaining_seconds <= 0:
        return "0 seconds"

    minutes = remaining_seconds // 60
    seconds = remaining_seconds % 60

    parts = []
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    return " ".join(parts) if parts else "0 seconds"


def record_upload_attempt(
    server_id: str,
    success: bool = True,
    file_hash: Optional[str] = None,
    base_dir: Optional[str] = None
) -> bool:
    """Record an upload attempt in the log.

    Args:
        server_id: Discord server ID
        success: Whether the upload was successful
        file_hash: Optional hash of the uploaded file
        base_dir: Optional base directory

    Returns:
        bool: True if recorded successfully
    """
    log_data = _load_upload_log(server_id, base_dir)

    current_time = datetime.now()

    # Update last upload info
    log_data["last_upload_timestamp"] = current_time.isoformat()
    log_data["last_upload_success"] = success

    # Add to uploads history
    upload_entry = {
        "timestamp": current_time.isoformat(),
        "success": success,
        "file_hash": file_hash
    }

    log_data["uploads"].append(upload_entry)

    # Keep only last 10 uploads to prevent log bloat
    log_data["uploads"] = log_data["uploads"][-10:]

    return _save_upload_log(server_id, log_data, base_dir)


def get_upload_history(server_id: str, base_dir: Optional[str] = None) -> list:
    """Get the upload history for a server.

    Args:
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        list: List of upload entries
    """
    log_data = _load_upload_log(server_id, base_dir)
    return log_data.get("uploads", [])


def is_rate_limited(server_id: str, base_dir: Optional[str] = None) -> bool:
    """Quick check if server is currently rate limited.

    Args:
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        bool: True if currently rate limited
    """
    can_upload, _ = check_upload_cooldown(server_id, base_dir)
    return not can_upload
