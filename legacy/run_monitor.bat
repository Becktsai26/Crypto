@echo off
cd /d "%~dp0"
echo Starting Bybit Monitor...
call venv\Scripts\activate
python start_monitor.py
pause
