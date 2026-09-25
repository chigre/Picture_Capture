#!/bin/sh
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "[Picture Capture] uv was not found."
    echo "Install uv, then run this file again."
    printf "\nPress Enter to close..."
    read _answer
    exit 1
  fi

  echo "[Picture Capture] Preparing the core environment..."
  if ! uv sync --locked --no-dev; then
    echo
    echo "[Picture Capture] Could not prepare the core environment."
    printf "\nPress Enter to close..."
    read _answer
    exit 1
  fi

".venv/bin/python" "scripts/ocr_setup.py"
status=$?
if [ "$status" -ne 0 ]; then
  printf "\nPress Enter to close..."
  read _answer
fi
exit "$status"
