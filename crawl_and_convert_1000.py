"""
Script cào nội dung và chuyển thể audio từ chương 1000 trở đi
"""
import asyncio
import os
import sys
import io

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

async def main(start_chap=1000, count=10):
    await db.init_db()
    
    print(f"[*] Đang đồng bộ danh sách chương từ trang 1 đến 17...", flush=True)
    all_chapters = await scraper.get_chapter_list(start_page=1, max_pages=17)
    print(f"[+] Lấy được tổng cộng {len(all_chapters)} chương!", flush=True)
    await db.upsert_chapters_bulk(all_chapters)
    
    # Lọc các chương >= start_chap
    target_chapters = [c for c in all_chapters if c['num'] >= start_chap]
    print(f"[+] Có {len(target_chapters)} chương từ chương {start_chap} trở đi (chương cao nhất: {target_chapters[-1]['num'] if target_chapters else 'None'})", flush=True)
    
    if not target_chapters:
        print("[!] Không tìm thấy chương nào thoả mãn!")
        return

    # Lấy batch cần cào
    batch = target_chapters[:count]
    print(f"\n[*] Bắt đầu xử lý {len(batch)} chương (từ {batch[0]['num']} đến {batch[-1]['num']})...\n", flush=True)

    for idx, ch in enumerate(batch):
        num = ch['num']
        title = ch.get('title', f"Chương {num}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", flush=True)
        print(f"[{idx+1}/{len(batch)}] Xử lý Chương {num}: {title}", flush=True)

        # 1. Kiểm tra hoặc cào nội dung
        db_chap = await db.get_chapter(num)
        content = db_chap.get('content') if db_chap else None
        
        if not content or len(content.strip()) < 100:
            print(f"  [1/2] Đang cào nội dung từ: {ch['url']} ...", flush=True)
            c_data = await scraper.get_chapter_content(ch['url'])
            if c_data and c_data.get('content'):
                content = c_data['content']
                await db.update_chapter_content(num, content, c_data.get('word_count', 0))
                print(f"  -> Đã cào xong: {c_data.get('word_count', 0)} chữ.", flush=True)
            else:
                print(f"  -> LỖI cào nội dung chương {num}!", flush=True)
                continue
        else:
            print(f"  [1/2] Nội dung đã có sẵn trong CSDL ({db_chap.get('word_count')} chữ).", flush=True)

        # 2. Convert TTS
        audio_filename = f"chapter_{num:04d}.mp3"
        audio_path = os.path.join(AUDIO_DIR, audio_filename)
        rel_audio_path = f"audio/{audio_filename}"

        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 10000:
            print(f"  [2/2] File audio đã tồn tại ({os.path.getsize(audio_path)//1024} KB), cập nhật trạng thái done.", flush=True)
            await db.update_audio_status(num, 'done', rel_audio_path)
            continue

        print(f"  [2/2] Đang chuyển thể TTS (Microsoft Neural vi-VN-HoaiMyNeural)...", flush=True)
        await db.update_audio_status(num, 'converting')
        
        ok = await tts_converter.convert_chapter_to_audio(
            text=content,
            output_path=audio_path,
            voice=tts_converter.DEFAULT_VOICE,
            title=title
        )

        if ok and os.path.exists(audio_path) and os.path.getsize(audio_path) > 10000:
            size_kb = os.path.getsize(audio_path) // 1024
            print(f"  -> THÀNH CÔNG! Đã tạo {audio_filename} ({size_kb} KB).", flush=True)
            await db.update_audio_status(num, 'done', rel_audio_path)
        else:
            print(f"  -> LỖI khi chuyển thể TTS cho chương {num}!", flush=True)
            await db.update_audio_status(num, 'error')

        await asyncio.sleep(0.5)

    print(f"\n[HOÀN TẤT] Đã xử lý xong batch {len(batch)} chương!", flush=True)
    await scraper.close()

if __name__ == '__main__':
    start = 1000
    cnt = 10
    if len(sys.argv) > 1:
        start = int(sys.argv[1])
    if len(sys.argv) > 2:
        cnt = int(sys.argv[2])
    asyncio.run(main(start, cnt))
