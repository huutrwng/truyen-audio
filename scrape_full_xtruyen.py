"""
Scrape đầy đủ nội dung nguyên bản từ xtruyen.vn bằng Headless Chrome (đảm bảo giải mã JS đầy đủ 100%).
Tự động bỏ qua các chương đã có đầy đủ nội dung (>= 8000 ký tự).
"""
import sys
import os
import io
import re
import time
import asyncio
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
logger = logging.getLogger("XTruyenFullScraper")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_DIR, 'data', 'chapters.db')
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "https://xtruyen.vn/truyen/tu-tien-khai-cuc-tong-duoc-dong-khai-thuy"

async def scrape_single_chapter(num: int, sem: asyncio.Semaphore, max_retries: int = 3):
    url = f"{BASE_URL}/chuong-{num}/"
    cmd = [
        CHROME_PATH,
        '--headless=new',
        '--disable-gpu',
        '--blink-settings=imagesEnabled=false',
        '--disable-extensions',
        '--no-first-run',
        '--no-default-browser-check',
        '--dump-dom',
        url
    ]

    for attempt in range(1, max_retries + 1):
        async with sem:
            proc = None
            t0 = time.time()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=25.0)
                html = stdout.decode('utf-8', errors='replace')
                dur = time.time() - t0

                if not html or len(html) < 500:
                    logger.warning(f"[Chương {num}] HTML quá ngắn ({len(html)} bytes), thử lại ({attempt}/{max_retries})...")
                    await asyncio.sleep(1.0)
                    continue

                soup = BeautifulSoup(html, 'html.parser')
                
                # Trích xuất tiêu đề
                h2 = soup.find('h2')
                title = h2.get_text(strip=True) if h2 else ''
                if not title:
                    h1 = soup.find('h1')
                    title = h1.get_text(strip=True) if h1 else f"Chương {num}"

                if not re.search(r'chuong|chương', title, re.IGNORECASE):
                    title = f"Chương {num}: {title}"

                # Trích xuất nội dung
                d = soup.find('div', class_='reading-content') or soup.find('div', class_='entry-content')
                if not d:
                    for cl in ['chapter-content', 'content']:
                        d = soup.find('div', class_=cl)
                        if d:
                            break

                if not d:
                    logger.warning(f"[Chương {num}] Không tìm thấy reading-content, thử lại ({attempt}/{max_retries})...")
                    await asyncio.sleep(1.0)
                    continue

                for bad in d.find_all(['script', 'style', 'iframe', 'button', 'a']):
                    bad.decompose()

                ps = [p.get_text(strip=True) for p in d.find_all('p') if p.get_text(strip=True)]
                if not ps:
                    text_raw = d.get_text('\n', strip=True)
                    ps = [line.strip() for line in text_raw.split('\n') if line.strip()]

                content = '\n\n'.join(ps)
                word_count = len(content.split())
                char_count = len(content)

                if char_count < 3000:
                    logger.warning(f"[Chương {num}] Nội dung nghi ngờ bị cắt ({char_count} ký tự, {word_count} từ), thử lại ({attempt}/{max_retries})...")
                    await asyncio.sleep(1.0)
                    continue

                # Cập nhật ngay vào SQLite
                slug = f"chuong-{num}"
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("""
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
                conn.close()

                logger.info(f"✓ [Chương {num}] '{title}' -> {len(ps)} đoạn, {word_count} từ, {char_count} ký tự ({dur:.2f}s)")
                return True

            except asyncio.TimeoutError:
                logger.warning(f"[Chương {num}] Chrome timeout 25s (lần {attempt}/{max_retries})")
                if proc and proc.returncode is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.error(f"[Chương {num}] Lỗi: {e} (lần {attempt}/{max_retries})")
                if proc and proc.returncode is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                await asyncio.sleep(1.0)

    logger.error(f"❌ [Chương {num}] Thất bại hoàn toàn sau {max_retries} lần thử!")
    return False

async def main(start_chap: int = 935, end_chap: int = 2045, concurrency: int = 3):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Tìm tất cả các chương >= start_chap và <= end_chap cần cào (chưa có hoặc < 8000 ký tự)
    cur.execute("""
        SELECT num FROM chapters 
        WHERE num >= ? AND num <= ? 
          AND (content IS NULL OR length(content) < 8000)
        ORDER BY num
    """, (start_chap, end_chap))
    targets = [r[0] for r in cur.fetchall()]
    conn.close()

    logger.info(f"============================================================")
    logger.info(f"🔍 BẮT ĐẦU CÀO ĐẦY ĐỦ NỘI DUNG TỪ XTRUYEN.VN")
    logger.info(f"   Khoảng chương: [{start_chap} -> {end_chap}]")
    logger.info(f"   Số chương cần cào: {len(targets)}")
    logger.info(f"   Số luồng song song: {concurrency}")
    logger.info(f"============================================================")

    if not targets:
        logger.info("Tất cả các chương đã có đầy đủ nội dung (>8000 ký tự). Hoàn tất!")
        return

    sem = asyncio.Semaphore(concurrency)
    success_count = 0
    t_start = time.time()

    # Chạy theo từng đợt để hiển thị tiến độ và giải phóng bộ nhớ
    batch_size = 20
    for i in range(0, len(targets), batch_size):
        batch = targets[i:i+batch_size]
        tasks = [scrape_single_chapter(num, sem) for num in batch]
        results = await asyncio.gather(*tasks)
        success_count += sum(1 for r in results if r)
        elapsed = time.time() - t_start
        rate = success_count / elapsed if elapsed > 0 else 0
        rem = (len(targets) - (i + len(batch))) / rate if rate > 0 else 0
        logger.info(f"--- Tiến độ: {i + len(batch)}/{len(targets)} | Thành công: {success_count} | Tốc độ: {rate:.2f} ch/s | Còn khoảng {rem/60:.1f} phút ---")

    logger.info(f"============================================================")
    logger.info(f"🎉 CÀO NỘI DUNG HOÀN THÀNH!")
    logger.info(f"   Tổng thành công: {success_count}/{len(targets)} chương")
    logger.info(f"   Tổng thời gian: {(time.time() - t_start)/60:.2f} phút")
    logger.info(f"============================================================")

if __name__ == '__main__':
    start = 935
    end = 2045
    concurrency = 3
    if len(sys.argv) > 1:
        start = int(sys.argv[1])
    if len(sys.argv) > 2:
        end = int(sys.argv[2])
    if len(sys.argv) > 3:
        concurrency = int(sys.argv[3])
    asyncio.run(main(start, end, concurrency))
