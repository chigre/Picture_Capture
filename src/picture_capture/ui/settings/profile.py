from __future__ import annotations

from typing import Any
import tkinter as tk
from tkinter import ttk

from ...collation import available_profile_labels
from ...dictionary_profile import (
    DEFAULT_PROFILE_ID,
    available_dictionary_profiles,
    dictionary_profile_preset,
    effective_project_profile_id,
    language_effective_settings,
    profile_effective_settings,
    profile_layout_summary,
)
from ...project_storage import profile_path as project_profile_path


def build_profile_tab(dialog: Any, tab: ttk.Frame) -> None:
    tab.columnconfigure(0, weight=1)
    tab.rowconfigure(1, weight=1)
    top = ttk.Frame(tab, padding=(14, 12, 14, 8))
    top.grid(row=0, column=0, sticky="ew")
    top.columnconfigure(1, weight=1)

    selected_key = effective_project_profile_id(
        dialog.parent.settings,
        project_profile_path(dialog.parent.project.root) if dialog.parent.project else None,
    )
    try:
        selected = dictionary_profile_preset(selected_key)
    except Exception:
        selected = dictionary_profile_preset(DEFAULT_PROFILE_ID)
        selected_key = selected.key
    dialog._active_profile_key = selected_key
    dialog._profile_selection_changed = False
    dialog.custom_profile_name_var = tk.StringVar(
        value=str(getattr(dialog.parent.settings, "dictionary_custom_profile_name", "") or "")
    )
    dialog.vars["dictionary_custom_profile_name"] = dialog.custom_profile_name_var
    dialog._profile_label_to_key = dialog._build_profile_choice_labels()
    dialog.profile_choice_var = tk.StringVar(value=dialog._profile_label_for_key(selected_key))
    ttk.Label(top, text="词头类型：").grid(row=0, column=0, sticky="e", padx=(0, 8), pady=4)
    dialog.profile_combo = ttk.Combobox(
        top, textvariable=dialog.profile_choice_var,
        values=tuple(dialog._profile_label_to_key.keys()), state="readonly", width=44,
    )
    dialog.profile_combo.grid(row=0, column=1, sticky="ew", pady=4)
    dialog.profile_combo.bind("<<ComboboxSelected>>", dialog._on_profile_selected)
    ttk.Button(top, text="恢复 Profile 默认值", command=dialog.restore_profile_defaults).grid(
        row=0, column=2, padx=(10, 0), pady=4
    )

    ttk.Label(top, text="自定义结构名称：").grid(
        row=1, column=0, sticky="e", padx=(0, 8), pady=4
    )
    dialog.custom_profile_name_entry = ttk.Entry(
        top, textvariable=dialog.custom_profile_name_var, width=32,
    )
    dialog.custom_profile_name_entry.grid(row=1, column=1, sticky="ew", pady=4)
    ttk.Label(
        top,
        text="仅修改当前项目中“自定义结构”的显示名称；底层 Profile key 仍为 custom。",
        foreground="#666666",
    ).grid(row=1, column=2, columnspan=2, sticky="w", padx=(10, 0), pady=4)
    dialog.custom_profile_name_var.trace_add(
        "write", lambda *_args: dialog.after_idle(dialog._on_custom_profile_name_changed)
    )

    dialog.profile_description_var = tk.StringVar(value="")
    dialog.profile_examples_var = tk.StringVar(value="")
    dialog.profile_layout_summary_var = tk.StringVar(value="")
    profile_description = ttk.Label(
        top, textvariable=dialog.profile_description_var, justify="left"
    )
    profile_description.grid(
        row=2, column=0, columnspan=4, sticky="ew", pady=(8, 2)
    )
    profile_examples = ttk.Label(
        top, textvariable=dialog.profile_examples_var, justify="left"
    )
    profile_examples.grid(
        row=3, column=0, columnspan=4, sticky="ew", pady=(2, 0)
    )
    dialog._bind_responsive_labels(
        top,
        profile_description,
        profile_examples,
        horizontal_padding=20,
        min_wrap=180,
    )
    ttk.Label(
        top, textvariable=dialog.profile_layout_summary_var,
        font=("TkDefaultFont", 10, "bold"), foreground="#245a86",
    ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(5, 0))
    dialog._sync_custom_profile_name_state()

    profile_scroll_host = ttk.Frame(tab)
    profile_scroll_host.grid(row=1, column=0, sticky="nsew")
    profile_scroll_host.rowconfigure(0, weight=1)
    profile_scroll_host.columnconfigure(0, weight=1)
    profile_canvas = tk.Canvas(profile_scroll_host, highlightthickness=0, borderwidth=0)
    dialog.profile_canvas = profile_canvas
    profile_scrollbar = ttk.Scrollbar(
        profile_scroll_host, orient="vertical", command=profile_canvas.yview,
    )
    profile_canvas.configure(yscrollcommand=profile_scrollbar.set)
    profile_canvas.grid(row=0, column=0, sticky="nsew")
    profile_scrollbar.grid(row=0, column=1, sticky="ns")
    body = ttk.Frame(profile_canvas, padding=(14, 0, 14, 10))
    profile_window = profile_canvas.create_window((0, 0), window=body, anchor="nw")

    def _profile_sync_scrollregion(_event=None) -> None:
        bbox = profile_canvas.bbox("all")
        if bbox:
            profile_canvas.configure(scrollregion=bbox)

    def _profile_fit_width(event) -> None:
        profile_canvas.itemconfigure(profile_window, width=event.width)

    body.bind("<Configure>", _profile_sync_scrollregion)
    profile_canvas.bind("<Configure>", _profile_fit_width)
    body.columnconfigure(0, weight=1)
    body.columnconfigure(1, weight=1)
    field_meta = dialog._field_meta
    for gi, (title, names) in enumerate(dialog.PROFILE_FIELD_GROUPS):
        group = ttk.LabelFrame(body, text=title, padding=(10, 7))
        group.grid(row=gi // 2, column=gi % 2, sticky="nsew", padx=(0 if gi % 2 == 0 else 6, 6 if gi % 2 == 0 else 0), pady=(0, 8))
        group.columnconfigure(1, weight=1)
        for row, name in enumerate(names):
            label, _cast = field_meta[name]
            ttk.Label(group, text=label).grid(row=row, column=0, sticky="e", padx=(0, 7), pady=3)
            if name not in dialog.vars:
                dialog.vars[name] = tk.StringVar(value=str(getattr(dialog.parent.settings, name)))
            var = dialog.vars[name]
            if name == "ocr_language":
                widget = ttk.Combobox(group, textvariable=var, values=dialog.OCR_LANGUAGES, state="normal", width=24)
                widget.bind("<<ComboboxSelected>>", lambda _e: dialog._on_profile_language_changed())
                widget.bind("<FocusOut>", lambda _e: dialog._on_profile_language_changed())
                var.trace_add("write", lambda *_args: dialog.after_idle(dialog._refresh_sort_choices))
            elif name == "layout_writing_mode":
                widget = ttk.Combobox(
                    group, textvariable=var, values=("horizontal-tb", "vertical-rl", "vertical-lr"),
                    state="readonly", width=24,
                )
                widget.bind("<<ComboboxSelected>>", lambda _e: dialog._sync_layout_semantics())
            elif name == "layout_text_direction":
                widget = ttk.Combobox(group, textvariable=var, values=("ltr", "rtl"), state="readonly", width=24)
                widget.bind("<<ComboboxSelected>>", lambda _e: dialog._sync_layout_semantics())
            elif name == "layout_columns_policy":
                widget = ttk.Combobox(group, textvariable=var, values=("detect", "fixed"), state="readonly", width=24)
            elif name == "layout_column_separator_mode":
                widget = ttk.Combobox(group, textvariable=var, values=("auto", "present", "absent"), state="readonly", width=24)
            elif name == "analysis_threshold_mode":
                widget = ttk.Combobox(group, textvariable=var, values=("auto", "otsu", "adaptive", "fixed"), state="readonly", width=24)
            elif name == "layout_transform":
                widget = ttk.Entry(group, textvariable=var, width=24, state="readonly")
            else:
                widget = ttk.Entry(group, textvariable=var, width=24)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            try:
                var.trace_add("write", lambda *_args: dialog.after_idle(dialog._refresh_profile_status))
            except tk.TclError:
                pass

    check_group = ttk.LabelFrame(body, text="识别行为", padding=(10, 7))
    check_group.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
    for row, (label, name) in enumerate(dialog.PROFILE_CHECKS):
        if name not in dialog.vars:
            dialog.vars[name] = tk.BooleanVar(value=bool(getattr(dialog.parent.settings, name)))
        ttk.Checkbutton(check_group, text=label, variable=dialog.vars[name]).grid(row=row, column=0, sticky="w", pady=3)
        try:
            dialog.vars[name].trace_add("write", lambda *_args: dialog.after_idle(dialog._refresh_profile_status))
        except tk.TclError:
            pass

    dialog.profile_status_var = tk.StringVar(value="")
    status = ttk.Frame(tab, padding=(14, 0, 14, 10))
    status.grid(row=2, column=0, sticky="ew")
    ttk.Label(status, textvariable=dialog.profile_status_var).pack(side="left")
    ttk.Label(
        status,
        text="Profile 默认值是起点；这里的手工调整会作为项目 overrides 保存，不会改写内置 Profile。",
    ).pack(side="right")
    dialog._refresh_profile_summary()
    dialog.after_idle(dialog._refresh_profile_status)


def build_profile_choice_labels(dialog: Any) -> dict[str, str]:
    """Return numbered Profile labels, always keeping custom as the last item."""
    profiles = list(available_dictionary_profiles())
    profiles.sort(key=lambda profile: profile.key == "custom")
    custom_name = (
        str(dialog.custom_profile_name_var.get()).strip()
        if hasattr(dialog, "custom_profile_name_var") else ""
    )
    labels: dict[str, str] = {}
    for index, profile in enumerate(profiles, start=1):
        display_name = profile.display_name
        if profile.key == "custom" and custom_name:
            display_name = f"{custom_name}（自定义）"
        labels[f"{index}. {display_name}"] = profile.key
    return labels


def profile_label_for_key(dialog: Any, key: str) -> str:
    for label, value in dialog._profile_label_to_key.items():
        if value == key:
            return label
    # Compatibility aliases use the display name of their visible base
    # profile; map them back to that numbered visible choice.
    try:
        wanted_name = dictionary_profile_preset(key).display_name
    except Exception:
        wanted_name = ""
    for label, value in dialog._profile_label_to_key.items():
        try:
            if dictionary_profile_preset(value).display_name == wanted_name:
                return label
        except Exception:
            continue
    return next(iter(dialog._profile_label_to_key), "")


def profile_display_name(dialog: Any, key: str) -> str:
    if key == "custom":
        custom_name = str(dialog.custom_profile_name_var.get()).strip()
        if custom_name:
            return f"{custom_name}（自定义）"
    return dictionary_profile_preset(key).display_name


def sync_custom_profile_name_state(dialog: Any) -> None:
    if not hasattr(dialog, "custom_profile_name_entry"):
        return
    state = "normal" if dialog._current_profile_key() == "custom" else "disabled"
    dialog.custom_profile_name_entry.configure(state=state)


def on_custom_profile_name_changed(dialog: Any) -> None:
    if not hasattr(dialog, "profile_combo"):
        return
    current_key = dialog._current_profile_key()
    dialog._profile_label_to_key = dialog._build_profile_choice_labels()
    dialog.profile_combo.configure(values=tuple(dialog._profile_label_to_key.keys()))
    dialog.profile_choice_var.set(dialog._profile_label_for_key(current_key))
    dialog._sync_custom_profile_name_state()
    dialog._refresh_profile_summary()
    dialog._refresh_profile_status()


def current_profile_key(dialog: Any) -> str:
    if hasattr(dialog, "profile_choice_var"):
        return dialog._profile_label_to_key.get(
            dialog.profile_choice_var.get(),
            dialog._active_profile_key or DEFAULT_PROFILE_ID,
        )
    return str(
        dialog._active_profile_key
        or dialog.parent.settings.dictionary_profile_id
        or DEFAULT_PROFILE_ID
    )


def refresh_profile_summary(dialog: Any) -> None:
    profile = dictionary_profile_preset(dialog._current_profile_key())
    dialog.profile_description_var.set(profile.description)
    try:
        columns = (
            max(1, int(dialog.vars.get("columns").get()))
            if dialog.vars.get("columns") else 1
        )
    except (TypeError, ValueError, tk.TclError):
        columns = 1
    layout = {
        "writing_mode": (
            str(dialog.vars.get("layout_writing_mode").get())
            if dialog.vars.get("layout_writing_mode") else "horizontal-tb"
        ),
        "text_direction": (
            str(dialog.vars.get("layout_text_direction").get())
            if dialog.vars.get("layout_text_direction") else "ltr"
        ),
        "canonical_transform": (
            str(dialog.vars.get("layout_transform").get())
            if dialog.vars.get("layout_transform") else "identity"
        ),
        "columns": columns,
        "column_separator": (
            str(dialog.vars.get("layout_column_separator_mode").get())
            if dialog.vars.get("layout_column_separator_mode") else "auto"
        ),
    }
    language = (
        str(dialog.vars.get("ocr_language").get())
        if dialog.vars.get("ocr_language") else ""
    )
    dialog.profile_layout_summary_var.set(
        f"{language} · {dialog._profile_display_name(profile.key)} · "
        f"{profile_layout_summary(profile, layout)}"
    )
    if profile.examples:
        names = "；".join(example.dictionary for example in profile.examples)
        dialog.profile_examples_var.set(f"经典样例：{names}")
    else:
        dialog.profile_examples_var.set("经典样例：通用兼容型（当前未内置样页）")


def coerce_profile_var(dialog: Any, name: str):
    var = dialog.vars.get(name)
    if var is None:
        return None
    value = var.get()
    if isinstance(var, tk.BooleanVar):
        return bool(value)
    cast = dialog._casts.get(name, str)
    try:
        return cast(value)
    except Exception:
        return value


def refresh_profile_status(dialog: Any) -> None:
    if not hasattr(dialog, "profile_status_var"):
        return
    key = dialog._current_profile_key()
    current_language = str(
        dialog.vars.get("ocr_language").get()
        if dialog.vars.get("ocr_language") else ""
    )
    defaults = profile_effective_settings(key, current_language=current_language)
    changed = []
    for name, expected in defaults.items():
        if name not in dialog.vars:
            continue
        if dialog._coerce_profile_var(name) != expected:
            changed.append(name)
    suffix = "（使用预设默认值）" if not changed else f"（项目调整 {len(changed)} 项）"
    dialog.profile_status_var.set(f"{dialog._profile_display_name(key)} {suffix}")


def apply_profile_defaults_to_vars(
    dialog: Any,
    key: str,
    *,
    keep_supported_language: bool = True,
) -> None:
    current_language = ""
    if keep_supported_language and dialog.vars.get("ocr_language") is not None:
        current_language = str(dialog.vars["ocr_language"].get())
    defaults = profile_effective_settings(key, current_language=current_language)
    for name, value in defaults.items():
        if name not in dialog.vars:
            continue
        dialog.vars[name].set(value)
    dialog._active_profile_key = key
    dialog._refresh_profile_summary()
    dialog._on_profile_language_changed(update_profile_paddle=False)
    dialog._refresh_profile_status()


def on_profile_selected(dialog: Any, _event=None) -> None:
    key = dialog._current_profile_key()
    dialog._profile_selection_changed = True
    dialog._sync_custom_profile_name_state()
    dialog._apply_profile_defaults_to_vars(key, keep_supported_language=True)


def restore_profile_defaults(dialog: Any) -> None:
    dialog._apply_profile_defaults_to_vars(
        dialog._current_profile_key(), keep_supported_language=True
    )


def on_profile_language_changed(
    dialog: Any, update_profile_paddle: bool = True
) -> None:
    key = dialog._current_profile_key()
    profile = dictionary_profile_preset(key)
    language = str(
        dialog.vars.get("ocr_language").get()
        if dialog.vars.get("ocr_language") else ""
    )
    base = next((part.strip() for part in language.split("+") if part.strip()), "")
    if update_profile_paddle and dialog.vars.get("paddle_language") is not None:
        recommended = profile.paddle_language_by_language.get(base)
        if recommended:
            dialog.vars["paddle_language"].set(recommended)
    writing = (
        str(dialog.vars.get("layout_writing_mode").get())
        if dialog.vars.get("layout_writing_mode") else "horizontal-tb"
    )
    for name, value in language_effective_settings(language, writing).items():
        if name in dialog.vars and (
            update_profile_paddle or name != "paddle_language"
        ):
            dialog.vars[name].set(value)
    dialog._refresh_sort_choices()
    dialog._refresh_profile_summary()
    dialog._refresh_profile_status()


def sync_layout_semantics(dialog: Any) -> None:
    writing = str(dialog.vars["layout_writing_mode"].get())
    direction = str(dialog.vars["layout_text_direction"].get())
    transform = (
        "rotate_ccw90"
        if writing == "vertical-rl"
        else "rotate_cw90"
        if writing == "vertical-lr"
        else "mirror_x"
        if direction == "rtl"
        else "identity"
    )
    dialog.vars["layout_transform"].set(transform)
    dialog._on_profile_language_changed()


def refresh_sort_choices(dialog: Any, initial: bool = False) -> None:
    if not hasattr(dialog, "sort_combo"):
        return
    language = str(
        dialog.vars.get("ocr_language").get()
        if dialog.vars.get("ocr_language")
        else dialog.parent.settings.ocr_language
    ).strip() or "eng"
    dialog.sort_language_var.set(language)
    mapping = available_profile_labels(language)
    dialog._sort_label_to_value = mapping
    dialog.sort_combo.configure(values=tuple(mapping.keys()))
    current_key = (
        getattr(dialog.parent.settings, "headword_sort_mode", "auto")
        if initial
        else mapping.get(dialog.sort_mode_var.get(), "auto")
    )
    # Preserve a currently selected key only if it belongs to the new
    # language-specific menu.
    valid_values = set(mapping.values())
    if current_key not in valid_values:
        current_key = "auto"
    label = next(
        (label for label, value in mapping.items() if value == current_key),
        next(iter(mapping)),
    )
    dialog.sort_mode_var.set(label)
    dialog._toggle_custom_sort_state()


def toggle_custom_sort_state(dialog: Any) -> None:
    key = dialog._sort_label_to_value.get(dialog.sort_mode_var.get(), "auto")
    state = "normal" if key == "custom" else "disabled"
    dialog.custom_order_entry.configure(state=state)
    dialog.custom_fold_check.configure(state=state)
