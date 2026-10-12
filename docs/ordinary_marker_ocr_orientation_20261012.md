# 普通画线 → 单纯OCR：词头文本方向/错字诊断与修复（2026-10-12）

## 报告现象
用户提供了繁体双栏词典主界面截图，左侧「阅读方式」显示「横排：左→右」。
普通画线后执行【单纯OCR】，灰色可编辑词头文本框中的文字出现乱码/异常字符，
例如印刷三角形条目标记可能被识别成向左指的符号。

**截图不能单独证明根因为方向，也可能与OCR使用的语言包、释义区被截入、
OCR行框检测、字形质量有关。不要对 OCR 返回的字符串盲目做 reverse()。**

## 真实执行链
`PictureCaptureApp.ocr_ordinary_lines_text_selected_scope`
→ `processing_core.ocr_existing_entry_words_from_markers`
→ `_page_geometry_context` 有效页面 Profile + canonical geometry
→ `entry_ocr_crop_box` 测定正向坐标框
→ `_ordinary_marker_local_crop` 取实际送入OCR的图像
→ `OcrChannelSession.recognize_crop`（Paddle/Tesseract/Lens）
→ `parse_headword_text` 与通道择优
→ `Entry.word` → write_pdic → 页面重新载入 `tk.Entry.insert`。

普通画线的 Entry.x/y 本身不修改。UI 的 `tk.Entry` 根据文本
方向仅调整对齐方式（`rtl` 时右对齐），不是将字符顺序倒排。

## 本次代码修复

1. 原先 `_ordinary_marker_local_crop` 直接从
   `geometry.transform.canonical_image_for_analysis` 后的图像裁切。
   如果为了 Layout 使用 `mirror_x` 或 `rotate_*90`，
   OCR 会收到翻转或旋转后的中文字形。
2. 横排页面现在仍用**相同的 canonical crop box 与字符高度逻辑**
   定位，但会将该 box 通过 `geometry.transform.canonical_box_to_source`
   映射回原图，改从规范化的**原始扫描图**裁切。
   避免 OCR 输入携带仅供 Layout 用的镜像/旋转、页眉屏蔽等处理。
   文字本身不反序、不改画线坐标、不改词条数量。
3. 行高、行距估计从 `settings` 更改为与页面空间参数一致的
   `effective`，避免普通画线与后续 OCR 用不同 Profile 计算物理行。
4. 竖排页面保留历史 canonical OCR 裁剪行为，不擅自改变竖排识别；
   原有 Tesseract PSM=5 分支和 Paddle 文本行朝向配置不变。
5. 单元测试使用红/绿/蓝非对称墨迹块检查
   `identity`、`mirror_x`、`rotate_ccw90` 情况下，
   横排最终 OCR 输入字节与**原始源图对应区域完全一致**；
   保证 Entry 坐标不变化且竖排行为不回退。

## 验收和已有错误词条的处理

【普通画线后OCR文字】默认为**只填空白**（`only_blank=True`）：
原有文字或人工校对过的文本不会被覆盖。因此更新代码后，
直接再次按【单纯OCR】**无法修复已经填入的错误词条**。

请先备份当前 PDIC，然后在复制的测试项目中，恢复执行 OCR 前
只含空白画线的 PDIC，或仅清空要重识别的错误词条，重新运行
【单纯OCR】。不应为此重新普通画线覆盖已编辑内容。

同一张原图和相同OCR模型/语言设置下，逐条对比：
- 词头裁剪是否水平正向且不包含相邻栏内容；
- `layout_transform` / `layout_writing_mode` / `layout_text_direction`；
- Paddle/Tesseract 的中文简/繁语言配置；
- OCR结果是否仍将形似字符、三角形/中括号误认；
- 现存人工词条是否被保护、自动线数/X/Y是否完全不变。

如果实际 Layout transform 已是 identity，新增源图裁切主要避免
分析屏蔽引起的OCR取样损失；仍有错字时，应进一步审计原始OCR
输入截图、引擎语言与结果，而非断言此修复已经改善准确率。
