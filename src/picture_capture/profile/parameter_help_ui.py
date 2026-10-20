from __future__ import annotations

"""Keep parameter controls compact while showing explanations on the right.

The Settings dialog already owns a right-side help pane, but older builders also
rendered the same long explanation below every field.  Project Profile had the
opposite problem: rich parameter explanations lived only in the left scroll pane
while the right pane was image-only.  This module makes the two surfaces follow
one rule without changing persisted settings or detection behavior:

* left = control, value/unit, short status;
* right = full explanation for the currently focused/hovered parameter;
* Project Profile keeps its image preview below the explanation box.
"""

import tkinter as tk
from tkinter import ttk
from typing import Any, Iterable


def _descendants(root: tk.Misc) -> Iterable[tk.Misc]:
    for child in root.winfo_children():
        yield child
        yield from _descendants(child)


def _grid_row(widget: tk.Misc) -> int | None:
    try:
        value = widget.grid_info().get("row")
        return int(value) if value not in (None, "") else None
    except (tk.TclError, TypeError, ValueError):
        return None


def _grid_column(widget: tk.Misc) -> int | None:
    try:
        value = widget.grid_info().get("column")
        return int(value) if value not in (None, "") else None
    except (tk.TclError, TypeError, ValueError):
        return None


def _widgets_on_row(frame: tk.Misc, row: int) -> list[tk.Misc]:
    return [child for child in frame.winfo_children() if _grid_row(child) == int(row)]


def _find_label_frame(root: tk.Misc, text: str) -> ttk.LabelFrame | None:
    for child in _descendants(root):
        if not isinstance(child, ttk.LabelFrame):
            continue
        try:
            if str(child.cget("text")) == text:
                return child
        except tk.TclError:
            continue
    return None


def _remove_labels_on_row(frame: tk.Misc, row: int) -> None:
    for child in _widgets_on_row(frame, row):
        if isinstance(child, (ttk.Label, tk.Label)):
            try:
                child.grid_remove()
            except tk.TclError:
                pass


def _bind_profile_help(
    owner: Any,
    widgets: Iterable[tk.Misc],
    title: str,
    body: str,
) -> None:
    def show(_event=None) -> None:
        owner._set_profile_parameter_help(title, body)

    for widget in widgets:
        try:
            widget.bind("<Enter>", show, add="+")
            widget.bind("<FocusIn>", show, add="+")
            widget.bind("<Button-1>", show, add="+")
        except (tk.TclError, AttributeError):
            pass


def _add_info_label(
    owner: Any,
    frame: ttk.Frame,
    row: int,
    title: str,
    body: str,
    *,
    text: str = "ⓘ",
    column: int = 2,
) -> ttk.Label:
    info = ttk.Label(frame, text=text, foreground="#6b7280", cursor="hand2")
    info.grid(row=row, column=column, sticky="w", padx=(6, 0), pady=3)
    _bind_profile_help(owner, [info], title, body)
    return info


PROFILE_STEP_HELP: tuple[tuple[str, str], ...] = (
    (
        "词典与阅读",
        "左侧填写项目资料与阅读/OCR设置。把鼠标停在参数或进入输入框时，右侧这里显示该项的作用；下方继续显示代表页。",
    ),
    (
        "页面模板参数",
        "左侧只保留页面模板的控制项。参数的含义、调节方向和影响范围显示在这里；下方仍是实时页面模板预览。",
    ),
    (
        "词头结构参数",
        "左侧只保留词头结构、符号样本与阈值控件。把鼠标停在控件上或用 Tab 进入后，这里显示完整解释；下方仍保留词头样例。",
    ),
    (
        "测试确认",
        "测试页主要用于比较实际画线结果。页面理解与模式诊断仍显示在左侧状态区；右侧下方显示当前测试页。",
    ),
)


def build_profile_parameter_help_wizard(base_class: type[Any]) -> type[Any]:
    """Wrap Project Profile with a persistent right-side parameter help area."""

    class ProjectProfileWizard(base_class):
        def _build_right_image_workspace(self, parent: ttk.Frame) -> None:
            shell = ttk.Frame(parent)
            shell.grid(row=0, column=0, sticky="nsew")
            shell.columnconfigure(0, weight=1)
            shell.rowconfigure(1, weight=1)

            help_box = ttk.LabelFrame(shell, text="参数说明", padding=(10, 8))
            help_box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
            help_box.columnconfigure(0, weight=1)
            self.profile_parameter_help_title_var = tk.StringVar(
                value=PROFILE_STEP_HELP[0][0]
            )
            self.profile_parameter_help_body_var = tk.StringVar(
                value=PROFILE_STEP_HELP[0][1]
            )
            ttk.Label(
                help_box,
                textvariable=self.profile_parameter_help_title_var,
                font=("TkDefaultFont", 10, "bold"),
                justify="left",
            ).grid(row=0, column=0, sticky="w")
            help_body = ttk.Label(
                help_box,
                textvariable=self.profile_parameter_help_body_var,
                foreground="#555b63",
                justify="left",
            )
            help_body.grid(row=1, column=0, sticky="ew", pady=(5, 0))
            help_box.bind(
                "<Configure>",
                lambda event, label=help_body: label.configure(
                    wraplength=max(240, int(event.width) - 28)
                ),
                add="+",
            )

            image_host = ttk.Frame(shell)
            image_host.grid(row=1, column=0, sticky="nsew")
            image_host.columnconfigure(0, weight=1)
            image_host.rowconfigure(0, weight=1)
            super()._build_right_image_workspace(image_host)

        def _set_profile_parameter_help(self, title: str, body: str) -> None:
            if hasattr(self, "profile_parameter_help_title_var"):
                self.profile_parameter_help_title_var.set(str(title))
            if hasattr(self, "profile_parameter_help_body_var"):
                self.profile_parameter_help_body_var.set(str(body))

        def _on_wizard_tab_changed(self, event=None) -> None:
            super()._on_wizard_tab_changed(event)
            try:
                index = int(self.notebook.index(self.notebook.select()))
            except (tk.TclError, ValueError):
                return
            index = max(0, min(len(PROFILE_STEP_HELP) - 1, index))
            title, body = PROFILE_STEP_HELP[index]
            if index == 2:
                hint = str(
                    getattr(self, "headword_specificity_hint_var", tk.StringVar(value="")).get()
                    if hasattr(self, "headword_specificity_hint_var")
                    else ""
                ).strip()
                if hint:
                    body = hint + "\n\n" + body
            self._set_profile_parameter_help(title, body)

        def _build_template_tab(self, tab: ttk.Frame) -> None:
            super()._build_template_tab(tab)
            self._install_template_parameter_help(tab)

        def _install_template_parameter_help(self, tab: ttk.Frame) -> None:
            body = _find_label_frame(tab, "正文与分栏")
            if body is not None:
                _remove_labels_on_row(body, 1)
                column_help = (
                    "正文栏数",
                    "代表页会自动分析并建议栏数；确认后作为项目的稳定栏数使用。若词典正文始终为固定栏数，应保持这一项目级值稳定，而不是让某一页的插图或空白改变它。",
                )
                _bind_profile_help(self, _widgets_on_row(body, 0), *column_help)
                _add_info_label(self, body, 0, *column_help)
                separator_help = (
                    "中央分隔线",
                    "告诉版面分析栏间是否存在明显印刷分隔线。自动判断适合大多数页面；明确有/无稳定分隔线时可直接指定，以减少栏边搜索歧义。",
                )
                _bind_profile_help(self, _widgets_on_row(body, 2), *separator_help)
                _add_info_label(self, body, 2, *separator_help)

            edges = _find_label_frame(tab, "页眉 / 页尾 / 页边")
            if edges is not None:
                _remove_labels_on_row(edges, 9)
                help_by_row = {
                    0: ("页眉模式", "自动检测会根据当前页结构估计正文上边界；明确没有页眉时不额外排除；固定页眉适合整本词典顶部占位区域稳定的版式。"),
                    1: ("页眉排除高度", "仅在选择固定页眉时生效，表示从页面顶部排除的高度百分比。数值过大会切掉第一条正文，过小则可能把 running header / 页码纳入正文。"),
                    2: ("页尾模式", "控制页面底部是否需要固定排除。无稳定页尾内容时保持“不排除页尾”；固定页尾用于整本词典底部区域稳定的情况。"),
                    3: ("页尾排除高度", "仅在固定页尾模式下生效，按页面高度百分比排除底部区域。"),
                    4: ("页边内容", "用于装订边、外侧索引、固定页边注等不属于正文栏的占位内容。A/B 外侧或内侧交替适合左右页扫描交替的书籍。"),
                    5: ("固定页边宽度", "左侧固定或右侧固定模式下使用，按页面宽度百分比排除页边内容。"),
                    6: ("A 页排除宽度", "A/B 交替模式下 A 页的页边排除宽度，可与 B 页不同。"),
                    7: ("B 页排除宽度", "A/B 交替模式下 B 页的页边排除宽度，可与 A 页不同。"),
                    8: ("A/B 起始页", "只在外侧/内侧交替模式下有意义。第一张扫描若属于 B 页，可在这里整体翻转 A/B 交替关系。"),
                }
                for row, help_pair in help_by_row.items():
                    _bind_profile_help(self, _widgets_on_row(edges, row), *help_pair)

            indent = _find_label_frame(tab, "缩进版式")
            if indent is not None:
                _remove_labels_on_row(indent, 1)
                indent_help = (
                    "缩进版式",
                    "这是整本词典的页面排版语义，与词头是大字、【】、编号或普通文字无关。词头缩进＝entry 比正文更靠栏内；正文缩进＝正文比 entry 更靠栏内；无明显缩进＝两者基本同栏起点，不使用缩进方向判定词条。",
                )
                _bind_profile_help(self, _widgets_on_row(indent, 0), *indent_help)
                _add_info_label(self, indent, 0, *indent_help)

            adaptive = _find_label_frame(tab, "逐页版面适配")
            if adaptive is not None:
                _remove_labels_on_row(adaptive, 1)
                adaptive_help = (
                    "逐页版面适配",
                    "开启后，每页先独立估计版面；只把下方勾选字段替换成当前页检测值，未勾选字段继续使用 Project Profile 固定值。本页结果不会传给下一页。适合扫描位置逐页轻微漂移。",
                )
                _bind_profile_help(self, _widgets_on_row(adaptive, 0), *adaptive_help)
                auto_field_help = {
                    "分栏数": "勾选后允许当前页重新估计栏数；栏数固定的词典通常不需要逐页变化。",
                    "正文起始Y": "勾选后允许正文上边界逐页适配，适合页眉位置或裁切上下轻微漂移。",
                    "首栏X": "勾选后允许整页左右平移时重新估计第一栏起点。",
                    "单栏宽": "勾选后允许当前页重新估计栏宽；版式固定时通常保持项目值更稳定。",
                    "栏间空": "勾选后允许当前页重新估计栏间距。",
                    "普通字/行高": "勾选后允许当前页重新估计普通正文的行高尺度。",
                    "行间空": "勾选后允许当前页重新估计普通行之间的空白尺度。",
                }
                for widget in _descendants(adaptive):
                    if not isinstance(widget, ttk.Checkbutton):
                        continue
                    try:
                        label = str(widget.cget("text"))
                    except tk.TclError:
                        continue
                    if label in auto_field_help:
                        _bind_profile_help(
                            self,
                            [widget],
                            f"逐页适配：{label}",
                            auto_field_help[label] + " 未勾选时始终使用 Project Profile 的固定值。",
                        )

        def _build_headword_tab(self, tab: ttk.Frame) -> None:
            super()._build_headword_tab(tab)
            self._install_headword_parameter_help(tab)

        def _install_headword_parameter_help(self, tab: ttk.Frame) -> None:
            tail = getattr(self, "tail_structure_frame", None)
            if tail is not None:
                _remove_labels_on_row(tail, 8)
                _remove_labels_on_row(tail, 9)
                tail_required = (
                    "普通左缘词的词后证据",
                    "开启后，普通栏左词必须命中至少一种已勾选的 POS、词形/屈折、变体、发音或描述型结构。固定符号、编号等强前缀仍可作为独立边界证据。",
                )
                tail_rescue = (
                    "词后结构 OCR 失败时的视觉补救",
                    "开启后，OCR 没读出词后结构时允许由严格栏左缘 + 粗体等视觉证据补救。补救直接使用下方可见的【栏左缘容差】【粗体倍率】【候选强度】，不再叠加隐藏门槛。",
                )
                _bind_profile_help(self, _widgets_on_row(tail, 6), *tail_required)
                _bind_profile_help(self, _widgets_on_row(tail, 7), *tail_rescue)
                _add_info_label(self, tail, 6, *tail_required, column=1)
                _add_info_label(self, tail, 7, *tail_rescue, column=1)

            symbol = getattr(self, "symbol_inventory_frame", None)
            if symbol is not None:
                for row in (2, 4, 6, 8, 10):
                    _remove_labels_on_row(symbol, row)
                symbol_help = {
                    1: ("独立入口标记", "只填写 ○、●、◆ 等独立词条前缀；【不要填这里】。可连续输入，也可用空格或逗号分隔。独立入口标记可作为强边界证据。"),
                    3: ("括号词头起始", "默认【。括号内文字才是词头；它属于 bracket_open，而不是独立 entry_marker。若词典使用〔［「等，再按实际版式添加。"),
                    5: ("视觉形状补救", "OCR 经常漏掉/错认入口符号或括号时才开启。视觉样本直接从扫描像素匹配；括号样本仍保持 bracket_open 角色，不会变成独立入口标记。"),
                    7: ("marker lane 过滤", "开启后，只接受落在本栏稳定标记带附近的视觉符号，可减少正文中相似圆点、方块或括号造成的误检。"),
                    9: ("marker lane 容差", "以普通行高百分比表示允许视觉标记偏离稳定 marker lane 的距离。越小越严格；默认 50%。"),
                }
                for row, help_pair in symbol_help.items():
                    _bind_profile_help(self, _widgets_on_row(symbol, row), *help_pair)
                _add_info_label(self, symbol, 9, *symbol_help[9], text="% 行高  ⓘ")

                visual = _find_label_frame(symbol, "本词典视觉标记样本")
                if visual is not None:
                    _remove_labels_on_row(visual, 6)
                    visual_help = {
                        0: ("视觉样本识别方式", "字符符号集 + 视觉样本会同时使用配置字符与真实扫描模板；仅字符符号集关闭模板匹配；视觉样本优先则在已有模板时优先相信模板族。"),
                        1: ("视觉样本组织", "按角色合并适合多个不同外观但语义相同的入口标记；按具体符号区分适合不同符号承担不同结构意义的词典。"),
                        2: ("最低模板匹配分数", "视觉模板匹配的最低接受分数。默认 0.68；真实扫描差异较大时可适度降低，但过低会增加正文中相似形状的误命中。"),
                        3: ("记录模板诊断", "开启后在 OCR/候选诊断中记录模板匹配分数与样本来源，便于定位某个视觉样本为什么命中或未命中。"),
                        5: ("视觉标记样本", "直接框选真实印刷符号。采【时按“括号起始”保存，不会当成独立入口标记；每类建议采 2–5 个来自不同页面的样本。"),
                    }
                    for row, help_pair in visual_help.items():
                        _bind_profile_help(self, _widgets_on_row(visual, row), *help_pair)
                    for child in _widgets_on_row(visual, 2):
                        if isinstance(child, (ttk.Label, tk.Label)) and _grid_column(child) == 2:
                            try:
                                child.configure(text="ⓘ", cursor="hand2")
                            except tk.TclError:
                                pass
                            _bind_profile_help(self, [child], *visual_help[2])

            specificity = getattr(self, "headword_specificity_frame", None)
            if specificity is not None:
                _remove_labels_on_row(specificity, 0)
                parameter_help = {
                    1: ("栏左缘容差", "允许词头起点偏离栏左边界的最大距离，以单栏宽百分比表示。越小越严格；过小会漏掉轻微扫描偏移或排版偏移，过大则更容易把正文行纳入候选。"),
                    2: ("文字大小倍率", "候选文字高度相对普通正文文字尺度的倍率下限。主要用于视觉突出型词头；普通拉丁词典通常不要把字号当成唯一证据。"),
                    3: ("粗体倍率", "候选词头相对本页普通正文的墨迹/粗体强度倍率下限。数值越高越严格；用于 OCR 词后结构缺失时的视觉补救。"),
                    4: ("候选强度", "综合候选证据达到的最低强度门槛。它是候选层阈值，不应替代词典结构本身；出现稳定重复的误检/漏检模式时再调整。"),
                }
                for row, help_pair in parameter_help.items():
                    _bind_profile_help(self, _widgets_on_row(specificity, row), *help_pair)
                for child in _widgets_on_row(specificity, 1):
                    if isinstance(child, (ttk.Label, tk.Label)) and _grid_column(child) == 2:
                        try:
                            child.configure(text="% 单栏宽  ⓘ", cursor="hand2")
                        except tk.TclError:
                            pass
                        _bind_profile_help(self, [child], *parameter_help[1])
                for row in (2, 3, 4):
                    _add_info_label(self, specificity, row, *parameter_help[row])

            cjk = getattr(self, "cjk_specificity_frame", None)
            if cjk is not None:
                cjk_help = {
                    0: ("CJK：必须靠近栏左缘", "开启后，大字单字/括号词还需要位于词条侧的栏起始区域，减少正文内部相似结构误检。"),
                    2: ("CJK：必须视觉突出", "开启后，只有明显区别于普通正文的单字/括号结构才作为词头；适合正文中也经常出现相似字符结构的页面。"),
                    3: ("大字右侧留白分析", "仅辅助大字单字判断。程序检查大字右侧局部留白/密度是否符合独立展示词头，而不是把正文中的大号字符直接当词条。"),
                    4: ("大字右侧检测宽度", "以检测到的大字高度百分比表示右侧上下文分析宽度。默认 80%；同时参考整体、下部留白和相对正文密度。"),
                }
                for row, help_pair in cjk_help.items():
                    _bind_profile_help(self, _widgets_on_row(cjk, row), *help_pair)
                for child in _widgets_on_row(cjk, 4):
                    if isinstance(child, (ttk.Label, tk.Label)) and _grid_column(child) == 2:
                        try:
                            child.configure(text="% 大字高度  ⓘ", cursor="hand2")
                        except tk.TclError:
                            pass
                        _bind_profile_help(self, [child], *cjk_help[4])

    ProjectProfileWizard.__name__ = "ProjectProfileWizard"
    ProjectProfileWizard.__qualname__ = "ProjectProfileWizard"
    return ProjectProfileWizard


def install_settings_parameter_help(app_module: Any) -> None:
    """Compatibility no-op; SettingsDialog help ownership is static."""
    _ = app_module
