from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / ".picture_capture_ocr_extra"

PROFILES = {
    "1": {"label": "CPU - PaddleOCR + Google Lens", "extra": "ocr-cpu", "expect": "cpu"},
    "2": {"label": "GPU CUDA 11.8 - PaddleOCR + Google Lens", "extra": "ocr-gpu-cu118", "expect": "gpu"},
    "3": {"label": "GPU CUDA 12.6 - PaddleOCR + Google Lens", "extra": "ocr-gpu-cu126", "expect": "gpu"},
    "4": {"label": "GPU CUDA 12.9 - PaddleOCR + Google Lens", "extra": "ocr-gpu-cu129", "expect": "gpu"},
    "5": {"label": "Google Lens only", "extra": "lens", "expect": "lens"},
    "6": {"label": "Core only - no optional OCR profile", "extra": None, "expect": None},
}


def venv_python() -> Path:
    if sys.platform.startswith("win"):
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def sync_command(profile: dict[str, str | None]) -> list[str]:
    command = ["uv", "sync", "--locked", "--no-dev"]
    extra = profile["extra"]
    if extra:
        command.extend(["--extra", extra])
    return command


def verification_command(profile: dict[str, str | None]) -> list[str]:
    extra = profile["extra"]
    expect = profile["expect"]
    if not extra or not expect:
        return []
    return [
        str(venv_python()),
        str(ROOT / "scripts" / "verify_ocr_environment.py"),
        "--expect",
        expect,
        "--profile",
        extra,
    ]


def run(command: list[str]) -> int:
    print()
    print("> " + " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return int(completed.returncode)


def show_gpu() -> None:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return
    print()
    print("Detected NVIDIA GPU / driver:")
    subprocess.run(
        [nvidia_smi, "--query-gpu=name,driver_version", "--format=csv,noheader"],
        cwd=ROOT,
        check=False,
    )


def choose_profile() -> dict[str, str | None] | None:
    print()
    print("=" * 60)
    print("Picture Capture OCR installer")
    print("=" * 60)
    show_gpu()
    print()
    print("Choose one profile:")
    for key, profile in PROFILES.items():
        print(f"  {key}. {profile['label']}")
    print()
    choice = input("Selection [1-6, Enter to cancel]: ").strip()
    if not choice:
        return None
    return PROFILES.get(choice)


def persist_profile(profile: dict[str, str | None]) -> None:
    extra = profile["extra"]
    if extra:
        MARKER.write_text(extra + "\n", encoding="utf-8")
    else:
        MARKER.unlink(missing_ok=True)


def install_profile(profile: dict[str, str | None]) -> int:
    if shutil.which("uv") is None:
        print("ERROR: uv was not found. Install uv and run this installer again.")
        return 1

    print()
    print(f"Selected: {profile['label']}")
    if run(sync_command(profile)) != 0:
        print("ERROR: uv sync failed. The saved OCR profile was not changed.")
        return 1

    verify = verification_command(profile)
    if verify and run(verify) != 0:
        print("ERROR: OCR environment verification failed. The saved OCR profile was not changed.")
        return 2

    persist_profile(profile)
    print()
    extra = profile["extra"]
    if extra:
        print(f"Installation complete. Saved OCR profile: {extra}")
    else:
        print("Core environment is ready. Optional OCR components were removed.")
    return 0


def main() -> int:
    profile = choose_profile()
    if profile is None:
        print("Cancelled.")
        return 0
    return install_profile(profile)


if __name__ == "__main__":
    raise SystemExit(main())
