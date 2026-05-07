"""Pathnotes scraper for video game patch notes.

Scrapes patch notes from popular gaming platforms like Steam, Blizzard, Epic Games, etc.
"""

import asyncio
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from curl_cffi import requests
from bs4 import BeautifulSoup
from agent_logging import get_logger

logger = get_logger('pathnotes_scraper')


class PathnotesScraper:
    """Scraper for video game patch notes from various platforms."""

    # Platform configurations
    PLATFORMS = {
        'steam': {
            'name': 'Steam News Hub',
            'base_url': 'https://store.steampowered.com/news/{app_id}',
            'list_url': 'https://store.steampowered.com/news/{app_id}?emclan=103582791433666113&emclan103582791433666113=103582791433666113',
        },
        'blizzard': {
            'name': 'Blizzard Patch Notes',
            'base_url': 'https://news.blizzard.com/{game}',
        },
        'pathofexile': {
            'name': 'Path of Exile Patch Notes',
            'base_url': 'https://www.pathofexile.com/forum/view-forum/patch-notes',
        },
        'poe2': {
            'name': 'Path of Exile 2 Patch Notes',
            'base_url': 'https://www.pathofexile.com/path-of-exile-two',
        },
        'diablo4': {
            'name': 'Diablo 4 Patch Notes',
            'base_url': 'https://news.blizzard.com/en-us/diablo4',
        },
        'wow': {
            'name': 'World of Warcraft Patch Notes',
            'base_url': 'https://news.blizzard.com/en-us/world-of-warcraft',
        },
        'overwatch': {
            'name': 'Overwatch Patch Notes',
            'base_url': 'https://overwatch.blizzard.com/en-us/news/patch-notes/',
        },
        'valorant': {
            'name': 'Valorant Patch Notes',
            'base_url': 'https://playvalorant.com/en-us/news/tags/patch-notes/',
        },
        'fortnite': {
            'name': 'Fortnite Patch Notes',
            'base_url': 'https://www.fortnite.com/news?category=patch-notes',
        },
        'apex': {
            'name': 'Apex Legends Patch Notes',
            'base_url': 'https://www.ea.com/games/apex-legends/news',
        },
        'genshin': {
            'name': 'Genshin Impact Patch Notes',
            'base_url': 'https://genshin.hoyoverse.com/en/news?tag=1',
        },
        'lostark': {
            'name': 'Lost Ark Patch Notes',
            'base_url': 'https://www.playlostark.com/en-us/news?tag=patch-notes',
        },
    }

    def __init__(self):
        self.session = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def _get_session(self):
        """Get or create curl_cffi session."""
        if self.session is None:
            self.session = requests.AsyncSession(
                impersonate="chrome",
                headers=self.headers,
            )
        return self.session

    async def scrape_all(self, max_per_platform: int = 10) -> List[Dict]:
        """Scrape patch notes from all supported platforms.

        Args:
            max_per_platform: Maximum patches to fetch per platform

        Returns:
            List of patch note dicts with keys: title, game_name, patch_version,
            content, source_url, published_date, platform
        """
        all_patches = []

        tasks = [
            self._scrape_blizzard(max_per_platform),
            self._scrape_pathofexile(max_per_platform),
            self._scrape_poe2(max_per_platform),
            self._scrape_diablo4(max_per_platform),
            self._scrape_wow(max_per_platform),
            self._scrape_valorant(max_per_platform),
            self._scrape_fortnite(max_per_platform),
            self._scrape_apex(max_per_platform),
            self._scrape_genshin(max_per_platform),
            self._scrape_lostark(max_per_platform),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_patches.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Error scraping platform: {result}")

        # Sort by published_date descending
        all_patches.sort(key=lambda x: x.get('published_date', ''), reverse=True)

        logger.info(f"Scraped {len(all_patches)} total patch notes from all platforms")
        return all_patches

    async def _fetch_html(self, url: str) -> Optional[str]:
        """Fetch HTML from URL."""
        try:
            session = self._get_session()
            response = await session.get(url, timeout=30)
            if response.status_code == 200:
                return response.text
            logger.warning(f"HTTP {response.status_code} for {url}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return None

    def _extract_text_from_html(self, html: str) -> str:
        """Extract clean text from HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text(separator='\n', strip=True)
        # Clean up whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)

    def _normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize various date formats to ISO format."""
        if not date_str:
            return None

        date_formats = [
            '%B %d, %Y',
            '%d %B %Y',
            '%Y-%m-%d',
            '%Y-%m-%dT%H:%M:%S',
            '%m/%d/%Y',
            '%d/%m/%Y',
        ]

        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.isoformat()
            except ValueError:
                continue

        # Try to extract date from text
        date_patterns = [
            r'(\d{1,2})[\-/](\d{1,2})[\-/](\d{4})',  # MM/DD/YYYY or DD/MM/YYYY
            r'(\d{4})-(\d{2})-(\d{2})',  # YYYY-MM-DD
        ]

        for pattern in date_patterns:
            match = re.search(pattern, date_str)
            if match:
                try:
                    # Try YYYY-MM-DD first
                    if len(match.groups()) == 3 and len(match.group(1)) == 4:
                        year, month, day = match.groups()
                        dt = datetime(int(year), int(month), int(day))
                        return dt.isoformat()
                except:
                    pass

        return None

    async def _scrape_blizzard(self, max_items: int = 10) -> List[Dict]:
        """Scrape patch notes from Blizzard news (covers WoW, Diablo, etc.)."""
        patches = []
        base_url = "https://news.blizzard.com/en-us"

        # Blizzard games to check
        games = [
            ('world-of-warcraft', 'World of Warcraft'),
            ('diablo4', 'Diablo IV'),
            ('diablo-immortal', 'Diablo Immortal'),
            ('hearthstone', 'Hearthstone'),
        ]

        for game_slug, game_name in games:
            try:
                url = f"{base_url}/{game_slug}"
                html = await self._fetch_html(url)
                if not html:
                    continue

                soup = BeautifulSoup(html, 'html.parser')
                articles = soup.find_all('article', limit=max_items)

                for article in articles:
                    try:
                        title_elem = article.find('h2') or article.find('h3')
                        if not title_elem:
                            continue

                        title = title_elem.get_text(strip=True)

                        # Only include if it looks like a patch note
                        if not any(keyword in title.lower() for keyword in ['patch', 'update', 'hotfix', 'maintenance']):
                            continue

                        link_elem = article.find('a', href=True)
                        if link_elem:
                            href = link_elem['href']
                            source_url = href if href.startswith('http') else f"https://news.blizzard.com{href}"
                        else:
                            source_url = url

                        date_elem = article.find('time')
                        published_date = self._normalize_date(date_elem.get_text(strip=True) if date_elem else '')

                        # Get summary/content
                        summary_elem = article.find('p')
                        summary = summary_elem.get_text(strip=True) if summary_elem else ''

                        # Build full content
                        content = f"{title}\n\n{summary}"

                        patches.append({
                            'title': title,
                            'game_name': game_name,
                            'patch_version': self._extract_version(title),
                            'content': content,
                            'summary': summary[:500] if summary else title,
                            'source_url': source_url,
                            'published_date': published_date or datetime.now().isoformat(),
                            'platform': 'blizzard',
                        })
                    except Exception as e:
                        logger.debug(f"Error parsing Blizzard article: {e}")
                        continue

                await asyncio.sleep(0.5)  # Rate limiting

            except Exception as e:
                logger.warning(f"Error scraping Blizzard {game_name}: {e}")

        logger.info(f"Scraped {len(patches)} patches from Blizzard")
        return patches

    async def _scrape_pathofexile(self, max_items: int = 10) -> List[Dict]:
        """Scrape Path of Exile 1 patch notes from forum."""
        patches = []
        url = "https://www.pathofexile.com/forum/view-forum/patch-notes"

        try:
            html = await self._fetch_html(url)
            if not html:
                return patches

            soup = BeautifulSoup(html, 'html.parser')
            threads = soup.find_all('td', class_='thread', limit=max_items)

            for thread in threads:
                try:
                    title_elem = thread.find('a', class_='title')
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    href = title_elem.get('href', '')
                    source_url = f"https://www.pathofexile.com{href}" if href.startswith('/') else href

                    # Extract date
                    date_elem = thread.find('td', class_='post_date')
                    date_str = date_elem.get_text(strip=True) if date_elem else ''
                    published_date = self._normalize_date(date_str)

                    # Get preview content
                    preview_elem = thread.find('div', class_='content-preview')
                    preview = preview_elem.get_text(strip=True) if preview_elem else ''

                    patches.append({
                        'title': title,
                        'game_name': 'Path of Exile',
                        'patch_version': self._extract_version(title),
                        'content': preview,
                        'summary': preview[:500] if preview else title,
                        'source_url': source_url,
                        'published_date': published_date or datetime.now().isoformat(),
                        'platform': 'pathofexile',
                    })
                except Exception as e:
                    logger.debug(f"Error parsing POE thread: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error scraping Path of Exile: {e}")

        logger.info(f"Scraped {len(patches)} patches from Path of Exile")
        return patches

    async def _scrape_poe2(self, max_items: int = 10) -> List[Dict]:
        """Scrape Path of Exile 2 specific patch notes."""
        patches = []
        url = "https://www.pathofexile.com/path-of-exile-two"

        try:
            html = await self._fetch_html(url)
            if not html:
                return patches

            soup = BeautifulSoup(html, 'html.parser')
            # Look for news/patch note articles
            articles = soup.find_all('article', limit=max_items)
            if not articles:
                # Fallback to div containers
                articles = soup.find_all('div', class_=re.compile('news|patch|update', re.I), limit=max_items)

            for article in articles:
                try:
                    title_elem = article.find(['h2', 'h3', 'h1'])
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)

                    # Filter for patch-related content
                    if not any(keyword in title.lower() for keyword in ['patch', 'update', 'hotfix', 'change']):
                        continue

                    link_elem = article.find('a', href=True)
                    href = link_elem['href'] if link_elem else ''
                    source_url = f"https://www.pathofexile.com{href}" if href.startswith('/') else href

                    content_elem = article.find('p') or article.find('div', class_=re.compile('content|summary'))
                    content = content_elem.get_text(strip=True) if content_elem else title

                    patches.append({
                        'title': title,
                        'game_name': 'Path of Exile 2',
                        'patch_version': self._extract_version(title),
                        'content': content,
                        'summary': content[:500] if content else title,
                        'source_url': source_url or url,
                        'published_date': datetime.now().isoformat(),
                        'platform': 'poe2',
                    })
                except Exception as e:
                    logger.debug(f"Error parsing POE2 article: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error scraping POE2: {e}")

        logger.info(f"Scraped {len(patches)} patches from Path of Exile 2")
        return patches

    async def _scrape_diablo4(self, max_items: int = 10) -> List[Dict]:
        """Scrape Diablo 4 specific patch notes."""
        # This is handled by _scrape_blizzard for efficiency
        # But can be extended for specific Diablo 4 sources
        return []

    async def _scrape_wow(self, max_items: int = 10) -> List[Dict]:
        """Scrape WoW specific patch notes."""
        # This is handled by _scrape_blizzard for efficiency
        return []

    async def _scrape_valorant(self, max_items: int = 10) -> List[Dict]:
        """Scrape Valorant patch notes."""
        patches = []
        url = "https://playvalorant.com/en-us/news/tags/patch-notes/"

        try:
            html = await self._fetch_html(url)
            if not html:
                return patches

            soup = BeautifulSoup(html, 'html.parser')
            articles = soup.find_all('article', limit=max_items)

            for article in articles:
                try:
                    title_elem = article.find(['h2', 'h3', 'h4'])
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)

                    link_elem = article.find('a', href=True)
                    href = link_elem['href'] if link_elem else ''
                    source_url = href if href.startswith('http') else f"https://playvalorant.com{href}"

                    content_elem = article.find('p') or article.find('div', class_='content')
                    content = content_elem.get_text(strip=True) if content_elem else title

                    # Try to find date
                    date_elem = article.find('time') or article.find(string=re.compile(r'\d{1,2}/\d{1,2}/\d{4}'))
                    date_str = date_elem.get_text(strip=True) if date_elem else ''
                    published_date = self._normalize_date(date_str)

                    patches.append({
                        'title': title,
                        'game_name': 'Valorant',
                        'patch_version': self._extract_version(title),
                        'content': content,
                        'summary': content[:500] if content else title,
                        'source_url': source_url,
                        'published_date': published_date or datetime.now().isoformat(),
                        'platform': 'valorant',
                    })
                except Exception as e:
                    logger.debug(f"Error parsing Valorant article: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error scraping Valorant: {e}")

        logger.info(f"Scraped {len(patches)} patches from Valorant")
        return patches

    async def _scrape_fortnite(self, max_items: int = 10) -> List[Dict]:
        """Scrape Fortnite patch notes."""
        patches = []
        url = "https://www.fortnite.com/news?category=patch-notes"

        try:
            html = await self._fetch_html(url)
            if not html:
                return patches

            soup = BeautifulSoup(html, 'html.parser')
            # Look for news cards/items
            items = soup.find_all('div', class_=re.compile('card|item|post', re.I), limit=max_items)

            for item in items:
                try:
                    title_elem = item.find(['h2', 'h3', 'h4', 'span'])
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)

                    # Filter for patch notes
                    if 'patch' not in title.lower():
                        continue

                    link_elem = item.find('a', href=True)
                    href = link_elem['href'] if link_elem else ''
                    source_url = href if href.startswith('http') else f"https://www.fortnite.com{href}"

                    patches.append({
                        'title': title,
                        'game_name': 'Fortnite',
                        'patch_version': self._extract_version(title),
                        'content': title,
                        'summary': title,
                        'source_url': source_url,
                        'published_date': datetime.now().isoformat(),
                        'platform': 'fortnite',
                    })
                except Exception as e:
                    logger.debug(f"Error parsing Fortnite item: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error scraping Fortnite: {e}")

        logger.info(f"Scraped {len(patches)} patches from Fortnite")
        return patches

    async def _scrape_apex(self, max_items: int = 10) -> List[Dict]:
        """Scrape Apex Legends patch notes."""
        patches = []
        url = "https://www.ea.com/games/apex-legends/news"

        try:
            html = await self._fetch_html(url)
            if not html:
                return patches

            soup = BeautifulSoup(html, 'html.parser')
            articles = soup.find_all('article', limit=max_items)

            for article in articles:
                try:
                    title_elem = article.find(['h2', 'h3'])
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)

                    # Filter for patch/update notes
                    if not any(keyword in title.lower() for keyword in ['patch', 'update', 'notes']):
                        continue

                    link_elem = article.find('a', href=True)
                    href = link_elem['href'] if link_elem else ''
                    source_url = href if href.startswith('http') else f"https://www.ea.com{href}"

                    content_elem = article.find('p')
                    content = content_elem.get_text(strip=True) if content_elem else title

                    patches.append({
                        'title': title,
                        'game_name': 'Apex Legends',
                        'patch_version': self._extract_version(title),
                        'content': content,
                        'summary': content[:500] if content else title,
                        'source_url': source_url,
                        'published_date': datetime.now().isoformat(),
                        'platform': 'apex',
                    })
                except Exception as e:
                    logger.debug(f"Error parsing Apex article: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error scraping Apex: {e}")

        logger.info(f"Scraped {len(patches)} patches from Apex Legends")
        return patches

    async def _scrape_genshin(self, max_items: int = 10) -> List[Dict]:
        """Scrape Genshin Impact patch notes."""
        patches = []
        url = "https://genshin.hoyoverse.com/en/news?tag=1"

        try:
            html = await self._fetch_html(url)
            if not html:
                # Fallback to genshin-impact.fandom.com
                url = "https://genshin-impact.fandom.com/wiki/Version/Change_History"
                html = await self._fetch_html(url)

            if not html:
                return patches

            soup = BeautifulSoup(html, 'html.parser')

            if 'fandom.com' in url:
                # Fandom wiki format
                items = soup.find_all('div', class_='mw-parser-output', limit=max_items)
                for item in items:
                    try:
                        # Look for version headers
                        headers = item.find_all(['h2', 'h3'])
                        for header in headers[:max_items]:
                            title = header.get_text(strip=True)
                            if 'version' in title.lower():
                                patches.append({
                                    'title': title,
                                    'game_name': 'Genshin Impact',
                                    'patch_version': self._extract_version(title),
                                    'content': title,
                                    'summary': title,
                                    'source_url': url,
                                    'published_date': datetime.now().isoformat(),
                                    'platform': 'genshin',
                                })
                    except Exception as e:
                        logger.debug(f"Error parsing Genshin wiki: {e}")
            else:
                # Hoyoverse format
                articles = soup.find_all('article', limit=max_items)
                for article in articles:
                    try:
                        title_elem = article.find(['h2', 'h3'])
                        if not title_elem:
                            continue

                        title = title_elem.get_text(strip=True)

                        link_elem = article.find('a', href=True)
                        href = link_elem['href'] if link_elem else ''
                        source_url = href if href.startswith('http') else f"https://genshin.hoyoverse.com{href}"

                        patches.append({
                            'title': title,
                            'game_name': 'Genshin Impact',
                            'patch_version': self._extract_version(title),
                            'content': title,
                            'summary': title,
                            'source_url': source_url,
                            'published_date': datetime.now().isoformat(),
                            'platform': 'genshin',
                        })
                    except Exception as e:
                        logger.debug(f"Error parsing Genshin article: {e}")

        except Exception as e:
            logger.warning(f"Error scraping Genshin: {e}")

        logger.info(f"Scraped {len(patches)} patches from Genshin Impact")
        return patches

    async def _scrape_lostark(self, max_items: int = 10) -> List[Dict]:
        """Scrape Lost Ark patch notes."""
        patches = []
        url = "https://www.playlostark.com/en-us/news?tag=patch-notes"

        try:
            html = await self._fetch_html(url)
            if not html:
                return patches

            soup = BeautifulSoup(html, 'html.parser')
            articles = soup.find_all('article', limit=max_items)

            for article in articles:
                try:
                    title_elem = article.find(['h2', 'h3'])
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)

                    link_elem = article.find('a', href=True)
                    href = link_elem['href'] if link_elem else ''
                    source_url = href if href.startswith('http') else f"https://www.playlostark.com{href}"

                    content_elem = article.find('p')
                    content = content_elem.get_text(strip=True) if content_elem else title

                    patches.append({
                        'title': title,
                        'game_name': 'Lost Ark',
                        'patch_version': self._extract_version(title),
                        'content': content,
                        'summary': content[:500] if content else title,
                        'source_url': source_url,
                        'published_date': datetime.now().isoformat(),
                        'platform': 'lostark',
                    })
                except Exception as e:
                    logger.debug(f"Error parsing Lost Ark article: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error scraping Lost Ark: {e}")

        logger.info(f"Scraped {len(patches)} patches from Lost Ark")
        return patches

    def _extract_version(self, title: str) -> str:
        """Extract version number from title."""
        patterns = [
            r'(?:patch|update|version)\s*[:\-\s]*([\d.]+[\d.a-z]*)',
            r'([\d.]+[\d.a-z]*)\s*(?:patch|update|hotfix)',
            r'v([\d.]+[\d.a-z]*)',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1)

        return 'unknown'


# Convenience function for direct use
async def scrape_pathnotes(max_per_platform: int = 10) -> List[Dict]:
    """Convenience function to scrape all pathnotes.

    Args:
        max_per_platform: Maximum patches to fetch per platform

    Returns:
        List of patch note dicts
    """
    scraper = PathnotesScraper()
    return await scraper.scrape_all(max_per_platform)
