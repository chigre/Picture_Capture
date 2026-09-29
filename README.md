# Picture Capture

Picture Capture 是一个面向**扫描版词典数字化制作、OCR 词头定位、人工校对与 PicDic/PDIC 后期制作**的桌面工具。它继承 2016 年 VB.NET 版本的核心工作流，并在 Python 版本中持续扩展多 OCR、Project Profile、结构化词头识别、跨平台运行与项目数据管理。

当前版本：**v2.14.1**  
界面：Tkinter  
环境管理：**uv + 项目专属 `.venv`**  
主要平台：**Windows / Linux / macOS**

> **v2.14.0 是相对于上一个正式 Release v2.13.2 的大幅更新版本。**  
> 原计划中的 v2.13.3 没有单独发布，其修复和后续大量功能均已并入 v2.14.0。

---

## v2.14.1 主要变化

v2.14.1 是 v2.14.0 之后的维护与工作流增强版本，重点收拢 2026-09-27 至 2026-09-29 完成的功能、界面与稳定性改进。

- 新增非破坏性【图片预处理（前置）】工作流，支持页面几何分析、透视/展平复核、批量导出以及将处理结果安全设为工作图片。
- 新增【融合画线+OCR】与【仅OCR】等路径，改进普通画线与 OCR 画线互补、局部 OCR 补字、大字头重复线抑制和 CJK/括号词头召回。
- 重点筛选校对改进为首批快速显示、后台续扫与相邻批次预取，减少大项目筛选等待。
- 颜色模式升级为【浅色 / 深色 / 跟随系统】，并在 Windows、macOS、Linux 上读取系统外观偏好。
- 主界面【四、画线 / OCR / 插图 / 校对】重新整理操作顺序；【图片预处理（前置）】默认折叠。
- 设置中心恢复每个参数下方的详细说明，同时保留右侧说明与图解；与版面尺寸相关的用户输入进一步统一为相对百分比显示。
- Project Profile 栏左线微调、词头左缘容差、普通分析左右边界和页眉横线搜索高度改为更稳定的相对单位界面。
- 【PaddleOCR缓存】改为紧凑持久化：每页只长期保存可复用 OCR/校对所需 JSON 与人工选择覆盖，不再默认重复写入多份 diagnostics/comparison/issues/engines/fusion 文本；主界面【压缩OCR缓存】可在不重新 OCR、且保留人工选择的前提下压缩旧项目缓存。
- 无 wordslist 文件时，主界面词条框使用浅灰色边框而不再全部标红；词条序号按当前页总数统一位数，并改为浅灰底黑字。
- 更新 Picture Capture 应用图标，并补强 PNG 资源和 GUI smoke 验证。

## v2.14.0 主要变化

### 1. Project Profile 与词头识别体系升级

- 【项目 Profile】成为词典级版式与词头结构配置中心，可定义页面方向、分栏、页眉页尾、词头前缀/本体/词后结构、固定入口符号和 OCR 语言规则。
- 支持 POS、词形/屈折、变体/性数、发音/音标、描述型结构等词后证据，不再依赖单一隐藏规则。
- 支持从真实扫描页采集**视觉词头标记模板**，用于圆点、方形、菱形、三角形、括号等固定符号的识别补救。
- 新增 CJK/非 CJK 语言兼容约束、大字单字视觉证据、栏左线人工微调以及 Profile 多页诊断。

### 2. OCR 画线确立为推荐默认流程

- **OCR画线是默认推荐路径**：PaddleOCR 主识别 → 可选 Tesseract 对照 → 多 OCR 融合 → 结构/视觉证据校验。
- 普通画线保留为备用路径，并重新按 2016 VB.NET `Draw_Auto` 核心流程实现。
- 自动版面参数、横线精修、动态栏左路径、词头结构和页面几何统一接入同一套运行逻辑。

### 3. 坐标、版面与 SECTION 重新统一

- 主要运行和持久化几何统一到**原图像素 X/Y**，避免窗口缩放、不同 DPI 或旧参考宽度造成坐标漂移。
- 页面级新增 **SECTION**：同一页可设置多个独立阅读区域，并统一用于 OCR、排序、校对、TXT 填充、PDIC 修复/恢复和整词条切图。
- 主界面几何参数支持 **% + px 双输入**：px 作为底层真值，百分比用于直观填写和跨尺寸理解。
- 新增四边标尺、页面特异栏几何和更明确的页眉/页尾/正文边界语义。

### 4. 校对与后期制作工作流增强

- 【词条校对】重组为显示设置、OCR 结果、词条联网核验结果、参考词表等可折叠区域。
- 重点筛选校对支持 OCR 不匹配、批次浏览、轻量首扫和直接填充 OCR 结果。
- OpenCC 简体化支持独立保存、重新简体化以及与 CC-CEDICT 的结果比较。
- 继续支持 PDIC/PPP、词条切图、插图切图、PicDic 制作、训练标记包导出和备份/恢复。

### 5. 全局深色模式与界面收口

- 应用级颜色模式支持浅色、深色与跟随系统；主界面、设置中心、词条校对、Project Profile、新旧比较和主要二级窗口统一响应。
- 扫描图夜间显示只改变预览，不修改原图、OCR 输入、PDIC/PPP、切图或导出结果。
- 设置中心、帮助中心和主界面重新整理信息架构，并改进中文/英文混排换行、高 DPI 显示与窗口工作区适配。
- v2.14.0 使用新版 Picture Capture 应用图标，并作为主窗口及 Toplevel 的统一窗口图标。

### 6. 环境中心与跨平台运行

- 新增【环境中心】，集中检查 PaddleOCR/PaddlePaddle、Google Lens、Tesseract、OpenCC、CC-CEDICT 与网络词典状态。
- OCR 安装逻辑统一到 `scripts/ocr_setup.py`，Windows、Linux、macOS 共用同一套 profile 与验证逻辑。
- Windows/Linux x86_64 可自动检测 NVIDIA GPU、Compute Capability 与驱动 CUDA 上限，并选择兼容的 `cu118 / cu126 / cu129` profile。
- CPU/GPU、Tesseract 路径、用户级 runtime 配置与项目数据解耦，项目跨机器或跨系统复制时更稳健。

### 7. 安装、CI 与 Release 安全收敛

- Windows 日常启动器不再承担安装、下载或依赖切换，只使用已准备好的项目 `.venv`。
- Release ZIP 明确包含 `scripts/`、三平台安装/启动入口、`uv.lock` 和文档。
- GitHub Actions 在 Windows、Ubuntu、macOS 上执行 pytest、GUI construction smoke、兼容性测试、compileall、Ruff 与 wheel build。
- OCR CPU profile 另有三平台真实安装与 runtime verification。
- Release 自动生成 wheel、source ZIP、用户 Release ZIP 和 `SHA256SUMS.txt`。

完整变更见 [CHANGELOG.md](CHANGELOG.md)。

---

## 主要能力

- 多栏扫描词典的项目化管理与页面浏览。
- PaddleOCR / Tesseract / Google Lens 多引擎 OCR。
- OCR 词头定位、结构证据、视觉符号模板与人工复核。
- 普通规则画线作为 OCR 不适用时的备用方案。
- Project Profile、自动版面检测、栏左微调与页面 SECTION。
- 原词条 / 简体词条双轨校对与 OpenCC。
- CC-CEDICT / 萌典 / Wiktionary / 网络搜索辅助核验。
- 外部 `wordslist.txt` 定位、填充、排序检查与新旧比较。
- PDIC / PPP、词条切图、插图切图、PicDic 与训练标记导出。
- 浅色 / 深色 / 跟随系统颜色模式、夜间扫描图预览和跨平台运行。

---

# 获取正式版本

普通用户请从 GitHub 的 [Releases 页面](https://github.com/chigre/Picture_Capture/releases/latest) 下载最新正式版本的 **Release ZIP**，完整解压后再安装和运行。

**不要使用 GitHub 自动生成的 “Source code” ZIP 代替正式 Release ZIP。** 自动生成的源码包主要供开发使用；正式 Release ZIP 才包含项目规定的发布目录结构和平台入口。

> **不要继续使用 2026-09-21 发布的 v2.13.2 Release ZIP。**  
> v2.13.2 生成于 Windows 启动/安装脚本安全收敛之前，而且没有包含此后完成的大量 v2.14.0 功能。请从 **v2.14.0** 起使用重新构建的正式 Release ZIP，并可使用同一 Release 中的 `SHA256SUMS.txt` 校验文件完整性。

---

# 安装前准备

Picture Capture 使用 [uv](https://docs.astral.sh/uv/) 管理 Python 与依赖。

- 项目要求 Python `>=3.10,<3.14`。
- 仓库的 `.python-version` 当前指定 **Python 3.13**。
- 正常使用时无需手工为本项目单独配置 Python 3.13；uv 会按项目配置准备环境。
- **需要先让系统能够找到 `uv` 命令。** 如果尚未安装，请按 uv 官方安装说明完成一次系统级安装。
- 所有 Python 依赖安装到项目自己的 `.venv`，不会使用全局 `pip` 污染系统 Python。

---

# 跨平台安装

Picture Capture 的平台入口只负责准备项目环境并调用统一 OCR 安装核心 `scripts/ocr_setup.py`。

| 平台 | 核心 GUI | PaddleOCR CPU | NVIDIA GPU | 推荐首次入口 |
| --- | --- | --- | --- | --- |
| Windows x86_64 | 支持 | 支持 | 支持；自动检测 GPU/驱动兼容性 | `install_ocr_windows.bat` |
| Linux x86_64 | 支持 | 支持 | 支持；使用同一 GPU 推荐逻辑 | `./install_ocr_linux.sh` |
| Linux arm64 | 支持 | 支持 | 不自动提供项目 GPU profile | `./install_ocr_linux.sh` |
| macOS Apple Silicon | 支持 | 支持 | PaddlePaddle 当前仅 CPU | `install_ocr_macos.command` |
| macOS Intel | 核心支持 | PaddlePaddle 3.3.x 当前无官方 x86_64 wheel | 不支持 | Core/Lens/Tesseract 路径 |

## Windows

首次安装：

```text
install_ocr_windows.bat
```

安装器会根据当前机器推荐 CPU 或 GPU OCR。对于受支持的 NVIDIA GPU，会结合 GPU 0 的 Compute Capability、驱动版本与驱动报告的 CUDA 兼容上限，从 `cu118 / cu126 / cu129` 中选择合适 profile；GPU 安装后仍会执行真实 Paddle `conv2d` 验证。

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

日常启动：

```bash
./run_linux.sh
```

Linux x86_64 可自动推荐 NVIDIA GPU OCR；Linux arm64 自动限定为 Paddle CPU。

## macOS

Apple Silicon 首次安装：

```bash
chmod +x install_ocr_macos.command run_macos.command
./install_ocr_macos.command
```

也可在 Finder 中运行 `install_ocr_macos.command`。

日常启动：

```bash
./run_macos.command
```

Apple Silicon 使用 Paddle CPU。Intel Mac 不会自动尝试安装当前没有官方 x86_64 wheel 的 PaddlePaddle 3.3.x，可使用 Core、Google Lens 或系统 Tesseract 路径。

---

# OCR profiles

| profile | Windows x64 | Linux x64 | Linux arm64 | macOS arm64 |
| --- | --- | --- | --- | --- |
| `ocr-cpu` | 支持 | 支持 | 支持 | 支持 |
| `ocr-gpu-cu118` | 支持 | 支持 | — | — |
| `ocr-gpu-cu126` | 支持 | 支持 | — | — |
| `ocr-gpu-cu129` | 支持 | 支持 | — | — |
| `lens` | 可选 | 可选 | 可选 | 可选 |
| Core only | 支持 | 支持 | 支持 | 支持 |

GPU profile 将 `paddlepaddle-gpu==3.3.0` 与对应 Paddle 官方 CUDA 索引声明在 `pyproject.toml`。Windows CUDA 12.6/12.9 profile 额外锁定项目内 cuDNN wheel并注册 DLL 搜索目录；CPU/GPU profile 互斥。

安装成功后会记录 `.picture_capture_ocr_extra`。日常启动器只运行已经准备好的环境，不会自动下载、同步或切换 OCR profile。

详细说明：

- [docs/platform-support.md](docs/platform-support.md)
- [docs/ocr-install.md](docs/ocr-install.md)

---

# 推荐使用流程

1. 从正式 Release ZIP 解压 Picture Capture，并完成当前平台首次安装。
2. 启动程序，在【项目中心】新建或打开词典项目。
3. 先进入【项目Profile】，用代表页确认页面方向、正文范围、分栏、词头结构和 OCR 语言。
4. 在少量代表页上运行【检测版面参数】和【运行OCR画线（推荐）】。
5. 检查词头、横线和 SECTION；必要时调整栏左线、固定符号模板或 OCR 结构规则。
6. 代表页稳定后，再扩展到批量 OCR / 批量画线。
7. 在【词条校对】完成原词条、简体、OCR 与参考词表核验。
8. 最后进入【后期词典制作】完成切图、PicDic、训练标记或其他导出。

【普通画线】建议只用于规则版式、历史项目或 OCR 暂不可用的场景。

---

# Tesseract

Tesseract 是系统级程序，不由 uv 管理。

Windows 可使用系统包管理器安装，例如：

```bat
winget install tesseract-ocr.tesseract
```

Linux/macOS 请使用对应系统包管理器安装 Tesseract 及所需语言数据。Picture Capture 的【环境中心】会检查当前 Tesseract 可执行程序和语言包，并给出下一步提示。

---

# CC-CEDICT

CC-CEDICT 是本地词典数据，不通过 pip / uv 安装。

Picture Capture 可使用它：

- 检查繁体或简体词条是否收录；
- 读取 CC-CEDICT 的繁体→简体对应；
- 与 OpenCC 自动简化结果比较；
- 对不一致结果提示人工复核。

安装说明见 [docs/cc-cedict-install.md](docs/cc-cedict-install.md)。

---

# 项目数据

新项目的软件数据统一保存在：

```text
<项目目录>/_PictureCapture/
```

主要结构：

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

v2.14.0 进一步把 CPU/GPU 选择、Tesseract 程序路径和用户级 runtime 配置与项目数据分离，因此词典项目在 Windows/Linux/macOS 或不同机器之间迁移时，不应再依赖旧机器的设备路径。

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

CI 当前覆盖 Windows、Ubuntu、macOS，并包含真实 Tk GUI construction smoke。OCR Platform Smoke 另外验证三平台 CPU OCR profile 的安装与 runtime。

---

# 文档索引

| 文件 | 内容 |
| --- | --- |
| [README.md](README.md) | 当前版本、安装、推荐工作流与主要能力 |
| [CHANGELOG.md](CHANGELOG.md) | 完整版本历史与 v2.14.0 详细变更 |
| [docs/usage.md](docs/usage.md) | 项目目录、画线、OCR、规则、CLI 与详细使用 |
| [docs/SETTINGS_REFERENCE.md](docs/SETTINGS_REFERENCE.md) | 设置中心参数说明 |
| [docs/FILE_FORMATS_AND_OUTPUTS.md](docs/FILE_FORMATS_AND_OUTPUTS.md) | 文件格式、sidecar 与输出说明 |
| [docs/ocr-install.md](docs/ocr-install.md) | OCR 安装、CPU/GPU profile、切换与验证 |
| [docs/platform-support.md](docs/platform-support.md) | Windows/Linux/macOS 平台支持边界 |
| [docs/cc-cedict-install.md](docs/cc-cedict-install.md) | CC-CEDICT 本地词典安装 |
| [docs/architecture.md](docs/architecture.md) | OCR / 词头管线与存储架构 |
| [docs/coordinate-system.md](docs/coordinate-system.md) | 原图像素坐标、canonical 变换与旧项目迁移 |
| [docs/legacy-function-map.md](docs/legacy-function-map.md) | 旧 VB.NET 功能到 Python 的映射 |

---

# 版本渊源

Picture Capture 根据 2016 年 VB.NET 项目 `picture_capture_V2016`（`Form1.vb`、`Form2.vb`、Designer 与 RESX 文件）重建为 Python 版本。

当前版本继续兼容主要历史工作流和数据格式（包括 `.pdic`、`.ppp`、`wordslist.txt`、`_Mysettings.ini` 等），同时以 Project Profile、OCR、结构化校对、统一坐标和 Project Storage 为新架构逐步承接旧功能。

完整版本演进见 [CHANGELOG.md](CHANGELOG.md)。
