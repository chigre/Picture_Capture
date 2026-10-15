"""Read-only, viewport-virtualized page-index thumbnails.

The original Treeview iid is the page's project index.  The native #0 tree
column owns each preview, so sorting/moving rows cannot detach its image.
Only rows in the viewport hold Tk PhotoImages; all project pages are eligible
for lazy preview without loading every scan (or writing scan-derived files).
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

from PIL import Image, ImageTk


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
                settings.to_json(Path(project.root) / "settings.json")
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
        if hasattr(self.app, "_schedule_page_cell_overlay_refresh"):
            self.app._schedule_page_cell_overlay_refresh()

    def _clear_images(self) -> None:
        self._generation += 1
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
            visible = set(self.app._visible_page_list_iids())
            for iid in set(self._attached) - visible:
                if self.tree.exists(iid):
                    self.tree.item(iid, image="")
                self._attached.pop(iid, None)
            rendered = 0
            for iid in self.app._visible_page_list_iids():
                try:
                    index = int(iid)
                    path = Path(project.images[index])
                    stat = path.stat()
                    key = (str(path), stat.st_mtime_ns, stat.st_size, self.width)
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

    def _make_photo(self, path: Path) -> ImageTk.PhotoImage:
        bounds = preview_bounds(self.width)
        with Image.open(path) as source:
            # JPEG decoder downsampling prevents decoding full-resolution scans
            # when the format supports draft mode.
            source.draft("RGB", bounds)
            preview = source.copy()
        preview.thumbnail(bounds, Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(preview, master=self.tree)


__all__ = [
    "PageThumbnailController", "normalized_thumbnail_width", "preview_bounds",
    "DEFAULT_THUMBNAIL_WIDTH", "MIN_THUMBNAIL_WIDTH",
    "MAX_THUMBNAIL_WIDTH", "THUMBNAIL_STEP",
]
