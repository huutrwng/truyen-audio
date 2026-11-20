import asyncio
import edge_tts
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

test_cases = [
    ('Standard quote', '"Ngươi là ai?"'),
    ('Left right curly quotes', '“Ngươi là ai?”'),
    ('Single quotes', "'Ngươi là ai?'"),
    ('Chinese quotes', '「Ngươi là ai?」'),
    ('Fullwidth quote', '＂Ngươi là ai?＂'),
    ('Quote with space', '" Ngươi là ai? "'),
    ('Standalone quote', 'Hắn nói: " Đúng vậy."'),
    ('Double quote with space before dot', 'Ta không biết. "'),
    ('Only quote', '"'),
    ('Escaped quote', '\\"'),
    ('Quote at end of line', 'Một hai ba. "\n\n" Bốn năm sáu.')
]

async def inspect_boundaries(label, text):
    c = edge_tts.Communicate(text, 'vi-VN-HoaiMyNeural', boundary='WordBoundary')
    spoken_words = []
    try:
        async for msg in c.stream():
            if msg['type'] == 'WordBoundary':
                spoken_words.append(msg['text'])
        print(f"\n[{label}] Input: {repr(text)}", flush=True)
        print(f"Spoken words: {' | '.join(spoken_words)}", flush=True)
        if any('ngoặc' in w.lower() or 'kép' in w.lower() for w in spoken_words):
            print("🚨 FOUND 'NGOẶC KÉP' SPOKEN HERE! 🚨", flush=True)
    except Exception as e:
        print(f"[{label}] Error: {e}", flush=True)

async def main():
    for label, text in test_cases:
        await inspect_boundaries(label, text)
        await asyncio.sleep(1.0)

asyncio.run(main())
