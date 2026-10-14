# 画线推理性能策略（阶段一）

适用：普通画线调用的 Layout TextDetection、OCR 画线使用的 PaddleOCR 主识别，以及共用 OCR 通道的其他消费者。

本阶段统一了两个模型构造器的机器级配置。**尚未开放多进程批量页面调度 UI**：历史六进程保护保留，避免重复 GPU 模型占满显存。下一阶段需要在实机基准测试后接入 CPU 专用有界 worker pool。

## 机器级设置

在用户配置目录的 `runtime.json` 中，可使用以下字段（不随项目文件跨电脑迁移）：

| 字段 | 取值 | 默认 |
| --- | --- | --- |
| `paddle_device` | `auto` / `cpu` / `gpu` | `auto` |
| `paddle_mkldnn` | `auto` / `on` / `off` | `auto` |
| `paddle_cpu_workers` | `auto` / `2` / `4` / `6` | `auto` |
| `paddle_cpu_threads` | 正整数 | 自动按核心数、worker 计算 |

对应环境变量优先：`PICTURE_CAPTURE_PADDLE_DEVICE`、`PICTURE_CAPTURE_PADDLE_MKLDNN`、`PICTURE_CAPTURE_PADDLE_CPU_WORKERS`、`PICTURE_CAPTURE_PADDLE_CPU_THREADS`。

`paddle_cpu_workers` **目前仅生成调度配置，不改变画线实际 worker 数**。正式接入调度器前，UI 不应显示为已生效并行。

oneDNN（MKL-DNN）仅适用于 CPU：`auto` 首先尝试开启；构造失败则尝试关闭（不保证推理阶段不出错，需真实页面验证）。`on` 维持明确请求而不自动降级；`off` 关闭。CPU 线程上限受机器核心数约束。

## 后续验收条件

- Windows 纯 CPU：普通画线和 OCR 画线分别测 1/2/4/6 workers、峰值内存、稳定性和每页耗时；
- Windows NVIDIA GPU：同一时间只允许一个 GPU 推理实例，CPU 处理流水线限流；
- 启动兼容性测试与真实 `predict()` 测试分别记录；需要 GPU 初始化/推理失败自动回退 CPU；
- 按页保留暂停、停止、失败记录、结果写入原子性、PDIC 保护；
- 双模式的检测与词头坐标结果和旧版本对照，不允许性能优化静默改变识别结果。
