from __future__ import annotations

import argparse
import importlib.util
from importlib import metadata
from pathlib import Path
import platform
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from picture_capture.windows_gpu_runtime import configure_windows_nvidia_dlls


def dist_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _gpu_smoke_test(paddle) -> str:
    paddle.set_device("gpu:0")
    x = paddle.ones([1, 1, 5, 5], dtype="float32")
    weight = paddle.ones([1, 1, 3, 3], dtype="float32")
    y = paddle.nn.functional.conv2d(x, weight)
    total = float(y.numpy().sum())
    return f"conv2d sum={total:.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Picture Capture optional OCR environment")
    parser.add_argument("--expect", choices=("cpu", "gpu", "lens"), default="cpu")
    parser.add_argument("--profile", default="")
    args = parser.parse_args()

    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python: {sys.version.split()[0]}")
    if args.profile:
        print(f"OCR profile: {args.profile}")

    dll_dirs = configure_windows_nvidia_dlls()
    if dll_dirs:
        print("NVIDIA DLL directories:")
        for path in dll_dirs:
            print(f"  {path}")

    errors: list[str] = []

    lens_version = dist_version("chrome-lens-py")
    lens_spec = importlib.util.find_spec("chrome_lens_py")
    if lens_version and lens_spec is not None:
        print(f"Google Lens: OK ({lens_version})")
    else:
        errors.append("Google Lens / chrome-lens-py is not available")

    if args.expect == "lens":
        if errors:
            for item in errors:
                print(f"ERROR: {item}")
            return 1
        print("Verification: OK")
        return 0

    paddleocr_version = dist_version("paddleocr")
    if paddleocr_version and importlib.util.find_spec("paddleocr") is not None:
        print(f"PaddleOCR: OK ({paddleocr_version})")
    else:
        errors.append("PaddleOCR is not available")

    cpu_version = dist_version("paddlepaddle")
    gpu_version = dist_version("paddlepaddle-gpu")
    cudnn12_version = dist_version("nvidia-cudnn-cu12")
    cudnn11_version = dist_version("nvidia-cudnn-cu11")
    if cpu_version and gpu_version:
        errors.append(f"both paddlepaddle CPU {cpu_version} and paddlepaddle-gpu {gpu_version} are installed")
    elif gpu_version:
        print(f"PaddlePaddle runtime: GPU {gpu_version}")
        if cudnn12_version:
            print(f"NVIDIA cuDNN CUDA 12 wheel: {cudnn12_version}")
        if cudnn11_version:
            print(f"NVIDIA cuDNN CUDA 11 wheel: {cudnn11_version}")
    elif cpu_version:
        print(f"PaddlePaddle runtime: CPU {cpu_version}")
    else:
        errors.append("PaddlePaddle runtime is not installed")

    try:
        import paddle  # type: ignore

        compiled_cuda = bool(paddle.device.is_compiled_with_cuda())
        print(f"Paddle CUDA build: {compiled_cuda}")
        try:
            print(f"Paddle device: {paddle.device.get_device()}")
        except Exception as exc:  # pragma: no cover - environment specific
            print(f"Paddle device query: unavailable ({exc})")

        if args.expect == "gpu" and not compiled_cuda:
            errors.append("GPU profile selected but Paddle was not compiled with CUDA")
        elif args.expect == "gpu":
            try:
                detail = _gpu_smoke_test(paddle)
                print(f"Paddle GPU/cuDNN smoke test: OK ({detail})")
            except Exception as exc:
                errors.append(
                    "GPU/cuDNN smoke test failed. Verify the NVIDIA driver and the selected "
                    f"Paddle CUDA runtime; on Windows also check cuDNN DLL discovery: {exc}"
                )
        if args.expect == "cpu" and compiled_cuda:
            errors.append("CPU profile selected but CUDA Paddle runtime is active")
    except Exception as exc:
        errors.append(f"Paddle import/runtime check failed: {exc}")

    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        return 1

    print("Verification: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
