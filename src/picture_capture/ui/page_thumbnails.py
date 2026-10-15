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
from picture_capture.page_thumbnail_cache import (
    display_page_thumbnail, get_page_thumbnail, source_fingerprint,
    thumbnail_name_map,
)


DEFAULT_THUMBNAIL_WIDTH = 80
MIN_THUMBNAIL_WIDTH = 40
MAX_THUMBNAIL_WIDTH = 160
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
    return width, round(width * 1.4)


def visible_page_iids(tree: ttk.Treeview) -> list[str]:
    """Find viewport rows without scanning all items or mistaking heading for row.

    Used by both line-status overlays and thumbnail display. The image index
    may have very tall rows, so locate the first visible item by y coordinate,
    then walk stable Treeview item links until the viewport ends.
    """
    try:
        height = max(1, int(tree.winfo_height()))
        iid = ""
        # The heading height and row heights vary across ttk themes and DPI.
        # Probe the viewport rather than assuming 20/40px always hit a row.
        for probe_y in range(1, height, 12):
            iid = tree.identify_row(probe_y)
            if iid:
                break
        result: list[str] = []
        while iid:
            bbox = tree.bbox(iid)
            if not bbox:
                break
            _x, y, _width, row_height = bbox
            if y >= height:
                break
            if y + row_height > 0:
                result.append(str(iid))
            iid = tree.next(iid)
        return result
    except tk.TclError:
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

    def _clear_images(self) -> None:
        self._generation += 1
        self._empty_view_retries = 0
        if self._warm_job is not None:
            try:
                self.app.after_cancel(self._warm_job)
            except tk.TclError:
                pass
            self._warm_job = None
        if self._refresh_job is not None:
            try:
                self.app.after_cancel(self._refresh_job)
            except tk.TclError:
                pass
            self._refresh_job = None
        for iid in self._attached:
            try:
                if self.tree.exists(iid):
                    self.tree.item(iid, image="")
            except tk.TclError:
                pass
        self._attached.clear()
        self._photos.clear()

    def request_visible(self) -> None:
        """Coalesce scrolls and rapid sorts; decode on Tk's idle loop only."""
        if not self._visible_enabled() or self._refresh_job is not None:
            return
        try:
            self._refresh_job = self.app.after_idle(self._render_visible)
        except tk.TclError:
            self._refresh_job = None

    def _render_visible(self) -> None:
        self._refresh_job = None
        project = getattr(self.app, "project", None)
        if project is None or not self._visible_enabled():
            return
        try:
            visible_rows = self.app._visible_page_list_iids()
            visible = set(visible_rows)
            if not visible and self.tree.get_children("") and self._empty_view_retries < 12:
                # On project open, Treeview can be populated before it is mapped
                # or sized. A one-shot after_idle then leaves previews blank.
                self._empty_view_retries += 1
                self._refresh_job = self.app.after(100, self._render_visible)
                return
            self._empty_view_retries = 0
            for iid in set(self._attached) - visible:
                if self.tree.exists(iid):
                    self.tree.item(iid, image="")
                self._attached.pop(iid, None)
            rendered = 0
            # When the browsed page is visible, render it first, then the
            # thumbnails below it; afterwards fill rows above it.
            browsed = str(getattr(self.app, "current_index", -1))
            if browsed in visible_rows:
                pivot = visible_rows.index(browsed)
                ordered_visible = visible_rows[pivot:] + visible_rows[:pivot]
            else:
                ordered_visible = visible_rows
            for iid in ordered_visible:
                try:
                    index = int(iid)
                    path = Path(project.images[index])
                    key = (str(path), source_fingerprint(path), self.width)
                except (ValueError, IndexError, OSError, TypeError):
                    continue
                if self._attached.get(iid) == key:
                    continue
                photo = self._photos.get(key)
                if photo is None:
                    try:
                        photo = self._make_photo(path)
                    except (OSError, ValueError, SyntaxError):
                        # A damaged or missing scan leaves only this thumbnail
                        # blank; neither project data nor the page index changes.
                        continue
                    self._photos[key] = photo
                self._photos.move_to_end(key)
                self.tree.item(iid, image=photo)
                self._attached[iid] = key
                rendered += 1
                while len(self._photos) > PHOTO_CACHE_LIMIT:
                    self._photos.popitem(last=False)
                if rendered >= 2:
                    break
            if rendered:
                # Fill additional visible rows without long synchronous stalls.
                self._refresh_job = self.app.after(15, self._render_visible)
        except tk.TclError:
            pass

    def _cache_names_for_project(self) -> dict[str, str]:
        """Build the collision-proof name plan once, not for every page."""
        project = getattr(self.app, "project", None)
        if project is None:
            return {}
        key = (str(project.root), id(project), len(project.images))
        if key != getattr(self, "_cache_project_key", None):
            self._cache_names = thumbnail_name_map(project.images)
            self._cache_project_key = key
        return self._cache_names

    def _make_photo(self, path: Path) -> ImageTk.PhotoImage:
        # A single cached master supports every [-]/[默]/[+] width.
        preview = display_page_thumbnail(
            self.app.project.root, path, self.width, self._cache_names_for_project(),
        )
        return ImageTk.PhotoImage(preview, master=self.tree)

    def project_rows_ready(self) -> None:
        """Called after the page Treeview has been populated for this project."""
        self._empty_view_retries = 0
        self._warm_priority_key = None  # Treeview now contains actual sorted rows.
        if self._visible_enabled():
            try:
                self.tree.xview_moveto(0.0)
            except tk.TclError:
                pass
        self.request_visible()
        self._schedule_warm_cache()

    def _warm_priority(self, project: Any) -> tuple:
        """Fast key used to reprioritize on current-page/sort changes."""
        current = getattr(self.app, "current_index", 0)
        try:
            current = int(current)
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
        if priority == getattr(self, "_warm_priority_key", None):
            return
        try:
            displayed = self.tree.get_children("")
        except (AttributeError, tk.TclError):
            displayed = tuple(str(i) for i in range(len(project.images)))
        ordered = prioritized_page_indices(len(project.images), priority[0], displayed)
        done = getattr(self, "_warm_done", set())
        self._warm_order = [index for index in ordered if index not in done]
        self._warm_cursor = 0
        self._warm_priority_key = priority

    def _schedule_warm_cache(self) -> None:
        """Generate current page, followed by pages below it, then the rest."""
        if not self._visible_enabled() or self._warm_job is not None:
            return
        project = getattr(self.app, "project", None)
        if project is None:
            return
        project_key = (str(project.root), id(project))
        if project_key != self._warm_project_key:
            self._warm_project_key = project_key
            self._warm_priority_key = None
            self._warm_done = set()
        self._rebuild_warm_order(project)
        if self._warm_cursor >= len(self._warm_order):
            return
        try:
            self._warm_job = self.app.after(90, self._warm_step)
        except tk.TclError:
            self._warm_job = None

    def _warm_step(self) -> None:
        self._warm_job = None
        if not self._visible_enabled():
            return
        project = getattr(self.app, "project", None)
        if project is None or (str(project.root), id(project)) != self._warm_project_key:
            return
        # A navigation jump can happen mid-generation. Process its nearby
        # ungenerated pages next without losing earlier completed work.
        self._rebuild_warm_order(project)
        if self._warm_cursor >= len(self._warm_order):
            return
        index = self._warm_order[self._warm_cursor]
        self._warm_cursor += 1
        image = Path(project.images[index])
        try:
            get_page_thumbnail(project.root, image, self._cache_names_for_project())
        except (OSError, ValueError, SyntaxError):
            # A corrupt/missing scan never blocks the rest of the project.
            pass
        self._warm_done.add(index)
        self._schedule_warm_cache()


__all__ = [
    "PageThumbnailController", "prioritized_page_indices", "visible_page_iids",
    "normalized_thumbnail_width", "preview_bounds",
    "DEFAULT_THUMBNAIL_WIDTH", "MIN_THUMBNAIL_WIDTH",
    "MAX_THUMBNAIL_WIDTH", "THUMBNAIL_STEP",
]
