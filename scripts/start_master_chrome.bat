@echo off
REM Start Chrome on the master computer with remote debugging enabled.
REM Log into ChatGPT Pro ONCE in this window; the worker attaches to it
REM and reuses the login forever.
REM
REM The dedicated profile keeps the automation completely separate from
REM any personal Chrome profile on this machine.

set PROFILE_DIR=C:\aiauto-chrome

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir=%PROFILE_DIR% ^
  --no-first-run ^
  https://chatgpt.com
