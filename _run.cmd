@echo off
rem ------------------------------------------------------------------
rem  Shared bootstrap: locate a Python 3.10+ interpreter and run
rem  launcher.py with whatever arguments were passed in.
rem  Kept ASCII-only on purpose so no codepage can corrupt it.
rem ------------------------------------------------------------------
cd /d "%~dp0"
set "PY="

where py >nul 2>nul && set "PY=py -3"
if defined PY goto run

where python >nul 2>nul && set "PY=python"
if defined PY goto run

if exist "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe" set "PY=%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if defined PY goto run

echo.
echo   [X] Python 3.10+ was not found on this machine.
echo.
echo       Install it from https://www.python.org/downloads/
echo       (tick "Add python.exe to PATH" during setup), then run this again.
echo.
pause
exit /b 1

:run
%PY% "%~dp0launcher.py" %*
set "RC=%ERRORLEVEL%"
exit /b %RC%
