@echo off
chcp 65001 >nul
echo [TruyenAudio] Dang dung tien trinh Worker...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*worker_daemon.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo [TruyenAudio] Da dung tien trinh Worker!
timeout /t 3 >nul
