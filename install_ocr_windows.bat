@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem This file is intentionally a thin wrapper.
rem Package selection and validation live in scripts\windows_ocr_setup.py.

if not exist ".venv\Scripts\python.exe" (
  where uv >nul 2>&1
  if errorlevel 1 (
    echo [Picture Capture] uv was not found.
    echo Install uv, then run this file again.
    pause
    exit /b 1
  )

  echo [Picture Capture] Preparing the core environment...
  uv sync --locked --no-dev
  if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" "scripts\windows_ocr_setup.py"
set "PC_EXIT=%ERRORLEVEL%"
if not "%PC_EXIT%"=="0" pause
exit /b %PC_EXIT%

:failed
echo.
echo [Picture Capture] Could not prepare the core environment.
pause
exit /b 1
