import os
import sqlite3

PROJECT_DIR = r'C:\Users\Admin\.gemini\antigravity\scratch\truyen-audio-server'
DB_PATH = os.path.join(PROJECT_DIR, 'data', 'chapters.db')
AUDIO_DIR = os.path.join(PROJECT_DIR, 'audio')

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 1. Reset all 'queued' or 'converting' to 'none'
cur.execute("UPDATE chapters SET audio_status = 'none' WHERE audio_status IN ('queued', 'converting')")

# 2. Check all files in audio/
for f in os.listdir(AUDIO_DIR):
    if f.startswith('chapter_') and f.endswith('.mp3'):
        num_str = f[8:12]
        if num_str.isdigit():
            num = int(num_str)
            full_path = os.path.join(AUDIO_DIR, f)
            sz = os.path.getsize(full_path)
            if sz >= 5 * 1024 * 1024:
                rel_path = f"audio/{f}"
                cur.execute(
                    "UPDATE chapters SET audio_status = 'done', audio_path = ?, voice = 'vi-VN-HoaiMyNeural' WHERE num = ?",
                    (rel_path, num)
                )
            else:
                try:
                    os.remove(full_path)
                except Exception:
                    pass
                cur.execute(
                    "UPDATE chapters SET audio_status = 'none', audio_path = NULL WHERE num = ?",
                    (num,)
                )

conn.commit()

# Print stats
cur.execute("SELECT count(*) FROM chapters WHERE audio_status = 'done'")
done_cnt = cur.fetchone()[0]
print(f"Total verified audio chapters in DB: {done_cnt}")
conn.close()
