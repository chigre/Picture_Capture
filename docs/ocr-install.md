# OCR 可选组件安装

Picture Capture v2.13.3 起，Windows 源码包与正式 Release **不再携带 `.bat`、`.cmd`、`.ps1`、`.vbs` 或 `.pyw` 启动/安装包装器**。这样可以直接消除批处理/脚本包装器被 Windows Defender 等安全软件启发式扫描误报的主要来源。

项目仍使用 uv 管理项目专属 `.venv`，不会把依赖安装到系统 Python。

## Windows 推荐方式

### 1. 建立核心环境

在 Picture Capture 根目录打开 Windows Terminal、PowerShell 或命令提示符：

```text
uv sync --locked --no-dev
```

该命令根据 `.python-version`、`pyproject.toml` 与 `uv.lock` 建立项目自己的 `.venv`。

### 2. 安装 / 切换 OCR profile

核心环境建立后运行：

```text
.venv\Scripts\python.exe scripts\windows_ocr_setup.py
```

安装器提供以下配置：

| 选项 | uv profile | 内容 |
| --- | --- | --- |
| CPU | `ocr-cpu` | PaddleOCR + PaddlePaddle CPU 3.3.0 + Google Lens |
| GPU CUDA 11.8 | `ocr-gpu-cu118` | PaddleOCR + PaddlePaddle GPU 3.3.0 + Google Lens |
| GPU CUDA 12.6 | `ocr-gpu-cu126` | PaddleOCR + PaddlePaddle GPU 3.3.0 + Google Lens + Windows cuDNN 9 |
| GPU CUDA 12.9 | `ocr-gpu-cu129` | PaddleOCR + PaddlePaddle GPU 3.3.0 + Google Lens + Windows cuDNN 9 |
| Lens only | `lens` | Google Lens / chrome-lens-py |
| Core only | 无 | 仅保留核心环境 |

GPU 模式下，`paddlepaddle-gpu==3.3.0` 与 CUDA 11.8 / 12.6 / 12.9 对应的 PaddlePaddle 官方索引都直接声明在 `pyproject.toml` 中。CPU/GPU profile 在 uv 中声明为互斥；安装器只执行标准的锁定同步，不手工拼接下载 URL，也不执行 `uv pip uninstall/install`。

Windows 上 Paddle 3.3.0 的 CUDA 12.6/12.9 wheel 需要 cuDNN 9 DLL，因此这两个 profile 显式加入 Windows `nvidia-cudnn-cu12`。Picture Capture 在导入 PaddleOCR 前只把 `.venv\Lib\site-packages\nvidia\*\bin` 注册到**当前 Python 进程**的 DLL 搜索路径，不修改系统 PATH。

## 启动

环境准备好后运行：

```text
.venv\Scripts\python.exe run.py
```

日常启动不会自动安装、更新或下载依赖。

## profile 持久化

安装成功后根目录会生成：

```text
.picture_capture_ocr_extra
```

文件只保存当前 profile 名，例如：

```text
ocr-gpu-cu126
```

该文件仅用于诊断和后续切换提示，已加入 `.gitignore`。

## 验证

安装器会自动运行：

```text
.venv\Scripts\python.exe scripts\verify_ocr_environment.py --expect gpu --profile <profile>
```

GPU 模式会检查：

- PaddleOCR 是否可导入；
- Google Lens / chrome-lens-py 是否可导入；
- 是否只存在一个 Paddle runtime；
- Paddle 是否为 CUDA build；
- 当前 Paddle 设备信息；
- Windows 项目内 NVIDIA DLL 目录是否可发现；
- 实际运行一次 GPU `conv2d`，确保 CUDA + cuDNN 真正可用。

## Windows 分发安全约束

仓库测试会阻止重新加入常见 Windows shell 包装器：`.bat`、`.cmd`、`.ps1`、`.vbs`、`.pyw`。正式 Release workflow 也只打包 Python 源码、文档、`scripts/` 和锁定依赖元数据，并生成 `SHA256SUMS.txt`。

这项约束针对的是**下载阶段的启发式误报面**：安装行为仍然明确可见地由用户在终端执行标准 uv 命令，而不是隐藏在可执行脚本包装器中。

## Tesseract

Tesseract 仍是系统级程序，不由 uv 管理。Windows 可使用：

```text
winget install tesseract-ocr.tesseract
```
