# Picture Capture

Picture Capture 是一个面向**多栏词典扫描页**的桌面制作与校对工具。它可以自动/半自动为词头画线，调用多引擎 OCR 识别词条，进行繁简校对、参考词表定位与词典核验，并输出 PDIC / PicDic / 训练数据。

当前版本：**v2.13.3**  
界面：Tkinter  
环境管理：**uv + 项目专属 `.venv`**

## 主要能力

- **OCR画线为推荐默认流程**：PaddleOCR 结合词头文字、位置与结构证据自动画线；`left_edge` 普通画线保留为规则版式或 OCR 暂不可用时的备用方案。
- PaddleOCR / Tesseract / Google Lens 多引擎 OCR、融合结果与人工复核。
- 校对窗口：参考词表定位、OpenCC 繁→简、简体独立编辑与保存。
- 夜间校对：全局深色模式同时调整界面与扫描图显示；仅改变预览，不改原图、OCR、PDIC/PPP 或导出结果。
- CC-CEDICT / 萌典 / Wiktionary 词条核验，并可比较 CC-CEDICT 与 OpenCC 的简体结果。
- 原词条与简体词条逐行对齐，删除与保存同步。
- 词条切图、插图多边形（PPP）、PicDic 制作、训练标注导出、PDIC 备份/恢复。
- Project Storage v2：程序数据集中保存到项目 `_PictureCapture/`，尽量保持项目根目录整洁。

## v2.13.x 的环境方式

从 v2.13.0 起，项目统一使用 [uv](https://docs.astral.sh/uv/) 管理 Python 和依赖：

- `.python-version` 固定为 **Python 3.13**；
- `uv.lock` 固定依赖版本；
- 依赖安装到项目自己的 `.venv`；
- **不会使用全局 `pip` 污染系统 Python**；
- 主程序和 OCR 附加组件使用同一个项目解释器，不再出现“程序运行在一个 Python、OCR 却装进另一个 Python”的情况。

> 项目要求 Python `>=3.10,<3.14`。正常使用不需要自己先安装 Python 3.13，uv 会按项目配置准备环境。

---

# 获取正式版本

普通用户请从 GitHub 的 [Releases 页面](https://github.com/chigre/Picture_Capture/releases/latest) 下载最新正式版本的 **Release ZIP**，完整解压后再安装和运行。不要使用 GitHub 自动生成的 “Source code” 压缩包代替正式发布包；仓库源码和 source archive 主要供开发者使用。

> **不要继续使用 2026-09-21 发布的 v2.13.2 Release ZIP。** 该旧包生成于 Windows 启动/安装脚本安全收敛之前，仍包含更复杂的批处理安装逻辑，可能触发杀毒软件启发式检测。v2.13.3 起请使用重新构建的 Release ZIP，并可用同一 Release 中的 `SHA256SUMS.txt` 校验文件完整性。

---

# 跨平台安装

Picture Capture 现在使用同一套 Python OCR 安装核心 `scripts/ocr_setup.py`，Windows、Linux 和 macOS 的平台入口只负责准备项目 `.venv` 并调用它。安装器会先识别操作系统与 CPU 架构，再决定 PaddleOCR CPU/GPU 是否属于当前平台的受支持路径。

| 平台 | 核心 GUI | PaddleOCR CPU | NVIDIA GPU | 推荐入口 |
| --- | --- | --- | --- | --- |
| Windows x86_64 | 支持 | 支持 | 支持；自动检测 Compute Capability 与驱动 CUDA 上限 | `install_ocr_windows.bat` |
| Linux x86_64 | 支持 | 支持 | 支持；与 Windows 使用同一自动推荐逻辑 | `./install_ocr_linux.sh` |
| Linux arm64 | 支持 | 支持 | 不自动提供项目 GPU profile | `./install_ocr_linux.sh` |
| macOS Apple Silicon (arm64) | 支持 | 支持 | PaddlePaddle 当前仅 CPU | `install_ocr_macos.command` |
| macOS Intel (x86_64) | 核心支持 | PaddlePaddle 3.3.x 官方 wheel 不支持 | 不支持 | Core/Lens/Tesseract 路径 |

项目要求 Python `>=3.10,<3.14`，默认由 uv 按 `.python-version` 使用 Python 3.13。所有依赖都安装在项目自己的 `.venv` 中，不污染系统 Python。

## Windows

首次安装直接运行：

```text
install_ocr_windows.bat
```

有受支持 NVIDIA GPU 时，安装器会读取 GPU 0 的 Compute Capability、驱动版本和驱动报告的 CUDA 兼容上限。只有 **Compute Capability > 7.5** 且驱动覆盖至少一个已声明 CUDA profile 时才自动推荐 GPU，并在 `cu118 / cu126 / cu129` 中选择最高兼容版本。安装后仍会执行真实 Paddle GPU `conv2d` smoke test。

日常启动：

```text
run_windows.bat
```

## Linux

首次安装：

```bash
chmod +x install_ocr_linux.sh run_linux.sh
./install_ocr_linux.sh
```

Linux x86_64 会自动检测 NVIDIA GPU 并使用与 Windows 相同的 GPU 推荐逻辑；Linux arm64 自动限定为 Paddle CPU。日常启动：

```bash
./run_linux.sh
```

## macOS

Apple Silicon（M 系列）首次运行：

```bash
chmod +x install_ocr_macos.command run_macos.command
./install_ocr_macos.command
```

也可在 Finder 中运行 `install_ocr_macos.command`。PaddlePaddle 在 macOS 当前只走 CPU，因此安装器不会显示 CUDA/GPU profile。日常启动：

```bash
./run_macos.command
```

Intel Mac 不会自动尝试安装当前没有官方 macOS x86_64 wheel 的 PaddlePaddle 3.3.x；安装器会保守推荐 Core only，同时仍可使用系统 Tesseract 或选择 Google Lens。

## OCR profile

| profile | Windows x64 | Linux x64 | Linux arm64 | macOS arm64 |
| --- | --- | --- | --- | --- |
| `ocr-cpu` | 支持 | 支持 | 支持 | 支持 |
| `ocr-gpu-cu118` | 支持 | 支持 | — | — |
| `ocr-gpu-cu126` | 支持 | 支持 | — | — |
| `ocr-gpu-cu129` | 支持 | 支持 | — | — |
| `lens` | 可选 | 可选 | 可选 | 可选 |
| Core only | 支持 | 支持 | 支持 | 支持 |

GPU profile 将 `paddlepaddle-gpu==3.3.0` 与对应 Paddle 官方 CUDA 索引声明在 `pyproject.toml` 中。Windows CUDA 12.6/12.9 profile 额外锁定项目内 cuDNN wheel并注册 DLL 搜索目录；Linux 使用 Paddle wheel 的平台依赖。CPU/GPU profile 互斥，切换时直接重新运行当前平台安装器即可。

安装成功后会记录 `.picture_capture_ocr_extra`。日常启动器只运行已经准备好的环境，不执行依赖同步、下载或 profile 切换。

详细平台边界见 [docs/platform-support.md](docs/platform-support.md)，OCR 安装与验证见 [docs/ocr-install.md](docs/ocr-install.md)。

---

# Tesseract

Tesseract 是系统级程序，不由 uv 管理。Windows 可使用：

```bat
winget install tesseract-ocr.tesseract
```

Linux/macOS 请使用系统包管理器安装 Tesseract 及所需语言数据。Picture Capture 会在运行时检查可用的 Tesseract 与语言包。

---

# CC-CEDICT

CC-CEDICT 是本地词典数据，不通过 pip / uv 安装。

Picture Capture 可使用它：

- 检查繁体或简体词条是否收录；
- 读取 CC-CEDICT 的繁体→简体对应；
- 与 OpenCC 自动简化结果进行比较；
- 对不一致结果提示人工复核。

安装说明见：

[docs/cc-cedict-install.md](docs/cc-cedict-install.md)

---

# 快速上手

1. 启动 Picture Capture。
2. 在左侧页面列表点击【打开项目目录】，选择词典项目文件夹。
3. 点击【OCR / 简化环境状态】确认 OCR、OpenCC、CC-CEDICT 等环境。
4. 在单页先校准版面参数和词头画线。
5. 确认结果后再执行批量 OCR / 批量画线。
6. 在【词条校对】中完成原词条、简体、OCR 与词典核验。

校对窗口支持：

- OpenCC 自动简化；
- 已保存简体内容保护，不会在重新打开页面时被 OpenCC 静默覆盖；
- CC-CEDICT 与 OpenCC 简体结果比较；
- 萌典 / Wiktionary / 网络搜索；
- 外部 wordslist 拼音/字母定位；
- 原词条和简体词条独立字体设置。

---

# 项目数据

新项目的软件数据统一写入：

```text
<项目目录>\_PictureCapture\
```

主要包括：

```text
_PictureCapture/
├─ project.json
├─ settings.json
├─ data/
│  ├─ PDIC/
│  ├─ PPP/
│  └─ Simplified/
├─ QT/
└─ output/
```

原始扫描图和用户自己的 `wordslist.txt` 不会被程序自动移动。

详见 [docs/usage.md](docs/usage.md)。

---

# 命令行

```bash
uv run picture-capture-cli "D:\Dictionary" inspect
uv run picture-capture-cli "D:\Dictionary" autodraw --page page001.tif
```

完整命令见 [docs/usage.md](docs/usage.md)。

---

# 开发与测试

安装开发依赖：

```bash
uv sync --group dev
```

运行测试：

```bash
uv run pytest
```

代码检查：

```bash
uv run ruff check .
```

---

# 文档索引

| 文件 | 内容 |
| --- | --- |
| [README.md](README.md) | 安装、启动与快速使用 |
| [docs/usage.md](docs/usage.md) | 项目目录、画线、OCR、规则、CLI 与详细使用 |
| [docs/ocr-install.md](docs/ocr-install.md) | Windows CPU/GPU OCR 一键安装、CUDA profile、切换与验证 |
| [docs/cc-cedict-install.md](docs/cc-cedict-install.md) | CC-CEDICT 本地词典安装 |
| [docs/architecture.md](docs/architecture.md) | OCR / 词头管线与存储架构 |
| [docs/coordinate-system.md](docs/coordinate-system.md) | 原图 / canonical / analysis / OCR band 坐标契约与旧项目迁移 |
| [docs/legacy-function-map.md](docs/legacy-function-map.md) | 旧 VB.NET 功能到 Python 的映射 |
| [CHANGELOG.md](CHANGELOG.md) | 完整版本历史 |

---

# 版本渊源

Picture Capture 是根据 2016 年 VB.NET 项目 `picture_capture_V2016`（`Form1.vb`、`Form2.vb`、Designer 与 RESX 文件）重建的 **Python 复原版**。程序保留了原工作流与主要数据格式（`.pdic`、`.ppp`、`wordslist.txt`、`_Mysettings.ini` 等），并持续增加 OCR、项目存储、繁简校对和批处理能力。

完整版本演进见 [CHANGELOG.md](CHANGELOG.md)。
