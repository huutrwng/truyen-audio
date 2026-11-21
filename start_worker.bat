@echo off
chcp 65001 >nul
echo [TruyenAudio] Dang khoi dong Worker chay ngam...
wscript.exe "%~dp0start_silent.vbs"
echo [TruyenAudio] Worker da duoc bat chay ngam!
timeout /t 3 >nul
