@echo off
title WorkBuddy Local Plugin Market - Unregister
rem  Remove this market from WorkBuddy's known_marketplaces.json.
rem  Plugin files and installed skills are left untouched.
call "%~dp0_run.cmd" --unregister
echo.
pause
