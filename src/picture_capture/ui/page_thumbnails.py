"""Read-only, viewport-virtualized page-index thumbnails.

The original Treeview iid is the page's project index.  The native #0 tree
column owns each preview, so sorting/moving rows cannot detach its image.
Only rows in the viewport hold Tk PhotoImages. All pages are progressively
cached as derived PNGs within the project's _PictureCapture working directory.
The cache is disposable, never a modification to original scans.
"""
from __future__ import annotations

from collections import OrderedDict
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
from typing import Any

from PIL import Image, ImageTk

from picture_capture.project_storage import settings_path
from picture_capture.page_thumbnail_cache import thumbnail_name_map
from picture_capture.page_thumbnail_tasks import ThumbnailTasks


DEFAULT_THUMBNAIL_WIDTH = 80
MIN_THUMBNAIL_WIDTH = 40
MAX_THUMBNAIL_WIDTH = 120
THUMBNAIL_STEP = 10
PHOTO_CACHE_LIMIT = 96


def normalized_thumbnail_width(value: object) -> int:
    """Normalize old, corrupted or manually edited settings safely."""
    try:
        width = int(value)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_THUMBNAIL_WIDTH
    return max(MIN_THUMBNAIL_WIDTH, min(MAX_THUMBNAIL_WIDTH, width))


def preview_bounds(width: int) -> tuple[int, int]:
    """Keep the full source aspect ratio inside this bounding rectangle."""
    width = normalized_thumbnail_width(width)
    # Cache masters have a strict 120px longest side; avoid oversized UI rows.
    return width, min(120, round(width * 1.4))


def visible_page_iids(tree: ttk.Treeview) -> list[str]:
    """Report the rows ACTUALLY on screen, including after far-away scrolls.

    The old next/bbox walker stopped at the first empty bbox. Tk/ttk returns
    empty bboxes for rows it has not laid out after scrolling or resizing,
    so the old walk could remain fixed to the first visible batch. Sampling
    actual widget coordinates avoids that early-stop failure after scrolling,
    reordering, or row-height changes. Cost depends on viewport height, not
    on the total number of pages in the project.
    """
    try:
        height = max(1, int(tree.winfo_height()))
        # 8 pixels is below the smallest supported ttk row height. Probe the
        # final pixel too to include a partially visible bottom row.
        seen: set[str] = set()
        visible: list[str] = []
        for y in list(range(0, height, 8)) + [height - 1]:
            iid = str(tree.identify_row(y) or "")
            if iid and iid not in seen:
                seen.add(iid)
                visible.append(iid)
        return visible
    except (tk.TclError, ValueError, TypeError):
        return []



def prioritized_page_indices(
    count: int, current_index: int, displayed_iids: list[str] | tuple[str, ...],
) -> list[int]:
    """First the viewed page, then the rows below it in the current sort.

    Pages above the active row follow afterward. No page is omitted even if
    the Treeview is still being built, is filtered, or contains invalid iids.
    """
    ordered: list[int] = []
    seen: set[int] = set()
    for raw in displayed_iids:
        try:
            index = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= index < count and index not in seen:
            ordered.append(index)
            seen.add(index)
    ordered.extend(index for index in range(count) if index not in seen)
    if not ordered:
        return []
    pivot = ordered.index(current_index) if current_index in seen or current_index in ordered else 0
    return ordered[pivot:] + ordered[:pivot]


class PageThumbnailController:
    """Small Tk-only presentation controller; never modifies page content."""

    def __init__(self, app: Any, tree: ttk.Treeview, host: ttk.Frame) -> None:
        self.app = app
        self.tree = tree
        self.width = DEFAULT_THUMBNAIL_WIDTH
        self.enabled_var = tk.BooleanVar(master=tree, value=False)
        self._photos: OrderedDict[tuple, ImageTk.PhotoImage] = OrderedDict()
        self._attached: dict[str, tuple] = {}
        self._refresh_job: str | None = None
        self._generation = 0
        self._tasks = ThumbnailTasks(workers=2)
        self._worker_pending: dict[int, tuple[int, tuple]] = {}
        self._worker_failures: dict[int, tuple] = {}
        self._poll_job: str | None = None
        self._visible_order: list[str] = []
        self._warm_job: str | None = None
        self._warm_cursor = 0
        self._warm_project_key: tuple | None = None
        self._warm_priority_key: tuple | None = None
        self._warm_order: list[int] = []
        self._warm_done: set[int] = set()
        self._cache_project_key: tuple | None = None
        self._cache_names: dict[str, str] = {}
        self._empty_view_retries = 0
        self.row = ttk.Frame(host, style="PC.Sidebar.TFrame")
        self.row.pack(fill="x", pady=(2, 3))
        self.toggle = ttk.Checkbutton(
            self.row, text="缩略图", variable=self.enabled_var,
            command=self._toggle,
        )
        self.toggle.pack(side="left")
        self.buttons: list[ttk.Button] = []
        for title, callback in (
            ("−", lambda: self._resize(-THUMBNAIL_STEP)),
            ("默", lambda: self._resize_to(DEFAULT_THUMBNAIL_WIDTH)),
            ("+", lambda: self._resize(THUMBNAIL_STEP)),
        ):
            button = ttk.Button(
                self.row, text=title, width=3, command=callback,
                style="PC.PageNav.TButton",
            )
            button.pack(side="left", padx=(2, 0))
            self.buttons.append(button)
        self.tree.heading("#0", text="缩略图", anchor="center")
        # Close on the Tk thread; no worker has a reference to Tk widgets.
        self.tree.bind("<Destroy>", self._on_tree_destroy, add="+")
        self.load_preferences()

    def _allowed(self) -> bool:
        return getattr(self.app, "workspace_mode", "正常") in {"正常", "最大"}

    def _visible_enabled(self) -> bool:
        return self._allowed() and bool(self.enabled_var.get())

    def _save(self, key: str, value: object) -> bool:
        settings = self.app.settings
        previous = getattr(settings, key)
        setattr(settings, key, value)
        project = getattr(self.app, "project", None)
        if project is not None:
            try:
                destination = settings_path(project.root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temp_name = tempfile.mkstemp(
                    prefix=".thumbnail-settings-", suffix=".tmp",
                    dir=str(destination.parent),
                )
                os.close(descriptor)
                try:
                    settings.to_json(Path(temp_name))
                    os.replace(temp_name, destination)
                finally:
                    Path(temp_name).unlink(missing_ok=True)
            except (OSError, ValueError, TypeError) as exc:
                setattr(settings, key, previous)
                status = getattr(self.app, "status_var", None)
                if status is not None:
                    status.set(f"缩略图设置保存失败，已恢复原设置：{exc}")
                return False
        return True

    def _toggle(self) -> None:
        desired = bool(self.enabled_var.get())
        if not self._allowed() or not self._save("page_list_show_thumbnails", desired):
            self.enabled_var.set(bool(self.app.settings.page_list_show_thumbnails))
        self.apply()

    def _resize(self, delta: int) -> None:
        self._resize_to(self.width + delta)

    def _resize_to(self, width: int) -> None:
        if not self._visible_enabled():
            return
        width = normalized_thumbnail_width(width)
        if width == self.width:
            return
        if not self._save("page_list_thumbnail_size", width):
            return
        self.width = width
        self._clear_images()
        self.apply()

    def load_preferences(self) -> None:
        """Reload independent project preferences, not previous-project state."""
        self._clear_images()
        self._warm_cursor = 0
        self._warm_project_key = None
        self._warm_priority_key = None
        self._warm_order = []
        self._warm_done = set()
        self._cache_project_key = None
        self._cache_names = {}
        settings = self.app.settings
        self.enabled_var.set(bool(getattr(settings, "page_list_show_thumbnails", False)))
        self.width = normalized_thumbnail_width(
            getattr(settings, "page_list_thumbnail_size", DEFAULT_THUMBNAIL_WIDTH),
        )
        self.apply()

    def on_mode_change(self) -> None:
        """Disable the whole control in 极简/紧凑; preserve saved preference."""
        self.apply()

    def apply(self) -> None:
        active = self._visible_enabled()
        allowed = self._allowed()
        self.toggle.configure(state="normal" if allowed else "disabled")
        for button in self.buttons:
            button.configure(
                state="normal" if active and (
                    button is self.buttons[1] or (
                        button is self.buttons[0] and self.width > MIN_THUMBNAIL_WIDTH
                    ) or (
                        button is self.buttons[2] and self.width < MAX_THUMBNAIL_WIDTH
                    )
                ) else "disabled",
            )
        self.tree.configure(show="tree headings" if active else "headings")
        self.tree.column(
            "#0", width=self.width + 26, minwidth=self.width + 26,
            stretch=False, anchor="center",
        )
        height = preview_bounds(self.width)[1] + 8 if active else 26
        ttk.Style(self.tree).configure("PC.Treeview", rowheight=height)
        if not active:
            self._clear_images()
        else:
            self.request_visible()
            self._schedule_warm_cache()
        if hasattr(self.app, "_schedule_page_cell_overlay_refresh"):
            self.app._schedule_page_cell_overlay_refresh()

    def _on_tree_destroy(self, event: tk.Event) -> None:
        if event.widget is self.tree:
            self.close()

    def close(self) -> None:
        """Stop scheduling work without waiting for large scan decoding."""
        self._clear_images()
        self._tasks.shutdown()

    def _clear_images(self) -> None:
        """Invalidate Tk-only images and ignore obsolete async completions."""
        self._generation += 1
        self._empty_view_retries = 0
        self._tasks.cancel_pending()
        self._worker_pending.clear()
        self._worker_failures.clear()
        for name in ("_refresh_job", "_poll_job"):
            job = getattr(self, name, None)
            if job is not None:
                try:
                    self.app.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, name, None)
        for iid in tuple(self._attached):
            try:
                if self.tree.exists(iid):
                    self.tree.item(iid, image="", text="")
            except tk.TclError:
                pass
        self._attached.clear()
        self._photos.clear()
        self._visible_order = []

    @staticmethod
    def _source_token(path: Path) -> tuple:
        """Fast identity check on Tk thread: no source image decode or hashing."""
        stat = path.stat()
        return (
            str(path.resolve()), int(stat.st_dev), int(stat.st_ino),
            int(stat.st_size), int(stat.st_mtime_ns), int(stat.st_ctime_ns),
        )

    def _cache_names_for_project(self) -> dict[str, str]:
        """Collision-safe filenames computed once per image-set identity."""
        project = getattr(self.app, "project", None)
        if project is None:
            return {}
        key = (str(project.root), id(project), len(project.images))
        if key != self._cache_project_key:
            self._cache_names = thumbnail_name_map(project.images)
            self._cache_project_key = key
        return self._cache_names

    def _current_project_id(self) -> tuple | None:
        project = getattr(self.app, "project", None)
        if project is None:
            return None
        return (str(project.root), id(project), len(project.images))

    def _view_key(self, index: int) -> tuple | None:
        project = getattr(self.app, "project", None)
        if project is None or not 0 <= index < len(project.images):
            return None
        try:
            return (self._current_project_id(), self._source_token(Path(project.images[index])), self.width)
        except (OSError, TypeError, ValueError):
            return None

    def request_visible(self) -> None:
        """Coalesce scrolling; only cheap stat/Tk operations on main thread."""
        if not self._visible_enabled() or self._refresh_job is not None:
            return
        try:
            self._refresh_job = self.app.after_idle(self._render_visible)
        except tk.TclError:
            self._refresh_job = None

    def _render_visible(self) -> None:
        """Attach already-decoded PhotoImages; enqueue misses without blocking."""
        self._refresh_job = None
        project = getattr(self.app, "project", None)
        if project is None or not self._visible_enabled():
            return
        try:
            rows = [str(iid) for iid in self.app._visible_page_list_iids()]
            if not rows and self.tree.get_children("") and self._empty_view_retries < 12:
                self._empty_view_retries += 1
                self._refresh_job = self.app.after(100, self._render_visible)
                return
            self._empty_view_retries = 0
            if rows != self._visible_order:
                self._warm_priority_key = None
            self._visible_order = rows
            visible = set(rows)
            for iid in set(self._attached) - visible:
                if self.tree.exists(iid):
                    self.tree.item(iid, image="")
                self._attached.pop(iid, None)
            for iid in rows:
                try:
                    index = int(iid)
                except (ValueError, TypeError):
                    continue
                key = self._view_key(index)
                if key is None:
                    if self.tree.exists(iid):
                        self.tree.item(iid, image="", text="×")
                    self._attached.pop(iid, None)
                    continue
                if self._attached.get(iid) == key:
                    continue
                photo = self._photos.get(key)
                if photo is not None and self.tree.exists(iid):
                    self._photos.move_to_end(key)
                    self.tree.item(iid, image=photo, text="")
                    self._attached[iid] = key
                else:
                    if self.tree.exists(iid):
                        self.tree.item(iid, image="", text="…")
                    self._attached.pop(iid, None)
            self._dispatch_jobs()
        except tk.TclError:
            return

    def _warm_priority(self, project: Any) -> tuple:
        try:
            current = int(getattr(self.app, "current_index", 0))
        except (TypeError, ValueError):
            current = 0
        if not 0 <= current < len(project.images):
            current = 0
        return (
            current, getattr(self.app, "_page_list_sort_column", None),
            bool(getattr(self.app, "_page_list_sort_descending", False)),
            len(project.images),
        )

    def _rebuild_warm_order(self, project: Any) -> None:
        priority = self._warm_priority(project)
        if priority == self._warm_priority_key:
            return
        try:
            displayed = self.tree.get_children("")
        except (AttributeError, tk.TclError):
            displayed = tuple(str(i) for i in range(len(project.images)))
        ordered = prioritized_page_indices(len(project.images), priority[0], displayed)
        self._warm_order = [index for index in ordered if index not in self._warm_done]
        self._warm_cursor = 0
        self._warm_priority_key = priority

    def _schedule_warm_cache(self) -> None:
        """Keep cache-wide precomputation running in background, not Tk."""
        if self._visible_enabled():
            self._dispatch_jobs()

    def _candidate_indices(self, project: Any) -> list[int]:
        """Visible/current page first; below in sorted index, then all others."""
        self._rebuild_warm_order(project)
        visible = list(self._visible_order)
        current = str(self._warm_priority(project)[0])
        if current in visible:
            pivot = visible.index(current)
            visible = visible[pivot:] + visible[:pivot]
        top = []
        for iid in visible:
            try:
                index = int(iid)
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(project.images) and index not in top:
                top.append(index)
        # The full-view current page takes precedence even if Treeview geometry
        # has not yet mapped it on first project open.
        current_index = self._warm_priority(project)[0]
        if current_index not in top and current_index not in self._warm_done:
            top.insert(0, current_index)
        return top + [i for i in self._warm_order if i not in top]

    def _dispatch_jobs(self) -> None:
        project = getattr(self.app, "project", None)
        if project is None or not self._visible_enabled():
            return
        project_id = self._current_project_id()
        if project_id != self._warm_project_key:
            self._warm_project_key = project_id
            self._warm_priority_key = None
            self._warm_done = set()
        names = self._cache_names_for_project()
        for index in self._candidate_indices(project):
            if self._tasks.active >= 2:
                break
            key = self._view_key(index)
            if key is None:
                self._warm_done.add(index)
                continue
            iid = str(index)
            if self._attached.get(iid) == key and index in self._warm_done:
                continue
            if index in self._worker_pending:
                continue
            if self._worker_failures.get(index) == key:
                continue
            if index in self._warm_done and iid not in self._visible_order:
                continue
            # Reuse Tk photo if a scrolled-out page becomes visible again.
            photo = self._photos.get(key)
            if photo is not None and iid in self._visible_order:
                self._photos.move_to_end(key)
                if self.tree.exists(iid):
                    self.tree.item(iid, image=photo, text="")
                    self._attached[iid] = key
                continue
            token = (self._generation, key)
            ticket = self._tasks.submit(
                index, token, Path(project.root),
                Path(project.images[index]), names,
            )
            if ticket is not None:
                self._worker_pending[index] = (ticket, token)
        self._schedule_poll()

    def _schedule_poll(self) -> None:
        if self._poll_job is not None or not self._tasks.active:
            return
        try:
            self._poll_job = self.app.after(50, self._collect_results)
        except tk.TclError:
            self._poll_job = None

    def _collect_results(self) -> None:
        """Only Tk event loop touches Treeview and ImageTk.PhotoImage."""
        self._poll_job = None
        for result in self._tasks.collect():
            pending = self._worker_pending.get(result.page_index)
            if pending is not None and pending[0] == result.ticket:
                del self._worker_pending[result.page_index]
            generation, key = result.identity
            if (generation != self._generation or
                not self._visible_enabled() or
                self._view_key(result.page_index) != key):
                continue
            if result.error:
                # Failed scans remain failed until source identity changes,
                # resize/reopen, or the user explicitly re-enables thumbnails.
                self._worker_failures[result.page_index] = key
                self._warm_done.add(result.page_index)
                iid = str(result.page_index)
                if iid in self._visible_order and self.tree.exists(iid):
                    self.tree.item(iid, image="", text="×")
                continue
            self._warm_done.add(result.page_index)
            iid = str(result.page_index)
            if iid not in self._visible_order or not self.tree.exists(iid):
                continue
            try:
                image = result.image.copy()
                image.thumbnail(preview_bounds(self.width), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image, master=self.tree)
                self._photos[key] = photo
                self._photos.move_to_end(key)
                self.tree.item(iid, image=photo, text="")
                self._attached[iid] = key
                while len(self._photos) > PHOTO_CACHE_LIMIT:
                    self._photos.popitem(last=False)
            except (OSError, ValueError, tk.TclError):
                continue
        if self._visible_enabled():
            self._dispatch_jobs()

    def project_rows_ready(self) -> None:
        self._empty_view_retries = 0
        self._warm_priority_key = None
        self._visible_order = []
        self.request_visible()
        self._schedule_warm_cache()


__all__ = [
    "PageThumbnailController", "prioritized_page_indices", "visible_page_iids",
    "normalized_thumbnail_width", "preview_bounds",
    "DEFAULT_THUMBNAIL_WIDTH", "MIN_THUMBNAIL_WIDTH",
    "MAX_THUMBNAIL_WIDTH", "THUMBNAIL_STEP",
]
