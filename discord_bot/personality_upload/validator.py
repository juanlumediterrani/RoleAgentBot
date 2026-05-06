"""ZIP validation and security checks for personality uploads."""

import hashlib
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import List, Set, Tuple


# Maximum ZIP file size (10 MB)
MAX_ZIP_SIZE_BYTES = 10 * 1024 * 1024

# Maximum uncompressed size (50 MB - prevents ZIP bombs)
MAX_UNCOMPRESSED_SIZE_BYTES = 50 * 1024 * 1024

# Maximum compression ratio (10:1)
MAX_COMPRESSION_RATIO = 10

# Allowed file extensions
ALLOWED_EXTENSIONS: Set[str] = {
    '.json', '.png', '.jpg', '.jpeg', '.webp', '.md', '.txt'
}

# Required personality files (none are strictly required - fallbacks available)
OPTIONAL_PERSONALITY_FILES = [
    'personality.json',
    'prompts.json',
    'answers.json',
    'descriptions.json'
]


class ValidationError(Exception):
    """Exception for validation errors with user-friendly message."""

    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code
        super().__init__(message)


class SecurityError(ValidationError):
    """Exception for security-related validation errors."""
    pass


def get_zip_hash(zip_path: str | Path) -> str:
    """Calculate SHA256 hash of ZIP file for caching.

    Args:
        zip_path: Path to ZIP file

    Returns:
        str: SHA256 hex digest
    """
    sha256_hash = hashlib.sha256()
    with open(zip_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def check_file_size(file_path: str | Path, max_bytes: int = MAX_ZIP_SIZE_BYTES) -> None:
    """Check if file size is within limits.

    Args:
        file_path: Path to file
        max_bytes: Maximum allowed size in bytes

    Raises:
        ValidationError: If file exceeds size limit
    """
    file_size = os.path.getsize(file_path)
    if file_size > max_bytes:
        size_mb = file_size / (1024 * 1024)
        max_mb = max_bytes / (1024 * 1024)
        raise ValidationError(
            f"File too large: {size_mb:.1f}MB (max: {max_mb:.0f}MB)",
            code="FILE_TOO_LARGE"
        )


def validate_zip_structure(zip_path: str | Path) -> None:
    """Validate that file is a valid ZIP archive.

    Args:
        zip_path: Path to ZIP file

    Raises:
        ValidationError: If ZIP is invalid or corrupted
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Check for corruption
            bad_file = zf.testzip()
            if bad_file:
                raise ValidationError(
                    f"Corrupted ZIP file: '{bad_file}' is invalid",
                    code="CORRUPTED_ZIP"
                )
    except zipfile.BadZipFile:
        raise ValidationError(
            "Invalid ZIP file format",
            code="INVALID_ZIP_FORMAT"
        )
    except Exception as e:
        raise ValidationError(
            f"Error reading ZIP file: {str(e)}",
            code="ZIP_READ_ERROR"
        )


def check_compression_ratio(zip_path: str | Path) -> Tuple[int, int]:
    """Check ZIP compression ratio to detect ZIP bombs.

    Args:
        zip_path: Path to ZIP file

    Returns:
        Tuple of (compressed_size, uncompressed_size)

    Raises:
        SecurityError: If compression ratio is suspicious
    """
    compressed_size = os.path.getsize(zip_path)
    uncompressed_size = 0

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            uncompressed_size += info.file_size

    # Check total uncompressed size
    if uncompressed_size > MAX_UNCOMPRESSED_SIZE_BYTES:
        raise SecurityError(
            f"ZIP contents too large when extracted: {uncompressed_size / (1024*1024):.1f}MB",
            code="ZIP_BOMB_SIZE"
        )

    # Check compression ratio
    if compressed_size > 0:
        ratio = uncompressed_size / compressed_size
        if ratio > MAX_COMPRESSION_RATIO and uncompressed_size > 1024 * 1024:
            raise SecurityError(
                f"Suspicious compression ratio: {ratio:.1f}:1 (max: {MAX_COMPRESSION_RATIO}:1). Possible ZIP bomb.",
                code="ZIP_BOMB_RATIO"
            )

    return compressed_size, uncompressed_size


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks.

    Args:
        filename: Original filename from ZIP

    Returns:
        str: Sanitized filename (basename only)

    Raises:
        SecurityError: If filename is suspicious
    """
    # Normalize path separators
    filename = filename.replace('\\', '/')

    # Remove any path components (take only basename)
    basename = os.path.basename(filename)

    # Check for path traversal attempts
    if '..' in filename or filename.startswith('/') or filename.startswith('~'):
        raise SecurityError(
            f"Path traversal attempt detected: '{filename}'",
            code="PATH_TRAVERSAL"
        )

    # Check for null bytes or control characters
    if any(ord(c) < 32 for c in basename):
        raise SecurityError(
            f"Invalid characters in filename: '{filename}'",
            code="INVALID_FILENAME"
        )

    return basename


def sanitize_path(filename: str) -> str:
    """Sanitize path while preserving subdirectory structure.

    Unlike sanitize_filename which returns only basename,
    this function preserves relative subdirectories but removes
    dangerous path components like '..' and absolute paths.

    Args:
        filename: Original filename/path from ZIP

    Returns:
        str: Sanitized relative path

    Raises:
        SecurityError: If path is suspicious
    """
    # Normalize path separators
    filename = filename.replace('\\', '/')

    # Check for absolute paths
    if filename.startswith('/') or filename.startswith('~'):
        raise SecurityError(
            f"Absolute path not allowed: '{filename}'",
            code="ABSOLUTE_PATH"
        )

    # Split into components and sanitize each
    components = filename.split('/')
    safe_components = []

    for component in components:
        # Skip empty components (from leading/trailing slashes or double slashes)
        if not component:
            continue

        # Check for path traversal
        if component == '..' or component.startswith('..'):
            raise SecurityError(
                f"Path traversal attempt detected: '{filename}'",
                code="PATH_TRAVERSAL"
            )

        # Check for null bytes or control characters
        if any(ord(c) < 32 for c in component):
            raise SecurityError(
                f"Invalid characters in path: '{filename}'",
                code="INVALID_FILENAME"
            )

        # Check for Windows reserved names (CON, PRN, AUX, etc.)
        reserved = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                    'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2',
                    'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}
        base_without_ext = os.path.splitext(component.upper())[0]
        if base_without_ext in reserved:
            raise SecurityError(
                f"Reserved Windows filename: '{component}'",
                code="RESERVED_FILENAME"
            )

        safe_components.append(component)

    return '/'.join(safe_components)


def check_file_extension(filename: str) -> bool:
    """Check if file extension is allowed.

    Args:
        filename: Name of file

    Returns:
        bool: True if allowed, False otherwise
    """
    ext = os.path.splitext(filename.lower())[1]
    return ext in ALLOWED_EXTENSIONS


def extract_and_validate(
    zip_path: str | Path,
    extract_to: str | Path,
    skip_invalid: bool = True,
    preserve_structure: bool = False
) -> List[str]:
    """Extract ZIP contents with security validation.

    Args:
        zip_path: Path to ZIP file
        extract_to: Directory to extract to
        skip_invalid: If True, skip files with invalid extensions instead of failing
        preserve_structure: If True, preserve subdirectory structure from ZIP (for custom personalities)

    Returns:
        List of extracted file paths

    Raises:
        SecurityError: If security validation fails
        ValidationError: If extraction fails
    """
    extracted_files = []
    extract_to = Path(extract_to)

    # Ensure extract directory exists
    extract_to.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            # Skip directories
            if info.is_dir():
                continue

            # Sanitize filename (preserve structure if requested)
            try:
                if preserve_structure:
                    safe_name = sanitize_path(info.filename)
                else:
                    safe_name = sanitize_filename(info.filename)
            except SecurityError:
                if skip_invalid:
                    continue
                raise

            # Check extension
            if not check_file_extension(Path(safe_name).name):
                if skip_invalid:
                    continue
                raise SecurityError(
                    f"File type not allowed: '{safe_name}'",
                    code="INVALID_FILE_TYPE"
                )

            # Build safe extraction path
            target_path = extract_to / safe_name

            # Ensure target is within extract_to directory (extra safety)
            try:
                target_path.relative_to(extract_to.resolve())
            except ValueError:
                raise SecurityError(
                    f"Path escapes extraction directory: '{info.filename}'",
                    code="PATH_ESCAPE"
                )

            # Create parent directories if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Extract file
            try:
                with zf.open(info) as src, open(target_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                extracted_files.append(str(target_path))
            except Exception as e:
                raise ValidationError(
                    f"Failed to extract '{safe_name}': {str(e)}",
                    code="EXTRACTION_ERROR"
                )

    return extracted_files


def get_missing_optional_files(extract_dir: str | Path) -> List[str]:
    """Check which optional personality files are missing.

    Args:
        extract_dir: Directory where files were extracted

    Returns:
        List of missing file names
    """
    extract_dir = Path(extract_dir)
    missing = []

    for filename in OPTIONAL_PERSONALITY_FILES:
        if not (extract_dir / filename).exists():
            missing.append(filename)

    return missing


def validate_personality_zip(zip_path: str | Path) -> Tuple[str, List[str], int]:
    """Full validation pipeline for personality ZIP upload.

    Args:
        zip_path: Path to uploaded ZIP file

    Returns:
        Tuple of (file_hash, missing_files, uncompressed_size)

    Raises:
        ValidationError: If validation fails
        SecurityError: If security check fails
    """
    # 1. Check file size
    check_file_size(zip_path, MAX_ZIP_SIZE_BYTES)

    # 2. Validate ZIP structure
    validate_zip_structure(zip_path)

    # 3. Check compression ratio (ZIP bomb detection)
    _, uncompressed_size = check_compression_ratio(zip_path)

    # 4. Calculate hash for caching
    file_hash = get_zip_hash(zip_path)

    # Create temporary extraction directory for validation
    import tempfile

    temp_dir = tempfile.mkdtemp(prefix="personality_validate_")
    try:
        # 5. Extract and validate files
        extract_and_validate(zip_path, temp_dir)

        # 6. Check for missing optional files
        missing_files = get_missing_optional_files(temp_dir)

        return file_hash, missing_files, uncompressed_size
    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def extract_to_custom_directory(
    zip_path: str | Path,
    custom_dir: str | Path,
    server_id: str
) -> List[str]:
    """Extract ZIP to the custom personality directory.

    Preserves subdirectory structure from ZIP (e.g., descriptions/ subdirectory).
    Avatar files are moved to the root directory as avatar.png.

    Args:
        zip_path: Path to ZIP file
        custom_dir: Target directory for extraction
        server_id: Server ID for logging

    Returns:
        List of extracted file paths
    """
    custom_dir = Path(custom_dir)

    # Clear existing custom directory if it exists
    if custom_dir.exists():
        for item in custom_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    # Extract files with structure preservation (for subdirectories like descriptions/)
    extracted = extract_and_validate(zip_path, custom_dir, preserve_structure=True)

    # Handle avatar extraction - look for avatar files anywhere in extracted files
    avatar_extensions = ['.png', '.jpg', '.jpeg', '.webp']
    avatar_source = None

    for extracted_file in extracted:
        file_path = Path(extracted_file)
        if file_path.name.lower().startswith('avatar'):
            ext = file_path.suffix.lower()
            if ext in avatar_extensions:
                avatar_source = file_path
                break

    # If avatar found, move it to root as avatar.png
    if avatar_source:
        avatar_target = custom_dir / 'avatar.png'
        try:
            # If source is not PNG, convert it
            if avatar_source.suffix.lower() != '.png':
                try:
                    from PIL import Image
                    img = Image.open(avatar_source)
                    img.save(avatar_target, 'PNG')
                    # Remove original file
                    avatar_source.unlink()
                    extracted.remove(str(avatar_source))
                    extracted.append(str(avatar_target))
                except ImportError:
                    # PIL not available, just copy the file
                    shutil.copy2(avatar_source, avatar_target)
                    # Remove original file
                    avatar_source.unlink()
                    extracted.remove(str(avatar_source))
                    extracted.append(str(avatar_target))
                except Exception:
                    # Conversion failed, just copy the file
                    shutil.copy2(avatar_source, avatar_target)
                    # Remove original file
                    avatar_source.unlink()
                    extracted.remove(str(avatar_source))
                    extracted.append(str(avatar_target))
            else:
                # Already PNG, just move it to root
                shutil.move(str(avatar_source), str(avatar_target))
                extracted.remove(str(avatar_source))
                extracted.append(str(avatar_target))
        except Exception as e:
            # If avatar extraction fails, log but don't fail the whole upload
            logging.warning(f"Failed to extract avatar for server {server_id}: {e}")

    return extracted
