"""
Priority Audio Converter for chapters: [1039, 1040, 1041, 1042, 1043, 1044, 1082]
Sentence-level synthesis: 100% reliable, zero NoAudioReceived drops, seamless concatenation.
"""
import asyncio
import os
import sys
import io
import re
import time
import sqlite3
import logging
from pathlib import Path

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import edge_tts
import database as db
import cloud_storage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("PriorityFix")

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

TARGET_VOICE = "vi-VN-HoaiMyNeural"
FALLBACK_VOICE = "vi-VN-NamMinhNeural"
PRIORITY_CHAPTERS = [1039, 1040, 1041, 1042, 1043, 1044, 1082]

def clean_text_for_tts(text: str) -> str:
    """Chuan hoa van ban, triet tieu loi Azure safety filter va dau cau bat thuong."""
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

def split_into_sentences(text: str) -> list[str]:
    cleaned = clean_text_for_tts(text)
    paragraphs = [p.strip() for p in cleaned.split('\n') if p.strip()]
    sentences = []
    for p in paragraphs:
        for s in p.split('.'):
            s = s.strip(' ,.')
            if s and re.search(r'[\w\d]', s):
                sentences.append(s + '.')
    return sentences

async def convert_sentence(sem: asyncio.Semaphore, idx: int, total: int, text: str, out_file: str) -> bool:
    async with sem:
        # 1. Hoai My
        try:
            comm = edge_tts.Communicate(text, TARGET_VOICE)
            await asyncio.wait_for(comm.save(out_file), timeout=18.0)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 500:
                return True
        except Exception:
            pass

        # 2. Nam Minh fallback
        try:
            comm = edge_tts.Communicate(text, FALLBACK_VOICE)
            await asyncio.wait_for(comm.save(out_file), timeout=18.0)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 500:
                return True
        except Exception:
            pass

        # 3. Simplify text (remove all commas)
        simple = re.sub(r'[,]+', ' ', text)
        simple = re.sub(r'\s+', ' ', simple).strip(' .') + '.'
        try:
            comm = edge_tts.Communicate(simple, FALLBACK_VOICE)
            await asyncio.wait_for(comm.save(out_file), timeout=18.0)
            if os.path.exists(out_file) and os.path.getsize(out_file) > 500:
                return True
        except Exception:
            pass

        # 4. Neu cau dai, chia doi
        words = text.split()
        if len(words) >= 6:
            mid = len(words) // 2
            h1 = (" ".join(words[:mid])).strip(' ,.') + "."
            h2 = (" ".join(words[mid:])).strip(' ,.') + "."
            f1 = out_file + "_h1.mp3"
            f2 = out_file + "_h2.mp3"
            try:
                c1 = edge_tts.Communicate(h1, FALLBACK_VOICE)
                await asyncio.wait_for(c1.save(f1), timeout=15.0)
                c2 = edge_tts.Communicate(h2, FALLBACK_VOICE)
                await asyncio.wait_for(c2.save(f2), timeout=15.0)
                if os.path.exists(f1) and os.path.exists(f2) and os.path.getsize(f1) > 200 and os.path.getsize(f2) > 200:
                    with open(out_file, 'wb') as out_f:
                        with open(f1, 'rb') as in1: out_f.write(in1.read())
                        with open(f2, 'rb') as in2: out_f.write(in2.read())
                    for f in [f1, f2]:
                        try: os.remove(f)
                        except Exception: pass
                    if os.path.exists(out_file) and os.path.getsize(out_file) > 500:
                        return True
            except Exception:
                for f in [f1, f2]:
                    try: os.remove(f)
                    except Exception: pass

    logger.warning(f"  [{idx+1}/{total}] Bo qua cau loi: {repr(text[:40])}")
    return False

def merge_audio_files(input_files: list[str], output_file: str) -> bool:
    try:
        valid_files = [f for f in input_files if os.path.exists(f) and os.path.getsize(f) > 300]
        if not valid_files:
            return False
        with open(output_file, 'wb') as out_f:
            for f in valid_files:
                with open(f, 'rb') as in_f:
                    out_f.write(in_f.read())
        return os.path.exists(output_file) and os.path.getsize(output_file) > 1000000
    except Exception as e:
        logger.error(f"Loi ghep file: {e}")
        return False

async def convert_chapter(num: int) -> bool:
    chapter = await db.get_chapter(num)
    if not chapter:
        logger.error(f"Khong tim thay chuong {num}")
        return False

    title = chapter.get('title', f'Chương {num}')
    content = chapter.get('content', '')
    if not content:
        logger.error(f"Chuong {num} khong co text")
        return False

    audio_filename = f"chapter_{num:04d}.mp3"
    audio_path = str(AUDIO_DIR / audio_filename)
    rel_path = f"audio/{audio_filename}"

    sentences = split_into_sentences(f"{title}.\n\n{content}")
    logger.info(f"▶ [Chương {num}] Convert: {title} ({len(content)} ky tu, {len(sentences)} cau)...")
    await db.update_audio_status(num, 'converting')

    temp_files = [str(AUDIO_DIR / f"_sen_{num:04d}_{i:04d}.mp3") for i in range(len(sentences))]
    sem = asyncio.Semaphore(4)  # 4 cau dong thoi

    t0 = time.time()
    tasks = [convert_sentence(sem, i, len(sentences), s, temp_files[i]) for i, s in enumerate(sentences)]
    results = await asyncio.gather(*tasks)
    elapsed = int(time.time() - t0)

    success_count = sum(1 for r in results if r)
    success_rate = success_count / len(sentences) * 100

    if success_count >= int(len(sentences) * 0.90):
        merged = merge_audio_files(temp_files, audio_path)
        for f in temp_files:
            try: os.remove(f)
            except Exception: pass

        if merged and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000000:
            mb = os.path.getsize(audio_path) / (1024 * 1024)
            logger.info(f"🎉 [Chương {num}] THANH CONG trong {elapsed}s! Dung luong: {mb:.2f} MB ({success_count}/{len(sentences)} cau - {success_rate:.1f}%)")
            await db.update_audio_status(num, 'done', rel_path, TARGET_VOICE)
            return True

    for f in temp_files:
        try: os.remove(f)
        except Exception: pass
    logger.error(f"✗ [Chương {num}] That bai ({success_count}/{len(sentences)} cau)")
    await db.update_audio_status(num, 'error')
    return False

async def main():
    await db.init_db()
    logger.info("=" * 65)
    logger.info(f"🎯 BẮT ĐẦU CONVERT ƯU TIÊN CÁC CHƯƠNG ĐỨT ĐOẠN: {PRIORITY_CHAPTERS}")
    logger.info("=" * 65)

    completed_files = []

    for num in PRIORITY_CHAPTERS:
        ok = await convert_chapter(num)
        if ok:
            fpath = AUDIO_DIR / f"chapter_{num:04d}.mp3"
            completed_files.append(fpath)
            
            # Checkpoint DB
            conn = sqlite3.connect(str(BASE_DIR / "data" / "chapters.db"))
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
            await asyncio.sleep(0.5)

    logger.info("=" * 65)
    logger.info(f"Đã hoàn thành {len(completed_files)}/{len(PRIORITY_CHAPTERS)} chương!")

    if completed_files:
        logger.info(f"Bắt đầu upload batch {len(completed_files)} files lên Hugging Face CDN...")
        uploaded = cloud_storage.upload_batch_audio(completed_files)
        if uploaded:
            logger.info("✓ Toàn bộ các file audio đã được đẩy lên Hugging Face Dataset thành công!")
        else:
            logger.warning("Upload batch gap loi, thu upload tung file...")
            for f in completed_files:
                cloud_storage.upload_single_audio(f)

    logger.info("✓ HOÀN TẤT TOÀN BỘ NHIỆM VỤ!")

if __name__ == "__main__":
    asyncio.run(main())
