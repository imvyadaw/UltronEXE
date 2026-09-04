@echo off
setlocal enabledelayedexpansion
title ULTRON Quick Start
color 0B

echo ============================================
echo   ULTRON - One-Click Setup
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo.
    echo Install Python 3.10 or 3.11 from https://python.org
    echo IMPORTANT: tick "Add Python to PATH" during install, then re-run this file.
    pause
    exit /b 1
)

cd /d "%~dp0"

if not exist ".venv" (
    echo [1/5] Creating virtual environment...
    python -m venv .venv
) else (
    echo [1/5] Virtual environment already exists, skipping.
)

echo [2/5] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [3/5] Installing dependencies (this can take a few minutes)...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if exist "requirements-windows.txt" (
    pip install -r requirements-windows.txt
)
echo   (If a package failed above, ULTRON can usually still run --text mode.
echo    Optional voice/vision packages are not required for basic use.)

echo [4/5] Checking configuration...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo   Created .env from .env.example
    ) else (
        echo. > .env
        echo   Created empty .env
    )
)

findstr /C:"GROQ_API_KEY=" .env >nul
if errorlevel 1 (
    echo GROQ_API_KEY=>> .env
)

for /f "tokens=2 delims==" %%A in ('findstr /B "GROQ_API_KEY=" .env') do set EXISTING_KEY=%%A

if "!EXISTING_KEY!"=="" (
    echo.
    echo   ULTRON needs a free Groq API key to think and respond.
    echo   Get one at: https://console.groq.com  (sign up, then "API Keys")
    echo.
    set /p USERKEY="  Paste your GROQ_API_KEY here (or press Enter to skip for now): "
    if not "!USERKEY!"=="" (
        powershell -Command "(Get-Content .env) -replace '^GROQ_API_KEY=.*', 'GROQ_API_KEY=!USERKEY!' | Set-Content .env"
        echo   Saved.
    ) else (
        echo   Skipped - remember to edit .env and add GROQ_API_KEY before running ULTRON.
    )
) else (
    echo   GROQ_API_KEY already set in .env, skipping.
)

echo [5/5] Setup complete!
echo.
echo ============================================
echo   Next steps:
echo     run_text.bat   -^> safest first test (typed input, typed reply)
echo     run_voice.bat  -^> typed input, spoken output
echo     start_ultron.bat -^> full hands-free voice mode
echo ============================================
echo.
set /p LAUNCH="Launch text mode now? (y/n): "
if /i "!LAUNCH!"=="y" (
    python main.py --text
)
pause
