"""REF settings, sample capture and local template management."""
from __future__ import annotations

from pathlib import Path

import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from ...ref_box_detection import (
    REF_SAMPLE_CATEGORIES, delete_ref_sample, default_ref_sample_direction,
    list_ref_samples, read_ref_sample_metadata, write_ref_sample_metadata,
)
from .schema import (
    REF_BOX_STYLE_FIELDS, REF_BOX_GEOMETRY_FIELDS, REF_BOX_CHECKS,
    REF_BOX_GEOMETRY_CHECKS, REF_TEXT_LABEL_FIELDS,
    REF_TEXT_LABEL_CHECKS, REF_OCR_EXTRACTION_FIELDS,
)


def show_ref_samples(dialog) -> None:
    """Grouped manager for per-template category and target direction."""
    project = dialog.parent.project
    if project is None:
        messagebox.showinfo("REF 样本", "请先打开词典项目", parent=dialog)
        return
    window = tk.Toplevel(dialog)
    window.title("分类管理 REF 引导词样本")
    window.geometry("710x570")
    frame = ttk.Frame(window, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="按引导词分类管理；每个样本可单独修改类别与向前/向后方向。",
              wraplength=670).pack(anchor="w", pady=(0, 8))
    tree = ttk.Treeview(frame, show="tree", height=11, selectmode="browse")
    tree.heading("#0", text="类别 / 图样（→ 向后，← 向前）")
    tree.pack(fill="both", expand=True)
    preview = ttk.Label(frame, text="选择样本预览")
    preview.pack(fill="x", pady=8)
    photos: list[ImageTk.PhotoImage] = []
    paths: dict[str, Path] = {}
    categories = list(REF_SAMPLE_CATEGORIES)
    category_var = tk.StringVar(value="未分类")
    direction_var = tk.StringVar(value="向后")
    editor = ttk.Frame(frame)
    editor.pack(fill="x", pady=(4, 8))
    ttk.Label(editor, text="引导词类别").pack(side="left")
    category_editor = ttk.Combobox(editor, textvariable=category_var,
                                   values=categories, width=14)
    category_editor.pack(side="left", padx=(4, 18))
    ttk.Label(editor, text="REF 位置").pack(side="left")
    ttk.Combobox(editor, textvariable=direction_var, state="readonly",
                 values=("向后", "向前"), width=10).pack(side="left", padx=4)

    def refresh(selected_path=None):
        paths.clear()
        tree.delete(*tree.get_children())
        grouped: dict[str, list[tuple[Path, str]]] = {}
        errors = []
        for path in list_ref_samples(project.root):
            try:
                meta = read_ref_sample_metadata(path)
            except (ValueError, OSError) as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            grouped.setdefault(meta["category"], []).append((path, meta["direction"]))
        for index, category in enumerate(sorted(grouped)):
            parent = tree.insert("", "end", iid=f"group_{index}",
                                 text=f"{category}（{len(grouped[category])}）", open=True)
            if category not in categories:
                categories.append(category)
            for path, direction in grouped[category]:
                iid = f"sample_{len(paths)}"
                paths[iid] = path
                tree.insert(parent, "end", iid=iid,
                            text=f"{'← 向前' if direction == 'before' else '→ 向后'}  {path.name}")
                if selected_path == path:
                    tree.selection_set(iid)
                    tree.see(iid)
        category_editor.configure(values=categories)
        preview.configure(image="", text=f"共 {len(paths)} 个样本" +
                          (f"；{len(errors)} 个元数据异常，请检查" if errors else ""))
        photos.clear()

    def chosen_path():
        selection = tree.selection()
        return paths.get(selection[0]) if selection else None

    def selected(_event=None):
        path = chosen_path()
        if path is None:
            return
        try:
            meta = read_ref_sample_metadata(path)
            category_var.set(meta["category"])
            direction_var.set("向前" if meta["direction"] == "before" else "向后")
            with Image.open(path) as opened:
                sample = opened.convert("RGB")
                sample.thumbnail((500, 140))
                photo = ImageTk.PhotoImage(sample)
            photos.clear()
            photos.append(photo)
            preview.configure(image=photo, text="")
        except (OSError, ValueError) as exc:
            preview.configure(image="", text=f"读取样本失败：{exc}")

    def save():
        path = chosen_path()
        if path is None:
            return
        try:
            if path not in list_ref_samples(project.root):
                raise ValueError("选中的样本已不在项目中")
            write_ref_sample_metadata(
                path, category=category_var.get().strip(),
                direction="before" if direction_var.get() == "向前" else "after",
            )
        except (ValueError, OSError) as exc:
            messagebox.showerror("保存样本属性失败", str(exc), parent=window)
            return
        refresh(selected_path=path)
        selected()

    def delete():
        path = chosen_path()
        if path is None:
            return
        if not messagebox.askyesno("删除 REF 样本", f"删除该图样及其类别/方向属性？\n{path.name}", parent=window):
            return
        try:
            delete_ref_sample(path, project.root)
        except (OSError, ValueError) as exc:
            messagebox.showerror("删除失败", str(exc), parent=window)
        refresh()

    tree.bind("<<TreeviewSelect>>", selected)
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="保存选中样本的类别/方向", command=save).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="删除选中样本", command=delete).pack(side="left")
    ttk.Button(buttons, text="刷新列表", command=refresh).pack(side="right", padx=(0, 8))
    ttk.Button(buttons, text="关闭", command=window.destroy).pack(side="right")
    refresh()

def build_ref_box_settings_tab(dialog, tab: ttk.Frame) -> None:
    page = dialog._scrollable_settings_page(tab)
    dialog._settings_intro(
        page, "REF 框 · 词条中的参见/同义词/反义词跳转区域",
        "单页保存 data/ref_box/页名.rbox；九列 TSV：id、x、y、w、h、"
        "w.ww%、h.hh%、entry_index、text。百分比均以原图宽度为分母。"
        "与 PDIC/PPP 分离。"
        "用户已框选的 REF 永不被自动识别覆盖；自动检测只做本地样本图案匹配。",
    )
    dialog._add_setting_group(
        page, "原图 REF 定位框", REF_BOX_STYLE_FIELDS,
        intro="框体覆盖原书目标区域，默认内部完全透明，只用轮廓提示定位；"
              "修改框体颜色/透明度不会改变右侧的识别文本标签。",
    )
    dialog._add_check_group(
        page, "原图 REF 框操作", REF_BOX_CHECKS,
        intro="手动创建、框体挂靠、删除和显隐仅作用于原图 REF 区域。",
    )
    dialog._add_setting_group(
        page, "REF 文本标签（独立于原图框）", REF_TEXT_LABEL_FIELDS,
        intro="有文字时默认在原图框右侧以带底色的独立标签展示 OCR 文本，"              "页面右侧不足时自动放到左侧；原图字符不会被标签画在框内遮盖。"              "文字颜色、字体、字号、加粗/斜体和标签底色均只影响文本标签。",
    )
    dialog._add_check_group(
        page, "REF 文本标签显示", REF_TEXT_LABEL_CHECKS,
        intro="只隐藏或调整识别文本标签，不清空已保存文本，也不隐藏原图定位框。",
    )
    dialog._add_setting_group(
        page, "OCR REF 文本提取正则", REF_OCR_EXTRACTION_FIELDS,
        intro="直接编辑 Python 正则表达式；优先取参与匹配的第一个捕获组，"              "无捕获组则取完整匹配。未匹配或留空保留 OCR 原文。"
              "默认规则提取成对中文引号内容，并兼顾左右引号缺失。"
              "只对后续 OCR REF 生效；人工已填写内容不会被覆盖。",
    )
    geometry_group = dialog._add_setting_group(
        page, "画框比例与图样匹配", REF_BOX_GEOMETRY_FIELDS,
        intro="单击按行高倍数创建默认框；拖动以真实坐标创建自定义大小。"
              "识别匹配分越高越保守；任何颜色/语言的图案均可采样。",
    )
    for label, name in REF_BOX_GEOMETRY_CHECKS:
        if name not in dialog.vars:
            dialog.vars[name] = tk.BooleanVar(
                value=bool(getattr(dialog.parent.settings, name))
            )
        row_index = geometry_group.grid_size()[1]
        checkbox = ttk.Checkbutton(
            geometry_group, text=label, variable=dialog.vars[name],
        )
        checkbox.grid(row=row_index, column=0, columnspan=2,
                      sticky="w", padx=(8, 0), pady=(8, 5))
        info = ttk.Label(geometry_group, text="ⓘ", cursor="hand2")
        info.grid(row=row_index, column=2, sticky="w", padx=(8, 0))
        help_callback = lambda l=label, n=name: dialog._show_check_help(l, n)
        dialog._bind_help_widget(checkbox, help_callback)
        dialog._bind_help_widget(info, help_callback)
        info.bind("<Button-1>", lambda _event, fn=help_callback: fn(), add="+")
    controls = ttk.LabelFrame(page, text="样本图案采集 / 管理", padding=(12, 10))
    controls.pack(fill="x", pady=(0, 12))
    ttk.Label(
        controls,
        text="当前页使用【采集 REF 样本】后，在主画布拖选图案并松开。"
             "只保存局部 PNG 到项目 data/ref_box/samples；无在线上传。",
        wraplength=640, justify="left",
    ).pack(anchor="w", pady=(0, 8))

    capture_options = ttk.Frame(controls)
    capture_options.pack(fill="x", pady=(0, 8))
    ttk.Label(capture_options, text="采集类别").pack(side="left")
    capture_category = tk.StringVar(value="见")
    capture_direction = tk.StringVar(value="向后")
    category_picker = ttk.Combobox(capture_options, textvariable=capture_category,
                                   values=REF_SAMPLE_CATEGORIES, width=14)
    category_picker.pack(side="left", padx=(6, 16))
    ttk.Label(capture_options, text="目标方向").pack(side="left")
    ttk.Combobox(capture_options, textvariable=capture_direction, state="readonly",
                 values=("向后", "向前"), width=9).pack(side="left", padx=6)

    def category_changed(_event=None):
        capture_direction.set(
            "向前" if default_ref_sample_direction(capture_category.get().strip()) == "before"
            else "向后"
        )

    category_picker.bind("<<ComboboxSelected>>", category_changed)
    ttk.Label(controls, text="连续拖框采集；每次保存后保持采集模式。主画布右键或 Esc 结束。",
              wraplength=640).pack(anchor="w", pady=(0, 8))
    def capture():
        # Settings Center is modeless; sample is captured on the main canvas.
        dialog.parent.ref_box_controller.start_capture_sample(
            category=capture_category.get().strip(),
            direction="before" if capture_direction.get() == "向前" else "after",
        )

    actions = ttk.Frame(controls)
    actions.pack(fill="x")
    ttk.Button(actions, text="连续采集 REF 样本（主画布拖框）",
               command=capture).pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="管理 / 删除样本",
               command=lambda: show_ref_samples(dialog)).pack(side="left")
