@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM ============================================================
REM  WorkBuddy Market one-click installer (Windows 10/11)
REM
REM  Download this single file and double-click it. It will:
REM    1. make sure Python 3.10+ is available (winget fallback)
REM    2. install pipx
REM    3. pipx-install / upgrade the workbuddy-market CLI
REM    4. download the market root (source zip) to
REM       %USERPROFILE%\workbuddy-market
REM    5. run doctor, then start the interactive launcher
REM       (Enter = browse only, 2 = register into WorkBuddy)
REM
REM  Safe to re-run at any time: every step is idempotent.
REM  Optional arguments: --no-launch, --update-root [--tag vX.Y.Z] [--force]
REM  --update-root replaces the source root; ordinary runs update the CLI only.
REM
REM  Style note: this script deliberately uses goto-flow with no
REM  parenthesized blocks, because quoted parentheses such as
REM  (3,10) break cmd.exe block parsing. Do not "modernize" it.
REM ============================================================

echo.
echo ============================================
echo   WorkBuddy Market one-click installer
echo ============================================
echo.

set "ZIPURL=https://github.com/zjs105910/workbuddy-market/archive/refs/heads/main.zip"
set "DEST=%USERPROFILE%\workbuddy-market"
set "UPDATE_ROOT="
if /i "%~1"=="--update-root" set "UPDATE_ROOT=1"
set "UPDATE_FORCE="
if /i "%~2"=="--force" set "UPDATE_FORCE=--force"
if /i "%~3"=="--force" set "UPDATE_FORCE=--force"
if /i "%~4"=="--force" set "UPDATE_FORCE=--force"
set "UPDATE_TAG="
if /i "%~2"=="--tag" set "UPDATE_TAG=--tag %~3"
if /i "%~3"=="--tag" set "UPDATE_TAG=--tag %~4"
set "PYCHECK=import sys; sys.exit(0 if sys.version_info.minor>=10 and sys.version_info.major==3 else 1)"

REM ---- [1/5] Python 3.10+ ----
set "PY="
py -3 -c "%PYCHECK%" >nul 2>&1 && set "PY=py -3"
if defined PY goto py_found
python -c "%PYCHECK%" >nul 2>&1 && set "PY=python"
if defined PY goto py_found
echo [1/5] Python 3.10+ not found. Trying winget install ...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements >nul 2>&1
py -3 -c "%PYCHECK%" >nul 2>&1 && set "PY=py -3"
if defined PY goto py_found
echo.
echo [ERROR] Python 3.10+ is required but was not found.
echo   1. Install Python from https://www.python.org/downloads/
echo      and tick "Add python.exe to PATH" in the installer.
echo   2. Open a NEW terminal window, then re-run this file.
echo.
pause
exit /b 1
:py_found
echo [1/5] Python OK: !PY!

REM ---- [2/5] pipx ----
%PY% -m pipx --version >nul 2>&1
if not errorlevel 1 goto pipx_ok
echo [2/5] Installing pipx ...
%PY% -m pip install --user pipx >nul 2>&1
%PY% -m pipx --version >nul 2>&1
if errorlevel 1 goto pipx_fail
%PY% -m pipx ensurepath >nul 2>&1
goto pipx_ok
:pipx_fail
echo [ERROR] pipx installation failed. Run manually:
echo     !PY! -m pip install --user pipx
pause
exit /b 1
:pipx_ok
echo [2/5] pipx OK.

REM ---- [3/5] workbuddy-market CLI ----
echo [3/5] Installing / upgrading workbuddy-market CLI ...
%PY% -m pipx install workbuddy-market >nul 2>&1
if errorlevel 1 %PY% -m pipx upgrade workbuddy-market >nul 2>&1
set "WBMEXE=%USERPROFILE%\.local\bin\workbuddy-market.exe"
if exist "!WBMEXE!" goto cli_ok
set "WBMEXE="
echo       CLI installed, will call it as a module.
goto cli_done
:cli_ok
echo       CLI OK: !WBMEXE!
:cli_done

if defined UPDATE_ROOT if exist "%DEST%\launcher.py" goto update_root_mode
if defined UPDATE_ROOT echo [INFO] No existing market root found; falling back to first-install flow.
if defined UPDATE_ROOT set "UPDATE_ROOT="

REM ---- [4/5] market root (web UI + launcher + wizard) ----
if exist "%DEST%\launcher.py" goto dest_ok
echo [4/5] Downloading market root to %DEST% ...
REM GitHub direct is unreachable on some networks (connection reset).
REM Strategy: retry the primary URL, then fall back to the
REM api.github.com zipball endpoint (different host, often reachable
REM when github.com is not).
curl -fsSL --retry 3 --retry-delay 2 -o "%TEMP%\wbm-main.zip" "%ZIPURL%"
if errorlevel 1 (
    echo       github.com direct failed, trying api.github.com fallback ...
    curl -fsSL --retry 3 --retry-delay 2 -o "%TEMP%\wbm-main.zip" "https://api.github.com/repos/zjs105910/workbuddy-market/zipball/main"
)
if errorlevel 1 goto dl_fail
mkdir "%DEST%" 2>nul
REM Use the absolute path to Windows bsdtar: a plain `tar` may resolve to
REM Git's GNU tar, which treats "C:\..." as a remote host ("Cannot connect
REM to C:"). Also capture errorlevel before `cd` resets it.
cd /d "%DEST%"
"%SystemRoot%\System32\tar.exe" -xf "%TEMP%\wbm-main.zip" --strip-components=1
set "TARERR=%errorlevel%"
cd /d "%~dp0"
if not "%TARERR%"=="0" goto dl_fail
del "%TEMP%\wbm-main.zip" 2>nul
goto dest_ok
:dl_fail
echo [ERROR] Download or extract failed. Check your network, or do it manually:
echo     1. Download %ZIPURL%
echo     2. Extract it anywhere, double-click the extracted folder's cmd files.
pause
exit /b 1
:dest_ok
echo       Market root ready: %DEST%
if defined WBMEXE call "!WBMEXE!" root-update --check-only --market-root "%DEST%"
if not defined WBMEXE %PY% -m workbuddy_market root-update --check-only --market-root "%DEST%"
echo.
REM ---- [5/5] doctor + launch ----
echo [5/5] Health check ...
echo       ^(First run: a few lines may show X here - they resolve once
echo        the wizard initializes the config below. Not an error.^)
pushd "%DEST%"
if defined WBMEXE goto doctor_exe
%PY% -m workbuddy_market doctor
goto doctor_done
:doctor_exe
call "!WBMEXE!" doctor
:doctor_done
echo.
if /i "%~1"=="--no-launch" goto no_launch
echo Starting WorkBuddy Market ...
echo   In the first-run wizard: press Enter = browse only,  2 = register into WorkBuddy.
echo.
%PY% launcher.py
popd
echo.
echo All done. Re-run this file anytime to update the CLI; use --update-root to update the market root.
pause
exit /b 0
:no_launch
popd
echo [--no-launch] Skipping launch. Market root: %DEST%
exit /b 0

:update_root_mode
echo [4/5] Updating market root explicitly ...
echo       Current root: %DEST%
if defined WBMEXE call "!WBMEXE!" root-update --market-root "%DEST%" !UPDATE_TAG! !UPDATE_FORCE!
if not defined WBMEXE %PY% -m workbuddy_market root-update --market-root "%DEST%" !UPDATE_TAG! !UPDATE_FORCE!
set "UPDATE_EXIT=!errorlevel!"
if not "!UPDATE_EXIT!"=="0" goto update_root_failed
echo       Market root update completed.
pause
exit /b 0
:update_root_failed
echo.
echo [ERROR] Market root update failed with exit code !UPDATE_EXIT!.
echo       Follow the recovery instructions above. Do not delete any .old-* backup manually.
pause
exit /b !UPDATE_EXIT!
