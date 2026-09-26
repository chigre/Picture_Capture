# Picture Capture v2.11.12 文件格式与输出目录

## 坐标契约

跨机器、跨版本可复用的标注坐标统一以**原图像素**为对外标准；原点位于原图左上角，X 向右、Y 向下。

- PDIC、PPP、最终 OCR 词头、Crop Plan 的 `source_xyxy`、切图日志：`source_image_pixels`。
- 项目版式设置与对外栏结构统一使用 `source_image_pixels`；不再保存 reference-width/canonical U/V 作为第二套持久化坐标。
- Profile 页眉/页尾/页边规则保存百分比，应用到具体页时解析为该页原图物理边界。
- OCR band/analysis/旋转坐标只属于函数内部临时计算，不作为项目设置或对外坐标。
- 旧 `parameter_display_width` / `geometry_reference_width` 仅用于一次性迁移历史项目。

完整定义见 [coordinate-system.md](coordinate-system.md)。

## 1. PDIC

每个扫描页可有一个同名 `.pdic` 文件，例如：

```text
0001.png
0001.pdic
```

每行格式：

```text
词条#X#Y#X比例#Y比例#当前页#上一页#下一页
```

示例：

```text
一#28#630#0.85#19.07#0001#@#0002
```

说明：

- `X/Y`：原始图片像素坐标。
- `X比例`：`X / 图片宽度 × 100`。
- `Y比例`：为兼容旧格式，程序同样使用“图片宽度”作为分母计算 `Y / 图片宽度 × 100`，不是图片高度。
- `当前/上一/下一页`：用于旧工作流和跨页关系。
- 写入词条时，`#` 会替换为全角 `＃`，避免破坏字段分隔。

### 修复 PDIC 排序

【修复排序】仅按：

```text
栏号 → Y
```

排序；**X 完全不参与**。同栏且 Y 完全相同则稳定保留原 PDIC 先后顺序。

该功能不会重新配对“词条文字与坐标”。因此：

- 如果只是记录顺序错，可以修复。
- 如果错误保存时文字已经配到了错误横线上，应从备份恢复或重新填词/校对。

## 2. PPP

每页插图标注使用同名 `.ppp`：

```text
0001.ppp
```

每行包含：区域序号、标签、顶点列表。顶点使用原图像素坐标。

PPP 在软件中可：

- 自动识别生成；
- 人工绘制；
- 拖动顶点；
- 矩形拖动四边；
- 修改名称；
- 删除单个区域。

自动识别区域使用 AUTO 标识；人工改名后即视为人工区域，后续自动识别不会覆盖它。

PPP 名称与词头名称一致时，Crop Plan 视为“关联插图”。

## 3. wordslist.txt

辅助词表，一般是一行一个词：

```text
abandon
abase
abate
...
```

空行忽略；以 `'` 开头的注释行忽略。

用途：

- 主界面词条成员提示；
- 校对窗口右侧参考词表；
- 当前词附近快速定位。

它不是“分页填充词条文件”。分页填充使用下一节的 `_WordsOfPages.txt` 或兼容格式。

## 4. 分页词条文件 / `_WordsOfPages.txt`

【选择词条文件】接受包含页码边界的 TXT。支持的典型形式包括：

- 完整 PDIC / `_WordsOfPages` 风格记录；
- `page<TAB>词条`；
- `[页码]` 分组；
- `页码:` 分组。

纯顺序词表如果没有任何分页边界，不能用于【填充词条】，因为程序无法可靠判断一页结束位置。

## 5. PDIC 备份

【备份PDIC】生成：

```text
all_pdic_backup_YYYYMMDD_HHMMSS.txt
```

它把项目全部已有 PDIC 合并为一个备份文本。操作为后台流式写入，不读取扫描图片。

【恢复PDIC】选择此类文件后，只恢复主界面当前选中的页面范围，范围外页面保持不变。

## 6. PicDic 索引

【导出PicDic索引】生成：

```text
PicDic_index_YYYYMMDD_HHMMSS.txt
```

无表头，每行四列，Tab 分隔：

```text
WORD	xx.xx	yy.yy	page
```

示例：

```text
一	0.85	19.07	0001
```

X/Y 直接读取 PDIC 已保存比例值，不重新从像素计算，也不带 `%`。

## 7. QT 目录

项目打开后会自动使用/创建 `QT/`。主要内容：

### `QT/PaddleOCR/`

OCR 缓存与诊断。最终词头与所有对外坐标使用 `source_x/source_y` 原图像素；OCR box 等临时坐标仅用于内部诊断，不得回写为项目设置。

主要文件：

- `<page>.json`：OCR候选、几何、融合信息。
- `<page>_manual_selection.json`：人工候选选择覆盖。
- `<page>_ocr_diagnostics.txt`：OCR诊断文本。
- `<page>_ocr_comparison.txt`：多 OCR 比较。
- `<page>_issues.tsv`：需要人工复核的问题表。

“复用缓存”会尽量使用这些结果；“强制重新识别”会重新运行 OCR。

### `QT/PWW/`

词条切图输出目录。

每页还生成 `.PWWords` 清单，记录页面、序号、词头和图片文件名。`PicDic制作` 以这些清单为源。

### `QT/PIC/`

独立 PPP 插图切图输出目录。插图 manifest 使用 `.PPPictures`。

### `QT/PicDic/`

【PicDic制作】输出：

- `PicDic_<项目名>.dsl`
- `PicDic_<项目名>.dsl.files.zip`

DSL 中同一词头可关联多张词条图片；跨页连续片段会尽量附到前一真实词头。

### `QT/CropPlan/`

正式切图前生成的逐页 Crop Plan JSON。主界面“切图预览（主图）”和正式切图使用同一套关系判定逻辑。v3 文件显式包含 `coordinate_space: source_image_pixels` 与 `box_format: source_xyxy`，其中所有导出框均可直接回到原扫描图定位。

### `QT/_file_log.txt`

词条/单行切图日志。新建日志首行写入 `coordinate_space=source_image_pixels`，后续每行的 `source_x / source_y / width / height` 都是原图像素。旧日志没有该注释行，但数据仍按历史格式兼容。

### `QT/_illustration_crop_log.txt`

插图切图决策日志，例如：

- 已完整包含于词条切图，跳过独立 PPP；
- 与词条部分相交，已并入词条；
- 关联词条外部，单独导出；
- 未关联，单独导出。

### `QT/_CropSettings.json`

统一切图设置。词条切图和插图切图共用。

### `QT/_WordFillStatus.json`

记录分页词条填充后的数量核对状态，用于页面列表“填充状态”。

## 8. 项目设置文件

### `picture_capture_settings.json`

项目级主参数、OCR参数、显示参数、列显示状态等。

### `dictionary_profile.json`

Profile v2 文件，结构核心为：

```json
{
  "format": "picture-capture-dictionary-profile-v2",
  "preset": "latin_structured_symbols",
  "language": "spa",
  "overrides": {
    "settings": {},
    "grammar": {}
  }
}
```

- `preset`：内置版面 Profile ID。
- `language`：当前语言变体。
- `overrides`：项目相对 Profile 默认值的个别修改。

发布包中的 `examples/dictionary_profile.example.json` 仅供参考。

## 9. 训练标记包

【导出训练标记包】会收集已有 PDIC 页的：

- 原图；
- 最终 PDIC；
- 可选 PPP；
- Paddle/Tesseract/Lens 候选与融合过程；
- 人工选择覆盖；
- 项目参数与上下文文件；
- manifest。

用于后续训练、误差分析或跨机器复现实验。
