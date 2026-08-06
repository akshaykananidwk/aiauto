@echo off
REM Run the AIAuto worker on the master computer (Windows).
REM Requires: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
REM           .venv\Scripts\playwright install chrome
cd /d %~dp0\..\backend
call .venv\Scripts\activate.bat
python -m worker.main
pause
