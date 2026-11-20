"""
Công cụ cào và chuyển thể Audio hàng loạt từ chương 1000 trở đi
"""
import asyncio
import os
import sys
import io
import time

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import scraper
import database as db
import tts_converter

AUDIO_DIR = os.path.join(PROJECT_DIR, 'audio')
os.makedirs(AUDIO_DIR, exist_ok=True)

async def batch_crawl_text(start_num: int = 1000, end_num: int = 1050):
    """Cào nhanh toàn bộ nội dung văn bản cho các chương từ start_num đến end_num."""
    await db.init_db()
    print(f"\n============================================================", flush=True)
    print(f"📥 BƯỚC 1: CÀO NỘI DUNG VĂN BẢN (CHƯƠNG {start_num} -> {end_num})", flush=True)
    print(f"============================================================", flush=True)

    success_cnt = 0
    for num in range(start_num, end_num + 1):
        chap = await db.get_chapter(num)
        if not chap:
            print(f"[-] Chương {num} chưa có trong danh mục DB.", flush=True)
            continue

        if chap.get('content') and len(chap.get('content', '').strip()) > 100:
            print(f"[✓] Chương {num} đã có sẵn văn bản ({chap.get('word_count')} từ).", flush=True)
            success_cnt += 1
            continue

        print(f"[*] Đang cào Chương {num}: {chap.get('title')} ...", flush=True)
        data = await scraper.get_chapter_content(chap['url'])
        if data and data.get('content') and len(data['content'].strip()) > 100:
            await db.update_chapter_content(num, data['content'], data.get('word_count', 0))
            print(f"    -> Đã cào xong: {data.get('word_count')} từ.", flush=True)
            success_cnt += 1
        else:
            print(f"    [!] Thất bại khi cào chương {num}!", flush=True)
        
        await asyncio.sleep(0.5)

    print(f"\n[+] Đã có văn bản cho {success_cnt}/{end_num - start_num + 1} chương!\n", flush=True)

async def batch_convert_audio(start_num: int = 1000, end_num: int = 1050, voice: str = tts_converter.DEFAULT_VOICE):
    """Chuyển thể TTS sang Audio cho các chương đã cào."""
    await db.init_db()
    print(f"============================================================", flush=True)
    print(f"🎧 BƯỚC 2: TẠO AUDIO MP3 (CHƯƠNG {start_num} -> {end_num})", flush=True)
    print(f"   Giọng đọc: {voice}", flush=True)
    print(f"============================================================", flush=True)

    for num in range(start_num, end_num + 1):
        chap = await db.get_chapter(num)
        if not chap or not chap.get('content'):
            print(f"[-] Chương {num} chưa có nội dung văn bản, bỏ qua.", flush=True)
            continue

        audio_filename = f"chapter_{num:04d}.mp3"
        audio_path = os.path.join(AUDIO_DIR, audio_filename)
        rel_path = f"audio/{audio_filename}"

        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 10000:
            kb = os.path.getsize(audio_path) // 1024
            print(f"[✓] Chương {num} đã có sẵn file audio ({kb} KB).", flush=True)
            await db.update_audio_status(num, 'done', rel_path, voice)
            continue

        title = chap.get('title') or f"Chương {num}"
        print(f"[*] Đang tạo audio Chương {num}: {title} ...", flush=True)
        await db.update_audio_status(num, 'converting', voice=voice)

        t0 = time.time()
        ok = await tts_converter.convert_chapter_to_audio(
            text=chap['content'],
            output_path=audio_path,
            voice=voice,
            title=title
        )
        elapsed = round(time.time() - t0, 1)

        if ok and os.path.exists(audio_path) and os.path.getsize(audio_path) > 10000:
            kb = os.path.getsize(audio_path) // 1024
            print(f"    -> XONG: {audio_filename} ({kb} KB, mất {elapsed}s)!", flush=True)
            await db.update_audio_status(num, 'done', rel_path, voice)
        else:
            print(f"    [!] Thất bại tạo audio chương {num}!", flush=True)
            await db.update_audio_status(num, 'error')

        await asyncio.sleep(1)

    print(f"\n============================================================", flush=True)
    print(f"🎉 HOÀN TẤT TẤT CẢ TIẾN TRÌNH!", flush=True)
    print(f"============================================================", flush=True)

async def main():
    start = 1000
    end = 1010
    if len(sys.argv) > 1:
        start = int(sys.argv[1])
    if len(sys.argv) > 2:
        end = int(sys.argv[2])

    await batch_crawl_text(start, end)
    await batch_convert_audio(start, end)
    await scraper.close()

if __name__ == '__main__':
    asyncio.run(main())
