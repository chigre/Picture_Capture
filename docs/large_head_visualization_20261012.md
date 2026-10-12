# 大字头检测可视化（只读调试工具，2026-10-12）

适用分支：PR #459。这个功能**不改变大字头检测、Layout role、普通画线和 PDIC 结果**。

## 在界面中使用

在「二、显示设置」打开「显示大字头检测」。可单独打开，也可和「显示Layout」同时打开。
- **绿色实线框**：正式 `ordinary_large_head_evidence` 检测器通过形态、行首及强大字证据的候选。
- **黄色虚线框**：几何大小/密度不符，或虽满足基本几何却达不到强证据阈值。
- **红色虚线框**：行首位置不匹配，或整块墨迹过高而不能安全拆分。
- **蓝色短横线**：候选附近的**最终普通自动画线位置**，来自真实 `processing.detect_entries` 的当前运行输出。

点击检测框，会显示候选 ID、栏、真实源图像框坐标、宽高、相对当前页普通行高的倍率、失败/通过理由、检测器最终是否输出此候选、最近 Layout 行的角色和证据，以及附近最终线数。

「导出大字诊断 JSON」使用标准文件保存对话框，由用户自主选定路径。**不会自动写入项目数据目录，不会更改 PDIC。**

## 结构与证据可解释性

- `ordinary_large_head_evidence.detect_ordinary_large_head_entries` 新增一个**可选** `diagnostics` 列表参数。正常画线从不传此参数，算法、阈值、Entry 返回值和去重顺序不变。
- `_candidate_boxes` 在诊断模式中提供通过/拒绝的候选框。形态判定仍调用原 `_valid_single_head_box`；行首判断仍调用 `strict_candidate_starts_at_row_front`。
- `large_head_visual_diagnostics` 用该检测器、当页相同 Layout 及 Profile 构造只读快照。**最终线独立通过 `processing.detect_entries` 重算**，不拿用户已经编辑过的 PDIC 线充作自动真值。
- 最近 Layout 行匹配和最终线匹配都是**坐标邻近关系**。一个大字候选被确认、附近有最终线，并不证明这条线只由该候选产生（它也可能由 indent 或 bracket 生成）。
- 诊断快照只缓存在本次 GUI 会话内，切换图像、页面、Profile 参数或去噪强度会重新检测。

## 限制与安全边界

1. 展示的是进入正式候选管线的形态连通区域，并非全页面每一个黑色像素或被最初 `_large_fragments` 排除的微小笔画。
2. 可视化仅支持显示普通画线的最终结果。对于 Paddle/Combined 等模式，仍可查看候选形态，但不会将其最终 OCR 线标作普通画线结果。
3. 对于启用了「屏蔽大插图」的页面，诊断沿用正式 Layout 使用的掩码分析图片。
4. 诊断可能增加一次候选分析和一次只读的最终自动画线计算；只在显式打开时执行，并在本页显示状态未变化时重用结果。
5. 可视化回归要求：开启或关闭诊断时，`detect_ordinary_large_head_entries` 的返回坐标及角色、常规 `processing.detect_entries` 不受影响。真实页的视觉验收依然需要用户截屏或运行导出的 JSON。

