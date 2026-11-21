import sqlite3
import os
import glob
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "chapters.db"
AUDIO_DIR = BASE_DIR / "audio"

def main():
    if not DB_PATH.exists():
        print("Không tìm thấy cơ sở dữ liệu chapters.db")
        return

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM chapters")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM chapters WHERE audio_status = 'done'")
    done = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM chapters WHERE audio_status = 'converting'")
    converting = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM chapters WHERE audio_status = 'error'")
    error = c.fetchone()[0]

    c.execute("SELECT num, title FROM chapters WHERE audio_status = 'converting' LIMIT 1")
    curr = c.fetchone()

    c.execute("SELECT num, title FROM chapters WHERE audio_status = 'done' ORDER BY num DESC LIMIT 1")
    latest_done = c.fetchone()
    conn.close()

    mp3_files = glob.glob(str(AUDIO_DIR / "chapter_*.mp3"))
    total_mb = sum(os.path.getsize(f) for f in mp3_files) / (1024 * 1024)

    print(f"  • Tổng số chương truyện:   {total}")
    print(f"  • Số chương đã có audio:   {done} ({done/total*100:.1f}%)")
    print(f"  • Dung lượng audio local:  {total_mb:.2f} MB ({len(mp3_files)} files)")
    print(f"  • Chương đang convert dở:  {converting}")
    if curr:
        print(f"    -> Đang xử lý: Chương {curr[0]}: {curr[1]}")
    if latest_done:
        print(f"  • Chương mới nhất đã xong: Chương {latest_done[0]}: {latest_done[1]}")

if __name__ == "__main__":
    main()
