@echo off
chcp 65001 >nul
cd /d "%~dp0"
call venv\Scripts\activate

echo ============================================
echo   Bybit Trading System - Sync to Notion
echo ============================================
echo.

python src/main.py

echo.
echo Done.
pause
