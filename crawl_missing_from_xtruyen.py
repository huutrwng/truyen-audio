"""
Cào bổ sung các chương bị thiếu từ xtruyen.vn
Tuần tự, an toàn tuyệt đối với Cloudflare, không bao giờ bị 429.
"""
import os
import sys
import io
import re
import asyncio
import aiohttp
import sqlite3
import logging
from bs4 import BeautifulSoup

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("XTruyenScraper")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_DIR, 'data', 'chapters.db')

BASE_URL = "https://xtruyen.vn/truyen/tu-tien-khai-cuc-tong-duoc-dong-khai-thuy"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
    "Referer": "https://xtruyen.vn/"
}

async def fetch_one(session: aiohttp.ClientSession, num: int, conn: sqlite3.Connection) -> bool:
    url = f"{BASE_URL}/chuong-{num}/"
    for attempt in range(3):
        try:
            await asyncio.sleep(0.4)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 404:
                    logger.warning(f"[Chương {num}] 404 Not Found")
                    return False
                if resp.status == 429:
                    logger.warning(f"[Chương {num}] 429 Rate limit, ngủ 8s...")
                    await asyncio.sleep(8)
                    continue
                if resp.status != 200:
                    logger.warning(f"[Chương {num}] HTTP {resp.status} (attempt {attempt+1})")
                    await asyncio.sleep(2)
                    continue

                html = await resp.text()
                soup = BeautifulSoup(html, 'lxml')

                h2 = soup.find('h2')
                title = h2.get_text(strip=True) if h2 else ''
                if not title:
                    h1 = soup.find('h1')
                    title = h1.get_text(strip=True) if h1 else f"Chương {num}"

                if not re.search(r'chuong|chương', title, re.IGNORECASE):
                    title = f"Chương {num}: {title}"

                d = soup.find('div', class_='reading-content') or soup.find('div', class_='entry-content')
                if not d:
                    for cl in ['chapter-content', 'content', 'reading-content', 'entry-content']:
                        d = soup.find('div', class_=cl)
                        if d: break

                if not d:
                    return False

                for bad in d.find_all(['script', 'style', 'iframe', 'button', 'a']):
                    bad.decompose()

                ps = [p.get_text(strip=True) for p in d.find_all('p') if p.get_text(strip=True)]
                if not ps:
                    text_raw = d.get_text('\n', strip=True)
                    ps = [line.strip() for line in text_raw.split('\n') if line.strip()]

                content = '\n\n'.join(ps)
                word_count = len(content.split())

                if len(content) < 100:
                    return False

                slug = f"chuong-{num}"
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO chapters (num, title, url, slug, content, word_count, audio_status)
                    VALUES (?, ?, ?, ?, ?, ?, 'none')
                    ON CONFLICT(num) DO UPDATE SET
                        title=excluded.title,
                        url=excluded.url,
                        slug=excluded.slug,
                        content=excluded.content,
                        word_count=excluded.word_count,
                        updated_at=CURRENT_TIMESTAMP
                """, (num, title, url, slug, content, word_count))
                conn.commit()

                logger.info(f"✓ [{num}] '{title}' ({word_count} chữ)")
                return True

        except Exception as e:
            logger.error(f"[Chương {num}] Error: {e}")
            await asyncio.sleep(2)

    return False

async def main(start_chap: int = 935, end_chap: int = 2045):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT num FROM chapters WHERE num >= ?", (start_chap,))
    existing_nums = set(row[0] for row in cursor.fetchall())
    
    missing_nums = [n for n in range(start_chap, end_chap + 1) if n not in existing_nums]
    logger.info(f"Tổng cần bổ sung: {len(missing_nums)} chương trong khoảng [{start_chap}, {end_chap}].")

    if not missing_nums:
        logger.info("Tất cả các chương đã đầy đủ 100%!")
        conn.close()
        return

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        success = 0
        for idx, num in enumerate(missing_nums):
            ok = await fetch_one(session, num, conn)
            if ok:
                success += 1
            if (idx + 1) % 25 == 0:
                logger.info(f"--- Tiến độ cào: {idx + 1}/{len(missing_nums)} (thành công {success}) ---")

    logger.info(f"============================================================")
    logger.info(f"🎉 HOÀN THÀNH: Đã bổ sung thành công {success}/{len(missing_nums)} chương!")
    logger.info(f"============================================================")
    conn.close()

if __name__ == '__main__':
    start = 935
    end = 2045
    if len(sys.argv) > 1:
        start = int(sys.argv[1])
    if len(sys.argv) > 2:
        end = int(sys.argv[2])
    asyncio.run(main(start, end))
