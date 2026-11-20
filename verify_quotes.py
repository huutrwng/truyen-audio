import sqlite3
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\Users\Admin\.gemini\antigravity\scratch\truyen-audio-server')
from tts_converter import clean_text_for_tts

conn = sqlite3.connect(r'C:\Users\Admin\.gemini\antigravity\scratch\truyen-audio-server\data\chapters.db')
c = conn.cursor()
c.execute('SELECT content FROM chapters WHERE num = 941')
raw = c.fetchone()[0]

quotes = re.findall(r'["\'“”‘’«»‹›「」『』〝〞＂＇‵′《》〈〉〔〕【】〖〗()\[\]{}]', raw)
print(f"Raw quotes in chap 941: {len(quotes)} instances, unique: {set(quotes)}")

cleaned = clean_text_for_tts(raw)
remaining = re.findall(r'["\'“”‘’«»‹›「」『』〝〞＂＇‵′《》〈〉〔〕【】〖〗()\[\]{}]', cleaned)
print(f"Remaining quotes after clean_text_for_tts: {len(remaining)}")
ngoac_kep = re.findall(r'ngoặc\s+kép', cleaned, flags=re.I)
print(f"Remaining 'ngoac kep' words: {len(ngoac_kep)}")

# Also check for any common quotes across all chapters 941-950
for num in range(941, 951):
    c.execute('SELECT content FROM chapters WHERE num = ?', (num,))
    r = c.fetchone()
    if r and r[0]:
        cl = clean_text_for_tts(r[0])
        rem = re.findall(r'["\'“”‘’«»‹›「」『』〝〞＂＇‵′《》〈〉〔〕【】〖〗()\[\]{}]', cl)
        assert len(rem) == 0, f"Chapter {num} has {len(rem)} unstripped quotes!"
print("All chapters 941-950 have ZERO quotes after cleaning!")
