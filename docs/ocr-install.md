# OCR 可选组件安装

Picture Capture v2.13.2 起，Windows 提供 `install_ocr_windows.bat`，用于统一管理 PaddleOCR、PaddlePaddle CPU/GPU runtime 与 Google Lens。项目继续使用 uv 管理 `.venv`，不会把依赖安装到系统 Python。

## Windows 推荐方式

在程序根目录双击或从命令行运行：

```bat
install_ocr_windows.bat
```

安装器提供以下配置：

| 选项 | uv profile | 内容 |
| --- | --- | --- |
| CPU | `ocr-cpu` | PaddleOCR + PaddlePaddle CPU 3.3.0 + Google Lens |
| GPU CUDA 11.8 | `ocr-gpu-cu118` | PaddleOCR + PaddlePaddle GPU 3.3.0 + Google Lens |
| GPU CUDA 12.6 | `ocr-gpu-cu126` | PaddleOCR + PaddlePaddle GPU 3.3.0 + Google Lens |
| GPU CUDA 12.9 | `ocr-gpu-cu129` | PaddleOCR + PaddlePaddle GPU 3.3.0 + Google Lens |
| Lens only | `lens` | Google Lens / chrome-lens-py |
| Core only | 无 | 删除可选 OCR profile，仅保留核心环境 |

GPU 模式下，`paddlepaddle-gpu==3.3.0` 与 CUDA 11.8 / 12.6 / 12.9 对应的 PaddlePaddle 官方索引都直接声明在 `pyproject.toml` 中。CPU/GPU profile 在 uv 中声明为互斥，安装器只执行标准的锁定同步，不再手工卸载 runtime、拼接下载 URL 或运行 `uv pip install`。

## profile 持久化

安装成功后，根目录会生成：

```text
.picture_capture_ocr_extra
```

文件只保存当前 profile 名，例如：

```text
ocr-gpu-cu126
```

该文件记录最近一次成功安装的 profile，主要用于诊断和切换提示。日常 `run_windows.bat` 不再读取它，也不会在每次启动时重新同步环境；启动脚本只直接运行已经准备好的项目 `.venv`。该 profile 文件属于本机环境设置，已加入 `.gitignore`。

## 为什么 GPU runtime 由安装器处理

PaddlePaddle GPU 的 wheel 使用 CUDA 专用索引。项目通过 uv 的 extra-specific source 配置，让 `ocr-gpu-cu118`、`ocr-gpu-cu126`、`ocr-gpu-cu129` 各自绑定对应官方索引，并将 CPU/GPU runtime profile 声明为互斥。

因此 PaddleOCR、Google Lens 和 Paddle runtime 都由同一份 `pyproject.toml + uv.lock` 管理，不再需要安装器对环境做额外的 pip 式修改。

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
- 当前 Paddle 设备信息。

也可在软件内点击【OCR / 简化环境状态】再次确认。

## 切换 CUDA 配置

直接重新运行 `install_ocr_windows.bat` 并选择新的 CUDA profile 即可。uv 会按所选互斥 profile 同步环境、移除不属于该 profile 的旧 runtime，再安装锁定的目标 runtime；验证成功后才更新 `.picture_capture_ocr_extra`。

不建议同时手工选择多个 GPU profile，也不要在 GPU 环境中叠加旧的 `paddleocr` CPU extra。

## Windows BAT 的安全收敛

两个 Windows BAT 都只保留最小包装逻辑：

- `run_windows.bat` 以前台 `python.exe` 直接运行主程序，不使用 `start`、`pythonw.exe`、隐藏窗口或后台重启。
- `install_ocr_windows.bat` 只负责确保核心 `.venv` 存在并调用 `scripts/windows_ocr_setup.py`；BAT 本身不包含 GPU 下载索引、包卸载、动态安装命令或交互式 profile 解析。

这种结构让批处理文件本身保持简单、可审计，同时把依赖选择交给 uv 的声明式配置。

## Tesseract

Tesseract 仍是系统级程序，不由 uv 管理。Windows 可使用：

```bat
winget install tesseract-ocr.tesseract
```
