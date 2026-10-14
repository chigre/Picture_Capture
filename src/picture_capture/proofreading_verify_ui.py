"""Explicit visual verification dialog for saved, project-local proofreading.

Never approves a record by default; presenting OCR or a manual edit is NOT a
gold label. The only durable action is a user-confirmed independent verify event.
"""
from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from uuid import NAMESPACE_URL, uuid5

from PIL import Image, ImageDraw, ImageOps, ImageTk

from .formats import pdic_path
from .project_storage import data_root
from .proofreading_events import load_events, sha256_file
from .proofreading_verification import verify_saved_action


def journal_for_existing_page(project_root: Path, page: Path) -> Path | None:
    """Read-only journal locator. Viewing must never create a project ID."""
    root = Path(project_root)
    identity_path = data_root(root) / "ProofreadingEvidence" / "project_identity.json"
    if not identity_path.is_file():
        return None
    try:
        from .proofreading_capture import IDENTITY_FORMAT
        record = json.loads(identity_path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("format") != IDENTITY_FORMAT:
            return None
        project_id = record.get("project_id")
        if not isinstance(project_id, str) or len(project_id) != 32:
            return None
        if any(c not in "0123456789abcdef" for c in project_id):
            return None
        relative = Path(page).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError, TypeError):
        return None
    key = uuid5(NAMESPACE_URL, relative).hex
    path = identity_path.parent / f"{key}.json"
    return path if path.is_file() else None


def actionable_saved_events(
    journal: Path | None, pdic: Path, image: Path,
    *, ocr_cache: Path | None = None,
) -> list[dict]:
    """Offer only fresh, stable, unreviewed events, without changing files."""
    if journal is None:
        return []
    events = load_events(journal)
    pdic_hash = sha256_file(pdic)
    image_hash = sha256_file(image)
    if not pdic_hash or not image_hash:
        return []
    checked = {
        row.get("before", {}).get("reviewed_operation_id")
        for row in events
        if row.get("action") == "verify" and isinstance(row.get("before"), dict)
    }
    current_ocr = None
    if ocr_cache is not None and Path(ocr_cache).is_file():
        try:
            raw = json.loads(Path(ocr_cache).read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                current_ocr = raw.get("signature")
        except (OSError, ValueError, TypeError):
            pass
    result = []
    for event in events:
        if event.get("action") == "verify":
            continue
        if event.get("verification_status") != "explicit_action_unverified_page":
            continue
        if not event.get("entry_id") or event.get("operation_id") in checked:
            continue
        if event.get("pdic_sha256") != pdic_hash:
            continue
        if event.get("image_sha256") != image_hash:
            continue
        signature = event.get("ocr_signature")
        if signature is not None and signature != current_ocr:
            continue
        result.append(event)
    return result


class ProofreadingVisualVerificationDialog(tk.Toplevel):
    """No preselection, no automatic consent, source-pixel proofread preview."""

    def __init__(self, owner: tk.Misc, *, project_root: Path,
                 page: Path, ocr_cache: Path | None = None) -> None:
        super().__init__(owner)
        self.page = Path(page)
        self.pdic = pdic_path(self.page)
        self.journal = journal_for_existing_page(project_root, page)
        self.ocr_cache = Path(ocr_cache) if ocr_cache is not None else None
        self.events: dict[str, dict] = {}
        self.preview_photo = None
        self.title("人工核验已保存校对操作（仅本地）")
        self.geometry("760x620")
        self.minsize(610, 500)
        self.transient(owner)
        self._selected_id: str | None = None
        self._preview_valid = False

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="逐项核验已保存操作", font=("", 13, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            outer, wraplength=710,
            text="先选操作，再对照原扫描局部。只有亲自核查后才能确认；"
                 "校对动作本身不是训练真值，不上传或训练模型。",
        ).pack(anchor="w", pady=(6, 10))
        columns = ("time", "kind", "change")
        self.table = ttk.Treeview(
            outer, columns=columns, show="headings", height=8, selectmode="browse"
        )
        for key, name, width in [
            ("time", "时间（UTC）", 180), ("kind", "操作", 100),
            ("change", "前后内容", 370),
        ]:
            self.table.heading(key, text=name)
            self.table.column(key, width=width, stretch=(key == "change"))
        self.table.pack(fill="x")
        self.table.bind("<<TreeviewSelect>>", self._select)
        self.preview = ttk.Label(outer, text="请选择一个操作，显示对应原扫描局部")
        self.preview.pack(anchor="center", pady=(14, 8))
        self.details = tk.StringVar(value="未选择")
        ttk.Label(outer, textvariable=self.details, wraplength=700).pack(
            anchor="w", pady=(0, 8)
        )
        self.confirmed = tk.BooleanVar(value=False)
        self.checkbox = ttk.Checkbutton(
            outer, text="我已亲自查看上述原扫描局部，并确认本次判断",
            variable=self.confirmed, command=self._enable_buttons,
        )
        self.checkbox.pack(anchor="w", pady=(8, 8))
        bar = ttk.Frame(outer)
        bar.pack(fill="x", side="bottom", pady=(12, 0))
        self.positive = ttk.Button(
            bar, text="确认：是词头", command=lambda: self._confirm("correct_headword")
        )
        self.positive.pack(side="left")
        self.negative = ttk.Button(
            bar, text="确认：非词头", command=lambda: self._confirm("not_headword")
        )
        self.negative.pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="关闭", command=self.destroy).pack(side="right")
        self._reload()
        self.grab_set()
        self._enable_buttons()

    def _reload(self) -> None:
        existing_rows = self.table.get_children()
        if existing_rows:
            self.table.delete(*existing_rows)
        try:
            rows = actionable_saved_events(
                self.journal, self.pdic, self.page, ocr_cache=self.ocr_cache
            )
        except (OSError, ValueError, TypeError) as error:
            messagebox.showerror("无法读取本地校对日志", str(error), parent=self)
            rows = []
        self.events = {row["operation_id"]: row for row in rows}
        for row in rows:
            before = row.get("before") or {}
            after = row.get("after") or {}
            description = f"{before.get('word', '—')} → {after.get('word', '—')}"
            self.table.insert(
                "", "end", iid=row["operation_id"],
                values=(row.get("recorded_utc", "")[:19], row.get("action", ""), description),
            )
        self._selected_id = None
        self._preview_valid = False
        self.preview.configure(image="", text="请选择一个操作，显示对应原扫描局部")
        self.preview_photo = None
        self.details.set(
            f"当前可核验 {len(rows)} 项。无记录通常意味着未开启功能、"
            "操作已核验，或原始 PDIC/图片已改变。"
        )
        self.confirmed.set(False)
        self._enable_buttons()

    def _select(self, _event=None) -> None:
        selected = self.table.selection()
        self.confirmed.set(False)
        self._selected_id = selected[0] if selected else None
        self._preview_valid = False
        self.preview_photo = None
        if not self._selected_id or self._selected_id not in self.events:
            self._enable_buttons()
            return
        row = self.events[self._selected_id]
        before = row.get("before") or {}
        after = row.get("after") or {}
        self.details.set(
            f"原记录：{before.get('word', '—')}，"
            f"保存后：{after.get('word', '—')}；"
            "红圈标示当前记录坐标；仅检查该处是否属于词头，不自动判定。"
        )
        position = after if "x" in after and "y" in after else before
        try:
            x, y = int(position["x"]), int(position["y"])
            # Do not show any unrelated page or auto-approve if the preview
            # cannot be obtained from the actual current source scan.
            with Image.open(self.page) as opened:
                source = ImageOps.exif_transpose(opened)
                w, h = source.size
                if not (0 <= x < w and 0 <= y < h):
                    raise ValueError("Marker position is outside the source scan")
                left, top = max(0, x - 140), max(0, y - 65)
                crop = source.crop((
                    left, top, min(w, x + 330), min(h, y + 100),
                )).convert("RGB")
                # The red circle annotates only the temporary preview, never
                # the original scanned dictionary image on disk.
                marker_x, marker_y = x - left, y - top
                ImageDraw.Draw(crop).ellipse(
                    (
                        marker_x - 9, marker_y - 9,
                        marker_x + 9, marker_y + 9,
                    ),
                    outline="#df3030", width=3,
                )
                crop.thumbnail((650, 270))
                photo = ImageTk.PhotoImage(crop, master=self)
            self.preview_photo = photo
            self.preview.configure(image=photo, text="")
            self._preview_valid = True
        except (OSError, ValueError, TypeError, KeyError, tk.TclError) as exc:
            self.preview.configure(image="", text=f"无法预览源扫描：{exc}")
        self._enable_buttons()

    def _enable_buttons(self) -> None:
        enabled = bool(
            self._selected_id and self._preview_valid and self.confirmed.get()
        )
        for button in (self.positive, self.negative):
            button.configure(state="normal" if enabled else "disabled")

    def _confirm(self, judgment: str) -> None:
        if not (
            self._selected_id and self._preview_valid and self.confirmed.get()
            and self._selected_id in self.events
        ):
            return
        if not messagebox.askyesno(
            "确认人工核验",
            "确认已亲自查看扫描图，并记录本次判断？\n"
            "此操作只记入本地审计日志，不用于模型训练。",
            parent=self,
        ):
            return
        try:
            verify_saved_action(
                journal=self.journal, pdic_file=self.pdic,
                image_file=self.page, operation_id=self._selected_id,
                judgment=judgment, explicitly_confirmed=True,
                ocr_cache=self.ocr_cache,
            )
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("核验失败（未写入）", str(exc), parent=self)
        else:
            messagebox.showinfo("核验已保存", "仅更新本地审计记录。", parent=self)
        self._reload()


def _review_has_uncommitted_text(review_window: tk.Misc) -> bool:
    """Fail closed if a save returned without binding/committing live editor text.

    A pending OCR page may decline ownership without raising an exception.
    Stable rendered Entry bindings, not index-based page sorting, are required.
    """
    try:
        rows = review_window._bound_row_entries()
        vars_ = review_window.vars
        if len(rows) != len(vars_):
            return True
        if any(field.get().strip() != entry.word for field, entry in zip(vars_, rows)):
            return True
        parent = review_window.parent
        page = getattr(parent, "current_page", None)
        dirty_pages = getattr(review_window, "_simplified_dirty_pages", ())
        if page is not None and page.stem in dirty_pages:
            return True
    except (AttributeError, TypeError, ValueError, tk.TclError):
        return True
    return False


def open_visual_verification(review_window: tk.Misc) -> None:
    """Open a dialog only with the local recording opt-in enabled."""
    parent = review_window.parent
    if not getattr(getattr(parent, "settings", None), "proofreading_event_capture", False):
        messagebox.showinfo(
            "核验未启用", "请先在设置中心开启“记录本地校对操作证据”。",
            parent=review_window,
        )
        return
    project = getattr(parent, "project", None)
    page = getattr(parent, "current_page", None)
    if project is None or page is None:
        return
    # Filtered edits can still be flushing in the background. Do not begin
    # confirmation until they are committed; the same applies to OCR batches.
    if getattr(review_window, "_filter_rows_active", False):
        messagebox.showinfo(
            "请先完成保存", "请先退出筛选校对，等待当前页修改完成保存后再核验。",
            parent=review_window,
        )
        return
    batch_state = getattr(parent, "_foreground_batch_state", None)
    current_index = getattr(parent, "current_index", -1)
    if callable(batch_state) and batch_state(current_index) in {"pending", "processing"}:
        messagebox.showinfo(
            "请先完成保存", "当前页正在处理或尚未完成保存，请稍后手动打开核验。",
            parent=review_window,
        )
        return
    # Commit outstanding live proofreading edits, then re-check disk. Never
    # display a stale operation as verified merely because it is still selected.
    review_window.save(redraw_main=False)
    if getattr(parent, "current_page", None) != page:
        return
    if _review_has_uncommitted_text(review_window) or (
        callable(batch_state)
        and batch_state(getattr(parent, "current_index", -1)) in {"pending", "processing"}
    ):
        messagebox.showinfo(
            "请先完成保存",
            "校对编辑尚未成功提交，或页面仍在处理中；请完成保存后再核验。",
            parent=review_window,
        )
        return
    cache_fn = getattr(parent, "_paddle_cache_path", None)
    cache = cache_fn() if callable(cache_fn) else None
    ProofreadingVisualVerificationDialog(
        review_window, project_root=project.root, page=page, ocr_cache=cache
    )
