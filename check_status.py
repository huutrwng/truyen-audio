"""
check_status.py - Kiểm tra trạng thái hệ thống Truyện Audio Worker trên PC
Hỗ trợ hiển thị tiếng Việt UTF-8 chuẩn trên mọi cửa sổ cmd / terminal.
"""
import sys
import io
import os
import glob
import sqlite3
import subprocess
from pathlib import Path

if sys.platform.startswith('win'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / "data" / "chapters.db"
AUDIO_DIR = BASE_DIR / "audio"
LOG_FILE = BASE_DIR / "worker.log"

def get_worker_pids():
    try:
        cmd = [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*worker_daemon.py*' }).ProcessId"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, errors='ignore', timeout=6)
        pids = [p.strip() for p in res.stdout.strip().split() if p.strip()]
        return pids
    except Exception:
        return []

def main():
    print("=" * 62)
    print("          TRẠNG THÁI HỆ THỐNG TRUYỆN AUDIO WORKER (PC)        ")
    print("=" * 62)

    # 1. Kiểm tra tiến trình ngầm
    pids = get_worker_pids()
    if pids:
        print(f"  🟢 Tiến trình Worker : ĐANG CHẠY NGẦM 24/7 (PID: {', '.join(pids)})")
    else:
        print("  ⚪ Tiến trình Worker : ĐANG TẮT (Chạy start_worker.bat để bật)")

    # 2. Kiểm tra database
    if not DB_PATH.exists():
        print(f"  ❌ Không tìm thấy file cơ sở dữ liệu: {DB_PATH}")
    else:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            c = conn.cursor()
            
            c.execute("SELECT COUNT(*) FROM chapters")
            total = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM chapters WHERE audio_status = 'done'")
            done = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM chapters WHERE audio_status = 'converting'")
            converting = c.fetchone()[0]

            c.execute("SELECT num, title FROM chapters WHERE audio_status = 'converting' LIMIT 1")
            curr = c.fetchone()

            c.execute("SELECT num, title FROM chapters WHERE audio_status = 'done' ORDER BY num DESC LIMIT 1")
            latest_done = c.fetchone()
            conn.close()

            mp3_files = list(AUDIO_DIR.glob("chapter_*.mp3"))
            total_mb = sum(f.stat().st_size for f in mp3_files) / (1024 * 1024)

            print(f"  📚 Tổng số chương   : {total} chương")
            print(f"  ✅ Đã hoàn thành audio: {done} chương ({done/total*100:.1f}%)")
            print(f"  💾 Kho lưu trữ local : {len(mp3_files)} files ({total_mb:.2f} MB)")
            
            if curr:
                curr_num = curr[0]
                chunk_files = list(AUDIO_DIR.glob(f"_c{curr_num:04d}_*.mp3"))
                print(f"  ⚡ Đang convert dở   : Chương {curr_num}: {curr[1]}")
                if chunk_files:
                    valid_chunks = [f for f in chunk_files if f.stat().st_size > 1000]
                    print(f"     -> Tiến độ chunk  : {len(valid_chunks)}/{len(chunk_files)} đoạn âm thanh đã xong")
            else:
                print(f"  ⚡ Đang convert dở   : Không có chương nào đang chạy dở")

            if latest_done:
                print(f"  🏆 Chương mới nhất   : Chương {latest_done[0]}: {latest_done[1]}")
        except Exception as e:
            print(f"  ⚠️ Lỗi đọc database: {e}")

    # 3. Nhật ký (log) 10 dòng mới nhất
    print("-" * 62)
    print("  📋 10 DÒNG NHẬT KÝ MỚI NHẤT (worker.log):")
    print("-" * 62)
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
                lines = [line.rstrip('\r\n') for line in f if line.strip()]
            for line in lines[-10:]:
                print(f"  {line}")
        except Exception as e:
            print(f"  (Không thể đọc file log: {e})")
    else:
        print("  (Chưa có file log worker.log)")
    print("=" * 62)

if __name__ == "__main__":
    main()
