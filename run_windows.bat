@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Minimal foreground launcher for the project virtual environment.

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

".venv\Scripts\python.exe" "run.py"
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo [Picture Capture] Startup failed.
echo [Picture Capture] For troubleshooting, run: uv run --locked --no-dev python run.py
pause
exit /b 1
