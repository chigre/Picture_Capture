# Platform support

Picture Capture uses one Python codebase and one uv-managed project environment across supported desktop systems. Platform launchers are intentionally thin; OCR profile selection lives in `scripts/ocr_setup.py`.

## Support matrix

| Platform | Core GUI | PaddleOCR CPU | PaddleOCR NVIDIA GPU | Notes |
| --- | --- | --- | --- | --- |
| Windows x86_64 | Supported | Supported | Supported | Automatic Compute Capability / driver / CUDA profile detection |
| Linux x86_64 | Supported | Supported | Supported | Uses the same NVIDIA recommendation logic as Windows |
| Linux arm64 | Supported | Supported | Not provided by this project | Current project GPU profiles target NVIDIA x86_64 |
| macOS arm64 (Apple Silicon) | Supported | Supported | Not supported by PaddlePaddle on macOS | CPU PaddleOCR only |
| macOS x86_64 (Intel) | Core supported | Not automatically supported | Not supported | PaddlePaddle 3.3.x official macOS wheel support is arm64 only |

“Supported” means the project has an explicit installation/runtime path and the platform contract is exercised by automated tests where a hosted runner is available. It does not imply that every third-party OCR engine or system package is bundled.

## Platform detection

The installer records:

- operating system;
- CPU architecture;
- whether the current platform/architecture has a supported PaddlePaddle CPU path;
- whether Picture Capture may offer NVIDIA GPU profiles.

On Windows/Linux x86_64, `nvidia-smi` is used to inspect GPU 0. GPU OCR is automatically recommended only when:

1. Compute Capability is greater than 7.5;
2. the NVIDIA driver reports compatibility with at least one declared CUDA profile;
3. the platform itself supports the project GPU profile.

The highest compatible declared profile is selected from CUDA 11.8, 12.6 and 12.9. A successful installation must still pass the real Paddle GPU `conv2d` smoke test.

## macOS

PaddlePaddle 3.3.x supports macOS arm64 CPU wheels and does not provide the project’s CUDA/NVIDIA path on macOS. Apple Silicon therefore receives `ocr-cpu` as the default OCR recommendation.

Intel macOS remains usable for Picture Capture core features, Tesseract and optional non-Paddle paths, but the installer does not attempt to install PaddlePaddle 3.3.x because current official macOS wheels are arm64-only.

## Linux ARM64

The PaddlePaddle CPU source contains Linux aarch64 wheels, so Picture Capture can select `ocr-cpu`. The project does not offer its NVIDIA CUDA profiles on Linux ARM64.

## Runtime portability

Machine-specific state is deliberately separated from project data:

- Paddle CPU/GPU is resolved from the current machine at runtime; legacy project `paddle_device` values are compatibility-only.
- Tesseract executable selection is stored in the current user's runtime configuration. A stale path from another OS falls back to the local PATH and common macOS/Windows locations.
- project-relative wordslist paths remain portable; a foreign absolute path falls back to a project-local `wordslist.txt` when available.
- legacy sidecars and PicDic manifests are read with a unique case-insensitive filename fallback so projects created on case-insensitive Windows filesystems can move to Linux/macOS safely.
- default UI fonts are resolved against installed fonts at render time, with Tk-native fallbacks when Windows-only fonts are unavailable.
- large windows are clamped to the usable desktop work area; macOS/Linux context menus include platform-specific secondary-click bindings.
- Windows BAT launchers use `pushd/popd` so UNC/network-share paths are valid working directories.
- source/Release OCR installer buttons are only shown through a detected checkout root; wheel/site-packages installs no longer guess a repository root.

## CI policy

Pull requests and pushes to `main` run the standard test/build job on:

- `ubuntu-latest`;
- `windows-latest`;
- `macos-latest`.

Each runner:

1. installs the locked core environment with Python 3.13;
2. imports Tkinter and reports the detected platform support contract;
3. dry-runs the `ocr-cpu` profile where Paddle CPU is supported and constructs the main Tk window plus key Toplevels;
4. runs pytest and the compatibility runner;
5. runs compileall and Ruff undefined-name checks;
6. builds the wheel.

GPU execution is not expected on GitHub-hosted CI runners. GPU correctness is therefore protected by unit tests for recommendation logic and by the real installation-time Paddle GPU smoke test on user hardware.

## Release contents

The release ZIP includes:

- `src/`;
- `scripts/`;
- Windows installers/launchers;
- Linux installers/launchers;
- macOS installers/launchers;
- locked uv metadata and documentation.

Keeping `scripts/` in the release artifact is required because all platform wrappers call the shared installer and verification scripts.
