@echo off
REM scripts\setup.bat - thin wrapper so `scripts\setup.bat` works on
REM Windows the same way `scripts/setup.sh` does on Linux/macOS.
REM All real logic lives in scripts\setup.py (idempotent, safe to re-run).

setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=python"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set "PY_CMD=py"
    ) else (
        echo Python was not found on PATH. Install Python 3 and try again.
        exit /b 1
    )
)

"%PY_CMD%" "%SCRIPT_DIR%setup.py" --root "%ROOT_DIR%" %*
exit /b %ERRORLEVEL%
