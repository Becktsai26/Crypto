@echo off
REM 這是新架構的統一入口腳本
REM 使用方式:
REM   cli.bat sync      -> 執行一次同步
REM   cli.bat monitor   -> 執行持續監控
REM   cli.bat --help    -> 查看說明

python -m app.cmd.cli %*

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Execution failed.
    pause
)
