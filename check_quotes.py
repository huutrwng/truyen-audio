import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect(r'C:\Users\Admin\.gemini\antigravity\scratch\truyen-audio-server\data\chapters.db')
cur = conn.cursor()

# Check literal "ngoặc kép"
cur.execute("SELECT num, title FROM chapters WHERE content LIKE '%ngoặc kép%' LIMIT 5")
rows = cur.fetchall()
print(f"Chapters with literal 'ngoặc kép': {len(rows)}")
for r in rows:
    print(f"Chap {r[0]}: {r[1]}")

# Check chapter 935, 936 content around quotes
cur.execute("SELECT content FROM chapters WHERE num = 935")
content_935 = cur.fetchone()[0]

# Look for quotes or special quote characters
quote_chars = set()
for ch in content_935:
    if ch in ['"', "'", '“', '”', '‘', '’', '«', '»', '「', '」', '『', '』', '〝', '〞', '＂']:
        quote_chars.add(ch)

print(f"Quote characters found in chapter 935: {[c for c in quote_chars]}")

# Print sample dialogue lines in chapter 935
print("\nSample dialogue lines in chapter 935:")
lines = [l.strip() for l in content_935.split('\n') if l.strip()]
for l in lines[:10]:
    if any(q in l for q in ['"', '“', '”']):
        print(l)
