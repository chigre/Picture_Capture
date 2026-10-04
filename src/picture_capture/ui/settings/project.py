from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from ...models import resolve_wordslist_path


def build_project_details_tab(
    dialog,
    tab: ttk.Frame,
    *,
    language_codes: tuple[str, ...],
    language_from_ocr,
) -> None:
    """Build project metadata fields without coupling back to the app module."""
    tab.columnconfigure(0, weight=1)
    form = ttk.LabelFrame(tab, text="词典项目详情", padding=(16, 12))
    form.grid(row=0, column=0, sticky="new", padx=14, pady=14)
    form.columnconfigure(1, weight=1)

    fields = (
        ("词典完整名称：", "dictionary_full_name"),
        ("词典缩写名称：", "dictionary_abbreviation"),
        ("ISBN：", "dictionary_isbn"),
    )
    for row, (label, name) in enumerate(fields):
        ttk.Label(form, text=label).grid(
            row=row, column=0, sticky="e", padx=(0, 8), pady=5
        )
        var = tk.StringVar(value=str(getattr(dialog.parent.settings, name)))
        dialog.vars[name] = var
        ttk.Entry(form, textvariable=var, width=42).grid(
            row=row, column=1, sticky="ew", pady=5
        )

    ocr_var_for_value = dialog.vars.get("ocr_language")
    ocr_language = str(ocr_var_for_value.get() if ocr_var_for_value else "")
    configured_index_language = str(
        dialog.parent.settings.dictionary_index_language
    ).strip().lower()
    suggested_index_language = language_from_ocr(ocr_language)
    dialog._project_index_language_auto = not configured_index_language
    index_var = tk.StringVar(
        value=configured_index_language or suggested_index_language
    )
    content_var = tk.StringVar(
        value=str(dialog.parent.settings.dictionary_content_language).strip().lower()
    )
    dialog.vars["dictionary_index_language"] = index_var
    dialog.vars["dictionary_content_language"] = content_var

    ttk.Label(form, text="索引语言：").grid(
        row=3, column=0, sticky="e", padx=(0, 8), pady=5
    )
    index_combo = ttk.Combobox(
        form,
        textvariable=index_var,
        values=language_codes,
        state="readonly",
        width=12,
    )
    index_combo.grid(row=3, column=1, sticky="w", pady=5)
    index_combo.bind(
        "<<ComboboxSelected>>",
        lambda _event: setattr(dialog, "_project_index_language_auto", False),
    )
    ttk.Label(
        form,
        text="2 位语言代号；首次按 OCR 语言自动选择",
        foreground="#666666",
    ).grid(row=3, column=1, sticky="w", padx=(120, 0), pady=5)

    ttk.Label(form, text="内容语言：").grid(
        row=4, column=0, sticky="e", padx=(0, 8), pady=5
    )
    ttk.Combobox(
        form,
        textvariable=content_var,
        values=language_codes,
        state="readonly",
        width=12,
    ).grid(row=4, column=1, sticky="w", pady=5)
    ttk.Label(form, text="2 位语言代号", foreground="#666666").grid(
        row=4, column=1, sticky="w", padx=(120, 0), pady=5
    )

    if "columns" not in dialog.vars:
        dialog.vars["columns"] = tk.StringVar(
            value=str(dialog.parent.settings.columns)
        )
    ttk.Label(form, text="词典版面栏数：").grid(
        row=5, column=0, sticky="e", padx=(0, 8), pady=5
    )
    ttk.Spinbox(
        form,
        textvariable=dialog.vars["columns"],
        from_=1,
        to=12,
        width=10,
    ).grid(row=5, column=1, sticky="w", pady=5)

    page_range_var = tk.StringVar(
        value=str(dialog.parent.settings.dictionary_body_page_range)
    )
    dialog.vars["dictionary_body_page_range"] = page_range_var
    ttk.Label(form, text="正文页码范围：").grid(
        row=6, column=0, sticky="e", padx=(0, 8), pady=5
    )
    ttk.Entry(form, textvariable=page_range_var, width=24).grid(
        row=6, column=1, sticky="w", pady=5
    )
    ttk.Label(form, text="例如：1-1250", foreground="#666666").grid(
        row=6, column=1, sticky="w", padx=(205, 0), pady=5
    )

    ocr_var = dialog.vars.get("ocr_language")
    if ocr_var is not None:
        def sync_index_language(*_args) -> None:
            if dialog._project_index_language_auto:
                mapped = language_from_ocr(str(ocr_var.get()))
                if mapped in language_codes:
                    index_var.set(mapped)

        ocr_var.trace_add("write", sync_index_language)

    ttk.Label(
        tab,
        text="这些资料随当前项目保存在 _PictureCapture/settings.json 中。",
        foreground="#666666",
    ).grid(row=1, column=0, sticky="w", padx=18)


def browse_wordslist_setting(dialog, var: tk.StringVar) -> None:
    """Choose a wordslist and persist a portable project-relative path when possible."""
    initialdir = str(dialog.parent.project.root) if dialog.parent.project else None
    current = str(var.get()).strip()
    if dialog.parent.project and current:
        try:
            current_path = resolve_wordslist_path(dialog.parent.project.root, current)
            if current_path.parent.exists():
                initialdir = str(current_path.parent)
        except Exception:
            pass

    chosen = filedialog.askopenfilename(
        parent=dialog,
        title="选择 wordslist 参考词表",
        initialdir=initialdir,
        filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
    )
    if not chosen:
        return

    path = Path(chosen)
    if dialog.parent.project:
        try:
            path_text = path.resolve().relative_to(
                dialog.parent.project.root.resolve()
            ).as_posix()
        except ValueError:
            path_text = str(path.resolve())
    else:
        path_text = str(path)
    var.set(path_text)
