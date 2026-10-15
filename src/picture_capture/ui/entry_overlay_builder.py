from __future__ import annotations

"""Source-native entry overlay rendering isolated from the main GUI shell.

The original PictureCaptureApp instance method is imported as an ordinary
descriptor. Canvas item identity, edit callbacks and PDIC/PPP behavior are
unchanged; nothing is dynamically monkey-patched at runtime.
"""

import tkinter as tk

from ..models import Entry as WordEntry
from ..processing import column_index, line_box
from ..overlay_layout_helpers import (
    canonical_headword_marker_span, effective_overlay_column_width,
    horizontal_entry_editor_slot,
    effective_main_overlay_font_size, entry_index_label_layout,
    horizontal_ocr_menu_layout, horizontal_overlay_layout,
    scaled_overlay_line_width, transformed_entry_anchor,
    vertical_marker_contact_gap, vertical_ocr_menu_layout,
    vertical_overlay_layout,
)
from ..overlay_opacity import create_alpha_canvas_line
from ..review_text_helpers import _entry_font_spec
from ..ui_compat import resolve_content_font_family
from .overlay_delete_button import create_overlay_delete_button, fixed_overlay_control_font
from .widgets.vertical_word import VerticalWordText


def draw_entry_overlay(
    self, entry: WordEntry, index: int, geometry, size: tuple[int, int],
    overlay_scale: float, *, processing_readonly: bool | None = None,
) -> None:
    """Draw one editable headword row without rebuilding the whole canvas."""
    if self.image is None or self.hide_var.get():
        return
    if processing_readonly is None:
        processing_readonly = self._foreground_batch_state(self.current_index) == "processing"
    entry_u, entry_v = geometry.source_to_canonical(entry.x, entry.y)
    col = column_index(entry.x, geometry, entry.y)
    canonical_x = geometry.x_at(col, entry_v)
    column_width = effective_overlay_column_width(
        geometry, col, self.settings.column_width,
    )
    record = {"widgets": [], "canvas_items": [], "index_widget": None}
    marker_left, marker_right = canonical_headword_marker_span(
        canonical_x, column_width, self.settings.right_ratio,
    )
    marker_start, marker_end = geometry.transform.canonical_marker_to_source(
        (marker_left, entry_v), (marker_right, entry_v),
        geometry.source_size,
    )
    column_end_source_x, _column_end_source_y = (
        geometry.transform.canonical_to_source_point(
            round(canonical_x + column_width),
            round(entry_v), geometry.source_size,
        )
    )
    column_end_screen_x = float(column_end_source_x) * self.view_scale
    # Controls are positioned from the *painted* marker endpoint, not
    # the full column edge; right_ratio may be less than 100%.
    marker_right_screen_x = max(
        float(marker_start[0]), float(marker_end[0]),
    ) * self.view_scale
    marker_right_screen_y = (
        float(marker_start[1]) if marker_start[0] >= marker_end[0]
        else float(marker_end[1])
    ) * self.view_scale

    marker_line_width = scaled_overlay_line_width(self.settings.marker_height, overlay_scale)
    show_markers = (
        self.quick_bool_vars.get("show_headword_markers").get()
        if hasattr(self, "quick_bool_vars") and "show_headword_markers" in self.quick_bool_vars
        else self.settings.show_headword_markers
    )
    if show_markers:
        item = create_alpha_canvas_line(
            self,
            (
                marker_start[0] * self.view_scale,
                marker_start[1] * self.view_scale,
                marker_end[0] * self.view_scale,
                marker_end[1] * self.view_scale,
            ),
            fill=self.settings.headword_marker_color,
            width=marker_line_width,
            opacity=self.settings.headword_marker_opacity,
        )
        record["canvas_items"].append(item)

    horizontal = self.settings.layout_writing_mode == "horizontal-tb"
    vertical = not horizontal
    rtl = horizontal and self.settings.layout_text_direction == "rtl"

    # [X] belongs to the visible separator, not to the editable headword
    # label. Instantiate it before the label visibility gate so it is also
    # available when users hide all text editors and sequence numbers.
    delete_button = None
    delete_req_width = 0
    if show_markers:
        delete_button = create_overlay_delete_button(
            self.canvas,
            command=lambda e=entry: self.delete_entry(e),
            attach_tooltip=self._attach_tooltip,
            tooltip="点击删除该画线!",
            ocr_language=self.settings.ocr_language,
            kind="entry",
        )
        if processing_readonly:
            delete_button.configure(state="disabled")
        self.overlay_widgets.append(delete_button)
        record["widgets"].append(delete_button)
        record["delete_widget"] = delete_button
        delete_req_width = max(1, delete_button.winfo_reqwidth())

    if not getattr(self.settings, "show_main_entry_labels", True):
        # Suppress editor, sequence and OCR widgets only. Keep a visible,
        # actionable [X] attached to the marker at the column's far edge.
        if delete_button is not None:
            record["canvas_items"].append(self.canvas.create_window(
                marker_right_screen_x, marker_right_screen_y,
                window=delete_button, anchor="ne",
            ))
        self._entry_visuals[id(entry)] = record
        return

    editor_font_size = effective_main_overlay_font_size(
        self.image.width, self.view_scale, self.settings,
    )
    main_family = resolve_content_font_family(
        self.canvas,
        self.settings.main_entry_font_family,
        self.settings.ocr_language,
    )
    editor_font = _entry_font_spec(
        main_family, editor_font_size,
        self.settings.main_entry_font_bold, self.settings.main_entry_font_italic,
    )
    if horizontal:
        editor = tk.Entry(
            self.canvas,
            width=max(4, int(self.settings.main_entry_width_chars)),
            font=editor_font,
            relief="flat",
        )
    else:
        # Use a real child widget, not a Canvas rectangle/text proxy.  The
        # narrow Text widget wraps by character, so CJK/kana display
        # top-to-bottom while remaining directly clickable and editable.
        editor = VerticalWordText(
            self.canvas,
            width=2,
            height=max(4, int(self.settings.main_entry_width_chars)),
            font=editor_font,
            wrap="char",
            relief="flat",
            borderwidth=0,
            padx=2,
            pady=1,
            spacing1=0,
            spacing2=0,
            spacing3=0,
            undo=False,
            cursor="xterm",
            exportselection=False,
        )
    editor.insert(0, entry.word)
    self._style_entry_editor(editor, entry)
    if processing_readonly:
        if isinstance(editor, VerticalWordText):
            editor.configure(state="disabled", foreground="#555555")
        else:
            editor.configure(state="disabled", disabledforeground="#555555")
    editor.bind("<FocusOut>", lambda _e, e=entry, w=editor: self.update_entry(e, w))
    editor.bind("<KeyPress>", self._entry_keypress_batch_guard)
    editor.bind("<<Paste>>", lambda _e: None if self._claim_page_for_manual_edit() else "break")
    editor.bind("<<Cut>>", lambda _e: None if self._claim_page_for_manual_edit() else "break")
    editor.bind(
        "<KeyRelease>",
        lambda _e, e=entry, w=editor: self._style_entry_editor(w, e, w.get().strip()),
    )
    editor.bind("<Return>", lambda e: self.focus_next(e.widget))
    editor.bind("<Tab>", lambda e: self.focus_next(e.widget))
    editor.bind("<Shift-Tab>", lambda e: self.focus_previous(e.widget))
    editor.bind("<Down>", lambda e: self.focus_next(e.widget))
    editor.bind("<Up>", lambda e: self.focus_previous(e.widget))
    # Tk Entry keeps its native <Delete> binding: remove a character/selection,
    # never the entire PDIC entry or its separator. [X] owns entry deletion.
    editor.bind("<KeyPress-grave>", lambda _e, e=entry: self.delete_entry(e))
    self.overlay_widgets.append(editor)
    record["widgets"].append(editor)
    self.entry_editor_bindings.append((editor, entry))
    editor_req_width = max(1, editor.winfo_reqwidth())
    editor_req_height = max(1, editor.winfo_reqheight())
    editor_anchor = "nw"
    horizontal_index: tuple[float, float] | None = None
    horizontal_index_anchor = "nw"
    if horizontal:
        (editor_x, editor_y), editor_anchor, horizontal_index, horizontal_index_anchor = (
            horizontal_overlay_layout(
                geometry.transform, canonical_x, entry_v, column_width,
                float(self.settings.main_entry_x_ratio), geometry.source_size,
                self.view_scale, rtl=rtl,
            )
        )
        # Canvas editor width uses the visible distance to the column end
        # minus the actual [X] control width, if the marker is displayed.
        editor_req_width, _delete_x, _delete_anchor = horizontal_entry_editor_slot(
            editor_x, column_end_screen_x, delete_req_width, rtl=rtl,
        )
    else:
        # Match horizontal semantics: apply main_entry_x_ratio within the
        # 当前栏 first, then transform that point to source space.
        editor_x, editor_y = transformed_entry_anchor(
            geometry.transform, canonical_x, entry_v, column_width,
            float(self.settings.main_entry_x_ratio), geometry.source_size, self.view_scale,
        )
    
    if rtl:
        editor.configure(justify="right")
    
    vertical_box: tuple[int, int, int, int] | None = None
    vertical_index: tuple[float, float] | None = None
    vertical_index_anchor_name = "nw"
    if vertical:
        # Touch the visible marker stroke with no empty gap.  editor_x is
        # the marker centreline, so offset by exactly half the painted line
        # width to place the widget border against the marker edge.
        marker_gap = vertical_marker_contact_gap(marker_line_width)
        (
            vertical_box,
            vertical_window,
            vertical_window_anchor,
            vertical_index,
            vertical_index_anchor_name,
        ) = vertical_overlay_layout(
            editor_x, editor_y, editor_req_width, editor_req_height,
            self.settings.layout_writing_mode, gap=marker_gap,
        )
        # The Text widget is permanently present.  Unlike the old Canvas
        # proxy, it receives mouse/key events exactly like a horizontal
        # Entry, so no click routing or temporary popup is involved.
        item = self.canvas.create_window(
            *vertical_window,
            window=editor,
            anchor=vertical_window_anchor,
            width=vertical_box[2] - vertical_box[0],
            height=vertical_box[3] - vertical_box[1],
        )
        record["canvas_items"].append(item)
    else:
        item = self.canvas.create_window(
            editor_x, editor_y,
            window=editor,
            anchor=editor_anchor,
            width=editor_req_width,
        )
        record["canvas_items"].append(item)

    candidate = self._candidate_for_entry(entry)
    # OCR-line candidate acceptance/rejection is a separate workflow owned
    # by the detection review layer.  Do not misrepresent an existing PDIC
    # entry as a selectable (or disabled) detection candidate.
    ocr_menu = (
        self._create_main_ocr_menu(entry, editor, candidate)
        if self._main_ocr_review_option_enabled("review_main_show_ocr_choices")
        else None
    )

    if ocr_menu is not None:
        if processing_readonly:
            ocr_menu.configure(state="disabled")

        self.overlay_widgets.append(ocr_menu)
        record["widgets"].append(ocr_menu)

        menu_req_width = max(1, ocr_menu.winfo_reqwidth())

        if vertical and vertical_box:
            if delete_button is not None and self.settings.layout_writing_mode == "vertical-lr":
                # [X] sits to the right of the vertical editor; the optional
                # OCR selector moves below rather than covering that action.
                ocr_x, ocr_y, ocr_anchor = (
                    float(vertical_box[0]), float(vertical_box[3] + 2), "nw",
                )
            else:
                ocr_x, ocr_y, ocr_anchor = vertical_ocr_menu_layout(
                    vertical_box, menu_req_width,
                    self.settings.layout_writing_mode, size[0],
                )
        else:
            # No false "candidate" checkbox for an already-saved Entry.
            # A genuine OCR-line candidate reviewer can reserve its own
            # approved slot in its own rendering layer; this OCR text menu
            # begins directly at the visible marker right endpoint.
            ocr_x = marker_right_screen_x
            ocr_y = marker_right_screen_y + (
                max(1, delete_button.winfo_reqheight()) + 2
                if delete_button is not None else 2
            )
            ocr_anchor = "nw"

        item = self.canvas.create_window(
            ocr_x,
            ocr_y,
            window=ocr_menu,
            anchor=ocr_anchor,
        )
        record["canvas_items"].append(item)

    # The sequence number belongs to the entry editor rather than to the
    # column edge. Use a real Label so its background can exactly follow the
    # editor background (including optional OCR-confidence colouring).
    index_x, index_y, index_anchor = entry_index_label_layout(
        editor_x,
        editor_y,
        editor_req_width,
        editor_req_height,
        horizontal=horizontal,
        rtl=rtl,
        vertical_box=vertical_box,
    )
    index_label = tk.Label(
        self.canvas,
        text=self._entry_sequence_text(index, len(self.entries)),
        bg="#e6e6e6",
        fg="#000000",
        bd=0,
        padx=2,
        pady=0,
        font=fixed_overlay_control_font(
            self.canvas, self.settings.ocr_language,
        ),
    )
    # Sequence numbers intentionally use a neutral light-gray control style;
    # the delete control remains red to preserve its destructive meaning.
    index_label._pc_skip_classic_appearance = True
    # B2: index widget owns a concrete Entry object, never a sorted-row index.
    # Right click gives an explicit original-image XY relocation action.
    # No ordinary left-click/canvas draw or text-editor gesture is changed.
    index_label.bind(
        "<Button-3>",
        lambda _event, e=entry: self._move_entry_via_dialog(e),
    )
    index_label.bind(
        "<Control-Button-1>",
        lambda _event, e=entry: self._move_entry_via_dialog(e),
    )
    self._attach_tooltip(index_label, "右键序号：按原图 X,Y 移动画线（一次一个）")

    self.overlay_widgets.append(index_label)
    record["widgets"].append(index_label)
    record["index_widget"] = index_label
    index_window = self.canvas.create_window(
        index_x, index_y, window=index_label, anchor=index_anchor,
    )
    record["canvas_items"].append(index_window)

    if delete_button is not None:
        if horizontal:
            # The button's RIGHT edge remains aligned with the painted
            # marker endpoint; editor width is reserved independently.
            delete_x = marker_right_screen_x
            delete_y = marker_right_screen_y
            delete_anchor = "ne"
        else:
            # For vertical text there is no horizontal trailing word box;
            # use the physical right edge of its actual vertical widget.
            delete_x = float(min(
                max(0, size[0] - delete_req_width),
                vertical_box[2] + 2 if vertical_box else column_end_screen_x,
            ))
            delete_y = float(editor_y)
            delete_anchor = "nw"
        record["canvas_items"].append(self.canvas.create_window(
            delete_x, delete_y, window=delete_button, anchor=delete_anchor,
        ))

    if self.crop_preview_var.get():
        left, top, right, bottom = line_box(entry, geometry, self.image, self.settings)
        item = self.canvas.create_rectangle(
            left * self.view_scale, top * self.view_scale,
            right * self.view_scale, bottom * self.view_scale,
            outline="#00acc1", width=1, dash=(5, 3),
        )
        record["canvas_items"].append(item)

    self._entry_visuals[id(entry)] = record

