@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Everyday path: launch the project's own pythonw.exe directly, then let this
rem short-lived batch window close.  No CREATE_NO_WINDOW or Python subprocess
rem relaunch is used.  The console remains visible only when setup/repair is
rem needed or when an error occurs.
set "PC_HOLD=pause"
set "PC_LOCK_MARKER=.venv\.picture_capture_uv.lock"
set "PC_NEED_SYNC=0"

if not exist ".venv\Scripts\pythonw.exe" set "PC_NEED_SYNC=1"
if not exist "%PC_LOCK_MARKER%" set "PC_NEED_SYNC=1"

if "%PC_NEED_SYNC%"=="0" (
  fc /b "uv.lock" "%PC_LOCK_MARKER%" >nul 2>&1
  if errorlevel 1 set "PC_NEED_SYNC=1"
)

if "%PC_NEED_SYNC%"=="1" (
  where uv >nul 2>&1
  if errorlevel 1 (
    echo [Picture Capture] uv was not found. Install it from https://docs.astral.sh/uv/
    %PC_HOLD%
    exit /b 1
  )

  set "PC_OCR_EXTRA="
  if exist ".picture_capture_ocr_extra" (
    set /p PC_OCR_EXTRA=<".picture_capture_ocr_extra"
  )

  echo [Picture Capture] Preparing project environment...
  if defined PC_OCR_EXTRA (
    uv sync --locked --extra "%PC_OCR_EXTRA%"
  ) else (
    uv sync --locked
  )
  if errorlevel 1 goto :failed

  if not exist ".venv\Scripts\pythonw.exe" (
    echo [Picture Capture] .venv\Scripts\pythonw.exe was not created.
    goto :failed
  )
  copy /y "uv.lock" "%PC_LOCK_MARKER%" >nul
)

start "" ".venv\Scripts\pythonw.exe" "run.py"
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo [Picture Capture] Startup failed.
echo [Picture Capture] To install or change OCR components, run: install_ocr_windows.bat
echo [Picture Capture] For troubleshooting, run: uv run --locked python run.py
%PC_HOLD%
exit /b 1
