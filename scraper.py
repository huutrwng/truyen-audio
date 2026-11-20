"""
Scraper cho metruyenchu.com.vn
Hỗ trợ lấy danh sách chương qua AJAX pagination API (xử lý cả chuong- và chuong-chuong-)
"""
import asyncio
import aiohttp
import re
import json
import logging
from bs4 import BeautifulSoup
from typing import Optional
import time

logger = logging.getLogger(__name__)

NOVEL_SLUG = "tu-tien-khai-cuc-tu-duoc-dong-bat-dau"
BASE_URL = "https://metruyenchu.com.vn"
NOVEL_URL = f"{BASE_URL}/{NOVEL_SLUG}"
BOOK_ID = 62237

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://metruyenchu.com.vn/",
    "X-Requested-With": "XMLHttpRequest"
}

_session: Optional[aiohttp.ClientSession] = None

async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(ssl=False)
        _session = aiohttp.ClientSession(headers=HEADERS, connector=connector)
    return _session

async def fetch_html(url: str, retries: int = 3) -> Optional[str]:
    """Fetch HTML from URL with retry logic."""
    session = await get_session()
    for attempt in range(retries):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    try:
                        return raw.decode('utf-8')
                    except UnicodeDecodeError:
                        return raw.decode('latin-1', errors='replace')
                elif resp.status == 403:
                    logger.warning(f"403 Forbidden: {url}")
                    return None
                else:
                    logger.warning(f"HTTP {resp.status}: {url}")
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
    return None

async def get_chapters_from_page(page: int, book_id: int = BOOK_ID) -> list[dict]:
    """Lấy danh sách chương của 1 trang cụ thể (mỗi trang có ~100 chương)."""
    url = f"{BASE_URL}/get/listchap/{book_id}?page={page}"
    session = await get_session()
    for attempt in range(4):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.warning(f"HTTP {resp.status} for page {page} (attempt {attempt+1})")
                    await asyncio.sleep(2)
                    continue
                data = await resp.json(content_type=None)
                html_content = data.get('data', '')
                if not html_content or len(html_content.strip()) < 50:
                    return []
                
                soup = BeautifulSoup(html_content, 'lxml')
                chapters = []
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    # Hỗ trợ cả chuong- và chuong-chuong-
                    m = re.search(r'/chuong(?:-chuong)?-(\d+)', href)
                    if m:
                        num = int(m.group(1))
                        full_url = BASE_URL + href if href.startswith('/') else href
                        chapters.append({
                            'num': num,
                            'title': title,
                            'url': full_url,
                            'slug': href.lstrip('/')
                        })
                return chapters
        except Exception as e:
            logger.error(f"Error fetching page {page} (attempt {attempt+1}): {e}")
            await asyncio.sleep(2 * (attempt + 1))
    return []

async def get_chapter_list(start_page: int = 1, max_pages: int = 20) -> list[dict]:
    """
    Lấy danh sách chương từ toàn bộ các trang.
    Không dừng lại ngay khi 1 trang lỗi, mà duyệt đủ max_pages.
    """
    all_chapters = []
    seen_nums = set()
    consecutive_empty = 0

    for p in range(start_page, max_pages + 1):
        chaps = await get_chapters_from_page(p)
        if not chaps:
            consecutive_empty += 1
            logger.info(f"Page {p} returned empty (empty streak: {consecutive_empty})")
            if consecutive_empty >= 2:
                logger.info(f"Stopping pagination at page {p} after 2 consecutive empty pages.")
                break
            continue
        
        consecutive_empty = 0
        new_count = 0
        for c in chaps:
            if c['num'] not in seen_nums:
                seen_nums.add(c['num'])
                all_chapters.append(c)
                new_count += 1
        logger.info(f"Fetched page {p}: {new_count} new chapters (total so far: {len(all_chapters)})")
        await asyncio.sleep(0.5)

    all_chapters.sort(key=lambda x: x['num'])
    return all_chapters

async def get_chapter_content(chapter_url: str) -> Optional[dict]:
    """
    Lấy nội dung một chương.
    Trả về {title, content, next_url, word_count}
    """
    html = await fetch_html(chapter_url)
    if not html:
        return None

    soup = BeautifulSoup(html, 'lxml')

    # Extract title
    title = ''
    h1 = soup.find('h1')
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        h2 = soup.find('h2')
        if h2:
            title = h2.get_text(strip=True)

    # Extract content
    content_text = ''
    content_div = None
    for selector in [
        {'class_': 'chapter-content'},
        {'class_': 'reading-content'},
        {'class_': 'text-content'},
        {'id': 'chapter-content'},
        {'class_': 'inner-content'},
    ]:
        content_div = soup.find('div', **selector)
        if content_div:
            break

    if not content_div:
        divs = soup.find_all('div')
        best_div = None
        best_count = 0
        for div in divs:
            ps = div.find_all('p', recursive=False)
            if len(ps) > best_count:
                best_count = len(ps)
                best_div = div
        if best_count >= 3:
            content_div = best_div

    if content_div:
        for tag in content_div.find_all(['script', 'style', 'button', 'a']):
            tag.decompose()

        paragraphs = []
        for p in content_div.find_all('p'):
            text = p.get_text(separator=' ', strip=True)
            if text and len(text) > 2:
                paragraphs.append(text)

        if not paragraphs:
            content_text = content_div.get_text(separator='\n', strip=True)
        else:
            content_text = '\n'.join(paragraphs)

    next_url = None
    for link in soup.find_all('a', href=True):
        link_text = link.get_text(strip=True).lower()
        if any(kw in link_text for kw in ['chương sau', 'tiếp', 'next', '>']):
            href = link.get('href', '')
            if NOVEL_SLUG in href:
                next_url = BASE_URL + href if href.startswith('/') else href
                break

    content_text = clean_text(content_text)

    return {
        'title': title,
        'content': content_text,
        'next_url': next_url,
        'word_count': len(content_text.split())
    }

def clean_text(text: str) -> str:
    """Clean up scraped text for TTS."""
    text = re.sub(r'-{3,}', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()

async def close():
    global _session
    if _session and not _session.closed:
        await _session.close()
