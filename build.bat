@echo off
setlocal

echo === Building Sims 4 Updater ===
echo.

:: Check Python
python --version 2>NUL
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    exit /b 1
)

:: Install dependencies
echo Installing dependencies...
pip install -q customtkinter requests pywin32 pyinstaller py7zr
echo.

:: Build
echo Running PyInstaller...
pyinstaller --clean --noconfirm sims4_updater.spec

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    exit /b 1
)

echo.
echo === Build complete ===
echo Output: dist\Sims4Updater.exe
dir dist\Sims4Updater.exe

endlocal
