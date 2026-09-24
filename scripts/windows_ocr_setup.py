from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / ".picture_capture_ocr_extra"


@dataclass(frozen=True)
class OCRProfile:
    label: str
    extra: str | None
    expect: str | None


PROFILES = {
    "1": OCRProfile("CPU - PaddleOCR + Google Lens", "ocr-cpu", "cpu"),
    "2": OCRProfile("GPU CUDA 11.8 - PaddleOCR + Google Lens", "ocr-gpu-cu118", "gpu"),
    "3": OCRProfile("GPU CUDA 12.6 - PaddleOCR + Google Lens", "ocr-gpu-cu126", "gpu"),
    "4": OCRProfile("GPU CUDA 12.9 - PaddleOCR + Google Lens", "ocr-gpu-cu129", "gpu"),
    "5": OCRProfile("Google Lens only", "lens", "lens"),
    "6": OCRProfile("Core only - no optional OCR profile", None, None),
}


def venv_python() -> Path:
    if sys.platform.startswith("win"):
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def sync_command(profile: OCRProfile) -> list[str]:
    command = ["uv", "sync", "--locked", "--no-dev"]
    if profile.extra:
        command.extend(["--extra", profile.extra])
    return command


def verification_command(profile: OCRProfile) -> list[str]:
    if not profile.extra or not profile.expect:
        return []
    return [
        str(venv_python()),
        str(ROOT / "scripts" / "verify_ocr_environment.py"),
        "--expect",
        profile.expect,
        "--profile",
        profile.extra,
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


def choose_profile() -> OCRProfile | None:
    print()
    print("=" * 60)
    print("Picture Capture OCR installer")
    print("=" * 60)
    show_gpu()
    print()
    print("Choose one profile:")
    for key, profile in PROFILES.items():
        print(f"  {key}. {profile.label}")
    print()
    choice = input("Selection [1-6, Enter to cancel]: ").strip()
    if not choice:
        return None
    return PROFILES.get(choice)


def persist_profile(profile: OCRProfile) -> None:
    if profile.extra:
        MARKER.write_text(profile.extra + "\n", encoding="utf-8")
    else:
        MARKER.unlink(missing_ok=True)


def install_profile(profile: OCRProfile) -> int:
    if shutil.which("uv") is None:
        print("ERROR: uv was not found. Install it from https://docs.astral.sh/uv/")
        return 1

    print()
    print(f"Selected: {profile.label}")
    if run(sync_command(profile)) != 0:
        print("ERROR: uv sync failed. The saved OCR profile was not changed.")
        return 1

    verify = verification_command(profile)
    if verify and run(verify) != 0:
        print("ERROR: OCR environment verification failed. The saved OCR profile was not changed.")
        return 2

    persist_profile(profile)
    print()
    if profile.extra:
        print(f"Installation complete. Saved OCR profile: {profile.extra}")
    else:
        print("Core environment is ready. Optional OCR components were removed.")
    return 0


def main() -> int:
    profile = choose_profile()
    if profile is None:
        print("Cancelled.")
        return 0
    if profile not in PROFILES.values():
        print("Invalid selection.")
        return 2
    return install_profile(profile)


if __name__ == "__main__":
    raise SystemExit(main())
