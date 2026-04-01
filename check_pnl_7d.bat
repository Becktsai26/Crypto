@echo off
cd %~dp0
call venv\Scripts\activate
python manual_report.py --days 7
timeout /t 5
