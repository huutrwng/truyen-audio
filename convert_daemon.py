"""
Worker Đa Luồng Convert Audio Tự Động Ngay Tại Server
Giọng nữ Hoài My (vi-VN-HoaiMyNeural)
Chạy từ chương 935 trở đi, tự động skip các chương đã convert hoàn chỉnh (>5MB).
"""
import asyncio
import os
import sys
import io
import time
import logging

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import database as db
import tts_converter
from scrape_full_xtruyen import scrape_single_chapter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ConvertDaemon")

AUDIO_DIR = os.path.join(PROJECT_DIR, 'audio')
os.makedirs(AUDIO_DIR, exist_ok=True)

TARGET_VOICE = "vi-VN-HoaiMyNeural"
MAX_CONCURRENT_WORKERS = 1  # 1 luồng chuyên sâu chống rate-limit, đảm bảo ổn định 100%
MIN_VALID_AUDIO_BYTES = 5 * 1024 * 1024  # Tối thiểu 5MB cho 1 chương đầy đủ

async def process_single_chapter(chap_info: dict, scrape_sem: asyncio.Semaphore):
    num = chap_info['num']
    title = chap_info.get('title') or f"Chương {num}"

    audio_filename = f"chapter_{num:04d}.mp3"
    audio_path = os.path.join(AUDIO_DIR, audio_filename)
    rel_path = f"audio/{audio_filename}"

    # 1. Kiểm tra file audio đã có và đủ lớn chưa (trên 5MB)
    if os.path.exists(audio_path):
        sz = os.path.getsize(audio_path)
        if sz >= MIN_VALID_AUDIO_BYTES:
            mb = sz / (1024 * 1024)
            logger.info(f"[Chương {num}] Đã có sẵn file audio hợp lệ ({mb:.2f} MB). Bỏ qua.")
            await db.update_audio_status(num, 'done', rel_path, TARGET_VOICE)
            return True
        else:
            # File quá nhỏ (bị lỗi hoặc teaser cũ), xóa đi làm lại
            try:
                os.remove(audio_path)
            except Exception:
                pass

    # 2. Kiểm tra nội dung text, nếu chưa có hoặc < 3000 ký tự thì cào bằng Headless Chrome
    content = chap_info.get('content')
    if not content or len(content.strip()) < 3000:
        db_chap = await db.get_chapter(num)
        if db_chap and db_chap.get('content') and len(db_chap['content'].strip()) >= 3000:
            content = db_chap['content']
            title = db_chap.get('title') or title
        else:
            logger.info(f"[Chương {num}] Đang cào trực tiếp nội dung đầy đủ từ xtruyen.vn...")
            ok_scrape = await scrape_single_chapter(num, scrape_sem)
            if ok_scrape:
                db_chap = await db.get_chapter(num)
                if db_chap and db_chap.get('content'):
                    content = db_chap['content']
                    title = db_chap.get('title') or title
            
            if not content or len(content.strip()) < 3000:
                logger.error(f"[Chương {num}] Không thể lấy đủ nội dung! Bỏ qua.")
                await db.update_audio_status(num, 'error')
                return False

    # 3. Chuyển thể TTS sang Audio
    logger.info(f"▶ [Chương {num}] Bắt đầu convert audio ({TARGET_VOICE}) | {len(content)} ký tự...")
    await db.update_audio_status(num, 'converting', voice=TARGET_VOICE)

    t0 = time.time()
    ok = await tts_converter.convert_chapter_to_audio(
        text=content,
        output_path=audio_path,
        voice=TARGET_VOICE,
        title=title
    )
    elapsed = round(time.time() - t0, 1)

    if ok and os.path.exists(audio_path) and os.path.getsize(audio_path) >= MIN_VALID_AUDIO_BYTES:
        mb = os.path.getsize(audio_path) / (1024 * 1024)
        logger.info(f"✓ [Chương {num}] HOÀN THÀNH trong {elapsed}s! File: {mb:.2f} MB.")
        await db.update_audio_status(num, 'done', rel_path, TARGET_VOICE)
        return True
    else:
        logger.error(f"✗ [Chương {num}] Lỗi chuyển thể TTS hoặc file quá nhỏ!")
        await db.update_audio_status(num, 'error')
        return False

async def worker(queue: asyncio.Queue, scrape_sem: asyncio.Semaphore, stats: dict):
    while not queue.empty():
        try:
            chap = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        try:
            ok = await process_single_chapter(chap, scrape_sem)
            if ok:
                stats['success'] += 1
            else:
                stats['fail'] += 1
        except Exception as e:
            logger.error(f"Lỗi worker: {e}")
            stats['fail'] += 1
        finally:
            queue.task_done()

async def main(start_chap: int = 935, end_chap: int = None, concurrency: int = MAX_CONCURRENT_WORKERS):
    await db.init_db()
    
    all_chapters = await db.get_all_chapters(limit=5000, offset=0)
    
    # Lọc danh sách các chương cần convert
    target_chapters = []
    for c in all_chapters:
        num = c['num']
        if num < start_chap:
            continue
        if end_chap and num > end_chap:
            continue
        
        audio_file = os.path.join(AUDIO_DIR, f"chapter_{num:04d}.mp3")
        # Nếu đã có file valid >= 5MB thì skip
        if os.path.exists(audio_file) and os.path.getsize(audio_file) >= MIN_VALID_AUDIO_BYTES:
            continue
        
        target_chapters.append(c)

    # Sắp xếp tăng dần theo số chương để convert tuần tự từ bé đến lớn
    target_chapters.sort(key=lambda x: x['num'])
    total_target = len(target_chapters)

    logger.info(f"════════════════════════════════════════════════════════════")
    logger.info(f"🚀 BẮT ĐẦU CHẠY CONVERT ĐA LUỒNG SERVER")
    logger.info(f"   Bắt đầu từ chương: {start_chap}")
    if end_chap:
        logger.info(f"   Đến chương: {end_chap}")
    logger.info(f"   Tổng số chương cần convert: {total_target}")
    logger.info(f"   Số luồng song song: {concurrency}")
    logger.info(f"   Giọng đọc: {TARGET_VOICE} (Nữ Hoài My)")
    logger.info(f"════════════════════════════════════════════════════════════")

    if not target_chapters:
        logger.info("Tất cả các chương đã có file audio đầy đủ (>5MB)! Không còn chương nào cần convert.")
        return

    queue = asyncio.Queue()
    for chap in target_chapters:
        queue.put_nowait(chap)

    scrape_sem = asyncio.Semaphore(2)
    stats = {'success': 0, 'fail': 0}

    workers = [asyncio.create_task(worker(queue, scrape_sem, stats)) for _ in range(concurrency)]
    await queue.join()

    for w in workers:
        w.cancel()

    logger.info(f"\n============================================================")
    logger.info(f"🎉 TỔNG KẾT TIẾN TRÌNH CONVERT: Thành công {stats['success']}/{total_target} chương!")
    logger.info(f"============================================================")

if __name__ == '__main__':
    start = 935
    end = None
    workers = MAX_CONCURRENT_WORKERS

    if len(sys.argv) > 1:
        start = int(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2] != 'max':
        end = int(sys.argv[2])
    if len(sys.argv) > 3:
        workers = int(sys.argv[3])

    asyncio.run(main(start, end, workers))
