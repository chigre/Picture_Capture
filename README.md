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

# Windows 推荐安装

## 1. 安装 uv

先安装 **uv >= 0.11**：

<https://docs.astral.sh/uv/getting-started/installation/>

安装后可在命令行确认：

```bat
uv --version
```

## 2. 解压 Picture Capture

将 Release ZIP 完整解压到一个普通文件夹中。不要直接在 ZIP 压缩包内运行程序。

## 3. 安装 OCR 组件

推荐直接双击：

```text
install_ocr_windows.bat
```

安装器会先自动检测 NVIDIA GPU、驱动版本以及 `nvidia-smi` 报告的最高 CUDA 兼容版本。

如果检测到可兼容的 NVIDIA GPU，会显示类似：

```text
Hardware check:
  NVIDIA GPU: GeForce RTX ...
  Driver: ...
  Driver CUDA compatibility: 12.9
  Recommended: GPU accelerated OCR (ocr-gpu-cu129)

1. GPU accelerated OCR (Recommended)
2. CPU OCR
3. Google Lens only
4. Core only
5. Advanced: choose CUDA profile manually
```

此时直接按 **Enter** 即接受 GPU 推荐。安装器会在已声明的 CUDA 11.8 / 12.6 / 12.9 profile 中，自动选择**不高于驱动兼容上限的最高版本**；普通用户不需要自己判断 CUDA profile。

如果未检测到 NVIDIA GPU、无法可靠取得 CUDA 兼容信息，或驱动兼容上限低于当前 GPU profile，则默认推荐 **CPU OCR**，同样直接按 Enter 即可。

### CPU 用户

没有可自动选择的兼容 GPU 时，直接接受 **CPU OCR (Recommended)** 即可。安装器会一次安装：

- PaddleOCR
- PaddlePaddle CPU 3.3.0
- Google Lens (`chrome-lens-py`)

### NVIDIA GPU 用户

检测成功时，推荐直接按 **Enter** 接受 GPU profile。安装器会自动：

1. 根据 NVIDIA 驱动报告的 CUDA 兼容上限选择最高兼容的已声明 GPU profile；
2. 使用所选 uv profile 同步项目 `.venv`；
3. 由 `pyproject.toml + uv.lock` 选择对应 PaddlePaddle 官方 CUDA 索引；
4. 一次性安装 PaddleOCR、Google Lens 与对应 GPU runtime；Windows CUDA 12.6/12.9 profile 还会安装项目内的 NVIDIA cuDNN wheel；
5. 在进程内自动加入项目 `.venv` 中 NVIDIA DLL 目录，无需手工修改系统 PATH；
6. 实际执行一次 GPU 卷积 smoke test，确认 CUDA + cuDNN 均可用；
7. 验证成功后保存当前 OCR profile。

**GPU 用户不需要再手工执行 `uv pip uninstall/install`，也不需要自己填写 CUDA 索引。**

只有在兼容性排查或明确知道目标 runtime 时，才需要进入 **Advanced** 手动选择 CUDA 11.8 / 12.6 / 12.9。

> GPU 用户不要再额外执行旧的 `uv sync --extra paddleocr`。该兼容 extra 是 CPU 预设，可能重新引入 CPU Paddle runtime。

### 只使用 Google Lens

在安装器中选择 **Google Lens only**。

### 不使用 PaddleOCR / Google Lens

在安装器中选择 **Core only**。Picture Capture 仍然可以启动；如果系统已经安装 Tesseract，也可以继续使用 Tesseract。

## 4. 启动程序

安装完成后，日常双击：

```text
run_windows.bat
```

Windows 启动脚本现在刻意保持为**前台、可见的最小包装器**：它直接使用项目自己的
`.venv\Scripts\python.exe` 运行 `run.py`，程序运行期间控制台窗口会保留。
这样不再使用 `start`、`pythonw.exe`、隐藏窗口或后台重启链路，减少安全软件对启动行为的启发式误判。

日常 `run_windows.bat` **不再执行任何安装、更新或联网命令**。如果 `.venv` 尚不存在，
启动器会直接提示先运行 `install_ocr_windows.bat` 并退出；不需要 PaddleOCR / Google Lens
时，在安装器中选择 **Core only** 即可建立仅含核心依赖的环境。

安装器会在程序目录生成本机配置：

```text
.picture_capture_ocr_extra
```

例如 GPU CUDA 12.6：

```text
ocr-gpu-cu126
```

该文件用于记录最近一次成功安装的 OCR profile，便于诊断和后续切换；日常 `run_windows.bat` 不再解析该文件，也不会在每次启动时重新同步依赖。

---

# OCR profile

v2.13.3 提供以下正式 profile：

| 安装选项 | uv profile | 内容 |
| --- | --- | --- |
| CPU | `ocr-cpu` | PaddleOCR + PaddlePaddle CPU + Google Lens |
| GPU CUDA 11.8 | `ocr-gpu-cu118` | PaddleOCR + Google Lens + cu118 GPU runtime |
| GPU CUDA 12.6 | `ocr-gpu-cu126` | PaddleOCR + Google Lens + cu126 GPU runtime + Windows cuDNN 9 |
| GPU CUDA 12.9 | `ocr-gpu-cu129` | PaddleOCR + Google Lens + cu129 GPU runtime + Windows cuDNN 9 |
| Lens only | `lens` | Google Lens |
| Core only | 无 | 仅核心依赖 |

GPU profile 已把 `paddlepaddle-gpu==3.3.0` 和对应 CUDA 官方索引直接声明在 `pyproject.toml` 中，并由 `uv.lock` 锁定。由于 Paddle 的 Windows CUDA wheel 不会像 Linux 一样自动声明 cuDNN pip runtime，CUDA 12.6/12.9 profile 另外锁定 Windows `nvidia-cudnn-cu12`；程序会自动把其 DLL 目录加入当前进程。安装器只负责选择 profile 并执行标准 `uv sync --locked --no-dev --extra <profile>`。

详细说明见 [docs/ocr-install.md](docs/ocr-install.md)。

## 切换 CPU / GPU / CUDA 版本

无需删除 `.venv`。重新运行：

```text
install_ocr_windows.bat
```

然后选择新的 profile 即可。uv 会按互斥 profile 同步对应 CPU/GPU runtime，并在完成后重新验证环境。

---

# Tesseract

Tesseract 是系统级程序，不由 uv 管理。

Windows 可安装：

```bat
winget install tesseract-ocr.tesseract
```

如需 `spa`、`chi_sim`、`chi_tra` 等语言，可将对应 `*.traineddata` 放入 Tesseract 的 `tessdata` 目录，并正确设置 `TESSDATA_PREFIX`。

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

# macOS / Linux

核心环境可直接运行：

```bash
uv run --locked python run.py
```

Windows 的 `install_ocr_windows.bat` 只针对 Windows；其他平台的 PaddleOCR / GPU runtime 请根据对应平台的 PaddlePaddle 安装方式配置。

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
