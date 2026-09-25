from __future__ import annotations

from pathlib import Path
import csv
import io
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / ".picture_capture_ocr_extra"
PADDLE_MIN_COMPUTE_CAPABILITY = (7, 5)

CPU_PROFILE = {"label": "CPU - PaddleOCR + Google Lens", "extra": "ocr-cpu", "expect": "cpu"}
LENS_PROFILE = {"label": "Google Lens only", "extra": "lens", "expect": "lens"}
CORE_PROFILE = {"label": "Core only - no optional OCR profile", "extra": None, "expect": None}
GPU_PROFILES = (
    {"label": "GPU CUDA 12.9 - PaddleOCR + Google Lens", "extra": "ocr-gpu-cu129", "expect": "gpu", "cuda": (12, 9)},
    {"label": "GPU CUDA 12.6 - PaddleOCR + Google Lens", "extra": "ocr-gpu-cu126", "expect": "gpu", "cuda": (12, 6)},
    {"label": "GPU CUDA 11.8 - PaddleOCR + Google Lens", "extra": "ocr-gpu-cu118", "expect": "gpu", "cuda": (11, 8)},
)


# Backward-compatible profile mapping used by existing tests and external callers.
# The interactive installer no longer exposes these numeric keys directly.
PROFILES = {
    "1": CPU_PROFILE,
    "2": GPU_PROFILES[2],
    "3": GPU_PROFILES[1],
    "4": GPU_PROFILES[0],
    "5": LENS_PROFILE,
    "6": CORE_PROFILE,
}


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


def parse_compute_capability(text: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d+)\.(\d+)\s*", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def parse_gpu_query_rows(text: str, *, with_compute_cap: bool) -> list[dict[str, object]]:
    gpus: list[dict[str, object]] = []
    for row in csv.reader(io.StringIO(text)):
        if not row or not any(part.strip() for part in row):
            continue
        parts = [part.strip().strip('"') for part in row]
        expected = 4 if with_compute_cap else 3
        if len(parts) < expected:
            continue
        index, name, driver = parts[:3]
        compute_cap = parse_compute_capability(parts[3]) if with_compute_cap else None
        gpus.append({
            "index": index,
            "name": name,
            "driver": driver,
            "compute_cap": compute_cap,
        })
    return gpus


def primary_gpu(gpu_info: dict[str, object] | None) -> dict[str, object] | None:
    if not gpu_info:
        return None
    gpus = gpu_info.get("gpus")
    if not isinstance(gpus, list):
        return None
    for item in gpus:
        if isinstance(item, dict) and str(item.get("index", "")).strip() == "0":
            return item
    for item in gpus:
        if isinstance(item, dict):
            return item
    return None


def detect_nvidia_gpu() -> dict[str, object] | None:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None

    query = subprocess.run(
        [
            nvidia_smi,
            "--query-gpu=index,name,driver_version,compute_cap",
            "--format=csv,noheader,nounits",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
    )
    gpus = parse_gpu_query_rows(query.stdout, with_compute_cap=True) if query.returncode == 0 else []

    capability_query_ok = query.returncode == 0 and bool(gpus)
    if not capability_query_ok:
        basic_query = subprocess.run(
            [nvidia_smi, "--query-gpu=index,name,driver_version", "--format=csv,noheader,nounits"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
        )
        gpus = parse_gpu_query_rows(basic_query.stdout, with_compute_cap=False)
        query_ok = basic_query.returncode == 0 and bool(gpus)
    else:
        query_ok = True

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
        "query_ok": query_ok,
        "capability_query_ok": capability_query_ok,
        "details_ok": details.returncode == 0,
    }


def recommended_profile(gpu_info: dict[str, object] | None) -> dict[str, object]:
    gpu = primary_gpu(gpu_info)
    if gpu is None:
        return CPU_PROFILE

    compute_cap = gpu.get("compute_cap")
    if not isinstance(compute_cap, tuple) or len(compute_cap) != 2:
        return CPU_PROFILE
    if compute_cap <= PADDLE_MIN_COMPUTE_CAPABILITY:
        return CPU_PROFILE

    cuda = gpu_info.get("cuda") if gpu_info else None
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
                index = item.get("index") or "?"
                name = item.get("name") or "NVIDIA GPU"
                driver = item.get("driver") or "unknown"
                compute_cap = item.get("compute_cap")
                print(f"  NVIDIA GPU {index}: {name}")
                print(f"  Driver: {driver}")
                if isinstance(compute_cap, tuple) and len(compute_cap) == 2:
                    print(f"  Compute Capability: {compute_cap[0]}.{compute_cap[1]}")
                else:
                    print("  Compute Capability: could not determine")
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
        gpu = primary_gpu(gpu_info)
        compute_cap = gpu.get("compute_cap") if gpu else None
        if not isinstance(compute_cap, tuple):
            print(
                "  GPU Compute Capability could not be verified. "
                "Automatic GPU recommendation requires PaddlePaddle's documented capability > 7.5."
            )
        elif compute_cap <= PADDLE_MIN_COMPUTE_CAPABILITY:
            print(
                f"  GPU Compute Capability {compute_cap[0]}.{compute_cap[1]} does not satisfy "
                "PaddlePaddle's documented requirement > 7.5."
            )
        else:
            print("  A compatible CUDA profile could not be selected automatically from the current driver.")


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
