# 使用与参考

本文件收录 Picture Capture 的长期参考说明：项目目录、坐标约定、画线方式、OCR 词头识别、规则、命令行与测试。安装与运行见 [README.md](../README.md)，版本演进见 [CHANGELOG.md](../CHANGELOG.md)。

## 项目目录约定

v2.12.0 起，新建项目的数据统一写入项目下的 `_PictureCapture/`，项目根目录只保留用户原始资料：

```text
项目目录/
├─ 0001.png / 0002.png / ...       # 用户原始扫描图
├─ wordslist.txt                    # 用户参考词表（如有）
└─ _PictureCapture/                 # 软件数据唯一根目录
   ├─ project.json                  # 项目标识与存储格式版本
   ├─ settings.json                 # 项目参数
   ├─ dictionary_profile.json
   ├─ rules/                        # 替换/词头过滤规则
   ├─ data/
   │  ├─ PDIC/
   │  ├─ PPP/
   │  ├─ Simplified/                 # 校对界面可编辑简化词条
   │  └─ PageSections/               # 特殊页面 SECTION canonical-V 边界
   ├─ QT/                           # OCR、切图、PicDic、CropPlan 等
   └─ output/                       # 训练包、PDIC备份、PicDic索引等
```

复制整个项目目录时，项目参数与处理数据会随 `_PictureCapture` 一起带走。

旧项目仍可直接打开并按历史布局读取；首次打开会询问是否安全整理（复制 → 校验 → 发布 → 清理旧软件文件）：

```text
词典项目/
├── page001.tif
├── page001.pdic
├── page001.ppp
├── wordslist.txt
├── _Replace.txt
├── _Mysettings.ini
├── picture_capture_settings.json
├── dictionary_profile.json（可选项目覆盖；未提供时使用内置配置）
└── QT/
    ├── page001.OCRed
    ├── _SpecialPages.txt
    ├── _file_log.txt
    ├── PaddleOCR/
    │   ├── page001.json
    │   ├── page001_ocr_diagnostics.txt
    │   ├── page001_ocr_comparison.txt
    │   ├── page001_ocr_engines.tsv
    │   ├── page001_fusion.tsv
    │   ├── page001_issues.tsv
    │   ├── page001_manual_selection.json
    │   └── _quality_summary.tsv
    ├── PSW/
    └── PWW/
```

项目只要求扫描图片；其他文件均为可选或由程序生成。打开旧目录后，建议先在一页上校准“分栏、栏宽、栏间隔、起始点 Y、正文缩进、字高”，确认智能画线正确后再执行批量操作。

### 跨平台运行时配置

项目文件只保存可迁移的词典/版面/OCR语义参数。机器相关状态独立保存：Paddle CPU/GPU 由当前机器自动解析，Tesseract 可执行程序由【环境中心】保存到用户级 runtime 设置。外部 wordslist 如果仍指向另一操作系统的绝对路径，程序会优先回退到项目内同名 `wordslist.txt`；旧 Windows 项目中的 PDIC/PPP/PWWords 文件名在 Linux/macOS 上按唯一的大小写不敏感匹配兼容读取。

### 坐标体系

Picture Capture 的用户设置和持久化文件统一使用 **原图像素 X/Y**。完整契约见 [coordinate-system.md](coordinate-system.md)。

- 原点在扫描原图左上角，X 向右、Y 向下。
- PDIC、PPP、人工标注、OCR 最终词头、切图框和训练导出都使用原图 X/Y。
- 项目版式参数（第一栏 X、正文起始/结束 Y、栏宽、栏间距、行高等）直接保存原图像素，不再绑定参考页宽度。
- OCR/画线中的像素距离参数（栏左容差、候选带余量、横线安全距离等）也是原图像素；例如 34 始终是 34 px，不会因页面宽度从 1400 变为 4200 而变成 102 px。
- Profile 中的页眉/页尾/页边百分比是规则，不是第二套坐标；应用到具体页后解析成该页原图 X/Y 边界。
- 镜像、RTL、竖排、analysis 缩图和 OCR band 只允许作为内部临时计算；结果离开内部函数前必须换回原图 X/Y，不能写入项目设置。
- 旧项目中的显示宽度坐标或 `geometry_reference_width` 仅用于一次性迁移，迁移后不再参与运行。

Ctrl＋滚轮只改变查看倍率，不改变任何设置值或 PDIC/PPP 坐标。项目转交时，坐标含义只由原始扫描图决定，与窗口大小、显示器分辨率无关。

### 特殊页面：多个 SECTION

少数词典页面会在同一页内上下分成一个或多个独立阅读区域。每个 SECTION 仍使用项目原有栏数，但阅读顺序必须先读完 SECTION 1 的全部栏，再进入 SECTION 2。主界面【六、页面列表】中有常驻 `Section` 列：

- `0` 表示普通页面，不启用页面级 SECTION；此时切图使用【设置中心 → 切图设置】中的一般页上下边界；
- `1–10` 表示显式 SECTION 数量；双击 `Section` 单元格即可修改；
- `Section=1` 可作为单个特殊页面的可拖动上/下边界，直接接管该页词条切图与插图切图的有效范围，替代旧版【特殊页面覆盖】手工输入；
- 保存为 `1–10` 后会进入该页 SECTION 边界编辑，拖动蓝色虚线上下边界；再次双击同一 `Section` 单元格结束编辑；
- `Section≥2` 时，各 SECTION 之间允许保留空白；空白不会参与词条新增、阅读排序或整词条切图；
- 阅读顺序统一为 `SECTION 1 / 栏1 → 栏2 → … → SECTION 2 / 栏1 → 栏2 → …`；
- 边界保存为当前页 **canonical full-resolution V**，位于 `_PictureCapture/data/PageSections/<page>.json`；旧项目使用 `QT/PageSections/<page>.json`；
- PDIC 仍只保存词条与 source XY，不新增 SECTION 字段；把 `Section` 改回 `0` 即删除 sidecar 并恢复普通页面行为。


### 推荐：优先使用 OCR画线

第一次使用建议先完成【项目 Profile】和【检测版面参数】，然后在 1–3 张典型页直接试【运行OCR画线（推荐）】。OCR画线是当前默认主流程；不要一开始就修改高级阈值。

- `paddleocr`：对应“运行OCR画线（推荐）”。它同时利用词头文字、位置、字号/粗体、词性和特殊符号等结构证据，并直接生成词头文字与坐标，适合绝大多数实际词典项目。主界面默认“使用有效缓存”，只有图像/模型发生变化或明确需要重跑时才选“重新OCR”。
- `left_edge`：对应“运行普通画线（备用）”。它不识别文字，只依据栏左几何、墨迹和正文缩进判断；主要用于词头始终紧贴栏左、正文缩进高度稳定的简单版式，或 OCR 环境暂不可用时。OCR 可用时，不建议把普通画线作为默认起点。

v2.4 已移除 `projection` / `hybrid` 及投影空白高度、投影阈值系数、自适应阈值块、自适应阈值C。旧项目若保存了这两种检测方式，载入时自动回退到 `left_edge`。

### 倾斜和局部变形跟踪

“跟随词头列倾斜/变形”默认关闭；只有扫描页确实存在明显倾斜、弯曲或栏左跟踪偏差时再开启。算法在每栏预设起点左右的有限走廊中工作，不分析整页内容；每个纵向分块估计一次文字左边缘，再限制异常跳变并连接成分段路径。

- “栏左跟随搜索范围”：按当前页当前栏的实际栏宽计算，默认 **5% 单栏宽**。
- “栏左跟随分块高度”：按当前页正文有效高度计算，默认 **3% 正文高度**。
- “栏左最大局部斜率”：相邻分块最大横向变化 = 分块高度 × 该百分比，默认 **8% 分块高度**。

如果页面完全规整，或自动路径明显受到装饰线影响，可在页面列表上方关闭该选项框，恢复固定竖直检测带。

版面行为中的【使用自动版面参数】在新项目中默认开启；默认只自动更新【正文起始Y】和【首栏X】，其余字段保持项目基准值。开启后，每一页执行普通画线前都会先检测本页版面；需要自动更新的字段（分栏数、正文起始Y、首栏X、单栏宽、栏间空、单行高、行间空）统一在【设置中心 → 普通画线 → 版面行为】勾选，页面之间不会互相继承检测结果。【跟随词头列倾斜和局部变形】仍可独立按需开启。普通画线不再使用旧【手动分栏 / 手动Y】执行模式。

## OCR

### 环境中心

首次使用或 OCR/简化功能异常时，先打开【环境中心】。该窗口集中显示 PaddleOCR/PaddlePaddle、Google Lens、Tesseract、OpenCC、CC-CEDICT 与网络词典状态，并提供下一步操作：

- PaddleOCR / Google Lens：启动当前平台 OCR 安装器或进入 OCR 设置；
- Tesseract：自动检测程序路径与当前项目所需语言包，可选择可执行程序，并给出当前平台安装/语言包命令；
- OpenCC：作为核心依赖由 uv 管理，异常时给出核心环境修复命令；
- CC-CEDICT：可直接选择已下载的 ZIP/GZ/TXT/U8 安装或打开官方下载页；
- 诊断信息可一键复制，便于提交安装问题。

环境中心不会静默调用系统包管理器安装 Tesseract；系统级修改始终由用户明确执行。
 工作流

```text
页面/分栏
   ├─ PaddleOCR ───┐
   ├─ Tesseract ───┤
   └─ Google Lens ─┤（按设置关闭/诊断/冲突调用/全页）
                 ↓
       OCR line normalizer
                 ↓
 Dictionary Profile + Grammar Parser
lemma / variant / plural / POS / usage / definition
                 ↓
      SequenceMatcher + 阅读轴 V 对齐
                 ↓
       Multi-OCR Arbitration
                 ↓
  confidence / visual / alphabetical sanity
                 ↓
        Final Entries + Issues
             ↙           ↘
        PDIC/画线      OCR冲突复核
```

主图右侧会为每一个**栏左 OCR 候选行**显示复选框：自动识别漏掉的 lemma 可直接勾选进入最终结果，误选可取消。人工选择保存在页面独立 sidecar 中，后续重新运行 parser/OCR 时优先于自动决策。

### PaddleOCR 词头识别

OCR词头识别阶段仍只截取各栏左侧候选带；只有用户主动点击“检测版面”时才对整页运行 detection-only 文本框检测。候选带随“倾斜/变形”路径变化并被拉直，因此即使词头列呈斜线或缓慢弯曲，OCR 仍接收到近似竖直的窄图。OCR box 本身属于候选带局部坐标；程序随后显式换算为 canonical U/V 和原图 source X/Y，最终 `.pdic` 只保存原图像素坐标。

【设置中心】中按任务调整：

- `PaddleOCR 语言/设备/模型版本`：留空语言时自动把 Tesseract 语言代码映射为 PaddleOCR 代码。
- `AI 候选带宽度/左侧余量/左缘容差`：控制送入模型的栏左区域以及词头允许偏离左缘的范围。
- `AI 候选置信度`：在同一印刷行的 OCR 片段合并以后再过滤；底层 OCR 会保留较低置信度片段，避免粗体、音节分隔词头先被模型丢弃。
- `AI 同行合并Y比`：控制同一印刷行中多个 OCR 框的合并容差。
- `AI 字高比/粗体比/行前空白比/最低候选分`：作为词性结构之外的辅助证据。
- `AI 词头提取正则`：作用于合并后的 OCR 行开头；第一个捕获组作为原始 lemma。默认支持前/后置连字符、Unicode 字母、撇号和 `a·ga·rrón` 一类音节分隔形式，并兼容 OCR 把分隔点识别成 `.`, `:`, `+`, `-`。它只负责“抽出合法词形”，最终是否接受还要结合位置、POS/变形/符号、视觉分数和 Profile；捕获组写得过宽会把 POS/正文吞进 lemma，过窄则会直接漏词。
- `AI 词性提示正则/词性搜索字符数`：在词头后的短距离内寻找 `s.m.`、`s.f.`、`adj.`、`v.`、`v.prnl.` 等标签，把 POS 当作强结构证据；不负责提取 lemma。注意：主程序加载 Dictionary Profile 后，实际 POS 正则通常由 Profile 的 `pos_labels` 生成，此设置主要作为兼容/fallback；当前项目要增删词性缩写优先改 Profile grammar。
- `AI去除词头音节分隔点`：输出 lemma 时删除音节分隔符；真正的单个词内连字符原则上保留。
- `AI自动忽略页眉横线以上`：在页面顶部搜索长横线，自动排除 running header；可调搜索高度、横线墨迹比例和横线后余量。
- `AI候选必须有词性/变形/词条符号`：默认开启，以抑制正文缩进行被误判为新词条。像 `(pl. agitaciones)` 这样的变形提示即使词性被 OCR 截断，也可作为强结构证据。
- `AI 特殊符号正则`：只在 OCR 行首寻找“可作为新词条起始证据”的项目符号；命中只是辅助证据，不会无条件接受该行。词条内部结构的 `■`、`□`、`||`、`~`、`→` 等应由 Dictionary Profile 单独处理，不要混进这个正则，否则正文行可能获得错误的新词条证据。
- `Paddle检测同时运行Tesseract对照`：对相同的拉直候选带额外运行 Tesseract，仅用于第二意见和诊断；沿用“OCR语言”；Tesseract 程序路径由【环境中心】按当前机器管理，不随项目迁移。
- `Tesseract结果可补漏Paddle词头`：开启后，只允许具有明确 POS/变形/描述词等结构证据的 Tesseract 候选补入 Paddle 漏线；建议先开启“对照”观察几页，再决定是否启用补漏。
- `Tesseract 对照 PSM`：默认 `6`，适合候选带这类单栏连续文本。

v1.5.9 起，词头结构解析会在正则之后再做一层语法校正：旧/自定义正则即使把 `lemma, da` 的逗号误吞进 lemma，也会自动把逗号归还给性别变体/POS 解析；长词头若把 POS 挤到紧邻下一印刷行，也可逻辑回接而不改变首行画线 Y。还支持 `s.amb.`、`pron.indef.`、`Contracción de` 和部分 `||` 平行表达结构，并把 `Pron. [..]` 视为发音说明以避免假词头。

每页的原始识别框、同行合并结果、`raw_headword`、`corrected_headword`、`ocr_repairs`、标准化后的 `normalized_headword`、词性/变形提示、候选得分和明确 `reject_reason` 保存在 `QT/PaddleOCR/页名.json`。v1.5.8 起，`页名_ocr_diagnostics.txt` 是严格的 12 列 TSV：`column / box / conf / text / accept-reject / score / lemma / raw / corrected / POS / repairs / reason`，只有一个表头，所有后续行列数完全相同；Paddle/Tesseract 来源写在 `reason` 的 `engine=...` 中。按 canonical 阅读轴 V 自动配对的双 OCR 对照移到独立 `页名_ocr_comparison.txt`，固定 27 列，可直接查看 `delta_y`、两侧 lemma/status 一致性和冲突原因。接受词头如果违反页面内近似字典序，只产生 `WARN:alphabetical_*`，不会因此被删除。JSON 还保存 `final_entries`，GUI 翻页后会恢复 OCR confidence，并用文本框底色分级显示。修改筛选正则和阈值后再次识别会复用 Paddle OCR 缓存；只有图像、列路径、候选带、语言或模型设置变化时才重新推理。需要忽略缓存时在主界面选择“②强制重新识别”后运行 OCR 画线。

整页版面参数估计使用 PaddleOCR detection-only 文本框，不把 PP-StructureV3 作为普通页面的必经流程；栏左词头 OCR 仍保持窄候选带策略，以避免无关正文增加耗时。

### 三 OCR 复核与人工复选框

- `v2 双OCR自动融合决策` 默认开启；即使“仅对照”未勾选，只要本机可找到 Tesseract，v2 会运行第二 OCR 参与 fusion。Tesseract 缺失/失败不会阻止 Paddle 结果。
- `*_ocr_diagnostics.txt` 仍严格固定为 12 列；parser stage/trace/bug type 写在最后的 `reason` 字段，因此旧 TSV 工作流不受影响。
- `*_ocr_comparison.txt` 仍严格固定 27 列，但配对算法按词头序列 + canonical 阅读轴 V 双重约束，不使用旋转后失真的 source Y 做配对。
- `*_ocr_engines.tsv` 是固定13列长表，同一候选的 Paddle/Tesseract/Lens 各占一行；`*_fusion.tsv` 保存最终选择，新增 OCR 引擎不再迫使旧双引擎表无限加列。
- `*_issues.tsv` 是固定16列人工复核入口，包含三引擎 lemma/text；`_quality_summary.tsv` 增加 Lens 使用数和多引擎多数一致数。
- 主图右边的复选框对应栏左 OCR 候选行。勾选被自动拒绝的行会立即创建词条线和可编辑 lemma 文本框；取消则从最终结果删除。
- “工具 -> OCR词头冲突复核”可按问题行查看三引擎结果；双击跳到原图位置，按钮可直接采用 Paddle/Tesseract/Lens/手工结果。
- 人工复核结果不会改写原始 OCR diagnostics，而保存在 `*_manual_selection.json`，因此自动结果和人工决定可以追溯。

### 校对文本框上下边距

校对窗口第一行可设置“上下边距（px）”。该值对文本框上、下两侧对称增加显示空间，用于避免重音字母、附加符号或特殊字形被单行控件裁切；不影响图片切图、PDIC 或 OCR。

## 词头过滤/强制接受规则

打开“参数设置 → 词头规则”可直接编辑。点击“保存参数”后，规则会同步保存到项目根目录的 `headword_filter_rules.txt`。规则一行一条，`#` 开头为注释。

常用示例：

```text
reject_lemma_exact: sa
reject_lemma_regex: ^[a-záéíóúüñ]{1,2}\.$
reject_line_contains: □ Conjug.
reject_line_regex: ^\S+\.\s+.*Conjug\.
accept_lemma_exact: aglomeración
accept_line_contains: Elemento compositivo
pos_exclude_exact: Conjug.
```

拒绝规则优先于接受规则。`accept_*` 可以跳过内置的结构/视觉阈值，但不会接受无法提取 lemma、超出栏左缘或位于页眉区的任意 OCR 噪声。规则文件不参与 PaddleOCR 原始缓存签名，因此改规则后通常无需“强制重新识别”。

## 命令行批处理

在项目根目录运行：

```bash
uv sync
uv run picture-capture-cli "D:\Dictionary" inspect
uv run picture-capture-cli "D:\Dictionary" autodraw --page page001.tif
uv run picture-capture-cli "D:\Dictionary" ocr --page page001
uv run picture-capture-cli "D:\Dictionary" split-lines
uv run picture-capture-cli "D:\Dictionary" split-whole
```

省略 `--page` 时处理全部页面。批量 `autodraw` 会重写相应 `.pdic`，请先备份已有人工校对结果。

## 与旧版相比的重要修复

- 末页“下一页”不再访问越界索引。
- 自动切图不再误用无关的 `CheckBox3` 状态。
- 所有裁剪框都会限制在图像范围内；不会因负坐标或超过边界而使整批任务崩溃。
- 不再用空的 `Catch` 吞掉错误；错误会显示原因并在终端输出详细信息。
- 旧显示/参考坐标仅用于兼容迁移；PDIC/PPP/设置/切图/PageSections 与对外标注统一使用原图 X/Y，内部临时变换不会改变任何持久化坐标。
- 文件路径使用 `pathlib`，不再依赖 Windows 反斜杠字符串拼接。

## 已复原的功能

- 打开含有 TIF/TIFF/PNG/JPG/BMP 页面的项目目录，并按文件名翻页。
- 读取、编辑和写回旧版 `.pdic`；字段顺序仍为 `词条#X#Y#X比例#Y比例#当前页#上一页#下一页`。
- 根据词典栏左侧的墨迹自动寻找词条行；支持整页检测，也支持右键只重画当前栏。
- 提供两种主画线方式：推荐默认使用 `paddleocr`（OCR识别词头与坐标并直接画线）；`left_edge`（普通画线，旧版左缘排版规则）作为规则版式或 OCR 暂不可用时的备用方案。v2.4 已移除旧的 `projection` / `hybrid` 方式及其四个投影参数。
- 左缘规则新增“跟随词头列倾斜/变形”：只分析每栏左侧的有限区域，沿页面高度建立多个X位置锚点，可跟随整体倾斜和局部拉伸造成的缓慢弯曲。红色列参考线、检测带、OCR行裁剪和词条整体裁剪使用同一路径。
- PaddleOCR 同样只处理每栏左侧候选带，并先沿动态列路径逐行拉直。v1.5 会先把同一印刷行上被 OCR 拆开的词头、复数信息和词性框重新合并，再用左缘位置、词头结构、词性/变形提示、字号、字重、特殊符号和行前空白综合筛选。
- v2.1 新增本词典缩写/符号配置、Google Lens 文字与 bbox、三 OCR arbitration、Tesseract 自动发现/语言检查/PSM 4与6自动比较、标准化长表及融合表。Lens 不提供稳定粗体字段，三引擎均从原图 bbox 统一计算字高和墨迹密度。
- v2.0 新增结构化 Grammar Parser、跨行状态机、Paddle/Tesseract 序列+Y对齐、自动 arbitration、页面一致性评分、issues.tsv、OCR冲突复核窗口和所有候选行右侧手工复选框。
- v1.5.9 基于 0055–0070 共16页真实扫描及 diagnostics 统一修正词头语法解析：兼容旧正则吞逗号、长词头 POS 换到下一印刷行、`aguantarv.`/`aire ar v.`、`s.amb.`/`pron.indef.`、`Contracción de`、`air mail || ...` 等结构，并收紧 `Pron. [...]` 发音说明和词条内部续义造成的假阳性。
- v1.5.8 将 OCR 诊断拆成两个严格矩形 TSV：`QT/PaddleOCR/页名_ocr_diagnostics.txt` 固定 12 列，`页名_ocr_comparison.txt` 固定 27 列；两文件都不再混入节标题、重复表头或不同列数的记录。v1.5.7 加入的字典序弱报警和 confidence 分级文本框底色继续保留。
- v1.5.7 继续扩展 55–60 页实测发现的 OCR 容错：`+`/`.-`/`+-` 音节分隔、`agro-` 等尾连字符词素、`Sufijo/Prefijo/Sigla de` 描述词、POS 前短版式噪声和 lemma 末尾数字/字母混淆。
- v1.5.6 扩展 `s.`、`so·ra`、`to·ra` 等词头结构，增加被拆开的 lemma/性别变体/POS 主动同行吸收，并记录 OCR 字符修复；还可选开启 Tesseract 对照与保守补漏。
- v1.5.5 新增“词头规则”分页和项目根目录 `headword_filter_rules.txt`：可用一行一条的 reject/accept/POS 排除规则处理个别误检或漏检，规则修改可直接复用已有 PaddleOCR 缓存。
- v1.5.4 将首个正文词头改为“首个持续墨迹Y”精修，并扩展西语词头结构：支持 `agnóstico, ca`、`agorero, ra`、`-a·go·gia`、`Elemento compositivo`、`superlat. irreg.` 等第53页常见形式；同时自动迁移未修改的旧默认OCR参数。
- v1.5.3 修正首个正文词头被顶部空白区拉高的问题，并拒绝 `sa. □ Conjug.`、`blación. □ Conjug.` 等断词续行误检；`Conjug.` 不再被 `conj.` 词性规则部分匹配。
- v1.5.2 在 PaddleOCR 词头粗定位后增加横线Y精修：在词头Y附近按栏计算每一行的黑色像素占比，对数个相邻扫描行做安全带平均，再取连续低墨迹谷的中心，减少紧密排版时上一行 `g/j/p/q/y` 下伸部被横线切到。
- 左键手动增加词条线，`Delete` 或反引号键删除；鼠标位置显示蓝色横纵交叉虚线，便于对齐词头顶端。
- 主界面取消菜单栏/顶部工具栏；版面参数、OCR参数、辅助显示与主要操作集中在左栏。页面列表占用左栏剩余高度并可滚轮滚动；底部固定为单行绿色入口【项目中心 / 初始Profile / 设置中心 / 帮助中心】。新建项目移到【项目中心】搜索栏最右侧；完整参数从【设置中心】打开，其中【切图设置】已作为独立页签整合进设置中心。
- 图片区域支持鼠标滚轮上下滚动、`Shift + 滚轮` 横向滚动、`Ctrl + 滚轮` 缩放。
- 可选择 Tesseract 5 或 PaddleOCR 识别当前页/全部页面已有的词条行；支持旧版 `_Replace.txt` 的普通替换 `N` 和正则替换 `R`。
- 导出/导入旧版 `.OCRed` 文本。
- 导出词条单行图到 `QT/PSW`，并生成 `.PSWords`。
- 按同栏下一词头、跨栏延续和跨页延续切出完整词条到 `QT/PWW`，并生成 `.PWWords`。
- 识别 `QT/_SpecialPages.txt` 中的特殊上下边界，生成兼容的 `_file_log.txt`。
- 校对窗口：默认宽度和高度均为当前屏幕的 70% 并居中；左侧切词+文本框区域支持滚轮，点击某个文本框后右侧显示 PaddleOCR/Tesseract/Lens 候选并可单击填入，同时保留 `wordslist.txt`、批量填充和变音字符。
- 读取旧版 `_Mysettings.ini`，以后将设置保存为更稳健的 `picture_capture_settings.json`。
- 导入旧版 `_WordsOfPages.txt`：既支持完整 PDIC 行，也支持按页面顺序排列的单词列表。
- 插图多边形绘制并保存为旧版 `.ppp`；可按页面范围裁出透明 PNG 到 `QT/PIC`。
- `PicDic制作` 根据 `QT/PWW/*.PWWords` 生成 GoldenDict/ABBYY DSL 图片词典及 `.dsl.files.zip` 图片包。
- 校对面板可选择独立 `wordslist` 参考文件，并对当前页或全项目做词头顺序核对（lower-case + Unicode/重音/标点普通化后比较）。
- 命令行批量模式，便于对大型词典项目自动处理。

旧源码中的 `TOP`、`RIGHT`、`CK1–CK5` 等是通过隐藏文本口令触发的开发调试开关，不属于正常制作流程，因此没有照搬这些隐蔽入口；其实际需要的坐标、缩放和错误日志已经直接显示或自动记录。

## 测试

```bash
uv run pytest
```

测试覆盖 PDIC/PPP 往返兼容、显示参数与原图坐标换算、规则/投影/倾斜词头检测、PaddleOCR 结果解析与候选缓存、音节分隔词头标准化、同行框合并/主动吸收、裸 `s.` 与音节化性别变体、OCR字符修复、诊断报告、词性结构提示、running header 排除、OCR 文本替换、裁剪边界以及单行/整体切图清单。
