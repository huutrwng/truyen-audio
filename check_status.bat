@echo off
chcp 65001 >nul
cls
echo ============================================================
echo        TRẠNG THÁI TIẾN TRÌNH CONVERT AUDIO NGẦM
echo ============================================================
echo.
powershell -Command "python '%~dp0check_status.py'"
echo.
echo ============================================================
echo   10 DÒNG NHẬT KÝ (LOG) MỚI NHẤT:
echo ============================================================
powershell -Command "if (Test-Path '%~dp0worker.log') { Get-Content '%~dp0worker.log' -Tail 10 } else { Write-Host 'Chưa có file log worker.log' }"
echo.
pause
