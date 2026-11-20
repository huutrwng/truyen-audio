@echo off
chcp 65001 >nul
title Truyen Audio Server

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   🎧  TRUYEN AUDIO SERVER                ║
echo  ║   Tu Tien: Khai Cuc Tu Duoc Dong         ║
echo  ╚══════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Python chua duoc cai dat!
    pause
    exit /b 1
)

:: Install deps if needed
echo [*] Kiem tra dependencies...
pip install aiosqlite -q 2>nul

:: Start server
echo [*] Khoi dong server tai http://localhost:8899
echo [*] Nhan Ctrl+C de dung
echo.
python main.py

pause
