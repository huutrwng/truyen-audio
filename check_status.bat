@echo off
chcp 65001 >nul
python "%~dp0check_status.py"
echo.
pause
