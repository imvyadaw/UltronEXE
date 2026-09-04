@echo off
echo ============================================
echo   ULTRON Setup (Windows)
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Install Python 3.10+ from https://python.org and re-run this file.
    echo IMPORTANT: check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

cd /d "%~dp0"

echo Creating virtual environment in .venv ...
python -m venv .venv

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Installing dependencies from requirements.txt ...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo ============================================
echo   Setup complete!
echo   Add your GROQ_API_KEY to a .env file first
echo   (copy .env.example to .env and edit it).
echo.
echo   Run start_ultron.bat       -^> hands-free voice mode (default)
echo   Run start_ultron_text.bat  -^> text-only mode
echo   Run start_ultron_voice.bat -^> typed input, spoken output
echo ============================================
pause
