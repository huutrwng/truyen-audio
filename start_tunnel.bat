@echo off
chcp 65001 >nul
title Ngrok Tunnel - Truyen Audio

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   🌐  NGROK TUNNEL                       ║
echo  ║   Truy cap tu dien thoai tren internet   ║
echo  ╚══════════════════════════════════════════╝
echo.
echo [*] Dang mo tunnel toi localhost:8899...
echo [*] Sau khi chay, copy URL dang: https://xxxx.ngrok-free.app
echo [*] Dan URL do vao tab "Cai dat" tren dien thoai
echo.

:: Try ngrok if installed
where ngrok >nul 2>&1
if not errorlevel 1 (
    ngrok http 8899
    goto :end
)

:: Try cloudflared if installed
where cloudflared >nul 2>&1
if not errorlevel 1 (
    cloudflared tunnel --url http://localhost:8899
    goto :end
)

echo [!] Ngrok hoac Cloudflared chua duoc cai dat.
echo.
echo Cac cach de truy cap tu xa:
echo.
echo Option 1 - Ngrok (de nhat):
echo   1. Tai ngrok tai https://ngrok.com/download
echo   2. Dang ky tai khoan mien phi
echo   3. Chay: ngrok config add-authtoken TOKEN
echo   4. Chay lai file nay
echo.
echo Option 2 - Cloudflare Tunnel (mien phi vinh vien):
echo   1. Tai: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
echo   2. Chay lai file nay
echo.
echo Option 3 - Mang noi bo (chi dung cung WiFi):
echo   Mo browser tren dien thoai va truy cap: http://[IP_MAY_TINH]:8899
echo   Tim IP may tinh: Vao cmd, chay: ipconfig
echo.

:end
pause
