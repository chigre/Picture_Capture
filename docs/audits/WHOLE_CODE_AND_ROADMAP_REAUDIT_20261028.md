# Picture_Capture 全库静态架构复审与路线图重排（2026-10-28）

> PC-CQ v1.3.0，关联 [#503](https://github.com/chigre/Picture_Capture/issues/503) / [#562](https://github.com/chigre/Picture_Capture/issues/562)，**唯一活跃开发 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663)**。此文是源码树全量清点 + 高风险执行路径定向审查，不是对每行代码形式验证或真实词典验收。以下基线指标截至提交 `66ad88c276b6965c075eeb72583b42dd0aa7f3ac`；后续 HEAD 必须重新核算。

## 1. 范围、证据分级与可复查快照

- 受检 main 比较基线：`ec20989ea8c026cca5337293e67850b6b6df30f2`（Git tree `540e5bca7412c1387f60b02a463121818d543369`）。
- 受检合并 Draft PR #663：`66ad88c276b6965c075eeb72583b42dd0aa7f3ac`（Git tree `3d75640dfc5769d06417642712ee28be40541328`）。两个树的 Git API `recursive=1` 均为 `truncated=false`，包括根文件/子模块/测试的完整路径和 Git blob 尺寸。
- 变更规模：**711 commits、551 changed files**（GitHub PR 元数据），不是 551 个独立已验收功能。main→PR `src/picture_capture/**/*.py` **398→551**；`tests/**/*.py` **443→614**；测试数是测试文件数，不是通过数、功能覆盖率或独立金标准。
- 本次定向阅读的实际 owner：`proofreading/transactions.py`、`ui/review_candidate_delete_actions.py`、`ocr/batch_publication.py`、`ui/focused_filter_workflow.py`、`ocr/headword_core_runtime.py`、`runtime/processing_core_runtime.py`、`scripts/architecture_guard.py`、`.github/workflows/ci.yml` 与规划/状态/验收规程。
- 当前确证自动化：[PR #663 六平台 CI #40559523622](https://github.com/chigre/Picture_Capture/actions/runs/40559523622) **completed/success 6/6**，含 Risk-tier 总门禁；[OCR Platform Smoke #40559523187](https://github.com/chigre/Picture_Capture/actions/runs/40559523187) **completed/success 3/3**。这仅认证旧的、精确 `66ad88c276b6965c075eeb72583b42dd0aa7f3ac`，**不覆盖本次文档修订新 HEAD**。Documentation architecture check 因 CI 风险分类可为 skipped，不应计作执行过。
- **未执行**：真实 Windows 人工词典页扫描、OCR/普通/组合模式、R3 20 步 Undo/Redo、候选 checkbox/manual_selection 交互、自动保存、跨 SECTION/关闭重开、PDIC/PPP/crop 原图坐标一致性、崩溃/断电破坏性测试；没有当前真实词典 P/R/F1、人工校对节时或性能加速结论。
- 审计等级：**E1** Git tree/可定位源码事实；**E2** CI 合成与跨平台测试；**E3** 用户真实工作流/词典实测（当前无证据）。不可用 E2 代替 E3。

## 2. 结构体检：根目录清理取得进展，但风险已转移至大 owner

| 计量项目 | main | #663 合并 HEAD | 结论 |
|---|---:|---:|---|
| `src/picture_capture/` 根目录直接 `.py` | 15 | **5**（含 `__init__.py`/`__main__.py`） | 已迁移 10 个根模块；不再以旧报告的「15→10」作为最新进度 |
| `app.py` Git blob 字节 | 348,586 | **152,962** | 仍然庞大，是下一轮有限责任抽取的优先入口 |
| 源码 `.py` 文件数 | 398 | **551** | 拆分很多，不等于耦合或复杂度已经消失 |
| 测试 `.py` 文件数 | 443 | **614** | 防回归资源增长，不等于测试覆盖率测得提升 |

剩余根模块为 `app.py` (~153 KB)、`ocr_channel.py` (~11.8 KB)、`models.py` (~7.8 KB)、`__init__.py` 与 `__main__.py`。**禁止用持续搬运目录文件数作为唯一 KPI**；应核查调用方向、运行时单一 owner、猴补接口/反射绑定、Windows spawn 导入、PDIC/像素格式 parity。

按文件字节观察的热点（不是性能热点）：`ocr/headword_core_runtime.py` 81,939；`ui/settings/help_catalog.py` 68,683；`ui/workspace_tools.py` 61,016；`ui/preprocess_workflow.py` 59,042；`ocr/candidate_filter.py` 58,684；`preprocess/pipeline.py` 55,038；`ui/review_workspace_workflow.py` 54,004；`runtime/processing_core_runtime.py` 53,403；`preprocess/orthogonal_dewarp.py` 51,544。架构守卫 `scripts/architecture_guard.py` 自身约 147 KB，长期需将重复的静态规则表抽至数据驱动约束，但不得一次移除历史安全守卫。

主要代码子树体量（Git blob 字节加总）：`ui/` 约 1.75 MB、`ocr/` 0.69 MB、`preprocess/` 0.51 MB、`profile/` 0.40 MB、`layout/` 0.38 MB。当前更应控制 UI→OCR→持久化循环依赖与 sidecar 责任边界，而非再造 facade。

## 3. 跨子系统静态审计发现（严重性和验证边界）

| 风险级别 | 模块 / 代码证据 | 判定与剩余缺口 | 下一步证据门槛 |
|---|---|---|---|
| **P0 事务完整性** | `proofreading/transactions.py`：`_create_exclusive_recovery_marker`、`_stage_recovery`、`_verified_recovery`、`recover_pending_for_page`、`ReviewSessionHistory` | 已通过 `O_EXCL` 独占创建、非普通标记拒绝、逐文件 before/after 复读和 v1/v2 原路径绑定加固；但没有整个 PDIC/manual_selection/simplified 事务的全程 OS 锁、目录持久化或跨文件原子 CAS。部分标记/突然掉电需人工恢复。 | 候选归属/编辑器完整性与并发故障注入；明确哪些操作不可 Undo，拒绝猜测并保留标记；真实 Windows 逐项验收 |
| **P0 双发布协调** | `ocr/batch_publication.py`：多次 R3 marker 拒绝、OCRed 先发布、PDIC 后发布及失败补偿 | 对 OCRed/PDIC 存在中间态、最后一次版本读取之后仍可竞争；现有防护是乐观核验，不是单个原子事务。不得直接引入无协议的自动删除/重写。 | 故障矩阵覆盖导出前/中/后，PDIC 写前/后、R3 写前/后和断点；文件字节/异常因果/人工内容保留，独立人工 SOP |
| **P0 验收债务** | `ui/review_candidate_delete_actions.py` 仅在提交后更新 candidate.selected、Entry 和 checkbox；`ReviewSessionHistory` 最多20步 | 工程有 candidate-linked 可撤销路径，但可逆性由严格 snapshot/owner 决定，不能宣称**所有**候选和复杂混合编辑都能成功 Undo/Redo。真正 Windows GUI 未验收。 | #503 runbook：候选选择/删除、20次 Undo/Redo、Redo 分叉、FocusOut、翻页、关闭重开、人工编辑，保存重读三文件及界面一致 |
| **P1 UI/架构** | 余留大 `app.py`，`ui/review_workspace_workflow.py`、`ui/focused_filter_workflow.py`，`ui/preprocess_workflow.py` | UI controller 和耗时工作仍多；提取时最容易损坏 Tk 线程约束、猴补调用时依赖、跨页异步结果和 Windows spawn/pickle owner。 | 每个 owner 抽取前后跨 OS 行为金样本、Tk smoke、F821、import identity、启动及 save/reopen |
| **P1 判定 parity** | `ocr/headword_core_runtime.py`、`runtime/processing_core_runtime.py`、`quality/`，原 R5 评分抽取 | #562 已将多处评分/运行时 owner 迁出根目录，故 R5 不是「所有工程都未开始」；但仍需对 score（结构/视觉）与 q（OCR 仲裁质量）分别建立无副作用、可序列化输入/输出 **逐字段 parity 证据**。 | 固定输入的 accept/score/q/reason/原图 X/Y/顺序逐字段一致；不改权重/门槛 |
| **P1 质控优先级** | `ui/focused_filter_workflow.py:run_focused_filter` 已有 PDIC/OCR JSON 筛选、批次预加载/渲染 | 存在可复用筛选基础，但没有证据证明原 R4 priority/normal/unknown 完整分层及可解释原因已经上线；不要重复实现筛选器。 | 先只读可解释风险函数；过期来源/不唯一 owner→unknown；可关闭队列，不改变默认原始页序 |
| **P1 安全测试治理** | `.github/workflows/ci.yml`、`scripts/architecture_guard.py`、`scripts/change_architecture_guard.py` | 有 Python 3.13/3.10、Windows/macOS/Ubuntu、Tk 合成 smoke、建筑守卫及 OCR Smoke；#663 的 551 变更文件/711 提交导致审查面很大。CI 成功不是人工功能验收或 CodeQL 必然成功。 | 每一批以 exact HEAD 记录变更→测试→运行；docs-only 分类要说明 skipped；合并前固定 SHA 安全审查、风险分层和人机门槛 |
| **P2 真实数据依赖** | 原 R2/R6/R7/R8 合同与 #483 W1–W11 | 没有明确人工核验的可靠金标时 R6 训练/影子部署保持 BLOCKED；性能优化要实际 profile，R8/PR-B 仍用户延后。 | 保留匿名/本地数据权限与词典级隔离，显式重新授权后方可动真实扫描或训练 |

**审计不是新发现所有路径均有可触发缺陷。** 上述「剩余缺口」包括已知系统设计非原子性、手工未验收与高风险边界，均需通过有目标的故障注入或真实用户操作进一步确认；不要把源代码可能性冒称已复现 bug。

## 4. v1.3.0 后续执行顺序（单活跃 PR，内部工作包）

| 内部工作包 | 优先级 / 依赖 | 本轮以后必须交付的成果 / DoD |
|---|---|---|
| **G0 合并版证据冻结** | P0，立即 | 锁定 #663 精确 HEAD，核对相对 main 的 root owner / 变更清单，CI 6/6 + OCR 3/3 + 评审/CodeQL 状态分别列明；人工验收单独为 OPEN。每新增生产改动重复本门禁 |
| **G1 R3 恢复最终收口** | P0，首个代码包 | 整理人工输入、candidate_id/checkbox、manual_selection/PDIC/simplified、Undo/Redo/跨页复原状态机；**只**修会覆盖校对数据的缺口。补文件中断+竞态+错误对象/恢复拒绝测试；明确真人 Windows 操作清单和证据归档。#503 不因 CI 成功关闭 |
| **G2 架构 owner 压缩** | P1，与 G1 不写同一文件 | 以 `app.py` 及运行时大模块为主，选择一个真实可抽离的责任 owner，一批一个行为边界；保留对外 API、猴补可见性、spawn、坐标、序列化；root count 不作为唯一验收 |
| **G3 R5 parity 抽取 + R4 opt-in 优先校对** | P1，G1/G2 界面合同稳后 | 分别建立 scorer 输入快照（score 与 q）、布尔/原因/像素坐标 parity；利用既有 focused_filter 添加纯函数优先级，仅在明确 opt-in 时改变顺序，来源 stale→unknown，保持原序默认 |
| **G4 R2 证据/AC-GAP 补审** | P1，穿插只读 | 清点 #483 W1–W11 尚未做的真机项、已合并 R2 的标签合同以及旧 A/C 未定义需求；无法可靠界定一律 blocked，不推断金标 |
| **G5 R6 离线/影子研究** | P2，**条件阻塞** | 只有 R2 真正有 verified 且词典级开发/外部集划分时才允许离线基线比较。shadow 默认关、只读、不写 PDIC；无标签必须继续 blocked |
| **G6 R7 性能/坐标 + R8** | P2，依赖证据/用户授权 | 先 cold/warm/CPU/GPU/RSS profiling 和 source↔transformed round-trip，单瓶颈优化；R8 完整扫描 PR-B 仍 **deferred_by_user**，不能自行启动 |

每一轮执行：先 **HEAD/CI/并发检查** → 只选一个无重叠 owner 的工作包 → 测试反例 → 实际修复/文档 → 提交 → latest-head CI（含 Windows/macOS/Ubuntu、Py3.10/Tk、OCR Smoke，按风险分类记录）→ 更新 Issue #503/#562。**只保留 #663 为唯一活跃开发 Draft PR**；原 #664 关闭未合并，但其 10 个提交、6 个文件由 #663 双父提交 `66ad88c276b6965c075eeb72583b42dd0aa7f3ac` 保留。不得另开重复 PR、不得自动 merge/Ready。

## 5. 明确的停止条件 / 人工发布门槛

- 无 main 上的真实用户词典人工验收，不标 R3 verified、不关闭 #503/#483、不把 R4「优先推荐」等同识别提升。
- OCRed/PDIC 或 R3 标记出现不可解释第三方 bytes/不可读状态，拒绝单侧回滚/无主覆写；先保全人工数据。
- 无当前版本真实词典配对 P/R/F1，不声称精度上升；无基准 profile 不声称变快；旧历史缓存的 96.86% 不是当前版本指标。
- Windows/Tk/original source X/Y/PDIC/PPP/SECTION/crop/export，相关功能在真实页验证前仅为 E2，不能 E3 发布。
- 单 PR 已包含数百文件、历史 700+ 提交，重大架构改动必须在这个 Draft 内用清晰内部批次、测试与记录降低审核难度；若出现不能安全整合的冲突或代码所有权不明，应停止该包而非强推。

## 6. 审计局限

此次无本地可执行真实仓库镜像、原始扫描数据或真人 Windows GUI 会话；没有运行内存泄漏/性能 profile、静态类型全量审查、SAST 新扫描、模型精度基准或测试覆盖率统计。已结合**完整 Git tree 清点**、**关键事务/架构/CI 路径源码阅读**和**已有精确 HEAD GitHub CI 结果**，其余目录仍需按风险选择代表性 owner 深入审查。不要从「测试文件 +171」推断质量/性能提升。本文件是全局风险地图和执行门槛，不是宣告整个项目通过验收。
