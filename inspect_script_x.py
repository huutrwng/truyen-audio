import re

with open('xtruyen_raw_940.html', 'r', encoding='utf-8') as f:
    html = f.read()

m = re.search(r'<script id="script-x">(.*?)</script>', html, re.DOTALL)
if m:
    s = m.group(1).strip()
    print("Length of script-x:", len(s))
    print("\n--- FIRST 400 CHARS ---")
    print(s[:400])
    print("\n--- LAST 400 CHARS ---")
    print(s[-400:])

# What script comes after script-x?
after_x = html[html.find('</script>', html.find('id="script-x"'))+9:html.find('</script>', html.find('id="script-x"'))+3000]
print("\n--- HTML AFTER SCRIPT-X ---")
print(after_x[:1500])
