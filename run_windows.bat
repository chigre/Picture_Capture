@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Keep the console visible so startup and any security-related diagnostics
rem are observable while testing this branch.
set "PC_HOLD=pause"

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

if defined PC_OCR_EXTRA (
  echo [Picture Capture] Starting with uv project environment + OCR profile: %PC_OCR_EXTRA%
  uv run --locked --extra "%PC_OCR_EXTRA%" python run.py
) else (
  echo [Picture Capture] Starting with uv project environment...
  uv run --locked python run.py
)

set "PC_RC=%errorlevel%"
if not "%PC_RC%"=="0" (
  echo.
  echo [Picture Capture] If uv reports that its version is too old, run: uv self update
  echo [Picture Capture] To install or change OCR components, run: install_ocr_windows.bat
  %PC_HOLD%
)
exit /b %PC_RC%
