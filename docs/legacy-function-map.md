# 旧版功能映射

| VB.NET 入口 | Python 对应位置 | 状态 |
| --- | --- | --- |
| `OpenFile` / `ListBox3_SelectedIndexChanged` | 主窗口“打开目录”与页面列表 | 已复原 |
| `OpenTetIfExist` / `Save_Pdic` | `formats.read_pdic` / `write_pdic` | 保持旧格式 |
| `DRAW_COORDS` / `Draw_Auto` | `processing.derive_geometry` / `detect_entries` | 恢复动态横向搜索，并升级为分段变形列跟踪；当前保留左缘规则与 PaddleOCR 词头坐标策略 |
| `PictureBox1_MouseMove` / `Paint` | 状态栏原图坐标 / 明确 canonical U/V ＋蓝色定位线 | 已复原；旧显示坐标仅作迁移兼容 |
| `PictureBox1_MouseDown` | 画布左键添加、右键重画栏 | 已复原 |
| `OCR` / `text_Process` | `run_tesseract`、`recognize_paddle_text` / `process_ocr_text` | 支持 Tesseract 5 和可选 PaddleOCR 3.x |
| `Split_OCR(0)` / `LoadTextOcred` | OCR 菜单的导出/导入 | 保持 `.OCRed` |
| `Split_OCR(1)` | `split_single_lines` | 保持 `QT/PSW` 与 `.PSWords` |
| `split_WHOLE_from_PDIC_FOR` | `split_whole_entries` | 保持跨栏/跨页切图逻辑 |
| `Save_PPP` | 多边形模式与 `write_ppp` | 保持 `.ppp`（读取旧 `.PPP` 兼容） |
| `Form2` | “校对”窗口 | 已复原并简化布局 |
| Timer 批量画线/OCR/切图 | 菜单批量命令与 CLI | 已复原，逐页显示进度 |
| `_Mysettings.ini` | 兼容读取；新设置写入 JSON | 已复原 |
| `_WordsOfPages.txt` | 工具菜单“导入旧版” | 已复原 |
| `TOP` / `RIGHT` / `CK1–CK5` | 无隐蔽口令 | 开发诊断入口未照搬；坐标和日志改为常显/自动 |
