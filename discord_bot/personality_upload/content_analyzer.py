"""Content analysis using LLM for detecting inappropriate content in personality uploads."""

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Cache TTL for analysis results (30 minutes)
ANALYSIS_CACHE_TTL_MINUTES = 30

# Cache directory name
CACHE_DIR = "cache"

# Maximum content length to analyze (to prevent token overflow)
MAX_CONTENT_LENGTH = 10000

# System prompt for content analysis
CONTENT_ANALYSIS_SYSTEM_PROMPT = """You are a content safety analyzer. Your task is to review text content from a Discord bot personality configuration and determine if it contains inappropriate content.

Analyze the text for the following categories of inappropriate content:
1. Sexual content or explicit sexual themes
2. Graphic violence or gore
3. Hate speech, discrimination, or promotion of hatred against protected groups
4. Content that sexualizes, endangers, or is otherwise inappropriate regarding minors

Respond ONLY with a JSON object in this exact format:
{
  "safe": true/false,
  "reasons": ["brief reason 1", "brief reason 2"],
  "severity": "low/medium/high",
  "categories": ["sexual/violence/hate_speech/minors"]
}

Rules:
- "safe": true if the content is appropriate, false if any concerning content is found
- "reasons": List of specific concerns found (empty if safe)
- "severity": Overall severity rating (low/medium/high)
- "categories": Which categories were detected (empty if safe)
- Be objective and conservative in your assessment
- Fictional violence in fantasy contexts is generally acceptable unless graphic/gory
- Personality traits like being rude, grumpy, or aggressive are acceptable unless promoting real-world harm"""

# System prompt for security analysis
SECURITY_ANALYSIS_SYSTEM_PROMPT = """You are a security analyzer specializing in detecting code injection and malicious content in JSON configuration files.

Analyze the text for the following security threats:
1. Code injection attempts (Python code, JavaScript, eval/exec patterns, import statements)
2. SQL injection patterns or database manipulation attempts
3. Command injection patterns (shell commands, system calls)
4. Path traversal attempts (../, ..\\, absolute paths trying to escape directories)
5. XML/JSON external entity references or malicious payloads
6. Overflow attempts (excessive data, buffer overflow patterns)
7. Obfuscated or encoded malicious content (base64, hex encoding of suspicious patterns)
8. Attempts to access sensitive files or environment variables
9. Network request patterns that could exfiltrate data
10. Template injection patterns (Jinja2, Django templates, etc.)

Respond ONLY with a JSON object in this exact format:
{
  "safe": true/false,
  "reasons": ["brief reason 1", "brief reason 2"],
  "severity": "low/medium/high/critical",
  "categories": ["code_injection/sql_injection/command_injection/path_traversal/malicious_payload/obfuscation/data_exfiltration"],
  "suspicious_patterns": ["pattern1", "pattern2"]
}

Rules:
- "safe": true if no threats detected, false if any suspicious patterns found
- "reasons": List of specific security concerns found (empty if safe)
- "severity": critical for active exploits, high for likely threats, medium for suspicious patterns, low for minor concerns
- "categories": Which security categories were detected (empty if safe)
- "suspicious_patterns": The actual suspicious text/snippets found (truncated to 50 chars max)
- Be conservative - flag anything that looks like code, commands, or encoded content in personality files
- Normal personality text should NOT contain code blocks, imports, eval statements, system calls, etc."""


def _get_cache_dir(server_id: str, base_dir: Optional[str] = None) -> Path:
    """Get the cache directory for analysis results.

    Args:
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        Path to cache directory
    """
    if base_dir:
        base = Path(base_dir)
    else:
        base = Path(__file__).parent.parent.parent / "databases" / server_id / "uploads" / CACHE_DIR

    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_cache_path(file_hash: str, server_id: str, base_dir: Optional[str] = None) -> Path:
    """Get the cache file path for a specific hash.

    Args:
        file_hash: SHA256 hash of the file
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        Path to cache file
    """
    return _get_cache_dir(server_id, base_dir) / f"{file_hash}.json"


def get_cached_analysis(file_hash: str, server_id: str, base_dir: Optional[str] = None) -> Optional[Dict]:
    """Get cached analysis result if it exists and is not expired.

    Args:
        file_hash: SHA256 hash of the file
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        Dict with cached analysis result or None if not found/expired
    """
    cache_path = _get_cache_path(file_hash, server_id, base_dir)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cached = json.load(f)

        # Check if cache is expired
        cached_time = datetime.fromisoformat(cached.get("timestamp", "2000-01-01T00:00:00"))
        expiration_time = cached_time + timedelta(minutes=ANALYSIS_CACHE_TTL_MINUTES)

        if datetime.now() > expiration_time:
            # Cache expired, delete it
            try:
                cache_path.unlink()
            except OSError:
                pass
            return None

        return cached.get("result")

    except (json.JSONDecodeError, KeyError, OSError):
        # Invalid cache file, delete it
        try:
            cache_path.unlink()
        except OSError:
            pass
        return None


def cache_analysis(file_hash: str, result: Dict, server_id: str, base_dir: Optional[str] = None) -> bool:
    """Cache analysis result for future use.

    Args:
        file_hash: SHA256 hash of the file
        result: Analysis result dictionary
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        bool: True if cached successfully
    """
    cache_path = _get_cache_path(file_hash, server_id, base_dir)

    cache_data = {
        "timestamp": datetime.now().isoformat(),
        "file_hash": file_hash,
        "result": result
    }

    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        print(f"Error caching analysis result: {e}")
        return False


def extract_text_from_personality(directory: str | Path) -> str:
    """Extract text content from all JSON files in a personality directory.

    Args:
        directory: Path to personality directory

    Returns:
        str: Concatenated text content from all JSON files
    """
    directory = Path(directory)
    text_parts = []

    json_files = [
        "personality.json",
        "prompts.json",
        "answers.json",
        "descriptions.json"
    ]

    for filename in json_files:
        file_path = directory / filename
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Convert JSON to text string
                text_content = json.dumps(data, ensure_ascii=False)
                text_parts.append(f"=== {filename} ===\n{text_content}\n")
            except (json.JSONDecodeError, IOError):
                # Skip files that can't be read
                continue

    # Also check descriptions directory
    descriptions_dir = directory / "descriptions"
    if descriptions_dir.exists() and descriptions_dir.is_dir():
        for json_file in descriptions_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                text_content = json.dumps(data, ensure_ascii=False)
                text_parts.append(f"=== descriptions/{json_file.name} ===\n{text_content}\n")
            except (json.JSONDecodeError, IOError):
                continue

    full_text = "\n".join(text_parts)

    # Truncate if too long
    if len(full_text) > MAX_CONTENT_LENGTH:
        full_text = full_text[:MAX_CONTENT_LENGTH] + "\n[Content truncated for analysis]"

    return full_text


def analyze_content_with_llm(text_content: str) -> Dict:
    """Analyze text content using LLM for inappropriate material.

    Args:
        text_content: Text to analyze

    Returns:
        Dict with analysis results
    """
    try:
        # Import here to avoid circular dependencies
        from agent_mind import call_llm

        prompt = f"Analyze the following personality content:\n\n{text_content}\n\nProvide your analysis as JSON only."

        response = call_llm(
            system_instruction=CONTENT_ANALYSIS_SYSTEM_PROMPT,
            prompt=prompt,
            background=True,  # Use background timeout (longer)
            call_type="content_analysis",
            temperature=0.1,  # Low temperature for consistent analysis
            max_tokens=500,
            critical=False,  # Non-critical, can fail gracefully
        )

        # Parse JSON response
        try:
            # Clean up response to extract JSON
            response = response.strip()
            # Remove markdown code blocks if present
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            result = json.loads(response)

            # Validate required fields
            if "safe" not in result:
                result["safe"] = True  # Default to safe if unclear
            if "reasons" not in result:
                result["reasons"] = []
            if "severity" not in result:
                result["severity"] = "low"
            if "categories" not in result:
                result["categories"] = []

            return result

        except json.JSONDecodeError:
            # If LLM didn't return valid JSON, assume safe but log issue
            return {
                "safe": True,
                "reasons": ["Analysis parsing error - assuming safe"],
                "severity": "low",
                "categories": [],
                "parsing_error": True
            }

    except Exception as e:
        # If LLM call fails, we need to decide what to do
        # For safety, we could fail closed (reject) or open (accept)
        # Given the use case, failing open with a warning is more user-friendly
        return {
            "safe": True,
            "reasons": [f"Analysis failed: {str(e)} - assuming safe"],
            "severity": "low",
            "categories": [],
            "analysis_error": str(e)
        }


async def analyze_content_async(text_content: str) -> Dict:
    """Async version of content analysis.

    Args:
        text_content: Text to analyze

    Returns:
        Dict with analysis results
    """
    try:
        # Import here to avoid circular dependencies
        from agent_mind import call_llm_async

        prompt = f"Analyze the following personality content:\n\n{text_content}\n\nProvide your analysis as JSON only."

        response = await call_llm_async(
            system_instruction=CONTENT_ANALYSIS_SYSTEM_PROMPT,
            prompt=prompt,
            background=True,
            call_type="content_analysis",
            temperature=0.1,
            max_tokens=500,
            critical=False,
        )

        # Parse JSON response
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            result = json.loads(response)

            # Validate required fields
            if "safe" not in result:
                result["safe"] = True
            if "reasons" not in result:
                result["reasons"] = []
            if "severity" not in result:
                result["severity"] = "low"
            if "categories" not in result:
                result["categories"] = []

            return result

        except json.JSONDecodeError:
            return {
                "safe": True,
                "reasons": ["Analysis parsing error - assuming safe"],
                "severity": "low",
                "categories": [],
                "parsing_error": True
            }

    except Exception as e:
        return {
            "safe": True,
            "reasons": [f"Analysis failed: {str(e)} - assuming safe"],
            "severity": "low",
            "categories": [],
            "analysis_error": str(e)
        }


def analyze_security_with_llm(text_content: str) -> Dict:
    """Analyze text content for security threats using LLM.

    Args:
        text_content: Text to analyze

    Returns:
        Dict with security analysis results
    """
    try:
        # Import here to avoid circular dependencies
        from agent_mind import call_llm

        prompt = f"Analyze the following content for security threats, code injection, and malicious patterns:\n\n{text_content}\n\nProvide your security analysis as JSON only."

        response = call_llm(
            system_instruction=SECURITY_ANALYSIS_SYSTEM_PROMPT,
            prompt=prompt,
            background=True,
            call_type="security_analysis",
            temperature=0.1,
            max_tokens=800,
            critical=False,
        )

        # Parse JSON response
        try:
            # Clean up response to extract JSON
            response = response.strip()
            # Remove markdown code blocks if present
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            result = json.loads(response)

            # Validate required fields
            if "safe" not in result:
                result["safe"] = True
            if "reasons" not in result:
                result["reasons"] = []
            if "severity" not in result:
                result["severity"] = "low"
            if "categories" not in result:
                result["categories"] = []
            if "suspicious_patterns" not in result:
                result["suspicious_patterns"] = []

            return result

        except json.JSONDecodeError:
            # If LLM didn't return valid JSON, assume safe but log issue
            return {
                "safe": True,
                "reasons": ["Security analysis parsing error - assuming safe"],
                "severity": "low",
                "categories": [],
                "suspicious_patterns": [],
                "parsing_error": True
            }

    except Exception as e:
        return {
            "safe": True,
            "reasons": [f"Security analysis failed: {str(e)} - assuming safe"],
            "severity": "low",
            "categories": [],
            "suspicious_patterns": [],
            "analysis_error": str(e)
        }


async def analyze_security_async(text_content: str) -> Dict:
    """Async version of security analysis.

    Args:
        text_content: Text to analyze

    Returns:
        Dict with security analysis results
    """
    try:
        # Import here to avoid circular dependencies
        from agent_mind import call_llm_async

        prompt = f"Analyze the following content for security threats, code injection, and malicious patterns:\n\n{text_content}\n\nProvide your security analysis as JSON only."

        response = await call_llm_async(
            system_instruction=SECURITY_ANALYSIS_SYSTEM_PROMPT,
            prompt=prompt,
            background=True,
            call_type="security_analysis",
            temperature=0.1,
            max_tokens=800,
            critical=False,
        )

        # Parse JSON response
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            result = json.loads(response)

            # Validate required fields
            if "safe" not in result:
                result["safe"] = True
            if "reasons" not in result:
                result["reasons"] = []
            if "severity" not in result:
                result["severity"] = "low"
            if "categories" not in result:
                result["categories"] = []
            if "suspicious_patterns" not in result:
                result["suspicious_patterns"] = []

            return result

        except json.JSONDecodeError:
            return {
                "safe": True,
                "reasons": ["Security analysis parsing error - assuming safe"],
                "severity": "low",
                "categories": [],
                "suspicious_patterns": [],
                "parsing_error": True
            }

    except Exception as e:
        return {
            "safe": True,
            "reasons": [f"Security analysis failed: {str(e)} - assuming safe"],
            "severity": "low",
            "categories": [],
            "suspicious_patterns": [],
            "analysis_error": str(e)
        }


def _combine_analysis_results(content_result: Dict, security_result: Dict) -> Dict:
    """Combine content and security analysis results.

    Args:
        content_result: Content analysis result
        security_result: Security analysis result

    Returns:
        Dict with combined results
    """
    # Determine overall safety
    is_safe = content_result.get("safe", True) and security_result.get("safe", True)

    # Combine reasons
    all_reasons = []
    if not content_result.get("safe", True):
        all_reasons.extend(content_result.get("reasons", []))
    if not security_result.get("safe", True):
        all_reasons.extend(security_result.get("reasons", []))

    # Determine highest severity
    severities = ["low", "medium", "high", "critical"]
    content_sev = content_result.get("severity", "low")
    security_sev = security_result.get("severity", "low")
    highest_sev = content_sev if severities.index(content_sev) >= severities.index(security_sev) else security_sev

    # Combine categories
    all_categories = []
    all_categories.extend(content_result.get("categories", []))
    all_categories.extend(security_result.get("categories", []))

    return {
        "safe": is_safe,
        "reasons": all_reasons,
        "severity": highest_sev,
        "categories": list(set(all_categories)),  # Remove duplicates
        "content_analysis": content_result,
        "security_analysis": security_result,
        "security_threats_found": not security_result.get("safe", True),
    }


def analyze_personality_directory(
    directory: str | Path,
    file_hash: str,
    server_id: str,
    base_dir: Optional[str] = None
) -> Dict:
    """Full analysis pipeline for a personality directory.

    Performs both content safety analysis and security threat detection.

    Args:
        directory: Path to extracted personality directory
        file_hash: Hash of the original ZIP file
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        Dict with combined analysis results
    """
    # Check cache first
    cached = get_cached_analysis(file_hash, server_id, base_dir)
    if cached is not None:
        return {**cached, "cached": True}

    # Extract text content
    text_content = extract_text_from_personality(directory)

    if not text_content.strip():
        # No content to analyze
        result = {
            "safe": True,
            "reasons": ["No text content found to analyze"],
            "severity": "low",
            "categories": [],
            "security_threats_found": False,
        }
        cache_analysis(file_hash, result, server_id, base_dir)
        return result

    # Perform both analyses
    content_result = analyze_content_with_llm(text_content)
    security_result = analyze_security_with_llm(text_content)

    # Combine results
    combined_result = _combine_analysis_results(content_result, security_result)

    # Cache the result
    cache_analysis(file_hash, combined_result, server_id, base_dir)

    return {**combined_result, "cached": False}


async def analyze_personality_directory_async(
    directory: str | Path,
    file_hash: str,
    server_id: str,
    base_dir: Optional[str] = None
) -> Dict:
    """Async full analysis pipeline for a personality directory.

    Performs both content safety analysis and security threat detection.

    Args:
        directory: Path to extracted personality directory
        file_hash: Hash of the original ZIP file
        server_id: Discord server ID
        base_dir: Optional base directory

    Returns:
        Dict with combined analysis results
    """
    # Check cache first
    cached = get_cached_analysis(file_hash, server_id, base_dir)
    if cached is not None:
        return {**cached, "cached": True}

    # Extract text content
    text_content = extract_text_from_personality(directory)

    if not text_content.strip():
        result = {
            "safe": True,
            "reasons": ["No text content found to analyze"],
            "severity": "low",
            "categories": [],
            "security_threats_found": False,
        }
        cache_analysis(file_hash, result, server_id, base_dir)
        return result

    # Perform both analyses concurrently
    content_task = analyze_content_async(text_content)
    security_task = analyze_security_async(text_content)
    content_result, security_result = await asyncio.gather(content_task, security_task)

    # Combine results
    combined_result = _combine_analysis_results(content_result, security_result)

    # Cache the result
    cache_analysis(file_hash, combined_result, server_id, base_dir)

    return {**combined_result, "cached": False}


def format_analysis_result(result: Dict) -> str:
    """Format analysis result for display to user.

    Args:
        result: Analysis result dictionary

    Returns:
        str: Formatted message
    """
    if result.get("safe", True):
        return "✅ Content analysis passed - no inappropriate or malicious content detected"

    reasons = result.get("reasons", [])
    severity = result.get("severity", "unknown")
    categories = result.get("categories", [])
    security_threats = result.get("security_threats_found", False)

    lines = ["❌ Content analysis detected issues:"]

    if security_threats:
        lines.append("   🚨 **SECURITY THREATS DETECTED** 🚨")

    if categories:
        lines.append(f"   Categories: {', '.join(categories)}")

    lines.append(f"   Severity: {severity.upper()}")

    if reasons:
        lines.append("   Reasons:")
        for reason in reasons:
            lines.append(f"      - {reason}")

    # Add suspicious patterns if available from security analysis
    security_analysis = result.get("security_analysis", {})
    if security_analysis and not security_analysis.get("safe", True):
        suspicious = security_analysis.get("suspicious_patterns", [])
        if suspicious:
            lines.append("   Suspicious patterns found:")
            for pattern in suspicious[:5]:  # Show max 5 patterns
                display_pattern = pattern[:50] + "..." if len(pattern) > 50 else pattern
                lines.append(f"      - {display_pattern}")

    return "\n".join(lines)
