"""
Script đồng bộ danh sách chương và cào truyện từ chương 1000 trở đi
"""
import asyncio
import os
import sys
import io

# Fix UTF-8 encoding for Windows console
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Set working directory to project root
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import scraper
import database as db

async def run(start_chapter=1000, max_crawl=50):
    await db.init_db()
    
    print(f"[*] Bắt đầu đồng bộ danh sách chương từ metruyenchu (tất cả các trang)...", flush=True)
    all_chaps = await scraper.get_chapter_list(start_page=1, max_pages=18)
    print(f"[+] Lấy được tổng cộng {len(all_chaps)} chương từ website!", flush=True)
    
    # Lưu vào database
    await db.upsert_chapters_bulk(all_chaps)
    print(f"[+] Đã lưu thông tin {len(all_chaps)} chương vào CSDL.", flush=True)
    
    # Lấy danh sách các chương từ start_chapter trở đi
    target_chapters = [c for c in all_chaps if c['num'] >= start_chapter]
    print(f"[+] Có {len(target_chapters)} chương từ chương {start_chapter} trở đi.", flush=True)
    
    # Bắt đầu cào nội dung text cho các chương (đầu tiên làm batch max_crawl chương)
    crawl_batch = target_chapters[:max_crawl]
    print(f"[*] Đang cào nội dung cho {len(crawl_batch)} chương (từ {crawl_batch[0]['num']} đến {crawl_batch[-1]['num']})...", flush=True)
    
    success_count = 0
    for idx, ch in enumerate(crawl_batch):
        num = ch['num']
        # Kiểm tra xem chương đã có nội dung trong DB chưa
        existing = await db.get_chapter(num)
        if existing and existing.get('content') and len(existing.get('content')) > 200:
            print(f"[{idx+1}/{len(crawl_batch)}] Chương {num} đã có nội dung sẵn ({existing.get('word_count')} chữ), bỏ qua.", flush=True)
            success_count += 1
            continue

        print(f"[{idx+1}/{len(crawl_batch)}] Đang cào Chương {num} ({ch['title']})...", flush=True)
        data = await scraper.get_chapter_content(ch['url'])
        if data and data.get('content'):
            await db.update_chapter_content(num, data['content'], data.get('word_count', 0))
            print(f"    -> OK: {data.get('word_count')} chữ", flush=True)
            success_count += 1
        else:
            print(f"    -> LỖI cào nội dung chương {num}!", flush=True)
        
        # Nghỉ nhẹ giữa các request để thân thiện với web
        await asyncio.sleep(0.5)

    print(f"\n[DONE] Hoàn tất cào {success_count}/{len(crawl_batch)} chương từ chương {start_chapter}!", flush=True)
    await scraper.close()

if __name__ == '__main__':
    start_chap = 1000
    batch_size = 30  # cào trước 30 chương từ 1000
    if len(sys.argv) > 1:
        start_chap = int(sys.argv[1])
    if len(sys.argv) > 2:
        batch_size = int(sys.argv[2])
    asyncio.run(run(start_chap, batch_size))
