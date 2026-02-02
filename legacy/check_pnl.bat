@echo off
cd %~dp0
call venv\Scripts\activate
python manual_report.py
timeout /t 5
