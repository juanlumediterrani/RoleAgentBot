import os
import sys
import sqlite3
import asyncio
from typing import Optional
from datetime import datetime, timedelta
import json
import requests

# Ensure project root imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent_logging import get_logger

logger = get_logger('wikipedia_fetcher')

# Cache database path
CACHE_DB_PATH = os.path.join(os.path.dirname(__file__), 'wikipedia_cache.db')

# Cache duration: 7 days
CACHE_DURATION_DAYS = 7

def init_cache_db():
    """Initialize SQLite cache database for Wikipedia extracts."""
    conn = sqlite3.connect(CACHE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wiki_cache (
            topic TEXT,
            lang TEXT,
            extract TEXT,
            fetched_at TIMESTAMP,
            PRIMARY KEY (topic, lang)
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_fetched_at ON wiki_cache(fetched_at)
    ''')
    conn.commit()
    conn.close()

def get_cached_extract(topic: str, lang: str) -> Optional[str]:
    """Get cached Wikipedia extract if available and not expired."""
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT extract, fetched_at FROM wiki_cache WHERE topic = ? AND lang = ?',
            (topic, lang)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            extract, fetched_at_str = result
            fetched_at = datetime.fromisoformat(fetched_at_str)
            if datetime.now() - fetched_at < timedelta(days=CACHE_DURATION_DAYS):
                logger.debug(f"Cache hit for {topic} ({lang})")
                return extract
            else:
                logger.debug(f"Cache expired for {topic} ({lang})")
                return None
    except Exception as e:
        logger.warning(f"Error reading cache: {e}")
    return None

def cache_extract(topic: str, lang: str, extract: str):
    """Cache Wikipedia extract."""
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO wiki_cache (topic, lang, extract, fetched_at) VALUES (?, ?, ?, ?)',
            (topic, lang, extract, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        logger.debug(f"Cached extract for {topic} ({lang})")
    except Exception as e:
        logger.warning(f"Error caching extract: {e}")

async def fetch_wikipedia_extract(topic: str, lang: str = 'en') -> Optional[tuple]:
    """Fetch Wikipedia extract using MediaWiki API.
    
    Args:
        topic: The topic to search for (spaces will be converted to underscores)
        lang: Language code (en, es, zh, etc.)
        
    Returns:
        Tuple of (extract_text, wikipedia_url) or None if not found/error
    """
    # Convert spaces to underscores for Wikipedia URL format
    topic_formatted = topic.replace(' ', '_')
    
    # Build Wikipedia URL
    wikipedia_url = f"https://{lang}.wikipedia.org/wiki/{topic_formatted}"
    
    # Check cache first
    cached = get_cached_extract(topic_formatted, lang)
    if cached:
        return (cached, wikipedia_url)
    
    # Wikipedia API endpoint
    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    
    params = {
        'action': 'query',
        'prop': 'extracts',
        'explaintext': 'true',
        'exintro': 'false',
        'format': 'json',
        'titles': topic_formatted,
        'redirects': 'true'  # Follow redirects automatically
    }
    
    try:
        # Use requests with proper headers to avoid 403
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': f'{lang},en;q=0.9',
        }
        response = await asyncio.to_thread(
            requests.get,
            api_url,
            params=params,
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            logger.warning(f"Wikipedia API returned status {response.status_code} for {topic} ({lang})")
            return None
        
        data = response.json()
        
        # Parse the response
        pages = data.get('query', {}).get('pages', {})
        
        # Find the page (not the -1 "missing" page)
        for page_id, page_data in pages.items():
            if page_id == '-1':
                # Page not found
                logger.debug(f"Wikipedia page not found: {topic} ({lang})")
                return None
            
            extract = page_data.get('extract', '')
            if extract:
                # Truncate to first ~2500 chars (approx intro + first section)
                truncated = truncate_extract(extract, max_chars=2500)
                # Cache the successful fetch
                cache_extract(topic_formatted, lang, truncated)
                logger.info(f"Fetched Wikipedia extract for {topic} ({lang})")
                return (truncated, wikipedia_url)
        
        logger.debug(f"No extract found for {topic} ({lang})")
        return None
        
    except Exception as e:
        logger.warning(f"Error fetching Wikipedia for {topic} ({lang}): {e}")
        return None

def truncate_extract(extract: str, max_chars: int = 2500) -> str:
    """Truncate extract to reasonable length, trying to break at sentence end.
    
    Args:
        extract: Full text extract
        max_chars: Maximum characters to keep
        
    Returns:
        Truncated text
    """
    if len(extract) <= max_chars:
        return extract
    
    # Try to break at sentence end (. ! ?)
    truncated = extract[:max_chars]
    # Find last sentence end
    for i in range(len(truncated) - 1, -1, -1):
        if truncated[i] in '.!?':
            return truncated[:i+1].strip()
    
    # If no sentence end found, break at last space
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return truncated[:last_space].strip()
    
    return truncated.strip()

def extract_until_second_h2(html: str) -> str:
    """Extract HTML content up to the second h2 header.
    
    Args:
        html: HTML from Wikipedia
        
    Returns:
        Cleaned text up to the second h2 header
    """
    import re
    
    # Find all h2 headers
    h2_pattern = r'<h2[^>]*>(.*?)</h2>'
    h2_matches = list(re.finditer(h2_pattern, html, re.IGNORECASE | re.DOTALL))
    
    if len(h2_matches) < 2:
        # If less than 2 h2s, return first 2000 chars
        content = html[:2000]
    else:
        # Cut at the start of the second h2
        end_pos = h2_matches[1].start()
        content = html[:end_pos]
    
    # Remove all HTML tags
    content = re.sub(r'<[^>]+>', '', content)
    
    # Decode HTML entities
    content = content.replace('&nbsp;', ' ')
    content = content.replace('&amp;', '&')
    content = content.replace('&lt;', '<')
    content = content.replace('&gt;', '>')
    content = content.replace('&quot;', '"')
    content = content.replace('&#39;', "'")
    
    # Remove references [1], [2], etc.
    content = re.sub(r'\[\d+\]', '', content)
    
    # Remove empty lines and extra whitespace
    content = re.sub(r'\n\s*\n', '\n\n', content)
    content = re.sub(r'^\s*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'[ \t]+', ' ', content)
    
    return content.strip()

def extract_until_second_header(wikitext: str) -> str:
    """Extract wikitext content up to the second level 2 header (==).
    
    Args:
        wikitext: Raw wikitext from Wikipedia
        
    Returns:
        Cleaned text up to the second == header
    """
    import re
    
    # Remove all template blocks {{...}} using a stack-based approach FIRST
    # This handles nested templates better
    result = []
    brace_count = 0
    in_template = False
    
    for i, char in enumerate(wikitext):
        if char == '{' and i + 1 < len(wikitext) and wikitext[i+1] == '{':
            brace_count += 2
            if not in_template:
                in_template = True
            i += 1  # Skip next char
        elif char == '}' and i + 1 < len(wikitext) and wikitext[i+1] == '}':
            brace_count -= 2
            if brace_count <= 0:
                in_template = False
                brace_count = 0
            i += 1  # Skip next char
        elif not in_template:
            result.append(char)
    
    wikitext = ''.join(result)
    
    # Find all level 2 headers (== Header Name ==)
    header_pattern = r'^==\s*([^=]+?)\s*==$'
    header_positions = []
    
    lines = wikitext.split('\n')
    for i, line in enumerate(lines):
        match = re.match(header_pattern, line.strip())
        if match:
            header_positions.append(i)
    
    # If no headers or only one, return first 2000 chars (intro)
    if len(header_positions) < 2:
        content = wikitext[:2000]
    else:
        # Cut at the second header
        end_pos = header_positions[1]
        content_lines = lines[:end_pos]
        content = '\n'.join(content_lines)
    
    # Cleanup remaining markup
    # Remove bold ('''text''') and italic (''text'')
    content = re.sub(r"'''([^']+)'''", r'\1', content)
    content = re.sub(r"''([^']+)''", r'\1', content)
    
    # Remove file/image links
    content = re.sub(r'\[\[(?:File|Image):[^\]]+\]\]', '', content)
    
    # Convert internal links [[text|alt]] to just text
    content = re.sub(r'\[\[([^|\]]+)\|([^\]]+)\]\]', r'\2', content)
    content = re.sub(r'\[\[([^\]]+)\]\]', r'\1', content)
    
    # Remove references <ref>...</ref>
    content = re.sub(r'<ref[^>]*>.*?</ref>', '', content, flags=re.DOTALL)
    
    # Remove HTML tags
    content = re.sub(r'<[^>]+>', '', content)
    
    # Remove bracketed metadata
    content = re.sub(r'\[[^\]]*\]', '', content)
    
    # Remove any lines that still have | key = value pattern (aggressive)
    content = re.sub(r'^\s*\|[^=]*=.*$', '', content, flags=re.MULTILINE)
    
    # Remove empty lines and extra whitespace
    content = re.sub(r'\n\s*\n', '\n\n', content)
    content = re.sub(r'^\s*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'[ \t]+', ' ', content)
    
    return content.strip()

def cleanup_old_cache():
    """Remove cache entries older than CACHE_DURATION_DAYS."""
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        cursor = conn.cursor()
        cutoff_date = (datetime.now() - timedelta(days=CACHE_DURATION_DAYS)).isoformat()
        cursor.execute('DELETE FROM wiki_cache WHERE fetched_at < ?', (cutoff_date,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old cache entries")
    except Exception as e:
        logger.warning(f"Error cleaning up cache: {e}")

# Initialize cache on import
try:
    init_cache_db()
except Exception as e:
    logger.error(f"Failed to initialize Wikipedia cache: {e}")
