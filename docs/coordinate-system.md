# Coordinate system contract

Picture Capture 对用户、项目设置和持久化文件只保留一套坐标：**原图像素 X/Y（source_image_pixels）**。

## 唯一持久化坐标：原图 X/Y

- 原点：原始扫描图左上角。
- X：向右增加。
- Y：向下增加。
- 单位：原图 1 个像素。
- 适用：项目版式参数、OCR/画线像素阈值、PDIC、PPP、鼠标/人工标注、切图框、训练导出和所有用户可见页面坐标。

因此，设置中写 `34 px` 就始终表示原图 34 px。它不会因为图片宽度是 1400、2800 或 4200 而自动乘除倍率，也不会受窗口大小、查看缩放或 `parameter_display_width` 影响。

项目级几何参数（例如第一栏 X、正文起始/结束 Y、栏宽、栏间距、行高、行间空白、栏左微调）和 OCR/画线距离参数（例如候选带左余量、栏左容差、页眉搜索高度、横线安全距离、平滑半径）都遵守同一规则。

## Profile 百分比

页眉、页尾或页边若以百分比配置，百分比本身不是坐标。应用到某一页时，程序根据该页原图宽高计算一次边界，得到的实际位置随后使用原图 X/Y。

## 内部临时变换

为支持镜像、RTL、竖排、OCR 裁带或性能优化，算法内部可以临时旋转、镜像、裁剪或缩小图像。这些临时坐标只存在于函数内部：

1. 进入内部处理前，从原图 X/Y 得到临时位置；
2. 完成检测后，立即换回原图 X/Y；
3. 不把临时 U/V、analysis、OCR-band 或缩放坐标写入项目设置；
4. 不允许临时缩放倍率改变设置参数的含义。

换句话说，内部可以“怎么计算”，但对用户和文件只有原图 X/Y 一套坐标。

## 旧项目迁移

旧版本可能包含两类历史坐标：

- v1：相对于 GUI/显示宽度的 `legacy_display_pixels`；
- v2：带 `geometry_reference_width` 的参考页坐标。

打开旧项目并取得真实原图尺寸后，程序会把这些历史几何值**一次性换算成当前原图的全分辨率像素**，升级为 coordinate version 3。迁移后：

- `geometry_coordinate_space = source_image_pixels`；
- `geometry_reference_width` 和 `parameter_display_width` 不再参与运行；
- 新保存的 `settings.json` 不再写出这两个旧基准字段；
- 后续运行不再进行 reference-width 或 1400px 归一化。

旧字段只作为读取历史项目时的迁移输入，不是当前坐标系统的一部分。

## 命名规则

跨模块、持久化或导出边界统一使用能表达原图坐标的名称，例如 `source_x`、`source_y`、`source_xy`、`source_xyxy`。内部临时变量可以描述 analysis/band/transform，但不得作为用户设置或持久化坐标输出。

## 导出契约

机器可读 `coordinate_contract` 的持久化坐标版本为 3：

- annotations: `source_image_pixels`
- settings_geometry: `source_image_pixels`
- tuning_distances: `source_image_pixels`
- temporary_processing: internal only / not persisted

同一个持久化 JSON 不应再混用另一套页面坐标。
