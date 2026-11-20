"""
Đồng bộ các chương từ trang 10 đến trang 17 (chương 890 đến 1473+)
"""
import urllib.request
import json
import re
import time
import sqlite3
import os
import sys
import io

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_DIR, 'data', 'chapters.db')

BASE_URL = "https://metruyenchu.com.vn"
BOOK_ID = 62237

def sync_remaining_pages():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    
    total_added = 0
    # Quét từ trang 10 đến 17
    for p in range(10, 18):
        url = f"{BASE_URL}/get/listchap/{BOOK_ID}?page={p}"
        print(f"[*] Đang lấy danh sách trang {p}...", flush=True)
        
        success = False
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': f"{BASE_URL}/tu-tien-khai-cuc-tu-duoc-dong-bat-dau"
                })
                with urllib.request.urlopen(req, timeout=25) as r:
                    data = json.loads(r.read().decode('utf-8', errors='ignore'))
                    html = data.get('data', '')
                    
                    # Tìm tất cả link chương: /chuong- hoặc /chuong-chuong-
                    matches = re.findall(r'<a\s+href=[\'"]([^\'"]+)[\'"]>([^<]+)</a>', html)
                    added_this_page = 0
                    for href, title in matches:
                        m = re.search(r'/chuong(?:-chuong)?-(\d+)', href)
                        if m:
                            num = int(m.group(1))
                            full_url = BASE_URL + href if href.startswith('/') else href
                            slug = href.lstrip('/')
                            title = title.strip()
                            cur.execute("""
                                INSERT INTO chapters (num, title, url, slug)
                                VALUES (?, ?, ?, ?)
                                ON CONFLICT(num) DO UPDATE SET
                                    title=excluded.title,
                                    url=excluded.url,
                                    slug=excluded.slug,
                                    updated_at=CURRENT_TIMESTAMP
                            """, (num, title, full_url, slug))
                            added_this_page += 1
                    
                    con.commit()
                    print(f"  -> Trang {p}: đã nạp {added_this_page} chương.", flush=True)
                    total_added += added_this_page
                    success = True
                    break
            except Exception as e:
                print(f"  -> Thử lại trang {p} lần {attempt+1} do lỗi: {e}", flush=True)
                time.sleep(2)
        
        if not success:
            print(f"  -> Bỏ qua trang {p} sau 4 lần thất bại.", flush=True)
        time.sleep(1)

    cur.execute("SELECT COUNT(*), MIN(num), MAX(num) FROM chapters")
    stats = cur.fetchone()
    print(f"\n[+] Tổng kết CSDL: {stats[0]} chương (từ chương {stats[1]} đến {stats[2]}).", flush=True)
    con.close()

if __name__ == '__main__':
    sync_remaining_pages()
