@echo off
REM AI job search + form filler. The AI picks search titles from config\profile.md, scores jobs
REM (Remote, US, Easy Apply), opens the best fit first, fills the form and STOPS at "Submit application".
REM YOU read the AI answers printed in this window, then submit (or close the form with its X to skip).
REM Double-click for up to 5 forms, or from a console: start_hybrid.bat --max-jobs 10 --min-fit 40
REM Keep the bot's Chrome window open. Press Enter here after each form for the next job.
REM NOTE: start.bat and the web control panel use the OLD bot, which no longer works with LinkedIn.
cd /d "%~dp0"
if "%~1"=="" (
    ".venv\Scripts\python.exe" hybrid_apply.py --max-jobs 5
) else (
    ".venv\Scripts\python.exe" hybrid_apply.py %*
)
echo.
pause
