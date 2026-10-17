## 2026-10-17｜main postmerge CI 最终结果：成功（Windows runner 重试后）

- R3 #542 已合并主干 `e12a9db4cc9199069e93d2c3ef12df97fcafd403`。该 SHA [postmerge CI 39013602419](https://github.com/chigre/Picture_Capture/actions/runs/39013602419) 在第一次 Windows hosted Tcl `init.tcl` 初始化异常后，**attempt 2 重跑失败 Windows 作业成功，最终四平台 SUCCESS**；[main CodeQL 39013601837](https://github.com/chigre/Picture_Capture/actions/runs/39013601837) SUCCESS。首次失败不能冒充未发生；是已记录的运行器异常。
- 此份文档仍需 #548 纯文档 PR 的自身固定 SHA CI/CodeQL 与合并后 main CI，不从上述旧 main SHA 推断文档合并后的结果。R3 的人工 Windows 交互验收依用户明确授权暂不进行，不是已实际 PASS；#483、#503 不关闭。

## 2026-10-17｜R3 工程合并完成；人工验收暂缓；main CI Windows 运行器重试

- R3.1/R3.2 [#542](https://github.com/chigre/Picture_Capture/pull/542) 最终 HEAD `f80daf07d7421f5bd8d20cce0c86fce160813697` 经 [四平台 CI 39013417928](https://github.com/chigre/Picture_Capture/actions/runs/39013417928) **SUCCESS**，[CodeQL 39013415268](https://github.com/chigre/Picture_Capture/actions/runs/39013415268) **SUCCESS** 后 squash merge [main@e12a9db4](https://github.com/chigre/Picture_Capture/commit/e12a9db4cc9199069e93d2c3ef12df97fcafd403)。
- 交付：候选所有权约束 Undo/Redo、20 步同会话历史、严格源指纹、PDIC+简体 sidecar 可恢复提交与字节回读、失败回滚及隔离、窗口关闭拒绝、延迟快照防护；合成故障注入/架构检查通过；不改变人工 PDIC/SECTION/Profile/OCR、原格式、R2 默认 OFF，不混入精修功能。跨文件恢复 **不等于 OS 原子性**。
- 用户本日授权本次**不进行**真人 Windows 验收而放行工程合并；R3/#503 与 R2/#483 W1–W11 的实际验收均是 **NOT PERFORMED**，不得记录为实际 pass/verified；R2/B2 继续 `in_progress`，#483 开放。
- 合并后 [CodeQL 39013601837](https://github.com/chigre/Picture_Capture/actions/runs/39013601837) **SUCCESS**；首次 [main CI 39013602419](https://github.com/chigre/Picture_Capture/actions/runs/39013602419) Ubuntu/macOS/Python 3.10 通过，Windows 2847 tests passed、1 项 GitHub hosted Python3.13 `init.tcl` 环境加载失败；已发起 Windows failed-job 重试 attempt 2，记录时尚未最终绿灯。
- main 分支保护禁止直接提交，故以**独立纯文档 PR** 同步 STATE/RESUME/B3_RUNBOOK，不绕过保护或开启第二个生产 PR。后续须验证 main Windows 重试、文档 PR 固定 SHA CI/CodeQL、合并及 docs postmerge CI。

## 2026-10-17｜#542 R3 安全工程收口，人工验收本次明确豁免（未声称通过）

- 用户明确授权：真人 Windows R3/R2 验收当前均暂不进行；**仅作为本次工程合并决策的人工验收豁免，实际结果仍是 NOT PERFORMED**。R2/B2 仍 `in_progress`，#483 W1–W11 保持 open；R3/#503 真人验收仍未实际完成，不制造 verified 标签。
- #542 同一 Draft PR，最新工程 HEAD `94a464b34a0569f3fc136fc1c263cd148883abc7`。已复用 B3 事务历史/候选所有权、恢复标记、严格源指纹，补 ReviewWindow 失败时窗口不关闭、内存与磁盘保护，以及 PDIC+简体 sidecar 配对暂存/两文件提交/回读/失败回滚；原项目格式和 R2 证据默认 OFF 不变。该机制是可恢复、fail-closed，**不是跨文件 OS 原子性**。精修画线独立。
- 此文档检查点时 [工程 CI 39013316496](https://github.com/chigre/Picture_Capture/actions/runs/39013316496) 尚未确认最终结果；文档提交将生成新 SHA，**必须以最后 SHA 的 Windows/macOS/Ubuntu/Python3.10、架构与 CodeQL 全绿为合并条件**，若失败只修复不合并。
- 唯一下一动作：核最终固定 SHA 的 CI 与 diff，安全通过后按用户豁免合并 #542，复核 postmerge main CI，并在 main 同步 STATE/RESUME/RUNBOOK；如有 blocker 保持 Draft、下小时继续。

## 2026-10-17｜#542 分支落后修复（仅同步 main，R3 未验收）

- GitHub live main：`db746ec4a15b5cae33f04526ef2995e86a91fd19`；#542 同步前 HEAD：`41f14fe55b0bd4f465e86f6e7314f30910e85281`。经 GitHub 自动无冲突试合并树核对，以两个父提交创建分支合并 `0511b30a20be57ba79d378eded03d4a1f0f7c9bf`（PR HEAD first parent；main second parent），非 force push；当前比较 `main...#542` 为 **behind 0 / ahead 24**（本条文档提交前）。仅同步历史，不表示 R3 安全验收。
- 旧 PR HEAD [CI 39008787964](https://github.com/chigre/Picture_Capture/actions/runs/39008787964) success；**合并后的新 SHA 尚无完整 CI 结论**。此文档提交也将进一步改变 HEAD，必须按最终 HEAD 重新检查 Windows/macOS/Ubuntu/Python3.10 + 架构 + CodeQL。
- #542 保持唯一 Draft 生产 PR，**未合入 main**；#503 真人 Windows R3、#483 Windows W1–W11 均未验收，R3/B3、R2/B2 仍 `in_progress`。后续单一安全动作：先补 ReviewWindow 保存失败/关闭及延迟快照保留的故障注入和修复，再跑四平台，禁止把精修画线改动当本 PR 的功能任务。

## B3/R3 #542 固定 SHA CI 结果（2026-10-17，自动验证通过，真人待验收）

Draft [PR #542](https://github.com/chigre/Picture_Capture/pull/542) 源码与文档 head `eaad5dd41c8742261592454ed4838713b6ea7a37` 的 Windows/macOS/Ubuntu/Python3.10 [CI 38970243351](https://github.com/chigre/Picture_Capture/actions/runs/38970243351) **四项 SUCCESS**；[PR gate 38970237522](https://github.com/chigre/Picture_Capture/actions/runs/38970237522) SUCCESS。main@05d345f8 的既有 [CI 38966764059](https://github.com/chigre/Picture_Capture/actions/runs/38966764059) SUCCESS。但这不等于 R3 全范围实现的真人验收，不等于跨文件 OS 原子性保证。#503 要求的真人 Windows ReviewWindow FocusOut、autosave、删除、重复 Undo/Redo、关闭/跨页、异常中断等交互尚未验收，R2/B2 #483 Windows W1–W11 仍未做；两阶段保持 `in_progress`，PR **保持 Draft/开放不合并**。唯一下一动作：严格审查剩余源指纹及失败路径并完成 R3 真人 Windows 验收；若有代码变动重新四平台 CI，再评估合并及 main CI。本次仅同步文档会产生新的 PR CI，需按该文档提交新 SHA 重新确认。

## B3/R3 #542 PR 与真实 CI 接力（2026-10-17 05:34 +0800；未验收）

B3 v4–v8 已正式提交原 R3 分支（`16e00f2`、`ded1117`），[Draft PR #542](https://github.com/chigre/Picture_Capture/pull/542) 是**唯一活跃生产 PR**。已将 main@05d345f8 (#539 PDIC 批量保护及其他主干更新) 以双亲合并提交 `3d8c157` 整合；PR 后来变为可合并，main 自身四平台 [38966764059](https://github.com/chigre/Picture_Capture/actions/runs/38966764059) SUCCESS。初次 R3 CI [38969777363](https://github.com/chigre/Picture_Capture/actions/runs/38969777363) 暴露 app.py 原架构上限 784737 字节被突破；`8b2186b` 将延迟保存抽离为独立 `proofreading_deferred_save.py`，主模块降至 784233 字节，**未放宽 ratchet**。下一轮 R3 CI [38969942123](https://github.com/chigre/Picture_Capture/actions/runs/38969942123) 的 Ubuntu 架构守卫通过，pytest 2800 通过、2 项原有源码文本断言因抽离模块而失败；`162764a` 调整断言查找实际调用与被调模块，**仍继续要求 PDIC 先提交、人工覆盖后于 PDIC、证据最后写入**。新 CI 尚未验证；R3 不得合并或标记 verified。R2/B2 `in_progress`，#483 真人 Windows W1–W11 待做，R3/#503 真人 GUI 验收也待做，不可替代。下一唯一动作：检查最新 fixed-head PR CI、逐项修复失败，然后严格审查数据/GUI安全及 Windows 人工验收。

## B3/R3 v4–v8 实装检查点（2026-10-17，未验收）

原 R3 分支 `feat/pc-cq-b3-candidate-undo-redo-20261015` 已真实提交 **v4/v5** 事务 rollback-intent／marker readback、失败后单文件或跨文件强制回滚（`16e00f2`），以及 **v6/v7/v8** 普通保存、共享 PDIC writer、ReviewWindow 编辑提交隔离和 deferred-save 失败快照保留（`ded1117`）。新增合成故障注入测试，但**未运行项目 pytest、Tk smoke、架构守卫或 R3 四平台 CI**；不得据此声称跨文件 OS 原子性、Undo/Redo 彻底安全或 R3 verified。main@05d345f8 的 [CI 38966764059](https://github.com/chigre/Picture_Capture/actions/runs/38966764059) 第 2 次运行四平台 SUCCESS，不能替代 R3 分支验证。R2/B2 与 R3/B3 维持 `in_progress`，#483 W1–W11 真人 Windows、#503 R3 真人 GUI 验收待做；用户已授权越过 B2 验收门槛推进 B3，不关闭 #483。恢复动作：只开一个 R3 draft PR 以获得固定 head CI，处理差异并做跨平台及真实 GUI 验收后再决定 merge。

## B3/R3 #503 readback/rollback safety checkpoint (2026-10-16 17:13 +0800; unverified)

On branch `feat/pc-cq-b3-candidate-undo-redo-20261015` (parent `8b52b344d755`, main `8ed4dd04bce0`), add exact post-publication bytes verification for candidate PDIC/manual/simplified bundle and one-/multi-file Undo/Redo. A silent rollback failure retains the recovery marker and blocks page reopening until recoverable; **this does not provide OS-level cross-file atomicity**. Add negative tests for invalid row index, silent partial writes, silent rollback and silent single-file Undo. No pytest/Tk/architecture/four-platform R3 CI has run; R3 remains in_progress. Only open PR #536 (unrelated UI, CI https://github.com/chigre/Picture_Capture/actions/runs/38878591544 failed), so do not open a parallel R3 PR. main CI https://github.com/chigre/Picture_Capture/actions/runs/38876986096 passed. #483 W1–W11 and R3 human Windows acceptance remain pending; R2/B2 in_progress, R2 evidence OFF, no real scans/uploads/training. Next: execute focused tests and architecture/Tk checks, then wait for PR slot and run R3 four-platform CI.

## #519 已合并后 CI 验证：R3 部分交付，不是 R3 完成（2026-10-15）

PR [#519](https://github.com/chigre/Picture_Capture/pull/519) head `16a6e8b2` [PR CI 38703019216](https://github.com/chigre/Picture_Capture/actions/runs/38703019216) 全绿（Windows/macOS/Ubuntu/Python 3.10，新增 real-Tk synthetic candidate delete、architecture、wheel）；CodeQL success。merge SHA `6987a4a2eac37a6b3524e6c63ae87a1b60f5ad7a`，[postmerge main CI 38703692439](https://github.com/chigre/Picture_Capture/actions/runs/38703692439)、[Push 38703694285](https://github.com/chigre/Picture_Capture/actions/runs/38703694285) success。确认继续使用事务日志/源指纹；未放宽旧 app.py ratchet。

完成 OCR candidate-linked 删除的原子提交（manual_selection、PDIC、simplified，v2 crash recovery），保存成功才刷新 Entry、OCR candidate.selected、checkbox；失败和脏编辑 fail-closed。仍不提供 candidate-owned Undo/Redo；当前执行安全删除后清空已存 Undo/Redo，避免错误恢复。继续 #503：定义 candidate 状态精确双向拥有者、支持同一事务三文件恢复和 redo、新保存清 redo、连续20步、FocusOut/autosave/删中间行/跨页/关闭真实 Tk，以及真人 Windows R3 验收。不得因该部分包合并就标 R3 verified 或关闭 #503。R2/B2 in_progress，#483 未验收且开放；R2 证据 OFF，严禁原图训练上传。

# PC-CQ/B3 — R3 校对事务化：实现与验收记录

**#502 安全工程增量已合并**：PR head `e063ddf0d6de64bf9ae3f97cd62a0b81b72edf06` 的 [CI 38630143182](https://github.com/chigre/Picture_Capture/actions/runs/38630143182) 成功；合并 `main@910b889898efab1ffc2975cdfa613eb675be70ef` 的 [CI 38630567897](https://github.com/chigre/Picture_Capture/actions/runs/38630567897) 四平台成功。**R3.1/R3.2 整体仍 in_progress**，下一工作包 [#503](https://github.com/chigre/Picture_Capture/issues/503) 包含 OCR 候选删除/manual_selection/复杂组合编辑的所有权与跨文件撤销；相关真人 GUI 验收还未执行。R2/B2 用户明确暂不验收。以下 T1–T12 的合成回归在 CI 通过，但不能代替真实人工操作。

## #519 候选归属与源指纹硬化（R3.1/R3.2 增量，未验收）

起点 main@e61fd001；PR [#519](https://github.com/chigre/Picture_Capture/pull/519) 开发中，最初 [CI 38701396654](https://github.com/chigre/Picture_Capture/actions/runs/38701396654) 在运行；最终应以 PR 末次提交固定版本 CI 为准。发现旧 SavedSnapshot 的对象引用不是不可变候选归属，快照后改 candidate_id 可误判旧普通文字事务；提交前没有再次验证 manual_selection/OCR 缓存；SECTION/Profile 改动也应使旧 Undo 失效。

当前工程改动（以 PR 和 CI 为准）：(1) 冻结 Entry ID→candidate_id；(2) 提交前复核人工覆盖、OCR、SECTION、Profile 路径与精确字节；(3) 多步历史链对任何来源或 owner 断裂清栈。反例包括候选归属变化、OCR/manual 最后瞬间修改、SECTION/Profile 外部修改与提交瞬间改变、历史串链污染。没有触碰 PDIC 格式/手工 OCR 结果/设置，R2 证据仍 OFF。

仍待 #503：candidate-linked 删除必须先建立拥有 candidate ID 的原子多文件操作，涵盖 manual_selection、PDIC、简体缓存和 UI checkbox，同一事务回滚，真实 Tk 自动保存/FocusOut/取消/跨页/关闭/重启测试。当前故意拒绝 candidate-linked Undo/Redo。不能把 #519 自动回归代替真实 Windows 人工操作，更不得关闭 #483 或标 R2/R3 verified。

## #519 扩展：OCR candidate-linked 删除的三文件事务提交（待最终 CI）

在同一个主题 PR 中继续 #503：新增 `proofreading_candidate_delete.py` 以唯一候选 ID、快照冻结 owner、来源原始文件校验生成删除计划，按保存 PDIC 的实际行识别一个原始记录，不用最近坐标/数组行号推断；原样保留其他 PDIC 行/8字段。新增 `proofreading_transactions.publish_owned_review_bundle`，以短期 v2 write-ahead 恢复标记同步 `pdic`、`manual_selection`、`simplified`，遇部分失败只在观察值属于原始/目标集合时回滚；重启恢复必须经 project root 推导的可信 OCR 文件路径，未知/伪造路径拒绝。原有 v1 PDIC+简体标记兼容。成功提交后 `ui.review_candidate_delete_actions` 才更新 Entry 实例归属、candidate.selected、Tk checkbox、简体缓存并重绘。保守拒绝 OCR 候选歧义、丢失源、脏 Tk 编辑、脏简体、无有效 PDIC 记录、其他页/损坏 JSON、R2 事件捕获已启用等情形；风险场景不得先修改 UI。

回归：`tests/test_b3_candidate_owned_deletion_20261015.py` + 扩展 `test_b3_review_session_transactions_20261015.py`；真实 Tk 合成集成 `scripts/gui_r3_candidate_delete_smoke.py` 加入 Windows/macOS/Ubuntu CI，不包含真实扫描。为满足 architecture ratchet，已删除 `app.py` 内在新分流后不可达的旧侧写覆盖块，守卫基线保持不变。**该提交只证明候选删除能够事务保存，候选删除的 Undo/Redo 仍刻意禁用**；需要下一工作包引入有明确操作身份的持久快照双向恢复、checkbox/候选缓存同步与断点/重复 Undo×N/Redo×N、跨页/FocusOut/关闭场景的最终验收。不能把自动化 Tk 合成冒充真人 Windows 验收。最终 PR-head / main CI 结论以 Actions 实时数据为准，旧的失败检查不得伪称成功。

## 用户阶段授权

2026-10-15 用户明确：「R2 暂不验收，继续 R3」。R2/B2 的 #483 和真人 Windows W1–W11 不关闭，也不标 verified。这是 R3 启动门槛的局部豁免，不是 R2 自动完成。

## 本 PR 同主题工程范围

- **R3.1**：ReviewWindow「保存」、共用 autosave、用户直接删除的前后持久快照；由 Entry **对象身份**关联，而非行号或最近 XY。相同会话中，支持纯保存文字、简体副本单独修改、两者同时修改、以及 OCR candidate **未关联**单条删除撤销/重做。PDIC 和简体文件恢复顺序执行，但以临时本地 write-ahead 恢复标记防止异常中断后静默失配。下次页面装载先恢复混合旧/新状态，若第三方编辑与两种状态均不匹配则拒绝覆盖。不永久保存用户 Undo 历史。
- **R3.2**：最多 20 步 Undo/Redo，撤销后新保存清空 Redo，跨页重新绑定与 ReviewWindow 关闭不沿用撤销栈；支持明确按钮「撤销保存」「重做保存」与非冲突快捷键 Ctrl+Alt+Z/Y，不篡改普通 Ctrl+Z/Y 编辑器行为。
- **绝对拒绝**：开启 R2 evidence 写入、OCR candidate-linked 人工决定/删除/manual_selection 变更、批量 OCR 正处理、图像/PDIC/简体来源过期、发生未保存 Tk 输入、多行增删/无 UI ownership 的新增或移动、预期外 OCR cache 变更、跨页尝试。UI 不因失败产生“磁盘未回退但文字已回退”。

## 自动化回归矩阵

| 验收项 | 独立断言 | 状态 |
| --- | --- | --- |
| T1 保存文字 Undo→Redo | PDIC 恢复完整原始**字节**；Entry 对象身份相同 | 合成回归随 #502 CI 通过；真人未验收 |
| T2 两次保存 + 排序重排 | 反向 Undo×2/Redo×2 不用行号猜测 | 合成回归随 #502 CI 通过；真人未验收 |
| T3 撤销后新改名 | 清空 Redo，不复活旧编辑 | 合成回归随 #502 CI 通过；真人未验收 |
| T4 未保存 Tk 文字 | 拒绝 Undo、不修改磁盘 | 合成回归随 #502 CI 通过；真人未验收 |
| T5 外部 PDIC/manual_selection/OCR 文件改变 | 指纹不匹配拒绝，不覆盖原始资料 | 合成回归随 #502 CI 通过；真人未验收 |
| T6 简体副本＋PDIC 同次改动 | 两个文件严格恢复并且恢复窗口缓存 | 合成回归随 #502 CI 通过；真人未验收 |
| T7 第二文件写入失败 | 自动回滚至提交前；内存数据不变 | 合成回归随 #502 CI 通过；真人未验收 |
| T8 崩溃后混合旧/新文件 | 下次 load_page 恢复，第三方改动拒绝 | 合成回归随 #502 CI 通过；真人未验收 |
| T9 单条无 OCR 关联删除 | Undo 恢复同一个 Entry；Redo 再删除；删最后一条可还原 | 合成回归随 #502 CI 通过；真人未验收 |
| T10 OCR-linked 删除/候选文字 | 拒绝 Undo，保留人工 override | 合成回归随 #502 CI 通过；真人未验收 |
| T11 翻页与 Tk 异步行重建 | 同页有源指纹才 Undo，行尚未就绪不能毁掉有效栈 | 合成回归随 #502 CI 通过；真人未验收 |
| T12 三平台 Tk/构建与 Python 3.10 | 最新 PR-head CI 及合并后 main CI | PR 与 postmerge main CI 均通过 |

## 仍未覆盖的 R3 正式 DoD

候选相关删除触发 `_write_manual_override(selected=False)` 的重做和撤销涉及 OCR candidate 状态、manual_selection 持久化、Simplified sidecar、PDIC 与可能存在的异步 UI。**当前严格拒绝这一类**，不能把单文件 Undo 作为完整 R3。复杂多行同时增删/移动与 R2 #483 真人 Windows 验收亦未执行。先就已有安全范围交付工程增量，不借用 R2 证据编造 gold label。

执行自动 CI 后填写完整 PR SHA、Windows/macOS/Ubuntu/Python3.10 结论、合并 SHA 与后续唯一任务；未全绿不得合并。
