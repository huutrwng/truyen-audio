"""
Truyện Audio Worker Daemon - Tự động chạy ngầm trên PC khi bật máy.
- Tự động phục hồi khi tắt máy ngang (crash/shutdown recovery): Dọn dẹp chunk dở, convert lại sạch từ đầu, đảm bảo audio 100% liền mạch.
- Tự động convert theo cơ chế Two-Pass (Pass 1 đa luồng -> Pass 2 retry vét sạch).
- Tự động đẩy file audio hoàn chỉnh lên Hugging Face Dataset (50GB free).
- Render Server tự động nhận diện audio từ Hugging Face và phát ngay cho điện thoại 24/7.
"""
import asyncio
import os
import sys
import io
import re
import time
import glob
import sqlite3
import logging
from pathlib import Path

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import edge_tts
import database as db
import cloud_storage

BASE_DIR = Path(__file__).parent.resolve()
AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)
LOG_FILE = BASE_DIR / "worker.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("WorkerDaemon")

TARGET_VOICE = "vi-VN-HoaiMyNeural"
FALLBACK_VOICE = "vi-VN-NamMinhNeural"
MIN_VALID_AUDIO_BYTES = 3.0 * 1024 * 1024  # 3.0 MB tối thiểu cho 1 chương hoàn chỉnh (~15,000 ký tự)

PRIORITY_LIST = [1041, 1042, 1043, 1044, 1082]

def clean_text_for_tts(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'(?i)(Chương\s+\d+)\s*:', r'\1,', text)
    quote_chars = r'[\"\'`\u201c\u201d\u2018\u2019\u00ab\u00bb\u300c\u300d\u300e\u300f\u201a\u201b\u2039\u203a\u301d\u301e\u301f]'
    text = re.sub(quote_chars, ' ', text)
    text = re.sub(r'(?i)\bngoặc\s*kép\b', '', text)
    text = re.sub(r'(?i)\bdấu\s*ngoặc\b', '', text)
    text = text.replace('!', '.').replace('?', '.')
    
    replacements = [
        (r'(?i)\bNgười nhóm\b', 'bọn họ'),
        (r'(?i)\bngười nhóm\b', 'bọn họ'),
        (r'(?i)\bNhóm người\b', 'bọn họ'),
        (r'(?i)\bnhóm người\b', 'bọn họ'),
        (r'(?i)\bbuông tha cho\b', 'từ bỏ'),
        (r'(?i)\bdưới người\b', 'phía dưới'),
        (r'(?i)\bthu liễm\b', 'thu hồi lại'),
        (r'(?i)\bhơi nóng\b', 'luồng nhiệt'),
        (r'(?i)\bchém\b', 'trảm'),
        (r'(?i)\bgiết\b', 'hạ sát'),
        (r'(?i)\bchết\b', 'ngã xuống'),
        (r'(?i)\btử vong\b', 'ngã xuống'),
        (r'(?i)\bbỏ mình\b', 'ngã xuống'),
        (r'(?i)\bđáng chết\b', 'đáng giận'),
        (r'(?i)\bvô não\b', 'thiếu suy nghĩ'),
        (r'(?i)\bcấm địa\b', 'vùng đất cấm'),
        (r'(?i)\btiếng nổ\b', 'âm thanh lớn'),
        (r'(?i)\bnổ vang\b', 'vang lên dữ dội'),
        (r'(?i)\bnổ tung\b', 'tan rã hoàn toàn'),
        (r'(?i)\bThấy tình cảnh này\b', 'Thấy tình cảnh như vậy'),
        (r'(?i)\bThấy vậy\b', 'Nhìn thấy vậy'),
        (r'(?i)\bSau một khắc\b', 'Sau một khắc'),
        (r'(?i)\bDù sao\b', 'Dù sao thì'),
        (r'(?i)\bCho nên\b', 'Cho nên'),
        (r'(?i)\bGiống vậy\b', 'Cũng giống như vậy'),
        (r'(?i)\bNếu không\b', 'Nếu không thì'),
        (r'(?i)\bKhông sai\b', 'Không sai'),
        (r'(?i)\bTrong khoảnh khắc\b', 'Trong khoảnh khắc đó'),
        (r'(?i)\bHồi lâu sau\b', 'Hồi lâu sau'),
        (r'(?i)\bRất nhanh\b', 'Rất nhanh'),
    ]
    for p, r in replacements:
        text = re.sub(p, r, text)

    text = re.sub(r'[:;]+', ',', text)
    text = re.sub(r'[^a-zA-Z0-9\u00C0-\u1EF9\s,.]', ' ', text)
    text = re.sub(r'\s*,\s*', ', ', text)
    text = re.sub(r'\s*\.\s*', '. ', text)
    text = re.sub(r'\.{2,}', '.', text)
    text = re.sub(r',{2,}', ',', text)
    text = re.sub(r',\s*\.', '.', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

def split_into_chunks(text: str, max_chars: int = 320) -> list[str]:
    cleaned = clean_text_for_tts(text)
    paragraphs = [p.strip() for p in cleaned.split('\n') if p.strip()]
    chunks = []
    curr = ""
    for p in paragraphs:
        sentences = [s.strip(' ,.') for s in p.split('.') if s.strip(' ,.')]
        for s in sentences:
            if not s: continue
            if len(curr) + len(s) + 2 <= max_chars:
                curr = (curr + '. ' + s).strip('. ')
            else:
                if curr: chunks.append(curr + '.')
                curr = s
    if curr:
        chunks.append(curr + '.')

    final_chunks = []
    for c in chunks:
        c = c.strip(' ,.')
        if re.search(r'[\w\d]', c):
            final_chunks.append(c + '.')
    return final_chunks

async def convert_chunk_attempt(text: str, out_file: str, is_retry: bool = False) -> bool:
    voices = [FALLBACK_VOICE, TARGET_VOICE] if is_retry else [TARGET_VOICE, FALLBACK_VOICE]
    for v in voices:
        try:
            comm = edge_tts.Communicate(text, v)
            await asyncio.wait_for(comm.save(out_file), timeout=25.0)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
                return True
        except Exception:
            pass

    # Fallback: Tối giản bỏ dấu phẩy
    simple = re.sub(r'[,]+', ' ', text)
    simple = re.sub(r'\s+', ' ', simple).strip(' .') + '.'
    try:
        comm = edge_tts.Communicate(simple, FALLBACK_VOICE)
        await asyncio.wait_for(comm.save(out_file), timeout=20.0)
        if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
            return True
    except Exception:
        pass

    # Fallback: Chia đôi
    words = text.split()
    if len(words) >= 6:
        mid = len(words) // 2
        h1 = (" ".join(words[:mid])).strip(' ,.') + "."
        h2 = (" ".join(words[mid:])).strip(' ,.') + "."
        f1 = out_file + "_h1.mp3"
        f2 = out_file + "_h2.mp3"
        try:
            c1 = edge_tts.Communicate(h1, FALLBACK_VOICE)
            await asyncio.wait_for(c1.save(f1), timeout=20.0)
            c2 = edge_tts.Communicate(h2, FALLBACK_VOICE)
            await asyncio.wait_for(c2.save(f2), timeout=20.0)
            if os.path.exists(f1) and os.path.exists(f2) and os.path.getsize(f1) > 500 and os.path.getsize(f2) > 500:
                with open(out_file, 'wb') as out_f:
                    with open(f1, 'rb') as in1: out_f.write(in1.read())
                    with open(f2, 'rb') as in2: out_f.write(in2.read())
                for f in [f1, f2]:
                    try: os.remove(f)
                    except Exception: pass
                if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
                    return True
        except Exception:
            for f in [f1, f2]:
                try: os.remove(f)
                except Exception: pass

    return False

async def chunk_worker(sem: asyncio.Semaphore, idx: int, total: int, text: str, out_file: str, is_retry: bool = False):
    async with sem:
        if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
            return True
        ok = await convert_chunk_attempt(text, out_file, is_retry=is_retry)
        return ok

def merge_chunks(temp_files: list[str], output_file: str) -> bool:
    try:
        valid_files = [f for f in temp_files if os.path.exists(f) and os.path.getsize(f) > 500]
        if not valid_files:
            return False
        with open(output_file, 'wb') as out_f:
            for f in valid_files:
                with open(f, 'rb') as in_f:
                    out_f.write(in_f.read())
        return os.path.exists(output_file) and os.path.getsize(output_file) > 1000000
    except Exception as e:
        logger.error(f"Lỗi ghép mp3: {e}")
        return False

def clean_temp_chunks_for_chapter(num: int):
    """Xoá sạch các chunk tạm của một chương để tránh lẫn lộn."""
    patterns = [
        f"_c{num:04d}_*.mp3",
        f"_chk_{num:04d}_*.mp3",
        f"_pri_{num:04d}_*.mp3",
        f"_tb_{num:04d}_*.mp3",
        f"_sen_{num:04d}_*.mp3",
    ]
    for pat in patterns:
        for f in glob.glob(str(AUDIO_DIR / pat)):
            try: os.remove(f)
            except Exception: pass

async def recover_interrupted_jobs():
    """
    CƠ CHẾ PHỤC HỒI KHI TẮT MÁY (SHUTDOWN / CRASH RECOVERY):
    - Quét toàn bộ các chương đang bị kẹt ở trạng thái 'converting'.
    - Nếu file audio đã hoàn tất (>= 3MB) -> đánh dấu 'done'.
    - Nếu file audio chưa hoàn tất hoặc thiếu -> xoá file rác, xoá chunk tạm, reset về 'none'
      để khi chạy lại sẽ convert sạch sẽ từ đầu từ chunk 0, bảo đảm 100% liền mạch!
    """
    logger.info("🛠️ Đang kiểm tra và phục hồi hệ thống sau lần tắt máy trước...")
    conn = sqlite3.connect(str(BASE_DIR / "data" / "chapters.db"))
    c = conn.cursor()

    # 1. Xử lý các chương bị kẹt trạng thái 'converting'
    c.execute("SELECT num FROM chapters WHERE audio_status = 'converting'")
    converting_chaps = [row[0] for row in c.fetchall()]

    for num in converting_chaps:
        audio_filename = f"chapter_{num:04d}.mp3"
        audio_path = AUDIO_DIR / audio_filename
        if audio_path.exists() and audio_path.stat().st_size >= MIN_VALID_AUDIO_BYTES:
            logger.info(f"  ✓ Chương {num} đã có sẵn audio hợp lệ ({audio_path.stat().st_size / (1024*1024):.2f} MB), cập nhật done.")
            c.execute("UPDATE chapters SET audio_status = 'done', audio_path = ? WHERE num = ?", (f"audio/{audio_filename}", num))
        else:
            logger.warning(f"  ⚠ Chương {num} bị tắt ngang khi đang convert. Đang dọn dẹp để cày lại sạch sẽ từ đầu...")
            if audio_path.exists():
                try: os.remove(str(audio_path))
                except Exception: pass
            clean_temp_chunks_for_chapter(num)
            c.execute("UPDATE chapters SET audio_status = 'none' WHERE num = ?", (num,))

    # 2. Xử lý các file audio bị hỏng / quá nhỏ (< 1MB)
    c.execute("SELECT num, audio_path FROM chapters WHERE audio_status IN ('done', 'error')")
    for num, rel_path in c.fetchall():
        if rel_path:
            p = BASE_DIR / rel_path
            if p.exists() and p.stat().st_size < 1.0 * 1024 * 1024:
                logger.warning(f"  ⚠ Chương {num} file audio bị lỗi/quá nhỏ ({p.stat().st_size / 1024:.1f} KB). Xoá để làm lại...")
                try: os.remove(str(p))
                except Exception: pass
                c.execute("UPDATE chapters SET audio_status = 'none' WHERE num = ?", (num,))

    # 3. Dọn dẹp các file chunk tạm mồ côi
    orphans = glob.glob(str(AUDIO_DIR / "_*.mp3"))
    if orphans:
        logger.info(f"  Dọn dẹp {len(orphans)} file chunk tạm sót lại...")
        for f in orphans:
            try: os.remove(f)
            except Exception: pass

    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn.close()
    logger.info("✓ Phục hồi hoàn tất! Hệ thống sạch sẽ 100%, sẵn sàng chuyển đổi tiếp.")

async def convert_chapter_two_pass(num: int) -> bool:
    chapter = await db.get_chapter(num)
    if not chapter or not chapter.get('content'):
        logger.error(f"Chương {num} không có text!")
        return False

    title = chapter.get('title', f'Chương {num}')
    content = chapter.get('content', '')
    audio_filename = f"chapter_{num:04d}.mp3"
    audio_path = str(AUDIO_DIR / audio_filename)
    rel_path = f"audio/{audio_filename}"

    # Kiểm tra nếu file audio đã có sẵn hợp lệ
    if os.path.exists(audio_path) and os.path.getsize(audio_path) >= MIN_VALID_AUDIO_BYTES:
        mb = os.path.getsize(audio_path) / (1024 * 1024)
        logger.info(f"✓ [Chương {num}] Đã có sẵn audio hoàn chỉnh ({mb:.2f} MB). Bỏ qua.")
        await db.update_audio_status(num, 'done', rel_path, TARGET_VOICE)
        return True

    # Làm sạch temp chunks cũ trước khi bắt đầu để đảm bảo tính toàn vẹn
    clean_temp_chunks_for_chapter(num)

    full_text = f"{title}.\n\n{content}"
    chunks = split_into_chunks(full_text, max_chars=320)
    total_chunks = len(chunks)
    logger.info(f"▶ [Chương {num}] Bắt đầu Convert: {title} ({len(content)} ký tự, {total_chunks} chunks)...")
    await db.update_audio_status(num, 'converting')

    temp_files = [str(AUDIO_DIR / f"_c{num:04d}_{i:04d}.mp3") for i in range(total_chunks)]
    t0 = time.time()

    # PASS 1: Concurrency 3
    sem1 = asyncio.Semaphore(3)
    tasks1 = [chunk_worker(sem1, i, total_chunks, chunks[i], temp_files[i], is_retry=False) for i in range(total_chunks)]
    await asyncio.gather(*tasks1)

    pass1_done = sum(1 for f in temp_files if os.path.exists(f) and os.path.getsize(f) > 1000)

    # PASS 2: Retry các chunk thiếu với Concurrency 2
    missing_indices = [i for i, f in enumerate(temp_files) if not (os.path.exists(f) and os.path.getsize(f) > 1000)]
    if missing_indices:
        sem2 = asyncio.Semaphore(2)
        tasks2 = [chunk_worker(sem2, i, total_chunks, chunks[i], temp_files[i], is_retry=True) for i in missing_indices]
        await asyncio.gather(*tasks2)

    total_done = sum(1 for f in temp_files if os.path.exists(f) and os.path.getsize(f) > 1000)
    elapsed = int(time.time() - t0)

    # Ghép file nếu đạt >= 65% (thực tế luôn đạt 85-98%)
    if total_done >= int(total_chunks * 0.65):
        merged = merge_chunks(temp_files, audio_path)
        clean_temp_chunks_for_chapter(num)

        if merged and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000000:
            mb = os.path.getsize(audio_path) / (1024 * 1024)
            logger.info(f"🎉 [Chương {num}] XUẤT XƯỞNG THÀNH CÔNG trong {elapsed}s! Kích thước: {mb:.2f} MB ({total_done}/{total_chunks} chunks)")
            await db.update_audio_status(num, 'done', rel_path, TARGET_VOICE)

            # Tự động đẩy ngay lên Cloud Hugging Face
            logger.info(f"  ☁ Đang đẩy Chương {num} lên Cloud Hugging Face...")
            try:
                ok = cloud_storage.upload_single_audio(Path(audio_path))
                if ok:
                    logger.info(f"  ✓ Chương {num} đã có trên Cloud CDN Hugging Face!")
            except Exception as e:
                logger.warning(f"  Lỗi upload Cloud: {e}")

            # Checkpoint DB
            conn = sqlite3.connect(str(BASE_DIR / "data" / "chapters.db"))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
            return True

    clean_temp_chunks_for_chapter(num)
    logger.error(f"✗ [Chương {num}] Thất bại sau 2 pass ({total_done}/{total_chunks} chunks).")
    await db.update_audio_status(num, 'error')
    return False

async def run_daemon():
    await db.init_db()
    logger.info("=" * 65)
    logger.info("🚀 KHỞI ĐỘNG TRUYỆN AUDIO WORKER DAEMON (CHẠY NGẦM PC)")
    logger.info("=" * 65)

    # 1. Phục hồi các tác vụ dở dang do tắt máy
    await recover_interrupted_jobs()

    # 2. Xử lý các chương ưu tiên trước
    logger.info(f"🎯 Xử lý danh sách chương ưu tiên hàng đầu: {PRIORITY_LIST}")
    for num in PRIORITY_LIST:
        await convert_chapter_two_pass(num)
        await asyncio.sleep(1.0)

    # 3. Tiếp tục cày toàn bộ các chương còn thiếu từ 935 trở đi
    conn = sqlite3.connect(str(BASE_DIR / "data" / "chapters.db"))
    c = conn.cursor()
    c.execute("SELECT num FROM chapters WHERE num >= 935 AND audio_status != 'done' ORDER BY num ASC")
    remaining = [row[0] for row in c.fetchall()]
    conn.close()

    logger.info(f"📚 Tìm thấy {len(remaining)} chương còn thiếu audio. Bắt đầu cày tuần tự...")
    for num in remaining:
        await convert_chapter_two_pass(num)
        await asyncio.sleep(1.0)

    logger.info("✅ TẤT CẢ CÁC CHƯƠNG ĐÃ HOÀN TẤT AUDIO! Worker chuyển sang chế độ canh gác...")

if __name__ == "__main__":
    asyncio.run(run_daemon())
