## B3/R3 #519 最终结果（2026-10-15，已验证部分交付）

#519 [PR](https://github.com/chigre/Picture_Capture/pull/519) final head `16a6e8b28c983b31a11b23682777f9be2efaf882` 四平台（含 Python 3.10、Tk synthetic、架构、wheel）[PR CI 38703019216](https://github.com/chigre/Picture_Capture/actions/runs/38703019216) SUCCESS；CodeQL 成功。已 squash 合并 main@`6987a4a2eac37a6b3524e6c63ae87a1b60f5ad7a`，合并后 [main CI 38703692439](https://github.com/chigre/Picture_Capture/actions/runs/38703692439) 与 [Push 38703694285](https://github.com/chigre/Picture_Capture/actions/runs/38703694285) 均 SUCCESS。旧 Windows init.tcl 运行器错误重跑后消失；没有改弱测试/基线。

已支持安全的 OCR candidate-linked **删除提交**：PDIC、人工覆盖、简体的恢复式多文件写入成功后才更改 Entry/candidate/Tk checkbox。快照冻结 OCR owner，检查源文件与源指纹。**仍不支持此删除的 Undo/Redo**，操作后清历史并提示。唯一下一项：[#503](https://github.com/chigre/Picture_Capture/issues/503) 实现可逆 candidate 状态恢复、三文件逆向事务、重复多步/FocusOut/autosave/窗口关闭/跨页行为以及必要真人 Windows R3 验收；之后才可能标记 R3 完成。R2/B2 用户授权暂不验收，仍 `in_progress`，#483 W1–W11 保持 open。无 R4/PR-B。

# Picture_Capture 核心质量升级：跨会话恢复操作规程

**计划 ID：PC-CQ-20261014**。这是用户明确要求的持久任务交接合同。每次新的聊天 / Work / Codex 环境都必须将 GitHub 的实时状态视作真实进度；禁止因为没有聊天记忆而从头实施。

## 最新接力（2026-10-15）：B3/R3 #519 源归属防护；#503 继续未完成

实时 main 起点 e61fd0016da1da43e39dc30d44e66f4c7c60fdfb，合并后四平台 CI [38700426803](https://github.com/chigre/Picture_Capture/actions/runs/38700426803) 成功；启动时无开放 PR。审计发现原 SavedSnapshot 仅保留可变 Entry 对象，撤销判定事后读取 candidate_id，并且提交前未再次验证 OCR cache/manual override。旧候选删除是 manual override→PDIC→简体文件的非原子写入链。

单一在建生产 PR [#519](https://github.com/chigre/Picture_Capture/pull/519)，分支 feat/pc-cq-b3-r3-source-fingerprint-20261015。它复用旧 #503 分支的三条反例，从最新 main 重新组织安全代码：冻结候选 ownership，manual/OCR/SECTION/Profile 路径与字节级提交前核验，历史串链失效清栈，并补并发/外部修改反例。初始 CI [38701396654](https://github.com/chigre/Picture_Capture/actions/runs/38701396654) 在运行；文档提交后必须以最终 PR 头部 SHA 的 CI 为准。CI 未绿不得合并，main CI 未通过不得标记工作包验证。

唯一下一接力：核 #519 最新 CI（Windows/macOS/Ubuntu/Python3.10、架构与 Tk），失败优先修复；成功则审查→合并→postmerge main CI→同步 STATE。之后继续 [#503](https://github.com/chigre/Picture_Capture/issues/503) 的 OCR candidate-linked 删除/人工覆盖与 PDIC/简体多文件事务及 Undo/Redo/Tk 行为，不能仅凭 #519 宣称完成。R2/B2 始终 in_progress，#483 的真人 Windows W1–W11 未验收；R3 亦 in_progress。不碰 PR-B、训练、私人原图与格式迁移。

## B3/R3 当前额外交付范围（PR #519）

#519 当前已扩展为同一主题的一组安全工作：冻结 OCR owner/人工覆盖/OCR/SECTION/Profile 源指纹并于 Undo 最后一刻复核；对“已确认为唯一 candidate 的 ReviewWindow 删除”先生成精确 PDIC/manual_selection/简体三文件目标字节，再用短暂 v2 恢复标记事务写入，**持久化成功才更新 Entry/candidate/Tk checkbox**。跨页重新打开由可信项目 OCR 路径恢复未完成事务。详细见 `CORE_QUALITY_B3_RUNBOOK.md`。修复时同时移除了 app.py 内不可达的旧候选写入分支，未修改架构基线。新增反例、真实 Tk 合成 smoke + 三平台 CI 配置。

**不要误判 R3 完成**：上述 candidate 删除尚不能 Undo/Redo，当前故意清理历史并明确状态提醒；#503 仍包含候选状态恢复/重复复合事务/真人 Windows 操作检查。先看最新 PR #519 HEAD 和固定 SHA CI，不要根据聊天里的中间提交的红/绿灯直接合并。完成 PR/main CI 后，更新 STATE/RESUME/RUNBOOK 并继续 #503。R2 始终 in_progress，#483 W1–W11 保持等待，不开启 R4/PR-B。

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

## 当前执行（2026-10-15）：#502 已合并并通过 main CI；B3/R3 继续 #503

**[#502](https://github.com/chigre/Picture_Capture/pull/502) 已合并**，main `910b889898efab1ffc2975cdfa613eb675be70ef`；固定版本 [CI 38630143182](https://github.com/chigre/Picture_Capture/actions/runs/38630143182) 和合并后 [main CI 38630567897](https://github.com/chigre/Picture_Capture/actions/runs/38630567897) 均已通过 Windows、macOS、Ubuntu、Python 3.10（含 Tk smoke 和构建）。该工程工作包支持当前会话已保存文字、简体副本和无 OCR 关联单条删除的撤销/重做与中断恢复，**不是整项 R3 完成**。唯一下一工作包：[#503](https://github.com/chigre/Picture_Capture/issues/503) OCR-linked 删除、manual_selection 人工覆盖和复杂组合事务；只能在来源和提交原子性可证明时开放。R2/B2 继续 in_progress、#483 不关闭，真人 Windows W1–W11 未验收。无活跃代码 PR，R4 和真实扫描 PR-B 暂不开始。

### 历史执行记录（#502 开发期）

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
