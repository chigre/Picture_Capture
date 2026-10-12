# Layout 参数可靠性审计：Profile 与逐页普通画线（2026-10-12）

结论：**尚不能宣称所有自动版面参数正确**。已修复两个明确定量问题（字高按页高推测、行间空默认值冒充测量），还发现一处逐页物理行过滤契约不一致、一处 Paddle 跨栏排序的行距低估问题。其余几何字段仍需完整真实页面/多种版心测试。

## 分别审阅两条计算路径

Profile 多页：`profile_setup.analyze_representative_pages` → `profile_layout_bootstrap.detect_profile_layout_parameters` → `_projection_layout_estimate` → `aggregate_layout_estimates` → `apply_analysis_suggestion`。为了速度而不用 Paddle，几何依赖像素投影，不能把所有字段视为实测。

逐页：`dictionary_page_layout_policy.resolve_page_layout_policy` → `layout_detection.detect_layout_parameters`（Paddle+Projection 融合/只有其一）→ `layout_profile_anchor` → Page Design / Physical Layout。逐页自动开关只让**勾选字段**采用测量，若有Profile锚定，会将稳定模板参数拉回项目原值。

| 字段 | Profile初始数据来源 | 逐页流程／残留风险 | 本PR措施 |
|---|---|---|---|
| columns | 横向墨迹+留白结构；多页众数 | 锚定层可将逐页自动列数恢复为Profile值；需明确UI契约 | 未自动解除列数锚定；防止稀疏首页误改 |
| start_y | 前38%页中最大的早期留白的下缘，多页汇总再减5px | 标题、正文内大空白可能让Y跳错；Profile页眉/排除区另行处理 | 尚需独立证据复核，不能宣布准确 |
| manual_x | 最早水平墨迹位置 | 当前有多栏语义共识注册；栏间斜竖线与页面漂移仍是风险 | 已增加竖线排除 |
| column_width | 投影空白区、其他栏宽和中位数 | 受Profile锚定（约1.5%或6px）限制，不适用于任意混合DPI | 尚需多分辨率测试 |
| gutter | 竖线/白沟，失败可退约列节距的5.5% | 受Profile锚定（约8%或3px）限制，倾斜竖线会污染 | 已增加斜线轨迹排除 |
| character_height | **旧** `round(原图高度×0.008)`；多页汇总也保留同源偏差 | Paddle框/投影融合，原有字符高回退漏触发，后续又被旧Profile夹紧 | 已使用全分辨率稳健墨迹高，且检查来源/样本数/多页一致性 |
| row_padding | **旧** Projection固定1px | **旧** Paddle跨两栏混排框的Y起点求节距；错行时系统低估 | Profile不再自动采用固定值；Paddle在各栏内测量，证据不足保留旧值 |
| bottom_y | **旧** 约原图高97%，不是末行观测 | 普通Layout会依据实际物理行的最后墨迹重新确定，且受页脚区域约束 | 已有运行时重算；Profile显示仍是启发式近似 |
| separator | 固定X长竖线/白沟检查 | 倾斜竖线的判定不应依赖固定X | 已增加斜竖线追踪供几何及first_x |
| 每行Indent | 不属于跨页固定模板值 | 物理行若缺失，无法靠后续角色修复；有竖线污染first_x风险 | 已统一基础PageDesign、逐页Policy、X注册 0.26–1.90倍物理投影行高契约 |

## 五本用户训练包，34页冻结数据

| 词典 | 页数 | Profile字高 | 源图 H×0.008 | Profile行间空 |
|---|---:|---:|---:|---:|
| XDHYCD | 3 | 17 | 17 | 1 |
| 葡汉 | 10 | 22 | 22 | 1 |
| 三民 | 10 | 46 | 46 | 1 |
| 新时代西汉（本包1页） | 1 | 30 | 30 | 1 |
| 字典𡨸喃摘引 | 10 | 25 | 12 | 1 |

四本存档字高与旧按页高的固定比例完全一致，表示具有同源系统性风险，**不代表四本的字高实际都错误**。XDHYCD完整三页另用图像墨迹核对为29–30px，行首节距约42–43px，明显区别于存档17px。注意 `row_padding` 原Paddle定义是“行节距减框高”的**一半**，与某些遗留`row_height=character_height+row_padding`调用的直观含义不同；为了避免破坏旧切图语义，目前先保持这一数值约定并在无实测时不自动覆盖。后续应统一`glyph_height / line_pitch / interline_gap`三个概念。

## 验证及仍需开展

* PR增加合成双栏错行测试，验证旧全页混合Y值导致的1px错误，和新各栏物理行节距测量。
* Profile新增真实墨迹证据、样本覆盖率、混合规模检查；只有可靠观测才能改写原来的页高0.8%启发值。
* 行高过滤条件已同时修复在基础PageDesign、逐页Policy、页面X注册，避免仅修某一路调用而旧路径仍丢实际30px行。
* **尚未在完整软件中对34页真实扫描重新执行新PR的普通画线并产生新叠加图/逐页TP、FP、FN，不能把这些单元测试结果当最终模型性能。**
* Profile start_y / bottom_y、gutter和宽度的鲁棒性以及逐页自动列数的UI契约仍须专项审查；不同分辨率代表页不能盲目中位数聚合。

受版权保护的原始扫描未提交至仓库。新分支保留Draft，不自动合并main。


## 续审：分隔线检测与证据传递（2026-10-12）

### 已定位并提交的额外问题

1. **Profile 中央分隔线自动判断存在逻辑断路。** `detect_profile_layout_parameters()` 强制 `layout_columns_policy="detect"`，而旧 `_projection_layout_estimate()` 仅在 `fixed` 分支写入 `separator_centers`，造成Profile检测到分栏后 `separator_x` 仍必定是 `None`。现为detect分支补入保守的竖线检测，并将未证实有竖线的Profile建议改为 `auto`（而不是断言 `absent`）。这只是修复证据丢失，不代表已经可靠处理各种倾斜分隔线。
2. **组合式Layout漏传字高证据。** `layout_composition.infer_composed_physical_page_layout()` 原先调用 `anchor_resolved_layout_to_profile(...)` 未传 `estimate`，上游 `observed_character_height` 即使恢复了真实29–30px，也会再次被Profile 17px附近的夹紧规则拉回。已改为 `estimate=estimate`，使经证实的墨迹高度在显著偏离旧Profile时可保留；不可信单页OCR框仍受正常锚定。
3. **逐页仅投影成功时不会触发字高补救。** `reliable_fusion+projection_only+paddle_error=...` 没有 `fallback=character_height` 标志，却仍使用页高0.8%估计。已允许这一来源进行全分辨率、足量物理行证据的高度测量，无合格证据时不随意修正。
4. 新增 `tests/test_layout_parameter_chain_20261012.py` 对上述三条路径设回归门槛；源代码已提交，但**测试状态以最新GitHub Actions结果为准，不能把创建测试等同测试通过**。

### 仍开放的参数可靠性边界（不应认定已完成）

| 参数或链路 | 剩余风险 | 建议验收准则 |
|---|---|---|
| Profile栏数 | 横投影的空隙可能把分隔线误当新栏；多页众数也可能选错 | 真样本栏数逐页一致、与人工栏模板一致；证据不足不自动应用 |
| Profile起始Y | 前38%最大留白策略会误选标题下/正文内空行 | 真正文首行附近定位；按页眉/无页眉/首页/普通页分组评估 |
| Profile页底Y | 97%页高启发式并非末行位置 | 用各栏最后实际墨迹行及显式页尾排除约束独立核对 |
| Profile栏宽及栏间空 | 最后栏宽强制中位数、栏距5.5%兜底，斜线及不齐栏受影响 | 每栏左右边界和真实留白均验证，记录每个值的来源 |
| Profile代表页融合 | 数值直接取绝对px中位数，无图像分辨率相容门槛 | 同源分辨率检查；不一致时分组或拒绝自动聚合 |
| 逐页栏数与行间空 | 选了自动，`layout_profile_anchor` 仍固定恢复Profile原值 | 澄清“Auto=测量生效”还是“Auto仅诊断”；UI与实际输出必须一致 |
| 逐页字高 | Paddle+投影共同成功但没有标记height fallback时，实测字高纠偏并非总会触发 | 带独立墨迹行证据的逐页比较/来源门控 |
| 行高/行距/行间空语义 | `row_padding` 的旧计算为半个额外节距，但`row_height=character_height+row_padding` | 显式区分glyph-ink-height、top-to-top line pitch和full interline gap，先做兼容迁移 |
| 右栏Indent与词头线 | 行过滤、栏定位、竖线排除及语义家族恢复相互影响 | 按列统计物理行召回、entry/body两类INDENT和最终PDIC TP/FP/FN |

**真实图像端到端重新验证仍未完成**：需用原5套34页训练包在此分支重新跑Profile建议、逐页测量、Layout叠加、普通画线与PDIC对照。不要以合成单测或仅凭之前的人工观察宣布全部参数正确。PR继续保留Draft，绝不因本次续审直接合并主分支。
