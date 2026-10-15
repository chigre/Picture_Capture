"""REF settings, sample capture and local template management."""
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from PIL import Image, ImageTk

from ...ref_box_detection import list_ref_samples
from .schema import REF_BOX_STYLE_FIELDS, REF_BOX_GEOMETRY_FIELDS, REF_BOX_CHECKS


def show_ref_samples(dialog) -> None:
    project = dialog.parent.project
    if project is None:
        messagebox.showinfo("REF 样本", "请先打开词典项目", parent=dialog)
        return
    window = tk.Toplevel(dialog)
    window.title("管理 REF 样本图案")
    window.geometry("550x400")
    frame = ttk.Frame(window, padding=12)
    frame.pack(fill="both", expand=True)
    samples = list_ref_samples(project.root)
    lst = tk.Listbox(frame, height=8, exportselection=False)
    lst.pack(fill="x")
    preview = ttk.Label(frame, text="选择样本可查看本地采集的图案")
    preview.pack(fill="both", expand=True, pady=8)
    photos: list[ImageTk.PhotoImage] = []

    def refresh():
        nonlocal samples
        samples = list_ref_samples(project.root)
        lst.delete(0, "end")
        for index, path in enumerate(samples, start=1):
            lst.insert("end", f"{index:03d}  {path.name}")
        preview.configure(image="", text=f"共 {len(samples)} 个样本")
        photos.clear()

    def selected(_event=None):
        picks = lst.curselection()
        if not picks:
            return
        try:
            with Image.open(samples[int(picks[0])]) as opened:
                sample = opened.convert("RGB")
                sample.thumbnail((450, 200))
                photo = ImageTk.PhotoImage(sample)
            photos.clear()
            photos.append(photo)
            preview.configure(image=photo, text="")
        except (OSError, ValueError) as exc:
            preview.configure(text=f"读取失败：{exc}", image="")

    def delete():
        picks = lst.curselection()
        if not picks:
            return
        path = samples[int(picks[0])]
        if not messagebox.askyesno("删除 REF 样本", f"只删除此图案模板？\n{path.name}", parent=window):
            return
        try:
            # Restrict deletion to an actually enumerated project-local sample.
            if path not in list_ref_samples(project.root):
                raise RuntimeError("样本路径已变化")
            path.unlink()
        except OSError as exc:
            messagebox.showerror("删除失败", str(exc), parent=window)
        refresh()

    lst.bind("<<ListboxSelect>>", selected)
    tools = ttk.Frame(frame)
    tools.pack(fill="x")
    ttk.Button(tools, text="删除选中样本", command=delete).pack(side="left")
    ttk.Button(tools, text="关闭", command=window.destroy).pack(side="right")
    refresh()


def build_ref_box_settings_tab(dialog, tab: ttk.Frame) -> None:
    page = dialog._scrollable_settings_page(tab)
    dialog._settings_intro(
        page, "REF 框 · 词条中的参见/同义词/反义词跳转区域",
        "单页保存 data/ref_box/页名.rbox；七列 TSV：id、x、y、w、h、"
        "entry_index、text。与 PDIC/PPP 完全分离。"
        "用户已框选的 REF 永不被自动识别覆盖；自动检测只做本地样本图案匹配。",
    )
    group = dialog._add_setting_group(
        page, "REF 文字与半透明显示", REF_BOX_STYLE_FIELDS,
        intro="默认系统推荐字体、16 号、淡蓝色 50% 不透明度、无边框。"
              "颜色填 #RRGGBB；仅改变显示，不改变 rbox 坐标。",
    )
    # The setting group owns the same tk.Variable used by autosave.
    for name in ("ref_box_fill_color", "ref_box_text_color"):
        v = dialog.vars.get(name)
        if v is None:
            continue
        index = list(REF_BOX_STYLE_FIELDS).index(name) + 1
        cell = group.grid_slaves(row=index, column=1)
        if cell:
            def choose(var=v):
                color = colorchooser.askcolor(color=str(var.get()), parent=dialog)[1]
                if color:
                    var.set(color)
            ttk.Button(cell[0], text="选色…", command=choose).grid(
                row=0, column=2, padx=(7, 0),
            )
    dialog._add_check_group(page, "显示与默认挂靠", REF_BOX_CHECKS)
    dialog._add_setting_group(
        page, "画框比例与图样匹配", REF_BOX_GEOMETRY_FIELDS,
        intro="单击按行高倍数创建默认框；拖动以真实坐标创建自定义大小。"
              "识别匹配分越高越保守；任何颜色/语言的图案均可采样。",
    )
    controls = ttk.LabelFrame(page, text="样本图案采集 / 管理", padding=(12, 10))
    controls.pack(fill="x", pady=(0, 12))
    ttk.Label(
        controls,
        text="当前页使用【采集 REF 样本】后，在主画布拖选图案并松开。"
             "只保存局部 PNG 到项目 data/ref_box/samples；无在线上传。",
        wraplength=640, justify="left",
    ).pack(anchor="w", pady=(0, 8))

    def capture():
        # Settings Center is modeless; sample is captured on the main canvas.
        dialog.parent.ref_box_controller.start_capture_sample()

    actions = ttk.Frame(controls)
    actions.pack(fill="x")
    ttk.Button(actions, text="采集 REF 样本（主画布拖框）",
               command=capture).pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="管理 / 删除样本",
               command=lambda: show_ref_samples(dialog)).pack(side="left")
