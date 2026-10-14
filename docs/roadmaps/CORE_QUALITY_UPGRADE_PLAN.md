# Picture_Capture 核心质量与校对效率升级：总计划（PC-CQ-20261014）

> 状态：**规划已固化；尚未开始生产代码升级**。版本：1.1.0。起草：2026-10-14。  
> 此文档定义目标、依赖和验收合同；同目录的 CORE_QUALITY_STATE.json 是机器可读执行检查点；CORE_QUALITY_RESUME.md 是跨会话恢复入口。  
> 原始评估依据：用户提供的《Picture_Capture 核心功能改进思考.md》；经过对 GitHub main 的源码再核查，以下内容**不是逐字采纳原评估**，明确标注了补充/纠正后的设计判断。

## 0. 项目宗旨、范围、起点

**终极目标（两项）**：（A）提高真实词典扫描中词头横线定位的 Precision、Recall、F1，兼顾 Y 定位质量；（B）降低在质量不退化前提下，每 1000 个经核验词条的人工校对耗时。二者必须按词典分别展示，不能以总体分数掩盖某一本词典的退化。

**持续性约束**：用户先前确定 PR-B（真实扫描全页基准）延后；在此之前，允许做回归基础设施、数据血缘、人工反馈、撤销、架构纯重构和无真实扫描依赖的测试，不得把历史缓存 F1 冒充新版本效果。训练/性能优化不得抢跑。

**核查起点**：GitHub 仓库 chigre/Picture_Capture，main 提交 7134bf68cf2595f1db61d7d410d7ac51290318ca。#475（最终 PDIC 决策审计与保守续行救回）、#476（opt-in 白缝 Y 核验）、#477（opt-in 分页续算/原始 Tesseract 缓存/懒诊断）已合并。main CI 运行 38443534599 成功。该 SHA 是**计划制定时的基线**，不是之后工作的固定 base；开始任何实施之前必须重读 GitHub 的实时 main 和 CI。

**工程合同**：遵循仓库 AGENTS.md、docs/architecture/CHANGE_POLICY.md、docs/refactor/REFACTOR_STATUS.md、docs/refactor/RESUMABLE_EXECUTION_PROTOCOL.md；这份计划不改变正在进行的架构 Phase 13，也不重开已完成 PR。跨会话不以聊天记忆为进度依据。

### 硬性保护条件

1. 不擅改现有 PDIC/PPP/Project Profile/SECTION 文件格式及公共 facade；如确有迁移需求，必须作为独立、经批准的 PR 和兼容测试。
2. 自动重跑不得默默覆盖人工编辑；保留 #475 的保存前 PDIC 备份与最终决策审计、失效保护。OCR 缓存只是预最终阶段的证据，**真正的已保存 PDIC 才是可见输出**。
3. 实验开关默认关闭：paddle_peer_style_rescue=False、separator_y_ink_safe_gap=False、ocr_resume_completed_pages=False、ocr_cache_tesseract_raw=False、ocr_lazy_tesseract_diagnostics=False。新增学习、校对排序开关亦默认关闭；不要改变已有成熟选项的默认值。
4. 不放宽 scripts/architecture_guard.py 中的任何大小上限、黑名单和基线以躲避 CI；app.py 仅做薄调用/组合，业务逻辑放到独立 service/helper，依赖方向不能反向。
5. 一个主题 PR 可以包含约 **2–4 个紧密关联的安全工作单元**，每项独立验收；先补失败回归测试，再做同一领域的实现及 CI。每次仅推进一个活跃的主题 PR，不得将无关功能、数据迁移或高风险重构硬绑在一起。
6. 真实扫描、OCR 缓存、个人项目及带版权图片不直接提交公开仓库。特征/标签也要审查版权、隐私和授权；不可声称没有像素就自然无版权风险。
7. 所有新记录须区分：人工确认真值、人工操作但未全页复核、自动推定、未知/歧义；自动推定**禁止**直接当监督学习金标准。
8. 任何不确定的合并冲突、数据损坏风险、平台 CI 红灯、并行开发、设计歧义或不可逆迁移，都停止自动推进并在 STATE 中记录 blocker；不可继续越过下一个阶段。
9. 如果本计划与 GitHub 实时运行状态冲突：以**实时代码/PR/CI 事实为准**，提出计划修订 PR，不得悄悄更改目标或宣称已完成。

## 1. 一张可执行阶段图

| 阶段 | 目的 | 工作单元（可按主题合并成一个 PR） | 验收门槛 | 真实扫描要求 |
| --- | --- | --- | --- | --- |
| **R0 基线保护** | 排除跨 PR 隐患、锁定默认行为 | R0.1 fingerprint 失效保护；R0.2 opt-out/PDIC 回归 | 指定反例测试通过、默认行为逐项相同、全 CI 绿 | 无 |
| **R1 测量与 Golden Set 设施** | 准确率与错误来源可重复衡量 | R1.1 指标口径；R1.2 特征级 CI fixtures；R1.3 基准 manifest / runner | 指标明确；确定性夹具闸门；绝不引用历史值当当前性能 | 先无，实际 F1 延后 |
| **R2 人工反馈闭环（只记录）** | 可靠获取标签与错误归因 | R2.1 人工事件模型；R2.2 OCR/PDIC/事件关联；R2.3 安全导出/质量审计 | 可证明标签出处、未知不误标、重新打开一致 | 无 |
| **R3 可撤销校对事务** | 防误操作、减少人工成本 | R3.1 ReviewWindow 单事务 Undo；R3.2 Redo 与复合编辑 | PDIC、人工覆盖、辅助缓存同步恢复；无数据丢失 | 无 |
| **R4 诊断驱动的校对顺序** | 优先处理高风险页/候选 | R4.1 确定性风险分层；R4.2 可选队列与耗时记录 | 默认排序不变；可解释、可关闭、跨 SECTION 不错配 | 初期无 |
| **R5 评分逻辑独立化** | 安全扩展算法，不增加大模块 | R5.1 特征快照/纯函数；R5.2 门控/打分小范围搬移 | parity 100%；公共调用兼容；架构守卫不放宽 | 无 |
| **R6 离线模型预研** | 验证机器学习是否值得启用 | R6.1 数据集门禁；R6.2 baseline/消融/校准；R6.3 shadow-only | 按词典外部验证、不泄露训练数据、可完全回退 | 有核验标签后才可评估效果 |
| **R7 性能与几何专项** | 解决测量证实的瓶颈与变换一致性 | R7.1 profiling；R7.2 单热点优化；R7.3 坐标变换合同 | 性能数字有环境记录；逐页结果不变；可逆迁移 | 真实性能决策需扫描 |
| **R8 PR-B 真实扫描基准与上线门禁** | 用真实数据决定启用与否 | R8.1 标注复核；R8.2 三模式全页对比；R8.3 逐词典上线判定 | 当前 main 重跑、独立标注、F1/Y/耗时/校对成本全部报告 | **必须；按用户决定延后** |

**阶段顺序**：R0 → R1 → R2；R3 与 R4 在 R2 的标签模型稳定后依次开展；R5 可在 R1 指标稳定后规划但与 R2/R3 不并行改同一模块；R6 以有质量的 R2 标签 + R1 基准为先决条件；R7 的优化必须先有真实 profiler；R8 延后但不能宣称其工作已完成。阶段是依赖关系，不是承诺的日期。

### 1.1 主题批次计划（v1.1.0）

**一个 PR ≠ 一个子任务**。按照共同数据流、共同测试边界和共同回退路径，将约 2–4 个关联子任务合并交付；关联性比数量重要。每个子任务保留 R 编号、独立测试和验收结论，不为凑数量扩大影响。一个主题最多一个活跃生产代码 PR；任何数据格式迁移或架构重大抉择必须单独审查。

| 主题 PR 批次 | 关联工作单元 | 一次交付的范围 | 限制 |
| --- | --- | --- | --- |
| **B0 已合并** | R0.1 | #479 OCR 恢复指纹补强 | 等合并后 main CI 通过才 verified，不重复开 PR |
| **B1 质量门禁** | R0.2 + R1.1 + R1.2 + R1.3 | 既有 #475–#477 回归、统一 TP/FP/FN/坐标口径、无扫描 Golden fixtures、基准报告来源识别 | 只增强测量与测试，不能改生产判定；过大可拆 B1a/B1b |
| **B2 反馈数据** | R2.1 + R2.2 + R2.3 | 人工编辑事件模型、OCR/最终 PDIC/人工关联、可靠标签与只读导出 | 只记录，不自动学习，不改 PDIC |
| **B3 校对事务** | R3.1 + R3.2 | 撤销/重做、保存和候选/人工覆盖状态同步 | 风险高，需要编辑/重启/持久化测试 |
| **B4 重点校对** | R4.1 + R4.2 | 可解释风险分层、可关闭优先队列、时间/操作成本记录 | 默认排序、原有校对不变 |
| **B5 判定抽取** | R5.1 + R5.2 | 评分特征快照、打分与门控纯函数、parity 验证 | 不调阈值、不放宽架构守卫 |
| **B6 离线模型** | R6.1 + R6.2 + R6.3 | 标签有效性门槛、离线模型比较、只读 shadow 输出 | 无真值则 blocked；过大拆为训练与影子评估 |
| **B7a 性能** | R7.1 + R7.2 | 真实 profiling 与一个确证热点优化 | 缺真实数据不可宣称速度改善 |
| **B7b 几何** | R7.3 | 源图/变换图/标记的坐标合同 | 独立高风险 PR，不混同性能 |
| **B8 暂缓** | R8.1 + R8.2 + R8.3 | PR-B 真实扫描验证 | 仍需用户另行授权 |

**批次顺序**：B0 的 post-merge main CI → B1 → B2 → B3 → B4 → B5 → B6 → B7a/B7b；真实数据不足时 B6/B7 允许 blocked，但不得自称 verified。依赖、平台与单元 DoD 仍按 R0–R8 原计划。若 B1 等范围明显超出可审查范围，可拆成两份独立的同主题 PR，先在 STATE 中更新批次映射，不能悄悄遗漏子任务。

**执行提速**：一次唤醒/会话可连续实施同一主题 PR 内的多个子任务，不必每完成一个子任务就等下一小时；PR 提交后一次性运行 CI。若 CI 进行中，不开启第二个生产 PR、不频繁轮询、不制造长篇状态聊天。所有已完成子任务必须提供明确的测试记录。

## 2. 各工作单元的具体实现合同

### R0 — 当前下一步（最高优先级）

**R0.1 修复 #477 断点恢复算法指纹覆盖不完整**

- 现有调用：app.py::_detect_pages → ocr_page_resume.validated_resume / write_page_resume；当前 _algorithm_environment_key 仅包含 processing.py、paddle_headwords_core.py、evidence_fusion.py、page_understanding_fusion.py 及部分安装包版本。
- 风险：若仅修改 ink_safe_separator.py、separator_y_refinement.py、ocr_tesseract_runner.py、ocr_lazy_secondary.py 等参与检测的实现，旧 checkpoint 仍可能校验通过。该项属于**源码推导的待复现风险**，不冒充已测实故障。
- 改法：在 src/picture_capture/ocr_page_resume.py 定义明确版本化的 **检测代码依赖 manifest**（所需的主入口、共享 Y、OCR runners、融合、判定、相关模型与几何算法等），将 manifest 版本及相关源码/运行依赖组成稳定哈希；禁止依赖仅 mtime/文件长度的捷径。涉及外部 OCR 可执行程序时，规定稳定可取得的版本或签名；取不到足够签名时失效关闭（不跳过），而非默认为可用。
- 性能约束：进程内缓存计算一次，禁止每页重复哈希所有源码/可执行文件；保留单页图片/PDIC/规则的字节级指纹，不改变强制刷新语义。
- 测试：相同数据命中；改源图单字节/PDIC/规则/Profile/SECTION/模型版本/关键模块内容均 miss；断点损坏、缺失依赖、强制刷新、并行/原子写异常均安全；现有测试 tests/test_ocr_page_resume_20261014.py 扩展。
- **DoD**：默认关闭时路径完全不变；打开时所有上述反例均不得跳过；不改变 PDIC 和自动检测算法输出。

**R0.2 三 PR 合并后行为契约回归**

- 把 #475 决策审计、保存前备份、#476 安全 Y、#477 三开关整合为默认关闭的专门回归组；测试 AppSettings 新实例、旧 JSON 加载、显式开启→保存→关闭→重启、设置中心绑定和帮助文字。
- 检查 OCR/融合/普通模式共享路径，确保关闭实验功能时与此前既有模式等价；新旧兼容测试及编辑 PDIC 后 sidecar 失效、备份不被覆盖、保存失败停止处理。
- 不把“实验开关关闭”误解为关掉原有成熟的 paddle_refine_separator_y；也不擅自改变已记录旧项目的用户设置。
- **DoD**：显式关闭测试 + 持久化/重开测试 + 三平台 CI；只修集成问题，不顺便重写模型。

### R1 — 建立可复用的验证仪表

**R1.1 定义唯一指标合同**。在独立评估模块复用 ordered_marker_matching.match_ordered_markers：每页同列、保持阅读顺序、一次一对一匹配；固定坐标空间与容差定义；定义 TP、FP、FN、P、R、F1（含 0 分母处理）、Y 误差中位数/P95、越过墨迹/切字、每页耗时。检测指标和文字 OCR 正确率必须分开；普通/OCR/融合模式分别输出。基准必须报告字典级别及 pooled 值、人工真值审核状态、版本、设置/引擎、运行环境、输入哈希。评估器自身应有密集相邻行、跨栏、重复候选、坐标变换、空页的确定性反例。

**R1.2 引入不依赖原始图片的 feature-level fixtures**。来自模拟/经授权特征与候选审核结果，重点测试 parser、条件门控、OCR 仲裁、最终 PDIC 关联，不能声称覆盖实际像素/Otsu/字形。CI 以正确性和结果不回退为硬门禁；实际 F1 尚无当前 main 的完整基线，**不设置虚构的 F1 阈值**。维护 fixture schema_version、source/provenance、label_status、算法适用阶段。

**R1.3 统一现有脚本报告**。已有 scripts/detection_benchmark.py、scripts/benchmark_training_archives.py（旧缓存审计）以及 scripts/run_training_archive_full_benchmark.py（实际重跑）。报告需明确 run_type=historic_cache / current_detector / synthetic_fixture，防止误引用；输出结构化 JSON 和 Markdown 摘要，便于对 PR 做基线差异比对；真实扫描 runner 先保留接口，不要求在 CI 下载用户图像。

### R2 — 人工数据从“覆盖记录”变成“可审计学习材料”

**R2.1 建立版本化事件 sidecar（append-only 逻辑）**，建议新建独立领域模块如 src/picture_capture/proofreading_events.py，而非继续增大 app.py。最小字段：schema_version、project/page stable ID、operation_id、time、action (add/delete/rename/move/select/deselect/verify/undo/redo)、source/coordinate_space、before/after、candidate_id（如有）、image+OCR+PDIC/version fingerprint、verification_status（verified / explicit_action_unverified_page / inferred / unknown）。维护稳定 Entry identity，禁止用当前列表行号关联最终坐标；敏感信息不进入遥测/网络。

**R2.2 把 #475 final_decisions 与人工动作关联**。明确 pre-OCR observation、post-Layout final saved PDIC、human-edited PDIC 三层。重复 candidate_id、同距关联、人工重排等出现歧义，输出 unknown，不猜关联；PDIC 校验不匹配时标记 stale 并禁止训练使用；历史 manual_selection 只在有确凿来源时映射，不自动批量提升为金标签。

**R2.3 只读的数据质量与导出**。统计 verified 正负标签、只改文字/只改位置/新增真漏检、候选未知、按词典/SECTION 分布；提供本地可选择导出，不自动上传，采用 privacy-first 最小字段，附有数据集版本/hash/许可声明。训练与验证分割所需的词典/project ID 必须可靠。

### R3 — 校对编辑事务化

**v1.2.0 阶段授权（2026-10-15）：** 用户明确决定「R2 暂不验收，继续 R3」。这是对原严格阶段依赖的**局部豁免**，只允许从 B2/R2 的工程增量进入 B3/R3；B2 仍 `in_progress`，真实 Windows W1–W11 验收与 #483 不关闭，任何 R2.1–R2.3 不可标 `verified`。本豁免不允许无来源 Undo，不影响人工 PDIC/SECTION/Profile 保护，不放开真实扫描 PR-B 或模型训练。R3 按严格文件指纹/会话事务边界分步递交；尚未覆盖的 OCR 人工覆盖、简体配对、删除和跨文件同步应明确拒绝撤销，不得假称 R3 全部完成。

**R3.1 单步 Undo**：将 ReviewWindow.delete_review_entry、_commit_edits 以及相关保存路径的业务性变更集中为可撤销事务（建议领域服务 proofreading_transactions.py + UI controller 薄路由）。快照/逆操作覆盖 entry 列表及 identity、词名、原图 X/Y、manual_selection 覆盖、候选状态、简化字缓存与保存 PDIC 的一致性；任何事务失败都不得留下“界面恢复但磁盘未恢复”的状态。第一版只需**同一打开会话内** Undo，不承诺重启后继续撤销；正常已保存 PDIC 在崩溃后仍须安全可读。
  
**R3.2 Redo 与组合编辑**：连续撤销重做、撤销后新编辑清空 redo、FocusOut/自动保存/跨页/窗口关闭正确处理事务边界；撤销误删除后重新 OCR 不能被旧的 deselection 悄悄删掉。测试 Windows/Linux/macOS 下按键绑定、重复点击、会话关闭及图形回读。保存撤销日志仅在用户同意后作为独立后续工作。
  
**DoD**：实际 PDIC + manual overrides + 缓存/界面在提交、撤销、重做后严格一致；不更改默认排序和既有快捷键。

### R4 — 先用诊断证据优化校对顺序，再考虑 ML

**R4.1 确定性可解释风险分层**：输入可以来自 OCR/Tesseract 分歧、弱 POS/结构证据、人工 final-only、行序/坐标异常、无法唯一关联、低 OCR 置信度等；分层为 priority review / normal / unknown，注明每个原因；不将未知视作确定错误，不使用会被当前 PDIC 修改失效的过期证据。
  
**R4.2 UI 与耗时测量**：扩展现有 run_focused_filter，不取代原有页序排序；通过可关闭选项提供高风险优先/恢复原顺序；保留 SECTION 与页面 identity、跳转、页码、编辑一致性。校对耗时按任务阶段记录可匿名聚合；不收集按键内容或联网埋点。比较相同词典的误差漏检、每千完成核验词条时间、跳转次数；无真实数据时只报告行为测试，不宣称节时。

### R5 — 评分架构安全抽取（parity only）

**R5.1 先定位纯计算边界**：在 src/picture_capture/paddle_headwords_core.py 中分清 score（词头结构/视觉证据）和后续 q（多 OCR 仲裁 quality + confidence），不能把两者误当同一门槛。引入独立、可序列化的特征快照和无副作用 scorer；第一步不修改权重或门槛。
  
**R5.2 小步搬迁而非一次性搬移数百行**：分别搬离纯打分、纯判定；原有公开 facade/monkeypatch test hook 保留；用测试金输入覆盖拉丁/POS 粘连、续行、CJK 单字、Tesseract/Lens 对照、OCR+Layout 边界；包括原始接受布尔值、理由、评分、坐标逐字段比较。满足 architecture_guard 和 change_architecture_guard；不抬尺寸基线。

### R6 — 离线学习与渐进启用

**R6.1 数据门槛**：仅使用 R2 已明确人工核验且来源一致的样本；缺候选的漏检单独统计，不当作现成负例。按词典和项目层面划分开发/独立测试，不将同一词典相邻页随机混入两侧；明确样本数量、每词典 FP/FN、不平衡、人工选择偏倚及漂移。
  
**R6.2 基线先行**：原规则不动，离线比较规则分数、可解释逻辑回归、轻量树模型/GBDT 和分层规则；量化 P/R/F1、词典级 FP/FN、Calibration/Brier/ECE、错误覆盖度、文字类型/CJK 分组和决策成本。多重调参与阈值选择只在开发组；不可用保留测试集选阈值。
  
**R6.3 shadow-only**：模型输出建议/风险而不写最终 PDIC；默认关闭，版本化可回滚，未来若要影响自动画线须另立明确审批与 PR-B 真实页复检门禁。**不做无监督自动在线更新，不自动将人工操作解释为完整金标**。

### R7 — 只有实测瓶颈才改变性能/坐标实现

- R7.1 沿用 docs/refactor/PHASE8D_BENCHMARK_RUNBOOK.md 以及 docs/audits/ISSUE419_OPERATIONAL_PERFORMANCE_20261013.md 的测量原则。记录 cold/warm、CPU/GPU、RSS、OCR 引擎启动、单 entry OCR 次数与批处理耗时；确认热区后再选 batching、缓存或有限并发，不依据源码循环就推测“几小时变一天”。
- R7.2 单瓶颈单 PR 优化。保持相同输入输出/人工保护、显式 worker 限制、并发取消与 Windows spawn 兼容、OCR engine线程/进程安全。真实工作流 benchmark 前不得承诺速度提升。
- R7.3 预处理坐标先定义 source → canonical → transformed 的版本化、正/逆映射合同，约束 SECTION、PDIC、PPP、ROI 多边形和切图；原始扫描不得破坏，非线性展平可继续生成新图作为物化产物，不应简单删除图像文件。先只读校验与 round-trip，再考虑迁移。

### R8 — 用户允许之后才执行 PR-B 真实扫描基准

- 人工复核前三套 30 页/1336 PDIC 真值的完整性和匹配条件；其 96.86% **只代表历史缓存**，不是当前 main 性能，也不能作新回归门槛。
- 为 FarEast 和 DICs_for_test 补真值，优先覆盖稀疏列/密集续行/CJK/插图旁排版/多 SECTION；记录标注者、争议复核与样本排除原因。
- 对每本词典分别用**当前受测提交**重跑 left_edge / paddleocr / combined，固定代码 SHA、环境、设置、Profile、图像哈希和 matching 口径；报 P/R/F1、Y error、跨墨、总耗时、人工校对时间、显著失败案例；配对比较同页基线/候选版，绝不把历史缓存和新版全页混用。
- **发布门禁**：不设凭空的统一 F1 提升目标；候选不能以显著牺牲任何主要词典的安全性换总体改善；如果证据不充分，默认关闭并公开限制。PR-B 由用户决定何时开始，当前 status=deferred_by_user。

## 3. A/C 功能缺口与已有工作如何衔接

用户曾要求“随后补充剩余 A/C 功能缺口”。目前缺少可靠的 A/C 完整验收定义，因此**禁止凭命名猜测 A/C 已覆盖什么**。在 R0.2 后设置独立的 AC-GAP-AUDIT 工作单元：读取历史设计/issue/PR 与用户约定，逐项建立“期望行为 / 现有代码 / 测试证据 / 未实现内容 / 对应 Rx 单元”，经核实后再排入 R2、R4、R5 等对应阶段。与 #475–#477 已合并内容重复的不得再造实现。

## 4. 单 PR 标准模板（强制）

每个主题 PR 都必须为**每个子任务**在 PR 里记录：

- **编号/目标**：例如 PC-CQ/R0.1；唯一的问题、输入、预期输出、拒绝做的事。
- **现状**：执行前 main SHA、已打开 PR、并行开发信号、依赖的已有实现/测试；逐条源码定位。
- **变更**：文件列表、数据流与所有权、受影响的持久化格式、开关默认值、兼容性路径。
- **测试**：先失败/后通过的回归、危险反例、重开/保存、基本 GUI smoke、架构守卫、完整 CI 平台矩阵。
- **效果**：区分确定性行为、feature-level 测试、真实扫描实测；不得混报。
- **回退**：如何关闭实验功能/撤销 PR，不删除人工数据；如有数据变更附迁移方案。
- **结果**：PR URL、提交 SHA、CI run URL/结论、每个子任务的验收状态、剩余风险与下一个主题批次。

**统一合并门禁**：所有 CI jobs success，变更仅在约定范围内；若检查未完成/unstable、存在冲突、完整集成结果不清晰则不得合并。合并后还要核对 main CI；不能以单元测试通过代替 GUI 行为证据。

## 5. 执行状态和跨会话协议

- **权威文件**：本 PLAN（目标/DoD）+ CORE_QUALITY_STATE.json（进度事实）+ CORE_QUALITY_RESUME.md（执行规则）；GitHub 实时 PR/分支/main/CI 优先于 checkpoint。可引用 docs/refactor/RESUMABLE_EXECUTION_PROTOCOL.md 的恢复纪律，但两条工作流进度互不篡改。
- **检查点只记录已证实的成果**，state 每个主题 PR / 批次结尾更新：status（todo / in_progress / blocked / pr_open / merged / verified）、active_work_item、main SHA、PR、head SHA、已验证的测试与 CI、阻塞原因、待办的唯一下一步、状态更新时间。
- **时序**：每次会话开始先读 3 文件 → 获取 GitHub 实时 main/open PR/最近提交/CI → 核对 state 与实际 → 没有并发冲突时选一个可执行主题批次（内含多个关联子任务）；提交 PR 后记录各子任务状态 → CI 成功和 merge 状态确认后再标 verified。不应因额度/会话中断从头再做或开启重复 PR。
- **写入冲突**：如果当前 active_work_item 已有 open PR，仅继续该 PR；若有另一个 Work/Codex 改同一区域、CI 在跑或状态不确定，转只读检查并报告 blocker。
- **状态数据有效性**：GitHub 的 merge/CI 才是成功证据；不能仅因模型曾经“认为完成”写 verified。状态文件与 PR 同一分支有未合并差异时，以 PR 的最新状态为追踪入口，不声称 main 已更新。
- **计划修订**：如新的可靠证据推翻工作次序，单开 docs PR 更新 PLAN.version + STATE.plan_version + change log，明确旧目标映射/保留、不偷偷改变原验收要求。
- **继续口令**：详见 CORE_QUALITY_RESUME.md；新的会话应直接读取 GitHub 文件，无需引用本聊天或依赖内存。
- **保守资源使用**：不连续轮询 CI；CI 运行未完成时报告 URL 与状态，不假装在后台继续。若执行环境缺 OCR 或真实扫描数据，只做受支持的测试并注明限制。

## 6. 当前立即执行目标（唯一激活单元）

**B0 / R0.1 已随 #479 合并**：待 main 合并后 CI 通过再标记 verified，之后 active_batch=B1。B1 可把 R0.2、R1.1、R1.2、R1.3 的验证设施放在一个主题 PR（如风险过大则先更新 STATE 并拆成 B1a/B1b）。不同时启动 B2，也不启动 PR-B。

建议新 PR 标题：**fix(ocr): invalidate resume checkpoints when detection dependencies change [PC-CQ/R0.1]**。

B0 验收：R0.1 对应三平台 CI、GitHub 合并及最新 main CI 成功；若 CI 未成功，停在 B0。B1 验收：R0.2、R1.1、R1.2、R1.3 各项 DoD 均完成、默认生产识别行为不变、完整 CI 通过。

## 7. 文档变更记录

- 2026-10-15 v1.2.0：用户明确授权 R2/B2 人工验收暂缓、继续 B3/R3；仅修改阶段门槛，不宣称 B2 verified，不更动原有数据与真实扫描延后原则。


- 1.0.0 / 2026-10-14：从用户评估文件与源码复核制定；修正“score 与 q 同一门槛”“特征级即完整扫描基准”“字节预算绝对为零”“人工覆盖可直接当金标”等不准确判断；继承 #475–#477；新增跨会话状态机制；延后真实扫描 PR-B；初始激活 R0.1。

- 1.1.0 / 2026-10-14：根据用户要求采用同主题打包 PR（约 2–4 个关联子任务），新增 B0–B8 批次、独立子任务验收与安全拆包条件；#479 已合并但 R0.1 仍须 main CI 通过才 verified。
