@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Run setup.bat -UiOnly first to prepare the lightweight download environment.
    pause
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\download_models.py" %*
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
