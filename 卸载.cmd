@echo off
title WorkBuddy Local Plugin Market - Full Uninstall
rem ------------------------------------------------------------------
rem  One-click FULL uninstall of the WorkBuddy local plugin market.
rem
rem  Works from ANY folder on ANY drive: it does NOT delete the folder
rem  it sits in. Instead it locates every market installation via
rem    1. WorkBuddy's known_marketplaces.json (authoritative registry)
rem    2. the default install location + a root-level scan of all drives
rem  then verifies each candidate is really a market root (signature:
rem  launcher.py + market_core.py) before touching it. Candidate
rem  folders without the signature are reported and left alone.
rem
rem  Deletion goes to the Recycle Bin whenever possible (recoverable).
rem
rem  Requires uninstall_market.py next to this script.
rem  ASCII-only on purpose so no codepage can corrupt it.
rem ------------------------------------------------------------------

set "HERE=%~dp0"
if not exist "%HERE%uninstall_market.py" goto no_helper

echo.
echo   Locating WorkBuddy local plugin market installations ...
echo   (this script deletes only verified market roots, never its own
echo    folder unless that folder IS a market root)
echo.

rem -- locate a Python 3.10+ interpreter, same policy as _run.cmd --
set "PY="
where py >nul 2>nul && set "PY=py -3"
if defined PY goto run
where python >nul 2>nul && set "PY=python"
if defined PY goto run
if exist "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe" set "PY=%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if defined PY goto run

echo   [X] Python 3.10+ was not found on this machine.
echo       Install it from https://www.python.org/downloads/
echo       (tick "Add python.exe to PATH"), then run this again.
pause
exit /b 1

:run
%PY% "%HERE%uninstall_market.py" %*
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%

:no_helper
echo.
echo   [X] uninstall_market.py was not found next to this script.
echo       Keep uninstall_market.py and this .cmd in the same folder.
pause
exit /b 1
