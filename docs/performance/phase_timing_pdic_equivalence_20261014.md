# #496 分阶段诊断与 PDIC 严格等价验证

## 性能分析（不会改变识别、画线或保存算法）

可在 Windows PowerShell 中设置环境变量，然后**从同一个 PowerShell 窗口启动应用**：

```powershell
$env:PICTURE_CAPTURE_DRAW_PROFILE = "1"
# 然后运行你平时使用的 Picture_Capture 启动命令
```

处理普通画线或 OCR 画线后，完成状态会显示各阶段累计耗时。独立 JSONL 记录位于当前用户的 PictureCapture 数据目录下 `draw_profiles/<PID>.jsonl`。每个子进程写自己的日志，避免跨进程争锁。

普通画线记录 `bootstrap`, `image_open_normalize`, `page_sections`, `detect_entries`, `automatic_baseline`, `pdic_write`；GPU 预检测额外记录 `gpu_read_normalize`, `gpu_prepare`, `gpu_layout_detection`, `gpu_finalize`。OCR 画线记录 `ocr_image_load`, `ocr_detect_entries`, `ocr_marker_text_fill`, `ocr_preserve_and_pdic`, `ocr_audit_resume`。

**重要**：这些是每页/每 worker 的墙钟耗时总和，GPU 预检测与 CPU 后处理可能重叠，因此阶段累计耗时可能大于整个批次的真实耗时。 `ocr_detect_entries` 含 OCR 计算与内部后处理；它不等于精确的 GPU kernel 时间。默认不开启，以避免在大量页面中产生额外 IO。

## 完整 PDIC 等价验证（只读）

同一套测试图片/参数，在改动前后各获得**独立保存**的 PDIC 文件树。不要直接在原目录重跑并覆盖基线。两个目录的相对路径应相同。推荐在两份项目副本中运行，或在每次运行后复制所有 PDIC 文件（含 `_PictureCapture` 下管理目录）到独立目录。

```powershell
python scripts/compare_pdic_snapshots.py "D:\\benchmark\\baseline" "D:\\benchmark\\candidate" --json "D:\\benchmark\\pdic_compare.json"
```

返回码：
- `0` 完全一致；
- `1` 页文件缺失/增加，或任意 PDIC 行及字段不一致；
- `2` 目录无效、非法坐标或读取错误。

验证包含：全部 PDIC 文件的相对路径、记录行数、文本、画线 X/Y 像素坐标、百分比、页面关联信息、记录顺序和其余全部字段。不会仅凭词条数相等判定通过。差异报告展示每个异常文件的前五处差异。

PDIC 一致性验证是 **严格输出一致**，不是与人工标注的准确率对比。由于 OCR 运行可能受模型和依赖版本影响，比较时必须固定模型版本、输入图片、画线参数和缓存/强制重跑策略。不同模式之间的算法输出若本来就不同，不应要求其 PDIC 字节级相同。

## 测试建议

同一批 20 页记录每种配置的总耗时、平均页耗时、峰值内存/显存、GPU/CPU 实际设备，以及完整 PDIC 比较结果。分别测试普通画线的串行、CPU pool、GPU stage，以及 OCR 画线的设备和 oneDNN 参数。还需验证暂停/停止、人工锁定页和 PDIC 备份机制。

**此变更仅添加诊断和验证能力，不表示各硬件配置已通过真实运行测试。**
