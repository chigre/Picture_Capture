# OCR画线：最终决策对齐与同栏排版一致性救回（PR #475）

## 真实执行边界

`DetectionController.run_ocr_draw_action → app._detect_pages → processing.detect_entries → evidence_fusion/filter_headword_records → apply_page_understanding → write_pdic`。

缓存中的 `review_candidates` 是 **OCR 仲裁阶段** 的观察；`PDIC` 是进一步经过 Layout/符号证据后、真正写盘的词条。二者没有理由天然相等。

## 最终决策 sidecar（不修改 PDIC 格式）

自动批量 OCR/融合画线每页成功写出 PDIC 后，读取实际 PDIC 并写入同页 OCR 缓存目录中的 `<page>_final_decisions.json`：

- `pdic_rows` + `pdic_snapshot_sha256`：原样保存词名及 X/Y，包含阅读顺序，供回读验证；
- `candidate_decisions`：每个 OCR 原始候选 `ocr_selected`、`final_selected`、`final_source_x/y`、`final_status`（retained、moved_by_post_ocr、removed_after_ocr、rejected）、OCR 原始理由；
- `final_only`：实际存在于 PDIC，但无法唯一关联 OCR 候选的横线（可能为 Layout/符号补线、ID 冲突等；**不得一概当作 Layout 补线**）；
- `summary`：候选数、实际横线数、唯一匹配数、后处理移动/删除数、未关联数。

候选 ID 必须唯一且位置合理；否则只有没有歧义的空间/词名匹配才允许关联。同一 PDIC 横线最多关联一个 OCR 候选。对于重复候选 ID、多个同样近的可能匹配，不猜测或自动转移人工状态。

侧车只用于审核和诊断，不反写 OCR 原始缓存、不迁移人工选择、不影响旧项目 PDIC 格式。

### 失效保护

打开候选审核时，只有 **当前 OCR 缓存签名匹配**且 **当前 PDIC 有序内容与 SHA256 全部匹配**，才将 `final_decision` 注释加入 OCR 候选供后续查看。人工校对修改文字、位置、增删横线，或强制重新识别改写 OCR 缓存，都会使旧快照失效。运行失败、异常或中断后不得把旧 sidecar 当成新的完成状态。

当前主界面绘制的仍是实际 PDIC 横线；`final_only` 不会被伪装成可编辑的 OCR 复选候选。后续如需要 Layout-only 专属审核控件，必须提供独立的人工覆盖语义。

## 同栏可信排版证据：对正文续行的保守救回

新增的 `ocr_peer_style.py` 只处理拉丁文字 OCR 的 `continuation_fragment`，且须同时满足：

1. OCR 置信度 ≥0.90，候选词头长度合格；
2. 明确语法证据（词性/屈折、前部结构、尾部结构之一）；
3. 栏首、页眉下方、无用户显式否定和硬反证；
4. 与候选互相匹配的原图白缝证据，strength ≥0.55；
5. 附近至少三条原始 OCR 阶段接受的可信词头，**候选上下两边都有**；
6. 左缘、相对高度及墨迹粗细与相邻可信词头一致。

仅原始已接受样本可以充当锚点。旧的“粘连词性救回”、这一新救回以及各引擎候选均不能递归为彼此提供新锚点。新救回会把使用的 peer 证据和原因放入诊断，供回归及人工审阅。CJK、大字头、页首尾、稀疏页和无安全白缝的页面默认 abstain。

**不会**因为单纯“粗体”或“一行看起来像词头”提升候选。现有词头解析、原图安全 Y 修正、手动校对与 PDIC 输出完全保留。

## 实验验证边界

新增自动化测试覆盖最终 PDIC 读回、状态关联、重复 ID、OCR 缓存失效、人工编辑失效、排版风格真/假例、CJK 排除、硬反证和**固定原始可信锚点**。这只说明逻辑约束，不证明真实词典准确率提升。

实际评估应对当前 main 与此 PR 同一完整扫描/设置/硬件环境运行：

```powershell
python scripts/detection_benchmark.py "D:\\YourProject" --modes paddleocr,combined --pages 1-30 --force-ocr --output benchmark_ocr_pr475.json
```

该示例的 `--pages` 输入形式应以脚本实际帮助为准；运行前先执行 `python scripts/detection_benchmark.py --help`。历史 30 页/1336 条真值与旧缓存对比，**不能充当本 PR 的 F1 改进结果**。

必须按词典报告 TP/FP/FN/F1，另测 Y 误差、人工修正次数、批量耗时、缓存磁盘增长与峰值内存。若葡汉 FN 改善但西汉 FP 明显变差，应维持旧默认或调整分项目策略；不可仅凭合并 F1 宣称成功。

## 已知限制

- `auto_detect_current()` 单页预览分支不会自动写入 PDIC，因此仅在真正保存 PDIC 的批量入口生成完成快照；
- 因 PID/横线索引被 PDIC 旧格式省略，无法无歧义对齐的项保持 unmatched；
- 早期无法获得跨页/整个词典完整字体先验；此版本只做同栏本次 OCR 原始可信样本内的排版比较。
