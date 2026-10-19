@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or later is required. Please install Python first.
  pause
  exit /b 1
)
python -c "from PIL import features; assert features.check('webp')" >nul 2>nul
if errorlevel 1 (
  echo Installing Pillow...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Installation failed. Please check your connection and try again.
    pause
    exit /b 1
  )
)
python app.py
if errorlevel 1 pause
