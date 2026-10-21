# Issue #562 — 根目录剩余 43 个模块逐文件所有权/历史兼容性审计

> 审计固定基线 main `020b8a81e9bb2e64c5e604b58c860cd10535b01a`，2026-10-22；891 条非截断 Git tree，`src/picture_capture/*.py` 精确 43 个（含 `__init__.py` 和 `__main__.py`）。逐一读取 43 个源文件并对照 bootstrap、pyproject、architecture_guard 与专项测试。main CI #39645635340 六作业通过，push CodeQL #39645635860 两作业通过，审计开始时无 open PR。

## 分类原则

- **K（保留根级契约）**：当前根模块路径对外可见，或被 root-retention 测试、pickle/猴补丁、入口、数据单写者/GPU/spawn 约束保护。不等于永远禁止对内部实现做进一步提取。
- **D（条件性迁移）**：领域归属明确，但需要先证明 ABI/导入、性能、事务和旧格式不变；**目前不能直接搬迁**。
- **P（候选）**：可设计一个小的真实物理迁移 PR，但必须先排除循环导入、修改全部静态/动态消费者，并通过完整门禁。
- 本报告是源码+现有 CI 的静态审计，不是全量运行时调用图，更不代表真实扫描页、原生 CUDA、Win/macOS GUI 人工验收。

分类合计：K 31，D 11，P 1；**43/43 全部覆盖**。

## 逐模块清单

| 当前类别 | 根模块 | 判定 | 职责、保留原因或下一条件 |
|---|---|---|---|
| 入口 | `__init__.py` | **K** | 版本及无副作用包 import |
| 入口 | `__main__.py` | **K** | python -m / multiprocessing.freeze_support |
| 入口 | `app.py` | **K** | Tk 主入口、页面锁、队列、GUI callback、人工校正 |
| 入口 | `cli.py` | **K** | CLI 入口；先 build_core_services 再绑定 I/O |
| 入口 | `picdic.py` | **K** | 旧 PicDic 包装与 DSL/ZIP 原子发布 |
| 入口 | `launcher.py` | **K** | 历史 launcher.main 和 prepare_app_module facade |
| 入口 | `gui_io.py` | **K** | 延迟 PDIC I/O；不可绕过分类 sidecar/bootstrap |
| 入口 | `processing.py` | **K** | 普通/融合检测 facade 与属性赋值镜像 |
| 入口 | `processing_core.py` | **K** | 老几何、裁剪、PDIC/PPP 内核，保留模块 API |
| 入口 | `facade_compat.py` | **K** | sys.modules+ModuleType monkeypatch 兼容 |
| 入口 | `models.py` | **K** | Entry X/Y、AppSettings/ProjectState、JSON schema |
| 持久化 | `formats.py` | **K** | PDIC/PPP 编码/字段/行序及原子替换 |
| 持久化 | `project_storage.py` | **K** | managed-v2/legacy 路由及用户扫描所有权 |
| 持久化 | `page_sections.py` | **K** | SECTION v2 原图线段、空记录覆盖旧 sidecar |
| 持久化 | `pdic_restore.py` | **K** | 人工合并/恢复、整页原子写和 page token |
| 持久化 | `processing_publish.py` | **D** | 多文件裁切 journal/rollback; 暂缓 project/transaction 迁移 |
| 持久化 | `entry_classification.py` | **D** | weakref+LRU、手工 override 和 formats I/O 装饰 |
| 历史 UI | `layout_visualization_ui_v3.py` | **K** | 现有测试强制保留的 Layout UI/diagnostic 旧入口 |
| 历史 UI | `settings_help_restore.py` | **K** | 历史 no-op installer import 兼容 |
| 历史 UI | `ui_terminology.py` | **K** | 文本迁移兼容 API，禁止恢复 Tk monkeypatch |
| Layout | `layout_core_understanding.py` | **D** | 物理/语义角色缓存和展示-普通画线同一理解 |
| Layout | `layout_detection.py` | **K** | 历史 TextDetection monkeypatch 注入 facade |
| Layout | `layout_detection_legacy.py` | **D** | TextDetection 模型 cache、CPU worker GPU guard |
| Layout | `layout_detector_live_binding.py` | **K** | 历史可 import 的 no-op installer |
| Layout | `layout_physical_indent.py` | **K** | 源像素 X 投影/缩进，static installer；root 测试 |
| Layout | `layout_rows_cache.py` | **K** | 物理行 JSON/cache/ContextVar；root 测试 |
| OCR/运行时 | `ocr_channel.py` | **K** | OCR 选择策略与 Paddle 缓存/锁/session |
| OCR/运行时 | `ocr_channel_legacy.py` | **D** | 对旧 core runner 的线程安全临时注入及恢复 |
| OCR/运行时 | `ocr_page_resume.py` | **K** | __file__.parent 全包指纹，远程 Lens fail-closed |
| OCR/运行时 | `paddle_headwords.py` | **K** | 历史 OCR public facade/插件 monkeypatch |
| OCR/运行时 | `paddle_headwords_core.py` | **K** | OCR legacy core / pickle __module__ 身份 |
| OCR/运行时 | `windows_gpu.py` | **K** | Windows cuDNN DLL 搜索目录及 handle 生命周期 |
| OCR/运行时 | `runtime_environment.py` | **K** | 机器环境/设备分配/跨 OS 路径 fallback |
| Y/精修 | `separator_y_refinement.py` | **K** | 只对已有分隔线做小范围安全 Y 微调 |
| Y/精修 | `marker_refinement_parallel.py` | **K** | spawn worker 只读 + 父协调者 PDIC CAS 提交 |
| 图像 | `image_preprocessing.py` | **D** | 150k 公开预处理 facade，test 强制留根 |
| 图像 | `image_utils.py` | **D** | 统一 EXIF/透明白底 RGB/原分辨率 analysis；test 留根 |
| 证据 | `evidence_fusion.py` | **D** | OCR core/动态导出/pyproject Ruff F821 特例 |
| 证据 | `symbol_evidence.py` | **P** | 可考虑转 layout/symbol_evidence，需检验循环导入和 source Y |
| 导出 | `single_line_parallel.py` | **D** | spawn pickle 顶级 job 和父进程共享日志单写者 |
| 导出 | `unlined_line_export.py` | **D** | Layout 物理行 - PDIC 已画行；spawn job / 权限 |
| 训练 | `training_export.py` | **D** | 旧训练导出根入口、manifest/ZIP 取消后原子提交 |
| 训练 | `training_export_ui.py` | **K** | 旧 export UI 兼容 API，测试明确要求根文件 |

## A. Layout、原始坐标、读向、Y 契约

- `Entry` 与项目 settings 中保存的 X/Y 是**原始扫描图像像素坐标**，临时 `layout_transform`、列/阅读方向转换不可把保存值偷偷变成 canonical 像素。`layout_detection.py` 把 `_get_text_detector` 作为 monkeypatch 入口；直接导出 legacy 方法会令此注入点失效。
- `layout_core_understanding.py` 共用显示/普通画线缓存与角色；`layout_physical_indent.py` 从物理 `first_x` 投影推断缩进；`layout_rows_cache.py` 只持久化**物理行**，不保存 entry/body 等语义。`separator_y_refinement.py` 不许新增、删除、接受或拒绝 entry，只能微调既有分隔线 Y。
- `page_sections.py` 的 SECTION v2 落盘为**原图坐标的水平段线**；历史 migrated QT SECTION 存在时空 SECTION 必须有显式新记录，不能仅删除文件导致旧边界复活。
- 现存门禁：`test_layout_followup_ownership_20261021.py` 要求 `layout_core_understanding`, `layout_physical_indent`, `layout_rows_cache`, `layout_detector_live_binding` 在根；`test_ui_physical_ownership_20261021.py` 要求 v3 可视化入口在根；`test_page_utility_ownership_20261021.py` 保护 `layout_rows_cache`。

## B. 图像源与像素保真

- `image_utils.normalize_page_rgb` 做 EXIF 定向、含 alpha 图像白底合成，并复制不透明 RGB；`build_analysis_image` 的去噪保持原分辨率/坐标、输出统一分析图，实验性的复用默认不启用。不同算法不能各自另选去噪像素。
- `image_preprocessing.py` 仍是外部预处理 facade，`geometry_corrected_image` 使用缓存的 deskew/perspective/UVDoc/orthogonal 变换，不应再次运行 Paddle；整文件搬迁风险高。`test_preprocess_ownership_20261020.py` **明确保护 `image_preprocessing.py` 与 `image_utils.py` 两个根入口**。
- 如果拆纯图像实现叶子：必须验证有/无 EXIF 旋转、透明 PNG、源坐标 Y、RTL/LTR、分栏、大图内存、去噪前后 PDIC 坐标、手动几何微调。此轮只审查源码，没有真实扫描像素哈希一致性证据。

## C. Windows spawn、GPU 模型单 owner

- `__main__.py` 保留 `multiprocessing.freeze_support()`；`cli.py` 在绑定 `formats` / `processing` callable 前主动 `build_core_services()`；`bootstrap/worker.py` 的 `build_worker_services()` 每个 spawn 进程独立、幂等组合。
- `marker_refinement_parallel.refine_page_job` 是只读 child job；`commit_refined_page_result()` 只由父协调者调用，校验页面 owner、PDIC 词/坐标及 PPP/SECTION/Profile/相关伴随文件指纹后再原子写 PDIC。`single_line_parallel`、`unlined_line_export` 的顶级 spawn job 路径若迁移，必须用 Windows spawn 测试 pickle/取消、共享日志和编辑权限。
- `layout_detection_legacy`、`ocr_channel`、`paddle_headwords_core` 分别存在 TextDetection、channel Paddle、legacy OCR 缓存，使用锁/资源策略不等于已证明原生 GPU 全进程单模型。`ordinary/gpu_pipeline.py` 的 CPU worker guard 不得解除。
- `windows_gpu` 在 import Paddle 之前将 NVIDIA/cuDNN bin 目录加入 DLL search path，`_DLL_DIR_HANDLES` 保活。需在真实 Windows x64/CUDA 上实测模型构造次数、显存、spawn 子进程及无 GPU fallback。
- 已有 `test_worker_bootstrap.py`, `test_spawn_layout_runtime.py`, `test_ordinary_single_gpu_pipeline_20261014.py`, `test_pdic_editable_batch_permissions_20261017.py`, `test_runtime_portability.py`，主要含合成/隔离测试；不能用其代替原生硬件实测。

## D. PDIC/PPP/SECTION/Profile、人工编辑和 crash recovery

- `formats` 确保 PDIC/PPP 列、换行和原子文本写；`gui_io` 避免在 `bootstrap.core.install_pdic_classification()` 之前提前捕获原始函数，保障 JSON sidecar 和训练 baseline 的原有行为。`entry_classification` 使用 weakref+512 LRU，人工 override 由 sidecar 保留，禁止按复用 id 污染。
- `project_storage` 区分用户扫描与软件 `'_PictureCapture'` 的 legacy/v2；`ProjectState.open` 不应在无明确迁移动作时移动用户数据。`processing_publish` 使用 pending/committed journal、backup 和项目路径边界执行崩溃恢复。
- **待证风险 1（不是已证 bug）：** `AppSettings.to_json()` 当前直接 `path.write_text(...)`；与 `formats.write_text_atomic` 或 `runtime_environment.save_runtime_setting` 不同。需要故障注入检查中途退出是否损坏旧 settings，单独 PR 修复，不与模块移动混合。
- **待证风险 2：** `page_sections.write_page_sections()` 固定写 `<target>.tmp` 再 replace；未来若两个写者碰到同页可能临时文件竞争。先审清父线程独占授权，再测试并发、唯一临时名和空 SECTION 覆盖旧 sidecar。
- **待证风险 3：** `windows_gpu.configure_windows_nvidia_dlls()` 重复调用会保留多次 handle；需真实 Win DLL 资源测试才能定性是否有风险。不要靠 Linux mock 宣称泄漏。
- `ocr_page_resume._algorithm_environment_key()` 明确使用 `Path(__file__).resolve().parent.rglob('*.py')` 哈希整个包源码，并校验工具版本、最终 PDIC 字节；若将模块不加修改地迁入 `ocr/`，会漏掉 layout/refinement 等文件而错误命中 OCR 缓存。使用 Lens 时禁用安全 resume。

## E. 审计后行动优先级

1. **下一单一候选 P：** `symbol_evidence.py` → `layout/symbol_evidence.py`，待验证无循环依赖、同步所有源码/测试/脚本及 import-string，严格比较 sampled entry marker 与 bracket 的不同授权（bracket 只确认，不独立救援）、profile、读向、源 Y、跨栏、重复过滤、人工编辑；不得保留旧根 shim。
2. **先测再拆叶：** `entry_classification` registry/persistence 与 `processing_publish` crash journal；根级 facade 暂留。`image_preprocessing`、`evidence_fusion`、`layout_core_understanding` 优先抽内部叶子，不整文件硬搬。
3. **目前冻结：** root public entry、`layout_detection` monkeypatch、`layout_rows_cache`、Y-refinement、`ocr_page_resume`、`paddle_headwords_core` pickle、Windows GPU、spawn/job 与 PDIC 单写者。
4. **可靠性整改独立于迁移：** settings JSON 写入异常中断、SECTION 固定 tmp 竞争、Windows DLL handle 幂等性，分别增故障注入/原生测试后再讨论更改。
5. **合并准入：** 精确 base/head、单一无冲突 Draft PR、完整 AST+懒导入/CLI/GUI、Python3.10/3.13 × Win/macOS/Ubuntu 全绿、wheel、arch guard 只收紧、CodeQL、review 与 postmerge main CI。用户真实扫描页/原生 GPU/人审 parity 未验证前不得关闭 Issue #562。

**说明：** 253→43 的 210 文件下降（83.0%）是“物理根文件减少”，**不是 83% 的安全迁移完成**，也不意味着这 43 个应最终全部消失。
