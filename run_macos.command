#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "[Picture Capture] Project environment is not prepared."
  echo "Run install_ocr_macos.command once before starting Picture Capture."
  printf "\nPress Enter to close..."
  read _answer
  exit 2
fi

".venv/bin/python" "run.py"
status=$?
if [ "$status" -ne 0 ]; then
  printf "\nPicture Capture exited with code %s. Press Enter to close..." "$status"
  read _answer
fi
exit "$status"
