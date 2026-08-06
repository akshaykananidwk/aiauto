@echo off
REM AIAuto one-command setup (Windows)
cd /d %~dp0
python scripts\setup.py %*
pause
