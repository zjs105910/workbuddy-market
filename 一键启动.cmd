@echo off
title WorkBuddy Local Plugin Market
rem  One-click startup: package -> self-check -> register -> open web UI.
call "%~dp0_run.cmd"
if errorlevel 1 (
  echo.
  echo   [X] Startup failed. See the message above.
  echo.
  pause
)
