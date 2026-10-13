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


def _app_key(app: Any) -> tuple[Any, ...]:
    from .adaptive_denoise import DENOISE_ENV
    return (
        id(getattr(app, "image", None)),
        int(getattr(app, "current_index", -1)),
        repr(getattr(app, "settings", None)),
        repr(getattr(app, "page_sections", ())),
        os.environ.get(DENOISE_ENV, "auto"),
    )


def _run_replay(source: Image.Image, settings: Any, page_index: int) -> tuple[LayoutStepTrace, Image.Image | None]:
    """Collect stages by running the actual production Layout Core once.

    This is a separate *read-only diagnostic run*: no layouts, Entry metadata,
    output files or project caches are mutated by playback.
    """
    from .image_utils import build_analysis_image
    from .layout_core_understanding import understand_layout_core

    trace = LayoutStepTrace()
    analysis = build_analysis_image(source, settings)
    try:
        profile = dict(analysis.info.get("analysis_denoise_profile") or {})
        trace.add_note(
            "image_preparation", "分析图与去噪",
            "原图未改动。该阶段显示实际送入 Layout 的共享分析图；"
            "去噪只改变分析副本，不改变原图坐标。",
            details={"denoise": profile, "source_size": list(source.size)},
        )
        masked = None
        if bool(getattr(settings, "layout_mask_illustrations", False)):
            from .layout_illustration_mask import mask_large_illustrations_for_layout
            try:
                masked, _stats = mask_large_illustrations_for_layout(
                    analysis, settings, profile_page_index=int(page_index),
                )
            except Exception:
                masked = None
        actual = masked if masked is not None else analysis
        if masked is not None and masked is not analysis:
            trace.add_note(
                "illustration_mask", "插图区域掩膜",
                "本阶段显示实际进入 Layout 的插图白化分析图（不改动原图）。",
            )
        # Only one downsized analysis preview is retained, rather than an
        # expensive RGB copy at each stage.
        cleaned = actual.copy()
        try:
            cleaned.thumbnail((1400, 1800), Image.Resampling.LANCZOS)
            understand_layout_core(actual, settings, page_index=page_index, trace=trace)
            return trace, cleaned
        except BaseException:
            cleaned.close()
            raise
        finally:
            if masked is not None and masked is not analysis:
                masked.close()
    finally:
        analysis.close()


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


def _format_stage(stage: dict[str, Any], *, selected: dict[str, Any] | None = None) -> str:
    lines = [stage["title"], "", stage["description"], ""]
    details = stage.get("details", {})
    for k, value in details.items():
        if isinstance(value, dict):
            lines.append(k + ":")
            for item, v in value.items():
                lines.append(f"  {item}: {v}")
        else:
            lines.append(f"{k}: {value}")
    rows = stage["rows"]
    if rows:
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["role"]] = counts.get(row["role"], 0) + 1
        lines.extend(["", f"本阶段物理行：{len(rows)}", "行角色：" + "、".join(
            f"{k} {v}" for k, v in sorted(counts.items())
        )])
    changes = stage.get("changes", [])
    if changes:
        lines.extend(["", f"相对上一个行状态的变化：{len(changes)}"])
        for c in changes[:100]:
            before = c["before"] if c["before"] is not None else "—"
            after = c["after"] if c["after"] is not None else "—"
            lines.append(f"  {c['id']}: {before} → {after} ({c['kind']})")
        if len(changes) > 100:
            lines.append(f"  ……其余 {len(changes)-100} 行可在图中查看")
    if selected is not None:
        lines.extend([
            "", "点击行详情：", selected["id"],
            "最终在这一阶段显示的角色：" + selected["role"],
            "原图位置：" + str(selected["source_box"]),
            "物理行 Y：" + str(selected["canonical_y"]),
            "检测到的 first_x：" + str(selected["first_x"]),
        ])
    lines.extend(["", "注意：此窗口只回放 Layout Core 的判定。",
                  "后续普通画线还有独立的裁决与过滤步骤；"
                  "相邻位置不代表某个证据是该线的唯一原因。"])
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
        self._cleaned: Image.Image | None = None
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
        self.step_combo = ttk.Combobox(toolbar, textvariable=self.step_var, state="readonly", width=30)
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
        self._cleaned = None
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
        self._cleaned = None
        self._photo = None
        self._photo_key = None
        self._stage_index = 0
        self._scale = min(1.0, 790.0 / max(1, source.width))
        self._size = source.size
        self.step_combo.configure(values=())
        self.step_var.set("计算中")
        self.status.set(f"正在分析第 {int(getattr(self.app, 'current_index', 0))+1} 页，记录真实阶段……")
        self.render()
        settings = copy.deepcopy(self.app._current_effective_profile_settings())
        page_index = int(getattr(self.app, "current_index", 0))
        future = self._executor.submit(_run_replay, source, settings, page_index)
        self._pending = future

        def completed(result: Any) -> None:
            if self.closed or token != self.generation:
                if isinstance(result, tuple) and isinstance(result[1], Image.Image):
                    result[1].close()
                return
            trace, cleaned = result
            self._trace = trace
            self._cleaned = cleaned
            self._stage_index = len(trace.stages) - 1
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
                if isinstance(result[1], Image.Image):
                    result[1].close()

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
        show_cleaned = bool(stage and stage["key"] in {"image_preparation", "illustration_mask"}
                            and self._cleaned is not None and not self.before.get())
        original = self._cleaned if show_cleaned else source
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
        for row in visual["rows"]:
            x0, y0, x1, y1 = row["source_box"]
            color = _ROLE_COLORS.get(row["role"], "#999999")
            self.canvas.create_rectangle(x0*factor, y0*factor, x1*factor, y1*factor,
                                         outline=color, width=1, tags=_STEP_TAG)
        self._visual_rows = visual["rows"]
        self.status.set(
            f"{self._stage_index+1}/{len(self._trace.stages)}  {stage['title']}  "
            f"｜红=词条 / 蓝=正文 / 灰=未知 / 绿=栏框｜点击物理行查看详情"
        )
        self._show_text(_format_stage(stage))

    def inspect_row(self, event: Any) -> None:
        if self._trace is None:
            return
        factor = max(0.01, getattr(self, "_render_scale", self._scale))
        x = int(self.canvas.canvasx(event.x) / factor)
        y = int(self.canvas.canvasy(event.y) / factor)
        row = _row_at_position(getattr(self, "_visual_rows", []), x, y)
        if row is not None:
            self._show_text(_format_stage(self._trace.stages[self._stage_index], selected=row))


def show_layout_step_replay(app: Any) -> None:
    current = getattr(app, "_layout_step_replay_window", None)
    if current is not None and not current.closed:
        current.window.lift()
        current.window.focus_set()
        return
    app._layout_step_replay_window = LayoutStepReplayWindow(app)
