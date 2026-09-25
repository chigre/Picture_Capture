from __future__ import annotations

import subprocess
import tkinter

from ocr_setup import platform_support


def main() -> int:
    support = platform_support()
    print(f"Platform support: {support}")
    print(f"Tkinter: {tkinter.TkVersion}")

    if support.get("paddle_cpu"):
        command = ["uv", "sync", "--locked", "--dry-run", "--no-dev", "--extra", "ocr-cpu"]
        print("> " + " ".join(command))
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            return int(completed.returncode)
    else:
        print("Paddle CPU profile dry-run skipped: no supported Paddle wheel for this platform/architecture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
