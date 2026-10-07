@echo off
title WorkBuddy Local Plugin Market - Web only (safe mode)
rem  Web-only mode: does NOT touch known_marketplaces.json at all.
call "%~dp0_run.cmd" --no-register
if errorlevel 1 (
  echo.
  echo   [X] Exited with an error. See the message above.
  echo.
  pause
)
