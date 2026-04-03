@echo off
chcp 65001 >nul
cd /d "%~dp0"
call venv\Scripts\activate
echo ============================================
echo   Trading Discord Bot - Starting...
echo ============================================
echo.
echo Bot will stay running. Press Ctrl+C to stop.
echo.
python start_bot.py
pause
