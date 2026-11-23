@echo off
REM LinkedIn Auto Applier desktop app. Double-click to open it.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo The virtual environment is missing. Run these once:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" desktop_app.py
