"""
Tự động chạy Cloudflare Tunnel, bóc tách URL HTTPS công khai cho 4G và ghi ra public_url.txt.
"""
import os
import sys
import re
import time
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUDFLARED_EXE = os.path.join(PROJECT_DIR, 'cloudflared.exe')
URL_FILE = os.path.join(PROJECT_DIR, 'public_url.txt')

def run_tunnel():
    print("[*] Khởi động Cloudflare Tunnel cho http://localhost:8899 ...")
    cmd = [CLOUDFLARED_EXE, 'tunnel', '--url', 'http://localhost:8899']
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding='utf-8',
        errors='replace',
        bufsize=1
    )

    url_found = False
    for line in iter(proc.stdout.readline, ''):
        print(line, end='', flush=True)
        if not url_found:
            m = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
            if m:
                url = m.group(0)
                url_found = True
                with open(URL_FILE, 'w', encoding='utf-8') as f:
                    f.write(url)
                print(f"\n============================================================")
                print(f"🎉 LINK TRUY CẬP 4G BẤT KỲ ĐÂU: {url}")
                print(f"============================================================\n", flush=True)

    proc.wait()

if __name__ == '__main__':
    while True:
        try:
            run_tunnel()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[!] Lỗi tunnel: {e}, khởi động lại sau 5s...")
            time.sleep(5)
