@echo off
cd /d "%~dp0"
echo === Ultron EXE build ===
echo.
echo Installing build + runtime dependencies...
pip install -q pyinstaller
pip install -q -r requirements.txt
if exist requirements-windows.txt pip install -q -r requirements-windows.txt

echo.
echo Cleaning previous build...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

echo.
echo Building (this can take 10-30+ minutes the first time)...
pyinstaller build_exe.spec

echo.
if exist dist\Ultron\Ultron.exe (
    echo BUILD SUCCEEDED.
    echo Your app is in: dist\Ultron\
    echo Run it with:    dist\Ultron\Ultron.exe
    echo IMPORTANT: copy your real .env file into dist\Ultron\ before running
    echo            ^(build only ships .env.example, never your real secrets^).
) else (
    echo BUILD FAILED - scroll up for the PyInstaller error.
)
pause
