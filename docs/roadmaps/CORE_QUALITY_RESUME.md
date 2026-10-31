## 2026-10-31｜G3 R4.2 异步裁剪缓存的原图/PDIC/SECTION 内容漂移（test-first E2 待核）

- 唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged；`main@ec20989ea8c026cca5337293e67850b6b6df30f2` 不变。上个 checkpoint `659dcb90156c67701a71bc562f513b95b0c93d16` 的 [CI #41167212998](https://github.com/chigre/Picture_Capture/actions/runs/41167212998) 6/6 + Risk-tier、[OCR #41167213013](https://github.com/chigre/Picture_Capture/actions/runs/41167213013) 3/3、[CodeQL #41167207899](https://github.com/chigre/Picture_Capture/actions/runs/41167207899) Actions/Python 2/2 全部 SUCCESS，仅自动化 E2。
- 真实 red-first 测试修正版 `0426f197e8890a648a3ae15565b4deb048487fc0` 的 [CI #41168242309](https://github.com/chigre/Picture_Capture/actions/runs/41168242309) Ubuntu Python3.13 **7 failed/4997 passed/3 skipped**、macOS Python3.13 **7 failed/4998 passed/2 skipped**。源图同尺寸并恢复 mtime、PDIC/SECTION 变化或 SECTION 删除后，原 crop cache key 不变、过期预取被 `_apply` 接受；无变动时正例通过。测试只用极小合成 BMP/sidecar，无私有扫描。
- 生产 `7ac6fb024fb3fbb804a1da96acd40d1840cf13fe`（新增 `proofreading/focused_crop_source_fingerprint.py`）+ `746ddef47298e18c608e54e231d967a8fea88e3f`（`ui/focused_filter_workflow.py`）：按当前批次逐页 SHA-256 读取原图、PDIC、当前 SECTION 及路径/缺席状态，纳入内存裁剪缓存键；回调和缓存渲染时重新比较，来源变化不显示旧裁剪、不改人工编辑和持久化。不可读来源按 fail-closed 提示。独立审计：[G3_R4_2_CROP_SOURCE_DRIFT_20261031.md](../architecture/G3_R4_2_CROP_SOURCE_DRIFT_20261031.md)。
- **准确门禁状态**：源 [CI #41168312629](https://github.com/chigre/Picture_Capture/actions/runs/41168312629) 六平台当时仍运行，Risk-tier SUCCESS；[OCR #41168312628](https://github.com/chigre/Picture_Capture/actions/runs/41168312628) 三 OS 3/3 SUCCESS；[CodeQL #41168309968](https://github.com/chigre/Picture_Capture/actions/runs/41168309968) Python/Actions 2/2 SUCCESS。**文档提交产生新 HEAD，全部门禁必须重新核验；不把 pending 写成 success。**
- 当前代码只防**裁剪预览**复用，不冒充跨文件 OS 原子性，也未证明更晚的源图/SECTION 变化下 PDIC 保存拥有可信快照。下一唯一相关包：保存快照源归属+时间窗口故障注入，保留 R3 writer/人工编辑。图像哈希新增同步 I/O，未做真实大图延迟基准。
- 真人 Windows R3 E3、#483 W1–W11、#503 Undo/Redo、G3 操作及真实词典 GUI/PDIC/PPP/SECTION/Profile 全部 **NOT PERFORMED**；R6 人工标签、R8 真实扫描 **DEFERRED**。保持 #663 Draft/Open/Unmerged，不合并、不开 Ready、不关闭 issue、不碰 main。

## 2026-10-31｜G3 R4.2 异步校对保存失败：屏蔽异常中的私有路径（test-first / E2 待核）

- GitHub 实时基线 `main@ec20989ea8c026cca5337293e67850b6b6df30f2` 未变，仅 [Draft #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged；上一 exact HEAD `455c07eed7dde06916952a0bf30cba7bfb8f6e5c` 的 [CI #41165453150](https://github.com/chigre/Picture_Capture/actions/runs/41165453150) 六平台 6/6、Risk-tier， [OCR #41165453132](https://github.com/chigre/Picture_Capture/actions/runs/41165453132) 三 OS 3/3、[CodeQL #41165449850](https://github.com/chigre/Picture_Capture/actions/runs/41165449850) Python/Actions 2/2 全部成功；独立文档 job SKIPPED，不算成功。
- 新增真实 test-first `070bf0b6a84b2e1d7587d58aed09827b6bfd6e5f`，源 [CI #41166900396](https://github.com/chigre/Picture_Capture/actions/runs/41166900396) Ubuntu 3.13/macOS 3.13 **各 2 个预期失败**，日志明确显示 `_flush_focused_changes.failed` 向 Tk status、错误弹窗和 stdout 泄漏原始异常/traceback 哨兵；新测试前面的未保存编辑恢复、后到人工编辑归属、synthetic PDIC 字节不变断言均通过。
- 最小生产修复 `066fc62da163526dc5bd7ba4f4e3a8f49517f622` 禁止在保存失败回调显示异常字符串和 traceback，仅显示泛化重试提示；不改原 R3 事务、PDIC 读写或 pending 编辑恢复逻辑。测试：`tests/test_g3_r4_focused_save_failure_redaction_20261031.py`；审计：[G3_R4_2_FOCUSED_SAVE_FAILURE_20261031.md](../architecture/G3_R4_2_FOCUSED_SAVE_FAILURE_20261031.md)。
- **当前 E2 仍待最终 exact-head 核验**：源 [CI #41166937906](https://github.com/chigre/Picture_Capture/actions/runs/41166937906) 六平台执行中、Risk-tier 成功；源 [OCR #41166937853](https://github.com/chigre/Picture_Capture/actions/runs/41166937853) 3/3 SUCCESS；独立 [CodeQL #41166933385](https://github.com/chigre/Picture_Capture/actions/runs/41166933385) Actions SUCCESS、Python 尚在运行。此文档提交也会改变 HEAD，需重新检查全部最终 SHA 的门禁；不把旧 SHA 绿灯迁移到最新 SHA。
- **人工 NOT PERFORMED**：Windows R3 E3、#483 W1–W11、#503 复杂 Undo、G3 R4.2 Windows 操作以及实际词典页 GUI/PDIC/PPP/SECTION/Profile；R6 人工标签、R8 真实扫描继续延期。保持唯一 #663 Draft/Open/Unmerged，main 不动，不关闭 Issues、不自动合并或 Ready。

## 2026-10-31｜G3 R4.2 首批扫描/裁剪错误回调 epoch 与路径脱敏（源修复，最终门禁待核）

- 实时核对：仅有 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) Open/Unmerged，main `ec20989ea8c026cca5337293e67850b6b6df30f2` 未变。上一轮 `e75747ecda54b0ee896b0a2e79d480908f56c4da` 的 [CI #41161659038](https://github.com/chigre/Picture_Capture/actions/runs/41161659038) 六平台 6/6 SUCCESS、[OCR #41161659989](https://github.com/chigre/Picture_Capture/actions/runs/41161659989) 三 OS 3/3 SUCCESS、[CodeQL #41161655346](https://github.com/chigre/Picture_Capture/actions/runs/41161655346) Python/Actions 2/2 SUCCESS、Risk-tier SUCCESS。Documentation architecture check SKIPPED，未记作通过。
- 反例先行 `85188655c43c7239471e9cc933934447c35732d8` 的 [CI #41165165064](https://github.com/chigre/Picture_Capture/actions/runs/41165165064) 在 Ubuntu 3.13 和 macOS 3.13 **各有 4 个真实失败**：首批 worker 失败误标已完成、模式退出后回调改写界面、旧 crop render 失败污染新 epoch、裁剪报错回显异常来源路径。其余该两平台用例分别 4,989/4,990 通过；这份红灯不是门禁成功。
- 生产修复 `901ad2ec2f96d6397eb39db73ffe0ce02b5a5b2d` 仅收紧 `ui/focused_filter_workflow.py` 当前 scan/render epoch + 活跃模式失败回调，首批失败保持 incomplete/failed、泛化显示信息；预取失败不输出异常路径并允许后续重试。后续扫描失败的显式批次提示继续保留，避免旧测试适配器 override 指示器时失去状态。新旧回调均不写入 PDIC/PPP/SECTION。
- 源修复固定 SHA 的 CI [#41165270089](https://github.com/chigre/Picture_Capture/actions/runs/41165270089) 在本次文档编辑时仍处于运行过程；最终本提交也必须单独检查 exact-head 六平台、OCR 三 OS、Risk-tier、CodeQL Python/Actions，不能复用上一 HEAD 成功结论。
- 审计：[G3_R4_2_INITIAL_CROP_FAILURE_20261031.md](../architecture/G3_R4_2_INITIAL_CROP_FAILURE_20261031.md)。**NOT PERFORMED / DEFERRED**：Windows R3 E3、#483 W1–W11、#503 人工 Undo、R4.2 真人操作、真实词典扫描、R6 人工标签和 R8 真实扫描；自动 E2 不是人工 E3。继续保持 #663 Draft/Open/Unmerged、main 不动、不关闭 Issues。
- 下一恢复：先核最终 HEAD exact CI 与 CodeQL，如失败检查测试/工作区回调路径并最小修正；若绿，继续 SECTION/裁剪预取在源文件改写和保存后的一致性合成负例，不引入新的持久化 schema 或真实数据。

## 2026-10-31｜G3 R4.2 后续页面异步扫描失败：明确中断、保留已就绪批次

- 实时起点：PR #663 Draft/Open/Unmerged `f2422e271d1d33dd3913942b4504633f47990477`；六平台 CI #41120989838 SUCCESS 6/6，OCR #41120989687 SUCCESS 3/3，Risk-tier 成功，独立 CodeQL #41120978327 Actions/Python 2/2 SUCCESS；架构文档 job SKIPPED（不计通过）。main `ec20989ea8c026cca5337293e67850b6b6df30f2` 未变。
- 真实失败先行提交 `6182785af8bcaf0bf27c4cf700819c9d3e2556ee`，CI https://github.com/chigre/Picture_Capture/actions/runs/41161338739：Ubuntu 3.13 1 failed / 4988 passed / 3 skipped；macOS 3.10 1 failed / 4989 passed / 2 skipped。问题是后续 worker error 只设 status 字符串，没有终止态标志或批次指示，界面可能仍误显示后台扫描中；另一个旧 epoch 回调隔离测试通过。
- 最小修复：`ui/focused_filter_workflow.py` 仅增加**内存态** `_filter_scan_failed`，每次新扫描重置；在当前 epoch + 活跃模式的后续 worker 失败时标记**中断/未完成**，保留已显示词条与编辑；禁止将未扫描页视为完成，明确提示用户重筛，旧回调不能污染新 epoch。失败文案不回显包含私有路径的异常字符串。完整批次可继续处理，partial 尾部仍隐藏。
- 测试：`tests/test_g3_r4_streaming_scan_failure_20261031.py` 两个纯合成用例：部分扫描失败的显式终态/原批保留，以及跨 epoch 旧失败拒绝。本提交 CI/OCR/Risk-tier/CodeQL 的 exact-head 结论**待实时核实**；失败先行的 CI 红灯不当成生产通过。
- 审计：不改变源图 XY、PDIC/PPP/SECTION/manual_selection/OCR 缓存、Profile、原子写入和持久化 schema；不增加自动数据采集或 R6/R8 实验。Windows R3 E3、#483 W1–W11、#503 真人 Undo、R4.2 真人操作、真实词典扫描均 **NOT PERFORMED / DEFERRED**；自动 E2 不能代替。
- 恢复：确认本次修复最终 PR HEAD 的六平台 CI、三平台 OCR、Risk-tier、CodeQL Python/Actions，架构审计与 PR review；有红灯先检查日志并修复，勿合并/Ready/关闭 Issues。

---

## 2026-10-30｜G3 R4.2 真正 Tk 合成集成测出来的首屏 R3 来源竞态（最新恢复入口）

之前文档最终 HEAD `58a8108c461efae36cda3fc9c677bc85e249bb5b` 全部 CI 6/6、OCR 3/3、CodeQL 2/2、Risk-tier SUCCESS，仅自动化 E2。新 `c65f3fbbe7f3263b798d49846eb1e7a9a343816e` 把真实 Tk 校对窗口+三个默认 OFF 开关+「筛选」按钮的合成临时项目集成测试加进 `.github/workflows/ci.yml` Python 3.13 的 Windows/macOS/Linux 三平台。首次脚本将标签中带「筛选」的复选框误当按钮，`e952f5737346f576e38b2ec163a2d65e2f6174e7` 只修测试 selector。随后 Mac/Windows GUI smoke 通过，Ubuntu **真正暴露产品时序缺口**：异步首屏校对来源/词条尚未建立时单页保存被原有 R3 `commit_review_bundle` 正确拒绝，原筛选回调未捕捉，导致挂起/超时。

修复生产 `bd796fd73a2906d4e083fbd43ff83caacc57472d`：首次筛选前要求 `current_page.stem==_rendered_page_stem`；首屏未就绪显示提示并保持人工文字/设置；R3 保存 RuntimeError/OSError/ValueError 或明确 False 时停止，**不持久化新的风险/证据/计时选项，也不启动筛选**；只有 R3 保存成功才保存筛选设置并开始下一轮 worker serial。预先检验批次整数防止失败筛选误保存。在 `tests/test_g3_r4_rejected_scan_and_origin_race_20261030.py` 新增未渲染/来源保存异常/False return 三条回归；真实 Tk 集成 smoke 则覆盖主动模拟未就绪拒绝→等待真实首屏 bound→成功筛选→未保存人工编辑拒绝重筛。所有测试只用自动生成项目，不能替代真人 Windows E3。

**恢复动作：**核对源 [CI #41094402643](https://github.com/chigre/Picture_Capture/actions/runs/41094402643) 六平台 OS/Python (Ubuntu 3.13 **4987 passed 3 skipped，Xvfb real Tk G3 smoke OK**)、[OCR #41094402645](https://github.com/chigre/Picture_Capture/actions/runs/41094402645) 3 OS、CodeQL Python/Actions、Risk-tier；若失败查相应 job logs 修复。再核对最新文档 HEAD 的完整 exact CI，不以过去代码绿灯代替新 HEAD。R3 Windows真人 E3/#483 W1–W11/#503 人工 Undo 全部 NOT PERFORMED，R6 可信人工标签缺，R8 真实扫描延期。保留 #663 唯一 Draft/Open/Unmerged，main 不动，不合并不 Ready 不关事项。

---

## 2026-10-30｜G3 R4.2 后续：被拒绝筛选不写入设置 + 风险来源文件竞态防护（最新恢复入口）

已核验起点 `1611f7c60a5f3f93ca191e01b9ee7cc47248c493`：CI 6/6、OCR 3/3、CodeQL 2/2、Risk gate 全 SUCCESS，仅 E2。新 `12fa0cd4bc800ab740e0cb148d6874698924ad31` 负向测试复现非法 batch size 仍修改部分 AppSettings、OCR 风险来源 sidecar 被并发换字节后仍可排序的缺口；其中 4 个早期 guard 测试有缺漏的 mock deps，`3252a949d615af1a819441778db2bd6c3f4f84c7` 仅补齐测试依赖，无变更业务断言。修复源 `691bcee0da9adc3b8a108ac737a2216ac03a5a9c` 让 pending/saving 编辑拒绝点提前到任何设置写入之前；特定字符为空不保存改动；所有设置字段在 batch size 成功验证后才统一提交；风险快照开始与结束复读原 `*_risk_origin_v1.json` 字节，来源变化则保留原顺序并拒绝认证。

**接力下一步：**先查看 corrected-test [CI #41082255201](https://github.com/chigre/Picture_Capture/actions/runs/41082255201) 六平台 + Risk、[OCR #41082255256](https://github.com/chigre/Picture_Capture/actions/runs/41082255256) 三平台和 CodeQL Python/Actions 2/2；再核查最新文档 HEAD exact SHA 所有检查。红灯必须读 job log 修复，不因早期 mock 错误声称全部测试先行成功。已保留真实两类失败证据。默认风险优先/来源采集/匿名计时三个选项继续 OFF；不修改 PDIC/PPP/SECTION/OCR、不产生人工真值、不上传用户内容。

后续剩余真正门槛为人工 Windows R3 E3、#483 W1–W11 和 #503 Undo/Redo；准备好的 [R4.2 Windows 操作者 runbook](https://github.com/chigre/Picture_Capture/blob/1611f7c60a5f3f93ca191e01b9ee7cc47248c493/docs/architecture/G3_R4_2_OPERATOR_ACCEPTANCE_20261030.md) 尚未执行。R6 标签不齐，R8 真实扫描待用户决定。保持唯一 Draft #663 不合并，不开启 Ready，不改 main，不关闭 #483/#503/#562。

---

## 2026-10-30｜G3 R4.2 大批次：匿名计时、旧预取防串代次与 Windows 人工验收包（最新恢复入口）

GitHub verified previous exact baseline `efed96356e1bb69a490525d927a062f40d10ff09`: [CI 41074662522](https://github.com/chigre/Picture_Capture/actions/runs/41074662522) 6/6 + Risk, [OCR 41074662499](https://github.com/chigre/Picture_Capture/actions/runs/41074662499) 3/3, CodeQL Python/Actions 2/2 全绿。#663 保持 Draft/Open/unmerged，main `ec20989ea8c026cca5337293e67850b6b6df30f2` 未改。

本轮测试先行 `a5414d69071a8c9fdb4e0d12fbb7f3939790f473` 缺 review_timing 模块 red；代码 `af797e858a2795e41eb51b7f9a435b9c0d096f7e` 新增 `ReviewTimingSession`：扫描/来源风险校验/预览生成/PDIC 保存的**本地内存**秒数和数量，仅包含聚合整数+浮点，无词条、原图、坐标、页面名、文件自动写入、网络上传；非人工主动校对时间，risk 含于 scan，不得相加宣称加速。第三个 GUI 默认 OFF 开关 `focused_review_timing_enabled=False`，只有点击「筛选」后新 epoch 采样；界面标签显示汇总。新增初始 worker invalidate、render serial advance、预取与渲染同时固定 scan epoch，旧扫描的迟到 done/failed 不能更新新一轮缓存或清除其 key；保存与人工修改仍用原可靠队列和源 X/Y。

源 [CI 41077510554](https://github.com/chigre/Picture_Capture/actions/runs/41077510554) Ubuntu py3.13 **4978 passed / 3 skipped**、Risk-tier、CodeQL 2/2 SUCCESS；[OCR 41077510565](https://github.com/chigre/Picture_Capture/actions/runs/41077510565) Ubuntu 成功，Windows job 在安装 setup-uv 的 GitHub 版本 API 报 Server Error、**测试未执行，不能视为通过**；macOS pending。其他 full OS/Python CI 仍 pending。**下一步先核对最新文档 HEAD 的全部 matrix 和安全门禁**；如果失败按日志修，非本地网络问题不改无关功能。Windows 操作者流程已写 `docs/architecture/G3_R4_2_OPERATOR_ACCEPTANCE_20261030.md`，全是 NOT PERFORMED，#483 W1–W11、R3 E3、#503 压力 Undo/Redo 仍另行验收。没有人工标签不启动 R6，R8 真实扫描延后。

---

## 2026-10-30｜G3 R4.2 重点筛选 Tk 可选队列：旧设置兼容修复（最新恢复入口）

#663 最新的选配 UI source `9ac248699e05b1524ca56cbe24a8b06f2729a18c` 完成 Tk 高风险优先与来源时证明采集两个默认 OFF 开关，但 CI 发现旧 `SimpleNamespace` 不具备两个新 Tk BooleanVar，导致旧测试 `test_focused_setting_write_validation_and_clamp` 抛 AttributeError。此失败是**真实回归，不是预期 RED**。已提交小修 `f7cba75de0dadb755b8eaa7505e39e31ce9f0f44`：缺少新控件时保留原设置或默认 False，真实窗口仍按 Checkbox 值保存。复测 [CI #41074003807](https://github.com/chigre/Picture_Capture/actions/runs/41074003807) Ubuntu py3.13 **4971 passed, 3 skipped**，OCR [#41074003632](https://github.com/chigre/Picture_Capture/actions/runs/41074003632) 3/3、Risk-tier、CodeQL Python/Actions 2/2 成功；其他 Python/OS 仍须读取 exact-head conclusion，不能预先宣布 E2 全部通过。

上一严格 SECTION `e60c59f9bb5a4a1656457f4e056c63986f5f39f6` 全绿自动化基线。默认 OFF 时筛选顺序、身份与 IO 不变；ON 时每页批量验证 OCR/PDIC/image/SECTION 与来源侧记录，只对已证明来源的诊断在同页连续 SECTION 内稳定排序，unknown 不冒充 normal；不能扫描未保存修改的可见批次，勾选变化需按「筛选」开启新 serial，不会中途重排编辑器。来源捕获仅下次批量 OCR/combined PDIC 成功落盘后才可选写文件。

**恢复动作：**先确认修复源 `f7cba75...` 六 CI 6/6、Risk、OCR 3OS、CodeQL 2/2；再确认最新文档 HEAD exact CI；若失败查日志修复，不推 merge。后续 local-only anonymous aggregate timing + GUI 工作者序列和 SECTION 人工 W1–W11 在获真实用户许可后进行。#663 Draft/Open/Unmerged、main 未修改；R3 E3、#483 W1–W11 仍 NOT PERFORMED；R6 人工标签缺失、R8 真实扫描 deferred。

---

## 2026-10-30｜G3 R4.2 可选风险优先队列已接入重点筛选（最新恢复入口）

前一 `e60c59f9bb5a4a1656457f4e056c63986f5f39f6` 已由 GitHub exact SHA 验证 CI 六平台 6/6、OCR 3/3、Risk-tier 与 CodeQL Python/Actions 2/2 全绿，SECTION 原图 XY 归属可作为来源快照基础；仍无人工真值。

本轮 `155727da9783178f8e9257e8e72a17682edb73df` 是 red-first（Ubuntu CI 41072980340 预期缺 review_risk_snapshot 模块），生产 `9ac248699e05b1524ca56cbe24a8b06f2729a18c` 把默认 **OFF** 的高风险优先选项实际接入 Tk「重点筛选」，并提供第二个默认 OFF 的「下次批量 OCR 记录来源证明」选项。仅在重新点击「筛选」后保存设置并捕获新 worker epoch，已经显示的编辑器不会被切换开关直接重排；尚未保存或仍在后台保存的编辑会阻止清空和重新筛选。每页合并读取来源 witness、OCR/PDIC/图像/SECTION、严格唯一源XY，并复检哈希；风险判定为 priority/normal/unknown，只在同页连续 SECTION 内稳定排序，缺少来源不能凭旧缓存认定高风险。默认 OFF 保留原列表和无额外页面读取。无需更改人工 PDIC、PPP、SECTION 或 OCR JSON。

**恢复动作：**核查生产 [CI #41073344700](https://github.com/chigre/Picture_Capture/actions/runs/41073344700) 六平台和 Risk、[OCR #41073344750](https://github.com/chigre/Picture_Capture/actions/runs/41073344750) 三平台、CodeQL 2/2 的 exact HEAD conclusion；有失败必须读对应 jobs logs 修复。**再**核对文档最终 HEAD 完整 CI。后续仅在自动化门禁绿时继续 R4.2 local-only aggregate timing / 明确 Windows E3 验收材料，不能凭 pytest 替代真实 GUI 操作与用户 W1–W11。#663 必须 Draft/Open/Unmerged、main 不动；R6 无可用人工核验标签，R8 真实扫描延后。

---

## 2026-10-30｜G3 R4.2 SECTION 原图几何严格归属（最新接力）

前一个 `b49d1ef181828f1699e2fc9e5304bac4cfb23d0c` 已由 GitHub 验证全部 CI 6/6 + Risk、OCR 3/3、CodeQL Python/Actions 2/2 SUCCESS。现仍唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663)，main 不动。

本轮 test-first `cd7aa3f055515e0e3785c05ef8cedb36329dee66` 预期缺 `review_section_provenance`；源 `ffbe5ded4c8b4de6f8b47bc01a8045a259cd1332` 新增严格 SECTION v2 原图 X/Y 归属，不用历史 UI 的最近区域逻辑：核对原图 EXIF 后尺寸、四种 layout transform、每条 source segment 与真实区间、序号与无重叠，再确认点唯一落在半开区间内。不在区域、边界歧义、坏文件、跨SECTION 不能认领。来源时 witness 增加原图SHA、SECTION SHA、候选所属 `section-N`，读取时复检旧图/缓存/PDIC/SECTION；只写软件自有可选来源 sidecar，设置继续默认 OFF；**未接 Tk 队列**。4 种变换与恶意损坏/间隙/同尺寸换图均有合成测试。

**恢复动作：**查询源 [CI #41068586911](https://github.com/chigre/Picture_Capture/actions/runs/41068586911)、[OCR #41068587040](https://github.com/chigre/Picture_Capture/actions/runs/41068587040)、CodeQL Python/Actions 的所有 exact-SHA conclusion，并核验最终文档 HEAD 6+3+2+Risk；任何错误查 job logs 修正，不能因 Ubuntu py3.13 `4961 passed, 3 skipped` 和 OCR 已绿就提前宣布全部完成。源全绿后才考虑 R4.2 Tk 选配队列的每页快照与 worker serial/cancellation、安全定位和 local-only timing。Windows R3 E3、#483 W1–W11 NOT PERFORMED；无人工真值或真实基准，R6 blocked、R8 deferred；不合并、不开 Ready、不关闭 #503/#562/#483。

---

## 2026-10-30｜G3 R4.2 来源时 witness 只读选配提交（最新恢复入口）

上一 checkpoint `f8d2d48acb68df3f11b83445d7ef2f0155ff8e99` 已经由 GitHub exact SHA 验证六平台 CI 6/6、OCR 3 OS 3/3、Risk-tier 和 CodeQL Python/Actions 2/2 全绿，**只是无 Tk 接线的 R4.2 基础模块**。

本轮先发 red-first `a81075569ed32e2c4d4618cc1c4bfcf9d8e1ce66`，Ubuntu CI 41064417899 预期 ModuleNotFoundError；随后实现 `2985eb6610aa54f070bf07eb919bf792678b6f67`：新增 `proofreading/review_risk_witness_storage.py`，以及 settings 默认 **False** 的 `focused_review_risk_witness_capture`。批量 OCR/combined 的 PDIC 已经落盘后才可选地生成 OCR/PDIC SHA256 来源时 witness，只支持**无 SECTION sidecar**，有 SECTION 或无法唯一证明候选ID、原图XY、词文本归属时跳过。文件保存前后复验；按真实当前文件复核旧 witness。不会改写 OCR JSON/PDIC/PPP/SECTION，默认不生成 sidecar，界面仍未接高风险优先排序。

**恢复动作：**核对源 [CI 41064630984](https://github.com/chigre/Picture_Capture/actions/runs/41064630984) 六平台 + Risk、[OCR 41064630989](https://github.com/chigre/Picture_Capture/actions/runs/41064630989) 3OS、CodeQL Python/Actions，失败按日志修复；另核对最新文档 HEAD，不以旧提交成功替代。继续 R4.2 SECTION 几何严格归属和默认 OFF Tk 实际接线之前，不能称 UI 高风险优先功能完成，不能把此 witness 当 OCR 错误真值。main 不动，#663 Draft，不合并，Windows R3 E3/#483 W1–W11 仍 NOT PERFORMED。

---

## 2026-10-30｜G3 R4.2 只读来源证据与默认 OFF 的稳定队列（最新接力）

[Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663) 当前以 `c6426614e112e0d8bc7a4d80aae941575e301b47` 全绿作为 R4.1 E2 基线：CI 六平台 6/6 + Risk-tier、OCR 3OS 3/3、CodeQL Python/Actions 2/2 成功。R4.1 不是人工真值分类。

本轮先提交测试 `c155a8dda3cf032b43e93ba396fcc2ba7b2d8dff`，Ubuntu 预期缺少模块导致 red；再提交生产 `898d90261727b3c5515cba43e5255b294e7135df`：新增 `proofreading/review_risk_queue.py`，只读检查 OCR/PDIC 实际 SHA-256、候选ID和原图X/Y唯一归属、SECTION sidecar 版本指纹与几何 SECTION 来源，同时提供只按原始页与连续 SECTION 段内稳定排序的函数，默认 OFF。缺少独立**来源时** witness 的老缓存一律 unknown；不能在校对时自行生成证据冒充来源。**尚未接线 Tk、尚未建立持久化来源证明，也不产生真实界面优先队列。** 保留原重点筛选、批次导航、Undo/Redo、用户所有文件与主分支不变。

**恢复动作：**源 [CI #41059425448](https://github.com/chigre/Picture_Capture/actions/runs/41059425448)、[OCR #41059425445](https://github.com/chigre/Picture_Capture/actions/runs/41059425445)、CodeQL Python/Actions 要确认 exact SHA 6+3+2+Risk 全绿；本段提交时源 Ubuntu py3.13、OCR 3/3、Risk 成功，其余 pending。再检查最新文档 HEAD 的全部 CI。随后单独研究可靠来源时 witness 的可选采集、SECTION geometry、界面明确 OFF 开关与 worker cancellation，不可直接对所有旧缓存排序。Windows R3 E3、#483 W1–W11 仍 NOT PERFORMED；R6 标签、R8 真实扫描 blocked；#663 仍 Draft 不合并。

---

## G3 R5.2 exact E2 + R4.1 fail-closed triage（2026-10-30）

R5.2 `11aa70a0a9327b7bac6080f863aa212da1af27de` 已核实 [CI 40968076780](https://github.com/chigre/Picture_Capture/actions/runs/40968076780) 六平台+Risk-tier、[OCR 40968076632](https://github.com/chigre/Picture_Capture/actions/runs/40968076632) 三平台、[CodeQL 40968072905](https://github.com/chigre/Picture_Capture/actions/runs/40968072905) Python/Actions 全部 SUCCESS，仅合成 E2。R4.1 红先行 `c3caec35` 预期 ModuleNotFoundError；源码 `460383db864663854905e7f8d2dd1abd665e26ca` 增加只读 `proofreading/review_risk.py`：需独立核验 OCR+PDIC SHA、project/page/SECTION、唯一 source XY，才输出 priority/normal，否则 unknown。源 [CI 40971810563](https://github.com/chigre/Picture_Capture/actions/runs/40971810563)、[OCR 40971810731](https://github.com/chigre/Picture_Capture/actions/runs/40971810731)、[CodeQL 40971805624](https://github.com/chigre/Picture_Capture/actions/runs/40971805624) 及最终文档 HEAD 必须核实结论。R4.2 UI 尚未接入，默认排序不变。详见 [R4 来源审计](../architecture/G3_R4_PROVENANCE_REVIEW_TRIAGE_20261030.md)。PR #663 唯一 Draft/Open/Unmerged；main 不变；Windows R3 E3、#483 W1–W11 **NOT PERFORMED**；无 R6 训练或真实扫描基准。

## 2026-10-30｜G3 R5.2 独立 OCR 仲裁 q 快照/纯函数（最新接力）

基线 R5.1 已在 `234870694bca285117deb6a863c11bd705f3891c` 确认六平台 CI #40965627205 6/6、Risk-tier、OCR #40965627204 3/3、CodeQL Python+Actions 2/2 全部成功。**仅为 E2 自动化，不等于真人 E3**。

本轮仍在唯一 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663)，先做 fail-first `5cd39dddc278553b10ded5d0efb57ff54f9375f3`（预期缺少 q 纯评分模块），再提交源代码 `e57346968a48372a0cb633cc63c6fce8fe0f0db9`：新增 `ocr/engine_quality_scoring.py` 的不可变、可 JSON 序列化的 11 字段快照及有序纯评分函数；`ocr/pairing_arbitration.py` 保持 pair/前缀转换及 monkeypatch 入口、三引擎投票逻辑、Lens diagnostic-only、并列 tie、门槛和原图坐标不变。新增 512 组纯 q 浮点逐项对比、异常值/边界值、P/T/L 及 15 个全量输出差分场景。

**唯一恢复动作：**检查源代码 [CI #40967756737](https://github.com/chigre/Picture_Capture/actions/runs/40967756737) 六平台、[OCR #40967756750](https://github.com/chigre/Picture_Capture/actions/runs/40967756750) 三平台及 CodeQL Python/Actions 的最终 conclusion；有失败立即查日志修本包，不能将 queued/in_progress 当 success。当前本节提交前 OCR 3/3 和 Risk-tier 已成功，完整源 CI 未完成。随后核对最新文档 HEAD 全套检查并将 R5.2 E2 标为 verified，方可启动 R4 priority/normal/unknown + 默认 OFF 队列。人工 E3、#483 W1–W11 仍 NOT PERFORMED，R6 标签阻塞，R8 真实扫描延后，不合并、不标 Ready、不关闭 #503/#562/#483。

---

## 2026-10-30｜G3 R5.1 candidate score immutable/pure checkpoint（历史完成证据）

同一 [Draft #663](https://github.com/chigre/Picture_Capture/pull/663) 中，基于 `50a913ef` 已完成 G2 全平台绿灯的基线，先提交 fail-first `9426de03`（缺模块导致预期 collection error），再在 `33fbef91` 将候选过滤器12项打分布尔特征抽为冻结可序列化快照和纯函数（精确保留原加法顺序，不改接受/拒绝/原图XY/保存逻辑），新增穷举4096组合、三个OCR来源及拉丁/CJK等合成差分用例。第一个 CI 暴露测试误以为所有 diagnostics 都是候选，实际另有合法页面级 meta；仅修正测试、绝不删改产品 meta，最新源和测试 HEAD `f63d8805d54100adafb802ed2bedd1ff91dd226f`。

**恢复动作：**核对该确切源 HEAD 的 [六平台 CI #40965305404](https://github.com/chigre/Picture_Capture/actions/runs/40965305404)、[OCR 3OS #40965305118](https://github.com/chigre/Picture_Capture/actions/runs/40965305118)、CodeQL Python+Actions；排队/运行中不是通过。有失败按真实日志修复；全绿后才能标记 R5.1 E2 完成，再启动 **R5.2 独立仲裁 q** 的纯函数/缺失值、边界强度、修复数、forced status及 Lens diagnostic-only 差分验证。**R4 默认 OFF，R6 未核标签 blocked，R3 Windows E3 / #483 W1–W11 NOT PERFORMED，PR 保持 Draft 不合并 main**。详细见 `docs/architecture/G3_R5_SCORE_Q_PARITY_AUDIT_20261030.md`。

---

## 2026-10-29｜G1 OCR candidate choice + 原图 Y 位置切换（此节为最新执行接力）

本次仅在 [Draft #663](https://github.com/chigre/Picture_Capture/pull/663) 内处理
`ui/review_selection_workflow.py` 一个 UI owner 的真实顺序错误：
人工 candidate choice 曾在 OCR 数值校验和 PDIC 保存前先落盘 manual_selection，
位置切换在兄弟候选完整暂存前就撤掉 Entry/checkbox。
先提交回归 HEAD `b036c68ef1c6cb9ba8c918c98210e6962e9e6e3b`，
[CI 40750612646](https://github.com/chigre/Picture_Capture/actions/runs/40750612646)
Ubuntu/Python3.13 **7 failed / 4722 passed / 3 skipped**，均为新故障注入反例。
随后修复为先校验、候选和兄弟人工作业内存批量暂存、严格
`candidate_id` 归属（禁止附近 X/Y 认领）、PDIC 优先持久化，
失败则依磁盘实际字节恢复 UI 或隔离不确定状态，**不擅自覆盖第三方人工字节**。
测试覆盖健康流程、写前/写后错误、外部人工竞争、旧版原始 Y 切换和
ReviewWindow 未提交时不准 Undo。详见
`docs/architecture/R3_G1_MANUAL_SELECTION_ORIGIN_AND_CHECKBOX_20261029.md`。

以 GitHub **最新 #663 HEAD 的 exact-head 六平台 CI/Risk、OCR 3 OS、
CodeQL Python/Actions** 为本包完成证据；queued、skipped、旧 SHA 通过均不可计入。
本节是新代码/测试提交记录，不能代替最新 CI 或 R3 真人 E3。
#663 保持 Draft/Open/Unmerged；#503/#562/#483 均不因合成测试关闭，
真实 Windows candidate/Undo/Redo×20/FocusOut、PDIC/PPP/SECTION、原图裁切
和 R2 W1–W11 **NOT PERFORMED**。先审查最终 CI，若失败只修本包。
若通过，下一安全包是剩余 FocusOut/自动保存和 ReviewWindow 历史
交叉边界；无复现实证则只读阻塞而非机械迁移。

---

## 2026-10-28｜v1.3.0 全库复审后唯一执行入口（取代以下旧接力状态）

**从现在起仅推进 [Draft PR #663](https://github.com/chigre/Picture_Capture/pull/663)**，同时跟踪 [#503](https://github.com/chigre/Picture_Capture/issues/503) R3 与 [#562](https://github.com/chigre/Picture_Capture/issues/562) 架构；旧 #664 关闭未合并，完整提交历史通过双父合并 HEAD `66ad88c276b6965c075eeb72583b42dd0aa7f3ac` 纳入 #663。旧文本中「新建 #503 实施 PR」「#542 仍当前 PR」「重新从 B0 启动」均为历史，不再作为可执行指令。

每次恢复**先**读取 `CORE_QUALITY_UPGRADE_PLAN.md` v1.3.0、`CORE_QUALITY_STATE.json` 中 `audit_20261028` 及 [全库复审](../audits/WHOLE_CODE_AND_ROADMAP_REAUDIT_20261028.md)，**再读取 GitHub 真实 PR HEAD 和 CI**（它们高于本文快照）。最近审计基线 `66ad88c276b6965c075eeb72583b42dd0aa7f3ac`：[#40559523622](https://github.com/chigre/Picture_Capture/actions/runs/40559523622) CI completed/success 6/6、[#40559523187](https://github.com/chigre/Picture_Capture/actions/runs/40559523187) OCR Smoke completed/success 3/3。只保证**该旧 HEAD**，不能直接用作下一次新提交证明。

**唯一下一主题 G1：#503 R3 候选归属、manual_selection/PDIC/simplified、Undo/Redo 和崩溃恢复的所有权/版本失败矩阵；**不重复已存在的 O_EXCL、非普通标记拒绝或多文件核验。其次 G2 `app.py`/大 owner 有限抽取、G3 R5 parity 与 R4 默认关闭可解释优先队列。禁止依赖源码行数声称性能提升；R6 没有经人工 verified 的标签保持 blocked；R8/真实扫描 PR-B 继续用户延后。

每个包：HEAD/CI/是否并发修改检查 → 责任 owner / 反例 → 源码、回归、架构文档 → 实际提交 → 新 HEAD 六平台 CI、OCR Smoke、按需 CodeQL 与人工门禁分别记录 → 两个 Issue 同步。**PR #663 维持 Draft/Open/Unmerged，不标 Ready，不合并 main**。真实 Windows 字典 R3 20-step Undo/Redo、候选checkbox、FocusOut、PDIC/PPP/SECTION/crop、source-image X/Y 人工验收 **NOT PERFORMED**；R2 #483 W1–W11 未验收。可因安全 blocker 停下，不可补造测试结论。

---

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
