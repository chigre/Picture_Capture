@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Foreground launcher only.
rem This file never installs, downloads, updates, or selects dependency profiles.

if not exist ".venv\Scripts\python.exe" (
  echo [Picture Capture] Project environment is not prepared.
  echo Run install_ocr_windows.bat once before starting Picture Capture.
  echo Choose "Core only" there if you do not need optional OCR components.
  pause
  exit /b 2
)

".venv\Scripts\python.exe" "run.py"
set "PC_EXIT=%ERRORLEVEL%"
if not "%PC_EXIT%"=="0" (
  echo.
  echo [Picture Capture] Startup failed with exit code %PC_EXIT%.
  pause
)
exit /b %PC_EXIT%
