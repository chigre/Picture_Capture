from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import tkinter as tk
from tkinter import filedialog, ttk

from ...project_storage import exports_root
from ...ui_compat import fit_window_to_work_area
from .common import _build_modern_dialog_heading


class OldNewComparisonWindow(tk.Toplevel):
    """Display page-aware differences between an old wordslist and current PDICs."""

    FILTERS = ("全部差异", "新增", "删除", "修改")

    def __init__(self, parent: "PictureCaptureApp", payload: dict[str, object]) -> None:
        super().__init__(parent)
        self.parent = parent
        self.payload = payload
        self.title("新旧比较")
        fit_window_to_work_area(self, 1180, 760, min_width=900, min_height=560)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)

        changes = list(payload.get("changes") or [])
        counts = dict(payload.get("counts") or {})
        page_order = list(payload.get("page_order") or [])
        source = Path(str(payload.get("source") or ""))
        missing_pages = list(payload.get("missing_old_pages") or [])

        outer = ttk.Frame(self, padding=(18, 14, 18, 12))
        outer.pack(fill="both", expand=True)
        _build_modern_dialog_heading(
            outer,
            "新旧比较",
            "将当前 PDIC 合集与旧词表按页面对齐比较。先确认比较来源，再查看差异、保存快照或导出报告。",
        )

        top = ttk.LabelFrame(outer, text="比较来源", padding=(10, 7))
        top.pack(fill="x")
        ttk.Label(top, text="旧词表：").pack(side="left")
        self.source_var = tk.StringVar(value=str(source))
        ttk.Entry(top, textvariable=self.source_var, state="readonly").pack(side="left", fill="x", expand=True, padx=(4, 8))
        ttk.Button(top, text="更换 wordslist…", command=self._choose_source_again).pack(side="left")
        ttk.Button(top, text="重新比较", command=self._refresh_from_parent).pack(side="left", padx=(6, 0))

        first = page_order[0] if page_order else "—"
        last = page_order[-1] if page_order else "—"
        diff_total = sum(int(counts.get(kind, 0) or 0) for kind in ("新增", "删除", "修改"))
        summary = (
            f"范围：{first} → {last}（{len(page_order)} 页）｜"
            f"旧 {int(counts.get('old_rows', 0) or 0)} 行｜新 {int(counts.get('new_rows', 0) or 0)} 行｜"
            f"差异 {diff_total}：新增 {int(counts.get('新增', 0) or 0)}，"
            f"删除 {int(counts.get('删除', 0) or 0)}，修改 {int(counts.get('修改', 0) or 0)}"
        )
        summary_box = ttk.LabelFrame(
            outer, text="比较摘要", padding=(10, 7),
        )
        summary_box.pack(fill="x", pady=(10, 6))
        ttk.Label(summary_box, text=summary, anchor="w").pack(fill="x")
        if missing_pages:
            preview = "、".join(missing_pages[:12])
            suffix = f" 等 {len(missing_pages)} 页" if len(missing_pages) > 12 else ""
            ttk.Label(
                outer,
                text=f"注意：旧词表未出现所选范围中的页面：{preview}{suffix}；这些页的当前 PDIC 词条会显示为新增。",
                foreground="#9a6700",
                wraplength=1120,
            ).pack(fill="x", pady=(0, 6))
        elif not changes:
            ttk.Label(outer, text="所选范围内文本完全一致。", foreground="#2d6a4f").pack(fill="x", pady=(0, 6))

        filter_row = ttk.Frame(outer)
        filter_row.pack(fill="x", pady=(4, 8))
        ttk.Label(filter_row, text="显示：").pack(side="left")
        self.filter_var = tk.StringVar(value="全部差异")
        combo = ttk.Combobox(filter_row, textvariable=self.filter_var, values=self.FILTERS, state="readonly", width=12)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_tree())
        self.visible_count_var = tk.StringVar(value="")
        ttk.Label(filter_row, textvariable=self.visible_count_var, foreground="#666666").pack(side="left", padx=(8, 0))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        diff_tab = ttk.Frame(notebook)
        notebook.add(diff_tab, text="差异")
        cols = ("kind", "page", "old_index", "old", "new_index", "new")
        self.tree = ttk.Treeview(diff_tab, columns=cols, show="headings", selectmode="browse")
        headings = {
            "kind": ("类型", 66, "center"),
            "page": ("页码", 92, "center"),
            "old_index": ("旧行", 58, "center"),
            "old": ("旧词条（wordslist）", 360, "w"),
            "new_index": ("新行", 58, "center"),
            "new": ("新词条（PDIC）", 360, "w"),
        }
        for key, (label, width, anchor_value) in headings.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=45, anchor=anchor_value, stretch=key in {"old", "new"})
        ybar = ttk.Scrollbar(diff_tab, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(diff_tab, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        diff_tab.rowconfigure(0, weight=1)
        diff_tab.columnconfigure(0, weight=1)
        self.refresh_appearance()

        self._add_text_tab(notebook, "当前 PDIC 合集", str(payload.get("new_text") or ""))
        self._add_text_tab(notebook, "旧 wordslist 片段", str(payload.get("old_text") or ""))

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(
            bottom, text="保存当前 PDIC 快照…",
            command=self._save_new_snapshot,
        ).pack(side="left")
        ttk.Button(
            bottom, text="导出差异报告…",
            command=self._save_diff_report,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(bottom, text="关闭", command=self._close).pack(side="right")

        self._refresh_tree()
        self.lift()
        try:
            self.focus_force()
        except tk.TclError:
            pass

    def refresh_appearance(self) -> None:
        if self.parent.appearance_mode == "dark":
            colors = {
                "新增": ("#21483b", "#d8f3dc"),
                "删除": ("#512f35", "#ffd7dc"),
                "修改": ("#51451f", "#ffe9a8"),
            }
        else:
            colors = {
                "新增": ("#e7f6ea", "#111827"),
                "删除": ("#fde8e7", "#111827"),
                "修改": ("#fff4d6", "#111827"),
            }
        for tag, (background, foreground) in colors.items():
            self.tree.tag_configure(tag, background=background, foreground=foreground)
        self.parent._apply_current_appearance(self)

    def _add_text_tab(self, notebook: ttk.Notebook, label: str, content: str) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=label)
        text_widget = tk.Text(frame, wrap="none", undo=False)
        ybar = ttk.Scrollbar(frame, orient="vertical", command=text_widget.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=text_widget.xview)
        text_widget.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        text_widget.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text_widget.insert("1.0", content)
        text_widget.configure(state="disabled")

    def _refresh_tree(self) -> None:
        selected = self.filter_var.get()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        shown = 0
        for index, item in enumerate(list(self.payload.get("changes") or [])):
            kind = str(item.get("kind") or "")
            if selected != "全部差异" and kind != selected:
                continue
            self.tree.insert(
                "", "end", iid=f"d{index}",
                values=(
                    kind,
                    str(item.get("page") or ""),
                    "" if item.get("old_index") is None else item.get("old_index"),
                    str(item.get("old") or ""),
                    "" if item.get("new_index") is None else item.get("new_index"),
                    str(item.get("new") or ""),
                ),
                tags=(kind,),
            )
            shown += 1
        self.visible_count_var.set(f"当前显示 {shown} 条")

    def _save_text_payload(self, *, title: str, initialfile: str, content: str) -> None:
        initialdir = exports_root(self.parent.project.root) if self.parent.project else Path.cwd()
        chosen = filedialog.asksaveasfilename(
            parent=self, title=title, initialdir=str(initialdir), initialfile=initialfile,
            defaultextension=".txt", filetypes=[("文本", "*.txt"), ("全部", "*")],
        )
        if not chosen:
            return
        Path(chosen).write_text(content, encoding="utf-8-sig")
        self.parent.status_var.set(f"已保存：{chosen}")

    def _save_new_snapshot(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._save_text_payload(
            title="保存当前 PDIC 合集",
            initialfile=f"PDIC_words_{stamp}.txt",
            content=str(self.payload.get("new_text") or ""),
        )

    def _save_diff_report(self) -> None:
        rows = ["类型\t页码\t旧行\t旧词条\t新行\t新词条"]
        for item in list(self.payload.get("changes") or []):
            values = [
                str(item.get("kind") or ""), str(item.get("page") or ""),
                "" if item.get("old_index") is None else str(item.get("old_index")),
                str(item.get("old") or "").replace("\t", " "),
                "" if item.get("new_index") is None else str(item.get("new_index")),
                str(item.get("new") or "").replace("\t", " "),
            ]
            rows.append("\t".join(values))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        page_order = [str(item) for item in list(self.payload.get("page_order") or []) if str(item)]
        first = page_order[0] if page_order else "unknown"
        last = page_order[-1] if page_order else first
        scope = first if first == last else f"{first}-{last}"
        # Windows-safe filename while preserving the visible page range.
        scope = re.sub(r'[<>:"/\\|?*]+', "_", scope).strip(" .") or "unknown"
        self._save_text_payload(
            title="保存新旧比较差异报告",
            initialfile=f"words_diff_{scope}_{stamp}.txt",
            content="\n".join(rows) + "\n",
        )

    def _refresh_from_parent(self) -> None:
        self.parent.compare_old_new_selected_scope(force_choose=False)

    def _choose_source_again(self) -> None:
        self.parent.compare_old_new_selected_scope(force_choose=True)

    def _close(self) -> None:
        if getattr(self.parent, "old_new_compare_window", None) is self:
            self.parent.old_new_compare_window = None
        self.destroy()


__all__ = ["OldNewComparisonWindow"]
