from __future__ import annotations

from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from ...appearance import themed_display_image
from ..text_wrap import _label_measure, _normalize_ui_paragraphs, _wrap_mixed_ui_text


def show_settings_help(
    dialog: Any,
    title: str,
    body: str,
    image_name: str | None = None,
) -> None:
    if hasattr(dialog, "_settings_help_title_var"):
        dialog._settings_help_title_var.set(str(title or "设置说明"))
    if hasattr(dialog, "_settings_help_body_var"):
        raw_body = str(body or "不确定时保持当前值即可。")
        dialog._settings_help_body_var.set(raw_body)
        help_body = getattr(dialog, "_settings_help_body_label", None)
        if help_body is not None:
            normalized = _normalize_ui_paragraphs(raw_body)
            help_body._pc_wrap_source = normalized
            help_body.configure(text=normalized, wraplength=0)
            try:
                dialog.after_idle(lambda w=help_body: w.event_generate("<Configure>"))
            except tk.TclError:
                pass
    dialog._settings_help_current_image = image_name
    dialog._schedule_settings_help_image_render()


def settings_help_image_path(image_name: str) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "data"
        / "layout_example"
        / image_name
    )


def load_settings_help_image(dialog: Any, image_name: str) -> Image.Image | None:
    cached = dialog._settings_help_original_images.get(image_name)
    if cached is not None:
        return cached
    path = dialog._settings_help_image_path(image_name)
    try:
        with Image.open(path) as opened:
            image = opened.convert("RGBA").copy()
    except (OSError, ValueError):
        return None
    dialog._settings_help_original_images[image_name] = image
    return image


def schedule_settings_help_image_render(dialog: Any) -> None:
    job = getattr(dialog, "_settings_help_image_job", None)
    if job is not None:
        try:
            dialog.after_cancel(job)
        except tk.TclError:
            pass
    dialog._settings_help_image_job = dialog.after_idle(dialog._render_settings_help_images)


def render_settings_help_images(dialog: Any) -> None:
    dialog._settings_help_image_job = None
    image_name = getattr(dialog, "_settings_help_current_image", None)
    original = dialog._load_settings_help_image(image_name) if image_name else None

    for label, separator, help_box in dialog._settings_help_image_widgets:
        if original is None:
            try:
                label.configure(image="")
                label.image = None
                label.pack_forget()
            except tk.TclError:
                pass
            continue
        try:
            mapped = bool(help_box.winfo_ismapped())
        except tk.TclError:
            continue
        if not mapped:
            continue

        available_width = max(180, int(help_box.winfo_width()) - 28)
        max_width = min(380, available_width)
        max_height = 330
        scale = min(
            1.0,
            max_width / max(1, original.width),
            max_height / max(1, original.height),
        )
        width = max(1, int(round(original.width * scale)))
        height = max(1, int(round(original.height * scale)))
        rendered = original.resize((width, height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(
            themed_display_image(rendered, dialog.parent.appearance_mode)
        )
        label.configure(image=photo)
        label.image = photo
        label.pack(
            anchor="center",
            fill="x",
            pady=(12, 2),
            before=separator,
        )


def show_setting_help(
    dialog: Any, name: str, *, show_layout_image: bool = False
) -> None:
    title = dialog.SETTING_LABELS.get(
        name, dialog._field_meta.get(name, (name, str))[0]
    )
    body = dialog.SETTING_HELP.get(
        name, "专家参数；不确定时建议保持当前值。"
    )
    unit = dialog.SETTING_UNITS.get(name, "")
    if unit:
        body += f"\n\n单位：{unit}"
    image_name = dialog.SETTING_HELP_IMAGES.get(name) if show_layout_image else None
    dialog._show_settings_help(title, body, image_name)


def show_check_help(dialog: Any, label: str, name: str) -> None:
    dialog._show_settings_help(
        label,
        dialog.CHECK_HELP.get(name, "高级行为开关；不确定时保持默认。"),
    )


def bind_help_widget(dialog: Any, widget: tk.Misc, callback) -> None:
    """Keep full explanations one glance away without filling every form row."""
    try:
        widget.bind("<Enter>", lambda _e: callback(), add="+")
        widget.bind("<FocusIn>", lambda _e: callback(), add="+")
    except tk.TclError:
        return
    try:
        for child in widget.winfo_children():
            dialog._bind_help_widget(child, callback)
    except tk.TclError:
        pass


def bind_responsive_labels(
    dialog: Any,
    container: tk.Misc,
    *labels: ttk.Label,
    horizontal_padding: int = 12,
    min_wrap: int = 120,
) -> None:
    """Character-wrap CJK prose to each label's real visible width."""
    pending = {"job": None}

    for label in labels:
        try:
            textvariable = str(label.cget("textvariable") or "").strip()
            label._pc_dynamic_textvariable = bool(textvariable)
            if label._pc_dynamic_textvariable:
                continue
            if not getattr(label, "_pc_wrap_source", None):
                label._pc_wrap_source = _normalize_ui_paragraphs(label.cget("text"))
            initial = _wrap_mixed_ui_text(
                label._pc_wrap_source,
                _label_measure(label),
                max(180, int(min_wrap) * 3),
            )
            label.configure(text=initial, wraplength=0)
        except (tk.TclError, TypeError, ValueError):
            continue

    def refresh() -> None:
        pending["job"] = None
        try:
            container_width = int(container.winfo_width())
        except (AttributeError, tk.TclError, TypeError, ValueError):
            return
        if container_width <= 1:
            return
        cap = max(60, container_width - max(0, int(horizontal_padding)))
        for label in labels:
            try:
                label_width = int(label.winfo_width())
                if label_width <= 20 or label_width > cap:
                    label_width = cap
                available = max(48, label_width - 12)
                if getattr(label, "_pc_dynamic_textvariable", False):
                    if getattr(label, "_pc_wrap_width", None) == available:
                        continue
                    label._pc_wrap_width = available
                    if int(float(label.cget("wraplength"))) != available:
                        label.configure(wraplength=available)
                    continue
                raw = getattr(label, "_pc_wrap_source", label.cget("text"))
                cache_key = (str(raw), int(available))
                if getattr(label, "_pc_wrap_cache_key", None) == cache_key:
                    continue
                rendered = _wrap_mixed_ui_text(
                    raw, _label_measure(label), available
                )
                label._pc_wrap_cache_key = cache_key
                if (
                    label.cget("text") != rendered
                    or int(float(label.cget("wraplength"))) != 0
                ):
                    label.configure(text=rendered, wraplength=0)
            except (tk.TclError, TypeError, ValueError):
                continue

    def schedule(_event=None) -> None:
        try:
            if pending["job"] is not None:
                dialog.after_cancel(pending["job"])
            # Debounce onto the normal event loop instead of the idle queue.
            # update_idletasks() drains idle callbacks synchronously; with many
            # Settings Center help labels that could stall Windows/Tk.
            pending["job"] = dialog.after(80, refresh)
        except tk.TclError:
            return

    try:
        # Container width is the authoritative wrapping constraint. Binding
        # each label's own <Configure> event creates a self-triggering loop.
        container.bind("<Configure>", schedule, add="+")
        schedule()
    except tk.TclError:
        pass
