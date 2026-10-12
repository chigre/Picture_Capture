# Picture Capture：画线准确性升级 — 实施及真实扫描证据

日期：2026-10-12；基线：`main` 合并 #458 后的 `668d7cbc`。
工作分支：`feat/headword-boundary-evidence-20261012`；PR #459（Draft，未合并）。

## 本阶段实际部署到分支的算法改动

1. **跨来源词头对齐不再贪心**：`ordered_marker_matching.match_ordered_markers()` 在按原阅读顺序排序后的候选上做一对一动态规划，先最大化有效配对数，再最小化总绝对 reading-Y 偏差。已替换 `processing_core._fuse_detection_entries()` 的已接受 OCR 与拒绝候选的两个配对环节，以及 `scripts/detection_benchmark.match_markers()`。不同栏不能生成跨栏配对边，CJK/普通的不同容差保留。
2. **成对括号词头复检更可靠**：`ordinary_bracket_pair.recover_bracketed_ordinary_entries()` 仍坚持“栏首 + 完整开闭括号配对”，但新增在文字上方实际白缝寻找安全分隔位置，避免 `bracket_top - 0.08 × line_height` 的无条件像素偏移；候选在 canonical 坐标检测后可逆映射到源图。维持既有 CJK 大字头去重、词条保存格式与旧调用接口。
3. **书写方向解耦**：区分 `uses_cjk_script`（文字所属语言）和 `uses_cjk_role_model`（目前仅经验证的横排缩进模型）。竖排 CJK 可以使用括号结构检测，但不会误启用横排缩进角色模型。
4. **词头来源诊断**：新增只读、不可变的 `BoundaryProposal`（栏、canonical V、源图 X/Y、来源、正证据、警示、keep_legacy）。`PageUnderstanding` 与诊断导出保存相应记录，**目前不根据警示直接删除真实词头**，尤其不能以“该栏词条太少”为由强制补线。

## 用户提供的真实词典局部图像验证

数据来自 `PictureCapture_Layout_RealScans_Review_20261010.zip/assets`，**不是** 3240×4600 原始完整扫描图。裁剪图中带人工标注的红色横线；对像素做检测前先剔除红色标注像素，以免将标注误认为真实墨迹。

运行：

```powershell
python scripts/validate_real_scan_rois.py --assets "C:\path\to\extracted\assets" --output real_crop_audit.json
```

**真实图像局部视觉证据通过：5/5 个独立可见真实括号词头，且题注没有成为括号结构候选。** 这是实际 JPEG 上的像素组件识别，而不是人工生成的矩形模拟。使用项目自己的 `_rle_components` 与 `_bracket_side` 两个函数，固定审阅截图局部开括号 y 作为独立人工核对值。

| 实际审阅截图 | 真词头局部 y（截图坐标）| 找到的真词头数量 | 额外约束 |
|---|---|---:|---|
| `040082_1391_correction.jpg` | 155, 237 | 2/2 | 两个相邻括号必须互不覆盖 |
| `040082_1886_correction.jpg` | 154 | 1/1 | 不把上方续行作为字头 |
| `040086_662_correction.jpg` | 152 | 1/1 | 红色标线干扰去除后仍可匹配 |
| `040088_1559_correction.jpg` | 233 | 1/1 | y≈150 的“东汉吊灯”题注不能变成括号字头 |

可复验的源素材 SHA256 前16位分别为：
`dd8ed0be5a253720`、`67cef8b40e7e85c3`、`8e497449d61d62ce`、`68f4e9009f44b085`。

局部截图中的 y **不能当作原图 PDIC 坐标**；历史 3 FN / 1 FP 不能宣称已在当前 main 上全部修复。当前 ZIP 缺少 10 页全尺寸原图和 OCR/PDIC 真值，不能执行三模式全页准确率基准，也不能由这四张 crop 推导整体 Recall、Precision、F1。

## 已增加的程序化测试

- 匹配歧义：预测 [0,5]、参考 [4,9]、容差 5 时贪心只有 1 对，单调 DP 必须得到 2 对。
- 一栏密集近邻 / 多栏不交叉 / 不合法输入 / 误差次级最优化。
- 自然白缝落线、不跨黑墨、无空白时位移有界。
- CJK 旋转/镜像回源图坐标；已存在源图标记时避免重复。
- 物理行候选的正证据/警示审计只读、稀疏延续栏绝不强制增加候选。
- 三平台项目全套 pytest 和 GUI 冒烟 CI（以 PR 页面结果为准）。

## **仍未宣称完成的下一阶段**

1. OCR 词头与真实释义续行的细粒度仲裁（西汉 `momento`、`una`）、词性、字体粗度、邻词样式及内部短语的分级证据；
2. 插图区域/题注几何证据直接参与候选反证（不仅仅是括号形态不匹配）；
3. 经确认的 PDIC 与完整扫描上，按词典分别跑本版普通/OCR/融合的 FP、FN、切字误差及耗时。真实完整数据未获得前，禁止因几张裁剪图而全局调低召回或彻底替换当前 Layout 的输出门控；
4. 一旦有整页真值，优先校正需要保留/删除的候选级错误，之后才能让 `BoundaryProposal` 从只读审计转为自动候选裁决。

本工作避免直接推送 `main`；如需合并，先完成 PR 的回归测试并对指定词典整页验证。


## 2026-10-12：用户新提供五个完整图片 ZIP 的真实数据核查

已核对 **74 张全部可读取的原始扫描**：三民 10、葡汉 10、新时代西汉 10、FarEast 20、DICs_for_test 24。只有前三本共 **30 页／1336 条 PDIC** 有人工标记；全部 30 页的 PDIC 与训练 JSON 坐标和词名逐条相同。后两包**无真值，不可计算 F1**。

对训练 ZIP 所附的 **历史 OCR 缓存 final_entries（非本分支新生成预测）**用同栏、单调有序最大配对数评估：

| 词典 | GT | 缓存 OCR | TP | FP | FN | F1 |
|---|---:|---:|---:|---:|---:|---:|
| 三民 | 230 | 229 | 229 | 0 | 1 | 99.78% |
| 新时代西汉 | 593 | 621 | 577 | 44 | 16 | 95.05% |
| 葡汉 | 513 | 490 | 490 | 0 | 23 | 97.71% |
| 合计 | 1336 | 1340 | 1296 | 44 | 40 | **96.86%** |

用字符高 ×0.3 至 ×1.0 的匹配容差，匹配数未变化。**本批已缓存结果中，贪心匹配与新增最优匹配 TP 相同**（0 个可观测配对差异），不能声称匹配器的修正提升了这批历史 F1。

错误归因：西汉 44 条误线中 41 条的历史 OCR 来源为 `missing_selected_tail_structure`，却带旧 `peer_typography_match`，如 `momento`、`su`、`una`（当前 main 已有更严格的粗体匹配，旧缓存不能视为当前 main 结果）。西汉+葡汉的 39 条历史漏线有 29 条出现过距离很近但被拒为 `continuation_fragment` 的 OCR 候选。

### 根据真实词典数据新增的粘连 POS 续行救回

新增 `latin_glued_pos_headwords.py`，接入 `evidence_fusion.py`，以词头首段**直接粘连词性标签**（如 `abaluartarv.t.`、`abanillom.`、`Abigaíln. pr.`）作为独立正证据，仍要求栏首、可靠图像边界、OCR 信心≥0.90、粗度≥0.60、无用户否定/硬反证。对历史被拒 OCR 候选离线回放：

- **22 个**候选触发新条件；
- **21 个**在人工 PDIC 已保存真词头处（葡汉15、西汉6）；
- **1 个**为葡汉第10页右栏开头 `abraçar`，未在 PDIC 中，但打开实际原图可见独立粗体词头、`v. t.` 与释义，**很可能是 PDIC 漏标**，不能简单算作算法误线。

这只是**基于旧候选的反事实回放**，不是运行整套升级引擎后的实际新增 22 条画线，未解决与现有线重复/上下游选择器等问题。必须全页重跑才能得到新版本真正的 P/R/F1。

### 源图像素定位验证

在全部 1336 条人工标记附近给定词头邻域，从真实像素求首个墨迹行并回放 `safe_gap_above`：三民230/230、西汉593/593、葡汉513/513 的预测空白分隔行都在对应人工 Y 的 0.45 字高内；中位绝对偏差为6、2、2像素。**这是给定已知词头的 Y 定位测试，不是自动词头识别测试**。

### 数据包真实性／版本限制

五包文件均已确认可正常解压和解码；扫描文件因版权原因没有提交 GitHub。`scripts/benchmark_training_archives.py` 为可复现的 ZIP OCR 缓存对照脚本，严格区分训练真值包与仅含扫描图片的包。

当前执行容器可以读取用户完整 ZIP，但无法从 GitHub 拉取 Picture Capture 全仓代码及运行依赖（DNS 不可用）。**尚未在这 74 张完整图上重跑 PR #459 的完整 ordinary/OCR/combined 画线器**；因此不得把旧缓存 F1 作为升级分支的新性能承诺。需在有两者完整环境的计算机上完成同条件两分支三模式检测后，再考虑合并。


## 2026-10-12 第二批：用户 **普通画线** training-v3 五本词典

与上面 OCR 缓存报告**严格分开**。这批是自动普通画线时 `captured_at_automatic_draw` 的冻结快照，及其后用户保存的人工 PDIC，含**34页／920条已保存 PDIC**。全部34页的保存 PDIC 与 annotation 坐标、词条名逐条一致。按原图 X 归栏、同栏有序最大匹配，容差 `max(8px, 0.5×保存字符高)`。

| 词典 | 页数 | GT | 历史自动 | TP | FP* | FN* | 历史F1* |
|---|---:|---:|---:|---:|---:|---:|---:|
| 葡汉 | 10 | 513 | 511 | 510 | 1 | 3 | 99.61% |
| 三民 | 10 | 230 | 216 | 210 | 6 | 20 | 94.17% |
| 新时代西汉（本包仅1页） | 1 | 30 | 2 | 2 | 0 | 28 | 12.50% |
| 字典𡨸喃摘引 | 10 | 62 | 62 | 15 | 47 | 47 | 24.19% |
| XDHYCD | 3 | 85 | 32 | 31 | 1 | 54 | 52.99% |
| 合计 | **34** | **920** | **823** | **768** | **55** | **152** | **88.12%** |

*与人工“保存 PDIC”相比；其中存在漏标可能，不一定全部是真正的视觉误线。以上**不是本PR新检测器的 F1**。

### 观察—修复—真实像素回放

- **三民（采样 `【】` 却连续漏）：** 原图印刷的 `【` 紧贴甚至略超栏首；原 `ordinary_bracket_pair.py` ROI 由栏首向内 0.5 倍行高开始，故漏掉开括号。现 ROI 向栏外扩展，覆盖不同宽高及较长词条；恢复了旧合成测试允许的有缩进开括号。独立实际图片组件原型找到 **228/230** 个已保存括号词头，0 新额外配对；与历史自动线模拟合并后 **FN20→1，FP仍6**。请注意原型≠此分支全引擎重跑。
- **新时代西汉（右栏全无）：** 上传的唯一页有28个右栏人工真线，历史自动**0**条右栏线，但同一包的独立 Page Design 诊断右栏有 **26** 个稳定词头缩进支持。新增 `ordinary_independent_indent_rescue.py`：仅对非 CJK、物理行众多但最终词头≤2的枯竭列，且独立重复词头簇/正文簇证据足够，补回独立真实版面检测候选，避免“右栏空就随意画”。尚待实际全引擎重跑确认28条的逐条准确性。
- **字典𡨸喃摘引（字心穿线）：** 页1–3基本没有系统 Y 偏移；页4–10 自动画线穿过很大的首字。用真实像素 ink-above、ink-crossing、preceding blank band 取页内一致位移的离线回放，逐页 **[0,0,0,24,21,20,23,23,24,23] px**，保存 GT 的 FP/FN **47/47→5/5**。新增 `ordinary_crossing_separator.py` 并在 CJK 直接普通画线后应用“≥22%独立支持+离差门控”的一致偏移；不根据书名/PDIC调固定值。注意 Profile 锚定仍可能限制逐页字符高偏移，必须在真实重跑时额外核查。
- **XDHYCD（未采样 `【】`）：** 实图同时存在小字成对 `【头】`、以及第二页**没有括号的超大首字**（如「啊」）。无模板成对括号独立像素检测找到 **59** 个候选，其中53个匹配保存 GT、6个没有对应人工线（可能存在 PDIC 漏标）；与历史线模拟合并 **FN54→23，FP1→7**。**没括号的大字头尚未被本次括号修复解决**，不能把未匹配6条全部当真误线。
- **葡汉保底：** 历史只差1 FP／3 FN；以上补括号及穿字逻辑均 gated to CJK，西汉独立列回退只在列严重枯竭时触发。最终是否零退化仍要跑实际检测。

**验证状态**：真实完整图像已用于像素/标记回放，代码测试与跨平台CI可验证；由于图片 ZIP 在隔离容器、完整项目源码/运行依赖在 GitHub Actions，**尚未在相同环境直接运行本分支 `detect_entries(..., method="left_edge")` 对所有34页重新输出预测**。上述“→”数字是反事实，不是新分支实测 P/R/F1。本PR保持 Draft，不可在正式全页逐本回归和人工漏标复检前合并。

复验脚本：`scripts/audit_ordinary_training_v3.py`（保存旧自动线对照，使用实际X归栏）以及 `scripts/run_training_archive_full_benchmark.py`（在同时拥有源码+原图ZIP的环境里实际重跑全部普通/OCR/融合检测）。


## 2026-10-12：第二栏 Indent 消失的统一 Layout Core 修复

用户重新提供了 XDHYCD 的实际 Layout 叠加截图，指出新时代西汉也存在“C2 第二栏没有 Indent”的同一症状。根因不是词头采样，也不是仅仅画线导出逻辑：

- **西汉**：已存诊断表明物理 Layout C2 把55个行首集中为一个正文缩进簇（仅1个游离entry）；同页独立 Page Design C2 的确有26个外侧词头、27个内侧正文，位置差约30px，说明真实印刷上确实存在两个家族但被主模型丢掉。
- **XDHYCD**：物理 detector 的 `projection_line_runs()` 允许0.26–1.90倍行高；消费端 `infer_dictionary_page_layout()` 却只接受0.45–1.55倍。真实 PNG 中第二栏成段墨迹高度常达29–32px，而页设置字符高18px（1.61–1.78倍），造成真实行在缩进聚类前被丢弃；原存诊断 C2 仅保留17左右的 physical lines。且某些页面外侧词头比内缩正文行**更多**，不能用最大支持簇直接推断 body。

**已推送实现**：

1. `dictionary_page_design.py` 严格保持传统非物理投影路径的1.55倍阈值；仅当 line_runs 明确为物理投影生成器时，消费者采用同一0.26–1.90倍契约。禁止无意识将所有大字行都当普通词条。
2. `layout_column_indent_recovery.py` 在 shared `understand_layout_core()` 的最终角色判断后，检查 *只有少量 entry / 字形行严重合并* 的列，使用两种独立可观测证据恢复真正的 Layout entry/body：
   - 拉丁词典：单独 Page Design 分析需要有≥5个外侧词头、≥5正文、相距≥0.3字高，并且候选真实 Y 映射到主 Layout 行；其他列不变。
   - CJK：采用源图成对完整 `【…】` 字形（至少3组）产生候选，恢复对应物理行及 Indent 簇，无人工采样也能使用。不凭“空列”强制增加词头。
3. 与之前仅在 `processing.py` 末尾补 Entry 的 fallback 不同，本次真正修改 `PageUnderstanding.layout.columns[].lines / indent_modes / entry_modes / body_mode`，普通画线结果与 L（显示Layout）调试图走相同修改后的几何角色数据，layout.reason 也加入 recovered_indent_columns/rows 计数。
4. 新增 `test_layout_column_indent_recovery_20261012.py` 以导出诊断还原 C2，及 `test_physical_line_height_contract_20261012.py` 对 18px 正常字高、30px 真实字形墨迹高的 producer/consumer 不一致做回归。CI 以该PR最新提交上的 GitHub Checks 为准。

**验证限定：** 已通过真实扫描文件及其随附的真实诊断发现上述失效，但还没有在 GitHub 源码/模型安装完整的同一执行环境对新代码进行完整34页重画并实测新的每列 P/R/F1；也没有拿到用户新版本的实时 Layout 叠加结果。因此不得宣布 XDHYCD 全页、或西汉右栏实际已经修好，必须以两本书新生成的 L 叠加图 + 按列 PDIC 匹配再确认。


## 2026-10-12 附：**真实根因：栏中斜竖线污染 first_x**（非仅仅是行高）

进一步使用用户提交的完整扫描 `XDHYCD_0001.png`（1388×2156）与 `0001.tif` 西汉（2536×3765）逐点测得：

| 词典 | 原图竖线 X | 真实第二栏 X | 旧 Layout 的 C2 最大体缩进中心 | 来源图+已保存真词头附近实测首次墨迹 X |
|---|---|---|---|---|
| XDHYCD | 随 Y 倾斜约690–697 | 711 | **-21.35**，相当于 X≈690 | 未排竖线中位 X≈691.5；排竖线后 X≈720 |
| 新时代西汉 | 随 Y 倾斜约1273–1277 | 1310 | **-36.03**，相当于 X≈1274 | 未排竖线中位 X≈1274；排竖线后 X≈1324 |

**这就是第二栏 Indent 失效的直接证据。** 主 Layout 下游的 `layout_column_drift.remeasure_layout_indents_from_ink()` 原本为了照顾行首越栏，往右栏左侧退1.75×字高采样，恰好把栏间竖线纳入。竖线存在几乎所有文字行的扫描带中，于是绝大多数词条/正文 `first_x` 被误取成负值，模式聚类把它们合并为最大 body。以前的 `dictionary_page_design._persistent_rule_mask()` 只看**相同 X** 的跨页持久性；真实竖线倾斜，会让每个固定 X 只在部分页面行中出现，遗漏了竖线。

**已在本PR修正根因**：
- `layout_gutter_rule.gutter_divider_right_edge()`：仅在两个已确定物理栏之间的纸张空白沟道内，通过多段 Y 窗口追踪高墨迹密度、缓慢漂移的竖线轨迹。必须≥55%窗口有密度≥50%的竖线候选，同时要求≥50%窗口 X 收敛在一个小范围；没有纵线的词典走原路径。
- **两处使用同一规则**：`dictionary_page_design._refine_column_geometry()` 对竖线候选进行 gutter 墨迹排除，避免错移第二栏起点；`layout_column_drift.remeasure_layout_indents_from_ink()` 在测量 `first_x` 时把左侧起点移到竖线外，保留跨栏小位移的文本行。源图数据完全不修改。
- `layout.reason` 记录 `slanted_gutter_rule_guard=C2:X...` 供 L（显示Layout）诊断。
- 新增合成倾斜竖线、无竖线、短文字假线、真实 C2 词头多于正文的方向角色、以及列位置对齐回归测试。

**重要区分**：上述 `≈691.5/720` 和 `≈1274/1324` 来自完整原图中已知人工标记附近的像素窗口对照，支持明确的根因诊断，但不是在全环境中重跑新的完整画线程序。正式修复是否达到目标，需要 PR 新代码生成的 Layout C2 内缩两簇分离图和全页 PDIC 回归指标进行最终确认。


## 2026-10-12 XDHYCD：大量 INDENT 消失的第三个根因（自动字高回退被跳过）

用户提供的新版 L 叠加图直接显示 `character_height=17`、`row_padding=1`、`line indents=35`（C1=10、C2=25），但视觉上仍有大量实际文字行没有 Indent。这说明不仅是 indent 分类失败，**物理行尚未全部恢复**。

**真实原始扫描的独立像素测量**（来源：`xdhycd_training_20261012_035134_756550.zip` 中全部三页；在两栏正文领先278px区段，以灰度 <170、每行≥2个暗像素、允许1px墨迹断裂，筛选符合 17px旧估计0.65–2.10倍的墨迹行高）：

| 原始页 | 文字墨迹行高中位数 | 行首-行首节距中位数 |
|---|---:|---:|
| XDHYCD_0001 | 30px | C1=42px / C2=43px |
| XDHYCD_0002 | 29px | C1=42px / C2=43px |
| XDHYCD_0003 | 30px | C1=43px / C2=43px |

**故障A**：`layout_character_height.apply_character_height_fallback()` 之前用子串 `"fallback=character_height" in method` 判断是否运行真实文字墨迹字高复测。然而实际诊断 method 为 `reliable_fusion+paddle+projection_fallback+separator_anchor+fallback=gutter,character_height`，其中不存在那个连续子串，复测被意外完全跳过。修复为提取 `fallback=` 参数中逗号分隔的所有字段，再检查其中是否有 `character_height`。原有8行最小样本量、MAD/10–90%离散度门控保留不变。

**故障B**：即使复测得到约30px，`layout_profile_anchor.anchor_resolved_layout_to_profile()` 仍对任意单页字高施加Profile基线±max(2px,6%)上限。17px旧基线会将30px真值压回19px，仍然导致按错误比例切行。因此仅在 `estimate.method` 含明确 `observed_character_height=`、estimate字高与被自动选中的值一致且比旧Profile高>25%时，允许该严格图像观测越过Profile夹紧；其他单页检测结果继续夹紧，未选中自动字高时不受影响。

**影响链**：`17px字高 → 行投影分裂/接受阈值偏低 → 实际29–32px字形难以被恢复为正确物理行 → C1/C2 line indents显著偏少 → 真词头进入不了角色分类 → 后续再好的Bracket/Indent复核都无从定位`。还需区分`row_padding=1`与真实行间节距：实际43px行首间距由文字墨迹行高约30px加行间空白构成，不可把17px字高误当43px行距。

**新增回归**：多字段fallback解析的正负用例、原Profile17px与严格复测30px的越界锚定保护、非证据支持异常字高仍被锚定。暂不声称**已经**在新PR版完整运行34页的Layout；实际叠加图下一步应该看到含`observed_character_height=...`的method、使用≈29–30px，而不是17px，并有更多逐行Indent。依旧保持Draft。


## 2026-10-12：Profile 初始化 17px 根因已追到最早的多页创建流程

此前仅处理了**已经创建 Profile 后**的逐页检测：多字段 `fallback=gutter,character_height` 未触发真实字高复测，以及后续 Profile 锚定回夹。但是，新项目的 Profile 多页向导有一条**完全不同**的测量路径：

```
profile_setup.ProjectProfileWizard.analyze_representative_pages
→ profile_layout_bootstrap.detect_profile_layout_parameters
→ layout_detection._projection_layout_estimate
→ character_height = round(image_height * 0.008)
→ layout_detection_legacy.aggregate_layout_estimates (robust median)
→ ProjectProfileWizard.apply_analysis_suggestion
→ Profile.character_height（固化为旧值）
```

Profile bootstrap 为了快速和避免循环依赖，明确**绕开**正常 Paddle/可靠性融合/前述 `apply_character_height_fallback()` 复测。其原先所谓字高只是按原图像素高度的0.8%取整：

| 实际 XDHYCD 源图 | 旧 Profile 推断 `round(H*.008)` | 源图 Otsu 阈值真实墨迹高（按项目代码统计） |
|---|---:|---:|
| `XDHYCD_0001.png` 1388×2156 | 17px | 29px，72个稳健行样本，P10–P90=28–31 |
| `XDHYCD_0002.png` 1385×2158 | 17px | 29px，46个稳健行样本，P10–P90=27–30 |
| `XDHYCD_0003.png` 1392×2152 | 17px | 29px，70个稳健行样本，P10–P90=28–31 |

多张图高度几乎相同，**会一致地算错**为17，中位数聚合不可能消除该系统性误差；`row_padding=1` 则是回退算法的固定赋值，并非43px的物理行间节距测量。

### 本次针对源头的修正

- `profile_layout_bootstrap.py` 在取得 OCR-free 投影栏与正文范围后，直接复用已有的 `observed_character_height`，对全分辨率真实墨迹行高进行多行稳健测量（≥8有效行、离散度、分位数筛查）；**不用引入 PaddleOCR**。
- 借助method诊断准确区分 `+observed_character_height=29(n=...)` 与 `+unverified_character_height`。
- `robust_profile_ink_height` 多页聚合**仅使用独立验证成功的真实字高**，要求至少半数代表页有可靠测量。出现3页29px/3页17px启发值时，Profile建议29而不是23；完全缺测则不自动覆盖原Profile字高，界面显示测量比例及警告。
- 其余多页栏数、栏起点、宽、沟宽度等稳定中位数聚合不变，已有Profile以往行为兼容。
- 测试：原图大小1388×2156、实际印刷29px文字带的合成页，验证Profile得到29而非17；未验证不冒充测量；3可靠29px+3原始启发17px时中位值=29；未过半时不自动更新。

**证据限定**：已在用户上传的真实三页上复现上述像素值（独立运行与已有 `observed_character_height` 对应的同一阈值／稳健统计）。新分支的代码回归以PR最新CI为准；尚未在实际GUI中从头创建一次XDHYCD Profile并人工查看自动建议。若旧Profile已保存17px，须在新版本的多页向导重新执行“分析代表页→采用建议”才会更新持久值，已有项目不会在打开时被自动改写。
