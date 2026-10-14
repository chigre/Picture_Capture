# Picture_Capture 核心质量升级：跨会话恢复操作规程

**计划 ID：PC-CQ-20261014**。这是用户明确要求的持久任务交接合同。每次新的聊天 / Work / Codex 环境都必须将 GitHub 的实时状态视作真实进度；禁止因为没有聊天记忆而从头实施。

## 新会话的一句启动指令（可原样复制）

请继续 chigre/Picture_Capture 的 PC-CQ-20261014 核心质量升级。首先通过 GitHub 读取 docs/roadmaps/CORE_QUALITY_UPGRADE_PLAN.md、docs/roadmaps/CORE_QUALITY_STATE.json、docs/roadmaps/CORE_QUALITY_RESUME.md，再核查实时 main SHA、open PR、最近提交、CI 与实际代码。若文件还在规划 PR 分支，请先定位规划 PR。按 STATE.active_batch 只推进一个主题 PR，可在该 PR 内完成约 2–4 个紧密关联子任务；每项独立验收，并在 PR/CI 状态变化后更新 checkpoint；不要重跑已完成工作。遵守 AGENTS.md/架构守卫，所有实验功能默认关闭，保留人工 PDIC 保护；真实扫描 PR-B 继续延后，不能冒充实测准确率。若发现冲突或并行工作，先只读报告 blocker。

## 强制恢复次序（实施前逐项执行）

1. 读取本规程、MASTER PLAN、STATE，确认 plan_id / plan_version 和 active_work_item。
2. 获取 GitHub 主分支实时 SHA、最近 merged PR、全部 open PR、当前/最近 CI 的明确结论。
3. 读取 AGENTS.md、docs/architecture/CHANGE_POLICY.md、docs/refactor/REFACTOR_STATUS.md 及相关源码/测试；不要把独立的 Phase13 重构状态写入本计划 state。
4. 比对 STATE 中记录的 active PR / SHA / status 与 GitHub。若 PR 已合并而 STATE 仍写 pr_open，先核 CI 与变更是否满足 DoD，必要时单独修正 state，不能重复开启 PR。
5. 检查是否有其他实例正在改同文件、是否存在未完成 CI、merge conflict、失效 checkpoint、权限或依赖阻塞。出现任何不确定，仅做只读检查，提供下一步建议，不并发修改。
6. 若具备写入条件，只推进 **一个 active_batch** 的一个可审查主题 PR；其中允许完成约 2–4 个具有相同测试边界的子任务。逐项记录测试/验收，先补回归反例，再实施并运行目标测试、架构守卫和完整 GitHub CI。超大/异质任务可经 STATE 明确记录后拆包；不同时开启第二个生产 PR。
7. 将实施证据登记到 STATE：before/after SHA、PR URL、CI URL+结论、目标测试、文件、是否已合并、下一步唯一编号、blocking_reason、work_in_progress。CI 正在跑时不得谎报完成。
8. 当 PR 已合并且最新 main CI 通过，才将该批次及其已验收子任务标记 verified；开始下一批次必须确认依赖、状态和用户限制未变。新阶段或目标改变应先更新 PLAN 版本。

## 当前执行（2026-10-15）：B3/R3 已启动 Draft [#502](https://github.com/chigre/Picture_Capture/pull/502)

**一个生产代码 PR #502**：加入会话内保存后的撤销/重做，支持可证明的词名、简体配对副本和无 OCR 候选关联的单条删除；采用 Entry 对象 ID 与当前原图、PDIC、manual_selection、OCR 缓存指纹校验，PDIC+简体文件使用仅在提交时出现的本地崩溃恢复标记。用户未授权永久撤销日志，因此重启后不能继续 Undo。遇 OCR-linked 删除/人工 override 变更、同页其他未保存编辑、来源漂移时拒绝。源码与回归见 `src/picture_capture/proofreading_transactions.py`、`tests/test_b3_review_session_transactions_20261015.py`，详见 [B3 RUNBOOK](CORE_QUALITY_B3_RUNBOOK.md)。**当前 PR 最新 CI 尚待核验，不能冒充 R3 完成。** R2 仍不验收。

## 当前阶段授权（2026-10-15）：R2 暂不验收，立即进入 B3/R3

用户明确改变阶段门槛：**R2/B2 保持 in_progress、#483 与 Windows W1–W11 留待真人验收，允许开始 B3/R3；不得借此把 R2 标为 verified。** 规划升级为 v1.2.0，旧的「B2 不完成就绝对不得开始 R3」仅对此次用户指令豁免。R3 业务事务要先查 ReviewWindow 保存/候选覆盖/简体配对调用链，只有源指纹严格一致的 Undo/Redo 才可实际启用，不能用内存文本倒退冒充 PDIC 已回滚。当前独立工程分支 `feat/pc-cq-b3-review-session-transactions-20261015`，先查 GitHub 实时 PR/CI 再续接。原有真实扫描 PR-B 延后。
 
## 历史入口（2026-10-14）：#500 合并和 main CI 均成功；仅 #483 Windows 真人验收尚需完成

**[#500](https://github.com/chigre/Picture_Capture/pull/500) 已成功合并到 main@`3248882a40606069c9eb5b931c1a690bef87c422`：** 基于已通过四平台 CI 的 main@`8a95e37d592f421d823efbe338942333867ad15c`，一次打包 R2.1/R2.2/R2.3 的“右键词条序号、输入原图 X,Y”具体对象所有权移动操作、post-PDIC evidence、拒绝来源歧义/重合/不同步的边界测试。该功能是明确操作的坐标输入移动，**不是通用自由拖动**；已有 OCR 候选/简体配对/后台批量运行时拒绝。固定提交 [PR CI 38619428582](https://github.com/chigre/Picture_Capture/actions/runs/38619428582) 与 [合并后 main CI 38619848886](https://github.com/chigre/Picture_Capture/actions/runs/38619848886) 四平台均通过；Windows 真人 W1–W11 仍待完成，R2/B2 不标 verified，下一批仍是 B2/#483，不启动 B3 或 PR-B。\n\n## 当前入口（2026-10-14）：#498 已合并且 main CI 通过；B2 仍等待 #483 真人验收与任意移动归属

**#498 已合并到 main@`c1b16d0b8112367f2a5ad816018fe8fd771c91d4`：PR [CI 38616327415](https://github.com/chigre/Picture_Capture/actions/runs/38616327415)、合并后 main [CI 38616790068](https://github.com/chigre/Picture_Capture/actions/runs/38616790068) 均通过四平台；一次交付 R2.1–R2.3 的身份血缘、锁内前驱校验和跨页/旧证据拒绝。无开放生产代码 PR。B2 仍 in_progress：#483 尚需真实 Windows 人工 W1–W8 验收与“任意词条 XY 移动/混合编辑”的操作所有权设计（当前应用未有通用 Entry 拖动事务）。下一批次仍为 B2/#483，不启动 B3 或 PR-B。**

**B0 #479、B1 #481 已通过对应主分支验收。B2 基础记录 #482、真实 Tk 合成核验 #486、同次保存多条独立文字修改的原子证据 #489 也已合并。** 当前 main@`04c02286` 的 [CI 38553009540](https://github.com/chigre/Picture_Capture/actions/runs/38553009540) 与 [CodeQL 38553009318](https://github.com/chigre/Picture_Capture/actions/runs/38553009318) 成功，所有已完成增量均保持用户校对证据默认关闭。#488 双栏行首修复已合并，但未把过去的原图单独像素审计冒充新版本的完整画线基准。**B2 仍未全部验收：Issue #483 继续要求任意 XY 标记移动/混合编辑的操作所有权身份，以及真正由人执行的 Windows ReviewWindow FocusOut/自动保存/跨 SECTION/异常重开检查。** B2 的唯一下一步是 #483，B3 和真实扫描 PR-B 继续延后。

**关键核查位置**：

- src/picture_capture/ocr_page_resume.py — _algorithm_environment_key、input_fingerprint、validated_resume、write_page_resume
- src/picture_capture/app.py — _detect_pages 内的恢复入口及 PDIC 保存
- src/picture_capture/ink_safe_separator.py / separator_y_refinement.py
- src/picture_capture/ocr_tesseract_runner.py / ocr_lazy_secondary.py
- tests/test_ocr_page_resume_20261014.py / tests/test_ocr_engine_cache_lazy_20261014.py
- scripts/architecture_guard.py / .github/workflows/ci.yml

**不可绕过**：即使 Linux 单平台通过，也不能宣称 Windows/macOS 已通过；没有 OCR 环境就明确写出未测试范围；若主分支已修复该风险，记录现有修复证据，不重复提交新实现，然后继续 R0.2。

## 每次会话结束时填写的小结（必须有事实依据）

- plan_id / plan_version / active_work_item：
- 开始时 main SHA / 结束时 main SHA：
- 查到的 open PR / 并行修改信号：
- 本轮实际变更文件、提交 SHA 和 PR URL：
- 已执行的 focused tests + 架构检查：
- 三平台 CI 的 run URL、status 与 conclusion：
- 改动对 PDIC、manual_selection、SECTION、Project Profile、实验开关的影响：
- 完成状态：todo / in_progress / blocked / pr_open / merged / verified：
- 唯一可执行的下一个主题批次（及子任务）：
- 未验证内容 / blocker / 需要用户裁定的问题：

## 何时必须停下

- 计划与代码、PR、CI 不一致；并行工作；有 merge conflict 或不稳定测试；需要改持久化格式；需要用户授权真实扫描、数据上传或自动在线训练；需要调整架构基线；需要超出当前同主题批次范围的多模块设计抉择；发现可能损害人工校对/备份。停止时仍要尽量将可证实状态记入 STATE，**不创造虚假成功状态**。

## 规划文档在哪里

- 仓库：chigre/Picture_Capture
- 文件：docs/roadmaps/CORE_QUALITY_UPGRADE_PLAN.md
- 检查点：docs/roadmaps/CORE_QUALITY_STATE.json
- 本规程：docs/roadmaps/CORE_QUALITY_RESUME.md
- 如 main 暂无这三份文件，查找分支 docs/core-quality-upgrade-plan-20261014 和对应规划 PR；优先把规划文件经 review/CI 合入 main 后再开始实施。
- 规划正文是稳定目标；STATE 是会变化的执行事实；GitHub 实时状态优先于二者的旧状态快照。

## v1.1.0：多子任务主题 PR 规则

- 计划批次和子任务映射见 CORE_QUALITY_UPGRADE_PLAN.md 的“1.1 主题批次计划”；当前首次批次 B1，推荐 2–4 关联点/PR，**可分拆不可强捆**。一个 PR 可一轮完成多个子任务、一次 CI；不必在两个子任务之间等待一小时。
- STATE 必须保存 active_batch、batches[batch].units、batches[batch].status、各个 units 的完成证据以及同一 active PR。先检查旧 PR 和实时 CI，不能重做、不能并发另开第二个生产 PR。
- 文档修订 PR 不等于生产代码 PR。合并后先确认 main CI 通过才开始下一批次。用户特别要求：**简短状态报告、主要进度留在 GitHub，不增加聊天长度**。
