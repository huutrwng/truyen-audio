@echo off
chcp 65001 >nul
echo [TruyenAudio] Đang dừng tiến trình Worker chạy ngầm...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*worker_daemon.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo [TruyenAudio] Đã dừng toàn bộ Worker!
timeout /t 3 >nul
