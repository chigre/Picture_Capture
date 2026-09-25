from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / ".picture_capture_ocr_extra"

CPU_PROFILE = {"label": "CPU - PaddleOCR + Google Lens", "extra": "ocr-cpu", "expect": "cpu"}
LENS_PROFILE = {"label": "Google Lens only", "extra": "lens", "expect": "lens"}
CORE_PROFILE = {"label": "Core only - no optional OCR profile", "extra": None, "expect": None}
GPU_PROFILES = (
    {"label": "GPU CUDA 12.9 - PaddleOCR + Google Lens", "extra": "ocr-gpu-cu129", "expect": "gpu", "cuda": (12, 9)},
    {"label": "GPU CUDA 12.6 - PaddleOCR + Google Lens", "extra": "ocr-gpu-cu126", "expect": "gpu", "cuda": (12, 6)},
    {"label": "GPU CUDA 11.8 - PaddleOCR + Google Lens", "extra": "ocr-gpu-cu118", "expect": "gpu", "cuda": (11, 8)},
)


def venv_python() -> Path:
    if sys.platform.startswith("win"):
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def sync_command(profile: dict[str, object]) -> list[str]:
    command = ["uv", "sync", "--locked", "--no-dev"]
    extra = profile["extra"]
    if extra:
        command.extend(["--extra", str(extra)])
    return command


def verification_command(profile: dict[str, object]) -> list[str]:
    extra = profile["extra"]
    expect = profile["expect"]
    if not extra or not expect:
        return []
    return [
        str(venv_python()),
        str(ROOT / "scripts" / "verify_ocr_environment.py"),
        "--expect",
        str(expect),
        "--profile",
        str(extra),
    ]


def run(command: list[str]) -> int:
    print()
    print("> " + " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return int(completed.returncode)


def parse_cuda_version(text: str) -> tuple[int, int] | None:
    match = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def detect_nvidia_gpu() -> dict[str, object] | None:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None

    query = subprocess.run(
        [nvidia_smi, "--query-gpu=name,driver_version", "--format=csv,noheader"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
    )
    rows = [line.strip() for line in query.stdout.splitlines() if line.strip()]
    gpus: list[dict[str, str]] = []
    for row in rows:
        name, separator, driver = row.rpartition(",")
        if separator:
            gpus.append({"name": name.strip(), "driver": driver.strip()})
        else:
            gpus.append({"name": row, "driver": ""})

    details = subprocess.run(
        [nvidia_smi],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
    )
    cuda = parse_cuda_version(details.stdout + "\n" + details.stderr)

    return {
        "gpus": gpus,
        "cuda": cuda,
        "query_ok": query.returncode == 0,
        "details_ok": details.returncode == 0,
    }


def recommended_profile(gpu_info: dict[str, object] | None) -> dict[str, object]:
    if not gpu_info:
        return CPU_PROFILE

    cuda = gpu_info.get("cuda")
    if not isinstance(cuda, tuple) or len(cuda) != 2:
        return CPU_PROFILE

    for profile in GPU_PROFILES:
        minimum = profile["cuda"]
        if isinstance(minimum, tuple) and cuda >= minimum:
            return profile
    return CPU_PROFILE


def show_hardware_recommendation(gpu_info: dict[str, object] | None, profile: dict[str, object]) -> None:
    print()
    print("Hardware check:")
    if not gpu_info:
        print("  NVIDIA GPU: not detected via nvidia-smi")
        print("  Recommended: CPU OCR")
        return

    gpus = gpu_info.get("gpus")
    if isinstance(gpus, list) and gpus:
        for item in gpus:
            if isinstance(item, dict):
                name = item.get("name") or "NVIDIA GPU"
                driver = item.get("driver") or "unknown"
                print(f"  NVIDIA GPU: {name}")
                print(f"  Driver: {driver}")
    else:
        print("  NVIDIA GPU: nvidia-smi detected, GPU details unavailable")

    cuda = gpu_info.get("cuda")
    if isinstance(cuda, tuple) and len(cuda) == 2:
        print(f"  Driver CUDA compatibility: {cuda[0]}.{cuda[1]}")
    else:
        print("  Driver CUDA compatibility: could not determine")

    if profile.get("expect") == "gpu":
        print(f"  Recommended: GPU accelerated OCR ({profile['extra']})")
        print("  PaddleOCR will use the supported NVIDIA GPU path; installation is verified by a real GPU test.")
    else:
        print("  Recommended: CPU OCR")
        print("  A usable NVIDIA CUDA profile could not be selected automatically.")


def choose_advanced_gpu_profile() -> dict[str, object] | None:
    print()
    print("Advanced GPU profiles:")
    for index, profile in enumerate(GPU_PROFILES, start=1):
        cuda = profile["cuda"]
        print(f"  {index}. CUDA {cuda[0]}.{cuda[1]} ({profile['extra']})")
    print("  Enter. Back")
    choice = input("Advanced selection [1-3]: ").strip()
    if not choice:
        return None
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(GPU_PROFILES):
            return GPU_PROFILES[index]
    print("Invalid selection.")
    return None


def choose_profile() -> dict[str, object] | None:
    print()
    print("=" * 60)
    print("Picture Capture OCR installer")
    print("=" * 60)

    gpu_info = detect_nvidia_gpu()
    recommendation = recommended_profile(gpu_info)
    show_hardware_recommendation(gpu_info, recommendation)

    print()
    print("Choose one profile:")
    if recommendation.get("expect") == "gpu":
        print(f"  1. GPU accelerated OCR (Recommended: {recommendation['extra']})")
        print("  2. CPU OCR")
        print("  3. Google Lens only")
        print("  4. Core only")
        print("  5. Advanced: choose CUDA profile manually")
        print()
        choice = input("Selection [Enter=Recommended, 1-5]: ").strip()
        if choice in {"", "1"}:
            return recommendation
        if choice == "2":
            return CPU_PROFILE
        if choice == "3":
            return LENS_PROFILE
        if choice == "4":
            return CORE_PROFILE
        if choice == "5":
            return choose_advanced_gpu_profile()
    else:
        print("  1. CPU OCR (Recommended)")
        print("  2. Google Lens only")
        print("  3. Core only")
        print("  4. Advanced: choose CUDA profile manually")
        print()
        choice = input("Selection [Enter=Recommended, 1-4]: ").strip()
        if choice in {"", "1"}:
            return CPU_PROFILE
        if choice == "2":
            return LENS_PROFILE
        if choice == "3":
            return CORE_PROFILE
        if choice == "4":
            return choose_advanced_gpu_profile()

    print("Invalid selection.")
    return None


def persist_profile(profile: dict[str, object]) -> None:
    extra = profile["extra"]
    if extra:
        MARKER.write_text(str(extra) + "\n", encoding="utf-8")
    else:
        MARKER.unlink(missing_ok=True)


def install_profile(profile: dict[str, object]) -> int:
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
        if profile.get("expect") == "gpu":
            print("Re-run the installer and choose CPU OCR if the GPU profile is not compatible with this machine.")
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
