@echo off
REM One-time setup for the LinkedIn Auto Applier desktop app. Double-click it, then use start_app.bat afterwards.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" in the installer, then run this file again.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo Creating the private Python environment...
    python -m venv .venv
    if errorlevel 1 ( echo Could not create the environment. & pause & exit /b 1 )
)
echo Installing the packages (a few minutes the first time)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo The install failed. Check your internet connection and run this file again. & pause & exit /b 1 )
echo Creating your private config files...
".venv\Scripts\python.exe" init_config.py
echo.
echo Setup finished. Opening the app. Next time just double-click start_app.bat.
start "" ".venv\Scripts\pythonw.exe" desktop_app.py
