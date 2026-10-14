# PC-CQ/B3 — R3 校对事务化：实现与验收记录

当前：**Draft [PR #502](https://github.com/chigre/Picture_Capture/pull/502)**；R3.1、R3.2 在进展中，未经最终 fixed-head CI 和真人操作验收不得称 verified。

## 用户阶段授权

2026-10-15 用户明确：「R2 暂不验收，继续 R3」。R2/B2 的 #483 和真人 Windows W1–W11 不关闭，也不标 verified。这是 R3 启动门槛的局部豁免，不是 R2 自动完成。

## 本 PR 同主题工程范围

- **R3.1**：ReviewWindow「保存」、共用 autosave、用户直接删除的前后持久快照；由 Entry **对象身份**关联，而非行号或最近 XY。相同会话中，支持纯保存文字、简体副本单独修改、两者同时修改、以及 OCR candidate **未关联**单条删除撤销/重做。PDIC 和简体文件恢复顺序执行，但以临时本地 write-ahead 恢复标记防止异常中断后静默失配。下次页面装载先恢复混合旧/新状态，若第三方编辑与两种状态均不匹配则拒绝覆盖。不永久保存用户 Undo 历史。
- **R3.2**：最多 20 步 Undo/Redo，撤销后新保存清空 Redo，跨页重新绑定与 ReviewWindow 关闭不沿用撤销栈；支持明确按钮「撤销保存」「重做保存」与非冲突快捷键 Ctrl+Alt+Z/Y，不篡改普通 Ctrl+Z/Y 编辑器行为。
- **绝对拒绝**：开启 R2 evidence 写入、OCR candidate-linked 人工决定/删除/manual_selection 变更、批量 OCR 正处理、图像/PDIC/简体来源过期、发生未保存 Tk 输入、多行增删/无 UI ownership 的新增或移动、预期外 OCR cache 变更、跨页尝试。UI 不因失败产生“磁盘未回退但文字已回退”。

## 自动化回归矩阵

| 验收项 | 独立断言 | 状态 |
| --- | --- | --- |
| T1 保存文字 Undo→Redo | PDIC 恢复完整原始**字节**；Entry 对象身份相同 | 待最终 PR CI |
| T2 两次保存 + 排序重排 | 反向 Undo×2/Redo×2 不用行号猜测 | 待最终 PR CI |
| T3 撤销后新改名 | 清空 Redo，不复活旧编辑 | 待最终 PR CI |
| T4 未保存 Tk 文字 | 拒绝 Undo、不修改磁盘 | 待最终 PR CI |
| T5 外部 PDIC/manual_selection/OCR 文件改变 | 指纹不匹配拒绝，不覆盖原始资料 | 待最终 PR CI |
| T6 简体副本＋PDIC 同次改动 | 两个文件严格恢复并且恢复窗口缓存 | 待最终 PR CI |
| T7 第二文件写入失败 | 自动回滚至提交前；内存数据不变 | 待最终 PR CI |
| T8 崩溃后混合旧/新文件 | 下次 load_page 恢复，第三方改动拒绝 | 待最终 PR CI |
| T9 单条无 OCR 关联删除 | Undo 恢复同一个 Entry；Redo 再删除；删最后一条可还原 | 待最终 PR CI |
| T10 OCR-linked 删除/候选文字 | 拒绝 Undo，保留人工 override | 待最终 PR CI |
| T11 翻页与 Tk 异步行重建 | 同页有源指纹才 Undo，行尚未就绪不能毁掉有效栈 | 待最终 PR CI |
| T12 三平台 Tk/构建与 Python 3.10 | 最新 PR-head CI 及合并后 main CI | 待执行 |

## 仍未覆盖的 R3 正式 DoD

候选相关删除触发 `_write_manual_override(selected=False)` 的重做和撤销涉及 OCR candidate 状态、manual_selection 持久化、Simplified sidecar、PDIC 与可能存在的异步 UI。**当前严格拒绝这一类**，不能把单文件 Undo 作为完整 R3。复杂多行同时增删/移动与 R2 #483 真人 Windows 验收亦未执行。先就已有安全范围交付工程增量，不借用 R2 证据编造 gold label。

执行自动 CI 后填写完整 PR SHA、Windows/macOS/Ubuntu/Python3.10 结论、合并 SHA 与后续唯一任务；未全绿不得合并。
