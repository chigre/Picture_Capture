from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from ...ui_compat import fit_window_to_work_area
from .common import _build_modern_dialog_heading


class OCRConflictReviewDialog(tk.Toplevel):
    """Review v2.1 multi-OCR decisions and jump directly to the page row."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("OCR词头冲突复核")
        fit_window_to_work_area(self, 1180, 680, min_width=900, min_height=520)
        self.only_issues = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="")
        self._row_ids: list[str] = []

        outer = ttk.Frame(self, padding=(18, 14, 18, 14))
        outer.pack(fill="both", expand=True)
        _build_modern_dialog_heading(
            outer,
            "OCR 词头冲突复核",
            "集中检查多 OCR 引擎意见不一致或需要人工确认的候选。先选中一行，再决定采用哪个结果。",
        )

        filter_bar = ttk.Frame(outer)
        filter_bar.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            filter_bar,
            text="只显示需要关注的候选",
            variable=self.only_issues,
            command=self.refresh,
        ).pack(side="left")
        ttk.Button(filter_bar, text="刷新", command=self.refresh).pack(
            side="left", padx=(8, 0)
        )

        action_bar = ttk.LabelFrame(
            outer, text="所选候选", padding=(10, 7),
        )
        action_bar.pack(fill="x", pady=(0, 10))
        ttk.Button(
            action_bar, text="选择 / 取消",
            command=self.toggle_selected,
        ).pack(side="left")
        ttk.Button(
            action_bar, text="手工词头…",
            command=self.choose_manual,
        ).pack(side="left", padx=(6, 0))
        ttk.Separator(action_bar, orient="vertical").pack(
            side="left", fill="y", padx=10
        )
        ttk.Button(
            action_bar, text="采用 Paddle",
            command=lambda: self.choose_engine("paddle"),
        ).pack(side="left")
        ttk.Button(
            action_bar, text="采用 Tesseract",
            command=lambda: self.choose_engine("tesseract"),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            action_bar, text="采用 Lens",
            command=lambda: self.choose_engine("lens"),
        ).pack(side="left", padx=(6, 0))

        frame = ttk.Frame(outer)
        frame.pack(fill="both", expand=True)
        cols = (
            "selected", "column", "y", "issues", "paddle", "tesseract",
            "lens", "final", "engine", "reason",
        )
        self.tree = ttk.Treeview(
            frame, columns=cols, show="headings", selectmode="browse"
        )
        labels = {
            "selected": "选中", "column": "栏", "y": "Y", "issues": "问题",
            "paddle": "Paddle", "tesseract": "Tesseract",
            "lens": "Google Lens", "final": "最终词头",
            "engine": "采用", "reason": "决策原因",
        }
        widths = {
            "selected": 55, "column": 45, "y": 70, "issues": 190,
            "paddle": 145, "tesseract": 145, "lens": 145,
            "final": 145, "engine": 85, "reason": 180,
        }
        for key in cols:
            self.tree.heading(key, text=labels[key])
            self.tree.column(key, width=widths[key], anchor="w")
        ybar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self.on_double_click)

        status_bar = ttk.Frame(outer)
        status_bar.pack(fill="x", pady=(8, 0))
        ttk.Label(
            status_bar, textvariable=self.status_var,
            foreground="#666666", anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(status_bar, text="关闭", command=self.destroy).pack(side="right")
        self.refresh()

    def _selected_candidate(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        cid = str(self.tree.item(selection[0], "tags")[0]) if self.tree.item(selection[0], "tags") else ""
        return self.parent.get_review_candidate(cid)

    def refresh(self) -> None:
        self.parent._load_ocr_review_candidates()
        for item in self.tree.get_children(): self.tree.delete(item)
        shown = 0
        for cand in self.parent.ocr_review_candidates:
            issues = list(cand.get("issue_types", []) or [])
            if self.only_issues.get() and not (issues or cand.get("needs_review")):
                continue
            p = cand.get("paddle", {}) or {}; t = cand.get("tesseract", {}) or {}; lens = cand.get("lens", {}) or {}
            values = (
                "✓" if self.parent._candidate_is_selected(cand) else "",
                int(cand.get("column", 0)) + 1,
                cand.get("source_y", ""),
                ",".join(issues),
                p.get("lemma", ""), t.get("lemma", ""), lens.get("lemma", ""), cand.get("word", ""),
                cand.get("final_engine", ""), cand.get("decision_reason", ""),
            )
            cid = str(cand.get("candidate_id", ""))
            self.tree.insert("", "end", values=values, tags=(cid,))
            shown += 1
        self.status_var.set(f"当前页显示 {shown} 条；双击任一行可跳到原图位置。")

    def on_double_click(self, _event=None) -> None:
        cand = self._selected_candidate()
        if cand:
            self.parent.jump_to_review_candidate(cand)

    def toggle_selected(self) -> None:
        cand = self._selected_candidate()
        if not cand: return
        self.parent.set_candidate_selected(cand, not self.parent._candidate_is_selected(cand))
        self.refresh()

    def choose_engine(self, engine: str) -> None:
        cand = self._selected_candidate()
        if not cand: return
        side = cand.get(engine, {}) or {}
        if side.get("y") is None:
            messagebox.showinfo("无此结果", f"该候选没有 {engine} 结果。", parent=self)
            return
        self.parent.apply_candidate_choice(cand, engine, str(side.get("lemma") or ""))
        self.refresh()

    def choose_manual(self) -> None:
        cand = self._selected_candidate()
        if not cand: return
        value = simpledialog.askstring("手工词头", "请输入最终 lemma：", initialvalue=str(cand.get("word", "")), parent=self)
        if value is None: return
        self.parent.apply_candidate_choice(cand, "manual", value.strip())
        self.refresh()


__all__ = ["OCRConflictReviewDialog"]
