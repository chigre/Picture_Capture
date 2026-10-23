"""PictureCaptureApp page_index actions and state: physical owner.

Original user-visible callbacks remain on the Tk shell with identical signatures.
Dependencies bind at each call, without importing heavyweight app.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk
    from pathlib import Path

@dataclass(frozen=True)
class PageIndexDeps:
    """Live collaborators from the compatibility shell."""
    tk: object
    ttk: object
    font: object
    simpledialog: object
    Image: object
    Path: object
    _sorted_page_list_rows: object
    _fill_status_cell_style: object
    settings_path: object
    read_page_sections: object
    write_page_sections: object
    PageSection: object
    LayoutTransform: object
    normalize_page_rgb: object
    page_template_analysis_image: object
    derive_geometry: object
    effective_page_settings: object
    read_pdic: object
    pdic_path: object
    read_ppp: object


def _resize_sidebar_content(self, deps: PageIndexDeps, self, event: tk.Event | None = None) -> None:
    """Fill unused sidebar height while retaining scrolling when necessary."""
    tk = deps.tk
    canvas = self.__dict__.get("sidebar_canvas")
    sidebar = self.__dict__.get("sidebar")
    window = self.__dict__.get("_sidebar_window")
    if canvas is None or sidebar is None or window is None:
        return
    try:
        viewport_width = max(1, canvas.winfo_width())
        viewport_height = max(1, canvas.winfo_height())
        requested_height = max(1, sidebar.winfo_reqheight())
        canvas.itemconfigure(
            window,
            width=viewport_width,
            height=max(viewport_height, requested_height),
        )
        canvas.configure(scrollregion=canvas.bbox("all"))
    except tk.TclError:
        return


def _apply_page_list_display_columns(self, deps: PageIndexDeps, self, *, save: bool = True) -> None:
    """Apply optional Treeview columns while keeping 页面 permanently visible."""
    settings_path = deps.settings_path
    if not hasattr(self, "page_list"):
        return
    columns = ["bookmark", "page", "lined"]

    if getattr(self, "_page_column_vars", {}).get("illustrations") is None or self._page_column_vars["illustrations"].get():
        columns.append("illustrations")
    columns.append("section")
    if getattr(self, "_page_column_vars", {}).get("fill_status") is None or self._page_column_vars["fill_status"].get():
        columns.append("fill_status")
    self.page_list.configure(displaycolumns=tuple(columns))
    self.after_idle(self._fit_page_list_columns)
    if hasattr(self, "settings"):
        self.settings.page_list_show_lined = True
        self.settings.page_list_show_fill_status = "fill_status" in columns
        self.settings.page_list_show_illustrations = "illustrations" in columns
        if save and self.project is not None:
            try:
                self.settings.to_json(settings_path(self.project.root))
            except Exception:
                pass
    self._schedule_page_cell_overlay_refresh()


def _page_list_configured(self, deps: PageIndexDeps, self, _event=None) -> None:
    """Keep visible page-list columns filling the full Treeview width."""
    self._fit_page_list_columns()
    self._schedule_page_cell_overlay_refresh()


def _fit_page_list_columns(self, deps: PageIndexDeps, self) -> None:
    tk = deps.tk
    font = deps.font
    if not hasattr(self, "page_list"):
        return
    try:
        raw = self.page_list.cget("displaycolumns")
        visible = tuple(self.tk.splitlist(raw))
        if not visible or visible == ("#all",):
            visible = tuple(self.tk.splitlist(self.page_list.cget("columns")))
        if not visible:
            return
        available = max(1, int(self.page_list.winfo_width()) - 2)
    except (tk.TclError, ValueError):
        return

    header_font = font.nametofont("TkHeadingFont")
    body_font = font.nametofont("TkDefaultFont")
    # Preserve content-sized page columns and horizontal scrolling.
    page_names = (
        page.stem for page in getattr(self.project, "images", ())
    ) if self.project else ()
    page_width = max(
        (body_font.measure(name) for name in page_names), default=0
    ) + 10
    base = {
        "bookmark": 25, "page": max(52, page_width),
        "section": 36, "lined": 36,
        "illustrations": 36, "fill_status": 68,
    }
    for column in visible:
        label = self._page_list_heading_labels.get(column, column)
        width = max(base.get(column, 60), header_font.measure(label) + 6)
        self.page_list.column(column, width=width, anchor="center", stretch=False)
    self._schedule_page_cell_overlay_refresh()


def _hide_page_list_section_heading_hint(self, deps: PageIndexDeps, self, _event=None) -> None:
    tk = deps.tk
    popup = getattr(self, "_page_list_section_heading_hint", None)
    if popup is not None:
        try:
            popup.destroy()
        except tk.TclError:
            pass
    self._page_list_section_heading_hint = None


def _page_list_section_heading_motion(self, deps: PageIndexDeps, self, event: tk.Event) -> None:
    """Show the SECTION edit hint only while the pointer is over its heading."""
    tk = deps.tk
    ttk = deps.ttk
    try:
        over_section = (
            self.page_list.identify_region(event.x, event.y) == "heading"
            and self._page_list_column_at(event.x) == "section"
        )
    except tk.TclError:
        over_section = False
    if not over_section:
        self._hide_page_list_section_heading_hint()
        return
    if getattr(self, "_page_list_section_heading_hint", None) is not None:
        return
    tip = tk.Toplevel(self.page_list)
    tip.wm_overrideredirect(True)
    tip.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 18}")
    ttk.Label(
        tip,
        text="双击进入Section编辑模式",
        padding=(7, 4),
        relief="solid",
    ).pack()
    self._page_list_section_heading_hint = tip


def _page_list_right_click(self, deps: PageIndexDeps, self, event: tk.Event) -> str | None:
    """Right-click a heading to choose which optional list columns are visible."""
    tk = deps.tk
    if not hasattr(self, "page_list") or self.page_list.identify_region(event.x, event.y) != "heading":
        return None
    menu = tk.Menu(self, tearoff=False)
    self._apply_current_appearance(menu)
    bookmark_var = tk.BooleanVar(value=True)
    menu.add_checkbutton(label="●", variable=bookmark_var, state="disabled")
    page_var = tk.BooleanVar(value=True)
    menu.add_checkbutton(label="页面", variable=page_var, state="disabled")
    section_var = tk.BooleanVar(value=True)
    menu.add_checkbutton(label="区块", variable=section_var, state="disabled")
    menu.add_checkbutton(label="画线", state="disabled")
    menu.add_checkbutton(
        label="插图", variable=self._page_column_vars["illustrations"],
        command=lambda: self._apply_page_list_display_columns(save=True),
    )
    menu.add_checkbutton(
        label="填充状态", variable=self._page_column_vars["fill_status"],
        command=lambda: self._apply_page_list_display_columns(save=True),
    )
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        try: menu.grab_release()
        except tk.TclError: pass
    return "break"


def _schedule_page_cell_overlay_refresh(self, deps: PageIndexDeps, self) -> None:
    """Coalesce visible table colors, cell borders and thumbnails on idle."""
    if not hasattr(self, "page_list"):
        return
    if self._page_overlay_refresh_job is not None:
        return

    def run() -> None:
        self._page_overlay_refresh_job = None
        self._refresh_lined_cell_overlays()
        grid = self.__dict__.get("_page_index_grid")
        if grid is not None:
            grid.repaint(dark="dark" in str(getattr(self, "appearance_mode", "")).lower())
        previews = self.__dict__.get("_page_thumbnails")
        if previews is not None:
            previews.request_visible()

    self._page_overlay_refresh_job = self.after_idle(run)


def _page_list_scroll(self, deps: PageIndexDeps, self, *args) -> None:
    self.page_list.yview(*args)
    self._schedule_page_cell_overlay_refresh()


def _page_list_hscroll(self, deps: PageIndexDeps, self, *args) -> None:
    self.page_list.xview(*args)
    self._schedule_page_cell_overlay_refresh()


def _page_list_yscroll(self, deps: PageIndexDeps, self, first: str, last: str) -> None:
    if hasattr(self, "page_scroll"):
        self.page_scroll.set(first, last)
    self._schedule_page_cell_overlay_refresh()


def _update_page_list_sort_headings(self, deps: PageIndexDeps, self) -> None:
    if not hasattr(self, "page_list"):
        return
    labels = getattr(self, "_page_list_heading_labels", {
        "bookmark": "🔖", "page": "页面", "section": "区块",
        "lined": "画线", "fill_status": "填充状态", "illustrations": "插图",
    })
    active = self._page_list_sort_column
    arrow = " ▼" if self._page_list_sort_descending else " ▲"
    for column, label in labels.items():
        self.page_list.heading(column, text=label + (arrow if column == active else ""))


def _apply_page_list_sort(self, deps: PageIndexDeps, self, *, ensure_current_visible: bool = False) -> None:
    _sorted_page_list_rows = deps._sorted_page_list_rows
    if not hasattr(self, "page_list") or not self._page_list_sort_column:
        return
    rows = [(iid, tuple(self.page_list.item(iid, "values"))) for iid in self.page_list.get_children("")]
    ordered = _sorted_page_list_rows(
        rows, self._page_list_sort_column, self._page_list_sort_descending
    )
    for position, (iid, _values) in enumerate(ordered):
        self.page_list.move(iid, "", position)
    self._update_page_list_sort_headings()
    self._schedule_page_cell_overlay_refresh()
    # Background metadata refreshes may re-sort the list many times.  Never
    # force the viewport back to the selected row in that path: doing so
    # makes mouse-wheel browsing snap back to the page the user clicked.
    # Only an explicit header sort asks to reveal the current page again.
    if ensure_current_visible and self.current_index >= 0:
        iid = str(self.current_index)
        if self.page_list.exists(iid):
            self.page_list.see(iid)
            self._center_page_list_iid(iid)


def _schedule_page_list_resort(self, deps: PageIndexDeps, self) -> None:
    if not self._page_list_sort_column or not hasattr(self, "page_list"):
        return
    if self._page_list_sort_job is not None:
        return
    def run() -> None:
        self._page_list_sort_job = None
        self._apply_page_list_sort(ensure_current_visible=False)
    self._page_list_sort_job = self.after(80, run)


def _sort_page_list(self, deps: PageIndexDeps, self, column: str) -> None:
    tk = deps.tk
    if column not in {"bookmark", "page", "section", "lined", "fill_status", "illustrations"}:
        return
    if self._page_list_sort_column == column:
        self._page_list_sort_descending = not self._page_list_sort_descending
    else:
        self._page_list_sort_column = column
        self._page_list_sort_descending = False
    if self._page_list_sort_job is not None:
        try:
            self.after_cancel(self._page_list_sort_job)
        except tk.TclError:
            pass
        self._page_list_sort_job = None
    self._apply_page_list_sort(ensure_current_visible=True)


def _page_list_column_at(self, deps: PageIndexDeps, self, x: int) -> str | None:
    """Return the logical Treeview column under a display-space X coordinate."""
    tk = deps.tk
    token = str(self.page_list.identify_column(x) or "")
    try:
        display_index = int(token.lstrip("#")) - 1
    except ValueError:
        return None
    raw = self.page_list.cget("displaycolumns")
    display = tuple(self.tk.splitlist(raw))
    if not display or display == ("#all",):
        display = tuple(self.tk.splitlist(self.page_list.cget("columns")))
    return str(display[display_index]) if 0 <= display_index < len(display) else None


def _page_section_count_text(self, deps: PageIndexDeps, self, index: int) -> str:
    read_page_sections = deps.read_page_sections
    if not self.project or not (0 <= index < len(self.project.images)):
        return "0"
    try:
        return str(len(read_page_sections(self.project.images[index])))
    except (TypeError, ValueError, OSError, AttributeError):
        return "0"


def _set_page_section_count(self, deps: PageIndexDeps, self, index: int, count: int) -> None:
    """Set a page's explicit SECTION count, preserving bounds when count is unchanged."""
    Image = deps.Image
    read_page_sections = deps.read_page_sections
    write_page_sections = deps.write_page_sections
    PageSection = deps.PageSection
    LayoutTransform = deps.LayoutTransform
    normalize_page_rgb = deps.normalize_page_rgb
    page_template_analysis_image = deps.page_template_analysis_image
    derive_geometry = deps.derive_geometry
    effective_page_settings = deps.effective_page_settings
    if not self.project or not (0 <= index < len(self.project.images)):
        return
    count = max(0, min(10, int(count)))
    page = self.project.images[index]
    existing = read_page_sections(page)

    if index == self.current_index and self.current_page == page and self.image is not None:
        image = self.image
        geometry = self._get_cached_display_geometry()
        effective_settings = effective_page_settings(self.settings, image.size, index)
    else:
        with Image.open(page) as opened:
            image = normalize_page_rgb(opened)
        effective_settings = effective_page_settings(self.settings, image.size, index)
        analysis_image = page_template_analysis_image(image, effective_settings, index)
        geometry = derive_geometry(analysis_image, effective_settings)

    if count == 0:
        sections: list[PageSection] = []
    elif len(existing) == count:
        sections = existing
    else:
        span = max(1, int(geometry.bottom) - int(geometry.top))
        bounds = [
            round(int(geometry.top) + span * item / count)
            for item in range(count + 1)
        ]
        sections = [
            PageSection(bounds[item], max(bounds[item] + 1, bounds[item + 1]))
            for item in range(count)
        ]

    transform = LayoutTransform(
        str(getattr(effective_settings, "layout_transform", "identity") or "identity")
    )
    canonical_width, canonical_height = transform.canonical_size(image.size)
    write_page_sections(
        page, sections,
        canonical_width=canonical_width,
        canonical_height=canonical_height,
        layout_transform=transform.kind,
    )
    iid = str(index)
    if hasattr(self, "page_list") and self.page_list.exists(iid):
        self.page_list.set(iid, "section", str(count))
        if self._page_list_sort_column == "section":
            self._schedule_page_list_resort()

    if index == self.current_index and self.current_page == page:
        self.page_sections = list(sections)
        self._sort_entries_reading_order()
        self._set_section_editing(count > 0)
        self.redraw()
        if count > 0:
            self.status_var.set(
                f"SECTION 编辑：当前页 {count} 个；拖动虚线定位Section，双击左键确认并退出编辑。"
            )
        else:
            self.status_var.set("当前页 SECTION 已关闭（Section = 0）")
        return

    self._pending_section_editor_index = index if count > 0 else None
    self._request_page_load(index, force=True)


def _edit_page_section_index(self, deps: PageIndexDeps, self, index: int) -> None:
    """Shared SECTION entry path for the 域 double-click and 区 shortcut."""
    simpledialog = deps.simpledialog
    read_page_sections = deps.read_page_sections
    if self._preprocess_mode_active():
        self.status_var.set("预处理模式中：SECTION 编辑已锁定。")
        return
    if not self.project or not (0 <= index < len(self.project.images)):
        self.status_var.set("请先打开词典页面，再编辑 Section 区域")
        return
    if index == self.current_index and self._section_editing:
        self._finish_section_editing()
        return
    page = self.project.images[index]
    current_count = len(read_page_sections(page))
    count = simpledialog.askinteger(
        "Section",
        f"{page.name}\nSection 数量（0 = 关闭；1–10 = 启用）：\n\n"
        "确认后：拖动虚线定位Section，双击左键确认并退出编辑。",
        parent=self, initialvalue=current_count, minvalue=0, maxvalue=10,
    )
    if count is None:
        return
    if count > 0 and index == self.current_index:
        # SECTION drag, polygon edit and auxiliary-line edit are separate
        # pointer modes. Do not leave an old edit mode intercepting drags.
        if self.polygon_draw_var.get():
            self.toggle_polygon_drawing()
        if self.auxiliary_mode_var.get():
            self.auxiliary_mode_var.set(False)
            self.toggle_auxiliary_mode()
    self._set_page_section_count(index, count)


def toggle_current_page_section_editing(self, deps: PageIndexDeps, self) -> None:
    """Toggle the same current-page editor as double-clicking 域."""
    self._edit_page_section_index(self.current_index)


def _page_list_section_double_click(self, deps: PageIndexDeps, self, event: tk.Event) -> str | None:
    """Edit the page-level Section count directly from the page list."""
    if self._preprocess_mode_active():
        self.status_var.set("预处理模式中：SECTION 编辑已锁定。")
        return "break"
    if self.page_list.identify_region(event.x, event.y) != "cell":
        return None
    if self._page_list_column_at(event.x) != "section":
        return None
    iid = self.page_list.identify_row(event.y)
    if not iid or not self.project:
        return "break"
    try:
        index = int(iid)
    except (TypeError, ValueError):
        return "break"
    self._edit_page_section_index(index)
    return "break"


def _bookmark_stems(self, deps: PageIndexDeps, self) -> set[str]:
    settings = self.__dict__.get("settings")
    return {
        str(stem) for stem in getattr(settings, "page_bookmarks", [])
        if str(stem).strip()
    }


def _page_list_bookmark_click(self, deps: PageIndexDeps, self, event: tk.Event) -> str | None:
    """Toggle only the bookmark cell; never swallow ordinary page clicks."""
    settings_path = deps.settings_path
    # This handler is bound to every left click on the Treeview. Determine
    # whether the click actually targets the bookmark column *before*
    # applying the preprocess read-only guard. Otherwise returning "break"
    # in preprocess mode suppresses Treeview selection on the 页面 column and
    # makes the page list appear frozen while analysis is running.
    if self.page_list.identify_region(event.x, event.y) != "cell":
        return None
    if self.page_list.identify_column(event.x) != "#1":
        return None
    if self._preprocess_mode_active():
        self.status_var.set("预处理模式中：仅保留页面浏览，不修改书签或其他项目数据。")
        return "break"
    iid = self.page_list.identify_row(event.y)
    if not iid or not self.project:
        return "break"
    try:
        index = int(iid)
        stem = self.project.images[index].stem
    except (TypeError, ValueError, IndexError):
        return "break"
    bookmarks = self._bookmark_stems()
    if stem in bookmarks:
        bookmarks.remove(stem)
    else:
        bookmarks.add(stem)
    self.settings.page_bookmarks = sorted(bookmarks, key=_natural_text_key)
    self.project.settings.page_bookmarks = list(self.settings.page_bookmarks)
    self.settings.to_json(settings_path(self.project.root))
    self._update_page_row(index)
    return "break"


def jump_to_bookmark(self, deps: PageIndexDeps, self, direction: int) -> None:
    """Jump to the nearest bookmarked page before or after this page."""
    if not self.project or self.current_index < 0:
        return
    bookmarks = self._bookmark_stems()
    bookmarked = [
        index for index, page in enumerate(self.project.images)
        if page.stem in bookmarks
    ]
    candidates = (
        [index for index in bookmarked if index < self.current_index]
        if direction < 0 else
        [index for index in bookmarked if index > self.current_index]
    )
    if not candidates:
        self.status_var.set("当前页之前没有书签" if direction < 0 else "当前页之后没有书签")
        return
    self._request_page_load(max(candidates) if direction < 0 else min(candidates))


def _center_page_list_iid(self, deps: PageIndexDeps, self, iid: str) -> None:
    """Place one page row as close as possible to the vertical viewport center."""
    tk = deps.tk
    try:
        children = tuple(self.page_list.get_children(""))
        if not children or iid not in children:
            return
        self.page_list.update_idletasks()
        first, last = self.page_list.yview()
        visible_fraction = max(0.0, min(1.0, float(last) - float(first)))
        if visible_fraction <= 0.0:
            return
        position = children.index(iid)
        row_center = (position + 0.5) / len(children)
        target = row_center - visible_fraction / 2.0
        max_start = max(0.0, 1.0 - visible_fraction)
        self.page_list.yview_moveto(max(0.0, min(max_start, target)))
        self._schedule_page_cell_overlay_refresh()
    except (AttributeError, ValueError, tk.TclError):
        return


def _set_page_list_selection(self, deps: PageIndexDeps, self, index: int, *, ensure_visible: bool = True) -> None:
    """Synchronize the Treeview to exactly one page iid.

    Programmatic page changes must replace, not accumulate, Treeview
    selection.  A stale first selected iid can otherwise be replayed by a
    later ``<<TreeviewSelect>>`` callback after sorting.
    """
    if not hasattr(self, "page_list"):
        return
    iid = str(index)
    if not self.page_list.exists(iid):
        return
    selected = tuple(self.page_list.selection())
    stale = tuple(value for value in selected if value != iid)
    if stale:
        self.page_list.selection_remove(*stale)
    if iid not in selected:
        self.page_list.selection_set(iid)
    if self.page_list.focus() != iid:
        self.page_list.focus(iid)
    if ensure_visible:
        self.page_list.see(iid)
        self._center_page_list_iid(iid)


def _clear_lined_cell_overlays(self, deps: PageIndexDeps, self) -> None:
    tk = deps.tk
    for mapping_name in ("_page_lined_overlays", "_page_fill_status_overlays"):
        mapping = self.__dict__.get(mapping_name, {})
        for widget in mapping.values():
            try:
                widget.destroy()
            except tk.TclError:
                pass
        mapping.clear()


def _visible_page_list_iids(self, deps: PageIndexDeps, self) -> list[str]:
    """Shared viewport scanner for semantic cell overlays and thumbnails."""
    return visible_page_iids(self.page_list) if hasattr(self, "page_list") else []


def _refresh_lined_cell_overlays(self, deps: PageIndexDeps, self) -> None:
    """Paint status-cell labels for visible rows; grid paints afterwards."""
    tk = deps.tk
    _fill_status_cell_style = deps._fill_status_cell_style
    if not hasattr(self, "page_list"):
        return
    self._clear_lined_cell_overlays()
    visible_iids = self._visible_page_list_iids()
    if not visible_iids:
        return

    # Legacy quick warning: only mismatched line-count cells are pale red.
    for iid in visible_iids:
        try:
            index = int(iid)
        except (TypeError, ValueError):
            continue
        if index not in self._word_fill_mismatch_pages:
            continue
        bbox = self.page_list.bbox(iid, "lined")
        if not bbox:
            continue
        x, y, width, height = bbox
        text = str(self.page_list.set(iid, "lined"))
        label = tk.Label(
            self.page_list, text=text, bg="#f8d7da", fg="#6b1f25",
            bd=0, highlightthickness=0, anchor="w", padx=4, pady=0,
        )
        label.place(x=x, y=y, width=width, height=height)
        label.bind("<Button-1>", lambda _e, i=index: self._select_page_from_lined_overlay(i))
        label.bind("<MouseWheel>", self._list_mousewheel)
        self._page_lined_overlays[index] = label

    # The fill-status cell itself carries the semantic status color.
    if "_page_fill_status_overlays" not in self.__dict__:
        self._page_fill_status_overlays = {}
    if not self.project:
        return
    for iid in visible_iids:
        try:
            index = int(iid)
        except (TypeError, ValueError):
            continue
        status_text = str(self.page_list.set(iid, "fill_status") or "")
        style = _fill_status_cell_style(status_text)
        if style is None:
            continue
        bbox = self.page_list.bbox(iid, "fill_status")
        if not bbox:
            continue
        x, y, width, height = bbox
        bg, fg = style
        label = tk.Label(
            self.page_list, text=status_text, bg=bg, fg=fg,
            bd=0, highlightthickness=0, anchor="w", padx=4, pady=0,
        )
        label.place(x=x, y=y, width=width, height=height)
        label.bind("<Button-1>", lambda _e, i=index: self._select_page_from_lined_overlay(i))
        label.bind("<MouseWheel>", self._list_mousewheel)
        self._page_fill_status_overlays[index] = label
    self._apply_current_appearance(self.page_list)


def _page_metadata(self, deps: PageIndexDeps, self, index: int) -> str:
    read_pdic = deps.read_pdic
    pdic_path = deps.pdic_path
    if not self.project or not (0 <= index < len(self.project.images)):
        return ""
    page = self.project.images[index]
    if index == self.current_index and self.current_page is not None:
        return str(len(self.entries))
    try:
        return str(len(read_pdic(pdic_path(page))))
    except (OSError, ValueError):
        return "0"


def _page_illustration_count_text(self, deps: PageIndexDeps, self, index: int) -> str:
    """Return the effective PPP region count for one page, blank for zero.

    The current page uses the in-memory polygon list so manual additions and
    deletions are reflected immediately without disk I/O. Other pages are
    read lazily during the existing metadata refresh; no page image pixels
    are opened or decoded for this column.
    """
    read_ppp = deps.read_ppp
    if not self.project or not (0 <= index < len(self.project.images)):
        return ""
    current_index = self.__dict__.get("current_index", -1)
    current_page = self.__dict__.get("current_page")
    if index == current_index and current_page is not None:
        count = len(self.__dict__.get("polygons", []))
    else:
        try:
            count = len(read_ppp(self._ppp_read_path(self.project.images[index])))
        except (AttributeError, OSError, TypeError, ValueError):
            count = 0
    return str(count) if count > 0 else ""


def _update_page_row(self, deps: PageIndexDeps, self, index: int) -> None:
    Path = deps.Path
    if not self.project or not hasattr(self, "page_list") or not (0 <= index < len(self.project.images)):
        return
    iid = str(index)
    if not self.page_list.exists(iid):
        return
    old_values = tuple(self.page_list.item(iid, "values"))
    section = self._page_section_count_text(index)
    lined = self._page_metadata(index)
    fill_status = self._word_fill_status_text(index)
    illustrations = self._page_illustration_count_text(index)
    page = self.project.images[index]
    page_stem = str(getattr(page, "stem", Path(str(page.name)).stem))
    bookmark = "●" if page_stem in self._bookmark_stems() else ""
    new_values = (bookmark, page_stem, section, lined, fill_status, illustrations)
    self.page_list.item(iid, values=new_values)
    # Avoid Tk's __getattr__ when the shell is not initialized.
    mini = self.__dict__.get("workspace_mini_page_list")
    if mini is not None and mini.exists(iid):
        mini.item(iid, values=new_values)
    active_column = self._page_list_sort_column
    if active_column:
        new_index = {
            "bookmark": 0, "page": 1, "section": 2, "lined": 3,
            "fill_status": 4, "illustrations": 5,
        }.get(active_column, 1)
        if len(old_values) >= 6:
            old_mapping = {
                "bookmark": 0, "page": 1, "section": 2, "lined": 3,
                "fill_status": 4, "illustrations": 5,
            }
        elif len(old_values) >= 5:
            old_mapping = {"bookmark": 0, "page": 1, "lined": 2, "fill_status": 3, "illustrations": 4}
        else:
            old_mapping = {"page": 0, "lined": 1, "fill_status": 2, "illustrations": 3}
        old_index = old_mapping.get(active_column, 0)
        old_value = old_values[old_index] if old_index < len(old_values) else ""
        new_value = new_values[new_index]
        if str(old_value) != str(new_value):
            self._schedule_page_list_resort()
    self._schedule_page_cell_overlay_refresh()


def _refresh_page_metadata_step(self, deps: PageIndexDeps, self, generation: int, start: int) -> None:
    if generation != self._page_meta_generation or not self.project:
        return
    batch = 8
    stop = min(len(self.project.images), start + batch)
    for index in range(start, stop):
        self._update_page_row(index)
    if stop < len(self.project.images):
        self._page_meta_job = self.after(1, lambda g=generation, s=stop: self._refresh_page_metadata_step(g, s))
    else:
        self._page_meta_job = None


def _refresh_page_quality_colors(self, deps: PageIndexDeps, self) -> None:
    """Refresh the lightweight '画线' state without reading OCR confidence caches."""
    tk = deps.tk
    if not self.project:
        return
    self._page_meta_generation += 1
    generation = self._page_meta_generation
    if self._page_meta_job:
        try: self.after_cancel(self._page_meta_job)
        except tk.TclError: pass
    self._page_meta_job = self.after_idle(lambda g=generation: self._refresh_page_metadata_step(g, 0))

