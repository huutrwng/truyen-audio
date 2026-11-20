import sys
import io
from bs4 import BeautifulSoup

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

with open('xtruyen_940.html', 'r', encoding='utf-8', errors='replace') as f:
    soup = BeautifulSoup(f.read(), 'lxml')

print('Title tag:', soup.title.get_text() if soup.title else 'None')
h1 = soup.find('h1')
print('H1:', h1.get_text(strip=True) if h1 else 'None')
h2 = soup.find('h2')
print('H2:', h2.get_text(strip=True) if h2 else 'None')

for cl in ['chapter-c', 'chapter-content', 'content', 'reading-content', 'entry-content', 'text-content', 'chapter-body', 'box-chap']:
    d = soup.find('div', class_=cl) or soup.find('div', id=cl)
    if d:
        print(f'Found {cl}: length={len(d.get_text(strip=True))}')

# Print top 5 largest divs
divs = soup.find_all('div')
div_sizes = [(len(d.get_text(strip=True)), d.get('class'), d.get('id')) for d in divs]
div_sizes.sort(key=lambda x: x[0], reverse=True)
print('\nTop 5 largest divs:')
for size, cls, did in div_sizes[:5]:
    print(f'  Size: {size}, class={cls}, id={did}')
