# 主界面版面参数可视化：开发指令

## 目标

在主界面【二、显示设置】增加【显示版面参数可视化】开关。开启后，直接在当前页面图像上叠加显示该页**实际推理并采用**的 layout 几何，而不是项目默认值或仅日志中的参数。

这个功能是纯显示诊断工具：开关状态不得改变普通画线、OCR画线、融合画线、PDIC/PPP、切图、训练导出或任何检测结果。

## 数据来源

1. 原始扫描图仍负责显示、坐标、PDIC 与最终裁图。
2. layout 推理使用共享的 full-resolution analysis image；该图只做通用孤立噪点清理，不缩放、不裁切、不改变坐标。
3. 若【逐页自动识别版面参数】开启：
   - 使用当前页的 raw layout estimate；
   - 按 `ORDINARY_AUTO_LAYOUT_FIELDS` 与每个字段的开关，生成实际采用的 effective settings；
   - 再由 effective settings 构造最终 geometry。
4. 若逐页自动识别关闭：显示当前 Project/Profile effective geometry，并明确标记为 `project/profile geometry`。

## 主界面 UI

位置：主界面【二、显示设置】区块。

控件：

- `[ ] 显示版面参数可视化`

默认关闭。

Tooltip：

> 在主图上显示当前页实际采用的版面推理：正文上下界、各栏左右边界、栏间中心、推理方法/置信度及自动字段采用情况。仅影响显示。

第一版不增加颜色设置、复杂子开关或导出按钮，避免把显示设置区做得过重。

## 图像 Overlay 必须显示的实体几何

### 1. 正文上下界

- `body_top`
- `body_bottom`

在图上横向画出，并标注实际像素 Y。

### 2. 每栏边界

对每栏显示：

- 左边界 / column path
- 右边界
- 栏编号 `C1`, `C2`, ...
- 当前栏 `x` 与 `width`

若 `follow_column_deformation` 产生曲线/折线路径，必须画真实 path，不能强制画成竖直线。

### 3. 栏间中心

相邻两栏之间显示 gutter 中心虚线，让用户肉眼判断推断的栏距是否落在真实栏间空白中。

### 4. 推理摘要

在主图左上角叠加一个 compact summary，包括：

- AUTO / CURRENT
- method
- confidence
- columns
- start_y
- bottom_y
- manual_x
- column_width
- gutter
- character_height
- row_padding
- auto applied fields
- raw-only fields（检测器算出了值，但对应字段自动开关关闭，因此没有实际采用）

## 推理与显示的关系

可视化必须区分两个概念：

1. **raw estimate**：layout detector 对当前页推理出来的值；
2. **used/effective geometry**：按项目自动字段开关筛选后，真正进入 ordinary detection 的值。

图上的几何线以 **used/effective geometry** 为准；摘要可同时提示哪些 raw 字段被采用、哪些仅计算但未采用。

## 坐标约束

- overlay 使用 source image X/Y。
- analysis image 与 source image 必须同宽同高。
- transformed/canonical geometry 必须经 `geometry.canonical_to_source()` 后再绘制。
- `view_scale` 只用于 Canvas 显示缩放，不能反写任何检测坐标。

## 性能约束

layout detector 可能较重，因此：

- 当前页 snapshot 必须缓存；
- 普通 redraw/zoom 只能复用 snapshot；
- 页面切换、layout settings 改动、auto-layout field switch 改动时才失效重算；
- overlay 关闭时不得主动运行 layout detector。

## 失败策略

这是 diagnostic-only 功能。若 layout visualization 自身异常：

- 不得阻止主界面 redraw；
- 不得阻止普通/OCR/融合检测；
- 只在 Canvas 上显示简短 `Layout visualization unavailable` 提示。

## 不允许的实现

- 不允许把 overlay 直接烧进原始图片。
- 不允许为了显示而修改 `settings.start_y/manual_x/...`。
- 不允许因为开关打开而改变 entry 数量或画线 Y。
- 不允许只画项目默认参数而声称是推理结果。
- 不允许普通画线使用一套去噪图、layout visualization 再使用另一套图。
- 不允许 redraw 每次都重新跑 Paddle layout detection。

## 第一版验收标准

1. 主界面【二、显示设置】出现【显示版面参数可视化】。
2. 默认关闭，关闭时 UI/检测行为与旧版一致。
3. 开启后可看到正文上下界、每栏左右边界/路径、栏间中心线和参数摘要。
4. auto layout 开启时，摘要显示 detector method/confidence 与 auto-applied fields。
5. 关闭某一个 auto field 后，该字段仍可作为 raw estimate 出现在摘要，但图上采用项目/Profile 的 effective 值。
6. 页面缩放后 overlay 与原图保持严格对齐。
7. 页面切换后 overlay 更新为新页参数。
8. 开关前后 PDIC、entry 坐标、OCR cache、crop 输出均不发生变化。
