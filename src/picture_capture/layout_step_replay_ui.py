"""Modeless, opt-in playback of production Layout intermediate decisions.

Only the current page is inspected. Raster data is NOT stored per step: one
normal source preview and (for the denoise step only) one small cleaned preview
are used with lightweight canvas geometry and provenance overlays.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import copy
import os
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from .layout_step_trace import LayoutStepTrace


_ROLE_COLORS = {
    "entry": "#d83b3b",
    "headword": "#d83b3b",
    "body": "#2773c6",
    "unknown": "#777777",
}
_STEP_TAG = "layout-replay-overlay"


from .layout_mask_source_guard import saved_illustration_stamp as _saved_illustration_stamp


def _app_key(app: Any) -> tuple[Any, ...]:
    from .adaptive_denoise import DENOISE_ENV
    return (
        id(getattr(app, "image", None)),
        int(getattr(app, "current_index", -1)),
        repr(getattr(app, "settings", None)),
        repr(getattr(app, "page_sections", ())),
        _saved_illustration_stamp(getattr(app, "current_page", None), getattr(app, "settings", None)),
        os.environ.get(DENOISE_ENV, "auto"),
    )


def _run_replay(
    source: Image.Image, settings: Any, page_index: int,
    page_sections: list[Any] | None = None,
    source_image_path: Path | None = None,
) -> tuple[LayoutStepTrace, dict[str, Image.Image]]:
    """Run the *actual* ordinary-drawing facade, not a reduced Layout imitation.

    The same call records shared preprocessing, optional mask, Layout Core,
    【】 recovery and final candidate filtering. It never publishes a PDIC.
    """
    from .processing import detect_entries

    # The normal 普通画线 button overrides the method for its worker. Replay
    # must do the same on a *copy*, regardless of the GUI's OCR selection.
    # Never silently run the OCR/combined pipeline and call it Layout replay.
    ordinary_settings = copy.deepcopy(settings)
    ordinary_settings.detection_method = "left_edge"

    trace = LayoutStepTrace()
    previews: dict[str, Image.Image] = {}

    def capture(key: str, image: Image.Image) -> None:
        preview = image.copy()
        try:
            preview.thumbnail((1400, 1800), Image.Resampling.LANCZOS)
            prior = previews.pop(key, None)
            if prior is not None:
                prior.close()
            previews[key] = preview
        except BaseException:
            preview.close()
            raise

    try:
        pipeline: dict[str, Any] = {
            "_layout_replay_trace": trace,
            "_layout_replay_preview": capture,
        }
        # Uses the same effective settings, sections, actual entry algorithms
        # and stage records as the 普通画线 button, once per requested page.
        detect_entries(
            source, ordinary_settings, profile_page_index=int(page_index),
            page_sections=page_sections, debug_trace=pipeline,
            # A visual replay is READ-ONLY: auto-detected candidates must not
            # write PPP. Only explicit reuse mode needs a path to read PPP.
            source_image_path=(source_image_path if bool(getattr(
                ordinary_settings, "layout_mask_illustrations_use_existing", False
            )) else None),
        )
        if not trace.stages:
            raise RuntimeError("普通画线未提供任何可回放阶段")
        return trace, previews
    except BaseException:
        for preview in previews.values():
            preview.close()
        raise


def _preview_at_stage(
    stages: list[dict[str, Any]], index: int, previous: bool,
    previews: dict[str, Image.Image], original: Image.Image,
) -> Image.Image:
    """Use the *latest actual* preprocessed raster, not the raw scan after mask.

    The before toggle at masking previews the analysis input; the first stage
    toggles between original and cleaned raster.
    """
    target = max(-1, index - int(previous))
    for position in range(target, -1, -1):
        candidate = previews.get(stages[position]["key"])
        if candidate is not None:
            return candidate
    return original


def _stage_entries_for_display(
    stages: list[dict[str, Any]], index: int, previous: bool,
) -> list[dict[str, Any]]:
    """Return the last recorded production marker list at/before this stage."""
    target = index - int(previous)
    for position in range(target, -1, -1):
        stage = stages[position]
        if "entries" in stage:
            return stage["entries"]
    return []


_PROJECTION_STAGES = {"projection_gap_bridge", "projection_tall_split"}


def _projection_candidates_for_display(
    stage: dict[str, Any], before: bool,
) -> list[dict[str, Any]]:
    """Before/after always compares the *same* captured projector pass."""
    kind = stage.get("key")
    candidates = stage.get("candidates", [])
    if kind == "projection_gap_bridge":
        statuses = {"raw_band"} if before else {"connected_band", "bridged_gap"}
    elif kind == "projection_tall_split":
        statuses = {"connected_band"} if before else {
            "retained_row", "split_valley", "fallback_slot", "ignored_short",
        }
    else:
        return candidates
    return [item for item in candidates if item.get("status") in statuses]


_PROJECTION_STYLE = {
    "raw_band": ("#999999", (5, 3), 1),
    "connected_band": ("#3785cb", (5, 3), 1),
    "bridged_gap": ("#ef8823", (), 3),
    "retained_row": ("#10a55b", (), 2),
    "split_valley": ("#ae44bd", (), 3),
    "fallback_slot": ("#d8a322", (3, 3), 2),
    "ignored_short": ("#a0a0a0", (2, 4), 1),
}


def _stage_rows_for_display(
    stages: list[dict[str, Any]], index: int, previous: bool,
) -> dict[str, Any]:
    """A before/after toggle uses *recorded* earlier state, never re-inference."""
    target = index - 1 if previous else index
    for i in range(target, -1, -1):
        if stages[i]["rows"] or stages[i]["columns"]:
            return stages[i]
    return stages[index]


def _row_at_position(rows: list[dict[str, Any]], x: int, y: int) -> dict[str, Any] | None:
    """Nearest physical row on an overlay click, in source-image coordinates."""
    matches = []
    for row in rows:
        x0, y0, x1, y1 = row["source_box"]
        if min(x0, x1) - 10 <= x <= max(x0, x1) + 10 and min(y0, y1) - 6 <= y <= max(y0, y1) + 6:
            matches.append((abs(y - (y0 + y1) / 2), row))
    return min(matches, key=lambda item: item[0])[1] if matches else None


def _candidate_at_source(
    candidates: list[dict[str, Any]], x: int, y: int, *,
    tolerance: int = 6,
) -> dict[str, Any] | None:
    """Hit-test smallest true candidate first, even inside its parent band.

    A 1px valley/gap is contained by a large connected ink band. Selecting
    the first containing box would make the actual bridge/split unclickable.
    """
    matches: list[tuple[float, dict[str, Any]]] = []
    for item in candidates:
        box = item.get("source_box")
        if box and len(box) == 4:
            x0, y0, x1, y1 = (float(v) for v in box)
            left, right = sorted((x0, x1))
            top, bottom = sorted((y0, y1))
            # Narrow gap/split lines need hit tolerance at preview zoom, but
            # regular row bands should not swallow clicks on adjacent rows.
            narrow = bottom - top <= 3
            margin = tolerance if narrow else 0
            if left - margin <= x <= right + margin and top - margin <= y <= bottom + margin:
                area = max(1.0, right-left) * max(1.0, bottom-top)
                distance = max(0, top-y, y-bottom)
                matches.append((area + distance, item))
            continue
        polygon = item.get("source_polygon")
        if polygon and len(polygon) >= 3:
            pxs = [float(p[0]) for p in polygon]
            pys = [float(p[1]) for p in polygon]
            if min(pxs) <= x <= max(pxs) and min(pys) <= y <= max(pys):
                matches.append(((max(pxs)-min(pxs))*(max(pys)-min(pys)), item))
            continue
        anchor = item.get("source_anchor")
        if anchor and len(anchor) == 2:
            dx, dy = float(anchor[0])-x, float(anchor[1])-y
            if abs(dx) <= tolerance and abs(dy) <= tolerance:
                matches.append((dx*dx + dy*dy, item))
    return min(matches, key=lambda record: record[0])[1] if matches else None


def _format_stage(
    stage: dict[str, Any], *,
    selected: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
    selected_candidate: dict[str, Any] | None = None,
    selected_marker: dict[str, Any] | None = None,
    marker_history: list[dict[str, str]] | None = None,
) -> str:
    lines = [stage["title"], "", stage["description"], ""]
    details = stage.get("details", {})
    if stage.get("key") in _PROJECTION_STAGES:
        lines.append("显示的是最终正文范围内、真正用于构造物理行的一次投影。")
        lines.append("注意：投影连接的是行方向的短空白，不修改像素或连通域。")
        lines.append("切换「查看修正前」可比较本阶段真实的输入和输出。")
        columns = details.get("columns", [])
        for column in columns:
            lines.extend([
                "",
                f"第 {column['column']} 栏｜设置采样 {column['requested_width_percent']:.1f}% 栏宽，"
                f"实际采样宽 {column['sample_strip_width']}px"
                f" / {column['configured_column_width']}px"
                f"（{column['effective_width_percent']:.1f}%），"
                f"参考行高 {column['row_height_reference']:.1f}px",
                f"阈值 {column['projection_threshold']:.1f} 墨迹像素/行；"
                f"最多连接 {column['gap_limit_px']} 个空白像素行",
                f"原始带 {column['raw_bands']} → 已连带 {column['connected_bands']}；"
                f"连接 {column['bridged_gaps']} 处",
                f"墨迹谷拆分 {column['valley_splits']} 处，"
                f"逻辑槽 {column['logical_slots']} 个，"
                f"过短剔除 {column['short_rejected']} 个，"
                f"输出行段 {column['output_rows']} 个",
            ])
        return "\n".join(lines)
    for k, value in details.items():
        if isinstance(value, dict):
            lines.append(k + ":")
            for item, v in value.items():
                lines.append(f"  {item}: {v}")
        else:
            lines.append(f"{k}: {value}")
    lanes = stage.get("lanes", ())
    provisional_no_indent = bool(stage.get("provisional_no_indent", False))
    if lanes:
        lines.append(
            f"物理行首位置聚类：{len(lanes)} 组（非词条类别）"
            if provisional_no_indent else f"缩进群：{len(lanes)}"
        )
        for lane in lanes:
            lines.append(
                f"  {lane['id']}：中心 {lane['center']:.1f}px，"
                f"容差 ±{lane['tolerance']:.1f}px，"
                f"支持 {lane['support']} 行，"
                + ("语义 未分类" if provisional_no_indent
                   else f"角色 {lane['role']}")
            )
        if provisional_no_indent:
            singleton = sum(int(lane["support"]) == 1 for lane in lanes)
            lines.extend([
                "",
                "【无明显缩进】不允许以行首 X 差异推断词条。",
                "历史底层实现会暂时给某些行标记 entry，"
                "但此阶段尚未应用 Profile；这些标签不是有效词头。",
                f"单行离群位置：{singleton} 组；可能来自异常行、插图或大字形，"
                "不能仅凭该聚类认定词头。",
            ])
    rows = stage["rows"]
    if rows:
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["role"]] = counts.get(row["role"], 0) + 1
        lines.extend(["", f"本阶段物理行：{len(rows)}",
                      ("语义状态（尚未分类）：" if provisional_no_indent else "行角色：") + "、".join(
            f"{k} {v}" for k, v in sorted(counts.items())
        )])
    if "entries" in stage:
        markers = stage["entries"]
        marker_changes = stage.get("entry_changes", [])
        lines.extend(["", f"当前真实普通画线候选：{len(markers)}",
                      f"相对上一画线阶段的变化：{len(marker_changes)}"])
        for item in marker_changes[:100]:
            before = item.get("before") or {}
            after = item.get("after") or {}
            lines.append(
                f"  ({item['x']}, {item['y']}): {item['kind']} "
                f"{before.get('source', '—')} → {after.get('source', '—')}"
            )
        if len(marker_changes) > 100:
            lines.append(f"  ……其余 {len(marker_changes)-100} 项")
    if selected_marker is not None:
        lines.extend(["", "点击自动画线候选：",
                      f"坐标：({selected_marker['x']}, {selected_marker['y']})",
                      f"来源：{selected_marker.get('source', 'unknown')}"])
        for item in marker_history or []:
            lines.append(f"  {item['stage']} → {item['role']}")
    changes = stage.get("changes", [])
    if changes:
        lines.extend(["", f"相对上一个行状态的变化：{len(changes)}"])
        for c in changes[:100]:
            before = c["before"] if c["before"] is not None else "—"
            after = c["after"] if c["after"] is not None else "—"
            lines.append(f"  {c['id']}: {before} → {after} ({c['kind']})")
        if len(changes) > 100:
            lines.append(f"  ……其余 {len(changes)-100} 行可在图中查看")
    if selected_candidate is not None:
        lines.extend(["", "点击视觉候选详情："])
        for key, value in selected_candidate.items():
            lines.append(f"  {key}: {value}")
    if selected is not None:
        lines.extend([
            "", "点击行详情：", selected["id"],
            "最终在这一阶段显示的角色：" + selected["role"],
            "原图位置：" + str(selected["source_box"]),
            "物理行 Y：" + str(selected["canonical_y"]),
            "检测到的 first_x：" + str(selected["first_x"]),
        ])
    if history:
        lines.append("该行的完整角色变化：")
        for item in history:
            lines.append(f"  {item['stage']} → {item['role']}")
            lines.append("    依据：" + item["reason"])
    lines.extend([
        "", "时间轴包含 Layout Core 与实际普通画线的候选处理阶段。",
        "候选位置的空间邻近关系不能单独证明因果；"
        "最终显示的坐标来自普通画线真实阶段记录。",
        "仅用于诊断，不写入 PDIC/PPP。",
    ])
    return "\n".join(lines)


class LayoutStepReplayWindow:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.closed = False
        self.generation = 0
        self._pending = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="layout-replay")
        self._snapshot_key: tuple[Any, ...] | None = None
        self._source: Image.Image | None = None
        self._previews: dict[str, Image.Image] = {}
        self._photo: ImageTk.PhotoImage | None = None
        self._photo_key: tuple[Any, ...] | None = None
        self._trace: LayoutStepTrace | None = None
        self._stage_index = 0
        self._scale = 1.0
        self._size = (0, 0)
        self._watch_job: str | None = None

        master = getattr(app, "root", None) or app
        self.window = tk.Toplevel(master)
        self.window.title("LAYOUT 分析过程回放（只读）")
        self.window.geometry("1210x810")
        self.window.minsize(750, 500)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        root = ttk.Frame(self.window, padding=8)
        root.pack(fill="both", expand=True)
        toolbar = ttk.Frame(root)
        toolbar.pack(fill="x", pady=(0, 7))
        ttk.Label(toolbar, text="LAYOUT 分析过程").pack(side="left", padx=(0, 9))
        self.previous_button = ttk.Button(toolbar, text="◀ 上一步", command=lambda: self.step(-1))
        self.previous_button.pack(side="left")
        self.step_var = tk.StringVar()
        # Tk's default popdown is only ~10 rows; when the final stage is
        # selected the pre-physical projector stages are scrolled out of view.
        self.step_combo = ttk.Combobox(
            toolbar, textvariable=self.step_var, state="readonly",
            width=37, height=28,
        )
        self.step_combo.pack(side="left", padx=5)
        self.step_combo.bind("<<ComboboxSelected>>", self.select_step)
        self.next_button = ttk.Button(toolbar, text="下一步 ▶", command=lambda: self.step(1))
        self.next_button.pack(side="left")
        self.before = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="查看修正前", variable=self.before,
                        command=self.render).pack(side="left", padx=12)
        ttk.Button(toolbar, text="－", width=3, command=lambda: self.zoom(0.8)).pack(side="left")
        ttk.Button(toolbar, text="＋", width=3, command=lambda: self.zoom(1.25)).pack(side="left")
        ttk.Button(toolbar, text="适应宽度", command=self.fit).pack(side="left", padx=3)
        ttk.Button(toolbar, text="运行版本／阶段清单",
                   command=self.show_runtime_diagnostics).pack(side="right", padx=3)
        ttk.Button(toolbar, text="刷新", command=lambda: self.refresh(force=True)).pack(side="right")

        self.status = tk.StringVar(value="正在准备当前页……")
        ttk.Label(root, textvariable=self.status).pack(fill="x", pady=(0, 5))
        body = ttk.PanedWindow(root, orient="horizontal")
        body.pack(fill="both", expand=True)
        image_frame = ttk.Frame(body)
        body.add(image_frame, weight=4)
        info_frame = ttk.Frame(body)
        body.add(info_frame, weight=2)
        self.canvas = tk.Canvas(image_frame, background="#333333", highlightthickness=0)
        vbar = ttk.Scrollbar(image_frame, orient="vertical", command=self.canvas.yview)
        hbar = ttk.Scrollbar(image_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        image_frame.grid_columnconfigure(0, weight=1)
        image_frame.grid_rowconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self.inspect_row)
        self.details = tk.Text(info_frame, wrap="word", font=("TkDefaultFont", 10))
        details_scroll = ttk.Scrollbar(info_frame, orient="vertical", command=self.details.yview)
        self.details.configure(yscrollcommand=details_scroll.set)
        self.details.pack(side="left", fill="both", expand=True)
        details_scroll.pack(side="right", fill="y")
        self.details.configure(state="disabled")
        self.refresh(force=True)
        self._watch_job = self.window.after(550, self.watch_page)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.generation += 1
        if self._watch_job is not None:
            try:
                self.window.after_cancel(self._watch_job)
            except tk.TclError:
                pass
        if self._pending is not None:
            self._pending.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._photo = None
        for preview in self._previews.values():
            preview.close()
        self._previews.clear()
        self._source = None
        self.app._layout_step_replay_window = None
        flag = getattr(self.app, "_layout_step_replay_var", None)
        if flag is not None:
            flag.set(False)
        try:
            self.window.destroy()
        except tk.TclError:
            pass

    def watch_page(self) -> None:
        if self.closed:
            return
        try:
            if self._snapshot_key != _app_key(self.app):
                self.refresh(force=True)
            self._watch_job = self.window.after(550, self.watch_page)
        except tk.TclError:
            self.close()

    def show_runtime_diagnostics(self) -> None:
        """Show the *executing* module paths and every collected stage.

        Downloading a branch ZIP does not switch an older desktop shortcut or
        a different installed source tree. Report resolved imports instead of
        assuming the downloaded files are the ones currently running.
        """
        from . import layout_composition, dictionary_page_layout_policy
        from . import layout_physical_indent
        modules = [
            ("回放窗口", __file__),
            ("阶段采集器", __import__(
                "picture_capture.layout_step_trace",
                fromlist=["__file__"],
            ).__file__),
            ("Layout 组装", layout_composition.__file__),
            ("真实投影", layout_physical_indent.__file__),
            ("逐栏 Page Design", dictionary_page_layout_policy.__file__),
        ]
        lines = [
            "LAYOUT 回放运行版本／全部阶段",
            "",
            "功能标识：#469 真实投影连接与过高墨迹带拆分",
            "以下均为当前进程实际加载的模块路径，不是下载目录推测。",
            "",
        ]
        for label, file_path in modules:
            lines.append(f"{label}：{Path(file_path).resolve()}")
        lines.append("")
        if self._trace is None:
            lines.append("状态：尚未生成当前页阶段记录，可能仍在计算或已失败。")
        else:
            keys = [stage["key"] for stage in self._trace.stages]
            lines.append(f"当前完整阶段总数：{len(keys)}")
            lines.append("所需阶段：" + "、".join(
                f"{key}={'已记录' if key in keys else '缺失'}"
                for key in ("projection_gap_bridge", "projection_tall_split", "physical_rows")
            ))
            for i, stage in enumerate(self._trace.stages, 1):
                lines.append(f"  {i:02d}  {stage['title']} [{stage['key']}]")
            if "physical_rows" in keys and not (
                "projection_gap_bridge" in keys and "projection_tall_split" in keys
            ):
                lines.extend([
                    "",
                    "异常：存在物理行阶段但缺少投影阶段。"
                    "请核对上面的实际加载路径并刷新回放。",
                ])
        self._show_text("\n".join(lines))

    def refresh(self, *, force: bool = False) -> None:
        if self.closed:
            return
        source = getattr(self.app, "image", None)
        if source is None:
            self.status.set("当前没有可回放的扫描图")
            return
        key = _app_key(self.app)
        if not force and self._snapshot_key == key:
            return
        self._snapshot_key = key
        self.generation += 1
        token = self.generation
        if self._pending is not None:
            self._pending.cancel()
        self._source = source
        self._trace = None
        for preview in self._previews.values():
            preview.close()
        self._previews.clear()
        self._photo = None
        self._photo_key = None
        self._stage_index = 0
        self._scale = min(1.0, 790.0 / max(1, source.width))
        self._size = source.size
        self.step_combo.configure(values=())
        self.step_var.set("计算中")
        self.status.set(f"正在分析第 {int(getattr(self.app, 'current_index', 0))+1} 页，记录真实阶段……")
        self.render()
        settings = copy.deepcopy(self.app.settings)
        page_index = int(getattr(self.app, "current_index", 0))
        page_sections = copy.deepcopy(list(getattr(self.app, "page_sections", []) or []))
        current_page = getattr(self.app, "current_page", None)
        source_path = Path(current_page) if current_page is not None else None
        future = self._executor.submit(
            _run_replay, source, settings, page_index, page_sections, source_path,
        )
        self._pending = future

        def completed(result: Any) -> None:
            if self.closed or token != self.generation:
                if isinstance(result, tuple) and isinstance(result[1], dict):
                    for preview in result[1].values():
                        preview.close()
                return
            trace, previews = result
            self._trace = trace
            self._previews = previews
            # Replay starts at the beginning, not at the final ordinary-drawing
            # result. The old default positioned Tk's small combobox list at
            # the bottom and concealed the new stages 03/04.
            self._stage_index = 0
            self.step_combo.configure(values=[
                f"{i+1:02d}  {stage['title']}" for i, stage in enumerate(trace.stages)
            ])
            self.render()

        def report(finished: Any) -> None:
            try:
                result = finished.result()
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}"
                def failed() -> None:
                    if not self.closed and token == self.generation:
                        self.status.set(f"回放诊断失败（原始 LAYOUT 不受影响）：{error_text}")
                try:
                    self.window.after(0, failed)
                except (RuntimeError, tk.TclError):
                    pass
                return
            try:
                self.window.after(0, completed, result)
            except (RuntimeError, tk.TclError):
                for preview in result[1].values():
                    preview.close()

        future.add_done_callback(report)

    def fit(self) -> None:
        if self._source is None:
            return
        width = max(350, int(self.canvas.winfo_width()) - 24)
        self._scale = min(1.0, width / max(1, self._source.width))
        self.render()

    def zoom(self, multiplier: float) -> None:
        self._scale = max(0.05, min(1.5, self._scale * multiplier))
        self.render()

    def select_step(self, _event: Any = None) -> None:
        if self._trace is None:
            return
        selected = self.step_combo.current()
        if selected >= 0:
            self._stage_index = selected
            self.before.set(False)
            self.render()

    def step(self, amount: int) -> None:
        if self._trace is None:
            return
        self._stage_index = max(0, min(len(self._trace.stages) - 1, self._stage_index + amount))
        self.before.set(False)
        self.render()

    def _show_text(self, text: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def render(self) -> None:
        if self.closed or self._source is None:
            return
        source = self._source
        stage = self._trace.stages[self._stage_index] if self._trace else None
        original = (
            _preview_at_stage(
                self._trace.stages, self._stage_index, self.before.get(),
                self._previews, source,
            )
            if self._trace else source
        )
        target = (
            max(1, int(source.width * self._scale)),
            max(1, int(source.height * self._scale)),
        )
        # Prevent accidental huge GUI photo allocations at high zoom.
        bound = min(1.0, 3000 / max(target), (15_000_000 / max(1, target[0] * target[1])) ** 0.5)
        target = (max(1, int(target[0] * bound)), max(1, int(target[1] * bound)))
        self._render_scale = target[0] / max(1, source.width)
        # Step changes repaint only overlay geometry; the expensive full-page
        # image resize is reused at a constant zoom and page.
        photo_key = (id(original), target)
        if self._photo is None or self._photo_key != photo_key:
            display = original.resize(target, Image.Resampling.LANCZOS)
            try:
                self._photo = ImageTk.PhotoImage(display, master=self.window)
            finally:
                display.close()
            self._photo_key = photo_key
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, *target))
        if stage is None:
            self._show_text("LAYOUT 正在计算。仅在本窗口启用期间进行诊断，正常识别结果不会改变。")
            return
        labels = self.step_combo.cget("values")
        if labels:
            self.step_combo.current(self._stage_index)
        self.previous_button.configure(state="normal" if self._stage_index else "disabled")
        self.next_button.configure(state="normal" if self._stage_index < len(self._trace.stages)-1 else "disabled")
        visual = _stage_rows_for_display(self._trace.stages, self._stage_index, self.before.get())
        factor = self._render_scale
        for col in visual["columns"]:
            # Source-aligned top-left/bottom-right envelope (not a fabricated
            # pixel-space segmentation mask).
            x0, y0 = col["source_start"]
            x1, y1 = col["source_end"]
            self.canvas.create_rectangle(x0*factor, y0*factor, x1*factor, y1*factor,
                                         outline="#129567", width=2, tags=_STEP_TAG)
        # Magenta dashed lines show actual per-column indent families, rather
        # than inventing sample rows from the final result.
        if visual["key"] in {"initial_roles", "indent_semantics", "body_lanes", "indent_recovery"}:
            for lane in visual.get("lanes", ()):
                x0, y0, x1, y1 = lane["source_line"]
                self.canvas.create_line(
                    x0*factor, y0*factor, x1*factor, y1*factor,
                    fill="#b63faa", width=2, dash=(4, 5), tags=_STEP_TAG,
                )
        changes = {item["id"]: item for item in stage.get("changes", [])}
        for row in visual["rows"]:
            x0, y0, x1, y1 = row["source_box"]
            changed = changes.get(row["id"]) if visual is stage else None
            # Role changes are outlined in vivid green. Removed rows are drawn
            # from their actual preceding stage, not guessed from final output.
            color = "#18ab42" if changed is not None else _ROLE_COLORS.get(row["role"], "#999999")
            width = 3 if changed is not None else 1
            self.canvas.create_rectangle(x0*factor, y0*factor, x1*factor, y1*factor,
                                         outline=color, width=width, tags=_STEP_TAG)
        if visual is stage and any(item["kind"] == "removed" for item in changes.values()):
            prior = _stage_rows_for_display(self._trace.stages, self._stage_index, True)
            by_id = {row["id"]: row for row in prior["rows"]}
            for key, change in changes.items():
                if change["kind"] != "removed" or key not in by_id:
                    continue
                x0, y0, x1, y1 = by_id[key]["source_box"]
                self.canvas.create_rectangle(x0*factor, y0*factor, x1*factor, y1*factor,
                                             outline="#e59a22", width=2, dash=(5, 3),
                                             tags=_STEP_TAG)
        # Candidate geometry comes directly from the same detector's optional
        # diagnostic trace (including rejected candidates), not a second scan.
        # Mask polygons belong to the AFTER state. They must disappear in
        # Before mode even when the current note has no physical rows.
        candidates = (
            _projection_candidates_for_display(stage, self.before.get())
            if stage["key"] in _PROJECTION_STAGES else
            (stage.get("candidates", []) if not self.before.get()
             else (self._trace.stages[self._stage_index-1].get("candidates", [])
                   if self._stage_index > 0 else []))
        )
        for candidate in candidates:
            status = str(candidate.get("status", "unknown"))
            polygon = candidate.get("source_polygon")
            if polygon and len(polygon) >= 3:
                points = [v*factor for p in polygon for v in p]
                self.canvas.create_polygon(
                    *points, fill="", width=3 if status == "masked" else 2,
                    outline="#e63c32" if status == "masked" else "#df9c24",
                    dash=() if status == "masked" else (5, 3), tags=_STEP_TAG,
                )
                continue
            box = candidate.get("source_box")
            if box and len(box) == 4:
                x0, y0, x1, y1 = box
                color, dash, width = _PROJECTION_STYLE.get(
                    status,
                    ("#16853c", (), 2) if status == "accepted" else
                    ("#c43d33", (4, 3), 2)
                    if "row_front" in status or "tall" in status else
                    ("#d99523", (4, 3), 2),
                )
                self.canvas.create_rectangle(
                    x0*factor, y0*factor, x1*factor, y1*factor,
                    outline=color, width=width, dash=dash,
                    tags=_STEP_TAG,
                )
            else:
                anchor = candidate.get("source_anchor")
                if anchor and len(anchor) == 2:
                    x0, y0 = anchor
                    r = 6
                    self.canvas.create_oval(
                        x0*factor-r, y0*factor-r, x0*factor+r, y0*factor+r,
                        outline="#d99523", width=2, tags=_STEP_TAG,
                    )
        self._visual_candidates = candidates
        self._visual_rows = visual["rows"]
        markers = _stage_entries_for_display(
            self._trace.stages, self._stage_index, self.before.get(),
        )
        marker_changes = (
            stage.get("entry_changes", []) if not self.before.get() else []
        )
        added = {
            (x["x"], x["y"]): x for x in marker_changes
            if x["kind"] in {"added", "provenance_changed"}
        }
        current_keys = {(x["x"], x["y"]) for x in markers}
        for marker in markers:
            x0, y0 = int(marker["x"]), int(marker["y"])
            marked = (x0, y0) in added
            self.canvas.create_oval(
                x0*factor-5, y0*factor-5, x0*factor+5, y0*factor+5,
                outline="#18a647" if marked else "#d63e3e",
                width=3 if marked else 2, tags=_STEP_TAG,
            )
        if not self.before.get():
            for event in marker_changes:
                if event["kind"] != "removed":
                    continue
                x0, y0 = event["x"]*factor, event["y"]*factor
                self.canvas.create_line(
                    x0-6, y0-6, x0+6, y0+6, fill="#dd9423",
                    width=2, tags=_STEP_TAG,
                )
                self.canvas.create_line(
                    x0+6, y0-6, x0-6, y0+6, fill="#dd9423",
                    width=2, tags=_STEP_TAG,
                )
        self._visual_markers = markers
        legend = (
            "灰=原始带 / 蓝=已连接带 / 橙=补足短空白"
            if stage["key"] == "projection_gap_bridge" else
            "蓝=拆分前 / 绿=输出段 / 紫=拆分点 / 黄=逻辑槽"
            if stage["key"] == "projection_tall_split" else
            "红=词条 / 蓝=正文 / 紫虚线=缩进群 / 绿粗框=变化"
        )
        self.status.set(
            f"{self._stage_index+1}/{len(self._trace.stages)}  {stage['title']}  "
            f"｜{legend}｜点击标记查看详情"
        )
        self._show_text(_format_stage(stage))

    def inspect_row(self, event: Any) -> None:
        if self._trace is None:
            return
        factor = max(0.01, getattr(self, "_render_scale", self._scale))
        x = int(self.canvas.canvasx(event.x) / factor)
        y = int(self.canvas.canvasy(event.y) / factor)
        selected_marker = next((
            item for item in getattr(self, "_visual_markers", [])
            if abs(int(item["x"]) - x) <= 9 and abs(int(item["y"]) - y) <= 9
        ), None)
        if selected_marker is not None:
            self._show_text(_format_stage(
                self._trace.stages[self._stage_index],
                selected_marker=selected_marker,
                marker_history=self._trace.history_for_entry(
                    int(selected_marker["x"]), int(selected_marker["y"]),
                ),
            ))
            return
        candidate = _candidate_at_source(
            getattr(self, "_visual_candidates", []), x, y,
            tolerance=max(6, int(round(4 / factor))),
        )
        if candidate is not None:
            self._show_text(_format_stage(
                self._trace.stages[self._stage_index], selected_candidate=candidate,
            ))
            return
        row = _row_at_position(getattr(self, "_visual_rows", []), x, y)
        if row is not None:
            self._show_text(_format_stage(
                self._trace.stages[self._stage_index], selected=row,
                history=self._trace.history_for_row(row["id"]),
            ))


def show_layout_step_replay(app: Any) -> None:
    current = getattr(app, "_layout_step_replay_window", None)
    if current is not None and not current.closed:
        current.window.lift()
        current.window.focus_set()
        return
    app._layout_step_replay_window = LayoutStepReplayWindow(app)
