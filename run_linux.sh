#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "[Picture Capture] Project environment is not prepared."
  echo "Run ./install_ocr_linux.sh once before starting Picture Capture."
  exit 2
fi

exec ".venv/bin/python" "run.py"
