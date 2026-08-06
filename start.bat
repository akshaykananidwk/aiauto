@echo off
REM AIAuto one-click start (Windows) - the ONLY file you need to run.
REM Starts Redis, backend, Chrome (ChatGPT session) and the worker,
REM verifies everything, then shows "System Ready".
REM On a central server WITHOUT Chrome, use:  start.bat --server-only
cd /d %~dp0
python scripts\start.py %*
pause
