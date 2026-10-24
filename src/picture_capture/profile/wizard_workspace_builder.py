"""Owner for Profile Wizard persistent representative-image workspace."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tkinter import ttk


def build_right_image_workspace(self, parent: ttk.Frame, *, deps) -> None:
    ttk = deps["ttk"]
    tk = deps["tk"]
    """Persistent image-only workspace shared by all Wizard steps."""
    host = ttk.LabelFrame(parent, text="图片预览", padding=6)
    host.grid(row=0, column=0, sticky="nsew")
    host.rowconfigure(1, weight=1)
    host.columnconfigure(0, weight=1)

    self.right_heading_var = tk.StringVar(value="代表页（前部 / 中部 / 后部）")
    ttk.Label(
        host, textvariable=self.right_heading_var,
        font=("TkDefaultFont", 11, "bold"),
    ).grid(row=0, column=0, sticky="w", pady=(0, 5))

    canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=1, column=0, sticky="nsew")
    scrollbar.grid(row=1, column=1, sticky="ns")
    self.right_canvas = canvas

    content = ttk.Frame(canvas, padding=(2, 2, 6, 6))
    self.right_content = content
    self._right_window = canvas.create_window((0, 0), window=content, anchor="nw")
    content.columnconfigure(0, weight=1)
    content.bind(
        "<Configure>",
        lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.bind(
        "<Configure>",
        lambda e: canvas.itemconfigure(self._right_window, width=e.width),
    )
    self.right_image_pages: list[ttk.Frame] = []
    for _ in range(4):
        page = ttk.Frame(content)
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        self.right_image_pages.append(page)

    # Step 1: six editable representative pages.
    sample_page = self.right_image_pages[0]
    sample_page.rowconfigure(0, weight=1)
    self.sample_frame = ttk.Frame(sample_page)
    self.sample_frame.grid(row=0, column=0, sticky="nsew")
    self.sample_frame.rowconfigure(0, weight=1)
    for column in range(3):
        self.sample_frame.columnconfigure(column, weight=1, uniform="sample")

    # Step 2: one live page-template preview at a time.
    template_page = self.right_image_pages[1]
    template_nav = ttk.Frame(template_page)
    template_nav.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    ttk.Button(
        template_nav, text="◀ 上一张",
        command=lambda: self._move_template_preview(-1),
    ).pack(side="left")
    ttk.Button(
        template_nav, text="下一张 ▶",
        command=lambda: self._move_template_preview(1),
    ).pack(side="right")
    self.template_preview_caption_var = tk.StringVar(value="")
    ttk.Label(
        template_nav, textvariable=self.template_preview_caption_var,
    ).pack(side="left", expand=True)
    self.template_preview_frame = ttk.Frame(template_page)
    self.template_preview_frame.grid(row=1, column=0, sticky="nsew")
    self.template_preview_frame.columnconfigure(0, weight=1)

    # Step 3: one fixed example image for each built-in headword type.
    examples_page = self.right_image_pages[2]
    self.headword_examples_frame = ttk.Frame(examples_page)
    self.headword_examples_frame.grid(row=0, column=0, sticky="ew")
    self.headword_examples_frame.columnconfigure(0, weight=1)
    self.headword_examples_frame.columnconfigure(1, weight=1)

    # Step 4: one full-width validation page at a time.
    validation_page = self.right_image_pages[3]
    nav = ttk.Frame(validation_page)
    nav.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    self.validation_prev_button = ttk.Button(
        nav, text="◀ 上一页",
        command=lambda: self._move_validation_preview(-1), state="disabled",
    )
    self.validation_prev_button.pack(side="left")
    self.validation_fit_mode = "height"
    ttk.Button(
        nav, text="适合高度",
        command=lambda: self._set_validation_fit("height"),
    ).pack(side="left", padx=(6, 0))
    ttk.Button(
        nav, text="适合宽度",
        command=lambda: self._set_validation_fit("width"),
    ).pack(side="left", padx=(6, 0))
    self.validation_caption_var = tk.StringVar(value="")
    ttk.Label(nav, textvariable=self.validation_caption_var).pack(
        side="left", expand=True
    )
    self.validation_next_button = ttk.Button(
        nav, text="下一页 ▶",
        command=lambda: self._move_validation_preview(1), state="disabled",
    )
    self.validation_next_button.pack(side="right")
    self.validation_frame = ttk.Frame(validation_page)
    self.validation_frame.grid(row=1, column=0, sticky="ew")
    self.validation_frame.columnconfigure(0, weight=1)

