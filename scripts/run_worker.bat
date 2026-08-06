@echo off
REM Run the AIAuto worker on the master computer (Windows).
REM Requires: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
REM           .venv\Scripts\playwright install chrome
REM The worker exits cleanly after a platform update (VERSION change) or a
REM crash — this loop restarts it on the new code. Close the window to stop.
cd /d %~dp0\..\backend
:loop
.venv\Scripts\python.exe -m worker.main
echo.
echo Worker exited — restarting in 5 seconds (close this window to stop)...
timeout /t 5 /nobreak >nul
goto loop
