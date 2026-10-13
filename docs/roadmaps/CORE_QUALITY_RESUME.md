# Picture_Capture 核心质量升级：跨会话恢复操作规程

**计划 ID：PC-CQ-20261014**。这是用户明确要求的持久任务交接合同。每次新的聊天 / Work / Codex 环境都必须将 GitHub 的实时状态视作真实进度；禁止因为没有聊天记忆而从头实施。

## 新会话的一句启动指令（可原样复制）

请继续 chigre/Picture_Capture 的 PC-CQ-20261014 核心质量升级。首先通过 GitHub 读取 docs/roadmaps/CORE_QUALITY_UPGRADE_PLAN.md、docs/roadmaps/CORE_QUALITY_STATE.json、docs/roadmaps/CORE_QUALITY_RESUME.md，再核查实时 main SHA、open PR、最近提交、CI 与实际代码。若文件还在规划 PR 分支，请先定位规划 PR。只推进 state 指定的下一个安全工作单元，并在完成一个 PR 后更新 checkpoint；不要重跑已完成工作。遵守 AGENTS.md/架构守卫，所有实验功能默认关闭，保留人工 PDIC 保护；真实扫描 PR-B 继续延后，不能冒充实测准确率。若发现冲突或并行工作，先只读报告 blocker。

## 强制恢复次序（实施前逐项执行）

1. 读取本规程、MASTER PLAN、STATE，确认 plan_id / plan_version 和 active_work_item。
2. 获取 GitHub 主分支实时 SHA、最近 merged PR、全部 open PR、当前/最近 CI 的明确结论。
3. 读取 AGENTS.md、docs/architecture/CHANGE_POLICY.md、docs/refactor/REFACTOR_STATUS.md 及相关源码/测试；不要把独立的 Phase13 重构状态写入本计划 state。
4. 比对 STATE 中记录的 active PR / SHA / status 与 GitHub。若 PR 已合并而 STATE 仍写 pr_open，先核 CI 与变更是否满足 DoD，必要时单独修正 state，不能重复开启 PR。
5. 检查是否有其他实例正在改同文件、是否存在未完成 CI、merge conflict、失效 checkpoint、权限或依赖阻塞。出现任何不确定，仅做只读检查，提供下一步建议，不并发修改。
6. 若具备写入条件，只处理 **一个 active_work_item** 的最小可审查变更。先建立回归反例，再实施，再运行目标测试、架构守卫和完整 GitHub CI。
7. 将实施证据登记到 STATE：before/after SHA、PR URL、CI URL+结论、目标测试、文件、是否已合并、下一步唯一编号、blocking_reason、work_in_progress。CI 正在跑时不得谎报完成。
8. 当 PR 已合并且最新 main CI 通过，才将该单元标记 verified；开启下一单元必须确认依赖、状态和用户限制未变。新阶段或目标改变应先更新 PLAN 版本。

## 首个待办：R0.1（不得跳过）

**目标**：审计与修复 #477 的 OCR 单页恢复 fingerprint 覆盖不完整问题。首先在 tests/test_ocr_page_resume_20261014.py 中添加算法依赖修改却错误复用 checkpoint 的失败测试；然后在 ocr_page_resume.py 中以清晰的依赖 manifest 作最小实现。可参考 CORE_QUALITY_UPGRADE_PLAN.md R0.1 的完整验收条件。保持默认开关关闭；不要启动 PR-B 或训练模型。

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
- 唯一可执行的下一个工作单元：
- 未验证内容 / blocker / 需要用户裁定的问题：

## 何时必须停下

- 计划与代码、PR、CI 不一致；并行工作；有 merge conflict 或不稳定测试；需要改持久化格式；需要用户授权真实扫描、数据上传或自动在线训练；需要调整架构基线；需要超出此单元的多模块设计抉择；发现可能损害人工校对/备份。停止时仍要尽量将可证实状态记入 STATE，**不创造虚假成功状态**。

## 规划文档在哪里

- 仓库：chigre/Picture_Capture
- 文件：docs/roadmaps/CORE_QUALITY_UPGRADE_PLAN.md
- 检查点：docs/roadmaps/CORE_QUALITY_STATE.json
- 本规程：docs/roadmaps/CORE_QUALITY_RESUME.md
- 如 main 暂无这三份文件，查找分支 docs/core-quality-upgrade-plan-20261014 和对应规划 PR；优先把规划文件经 review/CI 合入 main 后再开始实施。
- 规划正文是稳定目标；STATE 是会变化的执行事实；GitHub 实时状态优先于二者的旧状态快照。
