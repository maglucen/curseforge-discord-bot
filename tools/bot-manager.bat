@echo off
setlocal
cd /d "%~dp0.."

set "VENV_DIR=.local\.venv"

if exist "%VENV_DIR%\Scripts\pythonw.exe" (
    start "" "%VENV_DIR%\Scripts\pythonw.exe" -m src.manager_app
    exit /b 0
)

if exist "%VENV_DIR%\Scripts\python.exe" (
    start "" "%VENV_DIR%\Scripts\python.exe" -m src.manager_app
    exit /b 0
)

pythonw --version >nul 2>&1
if not errorlevel 1 (
    start "" pythonw -m src.manager_app
    exit /b 0
)

python --version >nul 2>&1
if not errorlevel 1 (
    start "" python -m src.manager_app
    exit /b 0
)

echo Python is not installed or not available in PATH.
echo.
pause
exit /b 1
