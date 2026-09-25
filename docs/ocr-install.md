# OCR 可选组件安装

Picture Capture 使用 uv 管理项目专属 `.venv`。Windows、Linux 和 macOS 现在共享同一套 OCR 安装核心：

```text
scripts/ocr_setup.py
```

各平台入口只负责准备核心环境并调用该脚本，不再各自维护 Paddle/CUDA 安装逻辑。

## 平台入口

### Windows

```text
install_ocr_windows.bat
```

### Linux

```bash
chmod +x install_ocr_linux.sh
./install_ocr_linux.sh
```

### macOS

```bash
chmod +x install_ocr_macos.command
./install_ocr_macos.command
```

Apple Silicon 可安装 PaddleOCR CPU；macOS 当前不提供 Paddle NVIDIA/CUDA 路径。Intel macOS 不自动安装 PaddlePaddle 3.3.x，因为当前官方 macOS wheel 是 arm64。

## 平台判定

安装器先识别操作系统与 CPU 架构，再决定可显示的 profile：

| 平台 | CPU Paddle | NVIDIA GPU profile |
| --- | --- | --- |
| Windows x86_64 | 是 | 是 |
| Linux x86_64 | 是 | 是 |
| Linux arm64 | 是 | 否 |
| macOS arm64 | 是 | 否 |
| macOS x86_64 | 否 | 否 |

不受支持的平台不会“尝试后再报错”，而是在 profile 推荐阶段直接隐藏/阻止不适用的 Paddle runtime。

## NVIDIA GPU 自动推荐

Windows/Linux x86_64 会调用 `nvidia-smi`，读取：

- GPU index/name；
- driver version；
- Compute Capability；
- 驱动报告的最高 CUDA compatibility。

自动推荐 GPU 需要主 GPU（GPU 0）的 **Compute Capability > 7.5**，并且驱动兼容上限至少覆盖一个项目 GPU profile。

当前 profile：

| uv profile | Paddle runtime |
| --- | --- |
| `ocr-cpu` | `paddlepaddle==3.3.0` |
| `ocr-gpu-cu118` | `paddlepaddle-gpu==3.3.0`, CUDA 11.8 index |
| `ocr-gpu-cu126` | `paddlepaddle-gpu==3.3.0`, CUDA 12.6 index |
| `ocr-gpu-cu129` | `paddlepaddle-gpu==3.3.0`, CUDA 12.9 index |
| `lens` | Google Lens only |
| Core only | 不安装可选 OCR runtime |

若驱动报告 CUDA 12.9 或更高，推荐 `ocr-gpu-cu129`；12.6–12.8 推荐 `ocr-gpu-cu126`；11.8–12.5 推荐 `ocr-gpu-cu118`。无法可靠确认 Compute Capability/CUDA compatibility 时保守推荐 CPU。

普通用户只需按 Enter 接受推荐值。具体 CUDA profile 仅放在 Advanced 中供兼容性排查。

## macOS 与 ARM 平台

Apple Silicon macOS 以及 Linux arm64 会直接推荐 `ocr-cpu`，不会运行 NVIDIA GPU 检测。

Intel macOS 不会自动安装 PaddlePaddle 3.3.x；安装器推荐 Core only，并允许选择 Google Lens。系统 Tesseract 仍可独立使用。

## Windows cuDNN

Windows CUDA 12.6/12.9 profile 显式加入项目内 `nvidia-cudnn-cu12`。运行前：

```text
src/picture_capture/windows_gpu_runtime.py
```

会发现 `.venv\Lib\site-packages\nvidia\*\bin` 并加入当前进程 DLL 搜索路径。Linux/macOS 不执行该 Windows DLL 逻辑。

## 安装后验证

除 Core only 外，安装器会调用：

```text
scripts/verify_ocr_environment.py
```

CPU profile 会验证：

- PaddleOCR 可导入；
- Google Lens 可导入；
- 只存在一个 Paddle runtime；
- Paddle 为 CPU build。

GPU profile额外验证：

- Paddle 为 CUDA build；
- `paddle.set_device("gpu:0")` 成功；
- 实际执行 GPU `conv2d`；
- 结果可回传到 NumPy；
- Windows 下项目内 cuDNN DLL 可发现。

只有验证成功后才写入：

```text
.picture_capture_ocr_extra
```

因此“安装了 GPU wheel”不等于“GPU 已可用”；最终以真实计算 smoke test 为准。

## 日常启动

Windows：

```text
run_windows.bat
```

Linux：

```bash
./run_linux.sh
```

macOS：

```bash
./run_macos.command
```

日常启动器都不执行安装、更新或依赖同步，只运行已经准备好的项目 `.venv`。

## 手动命令

受支持平台也可直接执行 CPU OCR profile：

```bash
uv sync --locked --no-dev --extra ocr-cpu
```

GPU 用户不应再叠加旧的 `paddleocr` CPU extra，因为 CPU/GPU runtime 在 uv 中声明为互斥。

## Tesseract

Tesseract 是系统级程序，不由 uv 管理。Picture Capture 会检查其路径与语言包；没有 PaddleOCR 时仍可继续使用 Tesseract 相关功能。

更完整的平台边界见 [platform-support.md](platform-support.md)。
