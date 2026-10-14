# AppSettings 全仓库参数契约审计（2026-10-15）

> 本文对应 PR #497；基准分支是 #496 `feat/integrated-ocr-runtime-monitor-20261014`。这不是 main 的独立补丁。

## 复现与产物

```sh
python scripts/audit_settings_runtime.py --out build/settings-audit
uv run --locked pytest -q tests/test_settings_runtime_audit_20261015.py tests/test_ink_safe_separator_20261014.py tests/test_separator_y_settings_tab_20261014.py
```

GitHub Actions：`.github/workflows/settings-audit.yml`（所有 Python 包文件 AST 扫描），以及 `.github/workflows/ci.yml`（Linux/Windows/macOS、Python 3.10/3.13、GUI smoke）。

输出目录：

- `appsettings_field_matrix.csv`：每个 `AppSettings` 数据类字段都有默认值表达式、schema 引用、设置中心 UI 位置（若可静态确认）、帮助覆盖、设置中心保存机制、JSON 加载机制、运行时代码静态读取点、持久化测试标识及已建立的特定算法测试标识。
- `hardcoded_threshold_candidates.json`：全部匹配的启发式数值条件及函数默认阈值，包含文件、行、表达式、是否直接提到已有设置字段、待人工复核状态。
- `threshold_triage_summary.json`：待分类候选数和本次已完成迁移的参数名单。
- `summary.json`：完整字段数量、静态 UI/运行读取覆盖等统计与不可推断的事项。

**静态读取点不是执行证据。** `runtime_status=targeted_behavior_test` 仅用于确实有针对性测试验证算法对设置变化作出响应的字段。其余字段即使有静态读取点，也不标记为行为测试已通过。

## 四层核验

1. **默认值**：AST 提取 `AppSettings` 每个 `AnnAssign` 默认值表达式；与 `dataclasses.fields(AppSettings)` 一一核对。
2. **界面**：扫描真实 `SettingsDialog` 使用的组（包含 Profile、插图自定义模块）；没有可证明的设置中心 UI 位置则置空，注明 internal/custom UI 待核对，而非臆造位置。
3. **保存加载**：`SettingsDialog.save()` 的可见字段写入 `parent.settings`；`AppSettings.to_json/from_json` 持久化及迁移。自动化测试对数据类 **全部字段** 做 JSON 默认往返一致性断言。需要进一步排除跨版本迁移的语义差别。
4. **运行读取**：静态 AST 捕获 `.field` 与 `getattr(obj, 'field')`，排除 schema 和模型定义；直接调用算法验证可调阈值是否真正影响计算结果。动态字段名、反射、闭包转发及运行环境参数不能仅凭 AST 宣称覆盖。

## 确认并迁移的算法阈值

已存在实验性、默认关闭的 `separator_y_ink_safe_gap`。保持历史默认数值不变，仅在开启时使用新参数：

| 字段 | 默认 | 位置 | 数值含义 |
| --- | ---: | --- | --- |
| `separator_y_ink_safe_max_fraction` | 0.25 | 设置中心 → 横线 Y 精修 | 白缝搜寻上限，相对于典型行高 |
| `separator_y_ink_safe_ink_threshold` | 185 | 同上 | 灰度低于该值计作墨迹 |
| `separator_y_ink_safe_existing_ink_ratio` | 0.045 | 同上 | 当前横线已足够安全时不移动 |
| `separator_y_ink_safe_gap_ink_ratio` | 0.02 | 同上 | 白缝连续三行逐行的墨迹比例上限 |

以上参数都配置了相应的 UI Spinbox、帮助文案、保存前验证、`AppSettings.__setattr__` 边界保护、JSON 持久化测试及与算法判定差异相关的测试。原功能默认关闭，故标准普通画线/OCR画线结果应保持不变。

## 不应一概挪入设置中心的常量

部分硬编码是基础数组/图像处理的有效性边界，例如 `ink_safe_separator.py` 中二维输入、最小 ROI 宽高及连续三行白缝的要求。这些不是可以依据用户偏好任意改变的分类阈值；变动可能导致越界或不再满足算法定义。

`ordinary_final_visual_consistency.py`、`layout_core_understanding.py`、`ordinary_bracket_pair.py` 中尚存在若干检测阈值。这些影响词条分类、栏修复和 CJK 特定逻辑；**尚未完成逐条真实词典 FN/FP 验证或专家批准前，不因扫描命中就批量改为可编辑**。审计清单保留文件行号，供下一轮按“领域决策参数／数值安全不变量／纯显示参数／兼容值”逐条批准。

## 设置说明滚动

`SettingsDialog._scrollable_settings_page` 现在每个页面均把实时共享的 `_settings_help_body_var` 放在可滚动 Canvas 中。说明自适应折行、长文本可向下滚动、新参数切换重置顶部，并保留图解。跨平台 `scripts/gui_smoke.py` 新增实际 Tk Canvas 构建、长段滚动与 reset 测试；单靠 `wraplength` 不能保证下半部分可见。

## 验收边界

- GitHub Actions pytest / GUI smoke 证明可重复构建和功能级行为；仍非高分辨率扫描多词典 FP/FN 测量。
- 项目 Profile 可能根据语言和字形重写有效参数；应以 **effective settings** 与逐页诊断核对最终执行参数。
- 这次仅把已经确认可安全配置、同时保留历史默认行为的实验白缝阈值移到 UI；余下扫描命中均为待分级证据，不代表功能缺陷数。
- 此 PR 叠加在 #496，后者未合并；合并时应沿用分支依赖关系，不要独立 cherry-pick 覆盖既有设置中心与环境中心变动。
