@echo off
REM AIAuto one-command start (Windows). Add --with-worker on the master computer.
cd /d %~dp0
python scripts\start.py %*
pause
