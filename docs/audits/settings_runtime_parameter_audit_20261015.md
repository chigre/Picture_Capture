# 设置中心与运行参数审计（阶段一：静态代码审查）

基线：PR #496，提交 `08762bce1b6f097e79be86a57fd0ddb039625186`。本文是**静态代码审查**，不是完整运行时覆盖率证明。保留待测事项，不将硬编码数值自动视作用户参数。

## 审计链

- `models.py`：`AppSettings` 及 JSON 序列化；
- `ui/settings/schema.py`：可见字段、复选框、帮助、取值边界与候选项；
- `app.py`：设置中心控件生成与保存、批量任务复制 `settings`；
- `processing.py`：Layout/普通画线入口及后处理；
- `paddle_headwords_core.py`、`ocr_boundary_detection.py`、`separator_y_refinement.py`：OCR 候选与共用 Y 精修；
- `ordinary_crossing_separator.py`、`ordinary_final_visual_consistency.py`、`ordinary_oversized_head_guard.py`、`ordinary_bracket_pair.py`：普通画线后处理。

## 重要发现（可定位）

### P0 — 共用 Y 精修设置与实际算法的契约需纠正
1. 设置中的 `paddle_separator_safety_px` 在 OCR 图像边界候选检测路径读取，但在 `paddle_headwords_core.refine_separator_y` 的墨迹谷算法本体不直接读取。设置中心把它描述为所有横线“精修后安全距离”容易误导。
2. `paddle_separator_roi_width_ratio` 100% 的确仅代表扣除 `paddle_separator_column_margin` 后的可用栏宽，不能保证全栏无墨迹穿越。
3. `separator_y_refinement.py` 在诊断回传细节使用部分 `separator_y_*` 别名且 `or` 后备值，可能使合法零值显示失真；应显示实际运行字段 `paddle_separator_*`。
4. 普通 Layout 主路径精修后还有 `ordinary_crossing_separator.adjust_page_coherent_crossing_separators` 和括号词头恢复、视觉修正，单个精修开关不能覆盖“所有最后 Y 修正”；应在 UI 帮助中清楚标明范围。

### P1 — 有临床场景同类的可调试阈值，但被硬编码
以下为“**建议先做诊断或专家模式开关**”的候选，不建议未经 PDIC 对照直接开放：
- `separator_y_refinement.py`：每条初始 Y 到最后 Y 的最大修正幅度 `0.45 × line_height`，以及最低 `3px`；直接影响穿字问题。
- `ordinary_crossing_separator.py`：墨迹交叉判据 `upper <= .105`、`crossing <= .14`，纠正目标距离区间 `0.35~1.75 × line_height`，整页一致性 MAD 阈值 `.30 × line_height`；对 CJK 页面最终画线有影响。
- `ordinary_final_visual_consistency.py`：字符/图形簇尺寸比例 `1.60~3.30 × reference`、`1.65~3.70 × reference`、正文跨度与最终矫正范围。宜先收集误判证据，再按 Profile 区分。
- `ordinary_oversized_head_guard.py`：大字头候选宽/高阈值（`2.3 × pitch` 与 `1.9 × pitch`）及首栏接近范围（`4.5 × pitch`）。
- `paddle_headwords_core.py`：内部候选去重重叠阈值、墨迹谷 `blank_threshold`、基础 raw OCR 置信门槛 `_RAW_OCR_THRESHOLD=0.20`。需要先确认是否已有对应用户级阈值，避免重复暴露矛盾开关。

### P1 — 设置中心“有控件”不等于“全部可见参数都在同一个入口”
- `PROFILE_FIELD_GROUPS` 仍保有“横线定位”副本，Project Profile 与横线 Y 专用标签之间可能出现重复入口；必须验证它们共享 AppSettings 且没有保存互相覆盖。
- `NORMAL_CHECKS` 有共享去噪/缩图等开关，但对应“Layout相关”设置仍归入普通画线 Tab，不应暗示所有 OCR 流程均在该 Tab 上直接读取这些参数。
- `paddle_separator_safety_px` 等精修字段虽移至独立 Tab，但其它代码中可能还有快捷入口或 Profile 项目设置，需要保证单一来源。

## 目前已确认的用户参数

- 普通画线：`ordinary_right_divisor`、`physical_row_projection_width_percent`、`analysis_threshold_mode`、`darkness_threshold`、`white_threshold_high/low`、`upward_ratio`、`whitespace_adjustment`、`column_track_*` 等在普通画线高级设置。
- OCR：`paddle_band_width_ratio`、`paddle_left_tolerance`、`paddle_min_candidate_score`、`paddle_preprocessing`、`paddle_tesseract_psm`、`paddle_alignment_*` 等在 OCR 设置。
- 共用 Y：五项 `paddle_separator_*`、`paddle_refine_separator_y`、`separator_y_ink_safe_gap` 在横线 Y 精修 Tab。
- 性能：`draw_performance_profile` 和 `reuse_prepared_analysis` 在“性能与诊断” Tab。
- Layout：插图白化、共享与 Layout 专用去噪、自动缩图与逐字段白名单均有项目级保存字段。

## 不应直接暴露的常量

数组边界、安全裁剪、坐标变换公式、二值化数学系数、图片大小判空、分页序列化协议、内部兼容性常量等，不属于普通用户应修改的参数。放开这类值会破坏可重复性与维护性。

## 余下需要完成才能宣称“全量审计”

1. 枚举整个 `src/picture_capture` 源代码，而不只是上述入口/主要后处理模块；
2. 对全部 `AppSettings` 字段做 AST 级“读取/写入/默认值/显示位置/配置验证”映射，排除 `Entry` 等非设置数据类型；
3. 动态验证 Settings Center 每个 Tab 的控件值保存、关闭重开、Windows spawn 子进程继承与实际分支读取；
4. 以相同原图/PPP/PDIC 建立输出等价性测试，再按优先级决定是否开放这些阈值。


## 第二阶段：自动化审计与整改（2026-10-15）

增加 `scripts/audit_settings_runtime.py`：基于 AST 遍历整个
`src/picture_capture/**/*.py`，列出每一个 `AppSettings` 字段的
默认表达式、设置中心 schema 位置、代码静态读取与写入位置，以及检测
模块中带数字比较的潜在硬编码阈值。通过
`python scripts/audit_settings_runtime.py --out build/settings-audit`
生成：

- `appsettings_field_matrix.csv`
- `hardcoded_threshold_candidates.json`
- `summary.json`

另有 `.github/workflows/settings-audit.yml` 在 GitHub Actions 运行全仓库
扫描并尝试上传 `settings-audit-inventory` artifact。
`tests/test_settings_runtime_audit_20261015.py` 在 CI 中实际执行该脚本、
检查设置默认值及全部设置 JSON 往返。

已做的不改变默认画线输出的修复：

1. 帮助面板原先绑定动态 `textvariable` 时，初始不设置 wraplength，窗口会
   先按单行长文本扩展。现设初始 `wraplength=300`，运行时继续按面板宽度重排。
2. 普通 Layout Y 精修位移上限原来固定为 `0.45×行高`，现在增加
   `separator_y_max_shift_ratio`，置于【横线 Y 精修】，默认值仍为 `0.45`。
3. `paddle_separator_safety_px` 说明纠正为实际 OCR 边界候选安全距离，
   不再暗示其能控制普通 Layout 的全部最终横线。
4. 更新旧测试对【横线 Y 精修】独立标签的归属要求。

**需要强调：自动审计产物是静态证据，不等于 UI 自动化或 PDIC 输出等价证明。**
静态字段位置可能漏掉手工构建的窗口与动态 `getattr`；数字比较列表包含
数学安全判据，必须人工筛选后才能成为可修改参数。剩余需运行 Windows
界面交互/跨进程、保存/重开、20 页 PDIC 严格比较等测试。未经实际故障
证据，不擅自开放 CJK 符号与大字头识别的几十个耦合阈值。
