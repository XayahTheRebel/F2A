@echo off
setlocal
cd /d "%~dp0"
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  python -m pip install pyinstaller
  if errorlevel 1 (
    echo Could not install PyInstaller.
    pause
    exit /b 1
  )
)
python -m pip install -r requirements.txt
if errorlevel 1 (
  pause
  exit /b 1
)
python -m PyInstaller --noconfirm --clean --onefile --name Frameflow --exclude-module numpy --add-data "static;static" app.py
if errorlevel 1 (
  pause
  exit /b 1
)
echo Build complete: dist\Frameflow.exe
pause
