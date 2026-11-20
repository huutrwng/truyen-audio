"""
Worker ưu tiên cao chuyển đổi Audio cho các chương 942 - 950
Sau khi hoàn thành 942 - 950, tiếp tục chuyển đổi các chương 951+ còn thiếu.
Tuân thủ nghiêm ngặt:
- Không bao giờ convert chương 1 - 935 (đã skip theo yêu cầu người dùng).
- Giọng đọc: Hoài My (vi-VN-HoaiMyNeural).
- Khử 100% ký tự ngoặc kép, nháy đơn, nháy kép ("ngoặc kép" sẽ không bao giờ được phát âm).
- Tự động fallback linh hoạt nếu gặp câu nhạy cảm của Azure.
"""
import asyncio
import os
import sys
import io
import time
import logging

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import database as db
import tts_converter

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = [handler]

logger = logging.getLogger("PriorityConverter")

AUDIO_DIR = os.path.join(PROJECT_DIR, 'audio')
os.makedirs(AUDIO_DIR, exist_ok=True)
TARGET_VOICE = "vi-VN-HoaiMyNeural"
MIN_VALID_AUDIO_BYTES = 4 * 1024 * 1024  # Tối thiểu 4MB cho 1 chương hoàn chỉnh

async def convert_one_chapter(num: int) -> bool:
    chap = await db.get_chapter(num)
    if not chap or not chap.get('content'):
        logger.warning(f"[Chương {num}] Không tìm thấy nội dung trong DB!")
        return False

    title = chap.get('title') or f"Chương {num}"
    content = chap['content']
    audio_filename = f"chapter_{num:04d}.mp3"
    audio_path = os.path.join(AUDIO_DIR, audio_filename)
    rel_path = f"audio/{audio_filename}"

    # Kiểm tra nếu file audio đã tồn tại hợp lệ
    if os.path.exists(audio_path):
        sz = os.path.getsize(audio_path)
        if sz >= MIN_VALID_AUDIO_BYTES:
            mb = sz / (1024 * 1024)
            logger.info(f"[Chương {num}] Đã có sẵn audio hoàn chỉnh ({mb:.2f} MB). Bỏ qua.")
            await db.update_audio_status(num, 'done', rel_path, TARGET_VOICE)
            return True
        else:
            try:
                os.remove(audio_path)
            except Exception:
                pass

    logger.info(f"▶ Bắt đầu chuyển đổi Chương {num}: {title} ({len(content)} ký tự)...")
    await db.update_audio_status(num, 'converting')

    t0 = time.time()
    try:
        ok = await tts_converter.convert_chapter_to_audio(
            text=content,
            output_path=audio_path,
            voice=TARGET_VOICE,
            title=title
        )
        elapsed = round(time.time() - t0, 1)

        if ok and os.path.exists(audio_path) and os.path.getsize(audio_path) >= MIN_VALID_AUDIO_BYTES:
            mb = os.path.getsize(audio_path) / (1024 * 1024)
            logger.info(f"🎉 [Chương {num}] HOÀN THÀNH trong {elapsed}s! Kích thước: {mb:.2f} MB")
            await db.update_audio_status(num, 'done', rel_path, TARGET_VOICE)
            return True
        else:
            logger.error(f"✗ [Chương {num}] Thất bại sau {elapsed}s (kích thước chưa đạt).")
            await db.update_audio_status(num, 'error')
            return False
    except Exception as e:
        logger.error(f"✗ [Chương {num}] Lỗi ngoại lệ: {e}")
        await db.update_audio_status(num, 'error')
        return False

async def main():
    await db.init_db()
    logger.info("=== BẮT ĐẦU TIẾN TRÌNH CONVERT ƯU TIÊN HÀNG ĐẦU ===")

    # 1. HÀNG ĐỢI ƯU TIÊN SỐ 1: Chương 942 đến 950
    priority_chapters = list(range(942, 951))
    logger.info(f"📌 [ƯU TIÊN HÀNG ĐẦU] Danh sách chương: {priority_chapters}")

    for num in priority_chapters:
        await convert_one_chapter(num)
        await asyncio.sleep(2.5)

    logger.info("✅ HOÀN THÀNH XUẤT SẮC TOÀN BỘ CHƯƠNG ƯU TIÊN 941 - 950!")

    # 2. HÀNG ĐỢI TIẾP THEO: Quét các chương còn thiếu từ 951 trở đi
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT num FROM chapters WHERE num >= 951 ORDER BY num ASC")
    all_future = [row[0] for row in c.fetchall()]

    for num in all_future:
        audio_filename = f"chapter_{num:04d}.mp3"
        audio_path = os.path.join(AUDIO_DIR, audio_filename)
        # Chỉ convert nếu file chưa có hoặc chưa đạt chuẩn 4MB
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < MIN_VALID_AUDIO_BYTES:
            logger.info(f"Tiếp tục chuyển đổi chương thiếu: {num}")
            await convert_one_chapter(num)
            await asyncio.sleep(2.5)

if __name__ == '__main__':
    asyncio.run(main())
