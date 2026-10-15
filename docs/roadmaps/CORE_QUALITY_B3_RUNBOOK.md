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
