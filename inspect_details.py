import sys
import io
import re
from bs4 import BeautifulSoup

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

with open('xtruyen_raw_940.html', 'r', encoding='utf-8', errors='replace') as f:
    html = f.read()
    soup = BeautifulSoup(html, 'lxml')

d = soup.find('div', class_='reading-content')
print(f"reading-content found: {d is not None}")
if d:
    print("Children tags in reading-content:")
    tags = [child.name for child in d.find_all(recursive=False)]
    print(set(tags))

    print("\nNext siblings of reading-content:")
    for sib in d.find_next_siblings():
        print(f"<{sib.name}> class={sib.get('class')} id={sib.get('id')}")
        text_preview = sib.get_text(strip=True)[:100]
        if text_preview:
            print(f"   text: {text_preview}")

# Check for any inline script or variables
scripts = soup.find_all('script')
print(f"\nTotal script tags: {len(scripts)}")
for idx, s in enumerate(scripts):
    txt = s.get_text()
    if any(k in txt.lower() for k in ['chapter', 'content', 'ajax', 'reading', 'token', 'novel', 'truyen']):
        print(f"\n--- Script {idx} (src={s.get('src')}) ---")
        lines = [line.strip() for line in txt.split('\n') if line.strip()]
        for l in lines[:10]:
            print("  ", l[:120])
