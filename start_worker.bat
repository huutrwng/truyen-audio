@echo off
chcp 65001 >nul
echo [TruyenAudio] Đang khởi động Worker chạy ngầm...
wscript.exe "%~dp0start_silent.vbs"
echo [TruyenAudio] Worker đã chạy ngầm trong background!
echo Bạn có thể kiểm tra trạng thái bằng file check_status.bat
timeout /t 3 >nul
