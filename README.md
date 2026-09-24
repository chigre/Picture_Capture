# Picture Capture

Picture Capture 是一个面向**多栏词典扫描页**的桌面制作与校对工具。它可以自动/半自动为词头画线，调用多引擎 OCR 识别词条，进行繁简校对、参考词表定位与词典核验，并输出 PDIC / PicDic / 训练数据。

当前版本：**v2.13.2**  
界面：Tkinter  
环境管理：**uv + 项目专属 `.venv`**

## 主要能力

- **OCR画线为推荐默认流程**：PaddleOCR 结合词头文字、位置与结构证据自动画线；`left_edge` 普通画线保留为规则版式或 OCR 暂不可用时的备用方案。
- PaddleOCR / Tesseract / Google Lens 多引擎 OCR、融合结果与人工复核。
- 校对窗口：参考词表定位、OpenCC 繁→简、简体独立编辑与保存。
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

安装器会显示：

```text
1. CPU       - PaddleOCR + Google Lens
2. GPU cu118 - PaddleOCR + Google Lens + PaddlePaddle GPU 3.3.0
3. GPU cu126 - PaddleOCR + Google Lens + PaddlePaddle GPU 3.3.0
4. GPU cu129 - PaddleOCR + Google Lens + PaddlePaddle GPU 3.3.0
5. Lens only - Google Lens only
6. Core only - 不安装可选 OCR 组件
```

### CPU 用户

选择：

```text
1. CPU
```

安装器会一次安装：

- PaddleOCR
- PaddlePaddle CPU 3.3.0
- Google Lens (`chrome-lens-py`)

### NVIDIA GPU 用户

根据自己的环境选择：

```text
2. CUDA 11.8
3. CUDA 12.6
4. CUDA 12.9
```

安装器会自动：

1. 建立/同步项目 `.venv`；
2. 安装 PaddleOCR；
3. 安装 Google Lens；
4. 清理可能冲突的 CPU / GPU Paddle runtime；
5. 从所选 PaddlePaddle 官方 CUDA 索引安装 `paddlepaddle-gpu==3.3.0`；
6. 检查 PaddleOCR、Google Lens、CUDA build 和当前 Paddle device；
7. 保存当前 OCR profile。

**GPU 用户不需要再手工执行多条 `uv pip install` 命令。**

> GPU 用户不要再额外执行旧的 `uv sync --extra paddleocr`。该兼容 extra 是 CPU 预设，可能重新引入 CPU Paddle runtime。

### 只使用 Google Lens

选择：

```text
5. Lens only
```

### 不使用 PaddleOCR / Google Lens

选择：

```text
6. Core only
```

Picture Capture 仍然可以启动；如果系统已经安装 Tesseract，也可以继续使用 Tesseract。

## 4. 启动程序

安装完成后，日常双击：

```text
run_windows.bat
```

正常情况下它只会短暂出现一个启动窗口，然后直接用项目自己的
`.venv\Scripts\pythonw.exe` 打开 Picture Capture；程序运行期间不会保留控制台窗口。
如果 `.venv` 尚未建立或 `uv.lock` 有变化，启动窗口会暂时保持可见并先同步环境。

后台运行时的输出与错误写入：

```text
%LOCALAPPDATA%\Picture_Capture\launcher.log
```

> 该启动方式不再使用 `Picture_Capture.pyw`、`CREATE_NO_WINDOW` 或 Python 内部
> `subprocess.Popen` 重启链路。当前分支用于验证这种更简单的静默启动方式是否避免
> Windows Defender 对 GitHub Download ZIP 的误报。

安装器会在程序目录生成本机配置：

```text
.picture_capture_ocr_extra
```

例如 GPU CUDA 12.6：

```text
ocr-gpu-cu126
```

`run_windows.bat` 会自动读取该配置并使用相同的 `.venv` 启动，因此不需要每次重新选择 OCR 环境。

---

# OCR profile

v2.13.2 提供以下正式 profile：

| 安装选项 | uv profile | 内容 |
| --- | --- | --- |
| CPU | `ocr-cpu` | PaddleOCR + PaddlePaddle CPU + Google Lens |
| GPU CUDA 11.8 | `ocr-gpu-cu118` | PaddleOCR + Google Lens + cu118 GPU runtime |
| GPU CUDA 12.6 | `ocr-gpu-cu126` | PaddleOCR + Google Lens + cu126 GPU runtime |
| GPU CUDA 12.9 | `ocr-gpu-cu129` | PaddleOCR + Google Lens + cu129 GPU runtime |
| Lens only | `lens` | Google Lens |
| Core only | 无 | 仅核心依赖 |

GPU profile 中，PaddleOCR 与 Google Lens 由 uv profile 管理；`paddlepaddle-gpu` 因不同 CUDA 版本需要不同官方索引，因此由 `install_ocr_windows.bat` 根据选择自动安装。

详细说明见 [docs/ocr-install.md](docs/ocr-install.md)。

## 切换 CPU / GPU / CUDA 版本

无需删除 `.venv`。重新运行：

```text
install_ocr_windows.bat
```

然后选择新的 profile 即可。安装器会处理 Paddle CPU/GPU runtime 的切换并重新验证环境。

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
| [docs/legacy-function-map.md](docs/legacy-function-map.md) | 旧 VB.NET 功能到 Python 的映射 |
| [CHANGELOG.md](CHANGELOG.md) | 完整版本历史 |

---

# 版本渊源

Picture Capture 是根据 2016 年 VB.NET 项目 `picture_capture_V2016`（`Form1.vb`、`Form2.vb`、Designer 与 RESX 文件）重建的 **Python 复原版**。程序保留了原工作流与主要数据格式（`.pdic`、`.ppp`、`wordslist.txt`、`_Mysettings.ini` 等），并持续增加 OCR、项目存储、繁简校对和批处理能力。

完整版本演进见 [CHANGELOG.md](CHANGELOG.md)。
