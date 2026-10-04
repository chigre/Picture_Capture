from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from ...coordinate_space import SOURCE_COORDINATE_SPACE
from ...crop.settings import CROP_SETTINGS_VERSION
from ...project_storage import qt_root
from ...ui_compat import fit_window_to_work_area
from .common import _build_modern_dialog_heading


class CropSettingsDialog(tk.Toplevel):
    """Unified crop settings used by both whole-entry and PPP illustration export."""

    CONFIG_NAME = "_CropSettings.json"

    def __init__(self, parent: tk.Misc, indices: list[int]) -> None:
        super().__init__(parent)
        self.parent = parent
        self.indices = list(indices)
        self.title("切图设置")
        fit_window_to_work_area(self, 780, 560, min_width=700, min_height=500)
        self.transient(parent)
        self.grab_set()
        self.general_top_var = tk.StringVar()
        self.general_bottom_var = tk.StringVar()
        self.entry_left_padding_var = tk.StringVar()
        self.entry_right_padding_var = tk.StringVar()
        self.integrate_illustrations_var = tk.BooleanVar(value=True)
        self.margin_var = tk.StringVar()
        self.workers_var = tk.StringVar()
        self.status_var = tk.StringVar(value="")
        self._load_initial_values()
        self._build()

    @property
    def _config_path(self) -> Path | None:
        if not self.parent.project:
            return None
        return qt_root(self.parent.project.root) / self.CONFIG_NAME

    def _load_initial_values(self) -> None:
        saved = self.parent._load_crop_settings()
        self.general_top_var.set(str(saved.get("general_top_y", self.parent.settings.start_y)))
        default_bottom = self.parent.settings.bottom_y if self.parent.settings.crop_to_bottom_y else 0
        self.general_bottom_var.set(str(saved.get("general_bottom_y", default_bottom)))
        self.entry_left_padding_var.set(str(saved.get("entry_left_padding_x", 0)))
        self.entry_right_padding_var.set(str(saved.get("entry_right_padding_x", 0)))
        self.integrate_illustrations_var.set(bool(saved.get("integrate_illustrations", True)))
        self.margin_var.set(str(saved.get("polygon_margin", 0)))
        self.workers_var.set(str(saved.get("parallel_workers", self.parent.settings.crop_parallel_workers)))
        self._specials = (
            dict(saved.get("special_pages", {}))
            if isinstance(saved.get("special_pages", {}), dict) else {}
        )

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=(18, 14, 18, 12))
        outer.pack(fill="both", expand=True)
        _build_modern_dialog_heading(
            outer,
            "切图设置",
            "完整切图设置（词条切图 / 插图切图共用）。Section=0 页面使用通用上下边界；Section>0 页面由主界面 Section 边界接管。",
        )

        general = ttk.LabelFrame(
            outer, text="通用切图规则", padding=(12, 10),
        )
        general.pack(fill="x")
        ttk.Label(general, text="主界面页面范围：").grid(row=0, column=0, sticky="w")
        scope = f"{len(self.indices)} 页"
        if self.indices and self.parent.project:
            first = self.parent.project.images[self.indices[0]].stem
            last = self.parent.project.images[self.indices[-1]].stem
            scope += f"（{first} → {last}）"
        ttk.Label(general, text=scope).grid(row=0, column=1, columnspan=4, sticky="w")

        ttk.Label(general, text="一般页切图上边界 Y（原图）：").grid(row=1, column=0, sticky="w", pady=(7, 2))
        ttk.Entry(general, textvariable=self.general_top_var, width=10).grid(row=1, column=1, sticky="w", pady=(7, 2))
        ttk.Label(general, text="一般页切图下边界 Y（原图）：").grid(row=1, column=2, sticky="w", padx=(14, 0), pady=(7, 2))
        ttk.Entry(general, textvariable=self.general_bottom_var, width=10).grid(row=1, column=3, sticky="w", pady=(7, 2))
        ttk.Label(
            general,
            text="单位：原图像素；0 = 页面底部。仅用于 Section=0 页面；Section>0 时以页面 Section 边界为准。",
            foreground="#666666",
        ).grid(row=2, column=0, columnspan=5, sticky="w")

        ttk.Label(general, text="词条 X 左侧额外留白：").grid(row=3, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(general, textvariable=self.entry_left_padding_var, width=10).grid(row=3, column=1, sticky="w", pady=(8, 2))
        ttk.Label(general, text="词条 X 右侧额外留白：").grid(row=3, column=2, sticky="w", padx=(14, 0), pady=(8, 2))
        ttk.Entry(general, textvariable=self.entry_right_padding_var, width=10).grid(row=3, column=3, sticky="w", pady=(8, 2))
        ttk.Label(
            general,
            text="单位：原图像素；运行时不按页面宽度缩放。",
        ).grid(row=4, column=0, columnspan=5, sticky="w")

        ttk.Checkbutton(
            general,
            text="是否综合插图计算切图信息",
            variable=self.integrate_illustrations_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Label(
            general,
            text="关闭后：词条只按自身矩形切图；PPP不扩框/不联合/不参与词条切图顺序，词条内部插图仍自然保留",
            foreground="#666666",
        ).grid(row=5, column=2, columnspan=3, sticky="w", pady=(8, 2))

        ttk.Label(general, text="PPP多边形外扩（原图）：").grid(row=6, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(general, textvariable=self.margin_var, width=10).grid(row=6, column=1, sticky="w", pady=(8, 2))
        ttk.Label(general, text="原图像素（只影响插图导出，不改PPP原图坐标）").grid(row=6, column=2, columnspan=3, sticky="w", pady=(8, 2))
        ttk.Label(general, text="并行进程：").grid(row=7, column=0, sticky="w", pady=2)
        ttk.Entry(general, textvariable=self.workers_var, width=10).grid(row=7, column=1, sticky="w", pady=2)
        ttk.Label(general, text="0 = 自动；词条/插图切图共用").grid(row=7, column=2, columnspan=3, sticky="w", pady=2)

        section_info = ttk.LabelFrame(
            outer, text="特殊页面范围", padding=(12, 10),
        )
        section_info.pack(fill="x", pady=(10, 0))
        ttk.Label(
            section_info,
            text="特殊页面请在主界面【六、页面列表】的 Section 列双击设置；Section=1 可直接拖动单一上/下边界，Section≥2 可设置多个阅读区。",
            wraplength=720, justify="left",
        ).pack(anchor="w")

        bottom = ttk.Frame(self, padding=(18, 0, 18, 12))
        bottom.pack(fill="x")
        ttk.Label(
            bottom, textvariable=self.status_var,
            anchor="w", foreground="#666666",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="关闭", command=self.destroy).pack(side="right")
        ttk.Button(
            bottom, text="保存并关闭", command=self.save_settings
        ).pack(side="right", padx=(0, 6))

    @staticmethod
    def _nonnegative_int(value: str, label: str) -> int:
        try:
            number = int(str(value).strip() or "0")
        except ValueError as exc:
            raise ValueError(f"{label}必须是整数") from exc
        if number < 0:
            raise ValueError(f"{label}不能小于0")
        return number

    def _payload(self) -> dict:
        top = self._nonnegative_int(self.general_top_var.get(), "一般页眉Y")
        bottom = self._nonnegative_int(self.general_bottom_var.get(), "一般底部Y")
        entry_left = self._nonnegative_int(self.entry_left_padding_var.get(), "词条左侧额外留白")
        entry_right = self._nonnegative_int(self.entry_right_padding_var.get(), "词条右侧额外留白")
        margin = self._nonnegative_int(self.margin_var.get(), "PPP多边形外扩")
        workers = self._nonnegative_int(self.workers_var.get(), "并行进程数")
        if workers > 8:
            raise ValueError("并行进程数必须为 0–8")
        if bottom and bottom <= top:
            raise ValueError("一般底部Y必须大于页眉Y，或填0表示图片底部")
        return {
            "version": CROP_SETTINGS_VERSION,
            "coordinate_space": SOURCE_COORDINATE_SPACE,
            "general_top_y": top,
            "general_bottom_y": bottom,
            "entry_left_padding_x": entry_left,
            "entry_right_padding_x": entry_right,
            "integrate_illustrations": bool(self.integrate_illustrations_var.get()),
            "polygon_margin": margin,
            "parallel_workers": workers,
            # Read-only compatibility for old projects. New per-page ranges live
            # in PageSections sidecars and take precedence during crop planning.
            "special_pages": dict(self._specials),
        }

    def save_settings(self) -> None:
        try:
            payload = self._payload()
            path = self._config_path
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            # Keep legacy AppSettings mirrors synchronized for backward compatibility,
            # but all user-facing crop controls live exclusively in 【切图设置】.
            self.parent.settings.crop_parallel_workers = int(payload["parallel_workers"])
            self.parent.save_settings()
            if self.parent.crop_preview_var.get():
                self.parent.redraw()
            self.parent.status_var.set("切图设置已保存；Section=0 页面使用通用边界，Section>0 页面使用各自 Section 边界。")
            self.destroy()
        except Exception as exc:
            messagebox.showerror("切图设置无效", str(exc), parent=self)


__all__ = ["CropSettingsDialog"]
