@echo off
:: Render Studio launcher (Windows) — double-click to run.
:: Checks Python, installs app dependencies, starts the server and opens
:: your browser. Everything else (engine, models) is one-click inside the app.
title Render Studio
cd /d "%~dp0"

set PY=python
where python >nul 2>nul && goto :deps
where py >nul 2>nul && (set PY=py -3) && goto :deps

echo Python 3 was not found on this PC.
choice /C YN /M "Install Python 3.12 automatically now (uses winget)"
if errorlevel 2 (
    echo Opening the Python download page instead...
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo winget install failed - install Python manually from python.org and re-run.
    pause
    exit /b 1
)
echo Python installed. Please close this window and double-click the launcher again
echo so the new install is picked up.
pause
exit /b 0

:deps
echo Checking app dependencies...
%PY% -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo Dependency install failed - check your internet connection and retry.
    pause
    exit /b 1
)

echo Starting Render Studio at http://127.0.0.1:8500 (browser opens automatically)
%PY% -m backend.main
pause
