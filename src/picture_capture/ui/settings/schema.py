from __future__ import annotations

from . import help_catalog as _help_catalog

"""Static Settings Center metadata.

The dialog keeps compatibility class attributes that reference these exact
objects, while runtime extensions remain free to replace attributes on the
dialog class without creating a dependency back into ``app.py``.
"""

FIELDS = [
        ("共享分析图去噪强度", "analysis_denoise_strength", str),
        ("词典完整名称", "dictionary_full_name", str),
        ("词典缩写名称", "dictionary_abbreviation", str),
        ("ISBN", "dictionary_isbn", str),
        ("索引语言", "dictionary_index_language", str),
        ("内容语言", "dictionary_content_language", str),
        ("正文页码范围", "dictionary_body_page_range", str),
        ("自定义 Profile 名称", "dictionary_custom_profile_name", str),
        ("词典分栏", "columns", int), ("两栏中隔", "gutter", float),
        ("单栏宽距", "column_width", float), ("起始点 Y", "start_y", float),
        ("正文结束 Y", "bottom_y", int), ("首栏 X", "manual_x", float),
        ("正文缩进", "body_indent", float), ("单行字高", "character_height", float),
        ("行间空白", "row_padding", float), ("向右比例 %", "right_ratio", float),
        ("切图宽度(%栏)", "crop_width_percent", float),
        ("VB 向右比例 1/x", "ordinary_right_divisor", float),
        ("物理行墨迹投影采样宽度（%栏宽）", "physical_row_projection_width_percent", float),
        ("微调判距", "horizontal_tolerance", float), ("标记线高", "marker_height", int),
        ("词头横线不透明度", "headword_marker_opacity", float),
        ("垂直线宽", "guide_width", int), ("栏左垂线不透明度", "guide_opacity", float),
        ("插图区域不透明度", "illustration_fill_opacity", float),
        ("黑色阈值 RGB 和", "darkness_threshold", int),
        ("候选区域白度上限 %", "dark_area_percent", float),
        ("VB 全白阈值上限", "white_threshold_high", int),
        ("VB 白度阈值下限", "white_threshold_low", int),
        ("VB 白带修正量", "whitespace_adjustment", int),
        ("VB 向上比例 1/x", "upward_ratio", float),
        ("检测后跳步（行高倍数）", "row_step_multiplier", float),
        ("普通分析左边界", "analysis_left", float),
        ("普通分析右边界", "analysis_right", float),
        ("自动保存间隔（秒）", "batch_interval", float),
        ("插图自动识别外扩（px）", "illustration_detect_padding", int),
        ("插图自动识别右侧外扩（px）", "illustration_detect_right_padding", int),
        ("检测灰度阈值", "illustration_detect_gray_threshold", int),
        ("插图识别并行进程数（0=自动）", "illustration_detect_parallel_workers", int),
        ("候选最小宽度", "illustration_detect_min_width", float),
        ("候选最小高度", "illustration_detect_min_height", float),
        ("尺寸单位（% / px）", "illustration_detect_size_unit", str),
        ("候选最小墨迹占比（%）", "illustration_detect_min_occupancy_percent", float),
        ("插图轮廓色", "illustration_outline_color", str),
        ("插图轮廓线宽", "illustration_outline_width", int),
        ("插图区域背景色", "illustration_fill_color", str),
        ("插图标签边框色", "illustration_label_border_color", str),
        ("插图标签边框宽", "illustration_label_border_width", int),
        ("插图标签背景色", "illustration_label_fill_color", str),
        ("插图标签字体", "illustration_label_font_family", str),
        ("插图标签字号", "illustration_label_font_size", int),
        ("REF 未填写底色（淡橙）", "ref_box_fill_color", str),
        ("REF 未填写底色不透明度 %", "ref_box_fill_opacity", float),
        ("REF 已填写底色（淡绿）", "ref_box_filled_color", str),
        ("REF 已填写底色不透明度 %", "ref_box_filled_opacity", float),
        ("REF 文本标签文字颜色", "ref_box_text_color", str),
        ("REF 文本标签字体", "ref_box_font_family", str),
        ("REF 文本标签字号", "ref_box_font_size", int),
        ("REF ×／编辑按钮位置", "ref_box_action_position", str),
        ("REF 文本标签底色", "ref_text_label_background_color", str),
        ("REF 文本标签底色不透明度 %", "ref_text_label_background_opacity", float),
        ("REF 文本标签与原图框距离 px", "ref_text_label_gap", int),
        ("REF 文本标签内边距 px", "ref_text_label_padding", int),
        ("OCR REF 提取正则", "ref_ocr_extract_regex", str),
        ("REF 默认宽度（行高倍数）", "ref_box_width_lines", float),
        ("REF 默认高度（行高倍数）", "ref_box_height_lines", float),
        ("REF 样本最低匹配分 0.60–0.999", "ref_match_threshold", float),
        ("REF 样本跨页缩放容差 ±%", "ref_match_scale_tolerance_percent", float),
        ("OCR 语言", "ocr_language", str),
        ("Tesseract 语言", "tesseract_language", str),
        ("书写模式", "layout_writing_mode", str),
        ("文字方向", "layout_text_direction", str),
        ("内部版面变换", "layout_transform", str),
        ("栏数策略", "layout_columns_policy", str),
        ("中央分隔线", "layout_column_separator_mode", str),
        ("分析阈值", "analysis_threshold_mode", str),
        ("栏左跟随搜索范围（%栏宽）", "column_track_radius", float),
        ("栏左跟随分块高度（%正文高）", "column_track_block_height", float),
        ("栏左最大局部斜率（%块高）", "column_track_max_step", float),
        ("PaddleOCR 语言", "paddle_language", str),
        ("PaddleOCR 模型版本", "paddle_ocr_version", str),
        ("OCR图像预处理", "paddle_preprocessing", str),
        ("OCR输入最大长边（px）", "paddle_max_input_side", int),
        ("候选带宽比例（%）", "paddle_band_width_ratio", float),
        ("候选带左侧余量", "paddle_band_left_margin", int),
        ("AI 左缘容差", "paddle_left_tolerance", float),
        ("AI 候选置信度", "paddle_rec_score_threshold", float),
        ("AI 同行合并Y比", "paddle_line_merge_y_ratio", float),
        ("AI 字高比阈值", "paddle_height_ratio", float),
        ("AI 粗体比阈值", "paddle_boldness_ratio", float),
        ("AI 行前空白比", "paddle_gap_ratio", float),
        ("AI 最低候选分", "paddle_min_candidate_score", float),
        ("AI 页眉横线搜索高度", "paddle_header_search_height", float),
        ("AI 页眉横线墨迹比例", "paddle_header_rule_ink_ratio", float),
        ("AI 页眉横线后余量", "paddle_header_rule_margin", int),
        ("AI 词性搜索字符数", "paddle_pos_search_chars", int),
        ("横线搜索半径（行高比）", "paddle_separator_search_ratio", float),
        ("墨迹平滑／笔画小断点（px）", "paddle_separator_band_radius", int),
        ("精修上缘最小留白（px）", "paddle_separator_safety_px", int),
        ("横线横向取样比例（% 单栏）", "paddle_separator_roi_width_ratio", float),
        ("横线Y精修栏边余量（px）", "paddle_separator_column_margin", int),
        ("精修硬性最大位移（行高比）", "separator_y_max_shift_ratio", float),
        ("原图白缝核验最大偏移（行高比）", "separator_y_ink_safe_max_fraction", float),
        ("原图白缝核验墨迹灰度阈值", "separator_y_ink_safe_ink_threshold", int),
        ("原横线允许墨迹比例", "separator_y_ink_safe_existing_ink_ratio", float),
        ("候选白缝最大墨迹比例", "separator_y_ink_safe_gap_ink_ratio", float),
        ("Tesseract 对照 PSM", "paddle_tesseract_psm", int),
        ("Google Lens 超时（秒）", "paddle_lens_timeout", int),
        ("Lens无置信度默认值", "paddle_lens_default_confidence", float),
        ("双OCR Y容差（行高比）", "paddle_alignment_y_tolerance_ratio", float),
        ("双OCR 最低lemma相似度", "paddle_alignment_min_similarity", float),
        ("冲突自动选择质量差", "paddle_conflict_review_margin", float),
        ("AI 词头提取正则", "paddle_headword_regex", str),
        ("AI 词性提示正则", "paddle_pos_regex", str),
        ("AI 特殊符号正则", "paddle_special_symbol_regex", str),
        ("主界面字体", "main_entry_font_family", str),
        ("主界面字号（100%）", "main_entry_font_size", int),
        ("竖排词框长度（字符；横排自动至栏末）", "main_entry_width_chars", int),
        ("主界面词框横向位置（栏宽比例）", "main_entry_x_ratio", float),
        ("校对界面字体", "review_entry_font_family", str),
        ("校对界面字号", "review_entry_font_size", int),
        ("校对文本框上下边距（px）", "review_entry_vertical_padding", int),
        ("校对单字行高（0=中文自动2.5×）", "review_single_cjk_line_height", int),
        ("校对缩放（0=自动适宽）", "review_zoom_percent", float),
        ("wordslist.txt 位置", "wordslist_path", str),
    ]

PROFILE_FIELD_GROUPS = [
        ("Profile v3 版面", [
            "layout_writing_mode", "layout_text_direction", "layout_transform",
            "layout_columns_policy", "layout_column_separator_mode", "analysis_threshold_mode",
        ]),
        ("OCR 与语言", ["ocr_language", "paddle_language", "tesseract_language"]),
        ("版式证据", [
            "columns", "paddle_band_width_ratio", "paddle_band_left_margin", "paddle_left_tolerance",
            "paddle_height_ratio", "paddle_boldness_ratio", "paddle_gap_ratio",
            "paddle_min_candidate_score", "paddle_pos_search_chars",
        ]),
        ("横线定位", [
            "paddle_separator_search_ratio", "paddle_separator_band_radius",
            "paddle_separator_safety_px", "paddle_separator_roi_width_ratio",
            "paddle_separator_column_margin",
        ]),
    ]

PROFILE_CHECKS = [
        ("PaddleOCR 启用文字行方向识别", "paddle_use_textline_orientation"),
        ("候选必须具有结构/视觉提示", "paddle_require_visual_cue"),
        ("候选必须有词性/变形/词条符号", "paddle_require_pos_or_symbol"),
        ("去除词头音节分隔点", "paddle_remove_syllable_separators"),
        ("自动忽略页眉横线以上", "paddle_auto_header_rule"),
        ("词头横线 Y 按栏内墨迹谷精修", "paddle_refine_separator_y"),
    ]

FIELD_GROUPS = [
        ("版面几何", [
            "gutter", "column_width", "start_y", "manual_x",
            "body_indent", "character_height", "row_padding", "crop_width_percent",
            "horizontal_tolerance", "darkness_threshold",
        ]),
        ("词条线显示", ["right_ratio", "marker_height", "headword_marker_opacity", "guide_width", "guide_opacity"]),
        ("主界面词条文本框", [
            "main_entry_font_family", "main_entry_font_size", "main_entry_width_chars", "main_entry_x_ratio",
        ]),
        ("词条校对文本框", [
            "review_entry_font_family", "review_entry_font_size", "review_entry_vertical_padding",
            "review_single_cjk_line_height", "review_zoom_percent",
        ]),
        ("辅助词表", ["wordslist_path"]),
        ("列跟踪", ["column_track_radius", "column_track_block_height", "column_track_max_step"]),
        ("OCR 基础", [
            "paddle_ocr_version",
            "paddle_preprocessing", "paddle_max_input_side", "batch_interval",
        ]),
        ("PaddleOCR 候选与版面（高级）", [
            "paddle_rec_score_threshold", "paddle_line_merge_y_ratio",
            "paddle_header_search_height", "paddle_header_rule_ink_ratio",
            "paddle_header_rule_margin",
        ]),
        ("多 OCR / Google Lens", [
            "paddle_tesseract_psm", "paddle_lens_timeout",
            "paddle_lens_default_confidence", "paddle_alignment_y_tolerance_ratio",
            "paddle_alignment_min_similarity", "paddle_conflict_review_margin",
        ]),
        ("词头识别正则（高级）", ["paddle_headword_regex", "paddle_pos_regex", "paddle_special_symbol_regex"]),
    ]

CHECK_GROUPS = [
        ("版面行为", [
        ("共享分析图自适应去噪", "analysis_denoise_enabled"),
        ("Layout 专用去噪", "layout_denoise_enabled"),
        ("启用按原图尺寸缩图估计（实验）", "layout_scale_enabled"),
        ("50% 可用：分栏数", "layout_scale_columns"),
        ("50% 可用：单栏宽", "layout_scale_column_width"),
        ("50% 可用：栏间距", "layout_scale_gutter"),
        ("50% 可用：正文起始 Y", "layout_scale_start_y"),
        ("50% 可用：首栏 X", "layout_scale_manual_x"),
        ("50% 可用：字高", "layout_scale_character_height"),
        ("50% 可用：行间空", "layout_scale_row_padding"),
            ("使用自动版面参数", "ordinary_auto_layout"),
            ("分栏数", "ordinary_auto_columns"),
            ("正文起始Y", "ordinary_auto_start_y"),
            ("首栏X", "ordinary_auto_manual_x"),
            ("单栏宽", "ordinary_auto_column_width"),
            ("栏间空", "ordinary_auto_gutter"),
            ("普通字/行高", "ordinary_auto_character_height"),
            ("行间空", "ordinary_auto_row_padding"),
            ("跟随词头列倾斜和局部变形", "follow_column_deformation"),
        ]),
        ("OCR 处理", [
            ("OCR 后执行替换", "ocr_replace"), ("OCR 转小写", "lowercase_ocr"),
        ]),
        ("多 OCR 行为", [
            ("Paddle检测同时运行Tesseract对照", "paddle_compare_tesseract"),
            ("Tesseract结果可补漏Paddle词头", "paddle_tesseract_rescue"),
            ("Tesseract自动比较 PSM 4/6", "paddle_tesseract_auto_psm"),
            ("多OCR自动融合决策", "paddle_dual_ocr_arbitration"),
            ("每个OCR左缘候选行显示复选框", "paddle_show_candidate_checkboxes"),
        ]),
        ("校对时主界面", [
            ("记录本地校对操作证据（默认关）", "proofreading_event_capture"),
            ("主界面显示 OCR 内容选择", "review_main_show_ocr_choices"),
            ("主界面按 OCR 置信度显示底色", "review_main_show_ocr_background"),
        ]),
    ]

OCR_LANGUAGES = ("eng", "spa", "fra", "ita", "por", "deu", "chi_sim", "chi_tra", "jpn", "ara")

SETTING_LABELS = _help_catalog.SETTING_LABELS

SETTING_HELP = _help_catalog.SETTING_HELP

COMMON_FIELDS = (
        "columns", "start_y", "manual_x", "column_width", "gutter",
        "character_height", "row_padding", "ocr_language",
    )

NORMAL_COMMON_FIELDS = (
        "body_indent", "horizontal_tolerance", "character_height", "row_padding",
    )

NORMAL_ADVANCED_FIELDS = (
        "analysis_denoise_strength",
        "analysis_threshold_mode", "darkness_threshold", "dark_area_percent",
        "ordinary_right_divisor", "physical_row_projection_width_percent",
        "white_threshold_high", "white_threshold_low",
        "whitespace_adjustment", "upward_ratio", "row_step_multiplier",
        "analysis_left", "analysis_right",
        "column_track_radius", "column_track_block_height", "column_track_max_step",
    )

OCR_COMMON_FIELDS = (
        "ocr_language", "paddle_preprocessing",
        "paddle_band_width_ratio", "paddle_left_tolerance",
    )

OCR_ADVANCED_FIELDS = (
        "paddle_max_input_side", "paddle_band_left_margin",
        "paddle_rec_score_threshold", "paddle_line_merge_y_ratio",
        "paddle_height_ratio", "paddle_boldness_ratio", "paddle_gap_ratio",
        "paddle_min_candidate_score", "paddle_header_search_height",
        "paddle_header_rule_ink_ratio", "paddle_header_rule_margin",
        "paddle_pos_search_chars", "paddle_tesseract_psm",
        "paddle_alignment_y_tolerance_ratio", "paddle_alignment_min_similarity",
        "paddle_conflict_review_margin",
    )

DISPLAY_FIELDS = (
        "marker_height", "headword_marker_opacity", "guide_width", "guide_opacity",
        "main_entry_font_family", "main_entry_font_size",
        "main_entry_width_chars", "main_entry_x_ratio",
        "review_entry_font_family", "review_entry_font_size",
        "review_entry_vertical_padding", "review_single_cjk_line_height",
        "review_zoom_percent", "wordslist_path",
    )

PROJECT_RUNTIME_FIELDS = (
        "batch_interval", "tesseract_language",
        "paddle_ocr_version", "paddle_max_input_side",
    )

EXPERT_FIELDS = (
        "layout_writing_mode", "layout_text_direction", "layout_transform",
        "layout_columns_policy", "layout_column_separator_mode",
        "paddle_language", "paddle_lens_timeout",
        "paddle_lens_default_confidence",
        "paddle_headword_regex", "paddle_pos_regex", "paddle_special_symbol_regex",
    )

SETTING_UNITS = {
        "separator_y_ink_safe_max_fraction": "× 行高",
        "separator_y_ink_safe_ink_threshold": "灰度 0–255",
        "separator_y_ink_safe_existing_ink_ratio": "比例 0–1",
        "separator_y_ink_safe_gap_ink_ratio": "比例 0–1",
        "columns": "栏",
        "guide_opacity": "%", "headword_marker_opacity": "%", "illustration_fill_opacity": "%",
        "start_y": "% 图高", "bottom_y": "原图px", "manual_x": "% 图宽",
        "column_width": "% 图宽", "gutter": "% 图宽", "body_indent": "% 图宽",
        "character_height": "% 图高", "row_padding": "% 图高", "horizontal_tolerance": "% 图宽",
        "darkness_threshold": "RGB 和", "dark_area_percent": "%",
        "ordinary_right_divisor": "1/x",
        "physical_row_projection_width_percent": "% 单栏宽",
        "white_threshold_high": "0–1000",
        "white_threshold_low": "0–1000", "whitespace_adjustment": "原图px",
        "upward_ratio": "1/x", "analysis_left": "% 图宽", "analysis_right": "% 图宽",
        "row_step_multiplier": "×行高", "column_track_radius": "% 单栏宽",
        "column_track_block_height": "% 正文高度", "column_track_max_step": "% 分块高度",
        "paddle_band_width_ratio": "%", "paddle_band_left_margin": "原图px",
        "paddle_left_tolerance": "% 单栏宽", "paddle_max_input_side": "px",
        "paddle_separator_safety_px": "原图px", "paddle_separator_band_radius": "原图px",
        "paddle_separator_roi_width_ratio": "%", "paddle_separator_column_margin": "原图px",
        "paddle_header_search_height": "% 图高", "paddle_header_rule_margin": "原图px",
        "batch_interval": "秒", "illustration_detect_padding": "原图px",
        "illustration_detect_right_padding": "原图px",
        "illustration_detect_gray_threshold": "0–255",
        "illustration_detect_parallel_workers": "进程",
        "illustration_detect_min_width": "按尺寸单位",
        "illustration_detect_min_height": "按尺寸单位",
        "illustration_detect_size_unit": "% / px",
        "illustration_detect_min_occupancy_percent": "%",
        "illustration_outline_width": "px",
        "illustration_label_border_width": "px",
        "illustration_label_font_size": "pt", "main_entry_font_size": "pt",
        "review_entry_font_size": "pt", "review_entry_vertical_padding": "px",
        "review_single_cjk_line_height": "原图px", "review_zoom_percent": "%",
    }

SETTING_SPIN = {
        "separator_y_ink_safe_max_fraction": (0.01, 0.30, 0.01),
        "separator_y_ink_safe_ink_threshold": (0, 255, 1),
        "separator_y_ink_safe_existing_ink_ratio": (0.0, 0.20, 0.005),
        "separator_y_ink_safe_gap_ink_ratio": (0.0, 0.10, 0.005),
        "columns": (1, 12, 1),
        "guide_opacity": (0.0, 100.0, 5.0),
        "headword_marker_opacity": (0.0, 100.0, 5.0),
        "illustration_fill_opacity": (0.0, 100.0, 5.0),
        "start_y": (0.0, 100.0, 0.05), "bottom_y": (0, 50000, 1),
        "manual_x": (0.0, 100.0, 0.05), "column_width": (0.01, 100.0, 0.05),
        "gutter": (0.0, 100.0, 0.05), "body_indent": (0.0, 100.0, 0.05),
        "character_height": (0.01, 100.0, 0.05), "row_padding": (0.0, 100.0, 0.05),
        "horizontal_tolerance": (0.0, 100.0, 0.05), "darkness_threshold": (0, 765, 1),
        "dark_area_percent": (1.0, 100.0, 0.1), "ordinary_right_divisor": (1.0, 5.0, 0.1),
        "physical_row_projection_width_percent": (10.0, 100.0, 1.0),
        "white_threshold_high": (0, 1000, 1), "white_threshold_low": (0, 1000, 1),
        "whitespace_adjustment": (0, 30, 1), "upward_ratio": (0.1, 10.0, 0.1),
        "row_step_multiplier": (0.5, 3.0, 0.1),
        "analysis_left": (0.0, 100.0, 0.1), "analysis_right": (0.0, 100.0, 0.1),
        "column_track_radius": (0.5, 50.0, 0.5),
        "column_track_block_height": (0.5, 25.0, 0.5),
        "column_track_max_step": (0.5, 50.0, 0.5),
        "paddle_band_width_ratio": (1.0, 100.0, 0.1), "paddle_band_left_margin": (0, 5000, 1),
        "paddle_left_tolerance": (0.0, 100.0, 0.1), "paddle_max_input_side": (256, 20000, 64),
        "paddle_separator_safety_px": (0, 1000, 1),
        "paddle_separator_band_radius": (0, 200, 1),
        "paddle_separator_roi_width_ratio": (10.0, 100.0, 0.1),
        "paddle_separator_column_margin": (0, 2000, 1),
        "separator_y_max_shift_ratio": (0.0, 1.5, 0.05),
        "paddle_header_search_height": (0.0, 100.0, 0.1), "paddle_header_rule_margin": (0, 1000, 1),
        "batch_interval": (0.5, 3600, 0.5),
        "illustration_detect_padding": (0, 5000, 1),
        "illustration_detect_right_padding": (0, 5000, 1),
        "illustration_detect_gray_threshold": (0, 255, 1),
        "illustration_detect_parallel_workers": (0, 8, 1),
        "illustration_detect_min_width": (0.0, 100000.0, 0.5),
        "illustration_detect_min_height": (0.0, 100000.0, 0.5),
        "illustration_detect_min_occupancy_percent": (0.0, 100.0, 0.5),
        "illustration_outline_width": (1, 20, 1),
        "illustration_label_border_width": (1, 20, 1),
        "illustration_label_font_size": (5, 200, 1),
        "main_entry_font_size": (5, 200, 1), "review_entry_font_size": (6, 200, 1),
        "review_entry_vertical_padding": (0, 30, 1),
        "review_single_cjk_line_height": (0, 500, 1), "review_zoom_percent": (0.0, 250.0, 0.5),
    }

SETTING_HELP_IMAGES = _help_catalog.SETTING_HELP_IMAGES

SETTING_CHOICES = {
        "ref_box_action_position": {
            "上方靠右（默认）": "above_right",
            "上方靠左": "above_left",
            "右侧": "right_side",
        },
        "analysis_denoise_strength": {"关闭": "off", "弱": "weak", "自动": "auto", "强": "strong"},
        "analysis_threshold_mode": {
            "自动（推荐，等同 Otsu）": "auto",
            "Otsu 全页阈值": "otsu",
            "自适应（底色不均时）": "adaptive",
            "固定阈值（旧项目/专家）": "fixed",
        },
        "paddle_preprocessing": {
            "原图（推荐）": "original",
            "灰度": "grayscale",
            "自动对比度": "auto_contrast",
            "二值化": "binary",
        },
    }

CHECK_HELP = _help_catalog.CHECK_HELP

REF_BOX_STYLE_FIELDS = (
    "ref_box_fill_color", "ref_box_fill_opacity",
    "ref_box_filled_color", "ref_box_filled_opacity",
    "ref_box_action_position",
)
REF_TEXT_LABEL_FIELDS = (
    "ref_box_text_color", "ref_box_font_family", "ref_box_font_size",
    "ref_text_label_background_color", "ref_text_label_background_opacity",
    "ref_text_label_gap", "ref_text_label_padding",
)
REF_OCR_EXTRACTION_FIELDS = ("ref_ocr_extract_regex",)
REF_TEXT_LABEL_CHECKS = (
    ("显示 REF 文本标签", "ref_box_show_text"),
    ("REF 文本标签字体加粗", "ref_box_font_bold"),
    ("REF 文本标签字体斜体", "ref_box_font_italic"),
)
REF_BOX_GEOMETRY_FIELDS = (
    "ref_box_width_lines", "ref_box_height_lines", "ref_match_threshold",
    "ref_match_scale_tolerance_percent",
)
REF_BOX_GEOMETRY_CHECKS = (
    ("图样宽度纳入画框", "ref_box_include_guide_width"),
)

REF_BOX_CHECKS = (
    ("显示 REF 框", "ref_box_show"),
    ("编辑模式中所有 REF 一直显示 ×", "ref_box_delete_always_visible"),
    ("新框自动挂靠所在正文词条", "ref_box_auto_attach"),
)

ILLUSTRATION_DETECTION_FIELDS = (
    "illustration_detect_gray_threshold", "illustration_detect_parallel_workers",
    "illustration_detect_min_width",
    "illustration_detect_min_height", "illustration_detect_size_unit",
    "illustration_detect_min_occupancy_percent",
    "illustration_detect_padding", "illustration_detect_right_padding",
)

ILLUSTRATION_APPEARANCE_FIELDS = (
    "illustration_outline_color", "illustration_outline_width",
    "illustration_fill_color", "illustration_fill_opacity",
    "illustration_label_border_color", "illustration_label_border_width",
    "illustration_label_fill_color", "illustration_label_font_family",
    "illustration_label_font_size",
)

ILLUSTRATION_CHECKS = (
    ("Layout 分析前白化插图", "layout_mask_illustrations"),
    ("使用已有的插图数据", "layout_mask_illustrations_use_existing"),
    ("显示插图区域标签", "show_illustration_labels"),
    ("插图标签粗体", "illustration_label_font_bold"),
    ("插图标签斜体", "illustration_label_font_italic"),
)

NORMAL_CHECKS = (
        ("共享分析图自适应去噪", "analysis_denoise_enabled"),
        ("Layout 专用去噪", "layout_denoise_enabled"),
        ("启用按原图尺寸缩图估计（实验）", "layout_scale_enabled"),
        ("50% 可用：分栏数", "layout_scale_columns"),
        ("50% 可用：单栏宽", "layout_scale_column_width"),
        ("50% 可用：栏间距", "layout_scale_gutter"),
        ("50% 可用：正文起始 Y", "layout_scale_start_y"),
        ("50% 可用：首栏 X", "layout_scale_manual_x"),
        ("50% 可用：字高", "layout_scale_character_height"),
        ("50% 可用：行间空", "layout_scale_row_padding"),
        ("跟随栏左缘倾斜/弯曲", "follow_column_deformation"),
        ("使用自动版面参数", "ordinary_auto_layout"),
        ("分栏数", "ordinary_auto_columns"),
        ("正文起始Y", "ordinary_auto_start_y"),
        ("首栏X", "ordinary_auto_manual_x"),
        ("单栏宽", "ordinary_auto_column_width"),
        ("栏间空", "ordinary_auto_gutter"),
        ("普通字/行高", "ordinary_auto_character_height"),
        ("行间空", "ordinary_auto_row_padding"),
    )

OCR_COMMON_CHECKS = (
        ("PaddleOCR 主识别", "paddle_use_paddleocr"),
        ("同时运行 Tesseract 对照", "paddle_compare_tesseract"),
        ("多 OCR 自动融合", "paddle_dual_ocr_arbitration"),
        ("要求结构/视觉提示", "paddle_require_visual_cue"),
        ("要求词性/变形/词条符号", "paddle_require_pos_or_symbol"),
    )

OCR_ADVANCED_CHECKS = (
        ("启用文字行方向识别", "paddle_use_textline_orientation"),
        ("批量 OCR 启用断点恢复（默认关）", "ocr_resume_completed_pages"),
        ("实验：Tesseract 分层缓存（默认关）", "ocr_cache_tesseract_raw"),
        ("实验：按需 Tesseract 诊断（默认关）", "ocr_lazy_tesseract_diagnostics"),
        ("自动忽略页眉横线以上", "paddle_auto_header_rule"),
        ("去除词头音节分隔点", "paddle_remove_syllable_separators"),
        ("Tesseract 可补漏 Paddle", "paddle_tesseract_rescue"),
        ("Tesseract 自动比较 PSM 4/6", "paddle_tesseract_auto_psm"),
        ("显示每个 OCR 候选复选框", "paddle_show_candidate_checkboxes"),
        ("实验：同栏词头样式救回续行（默认关）", "paddle_peer_style_rescue"),
    )

SEPARATOR_Y_FIELDS = (
    "paddle_separator_search_ratio",
    "paddle_separator_band_radius",
    "paddle_separator_safety_px",
    "paddle_separator_roi_width_ratio",
    "paddle_separator_column_margin",
    "separator_y_max_shift_ratio",
    "separator_y_ink_safe_max_fraction",
    "separator_y_ink_safe_ink_threshold",
    "separator_y_ink_safe_existing_ink_ratio",
    "separator_y_ink_safe_gap_ink_ratio",
)

SEPARATOR_Y_CHECKS = (
    ("自动画线 Y 精修（含墨迹安全检查）", "paddle_refine_separator_y"),
)

DISPLAY_STYLE_CHECKS = (
        ("主界面词条粗体", "main_entry_font_bold"),
        ("主界面词条斜体", "main_entry_font_italic"),
        ("校对词条粗体", "review_entry_font_bold"),
        ("校对词条斜体", "review_entry_font_italic"),
    )

DISPLAY_CHECKS = (
        ("校对时主界面显示 OCR 候选", "review_main_show_ocr_choices"),
        ("校对时主界面显示 OCR 置信度底色", "review_main_show_ocr_background"),
    )


__all__ = [
    "ILLUSTRATION_DETECTION_FIELDS", "ILLUSTRATION_APPEARANCE_FIELDS", "ILLUSTRATION_CHECKS",
    "FIELDS",
    "PROFILE_FIELD_GROUPS",
    "PROFILE_CHECKS",
    "FIELD_GROUPS",
    "CHECK_GROUPS",
    "OCR_LANGUAGES",
    "SETTING_LABELS",
    "SETTING_HELP",
    "COMMON_FIELDS",
    "NORMAL_COMMON_FIELDS",
    "NORMAL_ADVANCED_FIELDS",
    "OCR_COMMON_FIELDS",
    "OCR_ADVANCED_FIELDS",
    "DISPLAY_FIELDS",
    "SEPARATOR_Y_FIELDS", "SEPARATOR_Y_CHECKS",
    "PROJECT_RUNTIME_FIELDS",
    "EXPERT_FIELDS",
    "SETTING_UNITS",
    "SETTING_SPIN",
    "SETTING_HELP_IMAGES",
    "SETTING_CHOICES",
    "CHECK_HELP",
    "NORMAL_CHECKS",
    "OCR_COMMON_CHECKS",
    "OCR_ADVANCED_CHECKS",
    "DISPLAY_STYLE_CHECKS",
    "DISPLAY_CHECKS",
]
