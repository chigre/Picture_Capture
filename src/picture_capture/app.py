from __future__ import annotations
from pathlib import Path
from dataclasses import replace
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import bisect
import csv
import os
import queue
import threading
import shutil
from datetime import datetime
from importlib import util as importlib_util
from importlib import metadata as importlib_metadata
import json
import multiprocessing
import re
import statistics
import traceback
import unicodedata
import webbrowser
import tkinter as tk
from tkinter import colorchooser, filedialog, font, messagebox, simpledialog, ttk
from PIL import Image, ImageTk
from . import __version__
from .project import parameter_templates as _project_templates
from .ui.appearance import (
    appearance_palette,
    apply_classic_widget_appearance,
    apply_native_titlebar_appearance,
    detect_system_appearance_mode,
    normalize_appearance_mode,
    normalize_appearance_preference,
    themed_display_image,
    usage_guide_palette,
)
from .io.gui_io import pdic_path, read_pdic, read_ppp, write_pdic, write_ppp, write_text_atomic
from .ocr.action_guard import LENS_MODE_LABELS, LENS_MODE_VALUES, guard_ocr_action_selection
from .models import (
    AppSettings, Entry as WordEntry, PolygonRegion, ProjectState, project_page_images,
    read_noncomment_lines, resolve_wordslist_path, resolved_tesseract_language,
)
from .proofreading.pdic_restore import (
    build_page_lookup as _build_words_page_lookup, parse_merged_pdic_text as _parse_merged_pdic_text,
    resolve_page_token as _resolve_words_page_token, write_pdic_atomic as _write_pdic_atomic,
)
from .proofreading.page_word_mapping import (
    _compare_page_word_mappings, _compare_page_word_sequences,
    _fill_page_entries, _page_word_mapping_text, _parse_words_of_pages_text,
)
from .proofreading.text_helpers import (
    _has_distinct_ocr_alternatives,
    _candidate_choice_rows,
    _candidate_for_entry_from_list,
    _candidate_word_for_ocr_source,
    _entry_font_spec,
    _focused_review_character_tokens,
    _focused_review_is_single_character,
    _focused_review_page_indices,
    _review_editor_font_size,
    _review_similarity_color,
    _review_similarity_key,
    _review_text_similarity,
)
from .proofreading.crop_extension import (
    extended_review_crop_box, parse_review_crop_multiplier,
)
from .geometry.layout_percent_helpers import (
    LAYOUT_PERCENT_AXES,
    _column_percent_to_pixels,
    _column_pixels_to_percent,
    _format_layout_percent,
    _format_review_height_percent,
    _layout_percent_denominator,
    _layout_percent_to_pixels,
    _layout_pixels_to_percent,
    _review_height_percent_to_pixels,
    _review_height_pixels_to_percent,
)
from .project.page_list_helpers import (
    bookmarked_page_indices, _fill_status_cell_style,
    _natural_text_key, _sorted_page_list_rows,
)

from .ui.overlay_layout_helpers import (
    binary_preview_image,
    effective_main_overlay_font_size,
    entry_index_label_layout,
    horizontal_ocr_menu_layout,
    horizontal_overlay_layout,
    review_auto_fit_zoom,
    scaled_overlay_line_width,
    transformed_entry_anchor,
    vertical_marker_contact_gap,
    vertical_ocr_menu_layout,
    vertical_overlay_layout,
)
from .paddle_headwords import (
    DEFAULT_HEADWORD_FILTER_RULES, HEADWORD_FILTER_RULES_FILENAME,
    compact_ocr_cache_file, parse_headword_filter_rules,
)
from .ui.environment_center import EnvironmentCenterWindow
from .runtime.environment import legacy_user_config_files, resolve_paddle_device, user_config_root
from .ui.compat import (
    AUTO_FONT_FAMILY, bind_context_menu, fit_window_to_work_area,
    normalize_content_font_setting, preferred_font_family, resolve_content_font_family,
)
from .ui.widgets.vertical_word import VerticalWordText
from .ui.settings import schema as _settings_schema
from .ui.settings import help as _settings_help_ui
from .ui.settings import profile as _settings_profile_ui
from .ui.settings import rules as _settings_rules_ui
from .ui.settings import lifecycle as _settings_lifecycle_ui
from .ui.settings import window as _settings_window_ui
from .ui.settings import crop as _settings_crop_ui
from .ui.settings import inference_performance as _settings_inference_ui
from .ui.settings import project as _settings_project_ui
from .ui.settings import illustration as _settings_illustration_ui
from .ui.settings import ref_box as _settings_ref_box_ui
from .ui.settings import color_picker as _settings_color_ui
from .ui.ref_box_controller import RefBoxController
from .ui.controllers import (
    CanvasController, CropController, DetectionController, ExportController,
    HeadwordController, IllustrationController, PageController, ProjectController,
    ReviewController, SESSION_STATE_FILENAME, SessionController,
)
from .ui import project_session_workflow as _project_session
from .ui import review_workspace_workflow as _review_workspace
from .ui import review_reference_workflow as _review_reference
from .ui import review_lookup_workflow as _review_lookup
from .ui import review_simplified_workflow as _review_simplified
from .ui import review_ocr_compare_workflow as _review_ocr
from .ui import review_crop_actions as _review_crop
from .ui import review_entry_actions as _review_entry
from .ui import review_page_lifecycle as _review_page
from .ui import page_index_workflow as _page_index
from .ui import word_fill_status_workflow as _word_fill_status
from .ui import review_appearance_workflow as _review_appearance
from .ui import focused_filter_workflow as _focused_filter
from .proofreading import focused_pdic_updates as _focused_pdic
from .ui import main_canvas_render_workflow as _main_canvas_render
from .ui import canvas_pointer_workflow as _canvas_pointer
from .ui.page_thumbnails import PageThumbnailController, visible_page_iids
from .ui.page_list_grid import PageListGrid
from .ui.text_wrap import (
    _label_measure, _mixed_ui_wrap_tokens, _normalize_ui_paragraphs, _wrap_mixed_ui_text,
)
from .ui.dialogs.usage_guide import UsageGuideWindow
from .ui.dialogs.common import _build_modern_dialog_heading
from .ui.dialogs.old_new_comparison import OldNewComparisonWindow
from .ui.dialogs.ocr_conflict import OCRConflictReviewDialog
from .ui.dialogs.crop_settings import CropSettingsDialog
from .layout.detection import detect_layout_consistency, detect_layout_parameters
from .ui.layout_detection_actions import (
    detect_layout_current as _run_detect_layout_current,
    detect_layout_consistency_selected as _run_detect_layout_consistency_selected,
)
from .geometry.layout_transform import LayoutTransform
from .geometry.coordinate_space import SOURCE_COORDINATE_SPACE, coordinate_contract
from .crop.settings import (
    CROP_SETTINGS_VERSION,
    normalize_crop_settings_payload as _normalize_crop_settings_payload,
)
from .lexicon.collation import (
    LATIN_ORDER, available_profile_labels, collation_key, display_key,
    parse_custom_order, profile_label,
)
from .profile.dictionary import (
    DEFAULT_PROFILE_ID, PROFILE_FILENAME, available_dictionary_profiles,
    dictionary_profile_preset,
    effective_project_profile_id,
    language_effective_settings, managed_profile_setting_names, profile_effective_settings,
    profile_layout_summary, write_project_profile,
)
from .profile.wizard import ProjectProfileWizard, _screen_work_area
from .profile.semantics import (
    effective_page_settings, entry_allowed_by_page_template, page_template_analysis_image,
)
from .image_utils import normalize_page_rgb
from .ui import preprocess_workflow as _preprocess_ui
from .ui import batch_workflow as _batch_workflow
from .image_preprocessing import (
    PreprocessAnalysis,
    analysis_is_current as preprocess_analysis_is_current,
    analyze_preprocess_path,
    clear_manual_perspective_quad,
    geometry_corrected_image,
    load_analysis as load_preprocess_analysis,
    load_manual_perspective_quad,
    overlay_excluded_regions,
    output_canvas_info,
    preprocess_metadata_output_root,
    preview_output_root as preprocess_preview_output_root,
    processed_output_root as preprocess_processed_output_root,
    promote_processed_pages,
    result_summary as preprocess_result_summary,
    save_analysis as save_preprocess_analysis,
    save_manual_perspective_quad,
    save_processed_page,
    save_review_preview,
    export_diagnostic_json,
    export_summary_csv,
)
from .preprocess.geometry import perspective_from_quad
from .persistence.page_sections import (
    PageSection, read_page_sections, write_page_sections, v_is_inside_sections,
)
from .lexicon.reference_index import contains_cjk, reference_sort_key
from .lexicon.network_lookup import LexicalLookupResult, lookup_word_free, web_search_url
from .lexicon.cc_cedict import (
    DOWNLOAD_PAGE_URL as CC_CEDICT_DOWNLOAD_PAGE_URL,
    install_from_file as install_cc_cedict_from_file,
    simplified_candidates as cc_cedict_simplified_candidates,
    status as cc_cedict_status,
)
from .lexicon.chinese_simplify import simplify_text
from .proofreading.simplified_review import entry_key as simplified_entry_key, read_records as read_simplified_records, write_records as write_simplified_records
from .training_export import (
    TrainingExportCancelled, copy_project_context, export_training_page,
    make_training_zip, write_training_manifest,
)
from .text.encoding import read_text_detected
from .ui.unicode_nonbmp_input import attach_nonbmp_unicode_input, close_nonbmp_unicode_input
from .ui.overlay_opacity import (
    clear_alpha_line_photos,
    create_alpha_canvas_line, release_alpha_line_photos,
)
from .illustration.polygon_edit import nearest_polygon_segment
from .illustration.labels import label_text, user_edited_link
from .illustration.delete_overlay import create_illustration_delete_control, polygon_delete_center
from .illustration.fill_opacity import (
    clear_alpha_polygon_records,
    create_alpha_canvas_polygon, refresh_alpha_polygon_fill,
)
from .ui.ocr_crop_preview import draw_ocr_crop_preview
from .ui.layout_visualization_ui_v3 import draw_layout_visualization_if_enabled
from .ui.auxiliary_line_controller import AuxiliaryLineController
from .crop.auxiliary_lines import AuxiliaryLineEdits
from .proofreading.entry_classification_ui import sync_review_entry_classification
from .persistence.project_storage import (
    STORAGE_DIRNAME, ensure_project_storage, exports_root, has_legacy_project_data,
    headword_filter_rules_path, is_managed_project, migrate_legacy_project,
    ocr_cache_root, ppp_read_path_for_image, ppp_write_path_for_image, simplified_review_path_for_image,
    profile_path as project_profile_path, qt_root, replace_rules_path, settings_path,
    training_exports_root, word_fill_status_path, words_of_pages_default_path,
)
from .project.recent_projects import (
    load_recent_projects, recent_project_details, recent_project_stub_details, remove_recent_project, set_recent_project_pinned, touch_recent_project,
)
from .processing import (
    build_page_crop_plan,
    column_index,
    column_index_for_click,
    sort_entries_reading_order, sort_entries_column_y,
    derive_geometry, derive_nominal_geometry,
    detect_entries,
    detect_entries_job,
    export_ocred,
    import_ocred,
    line_box,
    load_replace_rules,
    parameter_scale,
    ocr_entries,
    ocr_existing_entry_words_from_markers,
    split_single_lines,
    split_whole_entries,
    split_illustrations,
    illustration_crop_bounds,
    illustration_polygon_box,
    entry_crop_column_boxes,
    entry_crop_piece_filename,
    resolve_crop_worker_count,
    refine_existing_entries,
)

DETECTION_LABELS = {
    "combined": "融合画线（推荐｜普通几何＋OCR语义）",
    "paddleocr": "PaddleOCR（单独｜词头＋坐标）",
    "left_edge": "左缘规则（单独｜几何）",
}
DETECTION_VALUES = {label: value for value, label in DETECTION_LABELS.items()}
OCR_ENGINE_LABELS = {"tesseract": "Tesseract", "paddleocr": "PaddleOCR"}
OCR_ENGINE_VALUES = {label: value for value, label in OCR_ENGINE_LABELS.items()}
APPEARANCE_MODE_LABELS = {"light": "浅色", "dark": "深色", "system": "跟随系统"}
APPEARANCE_MODE_VALUES = {label: value for value, label in APPEARANCE_MODE_LABELS.items()}

# ISO 639-1; common languages first, then alphabetical.
PROJECT_LANGUAGE_CODES = (
    "en", "zh", "es", "fr", "de", "it", "pt", "ja", "ko", "ru",
    "ar", "nl", "pl", "tr", "vi",
    "af", "am", "az", "be", "bg", "bn", "bs", "ca", "cs", "cy",
    "da", "el", "eo", "et", "eu", "fa", "fi", "ga", "gl", "gu",
    "he", "hi", "hr", "hu", "hy", "id", "is", "ka", "kk", "km",
    "kn", "la", "lt", "lv", "mk", "ml", "mn", "mr", "ms", "mt",
    "ne", "no", "pa", "ro", "sk", "sl", "sq", "sr", "sv", "sw",
    "ta", "te", "th", "tl", "uk", "ur", "uz",
)

OCR_TO_PROJECT_LANGUAGE = {
    "eng": "en", "spa": "es", "fra": "fr", "fre": "fr", "deu": "de", "ger": "de",
    "ita": "it", "por": "pt", "chi_sim": "zh", "chi_tra": "zh", "ch": "zh",
    "jpn": "ja", "japan": "ja", "kor": "ko", "korean": "ko", "rus": "ru",
}

def project_language_from_ocr(ocr_language: str) -> str:
    """Map the first configured OCR language to an ISO 639-1 code."""
    first = next((part.strip().lower() for part in str(ocr_language or "").split("+") if part.strip()), "")
    return OCR_TO_PROJECT_LANGUAGE.get(first, first if len(first) == 2 and first.isalpha() else "")

def transformed_geometry_pending(settings: AppSettings) -> bool:
    """Return whether a configured transform is unknown to the geometry adapter."""
    return str(getattr(settings, "layout_transform", "identity") or "identity") not in {
        "identity", "mirror_x", "rotate_ccw90", "rotate_cw90",
    }

OCR_SCOPE_LABELS = {"current": "当前页", "all": "全部页面"}
OCR_SCOPE_VALUES = {label: value for value, label in OCR_SCOPE_LABELS.items()}
OCR_REFRESH_LABELS = {
    "reuse": "复用缓存（参数变化自动重算）",
    "force": "强制重新识别",
}
OCR_REFRESH_VALUES = {label: value for value, label in OCR_REFRESH_LABELS.items()}

def _review_crop_settings(image: Image.Image, settings: AppSettings, viewer_width: int) -> AppSettings:
    """Return review settings unchanged; geometry is already source pixels."""
    return replace(settings)

def _review_crop_context(
    image: Image.Image,
    settings: AppSettings,
    viewer_width: int,
    page_index: int = 0,
):
    """Return review crop settings plus the same per-page Profile geometry as detection."""
    effective = effective_page_settings(settings, image.size, page_index)
    analysis_image = page_template_analysis_image(image, effective, page_index)
    return (
        _review_crop_settings(image, effective, viewer_width),
        derive_geometry(analysis_image, effective),
    )

def _is_cjk_review_index(settings: AppSettings) -> bool:
    """Return whether the active index/profile is Chinese-oriented."""
    language = str(getattr(settings, "ocr_language", "") or "").strip().lower()
    profile = str(getattr(settings, "dictionary_profile_id", "") or "").strip().lower()
    return language.startswith("chi_") or profile.startswith("cjk_")

def _effective_review_single_cjk_line_height(settings: AppSettings) -> int:
    """Resolve the review-only height for one-character CJK headwords.

    An explicit project value wins. New/older projects with value 0 use a
    language-aware default: Chinese index/profile = 2.5× the shared single-line
    height; other profiles retain a smaller legacy-like expansion.
    """
    try:
        explicit = int(getattr(settings, "review_single_cjk_line_height", 0) or 0)
    except (TypeError, ValueError):
        explicit = 0
    if explicit > 0:
        return max(1, explicit)
    base = max(1, int(getattr(settings, "character_height", 1) or 1))
    multiplier = 2.5 if _is_cjk_review_index(settings) else 1.6
    return max(base, round(base * multiplier))

def _effective_review_regular_crop_height(settings: AppSettings) -> int:
    """Resolve ordinary proofreading crop height in parameter pixels."""
    try:
        explicit = int(getattr(settings, "review_regular_crop_height", 0) or 0)
    except (TypeError, ValueError):
        explicit = 0
    if explicit > 0:
        return max(1, explicit)
    line_height = max(1, int(getattr(settings, "character_height", 1) or 1))
    row_padding = max(0, int(getattr(settings, "row_padding", 0) or 0))
    return max(1, line_height + row_padding)

def _review_line_box(
    entry: WordEntry,
    geometry,
    image: Image.Image,
    settings: AppSettings,
    next_entry: WordEntry | None = None,
    *,
    ordinary_height_only: bool = False,
    editor_text: str | None = None,
) -> tuple[int, int, int, int]:
    """Review crop height is based only on the actual edited headword text.

    A single character uses the explicitly configured large-head crop height;
    multiple characters use the ordinary height. Deprecated classification,
    OCR visual-run height and manual scale flags do not influence review crops.
    """
    configured_regular = max(
        0, int(getattr(settings, "entry_regular_crop_height", 0) or 0)
    )
    configured_oversized = max(
        0, int(getattr(settings, "entry_oversized_crop_height", 0) or 0)
    )
    regular_height = (
        configured_regular or _effective_review_regular_crop_height(settings)
    )
    oversized_height = (
        configured_oversized or _effective_review_single_cjk_line_height(settings)
    )
    displayed_text = entry.word if editor_text is None else editor_text
    height = (
        regular_height if ordinary_height_only
        else oversized_height if _focused_review_is_single_character(displayed_text)
        else regular_height
    )
    if geometry.transform.kind != "identity":
        classified_settings = replace(settings)
        classified_settings.character_height = int(height)
        return line_box(entry, geometry, image, classified_settings)

    left, _old_top, right, _bottom = line_box(
        entry, geometry, image, settings
    )
    row_padding = max(0, int(getattr(settings, "row_padding", 0) or 0))
    half_spacing = round(0.5 * row_padding)
    top = max(int(geometry.top), int(entry.y) - half_spacing)
    return left, top, right, min(
        int(image.height),
        top + max(1, int(height)),
    )

def _apply_focused_review_page_updates(
    page: Path, pages: list[Path], page_index: int, changes: list[dict],
) -> tuple[list[tuple[int, int, int, str]], list[str]]:
    """Keep the original writer API and call-time patchpoints."""
    return _focused_pdic.apply_focused_review_page_updates(
        page, pages, page_index, changes,
        deps=_focused_pdic.FocusedPdicDeps(
            pdic_path=pdic_path, read_pdic=read_pdic, replace=replace,
            Image=Image, _write_pdic_atomic=_write_pdic_atomic,
        ),
    )

class SettingsDialog(tk.Toplevel):
    FIELDS = _settings_schema.FIELDS
    PROFILE_FIELD_GROUPS = _settings_schema.PROFILE_FIELD_GROUPS
    PROFILE_CHECKS = _settings_schema.PROFILE_CHECKS
    FIELD_GROUPS = _settings_schema.FIELD_GROUPS
    CHECK_GROUPS = _settings_schema.CHECK_GROUPS
    OCR_LANGUAGES = _settings_schema.OCR_LANGUAGES
    SETTING_LABELS = _settings_schema.SETTING_LABELS
    SETTING_HELP = _settings_schema.SETTING_HELP
    COMMON_FIELDS = _settings_schema.COMMON_FIELDS
    NORMAL_COMMON_FIELDS = _settings_schema.NORMAL_COMMON_FIELDS
    NORMAL_ADVANCED_FIELDS = _settings_schema.NORMAL_ADVANCED_FIELDS
    OCR_COMMON_FIELDS = _settings_schema.OCR_COMMON_FIELDS
    OCR_ADVANCED_FIELDS = _settings_schema.OCR_ADVANCED_FIELDS
    DISPLAY_FIELDS = _settings_schema.DISPLAY_FIELDS
    PROJECT_RUNTIME_FIELDS = _settings_schema.PROJECT_RUNTIME_FIELDS
    EXPERT_FIELDS = _settings_schema.EXPERT_FIELDS
    SETTING_UNITS = _settings_schema.SETTING_UNITS
    SETTING_SPIN = _settings_schema.SETTING_SPIN
    SETTING_HELP_IMAGES = _settings_schema.SETTING_HELP_IMAGES
    SETTING_CHOICES = _settings_schema.SETTING_CHOICES
    CHECK_HELP = _settings_schema.CHECK_HELP
    SEPARATOR_Y_FIELDS = _settings_schema.SEPARATOR_Y_FIELDS
    SEPARATOR_Y_CHECKS = _settings_schema.SEPARATOR_Y_CHECKS
    NORMAL_CHECKS = _settings_schema.NORMAL_CHECKS
    OCR_COMMON_CHECKS = _settings_schema.OCR_COMMON_CHECKS
    OCR_ADVANCED_CHECKS = _settings_schema.OCR_ADVANCED_CHECKS
    DISPLAY_STYLE_CHECKS = _settings_schema.DISPLAY_STYLE_CHECKS
    DISPLAY_CHECKS = _settings_schema.DISPLAY_CHECKS

    def _show_settings_help(
        self,
        title: str,
        body: str,
        image_name: str | None = None,
    ) -> None:
        _settings_help_ui.show_settings_help(self, title, body, image_name)

    def _settings_help_image_path(self, image_name: str) -> Path:
        return _settings_help_ui.settings_help_image_path(image_name)

    def _load_settings_help_image(self, image_name: str) -> Image.Image | None:
        return _settings_help_ui.load_settings_help_image(self, image_name)

    def _schedule_settings_help_image_render(self) -> None:
        _settings_help_ui.schedule_settings_help_image_render(self)

    def _render_settings_help_images(self) -> None:
        _settings_help_ui.render_settings_help_images(self)

    def _show_setting_help(self, name: str, *, show_layout_image: bool = False) -> None:
        _settings_help_ui.show_setting_help(
            self, name, show_layout_image=show_layout_image
        )

    def _show_check_help(self, label: str, name: str) -> None:
        _settings_help_ui.show_check_help(self, label, name)

    def _bind_help_widget(self, widget: tk.Misc, callback) -> None:
        _settings_help_ui.bind_help_widget(self, widget, callback)

    def _bind_responsive_labels(
        self,
        container: tk.Misc,
        *labels: ttk.Label,
        horizontal_padding: int = 12,
        min_wrap: int = 120,
    ) -> None:
        _settings_help_ui.bind_responsive_labels(
            self,
            container,
            *labels,
            horizontal_padding=horizontal_padding,
            min_wrap=min_wrap,
        )

    def _setting_var(self, name: str) -> tk.Variable:
        if name in self.vars:
            return self.vars[name]
        raw = getattr(self.parent.settings, name)
        choices = self.SETTING_CHOICES.get(name)
        if choices:
            reverse = {value: label for label, value in choices.items()}
            value = reverse.get(str(raw), str(raw))
        elif name == "paddle_left_tolerance":
            value = _format_layout_percent(
                _column_pixels_to_percent(self.parent.settings, raw)
            )
        elif name in LAYOUT_PERCENT_AXES and self.parent.image is not None:
            source_value = (
                self.parent._quick_geometry_value(name)
                if hasattr(self.parent, "_quick_geometry_value")
                else raw
            )
            value = _format_layout_percent(
                _layout_pixels_to_percent(self.parent.image, name, source_value)
            )
        else:
            value = str(raw)
        var = tk.StringVar(value=value)
        self.vars[name] = var
        return var

    def _setting_widget(self, parent: ttk.Frame, name: str) -> tk.Widget:
        var = self._setting_var(name)
        choices = self.SETTING_CHOICES.get(name)
        if choices:
            return ttk.Combobox(
                parent, textvariable=var, values=tuple(choices.keys()),
                state="readonly", width=26,
            )
        if name in {"dictionary_index_language", "dictionary_content_language"}:
            return ttk.Combobox(
                parent, textvariable=var, values=PROJECT_LANGUAGE_CODES,
                state="readonly", width=26,
            )
        if name == "ocr_language":
            widget = ttk.Combobox(
                parent, textvariable=var, values=self.OCR_LANGUAGES,
                state="normal", width=26,
            )
            widget.bind("<<ComboboxSelected>>", lambda _e: self._refresh_sort_choices())
            widget.bind("<FocusOut>", lambda _e: self._refresh_sort_choices())
            return widget
        if name in {"main_entry_font_family", "review_entry_font_family", "ref_box_font_family"}:
            families = (
                AUTO_FONT_FAMILY,
                *tuple(sorted((f for f in font.families() if not f.startswith("@")), key=str.casefold)),
            )
            return ttk.Combobox(
                parent, textvariable=var, values=families, state="normal", width=26,
            )
        if name == "wordslist_path":
            box = ttk.Frame(parent)
            box.columnconfigure(0, weight=1)
            ttk.Entry(box, textvariable=var, width=28).grid(row=0, column=0, sticky="ew")
            ttk.Button(
                box, text="浏览…", command=lambda v=var: self._browse_wordslist_setting(v)
            ).grid(row=0, column=1, padx=(5, 0))
            return box
        if name in self.SETTING_SPIN:
            lower, upper, increment = self.SETTING_SPIN[name]
            return ttk.Spinbox(
                parent,
                textvariable=var,
                from_=lower,
                to=upper,
                increment=increment,
                width=18,
                justify="left",
            )
        if name == "layout_writing_mode":
            return ttk.Combobox(
                parent, textvariable=var,
                values=("horizontal-tb", "vertical-rl", "vertical-lr"),
                state="readonly", width=26,
            )
        if name == "layout_text_direction":
            return ttk.Combobox(
                parent, textvariable=var, values=("ltr", "rtl"),
                state="readonly", width=26,
            )
        if name == "layout_columns_policy":
            return ttk.Combobox(
                parent, textvariable=var, values=("detect", "fixed"),
                state="readonly", width=26,
            )
        if name == "layout_column_separator_mode":
            return ttk.Combobox(
                parent, textvariable=var, values=("auto", "present", "absent"),
                state="readonly", width=26,
            )
        if name == "layout_transform":
            return ttk.Entry(parent, textvariable=var, width=28, state="readonly")
        return (_settings_color_ui.make_color_widget(parent, var)
                if name.endswith("_color") else ttk.Entry(parent, textvariable=var, width=28))

    def _add_setting_group(
        self,
        parent: ttk.Frame,
        title: str,
        names: tuple[str, ...] | list[str],
        *,
        intro: str = "",
        help_images: bool = False,
        single_line_labels: bool = False,
    ) -> ttk.LabelFrame:
        group = ttk.LabelFrame(parent, text=title, padding=(12, 9))
        group.pack(fill="x", pady=(0, 10))
        group.columnconfigure(1, weight=1)
        if single_line_labels and names:
            label_font = font.nametofont("TkDefaultFont")
            longest_label_width = max(
                label_font.measure(
                    f"{self.SETTING_LABELS.get(name, self._field_meta.get(name, (name, str))[0])}："
                )
                for name in names
            )
            group.columnconfigure(0, minsize=longest_label_width + 4)
        row = 0
        if intro:
            intro_label = ttk.Label(
                group, text=intro, foreground="#5f6670", justify="left",
            )
            intro_label.grid(
                row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8)
            )
            self._bind_responsive_labels(
                group, intro_label, horizontal_padding=24, min_wrap=150
            )
            row += 1
        for name in names:
            label = self.SETTING_LABELS.get(name, self._field_meta.get(name, (name, str))[0])
            label_widget = ttk.Label(
                group,
                text=f"{label}：",
                justify="right",
                anchor="e",
                wraplength=0 if single_line_labels else 180,
            )
            label_widget.grid(row=row, column=0, sticky="e", padx=(0, 10), pady=5)

            control = ttk.Frame(group)
            control.grid(row=row, column=1, sticky="ew", pady=4)
            control.columnconfigure(0, weight=1)
            widget = self._setting_widget(control, name)
            widget.grid(row=0, column=0, sticky="ew")
            unit = self.SETTING_UNITS.get(name, "")
            if unit:
                ttk.Label(control, text=unit, foreground="#70757d").grid(
                    row=0, column=1, sticky="w", padx=(6, 0)
                )

            info = ttk.Label(group, text="ⓘ", foreground="#6b7280", cursor="hand2")
            info.grid(row=row, column=2, sticky="w", padx=(8, 0))
            callback = lambda n=name, hi=help_images: self._show_setting_help(
                n, show_layout_image=hi
            )
            self._bind_help_widget(label_widget, callback)
            self._bind_help_widget(control, callback)
            self._bind_help_widget(info, callback)
            info.bind(
                "<Button-1>",
                lambda _event, n=name, hi=help_images: self._show_setting_help(
                    n, show_layout_image=hi
                ),
                add="+",
            )

            row += 1
        return group

    def _add_check_group(
        self,
        parent: ttk.Frame,
        title: str,
        checks: tuple[tuple[str, str], ...] | list[tuple[str, str]],
        *,
        intro: str = "",
    ) -> ttk.LabelFrame:
        group = ttk.LabelFrame(parent, text=title, padding=(12, 9))
        group.pack(fill="x", pady=(0, 10))
        group.columnconfigure(0, weight=1)
        row = 0
        if intro:
            intro_label = ttk.Label(
                group, text=intro, foreground="#5f6670", justify="left",
            )
            intro_label.grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8)
            )
            self._bind_responsive_labels(
                group, intro_label, horizontal_padding=24, min_wrap=150
            )
            row += 1

        auto_child_names = (
            "ordinary_auto_columns",
            "ordinary_auto_start_y",
            "ordinary_auto_manual_x",
            "ordinary_auto_column_width",
            "ordinary_auto_gutter",
            "ordinary_auto_character_height",
            "ordinary_auto_row_padding",
        )
        auto_child_set = set(auto_child_names)
        auto_children = [
            (label, name) for label, name in checks if name in auto_child_set
        ]

        for label, name in checks:
            if name in auto_child_set:
                continue
            if name not in self.vars:
                self.vars[name] = tk.BooleanVar(
                    value=bool(getattr(self.parent.settings, name))
                )
            check = ttk.Checkbutton(group, text=label, variable=self.vars[name])
            check.grid(row=row, column=0, sticky="w", pady=4)
            if name == "layout_mask_illustrations_use_existing":
                parent_mask = self.vars.get("layout_mask_illustrations")
                if parent_mask is not None:
                    def _sync_illustration_reuse_state(*_ignored, master=parent_mask, child=check):
                        child.configure(state="normal" if master.get() else "disabled")
                    parent_mask.trace_add("write", _sync_illustration_reuse_state)
                    _sync_illustration_reuse_state()
            info = ttk.Label(group, text="ⓘ", foreground="#6b7280", cursor="hand2")
            info.grid(row=row, column=1, sticky="w", padx=(8, 0))
            callback = lambda l=label, n=name: self._show_check_help(l, n)
            self._bind_help_widget(check, callback)
            self._bind_help_widget(info, callback)
            info.bind(
                "<Button-1>",
                lambda _e, l=label, n=name: self._show_check_help(l, n),
                add="+",
            )
            row += 1

            if name == "ordinary_auto_layout" and auto_children:
                child_grid = ttk.Frame(group)
                child_grid.grid(
                    row=row, column=0, columnspan=2,
                    sticky="w", padx=(22, 0), pady=(0, 4),
                )
                for index, (child_label, child_name) in enumerate(auto_children):
                    if child_name not in self.vars:
                        self.vars[child_name] = tk.BooleanVar(
                            value=bool(getattr(self.parent.settings, child_name))
                        )
                    child_row = 0 if index < 3 else 1
                    child_col = index if index < 3 else index - 3
                    child = ttk.Checkbutton(
                        child_grid,
                        text=child_label,
                        variable=self.vars[child_name],
                    )
                    child.grid(
                        row=child_row, column=child_col,
                        sticky="w", padx=(0, 16), pady=4,
                    )
                    child_callback = (
                        lambda l=child_label, n=child_name:
                        self._show_check_help(l, n)
                    )
                    self._bind_help_widget(child, child_callback)
                row += 1
        return group

    def _add_collapsible_settings(
        self,
        parent: ttk.Frame,
        title: str,
        names: tuple[str, ...] | list[str],
        checks: tuple[tuple[str, str], ...] | list[tuple[str, str]] = (),
    ) -> None:
        shell = ttk.Frame(parent)
        shell.pack(fill="x", pady=(0, 10))
        expanded = tk.BooleanVar(value=False)
        title_var = tk.StringVar(value=f"▸ {title}")
        body = ttk.Frame(shell)

        def toggle() -> None:
            if expanded.get():
                expanded.set(False)
                body.pack_forget()
                title_var.set(f"▸ {title}")
            else:
                expanded.set(True)
                title_var.set(f"▾ {title}")
                body.pack(fill="x", pady=(6, 0))

        ttk.Button(shell, textvariable=title_var, command=toggle).pack(fill="x")
        if names:
            self._add_setting_group(body, "参数", names)
        if checks:
            self._add_check_group(body, "行为", checks)

    def _scrollable_settings_page(self, tab: ttk.Frame) -> ttk.Frame:
        host = ttk.Frame(tab)
        host.pack(fill="both", expand=True)

        panes = ttk.Panedwindow(host, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        canvas = tk.Canvas(left, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        content = ttk.Frame(canvas, padding=(14, 12, 10, 18))
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind(
            "<Configure>",
            lambda _e, cv=canvas: cv.configure(scrollregion=cv.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e, cv=canvas, item=window: cv.itemconfigure(item, width=e.width),
        )
        self._settings_canvases[str(tab)] = canvas

        right = ttk.Frame(panes, padding=(6, 8, 8, 8))
        panes.add(left, weight=3)
        panes.add(right, weight=2)

        split_initialized = {"done": False}

        def initialize_split(_event=None) -> None:
            if split_initialized["done"]:
                return
            try:
                width = int(panes.winfo_width())
                if width <= 200:
                    return
                panes.sashpos(0, int(width * 0.60))
                split_initialized["done"] = True
            except tk.TclError:
                return

        panes.bind("<Map>", initialize_split, add="+")
        panes.bind("<Configure>", initialize_split, add="+")
        self.after_idle(initialize_split)

        help_box = ttk.LabelFrame(right, text="设置说明", padding=(14, 12))
        help_box.pack(fill="both", expand=True)
        help_title = ttk.Label(
            help_box,
            textvariable=self._settings_help_title_var,
            font=("TkDefaultFont", 10, "bold"),
            justify="left",
        )
        help_title.pack(anchor="w", fill="x", padx=(0, 6))
        # Each tab owns a vertically scrollable help pane. The old Label
        # wrapped long explanations but clipped their bottom beyond the window.
        help_view = ttk.Frame(help_box)
        help_view.pack(fill="both", expand=True, pady=(7, 0))
        help_canvas = tk.Canvas(help_view, borderwidth=0, highlightthickness=0)
        help_scroll = ttk.Scrollbar(help_view, orient="vertical", command=help_canvas.yview)
        help_canvas.configure(yscrollcommand=help_scroll.set)
        help_canvas.pack(side="left", fill="both", expand=True)
        help_scroll.pack(side="right", fill="y")
        help_content = ttk.Frame(help_canvas)
        help_window = help_canvas.create_window((0, 0), window=help_content, anchor="nw")
        help_content.bind(
            "<Configure>",
            lambda _e, cv=help_canvas: cv.configure(scrollregion=cv.bbox("all")),
            add="+",
        )
        help_canvas.bind(
            "<Configure>",
            lambda e, cv=help_canvas, item=help_window: cv.itemconfigure(
                item, width=max(1, e.width)
            ),
            add="+",
        )
        self._settings_help_scroll_canvases.append(help_canvas)
        # Bind the live variable in every tab rather than taking a snapshot.
        help_body = ttk.Label(
            help_content,
            textvariable=self._settings_help_body_var,
            foreground="#555b63",
            justify="left",
            anchor="nw",
            wraplength=300,
        )
        help_body.pack(anchor="w", fill="x", padx=(0, 8))
        help_image = ttk.Label(help_content, anchor="center")
        help_separator = ttk.Separator(help_content, orient="horizontal")
        help_separator.pack(fill="x", pady=(14, 10))
        self._settings_help_image_widgets.append(
            (help_image, help_separator, help_content)
        )
        help_hint = ttk.Label(
            help_content,
            text="把鼠标停在设置项上、点击 ⓘ，或用 Tab/鼠标进入输入框时，"
                 "右侧会显示完整说明与版面图解；左侧只保留参数、单位和必要状态。",
            foreground="#7a8088",
            justify="left",
        )
        help_hint.pack(anchor="w", fill="x", padx=(0, 6))
        self._bind_responsive_labels(
            help_content,
            help_body,
            help_hint,
            horizontal_padding=18,
            min_wrap=120,
        )

        def scroll_help(event) -> str:
            direction = (
                (-1 if event.num == 4 else 1)
                if getattr(event, "num", None) in (4, 5)
                else (-1 if getattr(event, "delta", 0) > 0 else 1)
            )
            help_canvas.yview_scroll(3 * direction, "units")
            return "break"

        for wheel_widget in (help_canvas, help_content, help_body, help_hint, help_image):
            for event_name in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                wheel_widget.bind(event_name, scroll_help, add="+")
        help_box.bind(
            "<Configure>",
            lambda _e: self._schedule_settings_help_image_render(),
            add="+",
        )
        return content

    def _settings_intro(self, parent: ttk.Frame, title: str, text: str) -> None:
        title_label = ttk.Label(
            parent, text=title, font=("TkDefaultFont", 11, "bold"), justify="left",
        )
        title_label.pack(anchor="w", fill="x")
        body_label = ttk.Label(
            parent, text=text, foreground="#5f6670", justify="left",
        )
        body_label.pack(anchor="w", fill="x", pady=(3, 10))
        self._bind_responsive_labels(
            parent,
            title_label,
            body_label,
            horizontal_padding=12,
            min_wrap=160,
        )

    def __init__(self, parent: "PictureCaptureApp", initial_tab: str | None = None) -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("设置中心")
        self.update_idletasks()
        screen_w = max(900, self.winfo_screenwidth())
        screen_h = max(650, self.winfo_screenheight())
        fit_window_to_work_area(
            self,
            min(1120, max(840, int(screen_w * 0.80))),
            max(560, int(screen_h * 0.75)),
            min_width=840,
            min_height=560,
        )
        self.resizable(True, True)
        self.vars: dict[str, tk.Variable] = {}
        self.crop_vars: dict[str, tk.Variable] = {}
        self._crop_specials: dict[str, dict] = {}
        self._casts = {name: cast for _, name, cast in self.FIELDS}
        self._field_meta = {name: (label, cast) for label, name, cast in self.FIELDS}
        self._sort_label_to_value: dict[str, str] = {}
        self._settings_help_title_var = tk.StringVar(value="这里会解释当前设置")
        self._settings_help_body_var = tk.StringVar(
            value="把鼠标停在任一设置项上，或进入输入框，即可看到它控制什么、"
                  "什么时候需要调整，以及调大/调小可能带来的影响。"
        )
        self._settings_save_status_var = tk.StringVar(value="✓ 自动保存已开启")
        self._settings_help_current_image: str | None = None
        self._settings_help_original_images: dict[str, Image.Image] = {}
        self._settings_help_image_widgets: list[
            tuple[ttk.Label, ttk.Separator, ttk.LabelFrame]
        ] = []
        self._settings_help_image_job: str | None = None
        self._settings_help_scroll_canvases: list[tk.Canvas] = []

        outer = ttk.Frame(self, padding=(18, 14, 18, 12))
        outer.pack(fill="both", expand=True)
        _build_modern_dialog_heading(
            outer,
            "设置中心",
            "按工作任务整理：第一次使用优先看“常用 / OCR画线”；"
            "普通画线是备用方案，底层阈值、正则和后端参数集中在高级区，不确定时无需修改。",
        )
        self._configure_settings_appearance_styles()
        notebook = ttk.Notebook(outer, style="PC.Settings.TNotebook")
        self.notebook = notebook
        notebook.pack(fill="both", expand=True)
        self._settings_canvases: dict[str, tk.Canvas] = {}

        common_tab = ttk.Frame(notebook)
        normal_tab = ttk.Frame(notebook)
        illustration_tab = ttk.Frame(notebook)
        ref_box_tab = ttk.Frame(notebook)
        performance_tab = ttk.Frame(notebook)
        separator_y_tab = ttk.Frame(notebook)
        ocr_tab = ttk.Frame(notebook)
        display_tab = ttk.Frame(notebook)
        project_tab = ttk.Frame(notebook)
        crop_tab = ttk.Frame(notebook)
        advanced_tab = ttk.Frame(notebook)
        sort_tab = ttk.Frame(notebook)
        rules_tab = ttk.Frame(notebook)
        for tab, label in (
            (common_tab, "常用"),
            (ocr_tab, "OCR画线"),
            (normal_tab, "普通画线"),
            (separator_y_tab, "横线 Y 精修"),
            (illustration_tab, "插图"),
            (ref_box_tab, "REF框"),
            (performance_tab, "性能测试与诊断"),
            (display_tab, "显示/校对"),
            (project_tab, "项目/批量"),
            (crop_tab, "切图"),
            (advanced_tab, "高级"),
            (sort_tab, "排序"),
            (rules_tab, "过滤规则"),
        ):
            notebook.add(tab, text=label)

        self._settings_tabs = {
            "common": common_tab,
            "normal": normal_tab,
            "separator_y": separator_y_tab,
            "illustration": illustration_tab,
            "ref_box": ref_box_tab,
            "performance": performance_tab,
            "ocr": ocr_tab,
            "display": display_tab,
            "project": project_tab,
            "crop": crop_tab,
            "advanced": advanced_tab,
            "profile": advanced_tab,
            "params": common_tab,
            "sort": sort_tab,
            "rules": rules_tab,
        }
        self.select_tab(initial_tab)
        notebook.bind(
            "<<NotebookTabChanged>>",
            lambda _e: self._show_settings_help(
                "设置说明",
                "把鼠标停在任一设置项上，或进入输入框，即可看到它控制什么、"
                "什么时候需要调整，以及调大/调小可能带来的影响。",
            ),
            add="+",
        )

        # Reuse the project profile.
        self._active_profile_key = effective_project_profile_id(
            parent.settings,
            project_profile_path(parent.project.root) if parent.project else None,
        )
        self._profile_selection_changed = False
        self._profile_label_to_key: dict[str, str] = {}

        common = self._scrollable_settings_page(common_tab)
        self._settings_intro(
            common,
            "先确认版面，再用 OCR 画线完成代表页验证",
            "推荐流程：项目Profile → 检测版面参数 → 代表页运行 OCR 画线 → "
            "确认无明显漏线/误线后再批量。OCR画线是默认推荐路径，会同时利用文字、位置和结构证据；"
            "普通画线保留为备用方案，主要用于左缘极稳定的简单版式或 OCR 暂不可用时。",
        )
        workflow = ttk.Frame(common)
        workflow.pack(fill="x", pady=(0, 10))
        profile_button = ttk.Button(
            workflow, text="打开项目Profile…", command=parent.open_project_profile
        )
        profile_button.pack(side="left")
        parent._attach_tooltip(
            profile_button,
            "配置词典信息、阅读方向、页面模板和词头结构，并用代表页测试。",
        )
        layout_button = ttk.Button(
            workflow, text="检测版面参数", command=parent.detect_layout_current
        )
        layout_button.pack(side="left", padx=(6, 0))
        parent._attach_tooltip(
            layout_button,
            "按主界面当前页面范围检测；若页面数量≥2，数值参数取稳健中位数。",
        )
        environment_button = ttk.Button(
            workflow, text="环境中心", command=self.check_ocr_engines
        )
        environment_button.pack(side="left", padx=(6, 0))
        parent._attach_tooltip(
            environment_button,
            "检查 OCR、Tesseract、Lens、OpenCC 等运行环境。",
        )

        mode_group = ttk.LabelFrame(common, text="默认画线方式", padding=(12, 9))
        mode_group.pack(fill="x", pady=(0, 10))
        mode_group.columnconfigure(1, weight=1)
        method_var = tk.StringVar(
            value=DETECTION_LABELS.get(
                parent.settings.detection_method, DETECTION_LABELS["paddleocr"]
            )
        )
        self.vars["detection_method"] = method_var

        combined_mode = ttk.Radiobutton(
            mode_group,
            text="融合画线+OCR",
            variable=method_var,
            value=DETECTION_LABELS["combined"],
        )
        combined_mode.grid(row=0, column=0, sticky="w", pady=3)
        combined_mode_help = ttk.Label(
            mode_group,
            text="普通几何负责稳定定位，OCR负责语义确认与独立救漏；最终统一配对去重。",
            foreground="#666666",
            justify="left",
        )
        combined_mode_help.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=3)
        self._bind_responsive_labels(
            combined_mode_help, combined_mode_help, horizontal_padding=4, min_wrap=100
        )

        ocr_mode = ttk.Radiobutton(
            mode_group,
            text="OCR画线（默认）",
            variable=method_var,
            value=DETECTION_LABELS["paddleocr"],
        )
        ocr_mode.grid(row=1, column=0, sticky="w", pady=3)
        ocr_mode_help = ttk.Label(
            mode_group,
            text="只运行 OCR / parser / 视觉候选链，便于定位 OCR 侧问题。",
            foreground="#666666",
            justify="left",
        )
        ocr_mode_help.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=3)
        self._bind_responsive_labels(
            ocr_mode_help, ocr_mode_help, horizontal_padding=4, min_wrap=100
        )

        normal_mode = ttk.Radiobutton(
            mode_group,
            text="普通画线（单独诊断）",
            variable=method_var,
            value=DETECTION_LABELS["left_edge"],
        )
        normal_mode.grid(row=2, column=0, sticky="w", pady=3)
        normal_mode_help = ttk.Label(
            mode_group,
            text="只运行 VB 左缘几何/墨迹链；速度最快，适合检查缩进型版式的几何基线。",
            foreground="#666666",
            justify="left",
        )
        normal_mode_help.grid(row=2, column=1, sticky="ew", padx=(12, 0), pady=3)
        self._bind_responsive_labels(
            normal_mode_help, normal_mode_help, horizontal_padding=4, min_wrap=100
        )

        for widget, title, body in (
            (
                combined_mode,
                "融合画线+OCR",
                "两条成熟路径各自完整运行后再融合：普通模式提供高速、稳定的几何词条边界；"
                "OCR 模式提供词头文字、结构证据和普通模式之外的独立救漏。程序只在同栏、Y位置足够接近时一对一配对；"
                "匹配项输出唯一横线并继承 OCR 文字，未匹配项保留各自救漏能力，最后再用更严格阈值去重。"
                "普通/括号词优先保留 VB 分隔线位置；单个大汉字保留 OCR 的专用自适应精修位置。",
            ),
            (
                ocr_mode,
                "OCR画线（默认）",
                "单独运行现有 OCR 候选链，用于排查 OCR、词头 parser、符号/字高/粗体等结构证据。"
                "原始 OCR 缓存仍可复用。",
            ),
            (
                normal_mode,
                "普通画线（单独诊断）",
                "单独运行恢复的 VB.NET 左缘规则链，只看版面几何、墨迹和正文缩进。"
                "适合验证普通模式本身的定位效果和速度。",
            ),
        ):
            self._bind_help_widget(
                widget,
                lambda t=title, b=body: self._show_settings_help(t, b),
            )
        self._add_setting_group(
            common,
            "常用版面参数",
            self.COMMON_FIELDS,
            intro="这些值同时影响普通画线、OCR画线和后续切图。能自动检测时，优先使用检测结果。",
            help_images=True,
        )

        normal = self._scrollable_settings_page(normal_tab)
        self._settings_intro(
            normal,
            "普通画线（备用）：只使用几何和栏左墨迹",
            "这是二线方案，适合词头基本贴近栏左缘、释义正文有稳定缩进的简单版式，"
            "或 OCR 环境暂不可用时临时使用。若 OCR 可用，仍建议优先从 OCR画线开始。",
        )
        self._add_setting_group(
            normal,
            "常用设置",
            self.NORMAL_COMMON_FIELDS,
            intro="第一次使用通常只需要确认这四项。墨迹判断方式建议保持“自动（推荐）”。",
        )
        self._add_check_group(
            normal,
            "版面行为",
            self.NORMAL_CHECKS,
            intro="【使用自动版面参数】下面的七项决定每页检测后临时更新哪些版面字段；【跟随栏左缘倾斜/弯曲】及其三个百分比参数用于页面局部几何跟踪。",
        )
        self._add_collapsible_settings(
            normal,
            "高级设置（普通画线异常时再展开）",
            self.NORMAL_ADVANCED_FIELDS,
        )

        # Cross-cutting feature, not an OCR-only or ordinary-only option.
        separator_y_page = self._scrollable_settings_page(separator_y_tab)
        self._settings_intro(
            separator_y_page, "横线 Y 精修（所有画线共用）",
            "集中控制 OCR 与普通画线共享的局部墨迹谷精修。"
            "横向分析范围对新项目默认 100%；老项目已保存的取值保持不变。",
        )
        self._add_check_group(
            separator_y_page, "启用与安全检查", self.SEPARATOR_Y_CHECKS,
            intro="白缝安全核验为实验性功能，默认关闭。",
        )
        self._add_setting_group(
            separator_y_page, "精修参数", self.SEPARATOR_Y_FIELDS,
            intro="横向范围 100% 表示在扣除栏边余量后的整栏可用宽度内寻找空白带；"
            "并非保证每条线均不穿字。",
        )

        _settings_illustration_ui.build_illustration_settings_tab(self, illustration_tab)
        _settings_ref_box_ui.build_ref_box_settings_tab(self, ref_box_tab)
        performance_page = self._scrollable_settings_page(performance_tab)
        self._settings_intro(
            performance_page, "性能测试与诊断",
            "本页管理运行时测试开关和性能报告；项目设置会自动保存，"
            "新启动的普通画线子进程继承对应选项。",
        )
        self._add_check_group(
            performance_page, "分析图与性能日志",
            (
                ("启用普通画线性能诊断（导出 Markdown/CSV）", "draw_performance_profile"),
                ("复用已处理的分析图（实验）", "reuse_prepared_analysis"),
            ),
            intro="复用功能可能改变重复去噪语义，务必先比较完整 PDIC。",
        )
        _settings_inference_ui.build_inference_performance_group(self, performance_page)

        ocr_page = self._scrollable_settings_page(ocr_tab)
        self._settings_intro(
            ocr_page,
            "OCR画线（推荐默认）：用文字 + 版式 + 视觉证据判断真正词头",
            "优先使用这一模式。PaddleOCR 负责主识别；可选 Tesseract 作为第二意见，"
            "Google Lens 作为冲突时的第三意见。OCR 原始结果有缓存：参数只改变候选判断时无需重新跑 OCR。",
        )
        self._add_setting_group(
            ocr_page,
            "常用设置",
            self.OCR_COMMON_FIELDS,
            intro="先调识别范围与左缘容差；候选分数、合并阈值等放在高级区。",
        )
        self._add_check_group(
            ocr_page,
            "识别策略",
            self.OCR_COMMON_CHECKS,
            intro="结构/视觉提示用于减少正文误检；双 OCR 会更稳，但会增加运行时间。",
        )
        lens_group = ttk.LabelFrame(ocr_page, text="Google Lens（可选）", padding=(12, 9))
        lens_group.pack(fill="x", pady=(0, 10))
        if "paddle_enable_lens" not in self.vars:
            self.vars["paddle_enable_lens"] = tk.BooleanVar(
                value=bool(parent.settings.paddle_enable_lens)
            )
        lens_enable_check = ttk.Checkbutton(
            lens_group, text="启用 Lens 第三意见",
            variable=self.vars["paddle_enable_lens"],
        )
        lens_enable_check.pack(anchor="w")
        self._bind_help_widget(
            lens_enable_check,
            lambda: self._show_check_help("启用 Lens 第三意见", "paddle_enable_lens"),
        )
        lens_help = ttk.Label(
            lens_group,
            text="建议只在 Paddle/Tesseract 冲突时使用，避免不必要的网络等待。",
            foreground="#666666",
            justify="left",
        )
        lens_help.pack(anchor="w", fill="x", pady=(2, 5))
        self._bind_responsive_labels(
            lens_group, lens_help, horizontal_padding=12, min_wrap=120
        )
        lens_mode_var = tk.StringVar(
            value=LENS_MODE_LABELS.get(
                parent.settings.paddle_lens_mode, LENS_MODE_LABELS["conflict"]
            )
        )
        self.vars["paddle_lens_mode"] = lens_mode_var
        lens_row = ttk.Frame(lens_group)
        lens_row.pack(fill="x")
        ttk.Label(lens_row, text="运行模式：").pack(side="left")
        lens_mode_combo = ttk.Combobox(
            lens_row, textvariable=lens_mode_var, values=tuple(LENS_MODE_VALUES),
            state="readonly", width=34,
        )
        lens_mode_combo.pack(side="left")
        self._bind_help_widget(
            lens_row,
            lambda: self._show_setting_help("paddle_lens_mode"),
        )
        self._add_collapsible_settings(
            ocr_page,
            "高级设置（漏检/误检有明确模式时再展开）",
            self.OCR_ADVANCED_FIELDS,
            self.OCR_ADVANCED_CHECKS,
        )

        display = self._scrollable_settings_page(display_tab)
        self._settings_intro(
            display,
            "显示与校对只改变工作体验，不应该被误认为识别阈值",
            "字体、词框宽度、校对缩放和参考词表都集中在这里。"
            "修改这些项目不会改变普通画线/OCR画线的词头判断。",
        )
        appearance_group = ttk.LabelFrame(display, text="应用外观", padding=(12, 9))
        appearance_group.pack(fill="x", pady=(0, 10))
        appearance_row = ttk.Frame(appearance_group)
        appearance_row.pack(anchor="w", fill="x")
        ttk.Label(appearance_row, text="颜色模式：").pack(side="left")
        appearance_combo = ttk.Combobox(
            appearance_row, textvariable=self.parent.appearance_mode_var,
            values=tuple(APPEARANCE_MODE_VALUES), state="readonly", width=10,
        )
        appearance_combo.pack(side="left", padx=(4, 0))
        appearance_combo.bind("<<ComboboxSelected>>", self.parent._appearance_mode_selected)
        appearance_help = ttk.Label(
            appearance_group,
            text="浅色使用正常界面；深色同步主界面、校对/Profile/设置窗口及扫描图夜间预览；"
                 "跟随系统会自动响应 Windows、macOS 与 Linux 的系统颜色模式。"
                 "仅改变显示，不修改原图、OCR 输入、PDIC/PPP、切图或导出文件。",
            justify="left",
        )
        appearance_help.pack(anchor="w", fill="x", pady=(4, 0))
        self._bind_responsive_labels(
            appearance_group, appearance_help, horizontal_padding=24, min_wrap=160
        )
        self._add_setting_group(
            display,
            "界面与校对",
            self.DISPLAY_FIELDS,
        )
        self._add_check_group(
            display,
            "显示行为",
            self.DISPLAY_STYLE_CHECKS + self.DISPLAY_CHECKS,
        )

        project_page = self._scrollable_settings_page(project_tab)
        self._settings_intro(
            project_page,
            "项目资料与运行环境",
            "项目名称/语言等资料用于导出和词典制作；运行环境参数只在相应功能启用时生效。",
        )
        self._add_setting_group(
            project_page,
            "项目资料",
            (
                "dictionary_full_name", "dictionary_abbreviation", "dictionary_isbn",
                "dictionary_index_language", "dictionary_content_language",
                "dictionary_body_page_range",
            ),
        )
        self._add_setting_group(
            project_page,
            "运行与性能",
            self.PROJECT_RUNTIME_FIELDS,
            intro="OCR 模型和 Tesseract 路径稳定后不要频繁修改；模型/语言发生变化时应重新 OCR。",
        )
        text_ocr_group = ttk.LabelFrame(
            project_page, text="普通文本 OCR（不是 OCR画线）", padding=(12, 9)
        )
        text_ocr_group.pack(fill="x", pady=(0, 10))
        text_ocr_group.columnconfigure(2, weight=1)
        ocr_engine_var = tk.StringVar(
            value=OCR_ENGINE_LABELS.get(
                parent.settings.ocr_engine, OCR_ENGINE_LABELS["tesseract"]
            )
        )
        self.vars["ocr_engine"] = ocr_engine_var
        ttk.Label(text_ocr_group, text="OCR 引擎：").grid(
            row=0, column=0, sticky="e", padx=(0, 10), pady=4
        )
        ocr_engine_combo = ttk.Combobox(
            text_ocr_group, textvariable=ocr_engine_var,
            values=tuple(OCR_ENGINE_VALUES), state="readonly", width=28,
        )
        ocr_engine_combo.grid(row=0, column=1, sticky="w", pady=4)
        self._bind_help_widget(
            ocr_engine_combo,
            lambda: self._show_setting_help("ocr_engine"),
        )
        text_ocr_help = ttk.Label(
            text_ocr_group,
            text="用于“已有横线后再识别整行文本”的普通 OCR 功能；"
                 "OCR画线使用上一个页签中的多引擎流程，两者不要混淆。",
            foreground="#666666",
            justify="left",
        )
        text_ocr_help.grid(row=0, column=2, sticky="ew", padx=(12, 0), pady=4)
        self._bind_responsive_labels(
            text_ocr_help, text_ocr_help, horizontal_padding=4, min_wrap=120
        )
        project_checks = (
            ("OCR 后执行替换规则", "ocr_replace"),
            ("普通 OCR 文本转小写", "lowercase_ocr"),
        )
        self._add_check_group(project_page, "普通 OCR 文本处理", project_checks)

        self._build_crop_settings_tab(crop_tab)

        advanced = self._scrollable_settings_page(advanced_tab)
        self._settings_intro(
            advanced,
            "高级 / 专家参数",
            "这里保留版面语义、OCR 后端和正则规则等底层控制。"
            "如果只是想提高某本词典的识别率，请优先回到“OCR画线”页或【项目Profile】；"
            "只有左缘高度规则的简单版式才优先考虑“普通画线（备用）”。",
        )
        ttk.Button(
            advanced, text="打开项目Profile（推荐）…", command=parent.open_project_profile
        ).pack(anchor="w", pady=(0, 10))
        self._add_setting_group(advanced, "版面与后端", self.EXPERT_FIELDS)

        def _wheel(event) -> str | None:
            selected = notebook.select()
            target = self._settings_canvases.get(str(selected))
            if target is None:
                return None
            if getattr(event, "num", None) == 4:
                target.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                target.yview_scroll(3, "units")
            else:
                delta = getattr(event, "delta", 0)
                if delta:
                    target.yview_scroll(
                        (-1 if delta > 0 else 1)
                        * max(1, abs(int(delta / 120))) * 3,
                        "units",
                    )
            return "break"

        self.bind("<MouseWheel>", _wheel)
        self.bind("<Button-4>", _wheel)
        self.bind("<Button-5>", _wheel)

        # Language-aware collation tab.
        sort_frame = self._scrollable_settings_page(sort_tab)
        sort_frame.columnconfigure(1, weight=1)
        self.sort_language_var = tk.StringVar(value="")
        ttk.Label(sort_frame, text="OCR 语言：").grid(row=0, column=0, sticky="e", pady=4)
        ttk.Label(sort_frame, textvariable=self.sort_language_var).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(sort_frame, text="排序预设：").grid(row=1, column=0, sticky="e", pady=4)
        self.sort_mode_var = tk.StringVar(value="")
        self.vars["headword_sort_mode"] = self.sort_mode_var
        self.sort_combo = ttk.Combobox(sort_frame, textvariable=self.sort_mode_var, state="readonly", width=48)
        self.sort_combo.grid(row=1, column=1, sticky="ew", pady=4)
        self.sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._toggle_custom_sort_state())
        self._bind_help_widget(
            self.sort_combo,
            lambda: self._show_setting_help("headword_sort_mode"),
        )

        ttk.Label(sort_frame, text="自定义排序单元：").grid(row=2, column=0, sticky="ne", pady=(10, 4))
        custom_box = ttk.Frame(sort_frame)
        custom_box.grid(row=2, column=1, sticky="ew", pady=(10, 4))
        custom_box.columnconfigure(0, weight=1)
        self.custom_order_var = tk.StringVar(value=getattr(parent.settings, "headword_custom_order", LATIN_ORDER))
        self.vars["headword_custom_order"] = self.custom_order_var
        self.custom_order_entry = ttk.Entry(custom_box, textvariable=self.custom_order_var)
        self.custom_order_entry.grid(row=0, column=0, sticky="ew")
        self._bind_help_widget(
            self.custom_order_entry,
            lambda: self._show_setting_help("headword_custom_order"),
        )
        ttk.Label(custom_box, text="空格分隔；允许多字符单元，如 ch / ll / dz").grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.custom_fold_var = tk.BooleanVar(value=bool(getattr(parent.settings, "headword_custom_fold_accents", True)))
        self.vars["headword_custom_fold_accents"] = self.custom_fold_var
        self.custom_fold_check = ttk.Checkbutton(sort_frame, text="自定义规则中，未单列的重音字母按基础字母排序", variable=self.custom_fold_var)
        self.custom_fold_check.grid(row=3, column=1, sticky="w", pady=4)
        self._bind_help_widget(
            self.custom_fold_check,
            lambda: self._show_setting_help("headword_custom_fold_accents"),
        )
        help_text = (
            "排序只控制词头的比较/索引顺序，不会重排扫描图片，也不会改 PDIC 坐标。\n"
            "预设会随 OCR 语言变化；语言专用预设用于符合对应词典的字母序，始终还可选择通用 Unicode 或自定义。\n"
            "自定义顺序用空格分隔排序单元，可写 ch / ll / dz 等多字符单位；例如旧式西班牙语："
            "a b c ch d e f g h i j k l ll m n ñ o p q r s t u v w x y z。\n"
            "如果重音字母有独立排序地位，应显式列入自定义顺序；否则可用“按基础字母排序”折叠。"
        )
        sort_help = ttk.Label(sort_frame, text=help_text, justify="left")
        sort_help.grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )
        self._bind_responsive_labels(
            sort_frame, sort_help, horizontal_padding=24, min_wrap=180
        )
        self._refresh_sort_choices(initial=True)

        # User-editable OCR headword filter rules.
        rules_tab.columnconfigure(0, weight=1)
        rules_tab.rowconfigure(1, weight=1)
        rules_help = (
            "这是项目级候选覆盖层：用于处理某一本词典反复出现、但不值得改全局 parser/Profile 的例外。每行一条；# 开头为注释。\n"
            "拒绝规则优先于强制接受：reject_lemma_exact / reject_lemma_regex 针对 lemma；"
            "reject_line_contains / reject_line_regex 针对整行。accept_* 可救回已成功解析且位于合法栏左区域的候选，"
            "但不能把任意页眉/噪声变成词头。pos_exclude_exact / pos_exclude_regex 用于排除容易被误当 POS 的固定标签。\n"
            "修改过滤规则通常只需要重新跑候选解析，不必强制重做 PaddleOCR；若问题属于整类词典结构，应优先写入 Project Profile。"
        )
        rules_help_label = ttk.Label(
            rules_tab, text=rules_help, justify="left", padding=(12, 10, 12, 6)
        )
        rules_help_label.grid(row=0, column=0, sticky="ew")
        self._bind_responsive_labels(
            rules_tab, rules_help_label, horizontal_padding=24, min_wrap=180
        )
        rules_editor_frame = ttk.Frame(rules_tab, padding=(12, 0, 12, 6))
        rules_editor_frame.grid(row=1, column=0, sticky="nsew")
        rules_editor_frame.columnconfigure(0, weight=1); rules_editor_frame.rowconfigure(0, weight=1)
        self.rules_text = tk.Text(rules_editor_frame, wrap="none", undo=True, font=(preferred_font_family(self, ("Consolas", "Menlo", "DejaVu Sans Mono"), fallback_named_font="TkFixedFont"), 10), padx=8, pady=8, height=18)
        rules_ybar = ttk.Scrollbar(rules_editor_frame, orient="vertical", command=self.rules_text.yview)
        rules_xbar = ttk.Scrollbar(rules_editor_frame, orient="horizontal", command=self.rules_text.xview)
        self.rules_text.configure(yscrollcommand=rules_ybar.set, xscrollcommand=rules_xbar.set)
        self.rules_text.grid(row=0, column=0, sticky="nsew"); rules_ybar.grid(row=0, column=1, sticky="ns"); rules_xbar.grid(row=1, column=0, sticky="ew")
        rules_buttons = ttk.Frame(rules_tab, padding=(12, 0, 12, 10))
        rules_buttons.grid(row=2, column=0, sticky="ew")
        ttk.Button(rules_buttons, text="恢复默认规则", command=self.restore_default_rules).pack(side="left")
        ttk.Button(rules_buttons, text="导入规则…", command=self.import_rules).pack(side="left", padx=(8, 0))
        ttk.Button(rules_buttons, text="导出规则…", command=self.export_rules).pack(side="left", padx=(8, 0))
        self.rules_status_var = tk.StringVar(value="")
        ttk.Label(rules_buttons, textvariable=self.rules_status_var).pack(side="right")
        self.load_rules_editor()

        ttk.Separator(outer, orient="horizontal").pack(fill="x")
        footer = ttk.Frame(outer, padding=(0, 10, 0, 0))
        footer.pack(fill="x")
        ttk.Label(
            footer,
            textvariable=self._settings_save_status_var,
            foreground="#666666",
        ).pack(side="left")
        ttk.Button(
            footer, text="关闭", command=self._close_validated
        ).pack(side="right")
        ttk.Button(
            footer, text="校验当前设置",
            command=lambda: self._validate_settings_now(),
        ).pack(side="right", padx=(0, 8))
        _project_templates.add_default_button(footer, self)
        self.bind("<Control-s>", lambda _event: self._validate_settings_now())
        self.bind("<Escape>", lambda _event: self._close_validated())
        self.protocol("WM_DELETE_WINDOW", self._close_validated)
        self._autosave_job: str | None = None
        self._autosave_ready = True
        for _name, _var in self.vars.items():
            try:
                _var.trace_add("write", lambda *_args: self._schedule_autosave())
            except Exception:
                pass
        for _name, _var in self.crop_vars.items():
            try:
                _var.trace_add("write", lambda *_args: self._schedule_autosave())
            except Exception:
                pass
        # Keep the dialog modeless.
        # Do not use transient()/grab_set(), which would keep this window in
        # front and block interaction with the main workspace.

    @staticmethod
    def _crop_nonnegative_int(value: object, label: str) -> int:
        return _settings_crop_ui.crop_nonnegative_int(value, label)

    def _build_crop_settings_tab(self, tab: ttk.Frame) -> None:
        _settings_crop_ui.build_crop_settings_tab(self, tab)

    def _crop_settings_payload(self) -> dict:
        return _settings_crop_ui.crop_settings_payload(self)

    def _save_integrated_crop_settings(self) -> None:
        _settings_crop_ui.save_integrated_crop_settings(self)

    def _configure_settings_appearance_styles(self) -> None:
        _settings_window_ui.configure_settings_appearance_styles(self)

    def refresh_appearance(self) -> None:
        _settings_window_ui.refresh_appearance(self)

    def select_tab(self, key: str | None) -> None:
        _settings_window_ui.select_tab(self, key)

    def _build_project_details_tab(self, tab: ttk.Frame) -> None:
        _settings_project_ui.build_project_details_tab(
            self,
            tab,
            language_codes=PROJECT_LANGUAGE_CODES,
            language_from_ocr=project_language_from_ocr,
        )

    def _build_profile_tab(self, tab: ttk.Frame) -> None:
        _settings_profile_ui.build_profile_tab(self, tab)

    def _build_profile_choice_labels(self) -> dict[str, str]:
        return _settings_profile_ui.build_profile_choice_labels(self)

    def _profile_label_for_key(self, key: str) -> str:
        return _settings_profile_ui.profile_label_for_key(self, key)

    def _profile_display_name(self, key: str) -> str:
        return _settings_profile_ui.profile_display_name(self, key)

    def _sync_custom_profile_name_state(self) -> None:
        _settings_profile_ui.sync_custom_profile_name_state(self)

    def _on_custom_profile_name_changed(self) -> None:
        _settings_profile_ui.on_custom_profile_name_changed(self)

    def _current_profile_key(self) -> str:
        return _settings_profile_ui.current_profile_key(self)

    def _refresh_profile_summary(self) -> None:
        _settings_profile_ui.refresh_profile_summary(self)

    def _coerce_profile_var(self, name: str):
        return _settings_profile_ui.coerce_profile_var(self, name)

    def _refresh_profile_status(self) -> None:
        _settings_profile_ui.refresh_profile_status(self)

    def _apply_profile_defaults_to_vars(
        self,
        key: str,
        *,
        keep_supported_language: bool = True,
    ) -> None:
        _settings_profile_ui.apply_profile_defaults_to_vars(
            self,
            key,
            keep_supported_language=keep_supported_language,
        )

    def _on_profile_selected(self, _event=None) -> None:
        _settings_profile_ui.on_profile_selected(self, _event)

    def restore_profile_defaults(self) -> None:
        _settings_profile_ui.restore_profile_defaults(self)

    def _on_profile_language_changed(self, update_profile_paddle: bool = True) -> None:
        _settings_profile_ui.on_profile_language_changed(
            self, update_profile_paddle=update_profile_paddle
        )

    def _sync_layout_semantics(self) -> None:
        _settings_profile_ui.sync_layout_semantics(self)

    def _refresh_sort_choices(self, initial: bool = False) -> None:
        _settings_profile_ui.refresh_sort_choices(self, initial=initial)

    def _toggle_custom_sort_state(self) -> None:
        _settings_profile_ui.toggle_custom_sort_state(self)

    def _browse_wordslist_setting(self, var: tk.StringVar) -> None:
        _settings_project_ui.browse_wordslist_setting(self, var)

    def _rules_path(self) -> Path | None:
        return _settings_rules_ui.rules_path(self)

    def load_rules_editor(self) -> None:
        _settings_rules_ui.load_rules_editor(self)

    def restore_default_rules(self) -> None:
        _settings_rules_ui.restore_default_rules(self)

    def import_rules(self) -> None:
        _settings_rules_ui.import_rules(self)

    def export_rules(self) -> None:
        _settings_rules_ui.export_rules(self)

    def _schedule_autosave(self) -> None:
        _settings_lifecycle_ui.schedule_autosave(self)

    def _run_autosave(self) -> None:
        _settings_lifecycle_ui.run_autosave(self)

    def _validate_settings_now(self) -> bool:
        return _settings_lifecycle_ui.validate_settings_now(self)

    def _close_validated(self) -> None:
        _settings_lifecycle_ui.close_validated(self)

    def save(self, *, close: bool = True, show_errors: bool = True) -> bool:
        try:
            _settings_lifecycle_ui.validate_projection_width(self.vars)
            _settings_lifecycle_ui.validate_separator_gap_controls(self.vars)
            _settings_lifecycle_ui.validate_ref_box_controls(self.vars)
            _settings_color_ui.validate_color_controls(self.vars)
            previous_language = str(getattr(self.parent.settings, "ocr_language", "") or "")
            previous_backend = {
                name: getattr(self.parent.settings, name, None)
                for name in (
                    "paddle_language", "tesseract_language",
                    "paddle_tesseract_psm", "paddle_use_textline_orientation",
                )
            }
            for name, var in self.vars.items():
                value = var.get()
                if name in self.SETTING_CHOICES:
                    raw_value = self.SETTING_CHOICES[name].get(str(value), str(value))
                    cast = self._casts.get(name, str)
                    setattr(self.parent.settings, name, cast(raw_value))
                elif name in self._casts:
                    if name == "paddle_left_tolerance":
                        percent = float(value)
                        if not 0.0 <= percent <= 100.0:
                            raise ValueError("词头左缘容差必须在 0–100% 单栏宽之间。")
                        setattr(
                            self.parent.settings,
                            name,
                            _column_percent_to_pixels(self.parent.settings, percent),
                        )
                    elif name in LAYOUT_PERCENT_AXES and self.parent.image is not None:
                        percent = float(value)
                        if not 0.0 <= percent <= 100.0:
                            raise ValueError(f"{self.SETTING_LABELS.get(name, name)} 必须在 0–100% 之间。")
                        pixel_value = _layout_percent_to_pixels(
                            self.parent.image, name, percent
                        )
                        setattr(self.parent.settings, name, int(pixel_value))
                    else:
                        setattr(self.parent.settings, name, self._casts[name](value))
                elif name == "detection_method":
                    self.parent.settings.detection_method = DETECTION_VALUES[str(value)]
                elif name == "ocr_engine":
                    self.parent.settings.ocr_engine = OCR_ENGINE_VALUES[str(value)]
                elif name == "paddle_lens_mode":
                    self.parent.settings.paddle_lens_mode = LENS_MODE_VALUES[str(value)]
                elif name == "headword_sort_mode":
                    self.parent.settings.headword_sort_mode = self._sort_label_to_value.get(str(value), "auto")
                elif name == "headword_custom_order":
                    self.parent.settings.headword_custom_order = str(value).strip()
                elif name == "headword_custom_fold_accents":
                    self.parent.settings.headword_custom_fold_accents = bool(value)
                else:
                    setattr(self.parent.settings, name, bool(value))
            if self.parent.image is not None and not str(
                getattr(self.parent.settings, "layout_writing_mode", "horizontal-tb") or "horizontal-tb"
            ).startswith("vertical"):
                if (
                    "start_y" in self.vars
                    and str(getattr(self.parent.settings, "profile_header_mode", "auto") or "auto")
                    == "present"
                ):
                    source_y = int(self.parent.settings.start_y)
                    source_y = max(0, min(self.parent.image.height, source_y))
                    percent = source_y * 100.0 / max(1, self.parent.image.height)
                    if percent > 35.0:
                        raise ValueError("页眉不能超过原图高度的 35%。")
                    self.parent.settings.profile_header_percent = round(percent, 6)
                if (
                    "bottom_y" in self.vars
                    and str(getattr(self.parent.settings, "profile_footer_mode", "auto") or "auto")
                    == "present"
                ):
                    source_y = int(self.parent.settings.bottom_y)
                    source_y = max(0, min(self.parent.image.height, source_y))
                    percent = (
                        (self.parent.image.height - source_y)
                        * 100.0
                        / max(1, self.parent.image.height)
                    )
                    if not 0.0 <= percent <= 35.0:
                        raise ValueError("页尾必须位于原图底部 35% 范围内。")
                    self.parent.settings.profile_footer_percent = round(percent, 6)

            current_language = str(getattr(self.parent.settings, "ocr_language", "") or "")
            if current_language != previous_language:
                derived = language_effective_settings(
                    current_language, self.parent.settings.layout_writing_mode,
                )
                for name, value in derived.items():
                    if not hasattr(self.parent.settings, name):
                        continue
                    # Keep overrides, replacing only old language defaults.
                    if name not in previous_backend or getattr(self.parent.settings, name) == previous_backend[name]:
                        setattr(self.parent.settings, name, value)
            self.parent.settings.paddle_lens_language = str(
                getattr(self.parent.settings, "ocr_language", "") or ""
            )
            self.parent.settings.main_entry_font_family = normalize_content_font_setting(
                self.parent.settings.main_entry_font_family
            )
            self.parent.settings.illustration_label_font_family = normalize_content_font_setting(
                self.parent.settings.illustration_label_font_family
            )
            self.parent.settings.ref_box_font_family = normalize_content_font_setting(
                self.parent.settings.ref_box_font_family
            )
            self.parent.settings.main_entry_font_size = max(5, int(self.parent.settings.main_entry_font_size))
            self.parent.settings.main_entry_width_chars = max(4, int(self.parent.settings.main_entry_width_chars))
            self.parent.settings.main_entry_x_ratio = min(1.25, max(0.0, float(self.parent.settings.main_entry_x_ratio)))
            self.parent.settings.review_entry_font_family = normalize_content_font_setting(
                self.parent.settings.review_entry_font_family
            )
            self.parent.settings.review_simplified_font_family = normalize_content_font_setting(
                self.parent.settings.review_simplified_font_family
            )
            self.parent.settings.review_entry_font_size = max(6, int(self.parent.settings.review_entry_font_size))
            self.parent.settings.review_entry_vertical_padding = min(30, max(0, int(self.parent.settings.review_entry_vertical_padding)))
            self.parent.settings.review_single_cjk_line_height = min(500, max(0, int(self.parent.settings.review_single_cjk_line_height)))
            review_zoom_percent = float(self.parent.settings.review_zoom_percent)
            self.parent.settings.review_zoom_percent = (
                0.0 if review_zoom_percent <= 0 else min(250.0, max(20.0, review_zoom_percent))
            )
            if not 0 <= int(self.parent.settings.crop_parallel_workers) <= 8:
                raise ValueError("切图并行进程数必须为 0–8；0 表示自动，1 表示串行。")
            if not 1.0 <= float(self.parent.settings.paddle_band_width_ratio) <= 100.0:
                raise ValueError("候选带宽比例必须在 1–100 之间；100 即原候选带宽。")
            if int(self.parent.settings.paddle_max_input_side) < 256:
                raise ValueError("OCR输入最大长边必须至少为 256 px。")
            if str(self.parent.settings.paddle_preprocessing) not in {
                "original", "grayscale", "auto_contrast", "binary",
            }:
                raise ValueError("OCR图像预处理必须为 original/grayscale/auto_contrast/binary 之一。")
            if not 10.0 <= float(self.parent.settings.paddle_separator_roi_width_ratio) <= 100.0:
                raise ValueError("Y精修横向分析范围必须在 10–100% 之间。")
            if not 1 <= float(self.parent.settings.right_ratio) <= 100:
                raise ValueError("向右比例必须在 1–100% 之间。")
            if self.parent.settings.headword_sort_mode == "custom":
                parse_custom_order(self.parent.settings.headword_custom_order)
            self._save_integrated_crop_settings()
            self.parent.settings.dictionary_profile_id = self._current_profile_key()
            rules_text = self.rules_text.get("1.0", "end-1c")
            parse_headword_filter_rules(rules_text, "规则编辑框")
            if self.parent.project:
                self.parent.settings.to_json(settings_path(self.parent.project.root))
                write_project_profile(
                    project_profile_path(self.parent.project.root),
                    self.parent.settings,
                    self.parent.settings.dictionary_profile_id,
                    force=bool(getattr(self, "_profile_selection_changed", False)),
                )
                rules_path = headword_filter_rules_path(self.parent.project.root, HEADWORD_FILTER_RULES_FILENAME)
                rules_path.parent.mkdir(parents=True, exist_ok=True)
                rules_path.write_text(rules_text.rstrip() + "\n", encoding="utf-8")
                self.parent._request_wordslist_reload(persist=False, redraw=False)
            self.parent.sync_quick_settings(); self.parent.redraw()
            if close:
                self.destroy()
            return True
        except Exception as exc:
            self._last_settings_error = str(exc)
            if show_errors:
                messagebox.showerror("参数无效", str(exc), parent=self)
            return False

    def check_ocr_engines(self) -> None:
        """Open the shared environment center instead of a transient status dialog."""
        self.parent.show_environment_center()

def _review_window_dimensions(screen_w: int, screen_h: int) -> tuple[int, int]:
    """Default proofreading window size: 60% screen width and 70% screen height."""
    screen_w = max(1, int(screen_w))
    screen_h = max(1, int(screen_h))
    width = min(screen_w, max(560, int(round(screen_w * 0.60))))
    height = min(screen_h, max(420, int(round(screen_h * 0.70))))
    return width, height

def _focused_filter_deps() -> _focused_filter.FocusedFilterDeps:
    """Retain original live app module patchpoints on focused UI dispatch."""
    return _focused_filter.FocusedFilterDeps(
        ReviewWindow=ReviewWindow,
        messagebox=messagebox,
        _focused_review_character_tokens=_focused_review_character_tokens,
        read_pdic=read_pdic,
        pdic_path=pdic_path,
        ocr_cache_root=ocr_cache_root,
        json=json,
        _focused_review_is_single_character=_focused_review_is_single_character,
        _candidate_for_entry_from_list=_candidate_for_entry_from_list,
        _candidate_word_for_ocr_source=_candidate_word_for_ocr_source,
        _review_similarity_key=_review_similarity_key,
        replace=replace,
        normalize_page_rgb=normalize_page_rgb,
        _review_crop_context=_review_crop_context,
        sort_entries_reading_order=sort_entries_reading_order,
        read_page_sections=read_page_sections,
        column_index=column_index,
        _review_line_box=_review_line_box,
        review_auto_fit_zoom=review_auto_fit_zoom,
        Image=Image,
        _format_layout_percent=_format_layout_percent,
        tk=tk,
        ttk=ttk,
        ImageTk=ImageTk,
        resolve_content_font_family=resolve_content_font_family,
        _review_editor_font_size=_review_editor_font_size,
        _entry_font_spec=_entry_font_spec,
        themed_display_image=themed_display_image,
        _apply_focused_review_page_updates=_apply_focused_review_page_updates,
    )


class ReviewWindow(tk.Toplevel):
    # Keep diacritics in predictable vowel groups so visual lookup is quick.
    ACCENT_GROUPS = (
        ("´", ("á", "é", "í", "ó", "ú")),
        ("`", ("à", "è", "ì", "ò", "ù")),
        ("^", ("â", "ê", "î", "ô", "û")),
        ("¨", ("ä", "ë", "ï", "ö", "ü")),
        ("¯", ("ā", "ē", "ī", "ō", "ū")),
        ("其他", ("ã", "ñ", "õ", "ç")),
    )
    DIGIT_KEYS = "1234567890"
    OCR_COMPARE_LABEL_TO_KEY = {
        "融合结果": "fusion",
        "PaddleOCR": "paddle",
        "Tesseract": "tesseract",
        "LENS": "lens",
    }
    OCR_COMPARE_KEY_TO_LABEL = {value: key for key, value in OCR_COMPARE_LABEL_TO_KEY.items()}
    WORDSLIST_LOCATOR_LABEL_TO_KEY = {
        "自动": "auto",
        "外部索引（拼音/字母）": "sorted",
        "同源连续词表": "sequential",
    }
    WORDSLIST_LOCATOR_KEY_TO_LABEL = {value: key for key, value in WORDSLIST_LOCATOR_LABEL_TO_KEY.items()}

    def __init__(self, parent: "PictureCaptureApp") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title(f"词条校对 — {parent.current_page.name if parent.current_page else ''}")
        self.update_idletasks()
        screen_w = max(1, self.winfo_screenwidth())
        screen_h = max(1, self.winfo_screenheight())
        width, height = _review_window_dimensions(screen_w, screen_h)
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        # Only the compact index preset places proofreading beside the image.
        mini = getattr(parent, "workspace_mini_page_host", None)
        compact_workspace = (
            getattr(parent, "workspace_mode", "") in {"极简", "紧凑"}
            or (mini is not None and mini.winfo_manager() == "grid")
        )
        if compact_workspace:
            parent.update_idletasks()
            x = max(0, parent.winfo_rootx() + parent.winfo_width())
            y = max(0, parent.winfo_rooty())
            # Tk client height must exclude window decorations.
            from .ui.workspace_tools import _preset_work_geometry
            work_x, work_y, work_w, safe_client_height = _preset_work_geometry(parent)
            work_right = work_x + work_w
            x = min(max(x, work_x), work_right - 1)
            y = work_y  # Align compact proofreading to the usable desktop top.
            width = max(1, work_right - x)
            height = max(1, safe_client_height)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(300 if compact_workspace else 560, width),
                     min(420, height))
        self.active_index = 0
        # A stored 0 means automatic fit-to-left-pane. Positive values retain
        # the historical explicit/manual percentage mode.
        stored_review_zoom = float(getattr(parent.settings, "review_zoom_percent", 0.0) or 0.0)
        self.review_zoom_auto = stored_review_zoom <= 0
        self.review_zoom = (
            1.0 if self.review_zoom_auto
            else max(0.20, min(2.5, float(stored_review_zoom) / 100.0))
        )
        self.review_zoom_var = tk.StringVar(
            value="自动" if self.review_zoom_auto else f"{_format_layout_percent(self.review_zoom * 100.0)}%"
        )
        # Review typography is deliberately independent from the image zoom.
        # Expose the same persisted font settings directly in the review window
        # so users do not need to return to the detailed-settings dialog.
        self.review_font_family_var = tk.StringVar(
            value=normalize_content_font_setting(parent.settings.review_entry_font_family)
        )
        self.review_font_size_var = tk.StringVar(value=str(_review_editor_font_size(parent.settings)))
        self.review_font_bold_var = tk.BooleanVar(value=bool(parent.settings.review_entry_font_bold))
        self.review_font_italic_var = tk.BooleanVar(value=bool(parent.settings.review_entry_font_italic))
        self.review_simplified_font_family_var = tk.StringVar(
            value=normalize_content_font_setting(
                getattr(parent.settings, "review_simplified_font_family", parent.settings.review_entry_font_family)
            )
        )
        self.review_simplified_font_size_var = tk.StringVar(
            value=str(max(6, int(getattr(parent.settings, "review_simplified_font_size", _review_editor_font_size(parent.settings)))))
        )
        self.review_simplified_font_bold_var = tk.BooleanVar(
            value=bool(getattr(parent.settings, "review_simplified_font_bold", parent.settings.review_entry_font_bold))
        )
        self.review_simplified_font_italic_var = tk.BooleanVar(
            value=bool(getattr(parent.settings, "review_simplified_font_italic", parent.settings.review_entry_font_italic))
        )
        self.review_left_padding_var = tk.StringVar(value=str(max(0, int(parent.settings.review_entry_left_padding))))
        self.review_vertical_padding_var = tk.StringVar(
            value=str(max(0, min(30, int(parent.settings.review_entry_vertical_padding))))
        )
        self.review_line_height_var = tk.StringVar(
            value=_format_review_height_percent(
                parent.image, max(1, int(parent.settings.character_height))
            )
        )
        self.review_row_padding_var = tk.StringVar(
            value=_format_review_height_percent(
                parent.image, max(0, int(parent.settings.row_padding))
            )
        )
        self.review_regular_crop_height_var = tk.StringVar(
            value=_format_review_height_percent(
                parent.image, _effective_review_regular_crop_height(parent.settings)
            )
        )
        self.review_single_cjk_line_height_var = tk.StringVar(
            value=_format_review_height_percent(
                parent.image, _effective_review_single_cjk_line_height(parent.settings)
            )
        )
        self.review_line_height_px_var = tk.StringVar(
            value=str(max(1, int(parent.settings.character_height)))
        )
        self.review_row_padding_px_var = tk.StringVar(
            value=str(max(0, int(parent.settings.row_padding)))
        )
        self.review_regular_crop_height_px_var = tk.StringVar(
            value=str(_effective_review_regular_crop_height(parent.settings))
        )
        self.review_single_cjk_line_height_px_var = tk.StringVar(
            value=str(_effective_review_single_cjk_line_height(parent.settings))
        )
        self.review_extended_crop_multiplier_var = tk.StringVar(
            value=f"{float(getattr(parent.settings, 'review_extended_crop_height_multiplier', 2.5)):g}"
        )
        self.review_main_ocr_choices_var = tk.BooleanVar(
            value=bool(getattr(parent.settings, "review_main_show_ocr_choices", False))
        )
        self.review_main_ocr_background_var = tk.BooleanVar(
            value=bool(getattr(parent.settings, "review_main_show_ocr_background", False))
        )
        compare_key = str(getattr(parent.settings, "review_ocr_compare_source", "fusion") or "fusion").lower()
        if compare_key not in self.OCR_COMPARE_KEY_TO_LABEL:
            compare_key = "fusion"
        self.review_ocr_compare_var = tk.StringVar(value=self.OCR_COMPARE_KEY_TO_LABEL[compare_key])
        self.review_show_simplified_var = tk.BooleanVar(
            value=bool(getattr(parent.settings, "review_show_simplified", False))
        )
        locator_key = str(getattr(parent.settings, "wordslist_locator_mode", "auto") or "auto").lower()
        if locator_key not in self.WORDSLIST_LOCATOR_KEY_TO_LABEL:
            locator_key = "auto"
        self.wordslist_locator_var = tk.StringVar(value=self.WORDSLIST_LOCATOR_KEY_TO_LABEL[locator_key])
        self.network_lookup_enabled_var = tk.BooleanVar(
            value=bool(getattr(parent.settings, "review_network_lookup_enabled", True))
        )
        self.network_lookup_status_var = tk.StringVar(value="网络词汇核验：等待选择词条")
        self.cc_cedict_lookup_var = tk.StringVar(value="CC-CEDICT(?)")
        self.cc_simplified_compare_var = tk.StringVar(value="CC简(?)")
        self.moedict_lookup_var = tk.StringVar(value="萌(?)")
        self.wiktionary_lookup_var = tk.StringVar(value="Wiki(?)")
        self._network_source_urls: dict[str, str] = {}
        self._network_lookup_job: str | None = None
        self._network_lookup_serial = 0
        self._network_lookup_cache: dict[str, LexicalLookupResult] = {}
        self._network_lookup_word = ""
        self._network_result_queue: queue.Queue[tuple[int, str, LexicalLookupResult | None]] = queue.Queue()
        self._network_pending_serials: set[int] = set()
        self._network_poll_job: str | None = None
        self._review_font_apply_job: str | None = None
        self._review_simplified_font_apply_job: str | None = None
        self._review_padding_apply_job: str | None = None
        self._review_vertical_padding_apply_job: str | None = None
        self._review_line_height_apply_job: str | None = None
        self._review_row_padding_apply_job: str | None = None
        self._review_regular_crop_height_apply_job: str | None = None
        self._review_single_cjk_height_apply_job: str | None = None
        self._review_extended_crop_multiplier_job: str | None = None
        self._syncing_review_height_vars = False
        self._review_height_edit_source: dict[str, str] = {}
        self.word_highlight_index: int | None = None
        self.word_selected_local_index: int | None = None
        self.word_list_default_bg = "white"
        self.word_list_default_fg = "#111827"
        # The reference words may exceed 100k rows.  Keep the full data/index in
        # Python, but only render a small contiguous window in the Tk Listbox.
        self.word_window_radius = 250
        self.word_window_start = 0
        self.word_window_indices: list[int] = []
        self.word_keys: list[str] = []
        self.word_exact_index: dict[str, int] = {}
        self.word_exact_indices: dict[str, list[int]] = {}
        self._previous_reference_base_cache: tuple[int, int | None] | None = None
        self.sorted_word_keys: list[str] = []
        self.sorted_word_indices: list[int] = []
        self.word_sort_key_cache: dict[int, tuple[str, str]] = {}
        self.vars: list[tk.StringVar] = []
        # Stable Entry identities corresponding to ``vars``. Main-canvas line
        # insertion can reorder parent.entries while this window remains open.
        self.row_entries: list[WordEntry] = []
        self.editors: list[tk.Entry] = []
        self.editor_frames: list[tk.Frame] = []
        self.simplified_vars: list[tk.StringVar] = []
        self.simplified_editors: list[tk.Entry] = []
        self.simplified_search_buttons: list[tk.Button] = []
        self.simplified_actual_values: list[str | None] = []
        self.simplified_manual_flags: list[bool] = []
        # True only for rows that had no persisted simplified record when the page was opened.
        # Existing sidecar text is authoritative and must never be silently regenerated.
        self.simplified_auto_refresh_flags: list[bool] = []
        self._simplified_page_cache: dict[str, dict[str, dict]] = {}
        self._simplified_dirty_pages: set[str] = set()
        self._rendered_page_stem: str = ""
        self.editor_crop_widths: list[int] = []
        self.ocr_result_buttons: list[tuple[tk.Button, str]] = []
        self.thumbnails: list[ImageTk.PhotoImage] = []
        self.replace_digits = tk.BooleanVar(value=False)
        self.order_scope_var = tk.StringVar(value="current")
        self.review_mode_var = tk.StringVar(value="single")
        # Reuse the main-window 【指定】 text directly so proofreading and
        # every other batch action see the exact same page-range string.
        self.focused_page_range_var = parent.page_range_spec_var
        self.focused_include_mismatch_var = tk.BooleanVar(
            value=bool(getattr(parent.settings, "focused_review_include_ocr_mismatch", True))
        )
        self.focused_include_characters_var = tk.BooleanVar(
            value=bool(getattr(parent.settings, "focused_review_include_characters", False))
        )
        self.focused_exclude_single_var = tk.BooleanVar(
            value=bool(getattr(parent.settings, "focused_review_exclude_single_character", False))
        )
        self.focused_exclude_reference_var = tk.BooleanVar(
            value=bool(getattr(parent.settings, "focused_review_exclude_reference_words", False))
        )
        self.focused_characters_var = tk.StringVar(
            value=str(
                getattr(parent.settings, "focused_review_characters", "")
                or "椿,彝,壯,鳥,傅,顔,彝,榖,歴,内,脱,書,鳴"
            )
        )
        self.focused_batch_size_var = tk.StringVar(
            value=str(max(1, int(getattr(parent.settings, "focused_review_batch_size", 20) or 20)))
        )
        self.filtered_targets: list[dict] = []
        self.filtered_batch_index = 0
        self._filter_rows_active = False
        self.filter_batch_var = tk.StringVar(value="")
        self._filter_scan_serial = 0
        self._filter_render_serial = 0
        self._filter_scan_complete = True
        # Filter-mode render cache stores PIL crops only. Tk/ImageTk objects are
        # still created on the UI thread when a batch becomes visible.
        self._filter_batch_render_cache: dict[tuple[int, tuple], tuple] = {}
        self._filter_prefetch_key: tuple[int, tuple] | None = None
        self._filter_current_batch_targets: list[dict] = []
        self._filter_pending_changes: dict[int, dict[tuple[int, int], dict]] = {}
        self._filter_save_job: str | None = None
        self._filter_save_running = False
        self._filter_close_after_save = False
        self.focused_panel_expanded = tk.BooleanVar(value=False)
        self.digit_map_expanded = tk.BooleanVar(value=False)
        self.accent_panel_expanded = tk.BooleanVar(value=False)
        # Open only the reference word list by default; every other right-side
        # helper stays available behind its collapsible title on demand.
        self.review_right_section_expanded = {
            key: tk.BooleanVar(value=(key == "reference"))
            for key in ("display", "digit", "accent", "ocr", "network", "reference")
        }
        self._review_right_sections: dict[str, dict[str, object]] = {}
        self.autosave_label_var = tk.StringVar(value="")
        saved_digit_map = list(getattr(parent.settings, "review_digit_map", []) or [])
        defaults = list("áéíóúãçñõü")
        saved_digit_map = (saved_digit_map + defaults)[:10]
        self.digit_map_vars = [tk.StringVar(value=str(saved_digit_map[i])) for i in range(10)]
        self.active_candidate: dict | None = None
        # Adjacent-page proofreading prefetch. PIL/image/file parsing runs in a
        # daemon worker; Tk/ImageTk objects are still created only on the UI
        # thread.  This keeps previous/next navigation responsive without
        # changing saved page data or OCR semantics.
        self._prefetch_lock = threading.Lock()
        self._prefetched_pages: dict[int, dict] = {}
        self._prefetch_inflight: set[int] = set()
        self._prefetch_closed = False
        self._review_render_worker_key = f"review-render-{id(self)}"
        self._review_render_focus_index = 0
        self._review_auto_zoom_job: str | None = None
        self._review_auto_zoom_width = 0
        self.review_section_title_font = font.nametofont("TkDefaultFont").copy()
        self.review_section_title_font.configure(weight="bold")
        self._configure_review_styles()
        self._build()
        self.after_idle(self._initialize_review_layout_and_rows)
        self.protocol("WM_DELETE_WINDOW", self._close_review)
        self._update_title()
        # Traces are installed after the widgets are built so construction does
        # not trigger an unnecessary project-settings write.
        for _var in (self.review_font_family_var, self.review_font_size_var,
                     self.review_font_bold_var, self.review_font_italic_var):
            _var.trace_add("write", lambda *_args: self._schedule_review_font_apply())
        for _var in (self.review_simplified_font_family_var, self.review_simplified_font_size_var,
                     self.review_simplified_font_bold_var, self.review_simplified_font_italic_var):
            _var.trace_add("write", lambda *_args: self._schedule_review_simplified_font_apply())
        self.review_left_padding_var.trace_add("write", lambda *_args: self._schedule_review_padding_apply())
        self.review_vertical_padding_var.trace_add("write", lambda *_args: self._schedule_review_vertical_padding_apply())
        self.review_line_height_var.trace_add(
            "write", lambda *_args: self._schedule_review_line_height_apply("percent")
        )
        self.review_line_height_px_var.trace_add(
            "write", lambda *_args: self._schedule_review_line_height_apply("pixel")
        )
        self.review_row_padding_var.trace_add(
            "write", lambda *_args: self._schedule_review_row_padding_apply("percent")
        )
        self.review_row_padding_px_var.trace_add(
            "write", lambda *_args: self._schedule_review_row_padding_apply("pixel")
        )
        self.review_regular_crop_height_var.trace_add(
            "write", lambda *_args: self._schedule_review_regular_crop_height_apply("percent")
        )
        self.review_regular_crop_height_px_var.trace_add(
            "write", lambda *_args: self._schedule_review_regular_crop_height_apply("pixel")
        )
        self.review_single_cjk_line_height_var.trace_add(
            "write", lambda *_args: self._schedule_review_single_cjk_height_apply("percent")
        )
        self.review_single_cjk_line_height_px_var.trace_add(
            "write", lambda *_args: self._schedule_review_single_cjk_height_apply("pixel")
        )
        self.review_extended_crop_multiplier_var.trace_add(
            "write", lambda *_args: self._schedule_review_extended_crop_multiplier_apply()
        )
        for _var in self.digit_map_vars:
            _var.trace_add("write", lambda *_args: self._save_digit_map())

    def _configure_review_styles(self) -> None:
        """Configure dense, opt-in styles for the proofreading workspace only."""
        style = ttk.Style(self)
        base = appearance_palette(self.parent.appearance_mode)
        if self.parent.appearance_mode == "dark":
            colors = {
                "surface": base["surface"],
                "toolbar": base["surface_alt"],
                "panel": base["panel"],
                "border": base["border"],
                "text": base["text"],
                "muted": base["muted"],
                "button": base["button"],
                "button_hover": base["button_hover"],
                "primary": base["success"],
                "primary_hover": base["success_hover"],
                "danger": base["danger"],
                "danger_hover": "#4a2b30",
                "selection": base["selection"],
                "neutral_entry": base["input_bg"],
            }
        else:
            native_background = str(style.lookup("TFrame", "background") or "#f6f7f9")
            colors = {
                "surface": native_background,
                "toolbar": "#f3f4f6",
                "panel": "#f7f8fa",
                "border": "#d8dde5",
                "text": "#30343b",
                "muted": "#68707b",
                "button": "#eceff3",
                "button_hover": "#e1e5ea",
                "primary": "#5e9f69",
                "primary_hover": "#4f8e5c",
                "danger": "#9b3a3a",
                "danger_hover": "#f4d9d9",
                "selection": "#dce8f7",
                "neutral_entry": "#f4f4f4",
            }
        self._review_ui_colors = colors

        style.configure("PCR.Surface.TFrame", background=colors["surface"])
        style.configure("PCR.Toolbar.TFrame", background=colors["toolbar"])
        style.configure("PCR.Panel.TFrame", background=colors["panel"])
        style.configure(
            "PCR.SectionTitle.TLabel",
            background=colors["surface"],
            foreground=colors["text"],
            font=self.review_section_title_font,
            padding=(0, 2, 0, 1),
        )
        style.configure(
            "PCR.Toolbar.TLabel",
            background=colors["toolbar"],
            foreground=colors["text"],
        )
        style.configure(
            "PCR.Body.TLabel",
            background=colors["surface"],
            foreground=colors["text"],
        )
        style.configure(
            "PCR.Black.TLabel",
            background=colors["surface"],
            foreground="#000000" if self.parent.appearance_mode != "dark" else colors["text"],
        )
        style.configure(
            "PCR.Body.TCheckbutton",
            background=colors["surface"],
            foreground=colors["text"],
        )
        style.configure(
            "PCR.Muted.TLabel",
            background=colors["surface"],
            foreground=colors["muted"],
        )
        style.configure(
            "PCR.Header.TLabel",
            background=colors["surface"],
            foreground=colors["text"],
            font=self.review_section_title_font,
        )
        style.configure("PCR.Compact.TButton", padding=(7, 3))
        style.configure("PCR.Tool.TButton", padding=(4, 2))
        style.configure("PCR.Compact.TEntry", padding=(4, 2))
        style.configure("PCR.Compact.TSpinbox", padding=(3, 2))
        style.configure("PCR.Compact.TCombobox", padding=(3, 2))
        style.configure("PCR.Crop.TLabel", background=colors["surface"])

    def _review_flat_button(
        self, parent: tk.Misc, text: str, command, *, role: str = "neutral",
        width: int | None = None, anchor: str = "center",
    ) -> tk.Button:
        """Create one flat review-workspace button without changing global Tk styling."""
        # Classic Tk widgets are authored in the light palette even when the
        # window opens while dark mode is active; the global reversible mapper
        # darkens them after creation.
        palette = {
            "neutral": ("#eceff3", "#e1e5ea", "#30343b"),
            "primary": ("#5e9f69", "#4f8e5c", "#ffffff"),
            "danger": ("#f3eeee", "#f4d9d9", "#9b3a3a"),
        }
        background, active_background, foreground = palette.get(role, palette["neutral"])
        options = {
            "text": text,
            "command": command,
            "bg": background,
            "fg": foreground,
            "activebackground": active_background,
            "activeforeground": foreground,
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "padx": 8,
            "pady": 4,
            "cursor": "hand2",
            "anchor": anchor,
        }
        if width is not None:
            options["width"] = width
        return tk.Button(parent, **options)

    def _review_collapsible_section(
        self, parent: tk.Misc, key: str, title: str, *, padding: int = 6,
        fill: str = "x", expand: bool = False, pady=(0, 6),
    ) -> ttk.Frame:
        """Create one flat right-pane section while honoring its initial state."""
        frame = ttk.Frame(parent, padding=(padding, 2), style="PCR.Surface.TFrame")
        frame.pack(fill=fill, expand=expand, pady=pady)
        state = self.review_right_section_expanded.get(key)
        expanded = True if state is None else bool(state.get())
        title_var = tk.StringVar(value=("▾ " if expanded else "▸ ") + title)
        toggle = ttk.Label(
            frame, textvariable=title_var, style="PCR.Header.TLabel", cursor="hand2",
        )
        toggle.pack(fill="x")
        toggle.bind(
            "<Button-1>", lambda _event, section_key=key: self._toggle_review_right_section(section_key)
        )
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(3, 5))
        body = ttk.Frame(frame, style="PCR.Surface.TFrame")
        if expanded:
            body.pack(fill="both", expand=True)
        self._review_right_sections[key] = {
            "frame": frame,
            "body": body,
            "title": title,
            "title_var": title_var,
            "expand_when_open": bool(expand),
        }
        if not expanded:
            frame.pack_configure(expand=False)
        return body

    def _toggle_review_right_section(self, key: str) -> None:
        section = self._review_right_sections.get(key)
        state = self.review_right_section_expanded.get(key)
        if section is None or state is None:
            return
        expanded = not bool(state.get())
        state.set(expanded)
        title = str(section["title"])
        title_var = section["title_var"]
        body = section["body"]
        frame = section["frame"]
        title_var.set(("▾ " if expanded else "▸ ") + title)
        if expanded:
            body.pack(fill="both", expand=True)
            frame.pack_configure(expand=bool(section["expand_when_open"]))
        else:
            body.pack_forget()
            frame.pack_configure(expand=False)

    def _toggle_focused_panel(self) -> None:
        expanded = not bool(self.focused_panel_expanded.get())
        self.focused_panel_expanded.set(expanded)
        self.focused_panel_title.set(("▾ " if expanded else "▸ ") + "重点筛选校对")
        if expanded:
            self.focused_panel_body.pack(fill="x", pady=(4, 0))
        else:
            self.focused_panel_body.pack_forget()

    def _fit_review_left_pane_to_toolbar(self) -> None:
        """Size the left pane just wide enough to show the complete top toolbar."""
        panes = getattr(self, "review_panes", None)
        row = getattr(self, "review_control_row", None)
        if panes is None or row is None:
            return
        try:
            self.update_idletasks()
            required = int(row.winfo_reqwidth()) + 14
            available = max(1, int(panes.winfo_width()) - 1)
            panes.sashpos(0, min(required, available))
        except (tk.TclError, ValueError):
            return

    def _initialize_review_layout_and_rows(self) -> None:
        """Finalize pane geometry before the first proofreading crop render."""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self._fit_review_left_pane_to_toolbar()
        try:
            self.update_idletasks()
        except tk.TclError:
            return
        if self._review_auto_zoom_job is not None:
            try:
                self.after_cancel(self._review_auto_zoom_job)
            except tk.TclError:
                pass
            self._review_auto_zoom_job = None
        self._review_auto_zoom_width = self._review_image_area_width()
        self._request_render_rows(focus_index=0)

    def _review_image_area_width(self, canvas_width: int | None = None) -> int:
        """Leave room for the main-style sequence badge beside each crop."""
        try:
            if canvas_width is None:
                canvas_width = int(self.canvas.winfo_width())
            from .ui.review_crop_sequence import review_sequence_gutter
            badge_width = review_sequence_gutter(self)
        except (AttributeError, tk.TclError, TypeError, ValueError):
            return 1
        # 6px outer padding on each side, plus the measured badge and gap.
        return max(1, int(canvas_width) - 12 - badge_width)

    def _review_canvas_configured(self, event: tk.Event) -> None:
        try:
            self.canvas.itemconfigure(self.rows_window, width=event.width)
        except tk.TclError:
            return
        if not self.review_zoom_auto:
            return
        usable_width = self._review_image_area_width(event.width)
        # Ignore geometry noise that cannot change the rounded crop width.
        if abs(usable_width - int(self._review_auto_zoom_width or 0)) <= 1:
            return
        self._review_auto_zoom_width = usable_width
        if self._review_auto_zoom_job is not None:
            try:
                self.after_cancel(self._review_auto_zoom_job)
            except tk.TclError:
                pass
        self._review_auto_zoom_job = self.after(120, self._apply_auto_review_zoom_resize)

    def _apply_auto_review_zoom_resize(self) -> None:
        self._review_auto_zoom_job = None
        if not self.review_zoom_auto:
            return
        if getattr(self, "_filter_rows_active", False):
            self._request_filter_batch_render()
        else:
            self._request_render_rows(focus_index=self.active_index)

    def _stored_review_zoom_percent(self) -> float:
        return 0.0 if self.review_zoom_auto else round(self.review_zoom * 100.0, 2)

    def _build(self) -> None:
        return _review_workspace._build(self, _review_workspace_deps())

    def _change_review_mode(self) -> None:
        return _review_workspace._change_review_mode(self, _review_workspace_deps())

    def _set_filter_navigation(self, active: bool) -> None:
        return _review_workspace._set_filter_navigation(self, _review_workspace_deps(), active)

    def _persist_focused_filter_settings(self) -> None:
        return _focused_filter._persist_focused_filter_settings(self, _focused_filter_deps())

    def _clear_review_workspace(self, message: str = "") -> None:
        return _review_workspace._clear_review_workspace(self, _review_workspace_deps(), message)

    def run_focused_filter(self) -> None:
        return _focused_filter.run_focused_filter(self, _focused_filter_deps())

    def _focused_batch_size(self) -> int:
        return _focused_filter._focused_batch_size(self, _focused_filter_deps())

    def _filter_available_target_count(self) -> int:
        return _focused_filter._filter_available_target_count(self, _focused_filter_deps())

    def _update_filter_batch_indicator(self) -> None:
        return _focused_filter._update_filter_batch_indicator(self, _focused_filter_deps())

    def _filter_batch_snapshot(self, batch_index: int):
        return _focused_filter._filter_batch_snapshot(self, _focused_filter_deps(), batch_index)

    @staticmethod
    def _prepare_filter_batch_payload(
        targets: list[dict], pages: list[Path], settings: AppSettings,
        viewer_width: int, available_width: int, review_zoom: float,
        review_zoom_auto: bool,
    ) -> tuple[list[Image.Image], float, list[tuple[int, int]]]:
        return _focused_filter._prepare_filter_batch_payload(_focused_filter_deps(), targets, pages, settings, viewer_width, available_width, review_zoom, review_zoom_auto)

    def _cache_filter_batch_payload(self, cache_key: tuple[int, tuple], payload: tuple) -> None:
        return _focused_filter._cache_filter_batch_payload(self, _focused_filter_deps(), cache_key, payload)

    def _apply_filter_batch_payload(
        self, batch_index: int, cache_key: tuple[int, tuple], payload: tuple,
    ) -> bool:
        return _focused_filter._apply_filter_batch_payload(self, _focused_filter_deps(), batch_index, cache_key, payload)

    def _schedule_filter_next_batch_preload(self) -> None:
        return _focused_filter._schedule_filter_next_batch_preload(self, _focused_filter_deps())

    def change_filter_batch(self, delta: int) -> None:
        return _focused_filter.change_filter_batch(self, _focused_filter_deps(), delta)

    def _request_filter_batch_render(self) -> None:
        return _focused_filter._request_filter_batch_render(self, _focused_filter_deps())

    def _render_filter_batch(
        self, targets: list[dict], crops: list[Image.Image],
    ) -> None:
        return _focused_filter._render_filter_batch(self, _focused_filter_deps(), targets, crops)

    def _set_filter_active(self, index: int) -> None:
        return _focused_filter._set_filter_active(self, _focused_filter_deps(), index)

    def _focus_filter_index(self, index: int) -> str:
        return _focused_filter._focus_filter_index(self, _focused_filter_deps(), index)

    def _filter_ocr_word(self, target: dict) -> str:
        return _focused_filter._filter_ocr_word(self, _focused_filter_deps(), target)

    def _fill_filter_ocr_result(self, index: int) -> None:
        return _focused_filter._fill_filter_ocr_result(self, _focused_filter_deps(), index)

    def _commit_filter_editor_value(self, index: int) -> None:
        return _focused_filter._commit_filter_editor_value(self, _focused_filter_deps(), index)

    def _on_filter_key(self, event: tk.Event, index: int) -> None:
        return _focused_filter._on_filter_key(self, _focused_filter_deps(), event, index)

    def _queue_focused_change(self, target: dict, value: str) -> None:
        return _focused_filter._queue_focused_change(self, _focused_filter_deps(), target, value)

    def _flush_focused_changes_now(self) -> None:
        return _focused_filter._flush_focused_changes_now(self, _focused_filter_deps())

    def _flush_focused_changes(self) -> None:
        return _focused_filter._flush_focused_changes(self, _focused_filter_deps())

    def copy_char(self, char: str) -> str:
        return _review_workspace.copy_char(self, _review_workspace_deps(), char)

    def _review_membership_colors(
        self, in_wordslist: bool,
    ) -> tuple[str, str, str, str]:
        return _review_workspace._review_membership_colors(self, _review_workspace_deps(), in_wordslist)

    def _configure_word_list_appearance(self) -> None:
        return _review_workspace._configure_word_list_appearance(self, _review_workspace_deps())

    def _clear_word_list_rows(self) -> None:
        return _review_workspace._clear_word_list_rows(self, _review_workspace_deps())

    def _render_word_list_rows(self, words: list[str]) -> None:
        return _review_workspace._render_word_list_rows(self, _review_workspace_deps(), words)

    def _set_word_list_highlight(self, local: int | None) -> None:
        return _review_workspace._set_word_list_highlight(self, _review_workspace_deps(), local)

    def _word_list_local_index_from_event(self, event: tk.Event) -> int | None:
        return _review_workspace._word_list_local_index_from_event(self, _review_workspace_deps(), event)

    def _toggle_review_panel(self, panel: str) -> None:
        return _review_workspace._toggle_review_panel(self, _review_workspace_deps(), panel)

    def _sync_autosave_label(self) -> None:
        return _review_workspace._sync_autosave_label(self, _review_workspace_deps())

    def _toggle_shared_autosave(self) -> None:
        return _review_workspace._toggle_shared_autosave(self, _review_workspace_deps())

    def open_sort_rules(self) -> None:
        return _review_workspace.open_sort_rules(self, _review_workspace_deps())

    def run_order_check(self) -> None:
        return _review_workspace.run_order_check(self, _review_workspace_deps())

    def _update_title(self) -> None:
        return _review_workspace._update_title(self, _review_workspace_deps())

    def _finish_close_review(self) -> None:
        return _review_page._finish_close_review(self, _review_page_deps())

    def _close_review(self) -> None:
        from .ui.review_close_actions import close_review
        close_review(self, showerror=messagebox.showerror)

    def autosave_commit(self) -> bool:
        return _review_page.autosave_commit(self, _review_page_deps())

    def _effective_wordslist_locator_mode(self) -> str:
        return _review_reference._effective_wordslist_locator_mode(self, _review_reference_deps())

    def _change_wordslist_locator_mode(self, _event: tk.Event | None = None) -> None:
        return _review_reference._change_wordslist_locator_mode(self, _review_reference_deps(), _event)

    def _refresh_cc_cedict_button_idle(self) -> None:
        return _review_lookup._refresh_cc_cedict_button_idle(self, _review_lookup_deps())

    def _set_lookup_source_states(self, *, pending: bool = False, empty: bool = False) -> None:
        return _review_lookup._set_lookup_source_states(self, _review_lookup_deps(), pending=pending, empty=empty)

    def manage_cc_cedict(self) -> None:
        return _review_lookup.manage_cc_cedict(self, _review_lookup_deps())

    def _cc_simplified_comparison_details(self, index: int | None = None) -> dict[str, object]:
        return _review_lookup._cc_simplified_comparison_details(self, _review_lookup_deps(), index)

    def _refresh_cc_simplified_comparison(self, index: int | None = None) -> None:
        return _review_lookup._refresh_cc_simplified_comparison(self, _review_lookup_deps(), index)

    def show_cc_simplified_comparison(self) -> None:
        return _review_lookup.show_cc_simplified_comparison(self, _review_lookup_deps())

    def open_lookup_source(self, name: str) -> None:
        return _review_lookup.open_lookup_source(self, _review_lookup_deps(), name)

    def _toggle_network_lookup(self) -> None:
        return _review_lookup._toggle_network_lookup(self, _review_lookup_deps())

    def _active_review_word(self) -> str:
        return _review_lookup._active_review_word(self, _review_lookup_deps())

    def _schedule_network_lookup(self, word: str | None = None, *, force: bool = False) -> None:
        return _review_lookup._schedule_network_lookup(self, _review_lookup_deps(), word, force=force)

    def _start_network_lookup(self, serial: int, word: str) -> None:
        return _review_lookup._start_network_lookup(self, _review_lookup_deps(), serial, word)

    def _poll_network_lookup_results(self) -> None:
        return _review_lookup._poll_network_lookup_results(self, _review_lookup_deps())

    def _apply_network_lookup_result(
        self, serial: int, word: str, result: LexicalLookupResult | None,
    ) -> None:
        return _review_lookup._apply_network_lookup_result(self, _review_lookup_deps(), serial, word, result)

    def open_network_web_search(self) -> None:
        return _review_lookup.open_network_web_search(self, _review_lookup_deps())

    @staticmethod
    def _wordslist_lookup_key(word: str) -> str:
        return _review_reference._wordslist_lookup_key(_review_reference_deps(), word)

    def refresh_wordslist_display(self) -> None:
        return _review_reference.refresh_wordslist_display(self, _review_reference_deps())

    def _show_wordslist_window(self, target: int) -> None:
        return _review_reference._show_wordslist_window(self, _review_reference_deps(), target)

    def shift_wordslist_window(self, direction: int) -> None:
        return _review_reference.shift_wordslist_window(self, _review_reference_deps(), direction)

    def choose_wordslist_file(self) -> None:
        return _review_reference.choose_wordslist_file(self, _review_reference_deps())

    # Thin class-level UI delegation; the transaction service owns decisions.
    from .ui.review_transaction_actions import undo_saved_review, redo_saved_review

    def _commit_edits(self) -> None:
        from .proofreading.main_editor_sync import commit_proofread_entries
        commit_proofread_entries(self)

    def _open_proofreading_visual_verification(self) -> None:
        """User-initiated scan preview and independent judgment, never OCR."""
        from .proofreading.verify_ui import open_visual_verification
        open_visual_verification(self)

    def _review_evidence_before_save(self) -> list[WordEntry] | None:
        return _review_page._review_evidence_before_save(self, _review_page_deps())

    def _review_evidence_after_save(self, previous: list[WordEntry] | None) -> None:
        return _review_page._review_evidence_after_save(self, _review_page_deps(), previous)

    def _bound_row_entries(self) -> list[WordEntry]:
        return _review_simplified._bound_row_entries(self, _review_simplified_deps())

    def _simplified_page_records(self, page_stem: str | None = None) -> dict[str, dict]:
        return _review_simplified._simplified_page_records(self, _review_simplified_deps(), page_stem)

    @staticmethod
    def _simplified_display_from_value(original: str, value: str | None, manual: bool) -> str:
        return _review_simplified._simplified_display_from_value(_review_simplified_deps(), original, value, manual)

    def _auto_simplified_value(self, original: str, fallback: str | None = None) -> str | None:
        return _review_simplified._auto_simplified_value(self, _review_simplified_deps(), original, fallback=fallback)

    def _capture_simplified_edits(self, page_stem: str | None = None) -> None:
        return _review_simplified._capture_simplified_edits(self, _review_simplified_deps(), page_stem)

    def _persist_simplified_page(self, page_stem: str | None = None) -> None:
        return _review_simplified._persist_simplified_page(self, _review_simplified_deps(), page_stem)

    def _simplified_query_for_index(self, index: int) -> str:
        return _review_simplified._simplified_query_for_index(self, _review_simplified_deps(), index)

    def lookup_simplified_online(self, index: int) -> None:
        return _review_simplified.lookup_simplified_online(self, _review_simplified_deps(), index)

    def _focus_simplified_editor(self, index: int) -> None:
        return _review_simplified._focus_simplified_editor(self, _review_simplified_deps(), index)

    def _claim_simplified_clipboard_edit(self, index: int) -> str | None:
        return _review_simplified._claim_simplified_clipboard_edit(self, _review_simplified_deps(), index)

    def on_simplified_key(self, _event: tk.Event, index: int) -> None:
        return _review_simplified.on_simplified_key(self, _review_simplified_deps(), _event, index)

    def _schedule_review_font_apply(self) -> None:
        return _review_appearance._schedule_review_font_apply(self, _review_appearance_deps())

    def _apply_review_font_settings(self) -> None:
        return _review_appearance._apply_review_font_settings(self, _review_appearance_deps())

    def _schedule_review_simplified_font_apply(self) -> None:
        return _review_appearance._schedule_review_simplified_font_apply(self, _review_appearance_deps())

    def _apply_review_simplified_font_settings(self) -> None:
        return _review_appearance._apply_review_simplified_font_settings(self, _review_appearance_deps())

    def _schedule_review_padding_apply(self) -> None:
        return _review_appearance._schedule_review_padding_apply(self, _review_appearance_deps())

    def _apply_review_padding_setting(self) -> None:
        return _review_appearance._apply_review_padding_setting(self, _review_appearance_deps())

    def _schedule_review_vertical_padding_apply(self) -> None:
        return _review_appearance._schedule_review_vertical_padding_apply(self, _review_appearance_deps())

    def _apply_review_vertical_padding_setting(self) -> None:
        return _review_appearance._apply_review_vertical_padding_setting(self, _review_appearance_deps())

    def _review_height_pixels_from_percent_var(
        self,
        variable: tk.StringVar,
        *,
        minimum: int,
        maximum: int,
    ) -> tuple[int, str]:
        return _review_appearance._review_height_pixels_from_percent_var(self, _review_appearance_deps(), variable, minimum=minimum, maximum=maximum)

    @staticmethod
    def _review_height_pixels_from_pixel_var(
        variable: tk.StringVar,
        *,
        minimum: int,
        maximum: int,
    ) -> tuple[int, str]:
        return _review_appearance._review_height_pixels_from_pixel_var(_review_appearance_deps(), variable, minimum=minimum, maximum=maximum)

    def _sync_review_height_vars(self) -> None:
        return _review_appearance._sync_review_height_vars(self, _review_appearance_deps())

    def _schedule_review_line_height_apply(self, source: str = "percent") -> None:
        return _review_appearance._schedule_review_line_height_apply(self, _review_appearance_deps(), source)

    def _apply_review_line_height_setting(self) -> None:
        return _review_appearance._apply_review_line_height_setting(self, _review_appearance_deps())

    def _schedule_review_row_padding_apply(self, source: str = "percent") -> None:
        return _review_appearance._schedule_review_row_padding_apply(self, _review_appearance_deps(), source)

    def _apply_review_row_padding_setting(self) -> None:
        return _review_appearance._apply_review_row_padding_setting(self, _review_appearance_deps())

    def _schedule_review_regular_crop_height_apply(self, source: str = "percent") -> None:
        return _review_appearance._schedule_review_regular_crop_height_apply(self, _review_appearance_deps(), source)

    def _apply_review_regular_crop_height_setting(self) -> None:
        return _review_appearance._apply_review_regular_crop_height_setting(self, _review_appearance_deps())

    def _schedule_review_single_cjk_height_apply(self, source: str = "percent") -> None:
        return _review_appearance._schedule_review_single_cjk_height_apply(self, _review_appearance_deps(), source)

    def _apply_review_single_cjk_height_setting(self) -> None:
        return _review_appearance._apply_review_single_cjk_height_setting(self, _review_appearance_deps())

    def _schedule_review_extended_crop_multiplier_apply(self) -> None:
        return _review_appearance._schedule_review_extended_crop_multiplier_apply(self, _review_appearance_deps())

    def _apply_review_extended_crop_multiplier_setting(
        self, *, revert_invalid: bool = False,
    ) -> None:
        return _review_appearance._apply_review_extended_crop_multiplier_setting(self, _review_appearance_deps(), revert_invalid=revert_invalid)

    def _apply_review_main_ocr_display_options(self) -> None:
        return _review_appearance._apply_review_main_ocr_display_options(self, _review_appearance_deps())

    def change_review_zoom(self, factor: float) -> None:
        return _review_appearance.change_review_zoom(self, _review_appearance_deps(), factor)

    def apply_review_zoom_text(self, _event=None) -> None:
        return _review_appearance.apply_review_zoom_text(self, _review_appearance_deps(), _event)

    def reset_review_zoom(self) -> None:
        return _review_appearance.reset_review_zoom(self, _review_appearance_deps())

    def _exact_reference_position(self, word: str, near: int | None = None) -> int | None:
        return _review_reference._exact_reference_position(self, _review_reference_deps(), word, near=near)

    def _previous_page_reference_target(self, active_index: int) -> int | None:
        return _review_reference._previous_page_reference_target(self, _review_reference_deps(), active_index)

    def _current_wordslist_global_target(self) -> int | None:
        return _review_reference._current_wordslist_global_target(self, _review_reference_deps())

    def _sorted_reference_position(self, word: str) -> int | None:
        return _review_reference._sorted_reference_position(self, _review_reference_deps(), word)

    def _infer_sorted_reference_target(self, active_index: int, current_word: str) -> int:
        return _review_reference._infer_sorted_reference_target(self, _review_reference_deps(), active_index, current_word)

    def _infer_reference_target(self, active_index: int, current_word: str) -> int:
        return _review_reference._infer_reference_target(self, _review_reference_deps(), active_index, current_word)

    def locate_reference_word(self, word: str, active_index: int | None = None) -> None:
        return _review_reference.locate_reference_word(self, _review_reference_deps(), word, active_index=active_index)

    def scroll_rows(self, event: tk.Event) -> str:
        self.canvas.yview_scroll((-1 if event.delta > 0 else 1) * 3, "units")
        return "break"

    def scroll_rows_linux(self, direction: int) -> str:
        self.canvas.yview_scroll(direction * 3, "units")
        return "break"

    def _request_render_rows(
        self, *, focus_index: int | None = None, reset_scroll: bool = False,
    ) -> None:
        """Prepare proofreading crops off-thread; materialize Tk widgets only on Tk."""
        return _review_workspace._request_render_rows(self, _review_workspace_deps(), focus_index=focus_index, reset_scroll=reset_scroll)

    def render_rows(self, preloaded_crops: list[Image.Image] | None = None) -> None:
        return _review_workspace.render_rows(self, _review_workspace_deps(), preloaded_crops=preloaded_crops)

    def _candidate_for_entry(self, entry: WordEntry) -> dict | None:
        return self.parent._candidate_for_entry(entry)

    def _refresh_simplified_for_index(self, index: int) -> None:
        return _review_simplified._refresh_simplified_for_index(self, _review_simplified_deps(), index)

    def _refresh_all_simplified(self) -> None:
        return _review_simplified._refresh_all_simplified(self, _review_simplified_deps())

    def regenerate_simplified_current_page(self) -> None:
        return _review_simplified.regenerate_simplified_current_page(self, _review_simplified_deps())

    def _apply_simplified_visibility(self) -> None:
        return _review_simplified._apply_simplified_visibility(self, _review_simplified_deps())

    def _toggle_review_simplified(self) -> None:
        return _review_simplified._toggle_review_simplified(self, _review_simplified_deps())

    def _change_review_ocr_compare_source(self, _event: tk.Event | None = None) -> None:
        return _review_ocr._change_review_ocr_compare_source(self, _review_ocr_deps(), _event)

    def _ocr_compare_word(self, candidate: dict | None) -> str:
        return _review_ocr._ocr_compare_word(self, _review_ocr_deps(), candidate)

    def _refresh_editor_ocr_compare(self, index: int | None = None) -> None:
        return _review_ocr._refresh_editor_ocr_compare(self, _review_ocr_deps(), index)

    def _show_ocr_options(self, candidate: dict | None) -> None:
        return _review_ocr._show_ocr_options(self, _review_ocr_deps(), candidate)

    def _refresh_ocr_similarity_colors(self) -> None:
        return _review_ocr._refresh_ocr_similarity_colors(self, _review_ocr_deps())

    def use_ocr_word(self, word: str) -> None:
        return _review_ocr.use_ocr_word(self, _review_ocr_deps(), word)

    def _update_active_crop_preview(self, index: int) -> None:
        return _review_crop._update_active_crop_preview(self, _review_crop_deps(), index)

    def _schedule_review_crop_height_update(self, index: int) -> None:
        return _review_crop._schedule_review_crop_height_update(self, _review_crop_deps(), index)

    def _refresh_review_row_crop(self, index: int) -> None:
        return _review_crop._refresh_review_row_crop(self, _review_crop_deps(), index)

    def _ordinary_review_photo(self, index: int) -> ImageTk.PhotoImage:
        return _review_crop._ordinary_review_photo(self, _review_crop_deps(), index)

    def set_active(self, index: int) -> None:
        return _review_entry.set_active(self, _review_entry_deps(), index)

    def _scroll_editor_into_view(self, index: int) -> None:
        return _review_entry._scroll_editor_into_view(self, _review_entry_deps(), index)

    def focus_index(self, index: int) -> str:
        return _review_entry.focus_index(self, _review_entry_deps(), index)

    def on_key(self, event: tk.Event, index: int) -> None:
        return _review_entry.on_key(self, _review_entry_deps(), event, index)

    def _set_editor_membership_color(self, index: int, in_wordslist: bool) -> None:
        return _review_entry._set_editor_membership_color(self, _review_entry_deps(), index, in_wordslist)

    def delete_review_entry(self, index: int) -> str:
        return _review_entry.delete_review_entry(self, _review_entry_deps(), index)

    def _save_digit_map(self) -> None:
        return _review_entry._save_digit_map(self, _review_entry_deps())

    def insert_char(self, char: str) -> None:
        return _review_entry.insert_char(self, _review_entry_deps(), char)

    def _selected_wordslist_global_index(self) -> int | None:
        return _review_entry._selected_wordslist_global_index(self, _review_entry_deps())

    def use_selected_word(self, event: tk.Event | None = None) -> None:
        return _review_entry.use_selected_word(self, _review_entry_deps(), event)

    def fill_words(self) -> None:
        return _review_entry.fill_words(self, _review_entry_deps())

    def check_order(self, all_pages: bool) -> None:
        self.save()
        self.parent.check_headword_order(all_pages)

    def save(self, *, redraw_main: bool = True) -> bool:
        return _review_page.save(self, _review_page_deps(), redraw_main=redraw_main)

    def _reset_rows_scroll_top(self) -> None:
        return _review_page._reset_rows_scroll_top(self, _review_page_deps())

    @staticmethod
    def _prefetch_path_signature(path: Path) -> tuple[bool, int, int]:
        return _review_page._prefetch_path_signature(_review_page_deps(), path)

    @classmethod
    def _page_prefetch_signature_for(cls, project_root: Path, page: Path) -> tuple:
        return _review_page._page_prefetch_signature_for(cls, _review_page_deps(), project_root, page)

    def _page_prefetch_signature(self, page: Path) -> tuple:
        return _review_page._page_prefetch_signature(self, _review_page_deps(), page)

    def _review_prefetch_key(self) -> tuple:
        return _review_page._review_prefetch_key(self, _review_page_deps())

    def _take_prefetched_page(self, index: int) -> dict | None:
        return _review_page._take_prefetched_page(self, _review_page_deps(), index)

    def _schedule_adjacent_preload(self) -> None:
        return _review_page._schedule_adjacent_preload(self, _review_page_deps())

    def change_page(self, delta: int) -> None:
        return _review_page.change_page(self, _review_page_deps(), delta)



def _preprocess_ui_deps() -> _preprocess_ui.PreprocessUiDeps:
    """Snapshot original app module binding and monkeypatch state."""
    return _preprocess_ui.PreprocessUiDeps(
        Path=Path,
        replace=replace,
        csv=csv,
        json=json,
        re=re,
        tk=tk,
        font=font,
        messagebox=messagebox,
        ttk=ttk,
        Image=Image,
        ImageTk=ImageTk,
        pdic_path=pdic_path,
        AppSettings=AppSettings,
        ProjectState=ProjectState,
        fit_window_to_work_area=fit_window_to_work_area,
        normalize_page_rgb=normalize_page_rgb,
        themed_display_image=themed_display_image,
        PreprocessAnalysis=PreprocessAnalysis,
        preprocess_analysis_is_current=preprocess_analysis_is_current,
        analyze_preprocess_path=analyze_preprocess_path,
        clear_manual_perspective_quad=clear_manual_perspective_quad,
        geometry_corrected_image=geometry_corrected_image,
        load_preprocess_analysis=load_preprocess_analysis,
        load_manual_perspective_quad=load_manual_perspective_quad,
        overlay_excluded_regions=overlay_excluded_regions,
        output_canvas_info=output_canvas_info,
        preprocess_metadata_output_root=preprocess_metadata_output_root,
        preprocess_preview_output_root=preprocess_preview_output_root,
        preprocess_processed_output_root=preprocess_processed_output_root,
        promote_processed_pages=promote_processed_pages,
        preprocess_result_summary=preprocess_result_summary,
        save_preprocess_analysis=save_preprocess_analysis,
        save_manual_perspective_quad=save_manual_perspective_quad,
        save_processed_page=save_processed_page,
        save_review_preview=save_review_preview,
        export_diagnostic_json=export_diagnostic_json,
        export_summary_csv=export_summary_csv,
        perspective_from_quad=perspective_from_quad,
        _screen_work_area=_screen_work_area,
        ocr_cache_root=ocr_cache_root,
        ppp_read_path_for_image=ppp_read_path_for_image,
        settings_path=settings_path,
        AUTO_FONT_FAMILY=AUTO_FONT_FAMILY,
    )


def _batch_workflow_deps() -> _batch_workflow.BatchWorkflowDeps:
    """Snapshot current application batch threading and GUI dependencies."""
    return _batch_workflow.BatchWorkflowDeps(
        FIRST_COMPLETED=FIRST_COMPLETED,
        ProcessPoolExecutor=ProcessPoolExecutor,
        wait=wait,
        os=os,
        queue=queue,
        threading=threading,
        multiprocessing=multiprocessing,
        traceback=traceback,
        tk=tk,
        messagebox=messagebox,
        resolve_crop_worker_count=resolve_crop_worker_count,
    )


def _project_session_deps() -> _project_session.ProjectSessionDeps:
    """Capture the current original application project-session patch seams."""
    return _project_session.ProjectSessionDeps(
        Path=Path,
        tk=tk,
        ttk=ttk,
        font=font,
        messagebox=messagebox,
        Image=Image,
        ImageTk=ImageTk,
        json=json,
        ProjectController=ProjectController,
        ProjectState=ProjectState,
        STORAGE_DIRNAME=STORAGE_DIRNAME,
        _project_templates=_project_templates,
        has_legacy_project_data=has_legacy_project_data,
        is_managed_project=is_managed_project,
        migrate_legacy_project=migrate_legacy_project,
        load_recent_projects=load_recent_projects,
        recent_project_stub_details=recent_project_stub_details,
        remove_recent_project=remove_recent_project,
        set_recent_project_pinned=set_recent_project_pinned,
        touch_recent_project=touch_recent_project,
        settings_path=settings_path,
        ocr_cache_root=ocr_cache_root,
        pdic_path=pdic_path,
        ppp_read_path_for_image=ppp_read_path_for_image,
        read_page_sections=read_page_sections,
        read_pdic=read_pdic,
        read_ppp=read_ppp,
        normalize_page_rgb=normalize_page_rgb,
        normalize_appearance_mode=normalize_appearance_mode,
        themed_display_image=themed_display_image,
    )


def _review_workspace_deps() -> _review_workspace.ReviewWorkspaceDeps:
    """Capture live legacy module patchpoints for review layout and rows."""
    return _review_workspace.ReviewWorkspaceDeps(
        ttk=ttk,
        tk=tk,
        Image=Image,
        font=font,
        preferred_font_family=preferred_font_family,
        AUTO_FONT_FAMILY=AUTO_FONT_FAMILY,
        _format_layout_percent=_format_layout_percent,
        _review_crop_context=_review_crop_context,
        _review_line_box=_review_line_box,
        sync_review_entry_classification=sync_review_entry_classification,
        normalize_page_rgb=normalize_page_rgb,
        review_auto_fit_zoom=review_auto_fit_zoom,
        _entry_font_spec=_entry_font_spec,
        _review_editor_font_size=_review_editor_font_size,
        resolve_content_font_family=resolve_content_font_family,
        _focused_review_is_single_character=_focused_review_is_single_character,
        simplified_entry_key=simplified_entry_key,
        replace=replace,
        appearance_palette=appearance_palette,
    )


def _review_reference_deps() -> _review_reference.ReviewReferenceDeps:
    """Capture original wordslist search, selection and UI patchpoints."""
    return _review_reference.ReviewReferenceDeps(
        tk=tk, filedialog=filedialog, messagebox=messagebox,
        Path=Path, unicodedata=unicodedata, bisect=bisect,
        resolve_wordslist_path=resolve_wordslist_path,
        read_pdic=read_pdic, pdic_path=pdic_path,
        reference_sort_key=reference_sort_key,
        _is_cjk_review_index=_is_cjk_review_index,
    )


def _review_appearance_deps() -> _review_appearance.ReviewAppearanceDeps:
    """Capture original live style, crop and zoom helpers per callback."""
    return _review_appearance.ReviewAppearanceDeps(
        tk=tk, font=font,
        normalize_content_font_setting=normalize_content_font_setting,
        resolve_content_font_family=resolve_content_font_family,
        _entry_font_spec=_entry_font_spec,
        _review_height_percent_to_pixels=_review_height_percent_to_pixels,
        _format_review_height_percent=_format_review_height_percent,
        _effective_review_regular_crop_height=_effective_review_regular_crop_height,
        _effective_review_single_cjk_line_height=_effective_review_single_cjk_line_height,
        parse_review_crop_multiplier=parse_review_crop_multiplier,
        _format_layout_percent=_format_layout_percent,
    )


def _review_lookup_deps() -> _review_lookup.ReviewLookupDeps:
    """Resolve original collaborators at the moment of callback invocation."""
    return _review_lookup.ReviewLookupDeps(
        tk=tk,
        messagebox=messagebox,
        webbrowser=webbrowser,
        filedialog=filedialog,
        CC_CEDICT_DOWNLOAD_PAGE_URL=CC_CEDICT_DOWNLOAD_PAGE_URL,
        cc_cedict_status=cc_cedict_status,
        contains_cjk=contains_cjk,
        install_cc_cedict_from_file=install_cc_cedict_from_file,
        cc_cedict_simplified_candidates=cc_cedict_simplified_candidates,
        simplify_text=simplify_text,
        lookup_word_free=lookup_word_free,
        threading=threading,
        queue=queue,
        web_search_url=web_search_url,
    )


def _review_simplified_deps() -> _review_simplified.ReviewSimplifiedDeps:
    """Resolve original collaborators at the moment of callback invocation."""
    return _review_simplified.ReviewSimplifiedDeps(
        tk=tk,
        messagebox=messagebox,
        read_simplified_records=read_simplified_records,
        simplified_review_path_for_image=simplified_review_path_for_image,
        write_simplified_records=write_simplified_records,
        simplified_entry_key=simplified_entry_key,
        simplify_text=simplify_text,
    )


def _review_ocr_deps() -> _review_ocr.ReviewOcrDeps:
    """Resolve original collaborators at the moment of callback invocation."""
    return _review_ocr.ReviewOcrDeps(
        tk=tk,
        _candidate_word_for_ocr_source=_candidate_word_for_ocr_source,
        _review_similarity_key=_review_similarity_key,
        _candidate_choice_rows=_candidate_choice_rows,
        _review_similarity_color=_review_similarity_color,
        _review_text_similarity=_review_text_similarity,
    )


def _review_crop_deps() -> _review_crop.ReviewCropDeps:
    """Capture live ReviewWindow collaborators at event dispatch."""
    return _review_crop.ReviewCropDeps(
        tk=tk,
        Image=Image,
        ImageTk=ImageTk,
        replace=replace,
        _review_crop_context=_review_crop_context,
        _review_line_box=_review_line_box,
        parse_review_crop_multiplier=parse_review_crop_multiplier,
        extended_review_crop_box=extended_review_crop_box,
        _focused_review_is_single_character=_focused_review_is_single_character,
        themed_display_image=themed_display_image,
    )


def _review_entry_deps() -> _review_entry.ReviewEntryDeps:
    """Capture live ReviewWindow collaborators at event dispatch."""
    return _review_entry.ReviewEntryDeps(
        tk=tk,
        messagebox=messagebox,
        read_pdic=read_pdic,
        pdic_path=pdic_path,
        simplified_entry_key=simplified_entry_key,
        sync_review_entry_classification=sync_review_entry_classification,
    )


def _review_page_deps() -> _review_page.ReviewPageDeps:
    """Capture live ReviewWindow collaborators at event dispatch."""
    return _review_page.ReviewPageDeps(
        tk=tk,
        replace=replace,
        Image=Image,
        json=json,
        threading=threading,
        Path=Path,
        ocr_cache_root=ocr_cache_root,
        ppp_read_path_for_image=ppp_read_path_for_image,
        pdic_path=pdic_path,
        read_pdic=read_pdic,
        normalize_page_rgb=normalize_page_rgb,
        effective_page_settings=effective_page_settings,
        page_template_analysis_image=page_template_analysis_image,
        derive_geometry=derive_geometry,
        read_page_sections=read_page_sections,
        sort_entries_reading_order=sort_entries_reading_order,
        read_ppp=read_ppp,
        _review_crop_context=_review_crop_context,
        _review_line_box=_review_line_box,
        settings_path=settings_path,
    )


def _page_index_deps() -> _page_index.PageIndexDeps:
    """Snapshot original module bindings for a page index callback."""
    return _page_index.PageIndexDeps(
        tk=tk,
        ttk=ttk,
        font=font,
        simpledialog=simpledialog,
        Image=Image,
        Path=Path,
        _sorted_page_list_rows=_sorted_page_list_rows,
        _fill_status_cell_style=_fill_status_cell_style,
        settings_path=settings_path,
        read_page_sections=read_page_sections,
        write_page_sections=write_page_sections,
        PageSection=PageSection,
        LayoutTransform=LayoutTransform,
        normalize_page_rgb=normalize_page_rgb,
        page_template_analysis_image=page_template_analysis_image,
        derive_geometry=derive_geometry,
        effective_page_settings=effective_page_settings,
        read_pdic=read_pdic,
        pdic_path=pdic_path,
        read_ppp=read_ppp,
        visible_page_iids=visible_page_iids,
        _natural_text_key=_natural_text_key,
    )


def _word_fill_status_deps() -> _word_fill_status.WordFillStatusDeps:
    """Snapshot original module bindings for a page index callback."""
    return _word_fill_status.WordFillStatusDeps(
        Path=Path,
        json=json,
        os=os,
        word_fill_status_path=word_fill_status_path,
    )


def _main_canvas_render_deps() -> _main_canvas_render.MainCanvasRenderDeps:
    """Resolve live original Tk/geometry helpers for main-canvas drawing."""
    return _main_canvas_render.MainCanvasRenderDeps(
        clear_alpha_line_photos=clear_alpha_line_photos,
        clear_alpha_polygon_records=clear_alpha_polygon_records,
        draw_layout_visualization_if_enabled=draw_layout_visualization_if_enabled,
        draw_ocr_crop_preview=draw_ocr_crop_preview,
        parameter_scale=parameter_scale,
        create_alpha_canvas_line=create_alpha_canvas_line,
        scaled_overlay_line_width=scaled_overlay_line_width,
        tk=tk,
        create_alpha_canvas_polygon=create_alpha_canvas_polygon,
        _entry_font_spec=_entry_font_spec,
        resolve_content_font_family=resolve_content_font_family,
        label_text=label_text,
        create_illustration_delete_control=create_illustration_delete_control,
        entry_crop_piece_filename=entry_crop_piece_filename,
        _review_crop_settings=_review_crop_settings,
        _review_line_box=_review_line_box,
        Image=Image,
        ImageTk=ImageTk,
    )


def _canvas_pointer_deps() -> _canvas_pointer.CanvasPointerDeps:
    """Snapshot app symbols preserving original patched Tk and geometry seams."""
    return _canvas_pointer.CanvasPointerDeps(
        tk=tk,
        label_text=label_text,
        user_edited_link=user_edited_link,
        messagebox=messagebox,
        polygon_delete_center=polygon_delete_center,
        refresh_alpha_polygon_fill=refresh_alpha_polygon_fill,
        PageSection=PageSection,
        nearest_polygon_segment=nearest_polygon_segment,
        WordEntry=WordEntry,
        entry_allowed_by_page_template=entry_allowed_by_page_template,
        v_is_inside_sections=v_is_inside_sections,
        column_index_for_click=column_index_for_click,
    )


class PictureCaptureApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self._app_icon_photo: ImageTk.PhotoImage | None = None
        self._app_icon_registered = False
        self._app_icon_error: str | None = None
        icon_path = Path(__file__).resolve().parent / "data" / "app_icon.png"
        try:
            if not icon_path.exists():
                self._app_icon_error = f"icon asset not found: {icon_path}"
            else:
                with Image.open(icon_path) as icon_image:
                    self._app_icon_photo = ImageTk.PhotoImage(icon_image.convert("RGBA"))
        except (tk.TclError, OSError) as exc:
            self._app_icon_photo = None
            self._app_icon_error = f"{type(exc).__name__}: {exc} (path={icon_path})"
        if self._app_icon_photo is not None:
            # Prefer Tk's default icon so future Toplevels inherit it. Some
            # window-manager/headless combinations reject the default flag, so
            # fall back to explicitly setting the root icon instead.
            try:
                self.iconphoto(True, self._app_icon_photo)
                self._app_icon_registered = True
            except tk.TclError:
                try:
                    self.iconphoto(False, self._app_icon_photo)
                    self._app_icon_registered = True
                except tk.TclError:
                    pass
        # Reapply icon to mapped secondary windows.
        self.bind_class("Toplevel", "<Map>", self._app_icon_toplevel_mapped, add="+")
        self.title("Picture Capture")
        fit_window_to_work_area(self, 1440, 900, min_width=1, min_height=680)
        self.project: ProjectState | None = None
        self._project_words: set[str] = set()
        self.settings = AppSettings()
        self.current_index = -1
        self.current_page: Path | None = None
        self.image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.view_scale = 1.0
        self.entries: list[WordEntry] = []
        self.polygons: list[PolygonRegion] = []
        self.page_sections: list[PageSection] = []
        self._section_editing = False
        self._drag_section_boundary: tuple[int, str] | None = None
        self._ruler_hint: tk.Toplevel | None = None
        self._pending_section_editor_index: int | None = None
        self.new_polygon: list[tuple[int, int]] = []
        self.overlay_widgets: list[tk.Widget] = []
        self.entry_editor_bindings: list[tuple[tk.Entry, WordEntry]] = []
        self.status_var = tk.StringVar(value="请选择一个词典扫描项目目录")
        self.cursor_status_var = tk.StringVar(value="坐标：—｜缩放 100%｜词条 0")
        self.image_metadata_status_var = tk.StringVar(value="—×— px")
        self.hide_var = tk.BooleanVar(value=False)
        # polygon_var controls visibility of saved illustration polygons.
        # polygon_draw_var is a separate, explicit editing mode.
        self.polygon_var = tk.BooleanVar(value=False)
        self.polygon_draw_var = tk.BooleanVar(value=False)
        self.auxiliary_mode_var = tk.BooleanVar(value=False)
        self._auxiliary_edits = AuxiliaryLineEdits()
        self._auxiliary_drag = None
        self.crop_preview_var = tk.BooleanVar(value=False)
        self.binary_preview_var = tk.BooleanVar(value=False)
        self.display_mode_var = tk.StringVar(value="原图+标注")
        self._display_mode_syncing = False
        # Non-destructive scan preprocessing reuses the main canvas and page list.
        self.preprocess_mode_var = tk.BooleanVar(value=False)
        self.preprocess_auto_deskew_var = tk.BooleanVar(
            value=bool(self.settings.preprocess_auto_deskew)
        )
        self.preprocess_safety_var = tk.StringVar(
            value=str(int(self.settings.preprocess_safety_margin_px))
        )
        self.preprocess_geometry_var = tk.StringVar(
            value={
                "deskew": "轻量：旋转+裁边",
                "perspective": "自动透视",
                "dewarp": "UVDoc展平（Paddle高级）",
                "uvdoc": "UVDoc展平（Paddle高级）",
                "auto": "自动几何（推荐）",
            }.get(
                str(getattr(self.settings, "preprocess_geometry_mode", "auto") or "auto"),
                "自动几何（推荐）",
            )
        )
        self.preprocess_export_canvas_var = tk.BooleanVar(
            value=bool(getattr(self.settings, "preprocess_export_canvas_enabled", False))
        )
        self.preprocess_export_canvas_mode_var = tk.StringVar(
            value={
                "batch_max": "本批最大裁剪尺寸",
                "custom": "自定义尺寸",
            }.get(
                str(getattr(self.settings, "preprocess_export_canvas_mode", "batch_max") or "batch_max"),
                "本批最大裁剪尺寸",
            )
        )
        self.preprocess_export_canvas_width_var = tk.StringVar(
            value=str(int(getattr(self.settings, "preprocess_export_canvas_width", 0) or 0))
        )
        self.preprocess_export_canvas_height_var = tk.StringVar(
            value=str(int(getattr(self.settings, "preprocess_export_canvas_height", 0) or 0))
        )
        self.preprocess_export_margin_top_var = tk.StringVar(
            value=str(int(getattr(self.settings, "preprocess_export_margin_top", 0) or 0))
        )
        self.preprocess_export_margin_bottom_var = tk.StringVar(
            value=str(int(getattr(self.settings, "preprocess_export_margin_bottom", 0) or 0))
        )
        self.preprocess_export_margin_left_var = tk.StringVar(
            value=str(int(getattr(self.settings, "preprocess_export_margin_left", 0) or 0))
        )
        self.preprocess_export_margin_right_var = tk.StringVar(
            value=str(int(getattr(self.settings, "preprocess_export_margin_right", 0) or 0))
        )
        self.preprocess_export_align_x_var = tk.StringVar(
            value={
                "left": "左对齐", "center": "居中", "right": "右对齐",
            }.get(
                str(getattr(self.settings, "preprocess_export_align_x", "center") or "center"),
                "居中",
            )
        )
        self.preprocess_export_align_y_var = tk.StringVar(
            value={
                "top": "顶端对齐", "center": "居中", "bottom": "底部对齐",
            }.get(
                str(getattr(self.settings, "preprocess_export_align_y", "top") or "top"),
                "顶端对齐",
            )
        )
        self.preprocess_status_var = tk.StringVar(value="未分析")
        self._preprocess_results: dict[str, PreprocessAnalysis] = {}
        self._preprocess_photo: ImageTk.PhotoImage | None = None
        self._preprocess_photo_cache_key: tuple | None = None
        self._preprocess_corrected_image: Image.Image | None = None
        self._preprocess_corrected_image_key: tuple[int, int] | None = None
        self._preprocess_locked_widgets: list[tuple[tk.Misc, object]] = []
        self.preprocess_mode_button: ttk.Button | None = None
        self.polygon_draw_button: ttk.Button | None = None
        # PPP label editors and vertex-drag state are rebuilt with each canvas redraw.
        self.polygon_label_bindings: list[tuple[tk.Entry, PolygonRegion]] = []
        self._polygon_canvas_items: dict[int, dict] = {}
        self._drag_polygon_vertex: tuple[int, int] | None = None
        self._drag_polygon_edge: tuple[int, str] | None = None
        self._quick_autosave_job: str | None = None
        self._quick_trace_ready = False
        self.autosave_var = tk.BooleanVar(value=True)
        self.autosave_job: str | None = None
        self.cursor_canvas_xy: tuple[float, float] | None = None
        self.ocr_review_candidates: list[dict] = []
        self.candidate_check_vars: dict[str, tk.BooleanVar] = {}
        # v2.9.4: keep page pixels and foreground edit widgets on separate
        # lifecycles. Candidate checkbox edits only touch the corresponding
        # entry overlay; the expensive resized background PhotoImage is reused
        # until either the page object or view scale changes.
        self._display_photo_cache_key: tuple | None = None
        self._display_geometry_cache_key: tuple | None = None
        self._display_geometry_cache = None
        self._entry_visuals: dict[int, dict] = {}
        # Checkbox edits are immediately committed to the in-memory page model,
        # then PDIC/manual-selection disk writes are coalesced for a few hundred
        # milliseconds. Every page/project/batch boundary force-flushes them.
        self._deferred_save_job: str | None = None
        self._deferred_save_page: Path | None = None
        self._deferred_save_snapshot = None
        self._deferred_save_delay_ms = 300
        self._pending_manual_override_path: Path | None = None
        self._pending_manual_override_payload: dict | None = None
        self.ocr_review_window: OCRConflictReviewDialog | None = None
        self.review_window: ReviewWindow | None = None
        # (page_index, x, y) of the proofreading row mirrored on the main canvas.
        self._review_entry_highlight_target: tuple[int, int, int] | None = None
        # Keep the RGBA PhotoImage alive while the translucent review marker is shown.
        self._review_entry_highlight_photo: ImageTk.PhotoImage | None = None
        self.old_new_compare_window: OldNewComparisonWindow | None = None
        # Session-only source for 【新旧比较】.  The first comparison asks the
        # user to choose a page-aware wordslist TXT, then reuses it until changed.
        self._old_new_compare_source_path: Path | None = None
        self._usage_guide_window: UsageGuideWindow | None = None
        self._page_meta_generation = 0
        self._page_meta_job: str | None = None
        # v2.9.11: page-list headings are clickable. Sorting only changes the
        # Treeview display order; stable iids remain project page indices, so
        # selection/navigation always resolves to the original page.
        self._page_list_sort_column: str | None = None
        self._page_list_sort_descending = False
        self._page_list_sort_job: str | None = None
        # Pages whose line count disagreed with the last page-aware TXT fill.
        # Only the ``画线`` cell is overlaid in pale red; the page-name cell
        # remains untouched so the warning is visually scoped to the count issue.
        self._word_fill_mismatch_pages: set[int] = set()
        # v2.9.9: persist the last page-aware fill count check so pale-red
        # mismatch cells survive application/project reopen. Matching pages are
        # stored too, allowing later manual line-count edits to recompute the
        # warning against the remembered TXT count.
        self._word_fill_check_status: dict[str, dict] = {}
        # v2.9.8: selecting a large page-aware TXT and actually filling PDICs
        # are separate actions.  The parsed page->words mapping is cached after
        # the first fill so correcting a mismatch range never requires choosing
        # or reparsing the same 190k-word source again.
        self._word_fill_source_path: Path | None = None
        self._word_fill_source_signature: tuple[str, int, int] | None = None
        self._word_fill_source_mapping: dict[str, list[str]] | None = None
        # v2.9.10: remember which project pages were explicitly represented in
        # the selected TXT. An empty list and a completely absent page are not
        # the same thing for the visible fill-status column.
        self._word_fill_source_present_pages: set[str] | None = None
        self._page_lined_overlays: dict[int, tk.Label] = {}
        # v2.9.12: the visible fill-status cell carries its own semantic color
        # (match/mismatch/stale/no-data), while the legacy mismatch warning in
        # the 画线 cell is retained for compatibility and quick scanning.
        self._page_fill_status_overlays: dict[int, tk.Label] = {}
        # v2.9.13: cell-overlay repaints are coalesced.  Older builds queued an
        # after_idle repaint for every row metadata update/scroll callback; on
        # large dictionaries that turned startup into thousands of redundant
        # full-list scans.  Keep at most one pending repaint instead.
        self._page_overlay_refresh_job: str | None = None
        # Batch work runs off Tk; pause/stop at page boundaries.
        self._batch_queue: queue.Queue = queue.Queue()
        self._batch_thread: threading.Thread | None = None
        self._batch_pause_event = threading.Event()
        self._batch_pause_event.set()
        self._batch_stop_event = threading.Event()
        self._batch_active = False
        self._batch_parallel = False
        # Foreground edits are page-state locked to protect background PDIC.
        self._batch_foreground_pages = False
        # Navigation is independent from the task write lock.
        self._batch_allow_page_navigation = False
        self._batch_allow_pdic_edits = False
        self._batch_page_states: dict[int, str] = {}
        self._batch_state_lock = threading.Lock()
        self._batch_skipped_count = 0
        self._batch_poll_job: str | None = None
        self._batch_close_after_stop = False
        self._batch_on_done = None
        self._batch_title = ""
        # One-shot background jobs use a separate queue from multi-page batch
        # work. Workers never call Tk; per-key generations discard stale results.
        self._ui_worker_queue: queue.Queue = queue.Queue()
        self._ui_worker_poll_job: str | None = None
        self._ui_worker_generations: dict[str, int] = {}
        self._ui_worker_handlers: dict[tuple[str, int], tuple] = {}
        self._ui_worker_active: set[tuple[str, int]] = set()
        self._ui_worker_close_wait: set[tuple[str, int]] = set()
        self._ui_worker_shutdown = False
        self._ui_close_requested = False
        self._pending_page_index: int | None = None
        self.session_controller = SessionController(self)
        self._session_path = self._default_session_state_path()
        self._last_session = self._read_session_state()
        stored_mode = self._last_session.get("workspace_mode", "最大")
        self.workspace_mode = (
            "紧凑" if stored_mode in {"最简", "简单"} else stored_mode
            if stored_mode in {"极简", "紧凑", "正常", "最大"} else "最大"
        )
        self._restore_workspace_mode_pending = True
        requested_appearance = normalize_appearance_preference(
            self._last_session.get("appearance_mode")
        )
        self.appearance_preference = requested_appearance
        self.appearance_mode = "light"
        self.appearance_mode_var = tk.StringVar(
            value=APPEARANCE_MODE_LABELS[requested_appearance]
        )
        self._system_appearance_job: str | None = None
        self._light_ttk_theme = str(ttk.Style(self).theme_use())
        self._configure_global_appearance()
        self.section_expanded = {
            "preprocess": False,
            "normal": True,
            "aux": False,
            "ocr": False,
            "actions": False,
            "postproduction": False,
            "pages": True,
        }
        stored_sections = self._last_session.get("section_expanded", {})
        if isinstance(stored_sections, dict):
            for key in tuple(self.section_expanded):
                if key in stored_sections:
                    self.section_expanded[key] = bool(stored_sections[key])
        self._collapsible_sections: dict[str, ttk.LabelFrame] = {}
        self.section_title_font = font.nametofont("TkDefaultFont").copy()
        self.section_title_font.configure(weight="bold")
        # Keep miniature page rows at 90%, with separate 80% range controls.
        default_page_font = font.nametofont("TkDefaultFont")
        self.compact_page_font = default_page_font.copy()
        base_size = int(default_page_font.cget("size"))
        compact_size = max(7, round(base_size * 0.9)) if base_size > 0 else min(-7, round(base_size * 0.9))
        self.compact_page_font.configure(size=compact_size)
        self._configure_main_workspace_styles()
        self._auxiliary_controller = AuxiliaryLineController(self)
        self.canvas_controller = CanvasController(self)
        self.crop_controller = CropController(self)
        self.detection_controller = DetectionController(self)
        self.export_controller = ExportController(self)
        self.headword_controller = HeadwordController(
            self,
            parse_words_of_pages_text=_parse_words_of_pages_text,
            fill_page_entries=_fill_page_entries,
        )
        self.illustration_controller = IllustrationController(self)
        self.ref_box_controller = RefBoxController(self)
        self.project_controller = ProjectController(self)
        self.page_controller = PageController(self)
        self.review_controller = ReviewController(self)
        self._build_ui()
        self.bind_class("Toplevel", "<Map>", self._appearance_toplevel_mapped, add="+")
        self.set_appearance_mode(requested_appearance, persist=False)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.toggle_autosave()
        # Avoid maximize -> restore-to-compact flicker during session startup.
        if self.workspace_mode == "最大":
            self.after_idle(self._maximize_main_window)
        self.after_idle(self._ensure_sidebar_navigation_width)
        self.after_idle(self.restore_last_session)
        attach_nonbmp_unicode_input(self)

    def destroy(self) -> None:
        close_nonbmp_unicode_input(self)
        super().destroy()


    def _app_icon_toplevel_mapped(self, event: tk.Event) -> None:
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Toplevel) or self._app_icon_photo is None:
            return
        if getattr(widget, "_pc_app_icon_applied", False):
            return
        # Mark before iconphoto(): on Windows, changing the window icon while a
        # Toplevel is mapping may itself produce another Map notification.
        # The guard keeps icon propagation idempotent and prevents a remap loop.
        widget._pc_app_icon_applied = True
        try:
            widget.iconphoto(False, self._app_icon_photo)
        except tk.TclError:
            pass

    def _maximize_main_window(self) -> None:
        """Start the main window maximized, with cross-platform fallbacks."""
        try:
            self.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            self.attributes("-zoomed", True)
        except tk.TclError:
            try:
                work_x, work_y, work_w, work_h = _screen_work_area(self)
                self.geometry(f"{work_w}x{work_h}+{work_x}+{work_y}")
            except tk.TclError:
                pass

    def _ensure_sidebar_navigation_width(self) -> None:
        """Keep the sidebar at its mode-specific size, not the old 520px."""
        paned = self.__dict__.get("main_paned")
        if paned is None or not hasattr(self, "workspace_rail_width"):
            return
        try:
            from .ui.workspace_tools import preferred_sidebar_width
            self.update_idletasks()
            target = preferred_sidebar_width(
                self, extreme=self.workspace_mode == "极简",
                compact=self.workspace_mode == "紧凑",
            )
            available = max(1, self.winfo_width() - 160)
            paned.sashpos(0, min(target, available))
        except (tk.TclError, ValueError):
            return

    def _ui_worker_key_active(self, key: str) -> bool:
        return any(token[0] == key for token in self._ui_worker_active)

    def _start_ui_worker(
        self, key: str, worker, on_done, on_error=None, *, wait_on_close: bool = False,
    ) -> int:
        """Run one replaceable blocking operation without letting its worker touch Tk.

        wait_on_close is reserved for workers that may mutate durable files.
        A close request suppresses their UI callback but defers destroy() until
        the worker has reached its own success/error cleanup boundary.
        """
        if self._ui_worker_shutdown or self._ui_close_requested:
            return -1
        stale = [token for token in self._ui_worker_handlers if token[0] == key]
        for token in stale:
            self._ui_worker_handlers.pop(token, None)
        generation = int(self._ui_worker_generations.get(key, 0)) + 1
        self._ui_worker_generations[key] = generation
        token = (key, generation)
        self._ui_worker_handlers[token] = (on_done, on_error)
        self._ui_worker_active.add(token)
        if wait_on_close:
            self._ui_worker_close_wait.add(token)

        def runner() -> None:
            try:
                result = worker()
                event = ("done", key, generation, result, None, None)
            except Exception as exc:
                event = ("error", key, generation, None, exc, traceback.format_exc())
            self._ui_worker_queue.put(event)

        threading.Thread(
            target=runner, name=f"PictureCapture-{key}-{generation}", daemon=True,
        ).start()
        if self._ui_worker_poll_job is None:
            self._ui_worker_poll_job = self.after(40, self._poll_ui_worker_queue)
        return generation

    def _invalidate_ui_worker(self, key: str) -> None:
        self._ui_worker_generations[key] = int(self._ui_worker_generations.get(key, 0)) + 1
        stale = [token for token in self._ui_worker_handlers if token[0] == key]
        for token in stale:
            self._ui_worker_handlers.pop(token, None)

    def _poll_ui_worker_queue(self) -> None:
        self._ui_worker_poll_job = None
        if self._ui_worker_shutdown:
            return
        processed = 0
        while processed < 48:
            try:
                kind, key, generation, result, exc, detail = self._ui_worker_queue.get_nowait()
            except queue.Empty:
                break
            processed += 1
            token = (key, generation)
            self._ui_worker_active.discard(token)
            self._ui_worker_close_wait.discard(token)
            handler = self._ui_worker_handlers.pop(token, None)
            if (
                not self._ui_close_requested
                and generation == self._ui_worker_generations.get(key)
                and handler is not None
            ):
                on_done, on_error = handler
                try:
                    if kind == "done":
                        on_done(result)
                    elif on_error is not None:
                        on_error(exc, detail)
                    else:
                        if detail:
                            print(detail)
                        self.show_error(f"{key}失败", exc)
                except tk.TclError:
                    pass
                except Exception as callback_exc:
                    traceback.print_exc()
                    try:
                        self.show_error(f"{key}完成处理失败", callback_exc)
                    except tk.TclError:
                        pass

        if self._ui_close_requested and not self._ui_worker_close_wait:
            self.after_idle(self.on_close)
            return
        if (
            (self._ui_worker_handlers or self._ui_worker_close_wait or self._ui_worker_active)
            and not self._ui_worker_shutdown
        ):
            self._ui_worker_poll_job = self.after(
                8 if processed >= 48 else 60, self._poll_ui_worker_queue
            )

    def _configure_global_appearance(self) -> None:
        """Configure the active ttk theme for the global light/dark appearance."""
        style = ttk.Style(self)
        mode = normalize_appearance_mode(self.appearance_mode)
        palette = appearance_palette(mode)

        # ttk.Combobox popdowns are classic Tk Listboxes on common Tk builds;
        # style.configure("TCombobox", ...) does not recolor that popup.
        for pattern, value in (
            ("*TCombobox*Listbox.background", palette["input_bg"]),
            ("*TCombobox*Listbox.foreground", palette["input_fg"]),
            ("*TCombobox*Listbox.selectBackground", palette["selection"]),
            ("*TCombobox*Listbox.selectForeground", palette["selection_fg"]),
        ):
            try:
                self.option_add(pattern, value)
            except tk.TclError:
                pass

        if mode == "light":
            try:
                if self._light_ttk_theme in style.theme_names():
                    style.theme_use(self._light_ttk_theme)
            except tk.TclError:
                pass
            self.configure(bg=palette["bg"])
            return

        try:
            if "PCDark" not in style.theme_names():
                parent_theme = "clam" if "clam" in style.theme_names() else self._light_ttk_theme
                style.theme_create("PCDark", parent=parent_theme)
            style.theme_use("PCDark")
        except tk.TclError:
            pass

        style.configure(".", background=palette["surface"], foreground=palette["text"])
        style.configure("TFrame", background=palette["surface"])
        style.configure("TLabel", background=palette["surface"], foreground=palette["text"])
        style.configure("TLabelframe", background=palette["surface"], foreground=palette["text"])
        style.configure("TLabelframe.Label", background=palette["surface"], foreground=palette["text"])
        style.configure(
            "TButton", background=palette["button"], foreground=palette["text"],
            anchor="center", justify="center",
            bordercolor=palette["border"], lightcolor=palette["button"], darkcolor=palette["button"],
        )
        style.map(
            "TButton",
            background=[("active", palette["button_hover"]), ("pressed", palette["selection"])],
            foreground=[("disabled", palette["muted"]), ("!disabled", palette["text"])],
        )
        for style_name in ("TCheckbutton", "TRadiobutton"):
            style.configure(style_name, background=palette["surface"], foreground=palette["text"])
            style.map(
                style_name,
                background=[("active", palette["surface_alt"])],
                foreground=[("disabled", palette["muted"]), ("!disabled", palette["text"])],
            )
        for style_name in ("TEntry", "TSpinbox", "TCombobox"):
            style.configure(
                style_name,
                fieldbackground=palette["input_bg"],
                foreground=palette["input_fg"],
                background=palette["button"],
                bordercolor=palette["border"],
                insertcolor=palette["input_fg"],
                arrowcolor=palette["text"],
            )
            style.map(
                style_name,
                fieldbackground=[("readonly", palette["surface_alt"]), ("disabled", palette["surface_alt"])],
                foreground=[("readonly", palette["text"]), ("disabled", palette["muted"])],
            )
        style.configure("TNotebook", background=palette["bg"], bordercolor=palette["border"])
        style.configure(
            "TNotebook.Tab", background=palette["surface_alt"], foreground=palette["muted"],
            padding=(10, 5),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", palette["surface"]), ("active", palette["button_hover"])],
            foreground=[("selected", palette["text"]), ("active", palette["text"])],
        )
        style.configure(
            "Treeview",
            background=palette["surface"],
            fieldbackground=palette["surface"],
            foreground=palette["text"],
            bordercolor=palette["border"],
        )
        style.map(
            "Treeview",
            background=[("selected", palette["selection"])],
            foreground=[("selected", palette["selection_fg"])],
        )
        style.configure(
            "Treeview.Heading",
            background=palette["surface_alt"], foreground=palette["text"],
            bordercolor=palette["border"], relief="flat",
        )
        style.map("Treeview.Heading", background=[("active", palette["button_hover"])])
        style.configure("TSeparator", background=palette["border"])
        style.configure("TPanedwindow", background=palette["border"])
        style.configure(
            "TScrollbar",
            background=palette["button"],
            troughcolor=palette["surface_alt"],
            bordercolor=palette["border"],
            arrowcolor=palette["text"],
            lightcolor=palette["button"],
            darkcolor=palette["button"],
        )
        style.map("TScrollbar", background=[("active", palette["button_hover"])])
        style.configure(
            "TMenubutton",
            background=palette["button"], foreground=palette["text"],
            bordercolor=palette["border"], arrowcolor=palette["text"],
        )
        style.configure(
            "TScale",
            background=palette["surface"], troughcolor=palette["surface_alt"],
            bordercolor=palette["border"],
        )
        style.configure(
            "TProgressbar", background=palette["accent"], troughcolor=palette["surface_alt"],
            bordercolor=palette["border"],
        )
        self.configure(bg=palette["bg"])

    def _apply_current_appearance(self, root: tk.Misc) -> None:
        try:
            if not root.winfo_exists():
                return
            apply_classic_widget_appearance(root, self.appearance_mode)
            if not isinstance(root, (tk.Tk, tk.Toplevel)):
                return
            apply_native_titlebar_appearance(root, self.appearance_mode)
            # A transient Toplevel can disappear between the existence check
            # and the first child traversal (e.g. a tooltip during startup).
            stack = list(root.winfo_children())
        except tk.TclError:
            return
        while stack:
            widget = stack.pop()
            if isinstance(widget, tk.Toplevel):
                apply_native_titlebar_appearance(widget, self.appearance_mode)
            try:
                stack.extend(widget.winfo_children())
            except tk.TclError:
                pass

    def _appearance_toplevel_mapped(self, event: tk.Event) -> None:
        widget = getattr(event, "widget", None)
        if widget is None:
            return
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return
        # Applying a native title-bar appearance may itself trigger another
        # <Map> event on Windows.  Keep only one pending idle callback per
        # Toplevel so icon/titlebar refreshes cannot form a remap loop.
        if getattr(widget, "_pc_appearance_map_pending", False):
            return
        widget._pc_appearance_map_pending = True

        def apply_mapped_appearance(w=widget) -> None:
            try:
                self._apply_current_appearance(w)
            finally:
                try:
                    w._pc_appearance_map_pending = False
                except (AttributeError, tk.TclError):
                    pass

        try:
            # The callback belongs to the mapped window: destroying a tooltip
            # automatically removes its pending Tcl callback.
            widget.after_idle(apply_mapped_appearance)
        except tk.TclError:
            widget._pc_appearance_map_pending = False

    def _appearance_mode_selected(self, _event: tk.Event | None = None) -> None:
        self.set_appearance_mode(
            APPEARANCE_MODE_VALUES.get(self.appearance_mode_var.get(), "light")
        )

    def _cancel_system_appearance_poll(self) -> None:
        if self._system_appearance_job is not None:
            try:
                self.after_cancel(self._system_appearance_job)
            except tk.TclError:
                pass
            self._system_appearance_job = None
        self._invalidate_ui_worker("system-appearance-detect")

    def _schedule_system_appearance_poll(self, delay_ms: int = 2500) -> None:
        if self.appearance_preference != "system" or self._ui_worker_shutdown:
            return
        if self._system_appearance_job is not None:
            try:
                self.after_cancel(self._system_appearance_job)
            except tk.TclError:
                pass
        self._system_appearance_job = self.after(
            max(0, int(delay_ms)), self._poll_system_appearance
        )

    def _poll_system_appearance(self) -> None:
        self._system_appearance_job = None
        if self.appearance_preference != "system" or self._ui_worker_shutdown:
            return

        def worker() -> str:
            return detect_system_appearance_mode()

        def done(mode: str) -> None:
            if self.appearance_preference != "system":
                return
            resolved = normalize_appearance_mode(mode)
            if resolved != self.appearance_mode:
                self._apply_resolved_appearance(resolved)
            self._schedule_system_appearance_poll()

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            if self.appearance_preference == "system":
                self._schedule_system_appearance_poll()

        self._start_ui_worker("system-appearance-detect", worker, done, failed)

    def set_appearance_mode(self, mode: object, *, persist: bool = True) -> None:
        """Set light/dark/system preference without changing project data."""
        preference = normalize_appearance_preference(mode)
        self.appearance_preference = preference
        label = APPEARANCE_MODE_LABELS[preference]
        if self.appearance_mode_var.get() != label:
            self.appearance_mode_var.set(label)
        self._cancel_system_appearance_poll()
        if preference == "system":
            self._schedule_system_appearance_poll(delay_ms=0)
        else:
            self._apply_resolved_appearance(preference)
        if persist:
            self._save_session_state()

    def _apply_resolved_appearance(self, mode: object) -> None:
        normalized = normalize_appearance_mode(mode)
        self.appearance_mode = normalized
        self._configure_global_appearance()
        self._configure_main_workspace_styles()
        previews = self.__dict__.get("_page_thumbnails")
        if previews is not None:
            previews.apply()  # Theme reconfiguration resets the Treeview rowheight.
        self._apply_current_appearance(self)
        from .ui.workspace_tools import (
            refresh_compact_header_buttons, refresh_macaron_action_buttons,
        )
        from .ui.simple_page_controls import refresh_compact_range_appearance
        refresh_macaron_action_buttons(self)
        refresh_compact_header_buttons(self)
        refresh_compact_range_appearance(self)
        palette = appearance_palette(normalized)
        for name, color_key in (("sidebar_canvas", "bg"), ("canvas", "canvas")):
            widget = self.__dict__.get(name)
            if widget is not None:
                try:
                    widget.configure(bg=(self._main_ui_colors["canvas"] if name == "canvas" else palette[color_key]))
                except tk.TclError:
                    pass

        review = self.__dict__.get("review_window")
        if review is not None:
            try:
                if review.winfo_exists():
                    review._configure_word_list_appearance()
                    review._configure_review_styles()
                    if getattr(review, "_filter_rows_active", False):
                        review._request_filter_batch_render()
                    else:
                        review._request_render_rows(focus_index=review.active_index)
            except tk.TclError:
                pass

        settings_dialog = self.__dict__.get("_settings_dialog")
        if settings_dialog is not None:
            try:
                if settings_dialog.winfo_exists():
                    settings_dialog.refresh_appearance()
            except tk.TclError:
                pass
        guide = self.__dict__.get("_usage_guide_window")
        if guide is not None:
            try:
                if guide.winfo_exists():
                    guide.refresh_appearance()
            except tk.TclError:
                pass
        comparison = self.__dict__.get("old_new_compare_window")
        if comparison is not None:
            try:
                if comparison.winfo_exists():
                    comparison.refresh_appearance()
            except tk.TclError:
                pass
        recent_dialog = self.__dict__.get("_recent_projects_dialog")
        recent_rebuild = self.__dict__.get("_recent_projects_rebuild")
        if recent_dialog is not None and callable(recent_rebuild):
            try:
                if recent_dialog.winfo_exists():
                    recent_rebuild()
            except tk.TclError:
                pass

        self.photo = None
        self._display_photo_cache_key = None
        self._preprocess_photo = None
        self._preprocess_photo_cache_key = None
        self._schedule_page_cell_overlay_refresh()
        if self.image is not None:
            self.redraw()


    def _configure_main_workspace_styles(self) -> None:
        """Configure a scoped, dense visual system for the main workspace only.

        Do not switch the global ttk theme here. Secondary windows, especially
        proofreading, intentionally keep their existing appearance; every style
        below is opt-in through a PC.* style name.
        """
        style = ttk.Style(self)
        base = appearance_palette(self.appearance_mode)
        if self.appearance_mode == "dark":
            colors = {
                "sidebar": base["bg"],
                "footer": base["surface"],
                "status": base["bg"],
                "batch": base["surface_alt"],
                "border": base["border"],
                "text": base["text"],
                "muted": base["muted"],
                "button": base["button"],
                "button_hover": base["button_hover"],
                "button_border": base["border"],
                "primary": base["accent"],
                "primary_hover": base["accent_hover"],
                "success": base["success"],
                "success_hover": base["success_hover"],
                "tree_selected": base["selection"],
                "canvas": base["canvas"],
                "ruler_margin": "#20252b",
            }
        else:
            native_background = str(style.lookup("TFrame", "background") or "#f6f7f9")
            colors = {
                "sidebar": native_background,
                "footer": "#f1f3f6",
                "status": "#f6f7f9",
                "batch": "#eef2f6",
                "border": "#d8dde5",
                "text": "#000000",
                "muted": "#68707b",
                "button": "#f4f5f7",
                "button_hover": "#e7eaee",
                "button_border": "#d3d8df",
                "primary": "#4F7CAC",
                "primary_hover": "#416A94",
                "success": "#69A875",
                "success_hover": "#588F64",
                "tree_selected": "#dce8f7",
                "canvas": "#e9edf2",
                "ruler_margin": "#f1f3f6",
            }
        self._main_ui_colors = colors

        style.configure("PC.Sidebar.TFrame", background=colors["sidebar"])
        style.configure("PC.Footer.TFrame", background=colors["footer"])
        style.configure("PC.Status.TFrame", background=colors["status"])
        style.configure("PC.Batch.TFrame", background=colors["batch"])
        style.configure("PC.SectionBody.TFrame", background=colors["sidebar"])

        style.configure(
            "PC.Section.TLabelframe",
            background=colors["sidebar"],
            borderwidth=0,
            relief="flat",
        )
        style.configure(
            "PC.SectionTitle.TLabel",
            background=colors["sidebar"],
            foreground=colors["text"],
            font=self.section_title_font,
            padding=(0, 2, 0, 1),
        )
        style.configure(
            "PC.FieldLabel.TLabel",
            background=colors["sidebar"],
            foreground=colors["text"],
        )
        style.configure(
            "PC.Footer.TLabel",
            background=colors["footer"],
            foreground=colors["muted"],
        )
        style.configure(
            "PC.Status.TLabel",
            background=colors["status"],
            foreground=colors["muted"],
        )
        style.configure(
            "PC.Batch.TLabel",
            background=colors["batch"],
            foreground=colors["text"],
        )

        # Keep rail controls the same font and compact geometry in both themes.
        style.configure("PC.Rail.TButton", font="TkDefaultFont",
                        padding=(0, 0), relief="flat", borderwidth=0,
                        anchor="center", justify="center")
        style.configure("PC.QuickRail.TButton", font="TkDefaultFont",
                        padding=(0, 0), relief="flat", borderwidth=0,
                        anchor="center", justify="center")
        # Different ttk themes inherit different caption alignment defaults.
        for button_style in (
            "PC.Compact.TButton", "PC.Tool.TButton", "PC.Footer.TButton",
            "PC.PageNav.TButton", "PC.SimplePage.TButton",
            "PC.WindowMode.TButton", "PC.WindowProject.TButton",
            "PC.WindowQuick.TButton", "PC.Workspace80.TButton",
        ):
            style.configure(button_style, anchor="center", justify="center")
        style.configure("PC.CompactPage.Treeview", rowheight=22,
                        font=self.compact_page_font, background=base["surface"],
                        fieldbackground=base["surface"], foreground=colors["text"])
        style.configure("PC.CompactPage.Treeview.Heading",
                        font=self.compact_page_font, padding=(3, 3))
        style.configure("PC.Compact.TButton", padding=(7, 3))
        style.configure(
            "PC.EditActive.TButton",
            padding=(7, 3),
            background="#ffd166",
            foreground=colors["text"],
        )
        style.map(
            "PC.EditActive.TButton",
            background=[("active", "#f3c451"), ("pressed", "#eab843")],
        )
        style.configure("PC.Tool.TButton", padding=(4, 2))
        style.configure("PC.PageNav.TButton", padding=(0, 0))
        style.configure("PC.SimplePage.TButton", padding=(0, 0))
        style.configure("PC.Footer.TButton", padding=(7, 3))
        style.configure(
            "PC.Footer.TCheckbutton",
            background=colors["footer"],
            foreground=colors["text"],
            padding=(5, 2),
        )
        style.map(
            "PC.Footer.TCheckbutton",
            background=[("active", colors["footer"])],
            foreground=[("disabled", colors["muted"]), ("!disabled", colors["text"])],
        )
        style.configure("PC.Compact.TEntry", padding=(4, 2))
        style.configure("PC.Footer.TEntry", padding=(4, 2))

        style.configure(
            "PC.Treeview",
            rowheight=26,
            borderwidth=0,
            relief="flat",
            background=base["surface"],
            fieldbackground=base["surface"],
            foreground=colors["text"],
        )
        style.configure(
            "PC.Treeview.Heading",
            padding=(3, 4),
            relief="solid",
            borderwidth=1,
            font=self.section_title_font,
        )
        style.map(
            "PC.Treeview",
            background=[("selected", colors["tree_selected"])],
            foreground=[("selected", colors["text"])],
        )

    def _sidebar_action_button(
        self, parent: tk.Misc, text: str, command, *, role: str = "neutral"
    ) -> tk.Widget:
        """Return one dense action button for the main sidebar.

        Neutral actions intentionally use the exact same ttk style as
        `检测版面参数`, so sections 四/五 share one native button chrome.
        Only the three explicitly emphasized actions use custom colors.
        """
        if role == "neutral":
            return ttk.Button(
                parent,
                text=text,
                command=command,
                style="PC.Compact.TButton",
            )

        colors = self._main_ui_colors
        palette = {
            "primary": (
                colors["primary"], colors["primary_hover"], "#ffffff",
            ),
            "success": (
                colors["success"], colors["success_hover"], "#ffffff",
            ),
        }
        background, active_background, foreground = palette.get(
            role, palette["primary"]
        )
        border = colors["button_border"]
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=active_background,
            activeforeground=foreground,
            relief="flat",
            bd=0,
            anchor="center",
            justify="center",
            highlightthickness=1,
            highlightbackground=border,
            highlightcolor=border,
            padx=7,
            pady=3,
            cursor="hand2",
        )

    def _footer_action_button(
        self, parent: tk.Misc, text: str, command, *, role: str
    ) -> tk.Button:
        """Create one emphasized bottom-bar action with a functional color."""
        colors = self._main_ui_colors
        palette = {
            # Scheme A: project/config entry points share the same green
            # treatment as `保存当前页`.
            "project": (colors["success"], colors["success_hover"], "#ffffff"),
            "config": (colors["success"], colors["success_hover"], "#ffffff"),
        }
        background, active_background, foreground = palette[role]
        border = colors["button_border"]
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=active_background,
            activeforeground=foreground,
            relief="flat",
            bd=0,
            anchor="center",
            justify="center",
            highlightthickness=1,
            highlightbackground=border,
            highlightcolor=border,
            padx=7,
            pady=3,
            cursor="hand2",
        )


    def _section_frame(
        self, parent: tk.Misc, title: str, padding: int = 5, *, section_key: str | None = None
    ) -> ttk.LabelFrame:
        """Create a clickable, collapsible left-sidebar section.

        The content widgets keep their normal ``grid`` geometry.  Collapsing uses
        ``grid_remove`` so all original row/column options are preserved and can
        be restored losslessly.
        """
        key = section_key or title
        expanded = bool(self.section_expanded.get(key, True))
        title_var = tk.StringVar(value=("▾ " if expanded else "▸ ") + title)
        label = ttk.Label(
            parent,
            textvariable=title_var,
            style="PC.SectionTitle.TLabel",
            cursor="hand2",
        )
        frame = ttk.LabelFrame(
            parent,
            labelwidget=label,
            padding=(padding, max(3, padding - 1), padding, padding),
            style="PC.Section.TLabelframe",
        )
        frame._collapse_key = key  # type: ignore[attr-defined]
        frame._collapse_title = title  # type: ignore[attr-defined]
        frame._collapse_title_var = title_var  # type: ignore[attr-defined]
        frame._collapse_label = label  # type: ignore[attr-defined]
        label.bind("<Button-1>", lambda _event, section=frame: self._toggle_section(section))
        self._collapsible_sections[key] = frame
        return frame

    def _set_section_expanded(self, section: ttk.LabelFrame, expanded: bool, *, persist: bool = True) -> None:
        key = str(getattr(section, "_collapse_key", ""))
        title = str(getattr(section, "_collapse_title", key))
        title_var = getattr(section, "_collapse_title_var", None)
        if isinstance(title_var, tk.StringVar):
            title_var.set(("▾ " if expanded else "▸ ") + title)

        # Every direct content child in the five sidebar groups is grid-managed.
        # Merely calling grid_remove() is not enough for a ttk.LabelFrame: Tk keeps
        # the old requested grid size cached, which leaves a large blank rectangle.
        # When collapsed we therefore disable grid propagation and pin the section
        # to the title-row height.  Expanding restores propagation before putting
        # the original grid slaves back, so their geometry options remain intact.
        label = getattr(section, "_collapse_label", None)
        if expanded:
            try:
                section.grid_propagate(True)
                section.configure(height=1)
            except tk.TclError:
                pass
            for child in section.winfo_children():
                if child.winfo_manager() == "":
                    try:
                        child.grid()
                    except tk.TclError:
                        pass
        else:
            for child in section.winfo_children():
                if child.winfo_manager() == "grid":
                    child.grid_remove()
            try:
                section.update_idletasks()
                title_height = int(label.winfo_reqheight()) if label is not None else 20
                # A small allowance keeps the LabelFrame border/padding visible
                # without retaining any of the former content height.
                section.grid_propagate(False)
                section.configure(height=max(26, title_height + 8))
            except tk.TclError:
                pass

        self.section_expanded[key] = bool(expanded)
        if key == "pages" and hasattr(self, "sidebar"):
            self.sidebar.rowconfigure(1, weight=1 if expanded else 0)
        if persist and hasattr(self, "page_range_var"):
            self._save_session_state()

    def _toggle_section(self, section: ttk.LabelFrame) -> None:
        key = str(getattr(section, "_collapse_key", ""))
        if self._preprocess_mode_active() and key not in {"preprocess", "pages"}:
            self.status_var.set("预处理模式中：主界面仅保留图片预处理、页面浏览和缩放。")
            return
        self._set_section_expanded(section, not bool(self.section_expanded.get(key, True)))

    def _apply_initial_section_states(self) -> None:
        for key, section in self._collapsible_sections.items():
            self._set_section_expanded(section, bool(self.section_expanded.get(key, True)), persist=False)

    def _apply_new_project_sidebar_defaults(self) -> None:
        """Apply the release workspace layout only to a newly created project."""
        defaults = {
            "preprocess": False,
            "normal": True,
            "aux": False,
            "ocr": False,
            "actions": False,
            "postproduction": False,
            "pages": True,
        }
        for key, expanded in defaults.items():
            self.section_expanded[key] = expanded
            section = self._collapsible_sections.get(key)
            if section is not None:
                self._set_section_expanded(section, expanded, persist=False)

    @staticmethod
    def _default_session_state_path() -> Path:
        return SessionController.default_state_path()

    def _read_session_state(self) -> dict:
        return self.session_controller.read_state()

    def _save_session_state(self) -> None:
        self.session_controller.save_state()

    def restore_last_session(self) -> None:
        self.session_controller.restore_last_session()

    def _restore_workspace_layout(self) -> None:
        """Apply the saved preset once the initial project image is ready."""
        if not getattr(self, "_restore_workspace_mode_pending", False):
            return
        self._restore_workspace_mode_pending = False
        from .ui.workspace_tools import set_sidebar_mode
        set_sidebar_mode(self, self.workspace_mode)


    def on_close(self) -> None:
        if getattr(self, "_batch_active", False):
            if not messagebox.askyesno(
                "批量任务正在运行",
                "当前批量任务尚未结束。是否停止任务并在当前页处理完成后退出？",
                parent=self,
            ):
                return
            self._batch_close_after_stop = True
            self._request_batch_stop()
            return

        # Durable one-shot workers must finish their success/error cleanup
        # boundary before the process can disappear.
        if self._ui_worker_close_wait:
            if not self._ui_close_requested:
                self._ui_close_requested = True
                for key in tuple(self._ui_worker_generations):
                    self._invalidate_ui_worker(key)
                self.status_var.set("正在完成后台文件操作，完成后自动退出…")
                try:
                    self.withdraw()
                except tk.TclError:
                    pass
                if self._ui_worker_poll_job is None:
                    self._ui_worker_poll_job = self.after(40, self._poll_ui_worker_queue)
            return

        try:
            self._cancel_system_appearance_poll()
            self._ui_worker_shutdown = True
            self._ui_close_requested = True
            for key in tuple(self._ui_worker_generations):
                self._invalidate_ui_worker(key)
            if self._ui_worker_poll_job is not None:
                try:
                    self.after_cancel(self._ui_worker_poll_job)
                except tk.TclError:
                    pass
                self._ui_worker_poll_job = None
            self._flush_deferred_page_save()
            if self.project and self.current_page and self.image is not None:
                try:
                    self.save_pdic(silent=True)
                    self._save_normalized_ppp()
                    self.settings.to_json(settings_path(self.project.root))
                except (OSError, ValueError, tk.TclError):
                    pass
            self._save_session_state()
        finally:
            self.destroy()

    def _build_ui(self) -> None:
        # Keep the legacy information bar permanently visible.  Pack it before
        # the expanding body so Windows DPI/window-size changes cannot push it
        # below the visible client area.  General messages and mouse coordinates
        # use separate variables so moving the mouse no longer overwrites an
        # operation result/error message.
        self.bottom_stack = ttk.Frame(self, style="PC.Status.TFrame")
        self.bottom_stack.pack(side="bottom", fill="x")

        # Batch task bar is normally hidden. It appears above the permanent
        # status bar while a multi-page operation is running.
        self.status_bar = ttk.Frame(self.bottom_stack, style="PC.Status.TFrame")
        self.status_bar.pack(side="bottom", fill="x")
        status_bar = self.status_bar
        ttk.Separator(status_bar, orient="horizontal").pack(side="top", fill="x")
        self.batch_bar = ttk.Frame(status_bar, padding=(4, 1), style="PC.Status.TFrame")
        self.batch_text_var = tk.StringVar(value="")
        self.batch_progress_var = tk.DoubleVar(value=0.0)
        ttk.Label(
            self.batch_bar, textvariable=self.batch_text_var, anchor="w", style="PC.Batch.TLabel"
        ).pack(side="left", padx=(0, 8))
        self.batch_progress = ttk.Progressbar(
            self.batch_bar, variable=self.batch_progress_var, maximum=100.0, length=160, mode="determinate"
        )
        self.batch_progress.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.batch_pause_button = ttk.Button(
            self.batch_bar, text="暂停", width=8, command=self._toggle_batch_pause,
            style="PC.Compact.TButton",
        )
        self.batch_pause_button.pack(side="left", padx=(0, 5))
        self._attach_tooltip(
            self.batch_pause_button,
            "暂停或继续当前批量任务；已完成页面不会回滚。",
        )
        self.batch_stop_button = ttk.Button(
            self.batch_bar, text="停止", width=8, command=self._request_batch_stop,
            style="PC.Compact.TButton",
        )
        self.batch_stop_button.pack(side="left")
        self._attach_tooltip(
            self.batch_stop_button,
            "请求停止当前批量任务；正在处理的页面完成后安全停止。",
        )

        ttk.Label(
            status_bar,
            textvariable=self.status_var,
            anchor="w",
            padding=(8, 4),
            style="PC.Status.TLabel",
        ).pack(side="left", fill="x", expand=True)
        ttk.Label(
            status_bar, textvariable=self.image_metadata_status_var,
            anchor="e", padding=(8, 4), style="PC.Status.TLabel",
        ).pack(side="right")
        ttk.Label(
            status_bar,
            textvariable=self.cursor_status_var,
            anchor="e",
            padding=(8, 4),
            style="PC.Status.TLabel",
        ).pack(side="right")
        ttk.Separator(status_bar, orient="vertical").pack(side="right", fill="y", padx=2)

        # v2.3 intentionally has no menu bar or separate top toolbar.
        body = ttk.Panedwindow(self, orient="horizontal")
        self.main_paned = body
        body.pack(fill="both", expand=True)
        sidebar_host = ttk.Frame(body, style="PC.Sidebar.TFrame")
        self.sidebar_canvas = tk.Canvas(
            sidebar_host,
            highlightthickness=0,
            borderwidth=0,
            bg=self._main_ui_colors["sidebar"],
        )
        # This outer scrollbar duplicated the functional page-list scrollbar
        # and appeared inert beside the normal-mode list. Keep a reference for
        # compatibility but do not display it. The Treeview owns scrolling.
        self.sidebar_scrollbar = ttk.Scrollbar(
            sidebar_host, orient="vertical", command=self.sidebar_canvas.yview
        )
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)
        sidebar = ttk.Frame(
            self.sidebar_canvas, padding=(7, 0, 6, 5), style="PC.Sidebar.TFrame"
        )
        self._sidebar_window = self.sidebar_canvas.create_window((0, 0), window=sidebar, anchor="nw")
        sidebar.bind("<Configure>", self._resize_sidebar_content)
        self.sidebar_canvas.bind("<Configure>", self._resize_sidebar_content)
        self.bind_all("<MouseWheel>", self._sidebar_mousewheel, add="+")
        self.bind_all("<Button-4>", lambda event: self._sidebar_linux_mousewheel(event, -1), add="+")
        self.bind_all("<Button-5>", lambda event: self._sidebar_linux_mousewheel(event, 1), add="+")
        self.sidebar = sidebar
        viewer = ttk.Frame(body)
        body.add(sidebar_host, weight=0)
        body.add(viewer, weight=1)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(1, weight=1)

        from .ui.workspace_tools import install_workspace_tools
        install_workspace_tools(self, sidebar, sidebar_host)

        page_panel = ttk.Frame(sidebar, padding=(2, 0, 2, 0), style="PC.Sidebar.TFrame")
        self.page_panel = page_panel
        page_panel.grid(row=0, column=0, rowspan=2, sticky="nsew")
        page_panel.columnconfigure(0, weight=1)
        page_panel.rowconfigure(2, weight=1)

        self.page_range_var = tk.StringVar(value="current")
        self.page_range_spec_var = tk.StringVar()
        self.view_zoom_var = tk.StringVar(value="100%")

        nav_area = ttk.Frame(page_panel, style="PC.SectionBody.TFrame")
        nav_area.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        range_row = ttk.Frame(nav_area)
        self.page_range_controls_row = range_row
        range_row.pack(fill="x", pady=(0, 3))
        for label, mode in (("当前", "current"), ("至末页", "to_end"),
                            ("至指定", "to_specified"), ("书签", "bookmarks")):
            ttk.Radiobutton(range_row, text=label, variable=self.page_range_var,
                            value=mode).pack(side="left", padx=(0, 1))
        spec_row = ttk.Frame(nav_area)
        spec_row.pack(fill="x", pady=(0, 4))
        ttk.Radiobutton(spec_row, text="", variable=self.page_range_var,
                        value="specified").pack(side="left")
        page_range_entry = ttk.Entry(spec_row, textvariable=self.page_range_spec_var, width=12)
        page_range_entry.pack(side="left", fill="x", expand=True, padx=(3, 4))
        page_range_entry.bind("<Return>", lambda _event: self.jump_to_page_spec())
        jump_button = ttk.Button(spec_row, text="跳", width=2,
                                 command=self.jump_to_page_spec, style="PC.PageNav.TButton")
        jump_button.pack(side="left")
        self._attach_tooltip(jump_button, "跳转到指定页面的第一个有效页面；ENTER为快捷键")

        nav_row = ttk.Frame(nav_area)
        nav_row.pack(fill="x")
        for symbol, command, tip in (
            ("⨇", lambda: self.jump_to_bookmark(-1), "跳转到上一书签"),
            ("⨈", lambda: self.jump_to_bookmark(1), "跳转到下一书签"),
            ("上页", lambda: self.change_page(-1), "切换到上页（Shift + 鼠标右键）"),
            ("下页", lambda: self.change_page(1), "切换到下页（鼠标右键）"),
        ):
            button = ttk.Button(nav_row, text=symbol, width=4 if len(symbol) == 1 else 5,
                                command=command, style="PC.PageNav.TButton")
            button.pack(side="left", padx=(0, 4))
            self._attach_tooltip(button, tip)
        # First-column previews are controlled directly below the 下页 row,
        # not by Settings Center.  The original table remains authoritative.
        thumbnail_controls_host = ttk.Frame(nav_area, style="PC.Sidebar.TFrame")
        thumbnail_controls_host.pack(fill="x")
        list_frame = ttk.Frame(page_panel)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1); list_frame.rowconfigure(0, weight=1)
        columns = ("bookmark", "page", "section", "lined", "fill_status", "illustrations")
        self.page_list = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=12,
            style="PC.Treeview",
        )
        self._page_list_heading_labels = {
            "bookmark": "●", "page": "页面", "section": "域",
            "lined": "线", "fill_status": "填充状态", "illustrations": "图",
        }
        self.page_list.heading("bookmark", text="●", anchor="center")
        self.page_list.heading("page", text="页面", anchor="center")
        self.page_list.heading("section", text="域", anchor="center")
        self.page_list.heading("lined", text="线", anchor="center")
        self.page_list.heading("fill_status", text="填充状态", anchor="center")
        self.page_list.heading("illustrations", text="图", anchor="center")
        self.page_list.heading("bookmark", command=lambda: self._sort_page_list("bookmark"))
        self.page_list.heading("page", command=lambda: self._sort_page_list("page"))
        self.page_list.heading("section", command=lambda: self._sort_page_list("section"))
        self.page_list.heading("lined", command=lambda: self._sort_page_list("lined"))
        self.page_list.heading("fill_status", command=lambda: self._sort_page_list("fill_status"))
        self.page_list.heading("illustrations", command=lambda: self._sort_page_list("illustrations"))
        self.page_list.column("bookmark", width=44, anchor="center", stretch=False)
        self.page_list.column("page", width=180, anchor="center", stretch=False)
        self.page_list.column("section", width=64, anchor="center", stretch=False)
        self.page_list.column("lined", width=68, anchor="center", stretch=False)
        self.page_list.column("fill_status", width=110, anchor="center", stretch=False)
        self.page_list.column("illustrations", width=58, anchor="center", stretch=False)
        self.page_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self._page_list_scroll)
        page_hscroll = ttk.Scrollbar(list_frame, orient="horizontal", command=self._page_list_hscroll)
        self.page_list.configure(yscrollcommand=self._page_list_yscroll,
                                 xscrollcommand=page_hscroll.set)
        self.page_list.grid(row=0, column=0, sticky="nsew")
        self._page_index_grid = PageListGrid(self.page_list)
        page_hscroll.grid(row=1, column=0, sticky="ew")
        self.page_scroll.grid(row=0, column=1, sticky="ns")
        self.page_list.bind("<<TreeviewSelect>>", self.on_page_select)
        self.page_list.bind("<Button-1>", self._page_list_bookmark_click, add="+")
        self.page_list.bind("<Double-1>", self._page_list_section_double_click, add="+")
        self.page_list.bind("<MouseWheel>", self._list_mousewheel)
        bind_context_menu(self.page_list, self._page_list_right_click)
        self.page_list.bind("<Configure>", self._page_list_configured)
        self.page_list.bind("<Motion>", self._page_list_section_heading_motion, add="+")
        self.page_list.bind("<Leave>", self._hide_page_list_section_heading_hint, add="+")
        self._page_column_vars = {
            "lined": tk.BooleanVar(value=bool(getattr(self.settings, "page_list_show_lined", True))),
            "fill_status": tk.BooleanVar(value=bool(getattr(self.settings, "page_list_show_fill_status", False))),
            "illustrations": tk.BooleanVar(value=bool(getattr(self.settings, "page_list_show_illustrations", True))),
        }
        self._apply_page_list_display_columns(save=False)
        self._page_thumbnails = PageThumbnailController(
            self, self.page_list, thumbnail_controls_host,
        )

        self.canvas = tk.Canvas(
            viewer, bg=self._main_ui_colors["canvas"], highlightthickness=0
        )
        hbar = ttk.Scrollbar(viewer, orient="horizontal", command=self.canvas.xview)
        vbar = ttk.Scrollbar(viewer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        # The ≣ launcher now lives beside 普/O/校 in the workspace rail.
        # Keep the actual zoom tools on the image canvas as an on-demand
        # overlay, rather than showing a second permanent/hover-only icon.
        size_row = ttk.Frame(self.canvas, padding=(3, 2), style="PC.Sidebar.TFrame")
        self.page_size_row = size_row
        zoom_tools = ttk.Frame(size_row, style="PC.Sidebar.TFrame")
        self.page_zoom_tools = zoom_tools
        zoom_tools.pack(side="left")
        for symbol, command, tip in (
            ("−", lambda: self.zoom(0.87), "缩小显示"),
            ("+", lambda: self.zoom(1.15), "放大显示"),
            ("⇔", self.fit_page_width, "占满宽度"),
            ("◧", self.fit_single_column_width, "单栏占满宽度"),
            ("⇕", self.fit_page_height, "占满高度"),
        ):
            if symbol == "+":
                view_zoom_entry = ttk.Entry(
                    zoom_tools, textvariable=self.view_zoom_var, width=6,
                    justify="center", style="PC.Compact.TEntry",
                )
                view_zoom_entry.pack(side="left", padx=2)
                view_zoom_entry.bind("<Return>", self.apply_view_zoom_text)
                view_zoom_entry.bind("<FocusOut>", self.apply_view_zoom_text)
            button = ttk.Button(
                zoom_tools, text=symbol, width=3, command=command,
                style="PC.Tool.TButton",
            )
            button.pack(side="left", padx=(0, 3))
            self._attach_tooltip(button, tip)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns"); hbar.grid(row=1, column=0, sticky="ew")
        viewer.rowconfigure(0, weight=1); viewer.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self.canvas_left_click)
        # Explicit modifier binding keeps the new auxiliary gesture discoverable;
        # section and PPP editing retain their existing Shift-click behavior.
        self.canvas.bind("<Shift-Button-1>", self.canvas_left_click)
        self.canvas.bind("<Control-z>", lambda e: self.ref_box_controller.undo(e) if self.ref_box_controller.editing else self._auxiliary_controller.undo(e))
        self.canvas.bind("<Control-y>", lambda e: self.ref_box_controller.redo(e) if self.ref_box_controller.editing else None)
        self.canvas.bind("<F2>", lambda e: self.ref_box_controller.edit_properties() if self.ref_box_controller.editing else None)
        self.canvas.bind("<Escape>", self.ref_box_controller.cancel_capture)
        self.canvas.bind("<Double-Button-1>", self.canvas_left_double_click)
        self.canvas.bind("<B1-Motion>", self.canvas_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_left_release)
        bind_context_menu(self.canvas, self.canvas_right_click)
        self.canvas.bind("<Shift-Button-3>", lambda event: self._canvas_shift_right_click(event))
        self.canvas.bind("<Motion>", self.canvas_motion)
        self.canvas.bind("<Leave>", self.canvas_leave)
        self.canvas.bind("<MouseWheel>", self.canvas_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self.canvas_shift_mousewheel)
        self.canvas.bind("<Control-MouseWheel>", self.canvas_ctrl_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas_linux_mousewheel(e, -1))
        self.canvas.bind("<Button-5>", lambda e: self.canvas_linux_mousewheel(e, 1))

        # Apply persisted collapse states only after all section children exist.
        self._apply_initial_section_states()

    def _pointer_over_sidebar(self) -> bool:
        canvas = self.__dict__.get("sidebar_canvas")
        if canvas is None:
            return False
        try:
            x = canvas.winfo_pointerx() - canvas.winfo_rootx()
            y = canvas.winfo_pointery() - canvas.winfo_rooty()
            return 0 <= x < canvas.winfo_width() and 0 <= y < canvas.winfo_height()
        except tk.TclError:
            return False

    def _resize_sidebar_content(self, event: tk.Event | None = None) -> None:
        return _page_index._resize_sidebar_content(self, _page_index_deps(), event)

    def _sidebar_mousewheel(self, event: tk.Event) -> str | None:
        if not self._pointer_over_sidebar():
            return None
        delta = int(getattr(event, "delta", 0) or 0)
        if delta:
            self.sidebar_canvas.yview_scroll((-1 if delta > 0 else 1) * 3, "units")
            return "break"
        return None

    def _sidebar_linux_mousewheel(self, _event: tk.Event, direction: int) -> str | None:
        if not self._pointer_over_sidebar():
            return None
        self.sidebar_canvas.yview_scroll(direction * 3, "units")
        return "break"

    def _apply_page_list_display_columns(self, *, save: bool = True) -> None:
        return _page_index._apply_page_list_display_columns(self, _page_index_deps(), save=save)

    def _page_list_configured(self, _event=None) -> None:
        return _page_index._page_list_configured(self, _page_index_deps(), _event)

    def _fit_page_list_columns(self) -> None:
        return _page_index._fit_page_list_columns(self, _page_index_deps())

    def _hide_page_list_section_heading_hint(self, _event=None) -> None:
        return _page_index._hide_page_list_section_heading_hint(self, _page_index_deps())

    def _page_list_section_heading_motion(self, event: tk.Event) -> None:
        return _page_index._page_list_section_heading_motion(self, _page_index_deps(), event)

    def _page_list_right_click(self, event: tk.Event) -> str | None:
        return _page_index._page_list_right_click(self, _page_index_deps(), event)

    def _schedule_page_cell_overlay_refresh(self) -> None:
        return _page_index._schedule_page_cell_overlay_refresh(self, _page_index_deps())

    def _list_mousewheel(self, event: tk.Event) -> str:
        self.page_list.yview_scroll((-1 if event.delta > 0 else 1) * 3, "units")
        self._schedule_page_cell_overlay_refresh()
        return "break"

    def _page_list_scroll(self, *args) -> None:
        return _page_index._page_list_scroll(self, _page_index_deps(), *args)

    def _page_list_hscroll(self, *args) -> None:
        return _page_index._page_list_hscroll(self, _page_index_deps(), *args)

    def _page_list_yscroll(self, first: str, last: str) -> None:
        return _page_index._page_list_yscroll(self, _page_index_deps(), first, last)

    def _update_page_list_sort_headings(self) -> None:
        return _page_index._update_page_list_sort_headings(self, _page_index_deps())

    def _apply_page_list_sort(self, *, ensure_current_visible: bool = False) -> None:
        return _page_index._apply_page_list_sort(self, _page_index_deps(), ensure_current_visible=ensure_current_visible)

    def _schedule_page_list_resort(self) -> None:
        return _page_index._schedule_page_list_resort(self, _page_index_deps())

    def _sort_page_list(self, column: str) -> None:
        return _page_index._sort_page_list(self, _page_index_deps(), column)

    def _page_list_column_at(self, x: int) -> str | None:
        return _page_index._page_list_column_at(self, _page_index_deps(), x)

    def _page_section_count_text(self, index: int) -> str:
        return _page_index._page_section_count_text(self, _page_index_deps(), index)

    def _set_page_section_count(self, index: int, count: int) -> None:
        return _page_index._set_page_section_count(self, _page_index_deps(), index, count)

    def _edit_page_section_index(self, index: int) -> None:
        return _page_index._edit_page_section_index(self, _page_index_deps(), index)

    def toggle_current_page_section_editing(self) -> None:
        return _page_index.toggle_current_page_section_editing(self, _page_index_deps())

    def _page_list_section_double_click(self, event: tk.Event) -> str | None:
        return _page_index._page_list_section_double_click(self, _page_index_deps(), event)

    def _bookmark_stems(self) -> set[str]:
        return _page_index._bookmark_stems(self, _page_index_deps())

    def _page_list_bookmark_click(self, event: tk.Event) -> str | None:
        return _page_index._page_list_bookmark_click(self, _page_index_deps(), event)

    def jump_to_bookmark(self, direction: int) -> None:
        return _page_index.jump_to_bookmark(self, _page_index_deps(), direction)

    def _center_page_list_iid(self, iid: str) -> None:
        return _page_index._center_page_list_iid(self, _page_index_deps(), iid)

    def _set_page_list_selection(self, index: int, *, ensure_visible: bool = True) -> None:
        return _page_index._set_page_list_selection(self, _page_index_deps(), index, ensure_visible=ensure_visible)

    def _select_page_from_lined_overlay(self, index: int) -> None:
        if not self.project or not (0 <= index < len(self.project.images)):
            return
        # Overlay labels sit above Treeview cells, so navigate directly instead
        # of synthesizing a delayed TreeviewSelect event.
        if index != self.current_index:
            self._request_page_load(index)
        else:
            self._set_page_list_selection(index, ensure_visible=True)

    def _clear_lined_cell_overlays(self) -> None:
        return _page_index._clear_lined_cell_overlays(self, _page_index_deps())

    def _visible_page_list_iids(self) -> list[str]:
        return _page_index._visible_page_list_iids(self, _page_index_deps())

    def _refresh_lined_cell_overlays(self) -> None:
        return _page_index._refresh_lined_cell_overlays(self, _page_index_deps())

    def _word_fill_status_path(self) -> Path | None:
        return _word_fill_status._word_fill_status_path(self, _word_fill_status_deps())

    def _load_word_fill_status(self) -> None:
        return _word_fill_status._load_word_fill_status(self, _word_fill_status_deps())

    def _persist_word_fill_status(self) -> None:
        return _word_fill_status._persist_word_fill_status(self, _word_fill_status_deps())

    def _word_fill_status_text(self, index: int) -> str:
        return _word_fill_status._word_fill_status_text(self, _word_fill_status_deps(), index)

    def _record_word_fill_check(
        self, index: int, line_count: int, word_count: int, *, source: str = "",
        has_data: bool = True, persist: bool = False, refresh_overlay: bool = True,
        refresh_row: bool = True,
    ) -> None:
        return _word_fill_status._record_word_fill_check(self, _word_fill_status_deps(), index, line_count, word_count, source=source, has_data=has_data, persist=persist, refresh_overlay=refresh_overlay, refresh_row=refresh_row)

    def _refresh_word_fill_check_from_line_count(
        self, index: int, line_count: int, *, persist: bool = False,
    ) -> None:
        return _word_fill_status._refresh_word_fill_check_from_line_count(self, _word_fill_status_deps(), index, line_count, persist=persist)

    def _clear_word_fill_checks_for_indices(self, indices, *, persist: bool = False) -> None:
        return _word_fill_status._clear_word_fill_checks_for_indices(self, _word_fill_status_deps(), indices, persist=persist)

    def _preprocess_mode_active(self) -> bool:
        return _preprocess_ui._preprocess_mode_active(self, _preprocess_ui_deps())

    def _preprocess_config(self) -> tuple[int, bool, str]:
        return _preprocess_ui._preprocess_config(self, _preprocess_ui_deps())

    def _preprocess_export_config(
        self,
    ) -> tuple[bool, str, int, int, int, int, int, int, str, str]:
        return _preprocess_ui._preprocess_export_config(self, _preprocess_ui_deps())

    def _preprocess_export_settings_changed(self, _event=None) -> None:
        return _preprocess_ui._preprocess_export_settings_changed(self, _preprocess_ui_deps(), _event)

    def _preprocess_settings_changed(self, _event=None) -> None:
        return _preprocess_ui._preprocess_settings_changed(self, _preprocess_ui_deps(), _event)

    def _set_workspace_preprocess_locked(self, locked: bool) -> None:
        """Disable ordinary-edit controls while preserving page navigation."""
        return _preprocess_ui._set_workspace_preprocess_locked(self, _preprocess_ui_deps(), locked)

    def _preprocess_blocking_window_name(self) -> str | None:
        return _preprocess_ui._preprocess_blocking_window_name(self, _preprocess_ui_deps())

    def toggle_preprocess_mode(self) -> None:
        return _preprocess_ui.toggle_preprocess_mode(self, _preprocess_ui_deps())

    def _set_preprocess_mode(self, active: bool, *, analyze: bool = True) -> None:
        return _preprocess_ui._set_preprocess_mode(self, _preprocess_ui_deps(), active, analyze=analyze)

    @staticmethod
    def _default_preprocess_corner_quad(image: Image.Image) -> tuple[float, ...]:
        return _preprocess_ui._default_preprocess_corner_quad(_preprocess_ui_deps(), image)

    def edit_preprocess_corners(self) -> None:
        return _preprocess_ui.edit_preprocess_corners(self, _preprocess_ui_deps())

    def reset_preprocess_corners(self) -> None:
        return _preprocess_ui.reset_preprocess_corners(self, _preprocess_ui_deps())

    def _preprocess_result_for_page(self, index: int) -> PreprocessAnalysis | None:
        return _preprocess_ui._preprocess_result_for_page(self, _preprocess_ui_deps(), index)

    def _set_current_preprocess_status(self, analysis: PreprocessAnalysis | None) -> None:
        return _preprocess_ui._set_current_preprocess_status(self, _preprocess_ui_deps(), analysis)

    def analyze_preprocess_current(self, *, silent: bool = False) -> None:
        return _preprocess_ui.analyze_preprocess_current(self, _preprocess_ui_deps(), silent=silent)

    def analyze_preprocess_selected(self) -> None:
        return _preprocess_ui.analyze_preprocess_selected(self, _preprocess_ui_deps())

    def show_preprocess_diagnostics(self) -> None:
        """Show the current page's detailed preprocessing diagnostics on demand."""
        return _preprocess_ui.show_preprocess_diagnostics(self, _preprocess_ui_deps())

    def promote_preprocessed_working_images(self) -> None:
        """Replace root working scans with the verified processed export set."""
        return _preprocess_ui.promote_preprocessed_working_images(self, _preprocess_ui_deps())

    def jump_preprocess_review(self, delta: int) -> None:
        return _preprocess_ui.jump_preprocess_review(self, _preprocess_ui_deps(), delta)

    def _preprocess_analysis_for_export(
        self, project: ProjectState, page: Path, settings: AppSettings,
        safety: float, auto_deskew: bool, geometry_mode: str,
    ) -> PreprocessAnalysis:
        return _preprocess_ui._preprocess_analysis_for_export(self, _preprocess_ui_deps(), project, page, settings, safety, auto_deskew, geometry_mode)

    def export_preprocess_previews(self) -> None:
        return _preprocess_ui.export_preprocess_previews(self, _preprocess_ui_deps())

    def export_preprocess_images(self) -> None:
        return _preprocess_ui.export_preprocess_images(self, _preprocess_ui_deps())

    def _get_preprocess_display_photo(
        self, size: tuple[int, int], analysis: PreprocessAnalysis | None,
    ) -> ImageTk.PhotoImage:
        return _preprocess_ui._get_preprocess_display_photo(self, _preprocess_ui_deps(), size, analysis)

    def _redraw_preprocess_preview(self, size: tuple[int, int]) -> None:
        return _preprocess_ui._redraw_preprocess_preview(self, _preprocess_ui_deps(), size)

    @staticmethod
    def _style_color_button(button: tk.Button, color: str) -> None:
        color = str(color or "#ff0000")
        try:
            button.configure(bg=color, activebackground=color, text="")
        except tk.TclError:
            button.configure(text=color)

    def choose_overlay_color(self, setting_name: str, button: tk.Button) -> None:
        current = str(getattr(self.settings, setting_name, "#ff0000"))
        _rgb, chosen = colorchooser.askcolor(color=current, parent=self, title="选择颜色")
        if not chosen:
            return
        chosen = str(chosen).lower()
        if hasattr(self, "quick_color_vars") and setting_name in self.quick_color_vars:
            self.quick_color_vars[setting_name].set(chosen)
        setattr(self.settings, setting_name, chosen)
        self._style_color_button(button, chosen)
        self._quick_parameter_changed(immediate=True)

    def _quick_percent_parameter_changed(self, name: str) -> None:
        if not getattr(self, "_quick_trace_ready", False):
            return
        if getattr(self, "_quick_syncing", False):
            return
        self._quick_geometry_edit_source[name] = "percent"
        try:
            percent = float(self.quick_vars[name].get().strip().rstrip("%"))
            if self.image is not None and 0.0 <= percent <= 100.0:
                pixels = _layout_percent_to_pixels(self.image, name, percent)
                self._quick_syncing = True
                try:
                    self.quick_pixel_vars[name].set(str(int(pixels)))
                finally:
                    self._quick_syncing = False
        except (KeyError, TypeError, ValueError):
            pass
        self._quick_parameter_changed()

    def _quick_pixel_parameter_changed(self, name: str) -> None:
        if not getattr(self, "_quick_trace_ready", False):
            return
        if getattr(self, "_quick_syncing", False):
            return
        self._quick_geometry_edit_source[name] = "pixel"
        try:
            pixels = int(round(float(self.quick_pixel_vars[name].get().strip())))
            if pixels >= 0 and self.image is not None:
                percent = _layout_pixels_to_percent(self.image, name, pixels)
                self._quick_syncing = True
                try:
                    self.quick_vars[name].set(_format_layout_percent(percent))
                finally:
                    self._quick_syncing = False
        except (KeyError, TypeError, ValueError):
            pass
        self._quick_parameter_changed()

    def _quick_parameter_changed(self, *_args, immediate: bool = False) -> None:
        if not getattr(self, "_quick_trace_ready", False):
            return
        if getattr(self, "_quick_syncing", False):
            return
        if self._quick_autosave_job is not None:
            try:
                self.after_cancel(self._quick_autosave_job)
            except tk.TclError:
                pass
            self._quick_autosave_job = None
        delay = 1 if immediate else 450
        self._quick_autosave_job = self.after(delay, self._run_quick_autosave)

    def _apply_overlay_visibility_toggle(self, setting_name: str, variable: tk.BooleanVar) -> None:
        """ apply overlay visibility toggle."""
        setattr(self.settings, setting_name, bool(variable.get()))
        if setting_name == "show_rulers" and not bool(variable.get()):
            self._hide_ruler_hint()
        self._quick_parameter_changed(immediate=True)
        self.redraw()

    def _run_quick_autosave(self) -> None:
        self._quick_autosave_job = None
        # While the user is halfway through typing a numeric value, validation
        # can fail temporarily. Silent live-save simply waits for the next edit;
        # the explicit 保存参数 button still reports an error immediately.
        self.apply_quick_settings(show_status=False, persist=True, silent_errors=True)

    def _quick_geometry_value(self, name: str) -> int:
        """Return one main-panel layout value in the public coordinate contract."""
        raw = int(getattr(self.settings, name, 0) or 0)
        if self.image is None:
            return raw
        horizontal = not str(
            getattr(self.settings, "layout_writing_mode", "horizontal-tb") or "horizontal-tb"
        ).startswith("vertical")
        if horizontal and name == "start_y" and str(
            getattr(self.settings, "profile_header_mode", "auto") or "auto"
        ) == "present":
            return round(
                self.image.height
                * float(getattr(self.settings, "profile_header_percent", 0.0) or 0.0)
                / 100.0
            )
        if horizontal and name == "bottom_y" and str(
            getattr(self.settings, "profile_footer_mode", "auto") or "auto"
        ) == "present":
            return round(
                self.image.height
                * (
                    1.0
                    - float(getattr(self.settings, "profile_footer_percent", 0.0) or 0.0)
                    / 100.0
                )
            )
        return raw

    def _refresh_quick_coordinate_labels(self) -> None:
        if not hasattr(self, "quick_field_labels"):
            return
        labels = {
            "start_y": "正文起始Y：",
            "manual_x": "首栏X：",
        }
        for name, label in labels.items():
            widget = self.quick_field_labels.get(name)
            if widget is not None:
                widget.configure(text=label)

    def sync_quick_settings(self) -> None:
        if not hasattr(self, "quick_vars"):
            return
        self._quick_syncing = True
        try:
            self._refresh_quick_coordinate_labels()
            for name, var in self.quick_vars.items():
                if hasattr(self.settings, name):
                    value = getattr(self.settings, name)
                    if name in LAYOUT_PERCENT_AXES:
                        source_value = self._quick_geometry_value(name)
                        if self.image is not None:
                            value = _format_layout_percent(
                                _layout_pixels_to_percent(self.image, name, source_value)
                            )
                        else:
                            value = source_value
                        pixel_var = getattr(self, "quick_pixel_vars", {}).get(name)
                        if pixel_var is not None:
                            pixel_var.set(str(int(round(source_value))))
                    if name == "main_entry_x_ratio":
                        value = round(float(value) * 100)
                    elif name in {
                        "batch_interval", "guide_opacity", "headword_marker_opacity",
                        "illustration_fill_opacity",
                    }:
                        value = round(float(value))
                    if name in {
                        "main_entry_font_family",
                        "illustration_label_font_family",
                        "review_entry_font_family",
                        "review_simplified_font_family",
                    }:
                        value = normalize_content_font_setting(value)
                    var.set(str(value))
            for name, var in getattr(self, "quick_bool_vars", {}).items():
                if hasattr(self.settings, name):
                    var.set(bool(getattr(self.settings, name)))
            for name, var in getattr(self, "quick_color_vars", {}).items():
                if hasattr(self.settings, name):
                    value = str(getattr(self.settings, name))
                    var.set(value)
                    button = getattr(self, "quick_color_buttons", {}).get(name)
                    if button is not None:
                        self._style_color_button(button, value)
            if hasattr(self, "lens_mode_var"):
                self.lens_mode_var.set(
                    LENS_MODE_LABELS.get(
                        self.settings.paddle_lens_mode, LENS_MODE_LABELS["off"]
                    )
                )
            self._quick_geometry_edit_source.clear()
        finally:
            self._quick_syncing = False

    def apply_quick_settings(self, show_status: bool = True, persist: bool = False, silent_errors: bool = False) -> bool:
        if getattr(self, "_batch_active", False):
            self.status_var.set("批量任务运行中，参数修改将在任务结束后再进行。")
            return False
        try:
            previous_ocr_language = str(getattr(self.settings, "ocr_language", "") or "")
            original_geometry = {
                name: self._quick_geometry_value(name)
                for name in LAYOUT_PERCENT_AXES
                if name in self.quick_vars
            }
            for name, var in self.quick_vars.items():
                geometry_source = self._quick_geometry_edit_source.get(name, "percent")
                if (
                    name in original_geometry
                    and geometry_source == "pixel"
                    and name in getattr(self, "quick_pixel_vars", {})
                ):
                    value = int(round(float(self.quick_pixel_vars[name].get().strip())))
                else:
                    value = self.quick_field_casts[name](var.get())
                if name in original_geometry:
                    if (
                        geometry_source != "pixel"
                        and self.image is not None
                        and name in LAYOUT_PERCENT_AXES
                    ):
                        percent = float(value)
                        if not 0.0 <= percent <= 100.0:
                            raise ValueError(f"{name} 必须在 0–100% 之间。")
                        value = _layout_percent_to_pixels(self.image, name, percent)
                    else:
                        value = int(value)
                    if value < 0:
                        raise ValueError(f"{name} 不能小于 0。")
                    changed = value != original_geometry[name]
                    horizontal = not str(
                        getattr(self.settings, "layout_writing_mode", "horizontal-tb") or "horizontal-tb"
                    ).startswith("vertical")
                    if self.image is not None and horizontal and name == "start_y" and str(
                        getattr(self.settings, "profile_header_mode", "auto") or "auto"
                    ) == "present":
                        if value > self.image.height:
                            raise ValueError(f"页眉Y必须在原图 0–{self.image.height} 之间。")
                        if changed:
                            percent = value * 100.0 / max(1, self.image.height)
                            if percent > 35.0:
                                raise ValueError("页眉不能超过原图高度的 35%。")
                            self.settings.profile_header_percent = round(percent, 6)
                    elif self.image is not None and horizontal and name == "bottom_y" and str(
                        getattr(self.settings, "profile_footer_mode", "auto") or "auto"
                    ) == "present":
                        if value > self.image.height:
                            raise ValueError(f"页尾Y必须在原图 0–{self.image.height} 之间。")
                        if changed:
                            percent = (
                                (self.image.height - value)
                                * 100.0
                                / max(1, self.image.height)
                            )
                            if not 0.0 <= percent <= 35.0:
                                raise ValueError("页尾必须位于原图底部 35% 范围内。")
                            self.settings.profile_footer_percent = round(percent, 6)
                    value = int(value)
                if name == "paddle_band_width_ratio" and not 1.0 <= float(value) <= 100.0:
                    raise ValueError("候选带宽比例必须在 1–100 之间；100 即原候选带宽。")
                if name == "paddle_separator_safety_px" and not 0 <= int(value) <= 50:
                    raise ValueError("Y精修安全空间必须在 0–50 px 之间。")
                if name == "paddle_separator_roi_width_ratio" and not 10.0 <= float(value) <= 100.0:
                    raise ValueError("Y精修横向分析范围必须在 10–100% 之间。")
                if name == "right_ratio" and not 1 <= float(value) <= 100:
                    raise ValueError("向右比例必须在 1–100% 之间。")
                if name == "main_entry_x_ratio":
                    if not 0 <= float(value) <= 125:
                        raise ValueError("词条文本框偏移必须在 0–125% 之间。")
                    value = float(value) / 100.0
                if name in {"illustration_outline_width", "illustration_label_border_width", "page_section_width"} and not 1 <= int(value) <= 20:
                    raise ValueError("线条/外框粗细必须在 1–20 之间。")
                if name == "illustration_label_font_size" and not 5 <= int(value) <= 200:
                    raise ValueError("插图标签字号必须在 5–200 之间。")
                if name == "crop_preview_font_size" and not 5 <= int(value) <= 200:
                    raise ValueError("切图预览标签字号必须在 5–200 之间。")
                setattr(self.settings, name, value)
            for font_setting_name in (
                "main_entry_font_family",
                "illustration_label_font_family",
                "crop_preview_font_family",
                "review_entry_font_family",
                "review_simplified_font_family",
            ):
                setattr(
                    self.settings,
                    font_setting_name,
                    normalize_content_font_setting(getattr(self.settings, font_setting_name, "")),
                )
            current_ocr_language = str(getattr(self.settings, "ocr_language", "") or "")
            if current_ocr_language != previous_ocr_language:
                for setting_name, setting_value in language_effective_settings(
                    current_ocr_language, self.settings.layout_writing_mode,
                ).items():
                    if hasattr(self.settings, setting_name):
                        setattr(self.settings, setting_name, setting_value)
            # Lens always follows the active headword OCR language, including
            # old projects that still carry a historical independent value.
            self.settings.paddle_lens_language = current_ocr_language
            # Diagnostic view flags live only in the UI; never attempt to
            # persist an ad-hoc BooleanVar onto the slotted AppSettings model.
            for name, var in self.quick_bool_vars.items():
                if hasattr(self.settings, name):
                    setattr(self.settings, name, bool(var.get()))
            for name, var in getattr(self, "quick_color_vars", {}).items():
                value = str(var.get()).strip()
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                    raise ValueError(f"{name} 不是有效的 #RRGGBB 颜色")
                setattr(self.settings, name, value.lower())
            if not (self.settings.paddle_use_paddleocr or self.settings.paddle_compare_tesseract or self.settings.paddle_enable_lens):
                raise ValueError("OCR引擎至少需要勾选一个。")
            self.settings.paddle_lens_mode = LENS_MODE_VALUES.get(self.lens_mode_var.get(), self.settings.paddle_lens_mode)
            self.settings.hide_overlays = bool(self.hide_var.get())
            self.settings.polygon_mode = bool(self.polygon_var.get())
            if persist: self.save_settings()
            self.sync_quick_settings()
            self.redraw()
            if self.autosave_var.get(): self.toggle_autosave()
            if show_status: self.status_var.set("主界面参数已应用" + ("并保存" if persist else ""))
            return True
        except Exception as exc:
            if not silent_errors:
                self.show_error("参数无效", exc)
            return False

    def save_main_parameters(self) -> None:
        self.apply_quick_settings(persist=True)

    def _save_current_page_files(self, *, sync_editors: bool = True) -> tuple[Path, Path] | None:
        """Persist all editable artifacts for the currently displayed page.

        Page navigation must commit both the visible headword editors (.pdic)
        and illustration polygons (.ppp) before another page replaces them.
        """
        if not self.project or not self.current_page or self.image is None:
            return None
        self.save_pdic(silent=True, sync_editors=sync_editors)
        ppp = self._ppp_write_path(self.current_page)
        self._save_normalized_ppp()
        self._update_page_row(self.current_index)
        return pdic_path(self.current_page), ppp

    def _save_current_page_by_mode(self, *, sync_editors: bool = True) -> Path | None:
        """ save current page by mode."""
        if not self.project or not self.current_page or self.image is None:
            return None
        if self.__dict__.get("_batch_active", False) and not self._can_save_current_during_batch_navigation():
            self.status_var.set("后台任务运行中：当前页只读，避免覆盖处理结果。")
            return None
        from .illustration.profile import effective_page_kind
        if effective_page_kind(self.settings, self.current_page) == "illustrated":
            return None
        if self.polygon_draw_var.get() and not getattr(self, "_batch_allow_pdic_edits", False):
            target = self._ppp_write_path(self.current_page)
            self._save_normalized_ppp()
            self._update_page_row(self.current_index)
            return target
        self.save_pdic(silent=True, sync_editors=sync_editors)
        return pdic_path(self.current_page)

    def save_current_page(self) -> None:
        if not self.guard():
            return
        try:
            saved = self._save_current_page_by_mode()
            if saved is not None:
                mode = "插图" if self.polygon_draw_var.get() else "画线"
                self.status_var.set(f"已保存当前页（{mode}）：{saved.name}")
        except Exception as exc:
            self.show_error("保存当前页失败", exc)

    def export_training_package(self) -> None:
        self._export_controller_for_call().export_training_package()

    def show_help_dialog(self) -> None:
        existing = self.__dict__.get("_usage_guide_window")
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_force()
                    existing._refresh_context()
                    return
            except tk.TclError:
                pass
        window = UsageGuideWindow(self)
        self._usage_guide_window = window
        window.bind(
            "<Destroy>",
            lambda event, w=window: self.__dict__.pop("_usage_guide_window", None)
            if event.widget is w else None,
            add="+",
        )

    @staticmethod
    def _distribution_version(name: str) -> str | None:
        try:
            return importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            return None
        except Exception:
            return None

    @staticmethod
    def _version_at_least(version: str | None, minimum: tuple[int, ...]) -> bool:
        if not version:
            return False
        parts = [int(value) for value in re.findall(r"\d+", version)]
        if not parts:
            return False
        width = max(len(parts), len(minimum))
        return tuple(parts + [0] * (width - len(parts))) >= tuple(minimum) + (0,) * (width - len(minimum))

    def _paddle_environment_text(self, settings: AppSettings | None = None) -> str:
        settings = settings or self.settings
        paddleocr_version = self._distribution_version("paddleocr")
        paddlex_version = self._distribution_version("paddlex")
        paddle_gpu_version = self._distribution_version("paddlepaddle-gpu")
        paddle_cpu_version = self._distribution_version("paddlepaddle")
        paddle_available = importlib_util.find_spec("paddleocr") is not None

        if paddleocr_version:
            lines = [f"✓ PaddleOCR {paddleocr_version}"]
        elif paddle_available:
            lines = ["✓ PaddleOCR：已安装（版本未知）"]
        else:
            return "✗ PaddleOCR：未安装\nPP-OCRv6：不可用（需要 PaddleOCR >= 3.7）\nWindows 推荐运行 install_ocr_windows.bat 安装 CPU/GPU OCR 套件。"

        if paddlex_version:
            lines.append(f"✓ PaddleX {paddlex_version}")

        if paddle_gpu_version and paddle_cpu_version:
            lines.append(f"⚠ PaddlePaddle GPU {paddle_gpu_version} + CPU {paddle_cpu_version} 同时安装")
            lines.append("建议仅保留实际使用的一个 PaddlePaddle runtime，避免 CPU/GPU 包冲突。")
        elif paddle_gpu_version:
            lines.append(f"✓ PaddlePaddle GPU {paddle_gpu_version}")
        elif paddle_cpu_version:
            lines.append(f"✓ PaddlePaddle CPU {paddle_cpu_version}")
        else:
            lines.append("✗ PaddlePaddle runtime：未检测到")

        if self._version_at_least(paddleocr_version, (3, 7)):
            lines.append(f"✓ PP-OCRv6：支持（配置：{settings.paddle_ocr_version or 'PP-OCRv6'}）")
        else:
            lines.append(
                f"✗ PP-OCRv6：当前 PaddleOCR {paddleocr_version or '未知'} 不支持；请升级到 >= 3.7"
            )

        runtime_device = resolve_paddle_device()
        lines.append(f"本机运行设备：{runtime_device}（自动；项目不再固定 CPU/GPU）")
        if str(getattr(settings, "paddle_device", "auto") or "auto").lower() not in {"", "auto"}:
            lines.append("提示：项目中的旧 paddle_device 值仅保留兼容读取，当前运行已忽略该项目级设备设置。")
        try:
            import paddle  # type: ignore
            compiled_cuda = bool(paddle.device.is_compiled_with_cuda())
            if compiled_cuda:
                try:
                    gpu_count = int(paddle.device.cuda.device_count())
                except Exception:
                    gpu_count = 0
                lines.append(f"CUDA：可用（检测到 {gpu_count} 个 GPU）")
            elif paddle_gpu_version:
                lines.append("CUDA：GPU 版 runtime 已安装，但当前进程未检测到可用 CUDA。")
            else:
                lines.append("CUDA：未启用（CPU runtime）")
        except Exception as exc:
            lines.append(f"Paddle runtime 检查失败：{exc}")
        return "\n".join(lines)

    def show_environment_center(self) -> None:
        existing = self.__dict__.get("_environment_center_window")
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_force()
                    existing.refresh()
                    return
            except tk.TclError:
                pass
        window = EnvironmentCenterWindow(self)
        self._environment_center_window = window
        window.bind(
            "<Destroy>",
            lambda event, w=window: self.__dict__.pop("_environment_center_window", None)
            if event.widget is w else None,
            add="+",
        )

    def check_ocr_engines(self) -> None:
        """Backward-compatible action name: open the unified environment center."""
        self.show_environment_center()


    def detect_layout_current(self) -> None:
        """Run the existing selected-page layout detection workflow."""
        return _run_detect_layout_current(self)

    def detect_layout_consistency_selected(self) -> None:
        """Run the existing selected-page layout consistency report."""
        return _run_detect_layout_consistency_selected(self)

    @staticmethod
    def _normalize_suffix(value: str) -> str:
        value = value.strip()
        if not value: return ".png"
        return value.lower() if value.startswith(".") else f".{value.lower()}"

    @staticmethod
    def _page_number(path: Path) -> int | None:
        match = re.search(r"(\d+)(?!.*\d)", path.stem)
        return int(match.group(1)) if match else None

    def _parse_page_spec(self, spec: str) -> list[int]:
        if not self.project: return []
        tokens = [item.strip() for item in re.split(r"[,，]", spec) if item.strip()]
        if not tokens:
            raise ValueError("请填写指定页面范围，例如 0008-0020,0025,0030~0035。")
        # A numeric range denotes actual numbered page filenames (0001.png,
        # 0002.png, ...), not every filename whose final component happens to
        # be numeric. This keeps auxiliary scans such as 0000_01.png out of
        # ``1-100`` while retaining the historical ordinal fallback for
        # projects that have no purely numeric filenames at all.
        numeric_page_indices: dict[int, list[int]] = {}
        trailing_number_indices: dict[int, list[int]] = {}
        for index, page in enumerate(self.project.images):
            number = self._page_number(page)
            if number is not None:
                trailing_number_indices.setdefault(number, []).append(index)
            if page.stem.isdigit():
                numeric_page_indices.setdefault(int(page.stem), []).append(index)
        selected: list[int] = []
        for token in tokens:
            # Accept the range notations users commonly type/paste on Windows:
            # 0008-0020, 0008~0020, 0008～0020, 0008–0020, 0008—0020.
            # Leading zeroes are intentionally preserved in the input but page
            # matching is numeric so both 8 and 0008 resolve to page 0008.
            range_match = re.fullmatch(r"\s*(\d+)\s*[-~～–—−]\s*(\d+)\s*", token)
            if range_match:
                lo, hi = sorted((int(range_match.group(1)), int(range_match.group(2))))
                page_number_indices = numeric_page_indices or trailing_number_indices
                if page_number_indices:
                    missing = [number for number in range(lo, hi + 1) if number not in page_number_indices]
                    if missing:
                        shown = ", ".join(str(number) for number in missing[:12])
                        suffix = " …" if len(missing) > 12 else ""
                        raise ValueError(f"页面范围中以下页码不存在：{shown}{suffix}")
                    selected.extend(
                        index
                        for number in range(lo, hi + 1)
                        for index in page_number_indices[number]
                    )
                elif 1 <= lo <= hi <= len(self.project.images):
                    selected.extend(range(lo - 1, hi))
                else:
                    raise ValueError(f"页面范围超出项目：{token}")
            elif token.isdigit():
                number = int(token)
                if number in numeric_page_indices:
                    selected.extend(numeric_page_indices[number])
                elif not numeric_page_indices and number in trailing_number_indices:
                    selected.extend(trailing_number_indices[number])
                elif 1 <= number <= len(self.project.images):
                    selected.append(number - 1)
                else:
                    raise ValueError(f"找不到第 {number} 页。")
            else:
                raise ValueError(
                    f"页面范围格式错误：{token}。可使用 0008-0020、0008~0020，多个范围用逗号分隔。"
                )
        return sorted(set(selected))

    def selected_page_indices(self) -> list[int]:
        if not self.project: return []
        mode = self.page_range_var.get() if hasattr(self, "page_range_var") else "current"
        if mode == "current": return [self.current_index] if self.current_index >= 0 else []
        if mode == "bookmarks":
            return bookmarked_page_indices(self.project.images, self._bookmark_stems())
        if mode == "to_end": return list(range(max(0, self.current_index), len(self.project.images)))
        if mode == "to_specified":
            indices = self._parse_page_spec(self.page_range_spec_var.get())
            if len(indices) != 1:
                raise ValueError("当前至指定页需要输入一个结束页码")
            end = indices[0]
            return list(range(min(self.current_index, end), max(self.current_index, end) + 1))
        return self._parse_page_spec(self.page_range_spec_var.get())


    @staticmethod
    def _paddle_temp_matches_page(path: Path, page_stem: str) -> bool:
        """Return True only for PaddleOCR temp entries owned by one page stem."""
        name = path.name
        stem = str(page_stem or "")
        if not stem or name == stem:
            return bool(stem and name == stem)
        return any(
            name.startswith(stem + suffix)
            for suffix in (".", "_", "-")
        )

    def cleanup_paddleocr_temp_selected_scope(self) -> None:
        """Compact PaddleOCR cache for the selected pages without losing reusable OCR."""
        if not self.project:
            messagebox.showinfo("压缩OCR缓存", "请先打开项目。", parent=self)
            return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc)
            return
        if not indices:
            messagebox.showinfo("压缩OCR缓存", "当前页面范围为空。", parent=self)
            return

        cache_root = ocr_cache_root(self.project.root)
        if not cache_root.exists():
            messagebox.showinfo(
                "压缩OCR缓存",
                "当前项目没有 PaddleOCR 缓存可压缩。",
                parent=self,
            )
            return

        page_stems = [
            self.project.images[index].stem
            for index in indices
            if 0 <= int(index) < len(self.project.images)
        ]
        sidecar_suffixes = (
            "_ocr_diagnostics.txt", "_ocr_comparison.txt", "_issues.tsv",
            "_ocr_engines.tsv", "_fusion.tsv",
        )

        def human_size(size: int) -> str:
            value = float(max(0, size))
            units = ("B", "KB", "MB", "GB", "TB")
            for unit in units:
                if value < 1024.0 or unit == units[-1]:
                    return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
                value /= 1024.0
            return f"{size} B"

        existing_pages = 0
        estimated_bytes = 0
        legacy_sidecars = 0
        for stem in page_stems:
            cache_path = cache_root / f"{stem}.json"
            found = False
            paths = [cache_path]
            paths.extend(cache_root / f"{stem}{suffix}" for suffix in sidecar_suffixes)
            for path in paths:
                if not path.exists() or not path.is_file():
                    continue
                found = True
                try:
                    estimated_bytes += int(path.stat().st_size)
                except OSError:
                    pass
                if path != cache_path:
                    legacy_sidecars += 1
            if found:
                existing_pages += 1

        if not existing_pages:
            messagebox.showinfo(
                "压缩OCR缓存",
                f"所选 {len(indices)} 页没有对应的 PaddleOCR 缓存。",
                parent=self,
            )
            return

        confirmed = messagebox.askyesno(
            "压缩 PaddleOCR 缓存",
            (
                f"将优化所选范围内 {existing_pages} 页的 PaddleOCR 数据。\n\n"
                f"当前相关缓存/诊断约 {human_size(estimated_bytes)}；"
                f"发现 {legacy_sidecars} 个旧式可再生诊断文件。\n\n"
                "操作会：\n"
                "• 将 <page>.json 改写为紧凑缓存，只保留复用 OCR、Project Profile 诊断和校对所需信息；\n"
                "• 删除重复的 diagnostics/comparison/issues/engines/fusion 文本副本；\n"
                "• 保留 <page>_manual_selection.json 人工选择；\n"
                "• 保留 OCR 原始记录，因此之后正常“复用缓存”无需重新 OCR。\n\n"
                "原始扫描图、PDIC/PPP、词条文字和人工校对结果均不修改。是否继续？"
            ),
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return

        before_total = 0
        after_total = 0
        removed_sidecars = 0
        compacted = 0
        failed: list[str] = []
        for stem in page_stems:
            cache_path = cache_root / f"{stem}.json"
            try:
                before, after, removed = compact_ocr_cache_file(cache_path)
                if before <= 0 and removed <= 0:
                    continue
                before_total += before
                after_total += after
                removed_sidecars += removed
                compacted += 1
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                failed.append(f"{stem}: {exc}")

        released = max(0, before_total - after_total)
        summary = (
            f"已优化 {compacted} 页 PaddleOCR 缓存；"
            f"删除 {removed_sidecars} 个重复诊断文件；"
            f"释放约 {human_size(released)}"
        )
        self.status_var.set(summary)
        if failed:
            messagebox.showwarning(
                "OCR缓存压缩部分完成",
                summary + "\n\n以下页面未能压缩：\n" + "\n".join(failed[:12])
                + ("\n…" if len(failed) > 12 else ""),
                parent=self,
            )
            return
        messagebox.showinfo(
            "OCR缓存压缩完成",
            summary + "\n\n人工选择、可复用 OCR 原始记录、PDIC/PPP 和校对结果均已保留。",
            parent=self,
        )

    def jump_to_page_spec(self) -> None:
        """Navigate to the first page number typed in the specified-range box."""
        match = re.search(r"\d+", self.page_range_spec_var.get())
        if not match:
            messagebox.showinfo("跳到页面", "请先在“指定”文本框输入页码。", parent=self)
            return
        try:
            indices = self._parse_page_spec(match.group(0))
        except ValueError as exc:
            self.show_error("无法定位页面", exc)
            return
        if indices:
            self.page_range_var.set("specified")
            self.load_page(indices[0])

    def _foreground_batch_state(self, index: int | None = None) -> str:
        return _batch_workflow._foreground_batch_state(_batch_workflow_deps(), self, index=index)

    def _set_foreground_batch_state(self, index: int, state: str) -> None:
        return _batch_workflow._set_foreground_batch_state(_batch_workflow_deps(), self, index, state)

    def _claim_page_for_manual_edit(self, index: int | None = None) -> bool:
        """ claim page for manual edit."""
        return _batch_workflow._claim_page_for_manual_edit(_batch_workflow_deps(), self, index=index)

    def _can_save_current_during_batch_navigation(self) -> bool:
        return _batch_workflow._can_save_current_during_batch_navigation(_batch_workflow_deps(), self)

    def _entry_keypress_batch_guard(self, event: tk.Event) -> str | None:
        """Claim a pending page before a key can mutate a foreground Entry."""
        return _batch_workflow._entry_keypress_batch_guard(_batch_workflow_deps(), self, event)

    def _start_batch_task(
        self, title: str, items, worker, on_done=None, item_label=None,
        *, foreground_page_edit: bool = False, page_indexer=None,
        refresh_page_quality: bool = True,
        allow_page_navigation: bool = True,
        allow_pdic_edits: bool = False,
        flush_deferred_save: bool = True,
    ) -> bool:
        """ start batch task."""
        return _batch_workflow._start_batch_task(_batch_workflow_deps(), self, title, items, worker, on_done=on_done, item_label=item_label, foreground_page_edit=foreground_page_edit, page_indexer=page_indexer, refresh_page_quality=refresh_page_quality, allow_page_navigation=allow_page_navigation, allow_pdic_edits=allow_pdic_edits, flush_deferred_save=flush_deferred_save)

    def _start_parallel_batch_task(
        self, title: str, items, worker_func, job_builder, result_consumer=None,
        on_done=None, item_label=None, max_workers: int = 0,
        *, allow_page_navigation: bool = True, allow_pdic_edits: bool = False,
        foreground_page_edit: bool = False, page_indexer=None,
        gpu_preflight_func=None, gpu_job_builder=None,
        respect_cpu_workers: bool = False, isolate_worker: bool = False,
    ) -> bool:
        """Run bounded page jobs; optional one-process GPU preflight before CPU."""
        return _batch_workflow._start_parallel_batch_task(_batch_workflow_deps(), self, title, items, worker_func, job_builder, result_consumer=result_consumer, on_done=on_done, item_label=item_label, max_workers=max_workers, allow_page_navigation=allow_page_navigation, allow_pdic_edits=allow_pdic_edits, foreground_page_edit=foreground_page_edit, page_indexer=page_indexer, gpu_preflight_func=gpu_preflight_func, gpu_job_builder=gpu_job_builder, respect_cpu_workers=respect_cpu_workers, isolate_worker=isolate_worker)

    def _poll_batch_queue(self) -> None:
        return _batch_workflow._poll_batch_queue(_batch_workflow_deps(), self)

    def _finish_batch_task(self, completed: int, total: int, stopped: bool, results, error) -> None:
        return _batch_workflow._finish_batch_task(_batch_workflow_deps(), self, completed, total, stopped, results, error)

    def _hide_batch_bar_if_idle(self) -> None:
        return _batch_workflow._hide_batch_bar_if_idle(_batch_workflow_deps(), self)

    def _toggle_batch_pause(self) -> None:
        return _batch_workflow._toggle_batch_pause(_batch_workflow_deps(), self)

    def _request_batch_stop(self) -> None:
        return _batch_workflow._request_batch_stop(_batch_workflow_deps(), self)

    def guard(self) -> bool:
        if self._preprocess_mode_active():
            self.status_var.set("预处理模式中：普通编辑已锁定，请先退出预处理模式。")
            return False
        if getattr(self, "_batch_active", False):
            if not self._claim_page_for_manual_edit():
                return False
        if not self.project or not self.current_page or self.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
            return False
        return True

    @staticmethod
    def _ppp_write_path(page: Path) -> Path:
        return ppp_write_path_for_image(page)

    @staticmethod
    def _ppp_read_path(page: Path) -> Path:
        return ppp_read_path_for_image(page)

    def _save_normalized_ppp(self) -> bool:
        return self._illustration_controller_for_call().persist_current()

    def associate_illustrations(self) -> None:
        self._illustration_controller_for_call().associate_selected_scope()

    def reload_wordslist_reference(
        self, selected_path: Path | None = None, *, persist: bool = True, redraw: bool = True,
    ) -> tuple[Path, int]:
        """Reload the auxiliary wordslist and optionally remember a newly chosen file."""
        if not self.project:
            raise ValueError("尚未打开项目")
        if selected_path is not None:
            selected_path = selected_path.expanduser().resolve()
            if not selected_path.is_file():
                raise FileNotFoundError(selected_path)
            try:
                stored = selected_path.relative_to(self.project.root.resolve()).as_posix()
            except ValueError:
                stored = str(selected_path)
            self.settings.wordslist_path = stored
            self.project.settings.wordslist_path = stored
        path = resolve_wordslist_path(self.project.root, self.settings.wordslist_path)
        words = read_noncomment_lines(path) if path.exists() else []
        self.project.words = words
        self._project_words = set(words)
        if persist:
            self.settings.to_json(settings_path(self.project.root))
        if redraw and self.current_page is not None and self.image is not None:
            self.redraw()
        return path, len(words)

    def _request_wordslist_reload(
        self, selected_path: Path | None = None, *, persist: bool = True,
        redraw: bool = True, on_done=None, on_error=None,
    ) -> None:
        """Read a potentially huge wordslist off-thread, then commit it on Tk."""
        project = self.project
        if project is None:
            if on_error is not None:
                on_error(ValueError("尚未打开项目"))
            return

        configured = self.settings.wordslist_path
        stored_value: str | None = None
        if selected_path is not None:
            selected_path = selected_path.expanduser().resolve()
            if not selected_path.is_file():
                if on_error is not None:
                    on_error(FileNotFoundError(selected_path))
                return
            try:
                stored_value = selected_path.relative_to(project.root.resolve()).as_posix()
            except ValueError:
                stored_value = str(selected_path)
            configured = stored_value

        path = resolve_wordslist_path(project.root, configured)
        self.status_var.set(f"正在后台读取 wordslist：{path.name}…")

        def worker():
            words = read_noncomment_lines(path) if path.exists() else []
            return words

        def done(words) -> None:
            if self.project is not project:
                return
            if stored_value is not None:
                self.settings.wordslist_path = stored_value
                project.settings.wordslist_path = stored_value
            project.words = list(words)
            self._project_words = set(words)
            if persist:
                self.settings.to_json(settings_path(project.root))
            if redraw and self.current_page is not None and self.image is not None:
                self.redraw()
            self.status_var.set(f"wordslist 已载入：{path.name}｜{len(words)} 条")
            if on_done is not None:
                on_done(path, len(words))

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            if self.project is project:
                self.status_var.set(f"wordslist 读取失败：{exc}")
                if on_error is not None:
                    on_error(exc)
                else:
                    self.show_error("wordslist 读取失败", exc)

        self._start_ui_worker("wordslist-reload", worker, done, failed)


    def open_recent_project(self) -> None:
        """Show recent projects as a modern, information-focused card list."""
        return _project_session.open_recent_project(self, _project_session_deps())

    @staticmethod
    def _attach_tooltip(widget: tk.Widget, message: str) -> None:
        """Attach a lightweight native Tk tooltip without external dependencies."""
        return _project_session._attach_tooltip(_project_session_deps(), widget, message)

    def _project_controller_for_call(self) -> ProjectController:
        return _project_session._project_controller_for_call(self, _project_session_deps())

    def _choose_new_project_image_suffix(self, root: Path) -> str | None:
        return _project_session._choose_new_project_image_suffix(self, _project_session_deps(), root)

    def open_project(self) -> None:
        return _project_session.open_project(self, _project_session_deps())

    def _load_project(
        self, root: Path, *, requested_suffix: str | None = None,
        target_page: str | None = None, target_index: object = None,
        target_view_scale: float | None = None,
        launch_profile_setup: bool = False,
        parameter_template_root: Path | None = None,
    ) -> None:
        """Prepare project files off-thread and commit the prepared state on Tk."""
        return _project_session._load_project(self, _project_session_deps(), root, requested_suffix=requested_suffix, target_page=target_page, target_index=target_index, target_view_scale=target_view_scale, launch_profile_setup=launch_profile_setup, parameter_template_root=parameter_template_root)

    def on_page_select(self, _event: tk.Event) -> None:
        return _project_session.on_page_select(self, _project_session_deps(), _event)

    def _request_page_load(
        self, index: int, *, reset_zoom: bool = False,
        current_already_saved: bool = False, force: bool = False,
    ) -> bool:
        return _project_session._request_page_load(self, _project_session_deps(), index, reset_zoom=reset_zoom, current_already_saved=current_already_saved, force=force)

    def load_page(
        self, index: int, reset_zoom: bool = False, *,
        preloaded: dict | None = None, skip_current_save: bool = False,
    ) -> None:
        return _project_session.load_page(self, _project_session_deps(), index, reset_zoom=reset_zoom, preloaded=preloaded, skip_current_save=skip_current_save)

    def change_page(
        self, delta: int, *, preloaded: dict | None = None,
        current_already_saved: bool = False, async_allowed: bool = True,
    ) -> bool:
        return self.page_controller.change_page(
            delta,
            preloaded=preloaded,
            current_already_saved=current_already_saved,
            async_allowed=async_allowed,
        )

    def _get_cached_display_photo(self, size: tuple[int, int]) -> ImageTk.PhotoImage:
        """Return the resized page image for the current page/zoom.

        The page background is display-only.  OCR always receives ``self.image``
        in original-page pixels, so reusing this PhotoImage cannot alter OCR or
        separator coordinates.  A new page object or zoom size invalidates the
        cache automatically.
        """
        if self.image is None:
            raise RuntimeError("没有可显示的页面图像")
        binary = bool(self.binary_preview_var.get())
        key = (id(self.image), int(size[0]), int(size[1]), binary, self.appearance_mode)
        if self.photo is None or self._display_photo_cache_key != key:
            display = (
                binary_preview_image(self.image).resize(size, Image.Resampling.LANCZOS)
                if binary else self.image.resize(size, Image.Resampling.LANCZOS)
            )
            display = themed_display_image(display, self.appearance_mode)
            self.photo = ImageTk.PhotoImage(display)
            self._display_photo_cache_key = key
        return self.photo

    def _canvas_controller_for_call(self) -> CanvasController:
        controller = self.__dict__.get("canvas_controller")
        if controller is None:
            controller = CanvasController(self)
            self.__dict__["canvas_controller"] = controller
        return controller

    def _display_mode_from_flags(self) -> str:
        return self._canvas_controller_for_call().display_mode_from_flags()


    def _sync_display_mode_from_flags(self) -> None:
        self._canvas_controller_for_call().sync_display_mode_from_flags()


    def _apply_display_mode(self, _event=None) -> None:
        self._canvas_controller_for_call().apply_display_mode(_event)


    def _toggle_binary_preview(self) -> None:
        self._canvas_controller_for_call().toggle_binary_preview()


    def _toggle_hide_overlays(self) -> None:
        self._canvas_controller_for_call().toggle_hide_overlays()


    def _current_effective_profile_settings(self) -> AppSettings:
        """Resolve the current page's Project Profile template without mutating project settings."""
        if self.image is None:
            return self.settings
        return effective_page_settings(
            self.settings, self.image.size,
            max(0, int(self.__dict__.get("current_index", 0) or 0)),
        )

    def _display_geometry_key(self) -> tuple:
        if self.image is None:
            return ()
        s = self.settings
        return (
            id(self.image), int(self.__dict__.get("current_index", 0) or 0),
            int(s.columns),
            str(s.layout_columns_policy), str(s.layout_column_separator_mode),
            str(s.analysis_threshold_mode),
            float(s.manual_x), float(s.gutter), float(s.column_width),
            float(s.start_y), bool(s.crop_to_bottom_y), float(s.bottom_y),
            bool(s.follow_column_deformation), float(s.column_track_block_height),
            float(s.column_track_radius), float(s.body_indent),
            float(s.column_track_max_step), str(s.layout_transform),
            str(getattr(s, "layout_writing_mode", "horizontal-tb") or "horizontal-tb"),
            str(getattr(s, "layout_text_direction", "ltr") or "ltr"),
            str(getattr(s, "profile_header_mode", "auto")),
            str(getattr(s, "profile_footer_mode", "auto")),
            str(getattr(s, "profile_side_content_mode", "none")),
            str(getattr(s, "profile_page_pair_mode", "same")),
            str(getattr(s, "profile_first_page_variant", "A")),
            float(getattr(s, "profile_header_percent", 6.0)),
            float(getattr(s, "profile_footer_percent", 5.0)),
            float(getattr(s, "profile_side_percent", 8.0)),
            float(getattr(s, "profile_side_percent_a", getattr(s, "profile_side_percent", 8.0))),
            float(getattr(s, "profile_side_percent_b", getattr(s, "profile_side_percent", 8.0))),
        )

    def _get_cached_display_geometry(self):
        """Reuse the same per-page Profile geometry used by detection."""
        if self.image is None:
            raise RuntimeError("没有可显示的页面图像")
        key = self._display_geometry_key()
        if self._display_geometry_cache is None or self._display_geometry_cache_key != key:
            effective = self._current_effective_profile_settings()
            analysis_image = page_template_analysis_image(
                self.image, effective, max(0, int(self.current_index)),
            )
            self._display_geometry_cache = derive_geometry(analysis_image, effective)
            self._display_geometry_cache_key = key
        return self._display_geometry_cache

    def _main_ocr_review_option_enabled(self, setting_name: str) -> bool:
        """Return the persisted visibility of a main-canvas OCR aid."""
        return bool(getattr(self.settings, setting_name, False))

    # One entry's canvas/editor widgets are owned by the dedicated UI module.
    # Importing as a class attribute preserves method binding and call sites.
    from .ui.entry_overlay_builder import draw_entry_overlay as _draw_entry_overlay
    from .ui.entry_move_controller import move_entry_via_dialog as _move_entry_via_dialog

    def _remove_entry_overlay(self, entry: WordEntry) -> None:
        """Remove only the widgets/canvas items belonging to one headword row."""
        visuals = self.__dict__.get("_entry_visuals", {})
        record = visuals.pop(id(entry), None)
        if not record:
            return
        widgets = list(record.get("widgets") or [])
        canvas_items = list(record.get("canvas_items") or [])
        release_alpha_line_photos(self, canvas_items)
        for item in canvas_items:
            try:
                self.canvas.delete(item)
            except tk.TclError:
                pass
        for widget in widgets:
            try:
                widget.destroy()
            except tk.TclError:
                pass
            try:
                self.overlay_widgets.remove(widget)
            except ValueError:
                pass
        self.entry_editor_bindings = [
            (widget, bound_entry) for widget, bound_entry in self.entry_editor_bindings
            if bound_entry is not entry and widget not in widgets
        ]

    @staticmethod
    def _entry_sequence_text(index: int, total: int) -> str:
        """Format zero-based row numbers to one uniform width for the page."""
        width = max(1, len(str(max(1, int(total)))))
        return f"{int(index):0{width}d}"

    def _refresh_entry_index_labels(self) -> None:
        ordered = self._ordered_entries_reading_order()
        for index, entry in enumerate(ordered):
            record = self._entry_visuals.get(id(entry))
            widget = record.get("index_widget") if record else None
            if widget is not None:
                try:
                    widget.configure(
                        text=self._entry_sequence_text(index, len(ordered)),
                        bg="#e6e6e6",
                        fg="#000000",
                    )
                except tk.TclError:
                    pass

    def _update_entry_overlays_local(
        self, *, removed: list[WordEntry] | None = None, added: list[WordEntry] | None = None,
    ) -> None:
        """Apply a checkbox edit without re-resizing the page or rebuilding all rows."""
        removed = removed or []
        added = added or []
        for entry in removed:
            self._remove_entry_overlay(entry)
        image = self.__dict__.get("image")
        hide_var = self.__dict__.get("hide_var")
        if image is None or (hide_var is not None and hide_var.get()):
            return
        # A pure removal needs no geometry recomputation at all: the deleted
        # row's canvas ids are already gone, and only the tiny numeric labels
        # need renumbering. This is the most common proofreading action.
        if not added:
            self._refresh_entry_index_labels()
            if self.cursor_canvas_xy is not None:
                self.draw_cursor_guides(*self.cursor_canvas_xy)
            else:
                self._set_idle_cursor_status()
            return
        geometry = self._get_cached_display_geometry()
        size = (
            max(1, round(image.width * self.view_scale)),
            max(1, round(image.height * self.view_scale)),
        )
        overlay_scale = self.view_scale / parameter_scale(image, self.settings)
        ordered = self._ordered_entries_reading_order()
        index_by_id = {id(entry): index for index, entry in enumerate(ordered)}
        for entry in added:
            if id(entry) in self._entry_visuals:
                continue
            self._draw_entry_overlay(
                entry, index_by_id.get(id(entry), 0), geometry, size, overlay_scale,
                processing_readonly=False,
            )
        self._refresh_entry_index_labels()
        self._apply_current_appearance(self.canvas)
        if self.cursor_canvas_xy is not None:
            self.draw_cursor_guides(*self.cursor_canvas_xy)
        else:
            self._set_idle_cursor_status()

    def _toggle_crop_preview(self) -> None:
        self._canvas_controller_for_call().toggle_crop_preview()


    def _current_page_crop_plan(self):
        if self.image is None or self.current_page is None:
            return None
        config = self._load_crop_settings()
        special = config.get("special_pages", {}).get(self.current_page.stem, {}) if isinstance(config.get("special_pages", {}), dict) else {}
        top_y = int(special.get("top_y", config.get("general_top_y", self.settings.start_y)))
        bottom_y = int(special.get("bottom_y", config.get("general_bottom_y", 0)))
        margin = int(config.get("polygon_margin", 0))
        entry_left = int(config.get("entry_left_padding_x", 0))
        entry_right = int(config.get("entry_right_padding_x", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        return build_page_crop_plan(
            self.image, list(self.entries), list(self.polygons), self.settings,
            top_y=top_y, bottom_y=bottom_y, illustration_margin=margin,
            entry_left_padding=entry_left, entry_right_padding=entry_right,
            integrate_illustrations=integrate_illustrations,
            profile_page_index=max(0, int(self.current_index)),
            page_sections=list(self.page_sections),
            auxiliary_lines=list(self._auxiliary_edits.lines), page_stem=self.current_page.stem, previous_entry_ref=self._illustration_controller_for_call().previous_entry_ref(),
        )

    def _draw_crop_plan_preview(self) -> None:
        """Overlay the exact entry/PPP crop plan on the main page image."""
        return _main_canvas_render._draw_crop_plan_preview(self, _main_canvas_render_deps())

    def _rulers_visible(self) -> bool:
        return self._canvas_controller_for_call().rulers_visible()


    def _draw_percentage_rulers(self, geometry=None) -> None:
        self._canvas_controller_for_call().draw_percentage_rulers(geometry)


    def _ruler_hit_id(self, source_x: float, source_y: float) -> str | None:
        return self._canvas_controller_for_call().ruler_hit_id(source_x, source_y)


    def _hide_ruler_hint(self) -> None:
        self._canvas_controller_for_call().hide_ruler_hint()


    def _show_ruler_hint(self, event: tk.Event) -> None:
        self._canvas_controller_for_call().show_ruler_hint(event)


    def redraw(self) -> None:
        return _main_canvas_render.redraw(self, _main_canvas_render_deps())

    def _update_view_zoom_label(self) -> None:
        self._canvas_controller_for_call().update_view_zoom_label()


    def zoom(self, factor: float) -> None:
        self._canvas_controller_for_call().zoom(factor)


    def apply_view_zoom_text(self, _event=None) -> None:
        self._canvas_controller_for_call().apply_view_zoom_text(_event)


    def fit_page_width(self) -> None:
        self._canvas_controller_for_call().fit_page_width()


    def fit_single_column_width(self) -> None:
        """Scale a single dictionary column to the available viewer width."""
        if self.image is None:
            return
        try:
            column_width = float(self.settings.column_width)
            gutter = float(self.settings.gutter)
        except (AttributeError, TypeError, ValueError):
            column_width, gutter = 0.0, -1.0
        # Fit one column with a gutter-sized margin on each side.
        fit_width = column_width + 2 * gutter
        if not (0 < column_width <= self.image.width and gutter >= 0 and fit_width > 0):
            self.status_var.set("请先设置有效的单栏宽度和栏间距。")
            return
        self.update_idletasks()
        available = max(1, self.canvas.winfo_width())
        self.view_scale = min(3.0, max(0.08, available / fit_width))
        self._update_view_zoom_label()
        self.redraw()
        self._set_idle_cursor_status()
        self.canvas.xview_moveto(0.0)

    def fit_page_height(self) -> None:
        self._canvas_controller_for_call().fit_page_height()


    def canvas_mousewheel(self, event: tk.Event) -> str:
        return self._canvas_controller_for_call().canvas_mousewheel(event)


    def canvas_shift_mousewheel(self, event: tk.Event) -> str:
        return self._canvas_controller_for_call().canvas_shift_mousewheel(event)


    def canvas_ctrl_mousewheel(self, event: tk.Event) -> str:
        return self._canvas_controller_for_call().canvas_ctrl_mousewheel(event)


    def canvas_linux_mousewheel(self, event: tk.Event, step: int) -> str:
        return self._canvas_controller_for_call().canvas_linux_mousewheel(event, step)


    def original_xy(self, event: tk.Event) -> tuple[int, int]:
        return self._canvas_controller_for_call().original_xy(event)


    def draw_cursor_guides(self, canvas_x: float, canvas_y: float) -> None:
        self._canvas_controller_for_call().draw_cursor_guides(canvas_x, canvas_y)


    def canvas_leave(self, _event: tk.Event) -> None:
        self._canvas_controller_for_call().canvas_leave(_event)


    def _set_idle_cursor_status(self) -> None:
        self._canvas_controller_for_call().set_idle_cursor_status()


    @staticmethod
    def _polygon_display_name(region: PolygonRegion, index: int) -> str:
        return label_text(region.label) or f"P_{index + 1:02d}"

    def _set_polygon_display_name(self, region: PolygonRegion, name: str) -> None:
        """Compatibility setter: accept only association-code changes."""
        region.label = user_edited_link(region.label, name)

    def _update_polygon_label(self, region: PolygonRegion, widget: tk.Entry) -> None:
        if self._batch_active and self._batch_allow_pdic_edits:
            return
        try:
            text = widget.get().strip()
        except tk.TclError:
            return
        if self._illustration_controller_for_call().update_label(region, text):
            self.status_var.set(f"PPP标签已保存：{label_text(region.label)}")
        try:
            widget.delete(0, tk.END)
            widget.insert(0, label_text(region.label))
        except tk.TclError:
            pass

    def _commit_polygon_label_return(self, region: PolygonRegion, widget: tk.Entry) -> str:
        self._update_polygon_label(region, widget)
        try:
            self.canvas.focus_set()
        except tk.TclError:
            pass
        return "break"

    def _sync_polygon_label_texts(self) -> None:
        return _canvas_pointer._sync_polygon_label_texts(self, _canvas_pointer_deps())

    def _nearest_polygon_vertex(self, x: int, y: int, radius_screen: float = 11.0) -> tuple[int, int] | None:
        return _canvas_pointer._nearest_polygon_vertex(self, _canvas_pointer_deps(), x, y, radius_screen)

    @staticmethod
    def _rectangle_bounds(region: PolygonRegion, tolerance: int = 2) -> tuple[int, int, int, int] | None:
        """Return bounds when a four-point PPP is an axis-aligned rectangle."""
        if len(region.points) != 4:
            return None
        xs = [p[0] for p in region.points]
        ys = [p[1] for p in region.points]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        if x1 - x0 <= tolerance or y1 - y0 <= tolerance:
            return None
        expected = {(x0, y0), (x1, y0), (x1, y1), (x0, y1)}
        for px, py in region.points:
            if not any(abs(px - ex) <= tolerance and abs(py - ey) <= tolerance for ex, ey in expected):
                return None
        return x0, y0, x1, y1

    def _nearest_polygon_edge(self, x: int, y: int, radius_screen: float = 9.0) -> tuple[int, str] | None:
        return _canvas_pointer._nearest_polygon_edge(self, _canvas_pointer_deps(), x, y, radius_screen)

    @staticmethod
    def _set_rectangle_side(region: PolygonRegion, side: str, value: int) -> None:
        bounds = PictureCaptureApp._rectangle_bounds(region)
        if bounds is None:
            return
        x0, y0, x1, y1 = bounds
        if side == "left":
            value = min(value, x1 - 1)
            region.points = [(value if abs(x - x0) <= 2 else x, y) for x, y in region.points]
        elif side == "right":
            value = max(value, x0 + 1)
            region.points = [(value if abs(x - x1) <= 2 else x, y) for x, y in region.points]
        elif side == "top":
            value = min(value, y1 - 1)
            region.points = [(x, value if abs(y - y0) <= 2 else y) for x, y in region.points]
        elif side == "bottom":
            value = max(value, y0 + 1)
            region.points = [(x, value if abs(y - y1) <= 2 else y) for x, y in region.points]

    def _delete_polygon_region(self, region: PolygonRegion) -> None:
        return _canvas_pointer._delete_polygon_region(self, _canvas_pointer_deps(), region)

    @staticmethod
    @staticmethod
    def _external_polygon_label_position(
        min_x: float, min_y: float, max_x: float, max_y: float,
        label_width: int, label_height: int, canvas_width: float, canvas_height: float,
        gap: int = 6,
    ) -> tuple[float, float]:
        """Position label above the figure, aligned to its left edge."""
        margin = 2.0
        x = max(margin, min(min_x, max(margin, canvas_width - label_width - margin)))
        y = min_y - gap - label_height
        if y < margin:
            y = min(max(margin, min_y + gap), max(margin, canvas_height - label_height - margin))
        return x, y

    def _polygon_label_canvas_position(self, region: PolygonRegion, widget: tk.Widget) -> tuple[float, float]:
        return _canvas_pointer._polygon_label_canvas_position(self, _canvas_pointer_deps(), region, widget)

    def _update_polygon_canvas_geometry(self, region_index: int) -> None:
        return _canvas_pointer._update_polygon_canvas_geometry(self, _canvas_pointer_deps(), region_index)

    def _persist_current_page_sections(self) -> None:
        """Save explicit SECTION bounds without touching PDIC/PPP."""
        if self.current_page is None or self.image is None:
            return
        transform = LayoutTransform(
            str(getattr(self.settings, "layout_transform", "identity") or "identity")
        )
        canonical_width, canonical_height = transform.canonical_size(self.image.size)
        write_page_sections(
            self.current_page,
            list(self.page_sections),
            canonical_width=canonical_width,
            canonical_height=canonical_height,
            layout_transform=transform.kind,
        )

    def _set_section_editing(self, active: bool) -> None:
        return _canvas_pointer._set_section_editing(self, _canvas_pointer_deps(), active)

    def _restore_cursor_guides_after_section_edit(self) -> None:
        return _canvas_pointer._restore_cursor_guides_after_section_edit(self, _canvas_pointer_deps())

    def _finish_section_editing(self) -> bool:
        return _canvas_pointer._finish_section_editing(self, _canvas_pointer_deps())

    def _draw_page_sections(self, geometry=None) -> None:
        """Draw page-local SECTION bounds in source space on the main canvas."""
        return _main_canvas_render._draw_page_sections(self, _main_canvas_render_deps(), geometry)

    def _nearest_section_boundary(self, source_x: int, source_y: int) -> tuple[int, str] | None:
        return _canvas_pointer._nearest_section_boundary(self, _canvas_pointer_deps(), source_x, source_y)

    def _drag_page_section_boundary_to(self, source_x: int, source_y: int) -> None:
        return _canvas_pointer._drag_page_section_boundary_to(self, _canvas_pointer_deps(), source_x, source_y)

    def _section_gap_entry_count(self) -> int:
        if not self.page_sections:
            return 0
        geometry = self._get_cached_display_geometry()
        return sum(
            1 for entry in self.entries
            if not v_is_inside_sections(
                geometry.source_to_canonical(entry.x, entry.y)[1],
                self.page_sections, geometry.top, geometry.bottom,
            )
        )

    def toggle_auxiliary_mode(self) -> None:
        if self.ref_box_controller.pointer_active:
            self.ref_box_controller.stop_edit()
        self._auxiliary_controller.toggle_mode()

    def toggle_ref_box_edit(self) -> None:
        self.ref_box_controller.toggle_edit()

    def recognize_ref_boxes(self) -> None:
        self.ref_box_controller.recognize_selected_scope()

    def ocr_ref_boxes(self) -> None:
        self.ref_box_controller.ocr_selected_scope()

    def toggle_polygon_drawing(self) -> None:
        return _canvas_pointer.toggle_polygon_drawing(self, _canvas_pointer_deps())

    def canvas_left_double_click(self, event: tk.Event) -> str | None:
        return self._canvas_controller_for_call().canvas_left_double_click(event)

    def canvas_left_click(self, event: tk.Event) -> None:
        return _canvas_pointer.canvas_left_click(self, _canvas_pointer_deps(), event)

    def canvas_left_drag(self, event: tk.Event) -> str | None:
        return _canvas_pointer.canvas_left_drag(self, _canvas_pointer_deps(), event)

    def canvas_left_release(self, _event: tk.Event) -> str | None:
        return _canvas_pointer.canvas_left_release(self, _canvas_pointer_deps(), _event)

    def _canvas_shift_right_click(self, event: tk.Event) -> str:
        if self.project and self.current_page and self.image is not None:
            self.change_page(-1)
        return "break"

    def canvas_right_click(self, event: tk.Event) -> None:
        return _canvas_pointer.canvas_right_click(self, _canvas_pointer_deps(), event)

    def canvas_motion(self, event: tk.Event) -> None:
        self._canvas_controller_for_call().canvas_motion(event)

    def _confidence_bg(self, confidence: float | None) -> str:
        if confidence is None:
            return "#eeeeee"
        if confidence >= 0.95:
            return "#c8e6c9"
        if confidence >= 0.90:
            return "#e8f5c8"
        if confidence >= 0.80:
            return "#fff3bf"
        if confidence >= 0.65:
            return "#ffe0b2"
        return "#ffcdd2"

    def _style_entry_editor(
        self, widget: tk.Entry | VerticalWordText, entry: WordEntry, displayed_word: str | None = None
    ) -> None:
        """Style a main-view headword editor by wordslist membership.

        Membership is intentionally encoded only by the outer border:
        words present in wordslist.txt keep the normal thin neutral border,
        while missing words receive a conspicuous red outline.  The optional
        ``displayed_word`` lets KeyRelease refresh the border before FocusOut
        commits the edit back to ``entry.word``.
        """
        bg, border, thickness = self._entry_overlay_style(entry, displayed_word)
        options = {
            "bg": bg,
            "highlightthickness": thickness,
            "highlightbackground": border,
            "highlightcolor": border,
        }
        if isinstance(widget, VerticalWordText):
            options["insertbackground"] = "#111111"
        else:
            options["disabledbackground"] = bg
        widget.configure(**options)
        # Sequence labels use a fixed light-gray background with black text so
        # row numbering stays visually stable regardless of marker/OCR colours.
        record = self.__dict__.get("_entry_visuals", {}).get(id(entry))
        index_control = record.get("index_widget") if record else None
        if index_control is not None:
            try:
                index_control.configure(bg="#e6e6e6", fg="#000000")
            except tk.TclError:
                pass
        delete_control = record.get("delete_widget") if record else None
        if delete_control is not None:
            try:
                delete_control.configure(
                    bg="#9d042f", fg="#ffffff",
                    activebackground="#9d042f", activeforeground="#ffffff",
                )
            except tk.TclError:
                pass

    def _entry_overlay_style(
        self, entry: WordEntry, displayed_word: str | None = None,
    ) -> tuple[str, str, int]:
        """Return the shared editor background and membership border."""
        word = entry.word if displayed_word is None else displayed_word
        in_wordlist = bool(word and word in self._project_words)
        bg = (
            self._confidence_bg(entry.confidence)
            if self._main_ocr_review_option_enabled("review_main_show_ocr_background")
            else self.settings.main_entry_default_color
        )
        project = getattr(self, "project", None)
        wordslist_exists = bool(getattr(self, "_project_words", set())) if project is None else False
        if project is not None:
            try:
                wordslist_exists = resolve_wordslist_path(
                    project.root, self.settings.wordslist_path
                ).is_file()
            except OSError:
                wordslist_exists = False
        if not wordslist_exists:
            border = "#c7c7c7"
            thickness = 1
        elif in_wordlist:
            border = "#b0b0b0"
            thickness = 1
        else:
            border = "#d32f2f"
            thickness = 2
        return bg, border, thickness

    def _candidate_for_entry(self, entry: WordEntry) -> dict | None:
        """Find the OCR review candidate corresponding to a visible headword row."""
        if entry.candidate_id:
            for candidate in self.ocr_review_candidates:
                if str(candidate.get("candidate_id", "")) == entry.candidate_id:
                    return candidate
        tolerance = max(6, round(self._quick_geometry_value("character_height") * 0.55))
        nearby: list[tuple[float, dict]] = []
        for candidate in self.ocr_review_candidates:
            try:
                dx = abs(int(candidate.get("source_x", entry.x)) - entry.x)
                dy = abs(int(candidate.get("source_y", entry.y)) - entry.y)
            except (TypeError, ValueError):
                continue
            if dx <= 20 and dy <= tolerance:
                nearby.append((dy + dx * 0.1, candidate))
        return min(nearby, key=lambda item: item[0])[1] if nearby else None

    @staticmethod
    def _short_ocr_menu_word(word: str, limit: int = 12) -> str:
        word = str(word).strip()
        return word if len(word) <= limit else word[: max(1, limit - 1)] + "…"

    def _fill_main_entry_from_ocr(
        self, entry: WordEntry, editor: tk.Entry | VerticalWordText, candidate: dict,
        engine: str, word: str, menu_button: tk.Menubutton | None = None,
    ) -> None:
        """Fill one main-page editor from a compact OCR choice and persist it."""
        if not self._claim_page_for_manual_edit():
            return
        word = str(word).strip()
        if not word:
            return
        side = candidate.get(engine, {}) if engine in {"paddle", "tesseract", "lens"} else {}
        confidence = side.get("confidence") if isinstance(side, dict) else None
        try:
            entry.confidence = float(confidence) if confidence is not None else entry.confidence
        except (TypeError, ValueError):
            pass
        entry.word = word
        entry.ocr_source = engine
        entry.final_engine = engine
        entry.manually_selected = True
        cid = str(candidate.get("candidate_id", ""))
        if cid:
            entry.candidate_id = cid
        candidate["word"] = word
        candidate["final_engine"] = engine
        candidate["selected"] = True
        candidate["decision_reason"] = "main_view_ocr_choice"
        issues = list(candidate.get("issue_types", []) or [])
        if "MANUAL_OVERRIDE" not in issues:
            issues.append("MANUAL_OVERRIDE")
        candidate["issue_types"] = issues
        entry.issue_type = ",".join(str(item) for item in issues)
        editor.delete(0, "end")
        editor.insert(0, word)
        editor.icursor("end")
        self._style_entry_editor(editor, entry, word)
        # Keep every main-page OCR selector the same compact width.
        # The selected OCR word belongs in the editor, not on the selector button.
        self._write_manual_override(candidate, selected=True, word=word, engine=engine)
        self.save_pdic(silent=True)
        editor.focus_set()
        self.status_var.set(f"已填入 OCR 结果：{word}")

    def _create_main_ocr_menu(
        self, entry: WordEntry, editor: tk.Entry | VerticalWordText, candidate: dict | None,
    ) -> tk.Menubutton | None:
        """Create a compact OCR-result selector displayed beside a main editor."""
        rows = _candidate_choice_rows(candidate)
        if not _has_distinct_ocr_alternatives(candidate) or not rows:
            return None
        button = tk.Menubutton(
            self.canvas, text="OCR ▾",
            relief="groove", bd=1, padx=2, pady=0,
            bg="#f5f5f5", activebackground="#e8e8e8",
            font=("TkDefaultFont", 8), cursor="hand2",
        )
        menu = tk.Menu(button, tearoff=False)
        self._apply_current_appearance(menu)
        final_separator_added = False
        for engine, label, word, confidence, is_final in rows:
            if is_final and not final_separator_added:
                menu.add_separator()
                final_separator_added = True
            suffix = f"  ({confidence:.2f})" if confidence is not None else ""
            menu.add_command(
                label=f"{label}: {word}{suffix}",
                command=lambda e=engine, w=word, b=button, c=candidate: self._fill_main_entry_from_ocr(
                    entry, editor, c, e, w, b
                ),
            )
        button.configure(menu=menu)
        return button

    def _paddle_cache_path(self) -> Path | None:
        if not self.project or not self.current_page:
            return None
        return ocr_cache_root(self.project.root) / f"{self.current_page.stem}.json"

    def _manual_selection_path(self) -> Path | None:
        cache = self._paddle_cache_path()
        return cache.with_name(f"{cache.stem}_manual_selection.json") if cache else None

    def _review_controller_for_call(self) -> ReviewController:
        controller = self.__dict__.get("review_controller")
        if controller is None:
            controller = ReviewController(self)
            self.__dict__["review_controller"] = controller
        return controller

    def _load_ocr_review_candidates(self) -> None:
        self._review_controller_for_call().load_ocr_review_candidates()


    def get_review_candidate(self, candidate_id: str) -> dict | None:
        return self._review_controller_for_call().get_review_candidate(candidate_id)


    def _candidate_is_selected(self, cand: dict) -> bool:
        return self._review_controller_for_call().candidate_is_selected(cand)


    def _read_manual_overrides(self) -> dict:
        path = self._manual_selection_path()
        if (
            path is not None
            and self._pending_manual_override_path == path
            and self._pending_manual_override_payload is not None
        ):
            return self._pending_manual_override_payload
        if not path or not path.exists():
            return {"version": 1, "overrides": {}}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError
            raw.setdefault("version", 1)
            raw.setdefault("overrides", {})
            return raw
        except Exception:
            return {"version": 1, "overrides": {}}

    def _flush_pending_manual_override(self) -> None:
        path = self.__dict__.get("_pending_manual_override_path")
        payload = self.__dict__.get("_pending_manual_override_payload")
        if path is None or payload is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._pending_manual_override_path = None
        self._pending_manual_override_payload = None

    def _write_manual_override(
        self, cand: dict, *, selected: bool, word: str | None = None,
        engine: str | None = None, defer: bool = False,
    ) -> None:
        path = self._manual_selection_path()
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # If another page somehow still has a queued sidecar write, commit it
        # before switching the in-memory payload. Normal navigation already
        # force-flushes, but this guard prevents cross-page contamination.
        if self._pending_manual_override_path not in {None, path}:
            self._flush_pending_manual_override()
        payload = self._read_manual_overrides()
        cid = str(cand.get("candidate_id", ""))
        if not cid:
            return
        payload["page"] = self.current_page.stem if self.current_page else ""
        payload["overrides"][cid] = {
            "selected": bool(selected),
            "word": str(word if word is not None else cand.get("word", "")),
            "engine": str(engine if engine is not None else cand.get("final_engine", "manual")),
        }
        if defer:
            self._pending_manual_override_path = path
            self._pending_manual_override_payload = payload
        else:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            if self._pending_manual_override_path == path:
                self._pending_manual_override_path = None
                self._pending_manual_override_payload = None

    def _queue_proofreading_add_evidence(self, x: int, y: int) -> None:
        """Stage a user canvas click, NOT a durable event until PDIC commits."""
        if not getattr(getattr(self, "settings", None), "proofreading_event_capture", False):
            return
        state = self.__dict__
        if "_pending_evidence_add" in state:
            # More than one insertion or additional save requests coalesced.
            state["_pending_evidence_add"] = False
            return
        project = getattr(self, "project", None)
        page = getattr(self, "current_page", None)
        if project is None or page is None:
            return
        try:
            old = read_pdic(pdic_path(page))
        except (OSError, ValueError):
            return
        from .proofreading.capture import verified_ocr_preedit_fingerprints
        cache_fn = getattr(self, "_paddle_cache_path", None)
        cache = cache_fn() if callable(cache_fn) else None
        source = verified_ocr_preedit_fingerprints(cache, pdic_path(page))
        state["_pending_evidence_add"] = (page, old, (int(x), int(y)), source)

    def _flush_proofreading_add_evidence(self) -> None:
        """Record the manual click only after a successfully saved PDIC."""
        snapshot = self.__dict__.pop("_pending_evidence_add", None)
        if not isinstance(snapshot, tuple):
            return
        if not getattr(getattr(self, "settings", None), "proofreading_event_capture", False):
            return
        if len(snapshot) != 4:
            return
        page, old, xy, source = snapshot
        project = getattr(self, "project", None)
        if project is None or getattr(self, "current_page", None) != page:
            return
        try:
            from .proofreading.capture import capture_saved_manual_addition
            capture_saved_manual_addition(
                project_root=project.root, page=page,
                prior_pdic_entries=old, expected_xy=xy,
                source_fingerprints=source,
            )
        except (OSError, ValueError, TypeError):
            status = getattr(self, "status_var", None)
            if status is not None:
                status.set("词条已保存，但本地新增词条日志写入失败。")

    def _queue_proofreading_candidate_evidence(self, cand: dict, selected: bool) -> None:
        """Keep one pre-save checkbox snapshot; coalesced edits are ambiguous."""
        state = self.__dict__
        if not getattr(getattr(self, "settings", None), "proofreading_event_capture", False):
            return
        if "_pending_evidence_toggle" in state:
            state["_pending_evidence_toggle"] = False
            return
        page = getattr(self, "current_page", None)
        if page is None or getattr(self, "project", None) is None:
            return
        candidate_id = str(cand.get("candidate_id", "") or "")
        if not candidate_id or sum(
            str(row.get("candidate_id", "")) == candidate_id
            for row in getattr(self, "ocr_review_candidates", ())
            if isinstance(row, dict)
        ) != 1:
            return
        try:
            before = read_pdic(pdic_path(page))
            override = self._manual_selection_path()
            expected = (
                str(cand.get("word", "")),
                int(cand.get("source_x", 0)), int(cand.get("source_y", 0)),
            )
        except (OSError, ValueError, TypeError):
            return
        if override is None:
            return
        position_switch = None
        group_id = str(cand.get("position_group_id") or "")
        if selected and group_id:
            siblings = [
                row for row in getattr(self, "ocr_review_candidates", ())
                if row is not cand and isinstance(row, dict)
                and row.get("position_group_id") == group_id
                and str(row.get("candidate_id") or "") != candidate_id
            ]
            # Only an actual selected, uniquely linked sibling counts as the
            # pre-click physical-headword location; never infer from nearest Y.
            matched = [
                (str(entry.candidate_id), (str(entry.word), int(entry.x), int(entry.y)))
                for sibling in siblings
                for entry in getattr(self, "entries", ())
                if str(entry.candidate_id or "") == str(sibling.get("candidate_id") or "")
                and str(entry.candidate_id or "")
            ]
            if len(matched) == 1:
                removed_id, removed_row = matched[0]
                if sum(
                    str(row.get("candidate_id") or "") == removed_id
                    for row in getattr(self, "ocr_review_candidates", ())
                    if isinstance(row, dict)
                ) == 1:
                    position_switch = (removed_id, removed_row, group_id)
        from .proofreading.capture import verified_ocr_preedit_fingerprints
        cache_fn = getattr(self, "_paddle_cache_path", None)
        cache = cache_fn() if callable(cache_fn) else None
        source = verified_ocr_preedit_fingerprints(cache, pdic_path(page))
        state["_pending_evidence_toggle"] = (
            page, before, expected, candidate_id, bool(selected), override,
            position_switch, source,
        )

    def _flush_proofreading_candidate_evidence(self) -> None:
        """Only after PDIC and delayed manual-selection sidecar are both saved."""
        snapshot = self.__dict__.pop("_pending_evidence_toggle", None)
        if not isinstance(snapshot, tuple):
            return
        if len(snapshot) != 8:
            return
        page, before, expected, candidate_id, selected, override, position_switch, source = snapshot
        if not getattr(getattr(self, "settings", None), "proofreading_event_capture", False):
            return
        project = getattr(self, "project", None)
        # A deferred callback must never attribute a previous page's click
        # after navigation has already changed the active page.
        if project is None or getattr(self, "current_page", None) != page:
            return
        try:
            from .proofreading.capture import (
                capture_saved_candidate_selection,
                capture_saved_position_switch,
            )
            recorded = capture_saved_candidate_selection(
                project_root=project.root, page=page,
                prior_pdic_entries=before, expected_entry=expected,
                candidate_id=candidate_id, candidate_id_unique=True,
                selected=selected, manual_selection_path=override,
                source_fingerprints=source,
            )
            if not recorded and selected and position_switch is not None:
                old_candidate_id, old_entry, group_id = position_switch
                capture_saved_position_switch(
                    project_root=project.root, page=page,
                    prior_pdic_entries=before,
                    removed_entry=old_entry, added_entry=expected,
                    removed_candidate_id=old_candidate_id,
                    added_candidate_id=candidate_id,
                    position_group_id=group_id,
                    manual_selection_path=override,
                    source_fingerprints=source,
                )
        except (OSError, ValueError, TypeError):
            # Journal failure must not roll back user PDIC or overrides.
            status = getattr(self, "status_var", None)
            if status is not None:
                status.set("候选选择已保存，但本地校对日志写入失败。")

    def _schedule_deferred_page_save(self, *, sync_editors: bool = True) -> None:
        """Coalesce rapid checkbox edits while preserving an exact page snapshot."""
        project = self.__dict__.get("project")
        current_page = self.__dict__.get("current_page")
        image = self.__dict__.get("image")
        if not project or not current_page or image is None:
            return
        # Editor contents belong to the same in-memory page model and must be in
        # the snapshot; otherwise a checkbox click could save stale text. The
        # checkbox path has already synchronized them once, so it can skip the
        # duplicate widget walk here.
        if sync_editors:
            self._sync_entry_editor_texts()
        snapshot = (
            current_page,
            [replace(entry) for entry in self.entries],
            int(image.width),
            self.pages_tuple(),
            int(self.current_index),
        )
        self._deferred_save_page = current_page
        self._deferred_save_snapshot = snapshot
        deferred_job = self.__dict__.get("_deferred_save_job")
        if deferred_job is not None:
            try:
                self.after_cancel(deferred_job)
            except tk.TclError:
                pass
        self._deferred_save_job = self.after(self._deferred_save_delay_ms, self._flush_deferred_page_save)

    def _flush_deferred_page_save(self) -> None:
        """Flush pending PDIC edits without discarding a failed snapshot."""
        from .proofreading.deferred_save import flush_deferred_page_save
        flush_deferred_page_save(self, write_pdic=write_pdic, pdic_path=pdic_path)

    def _entry_for_candidate(self, cand: dict) -> WordEntry | None:
        return self._review_controller_for_call().entry_for_candidate(cand)


    def set_candidate_selected(self, cand: dict, selected: bool) -> bool:
        if not self._claim_page_for_manual_edit():
            return False
        self._queue_proofreading_candidate_evidence(cand, selected)
        # Commit every visible editor by object identity before changing the
        # entries list. This prevents a middle-row removal from reassigning the
        # following editor texts to earlier entries.
        self._sync_entry_editor_texts()
        removed_entries: list[WordEntry] = []
        added_entries: list[WordEntry] = []

        # Refined-Y and original/anchor-Y fallback rows are two positions for
        # the same physical headword. Selecting either is a one-click switch.
        group_id = str(cand.get("position_group_id", ""))
        if selected and group_id:
            for sibling in self.ocr_review_candidates:
                if sibling is cand or str(sibling.get("position_group_id", "")) != group_id:
                    continue
                sibling_entry = self._entry_for_candidate(sibling)
                if sibling_entry is not None and sibling_entry in self.entries:
                    self.entries.remove(sibling_entry)
                    removed_entries.append(sibling_entry)
                sibling["selected"] = False
                sibling_var = self.candidate_check_vars.get(str(sibling.get("candidate_id", "")))
                if sibling_var is not None:
                    sibling_var.set(False)
                self._write_manual_override(
                    sibling, selected=False,
                    word=str(sibling.get("word", "")), engine="position_switch", defer=True,
                )

        entry = self._entry_for_candidate(cand)
        if selected:
            if entry is None:
                entry = WordEntry(
                    str(cand.get("word", "")), int(cand.get("source_x", 0)), int(cand.get("source_y", 0)),
                    confidence=(float(cand.get("confidence")) if cand.get("confidence") is not None else None),
                    ocr_source=str(cand.get("final_engine", "manual")),
                    alphabetical_warning=str(cand.get("alphabetical_warning", "")),
                    candidate_id=str(cand.get("candidate_id", "")),
                    final_engine=str(cand.get("final_engine", "")),
                    issue_type=",".join(str(x) for x in cand.get("issue_types", []) or []),
                    parser_score=(float(cand.get("score")) if cand.get("score") is not None else None),
                    manually_selected=True,
                )
                self.entries.append(entry)
                added_entries.append(entry)
            cand["selected"] = True
        else:
            if entry is not None and entry in self.entries:
                self.entries.remove(entry)
                removed_entries.append(entry)
            cand["selected"] = False
        self._sort_entries_reading_order()
        self._write_manual_override(
            cand, selected=selected,
            word=(entry.word if entry else str(cand.get("word", ""))),
            engine="manual_checkbox", defer=True,
        )
        target_var = self.candidate_check_vars.get(str(cand.get("candidate_id", "")))
        if target_var is not None:
            target_var.set(bool(selected))

        # The data model is already final at this point. Only the affected entry
        # overlay is changed; the cached background and unrelated editors stay
        # untouched. Disk I/O is coalesced below.
        self._update_entry_overlays_local(removed=removed_entries, added=added_entries)
        self._schedule_deferred_page_save(sync_editors=False)
        variant = str(cand.get("position_variant", "refined"))
        if selected and variant in {"original", "anchor"}:
            self.status_var.set("已切回原始 Y / 图像锚点 Y")
        elif selected and variant == "refined":
            self.status_var.set("已使用精修 Y")
        return True

    def apply_candidate_choice(self, cand: dict, engine: str, word: str) -> None:
        if not self._claim_page_for_manual_edit():
            return
        self._sync_entry_editor_texts()
        side = cand.get(engine, {}) if engine in {"paddle", "tesseract", "lens"} else {}
        if engine in {"paddle", "tesseract", "lens"} and side:
            if side.get("y") is not None: cand["source_y"] = int(side.get("y"))
            if side.get("confidence") is not None: cand["confidence"] = float(side.get("confidence"))
            if side.get("score") is not None: cand["score"] = float(side.get("score"))
        cand["word"] = word
        cand["final_engine"] = engine
        cand["selected"] = True
        cand["decision_reason"] = "manual_review_choice"
        issues = list(cand.get("issue_types", []) or [])
        if "MANUAL_OVERRIDE" not in issues: issues.append("MANUAL_OVERRIDE")
        cand["issue_types"] = issues
        old = self._entry_for_candidate(cand)
        if old is not None: self.entries.remove(old)
        entry = WordEntry(
            word, int(cand.get("source_x", 0)), int(cand.get("source_y", 0)),
            confidence=(float(cand.get("confidence")) if cand.get("confidence") is not None else None),
            ocr_source=engine, candidate_id=str(cand.get("candidate_id", "")), final_engine=engine,
            issue_type=",".join(issues), parser_score=(float(cand.get("score")) if cand.get("score") is not None else None),
            manually_selected=True,
        )
        self.entries.append(entry); self._sort_entries_reading_order()
        self._write_manual_override(cand, selected=True, word=word, engine=engine)
        self.save_pdic(silent=True); self.redraw()

    def candidate_checkbox_changed(self, candidate_id: str, var: tk.BooleanVar) -> None:
        cand = self.get_review_candidate(candidate_id)
        if cand is not None:
            requested = bool(var.get())
            if not self.set_candidate_selected(cand, requested):
                # The checkbox toggles before the command callback fires. If a
                # background worker currently owns the page, immediately restore
                # the visual state so UI and in-memory data cannot diverge.
                var.set(self._candidate_is_selected(cand))

    def clear_review_entry_highlight(self) -> None:
        self._review_controller_for_call().clear_review_entry_highlight()


    def highlight_review_entry(self, entry: WordEntry) -> None:
        self._review_controller_for_call().highlight_review_entry(entry)


    def _scroll_review_entry_into_view(self, entry: WordEntry) -> None:
        """Scroll the main image only if the proofreading row is off-screen."""
        if self.image is None:
            return
        try:
            geometry = self._get_cached_display_geometry()
            crop_settings = _review_crop_settings(
                self.image, self.settings, self.canvas.winfo_width()
            )
            left, top, right, bottom = _review_line_box(
                entry, geometry, self.image, crop_settings
            )
            scale = self.view_scale
            left, top, right, bottom = (
                left * scale, top * scale, right * scale, bottom * scale
            )
            canvas = self.canvas
            canvas.update_idletasks()
            viewport_w = max(1, canvas.winfo_width())
            viewport_h = max(1, canvas.winfo_height())
            current_x = canvas.canvasx(0)
            current_y = canvas.canvasy(0)
            pad = 16
            new_x = current_x
            new_y = current_y
            if left < current_x + pad or right > current_x + viewport_w - pad:
                new_x = max(0.0, left - pad)
            if top < current_y + pad or bottom > current_y + viewport_h - pad:
                new_y = max(0.0, top - pad)
            image_w = max(1.0, self.image.width * scale)
            image_h = max(1.0, self.image.height * scale)
            if new_x != current_x:
                max_x = max(0.0, image_w - viewport_w)
                canvas.xview_moveto(min(new_x, max_x) / image_w)
            if new_y != current_y:
                max_y = max(0.0, image_h - viewport_h)
                canvas.yview_moveto(min(new_y, max_y) / image_h)
        except (tk.TclError, ValueError, TypeError, AttributeError):
            return

    def _draw_review_entry_highlight(self, geometry=None) -> None:
        return _main_canvas_render._draw_review_entry_highlight(self, _main_canvas_render_deps(), geometry)

    def jump_to_review_candidate(self, cand: dict) -> None:
        self._review_controller_for_call().jump_to_review_candidate(cand)


    def open_ocr_conflict_review(self) -> None:
        if not self.guard(): return
        self._load_ocr_review_candidates()
        if self.ocr_review_window is not None and self.ocr_review_window.winfo_exists():
            self.ocr_review_window.refresh(); self.ocr_review_window.lift(); return
        self.ocr_review_window = OCRConflictReviewDialog(self)

    def _current_page_quality_text(self) -> str:
        path = self._paddle_cache_path()
        if not path or not path.exists(): return ""
        try:
            q = json.loads(path.read_text(encoding="utf-8")).get("page_quality", {}) or {}
            if "agreement" not in q: return ""
            return f"双OCR一致性 {float(q['agreement'])*100:.1f}% / 待复核 {int(q.get('needs_review',0))}"
        except Exception:
            return ""

    def _page_metadata(self, index: int) -> str:
        return _page_index._page_metadata(self, _page_index_deps(), index)

    def _page_illustration_count_text(self, index: int) -> str:
        return _page_index._page_illustration_count_text(self, _page_index_deps(), index)

    def _update_page_row(self, index: int) -> None:
        return _page_index._update_page_row(self, _page_index_deps(), index)

    def _refresh_page_metadata_step(self, generation: int, start: int) -> None:
        return _page_index._refresh_page_metadata_step(self, _page_index_deps(), generation, start)

    def _refresh_page_quality_colors(self) -> None:
        return _page_index._refresh_page_quality_colors(self, _page_index_deps())

    def _restore_entry_ocr_metadata(self, payload: dict | None = None) -> None:
        """Restore runtime confidence/source/warnings from the Paddle JSON sidecar."""
        if not self.project or not self.current_page or not self.entries:
            return
        if payload is None:
            path = ocr_cache_root(self.project.root) / f"{self.current_page.stem}.json"
            if not path.exists():
                return
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return
        try:
            meta = list(payload.get("final_entries") or [])
            # Review candidates may have been manually toggled after the last OCR
            # cache write; use them as metadata fallback for PDIC rows.
            for cand in payload.get("review_candidates") or []:
                if not isinstance(cand, dict):
                    continue
                meta.append({
                    "word": cand.get("word", ""), "x": cand.get("source_x", 0), "y": cand.get("source_y", 0),
                    "confidence": cand.get("confidence"), "ocr_source": cand.get("final_engine", ""),
                    "alphabetical_warning": cand.get("alphabetical_warning", ""),
                    "candidate_id": cand.get("candidate_id", ""), "final_engine": cand.get("final_engine", ""),
                    "issue_type": ",".join(cand.get("issue_types", []) or []), "parser_score": cand.get("score"),
                })
        except Exception:
            return
        if not meta:
            return
        used: set[int] = set()
        for entry in self.entries:
            best = None
            best_distance = None
            for i, item in enumerate(meta):
                if i in used:
                    continue
                try:
                    x = int(item.get("x", entry.x)); y = int(item.get("y", entry.y))
                except (TypeError, ValueError):
                    continue
                if abs(x - entry.x) > 12:
                    continue
                word = str(item.get("word", ""))
                word_penalty = 0 if not entry.word or not word or entry.word.casefold() == word.casefold() else 12
                distance = abs(y - entry.y) + word_penalty
                if distance <= 18 and (best_distance is None or distance < best_distance):
                    best = (i, item); best_distance = distance
            if best is None:
                continue
            i, item = best; used.add(i)
            value = item.get("confidence")
            try:
                entry.confidence = float(value) if value is not None else None
            except (TypeError, ValueError):
                entry.confidence = None
            entry.ocr_source = str(item.get("ocr_source", ""))
            entry.alphabetical_warning = str(item.get("alphabetical_warning", ""))
            entry.candidate_id = str(item.get("candidate_id", ""))
            entry.final_engine = str(item.get("final_engine", item.get("ocr_source", "")))
            entry.issue_type = str(item.get("issue_type", ""))
            try:
                entry.parser_score = float(item.get("parser_score")) if item.get("parser_score") is not None else None
            except (TypeError, ValueError):
                entry.parser_score = None
            entry.manually_selected = bool(item.get("manually_selected", False))

    def update_entry(self, entry: WordEntry, widget: tk.Entry | VerticalWordText) -> None:
        new_word = widget.get().strip()
        if new_word != entry.word:
            if not self._claim_page_for_manual_edit():
                try:
                    widget.configure(state="normal")
                    widget.delete(0, "end"); widget.insert(0, entry.word)
                    if self._foreground_batch_state(self.current_index) == "processing":
                        widget.configure(state="disabled")
                except tk.TclError:
                    pass
                return
            entry.word = new_word
            # Manual text edits invalidate the OCR confidence for the word itself.
            entry.confidence = None
            entry.ocr_source = "manual"
            entry.final_engine = "manual"
            entry.manually_selected = True
            entry.alphabetical_warning = ""
            if entry.candidate_id:
                cand = self.get_review_candidate(entry.candidate_id)
                if cand is not None:
                    cand["word"] = new_word; cand["selected"] = True; cand["final_engine"] = "manual"
                    self._write_manual_override(cand, selected=True, word=new_word, engine="manual")
        self._style_entry_editor(widget, entry)

    def focus_next(self, widget: tk.Widget) -> str:
        widget.tk_focusNext().focus_set(); return "break"

    def focus_previous(self, widget: tk.Widget) -> str:
        widget.tk_focusPrev().focus_set(); return "break"

    def _delete_aligned_simplified_entry(self, entry: WordEntry) -> None:
        """Delete the simplified companion belonging to one main-page row.

        Original and simplified headwords are a one-to-one aligned pair keyed
        by the marker coordinates.  Deleting a row from the main window must
        therefore remove its simplified sidecar record too, including any
        unsaved copy currently held by an open proofreading window.
        """
        if not self.current_page:
            return
        stem = self.current_page.stem
        key = simplified_entry_key(entry.x, entry.y)
        review = getattr(self, "review_window", None)
        removed_from_review_cache = False
        if review is not None and getattr(review, "_rendered_page_stem", "") == stem:
            try:
                records = review._simplified_page_records(stem)
                if key in records:
                    records.pop(key, None)
                    review._simplified_dirty_pages.add(stem)
                    removed_from_review_cache = True
            except Exception:
                removed_from_review_cache = False
        path = simplified_review_path_for_image(self.current_page)
        if removed_from_review_cache and review is not None:
            try:
                review._persist_simplified_page(stem)
                return
            except Exception:
                pass
        records = read_simplified_records(path)
        if key in records:
            records.pop(key, None)
            write_simplified_records(path, stem, records)

    def delete_entry(self, entry: WordEntry) -> str:
        if not self._claim_page_for_manual_edit():
            return "break"
        self._sync_entry_editor_texts()
        self._delete_aligned_simplified_entry(entry)
        if entry in self.entries:
            self.entries.remove(entry)
        self.redraw()
        review = getattr(self, "review_window", None)
        if review is not None and getattr(review, "_rendered_page_stem", "") == (self.current_page.stem if self.current_page else ""):
            try:
                review.render_rows()
            except tk.TclError:
                pass
        return "break"

    def _guard_transformed_geometry(self, action: str) -> bool:
        if not transformed_geometry_pending(self.settings):
            return True
        message = (
            f"{action}尚未启用 {self.settings.layout_transform} 的完整 原图坐标适配；"
            "为避免写入错误 PDIC 或方向错误的切图，本次操作已取消。"
        )
        self.status_var.set(message)
        return False

    def auto_detect_current(
        self, clicked_x: int | None = None, force_paddle_refresh: bool = False,
    ) -> None:
        self._detection_controller_for_call().auto_detect_current(
            clicked_x=clicked_x,
            force_paddle_refresh=force_paddle_refresh,
        )

    def _detection_controller_for_call(self) -> DetectionController:
        controller = self.__dict__.get("detection_controller")
        if controller is None:
            controller = DetectionController(self)
            self.__dict__["detection_controller"] = controller
        return controller

    def paddle_detect_current(self, force_refresh: bool = False) -> None:
        self._detection_controller_for_call().paddle_detect_current(force_refresh)


    def refine_lines_selected_scope(self, *, fixed_half_gutter: bool = False) -> None:
        """Align all saved PDIC markers near proven first-row ink without OCR."""
        if not self.guard() or not self.apply_quick_settings(show_status=False):
            return
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再精修画线。")
            return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc)
            return
        if not indices:
            return

        first = self.project.images[indices[0]].name
        last = self.project.images[indices[-1]].name
        if not messagebox.askyesno(
            "精修Y（固定半栏距）" if fixed_half_gutter else "精修画线",
            f"精修所选 {len(indices)} 页：\n"
            f"{first}" + (f" → {last}" if len(indices) > 1 else "") +
            ("\n\n快速模式：临时填白插图，使用固定栏宽及两侧半栏距；不做逐页版式识别。\n"
             if fixed_half_gutter else "\n\n请先去设置中心的精修Y调整参数。\n") +
            "全部已有画线（含人工线）参与精修，不会新增或删除画线；"
            "在首行上缘附近寻找整栏空白Y；无安全位置则保留旧线。继续？",
            parent=self,
        ):
            return

        try:
            self._flush_deferred_page_save()
            self._sync_entry_editor_texts()
            self.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            self.show_error("精修画线准备失败", exc)
            return

        project = self.project
        pages = list(project.images)
        settings = replace(self.settings)
        settings.paddle_refine_separator_y = True
        from .marker_refinement_parallel import (
            configured_refine_workers, refinement_uses_page_layout,
            refine_page_job, commit_refined_page_result,
        )
        workers = configured_refine_workers(
            len(indices), settings=settings, fixed_half_gutter=fixed_half_gutter,
            cache_pages=tuple((pages[i], i) for i in indices),
        )

        def job_builder(index: int, _position: int, _total: int):
            return (str(pages[index]), settings, index, fixed_half_gutter,
                    workers > 1 and refinement_uses_page_layout(settings)
                    and not fixed_half_gutter)

        def page_owned(index: int) -> bool:
            with self._batch_state_lock:
                return self._batch_page_states.get(int(index)) == "processing"

        def save_result(index: int, computed):
            return commit_refined_page_result(index, computed, page_owned)

        def done(completed, total, stopped, results, error) -> None:
            if error is not None:
                return
            moved = sum(int((row or {}).get("moved", 0)) for row in results)
            skipped = [row for row in results if (row or {}).get("skipped")]
            uncertain = sum(int((row or {}).get("unverified", 0)) for row in results)
            max_delta = max(
                [int((row or {}).get("max_delta", 0)) for row in results] or [0]
            )
            parts = [f"移动 {moved} 条", f"最大允许位移 {max_delta}px",
                     f"计算进程 {workers}"]
            if uncertain:
                parts.append(f"{uncertain} 条未确认全栏空白")
            if skipped:
                parts.append(f"跳过 {len(skipped)} 页")
                parts.append("；".join(
                    f"{row['page']}: {str(row.get('reason', ''))[:70]}"
                    for row in skipped[:3]
                ))
            if stopped:
                parts.insert(0, f"提前停止 {completed}/{total} 页")
            self.status_var.set("精修画线完成：" + "；".join(parts))

        self._start_parallel_batch_task(
            "精修画线", indices, refine_page_job, job_builder, save_result, done,
            item_label=lambda i: pages[i].name,
            max_workers=workers, respect_cpu_workers=True,
            foreground_page_edit=True, allow_pdic_edits=True,
            isolate_worker=True,
        )

    def ocr_ordinary_lines_text_selected_scope(self) -> None:
        """OCR text for existing ordinary markers without changing geometry."""
        if not guard_ocr_action_selection(self):
            return
        if not self.guard() or not self.apply_quick_settings(show_status=False):
            return
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再执行普通画线后OCR文字。")
            return
        if not self._guard_transformed_geometry("普通画线后OCR文字"):
            return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc)
            return
        if not indices:
            return

        existing = [
            index for index in indices
            if read_pdic(pdic_path(self.project.images[index]))
        ]
        if not existing:
            self.status_var.set("所选范围没有已有画线可执行OCR文字识别")
            return

        if len(existing) > 1 and not messagebox.askyesno(
            "普通画线后OCR文字",
            f"将对 {len(existing)} 个已有画线的页面逐条调用共享 OCR 通道。\n\n"
            "重新 OCR 并覆盖已有的自动 OCR 文本；明确人工选定的词条保留；"
            "不会新增、删除或移动任何画线。继续？",
            parent=self,
        ):
            return

        try:
            self._flush_deferred_page_save()
            self._sync_entry_editor_texts()
            self.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            self.show_error("普通画线后OCR文字准备失败", exc)
            return

        project = self.project
        settings = replace(self.settings)
        rules = load_replace_rules(replace_rules_path(project.root))
        filter_path = headword_filter_rules_path(
            project.root, HEADWORD_FILTER_RULES_FILENAME
        )
        profile_path = filter_path.parent / PROFILE_FILENAME
        pages_info = {i: self.pages_tuple(i) for i in existing}

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            entries = read_pdic(pdic_path(page))
            original_count = len(entries)
            original_coords = [(int(entry.x), int(entry.y)) for entry in entries]
            protected_words = {
                (int(entry.x), int(entry.y)): str(entry.word or "")
                for entry in entries
                if bool(entry.manually_selected)
            }
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            sections = read_page_sections(page)
            updated, stats = ocr_existing_entry_words_from_markers(
                image,
                entries,
                settings,
                rules,
                profile_page_index=index,
                page_sections=sections,
                profile_path=profile_path,
                only_blank=False,
            )
            if len(updated) != original_count:
                raise RuntimeError(
                    f"{page.name} OCR文字前后画线数变化："
                    f"{original_count} → {len(updated)}"
                )
            if [(int(entry.x), int(entry.y)) for entry in updated] != original_coords:
                raise RuntimeError(f"{page.name} OCR文字意外修改了画线坐标")
            for entry in updated:
                key = (int(entry.x), int(entry.y))
                if key in protected_words and str(entry.word or "") != protected_words[key]:
                    raise RuntimeError(f"{page.name} OCR文字意外覆盖了人工选定文本")
            write_pdic(pdic_path(page), updated, image.width, pages_info[index])
            export_ocred(
                qt_root(project.root) / f"{page.stem}.OCRed",
                [entry.word for entry in updated],
            )
            return {"index": int(index), **stats}

        def done(completed, total, stopped, results, error):
            if error is not None:
                return
            if self.current_index in existing and not self._batch_foreground_pages:
                self.load_page(self.current_index, skip_current_save=True)
            filled = sum(int((row or {}).get("filled", 0)) for row in results)
            large = sum(int((row or {}).get("large", 0)) for row in results)
            regular = sum(int((row or {}).get("regular", 0)) for row in results)
            failed = sum(int((row or {}).get("failed", 0)) for row in results)
            skipped = sum(
                int((row or {}).get("skipped_existing", 0))
                + int((row or {}).get("skipped_manual", 0))
                for row in results
            )
            prefix = (
                f"普通画线后OCR文字已停止：{completed}/{total} 页"
                if stopped
                else f"普通画线后OCR文字完成：{completed}/{total} 页"
            )
            self.status_var.set(
                f"{prefix}；OCR 覆盖/识别 {filled} 条"
                f"（普通框 {regular}，大字框 {large}）"
                f"；未识别 {failed} 条；保留人工选定 {skipped} 条"
            )

        self._start_batch_task(
            "普通画线后OCR文字",
            existing,
            worker,
            done,
            item_label=lambda index: project.images[index].name,
            foreground_page_edit=True, allow_pdic_edits=True,
        )

    def run_combined_draw_action(self) -> None:
        self._detection_controller_for_call().run_combined_draw_action()


    def run_ocr_draw_action(self) -> None:
        self._detection_controller_for_call().run_ocr_draw_action()


    def run_normal_draw_action(self) -> None:
        self._detection_controller_for_call().run_normal_draw_action()

    def run_ocr_draw(self, scope: str, force_refresh: bool) -> None:
        self._detection_controller_for_call().run_ocr_draw(scope, force_refresh)


    def _detect_pages(self, indices: list[int], *, method: str, force_refresh: bool) -> None:
        if method == "left_edge":
            # One physical page must never be submitted to multiple writer
            # processes in the same batch, even through an unusual API caller.
            indices = list(dict.fromkeys(indices))
        if not self.project or not indices:
            self.status_var.set("没有需要处理的页面"); return
        if not self._guard_transformed_geometry("批量画线"):
            return
        label = {
            "combined": "融合画线",
            "paddleocr": "OCR画线",
            "left_edge": "普通画线",
        }.get(method, "画线")
        if len(indices) > 1 and not messagebox.askyesno(
            label,
            f"将对 {len(indices)} 页执行{label}并重写这些页面的 PDIC 画线。\n\n"
            "处理期间会显示进度，可暂停或停止；暂停/停止会在当前页完成后安全生效。继续？",
            parent=self,
        ):
            return
        from .layout.mask_source_guard import missing_saved_illustrations, detection_mask_source_path
        missing_ppp = missing_saved_illustrations(
            (self.project.images[i] for i in indices), self.settings,
        )
        if missing_ppp:
            names = "、".join(page.name for page in missing_ppp[:4])
            suffix = f" 等 {len(missing_ppp)} 页" if len(missing_ppp) > 4 else ""
            message = (f"这些页面缺少已保存的 PPP 插图数据：{names}{suffix}。\n"
                       "请先运行插图识别，或在设置中心→插图关闭‘使用已有的插图数据’。\n"
                       "本次画线未开始，其他页面的 PDIC 不会被部分覆盖。")
            self.status_var.set(message)
            messagebox.showerror("Layout 插图复用检查失败", message, parent=self)
            return
        import time
        batch_started_at = time.time()
        self.save_pdic(silent=True)
        # Auto illustration detection persists PPP in workers. Flush any
        # foreground manual edits first so the worker's AUTO merge preserves
        # them. PPP-reuse mode is read-only and must never fabricate a missing
        # PPP file.
        if (
            method == "left_edge"
            and bool(getattr(self.settings, "layout_mask_illustrations", False))
            and not bool(getattr(self.settings, "layout_mask_illustrations_use_existing", False))
            and self.current_page is not None
        ):
            from .io.formats import write_ppp
            self._sync_polygon_label_texts()
            self._save_normalized_ppp()
        self.settings.detection_method = method
        settings = replace(self.settings)
        # Set the process environment *before* spawning workers. Snapshot the
        # values at the start of this batch to keep child processes consistent.
        os.environ["PICTURE_CAPTURE_DRAW_PROFILE"] = (
            "1" if bool(getattr(settings, "draw_performance_profile", False)) else "0"
        )
        os.environ["PICTURE_CAPTURE_REUSE_PREPARED_ANALYSIS"] = (
            "1" if bool(getattr(settings, "reuse_prepared_analysis", False)) else "0"
        )
        project = self.project
        pages_info = {i: self.pages_tuple(i) for i in indices}
        filter_path = headword_filter_rules_path(project.root, HEADWORD_FILTER_RULES_FILENAME)
        from .ordinary.parallel import ordinary_draw_workers
        ordinary_workers = (
            ordinary_draw_workers(len(indices)) if method == "left_edge" else 1
        )
        from .ordinary.gpu_pipeline import staged_pipeline_enabled
        from .ordinary.cpu_pool import cpu_pool_enabled, cpu_pool_config
        cpu_pool = bool(
            method == "left_edge"
            and cpu_pool_enabled(settings, len(indices))
        )
        cpu_pool_workers, cpu_inference_threads = (
            cpu_pool_config(len(indices)) if cpu_pool else (1, 1)
        )
        # CPU-only takes priority over staged GPU mode.
        gpu_staged = bool(
            method == "left_edge" and not cpu_pool
            and staged_pipeline_enabled(settings, len(indices))
        )
        if cpu_pool:
            ordinary_workers = cpu_pool_workers
        elif gpu_staged:
            # Never duplicate CUDA models across workers.
            ordinary_workers = 2
        normal_executor = (
            ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
            if method == "left_edge" and ordinary_workers <= 1 else None
        )

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            from .quality.draw_performance_profile import enabled as profile_enabled, record_page
            tracing = profile_enabled() and method in {"paddleocr", "combined"}
            stages = {}
            trace_tick = time.perf_counter()
            resume_dependencies = ()
            if (
                method in {"paddleocr", "combined"}
                and settings.ocr_resume_completed_pages
                and not force_refresh
            ):
                from .persistence.project_storage import page_sections_read_path_for_image
                from .ocr.page_resume import validated_resume
                resume_dependencies = (
                    filter_path,
                    project_profile_path(project.root),
                    page_sections_read_path_for_image(page),
                    *( (replace_rules_path(project.root),) if method == "combined" else () ),
                )
                saved = pdic_path(page)
                previous_count = validated_resume(
                    ocr_cache_root(project.root), page, saved,
                    page_index=index, method=method, settings=settings,
                    dependencies=resume_dependencies,
                )
                if previous_count is not None:
                    return {"index": int(index), "count": previous_count, "resumed": True}
            if normal_executor is not None:
                if cpu_pool:
                    from .ordinary.cpu_pool import cpu_ordinary_page_job
                    count = normal_executor.submit(
                        cpu_ordinary_page_job, str(page), settings,
                        pages_info[index], index, cpu_inference_threads,
                    ).result()
                else:
                    count = normal_executor.submit(
                        detect_entries_job, str(page), settings, pages_info[index], index
                    ).result()
                return {"index": int(index), "count": int(count)}
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            if tracing:
                stages["ocr_image_load"] = time.perf_counter() - trace_tick
                trace_tick = time.perf_counter()
            cache_path = ocr_cache_root(project.root) / f"{page.stem}.json" if method in {"paddleocr", "combined"} else None
            sections = read_page_sections(page)
            entries, _geometry = detect_entries(
                image, settings, paddle_cache_path=cache_path,
                force_paddle_refresh=force_refresh,
                paddle_filter_rules_path=filter_path,
                profile_page_index=index,
                page_sections=sections,
                source_image_path=detection_mask_source_path(
                    page, settings, ordinary=method == "left_edge",
                ),
            )
            if tracing:
                stages["ocr_detect_entries"] = time.perf_counter() - trace_tick
                trace_tick = time.perf_counter()
            text_stats = None
            if method == "combined":
                original_coords = [
                    (int(entry.x), int(entry.y)) for entry in entries
                ]
                entries, text_stats = ocr_existing_entry_words_from_markers(
                    image,
                    entries,
                    settings,
                    load_replace_rules(replace_rules_path(project.root)),
                    profile_page_index=index,
                    page_sections=sections,
                    profile_path=project_profile_path(project.root),
                    only_blank=True,
                )
                if [
                    (int(entry.x), int(entry.y)) for entry in entries
                ] != original_coords:
                    raise RuntimeError(
                        f"{page.name} 融合画线自动补字意外修改了画线坐标"
                    )
            if tracing:
                stages["ocr_marker_text_fill"] = time.perf_counter() - trace_tick
                trace_tick = time.perf_counter()
            saved_pdic = pdic_path(page)
            if method in {"paddleocr", "combined"}:
                # Preserve manual PDIC before automated OCR overwrites it.
                from .ocr.pdic_preservation import preserve_prior_pdic
                preserve_prior_pdic(project.root, page, saved_pdic)
            write_pdic(saved_pdic, entries, image.width, pages_info[index])
            if tracing:
                stages["ocr_preserve_and_pdic"] = time.perf_counter() - trace_tick
                trace_tick = time.perf_counter()
            result = {"index": int(index), "count": len(entries)}
            if method in {"paddleocr", "combined"} and cache_path is not None:
                # The OCR cache is pre-Layout. Read the *actual saved PDIC*
                # and record final moves/removals/rescues separately. This
                # audit never modifies PDIC and failure must not lose a page.
                try:
                    from .ocr.final_decisions import record_final_decisions
                    result["final_audit"] = record_final_decisions(
                        cache_path, saved_pdic, entries,
                        tolerance=max(5, round(settings.character_height * 0.45)),
                    )
                except (OSError, ValueError, TypeError) as exc:
                    result["final_audit_error"] = f"{type(exc).__name__}: {exc}"
            if method in {"paddleocr", "combined"} and settings.ocr_resume_completed_pages:
                if not resume_dependencies:
                    # A forced OCR rerun bypasses prior checkpoints but still
                    # writes a *new* completed checkpoint for later resumption.
                    from .persistence.project_storage import page_sections_read_path_for_image
                    resume_dependencies = (
                        filter_path,
                        project_profile_path(project.root),
                        page_sections_read_path_for_image(page),
                        *((replace_rules_path(project.root),) if method == "combined" else ()),
                    )
                from .ocr.page_resume import write_page_resume
                try:
                    write_page_resume(
                        ocr_cache_root(project.root), page, pdic_path(page),
                        page_index=index, method=method, settings=settings,
                        marker_count=len(entries), dependencies=resume_dependencies,
                    )
                except (OSError, ValueError, TypeError) as exc:
                    result["resume_checkpoint_error"] = f"{type(exc).__name__}: {exc}"
            if text_stats:
                result.update({
                    "text_filled": int(text_stats.get("filled", 0)),
                    "text_regular": int(text_stats.get("regular", 0)),
                    "text_large": int(text_stats.get("large", 0)),
                    "text_failed": int(text_stats.get("failed", 0)),
                })
            if tracing:
                stages["ocr_audit_resume"] = time.perf_counter() - trace_tick
                record_page(page, index, stages, mode=method)
            return result

        def done(completed, total, stopped, results, error):
            if normal_executor is not None:
                normal_executor.shutdown(wait=False, cancel_futures=True)
            if error is not None:
                return
            self.load_page(self.current_index)
            quality_text = ""
            if method in {"paddleocr", "combined"}:
                self._refresh_page_quality_colors()
                quality_text = "；页面列表已按 OCR 一致性/质量状态更新"
                resumed = sum(
                    1 for row in results if isinstance(row, dict) and row.get("resumed")
                )
                if resumed:
                    quality_text += f"；经完整校验断点跳过 {resumed} 页"
                checkpoint_failures = sum(
                    1 for row in results
                    if isinstance(row, dict) and row.get("resume_checkpoint_error")
                )
                if checkpoint_failures:
                    quality_text += f"；{checkpoint_failures} 页无法记录恢复点"
                final_stats = [
                    row.get("final_audit")
                    for row in results
                    if isinstance(row, dict) and isinstance(row.get("final_audit"), dict)
                ]
                if final_stats:
                    quality_text += (
                        f"；最终PDIC对齐 {sum(int(v.get('linked', 0)) for v in final_stats)} 条"
                        f"，Layout等独立候选 {sum(int(v.get('unmatched_final', 0)) for v in final_stats)} 条"
                    )
                audit_errors = sum(
                    1 for row in results
                    if isinstance(row, dict) and row.get("final_audit_error")
                )
                if audit_errors:
                    quality_text += f"；{audit_errors} 页最终决策记录未能保存（PDIC已保存）"
                if method == "combined":
                    filled = sum(
                        int((row or {}).get("text_filled", 0))
                        for row in results
                    )
                    regular = sum(
                        int((row or {}).get("text_regular", 0))
                        for row in results
                    )
                    large = sum(
                        int((row or {}).get("text_large", 0))
                        for row in results
                    )
                    failed = sum(
                        int((row or {}).get("text_failed", 0))
                        for row in results
                    )
                    quality_text += (
                        f"；普通救漏自动补字 {filled} 条"
                        f"（普通框 {regular}，大字框 {large}，未识别 {failed}）"
                    )
            else:
                rows = [
                    value for value in results
                    if isinstance(value, dict)
                    and isinstance(value.get("count"), (int, float))
                    and int(value.get("count", -1)) >= 0
                ]
                counts = [int(row["count"]) for row in rows]
                median_count = float(statistics.median(counts)) if counts else 0.0
                suspect_rows: list[dict] = []
                for row in rows:
                    count = int(row["count"])
                    if count == 0:
                        suspect_rows.append(row)
                    elif len(counts) >= 5 and median_count >= 8:
                        if count < median_count * 0.45 or count > median_count * 1.80:
                            suspect_rows.append(row)
                if counts:
                    quality_text = f"；每页画线数中位数 {median_count:g}"
                if suspect_rows:
                    names = [
                        project.images[int(row["index"])].name
                        for row in suspect_rows[:3]
                        if 0 <= int(row.get("index", -1)) < len(project.images)
                    ]
                    more = "…" if len(suspect_rows) > 3 else ""
                    quality_text += (
                        f"；{len(suspect_rows)} 页画线数异常，建议优先复核"
                        + (f"（{', '.join(names)}{more}）" if names else "")
                    )
            from .quality.inference_monitor import recent_model_events
            elapsed_seconds = max(0.001, time.time() - batch_started_at)
            observed_events = recent_model_events(batch_started_at)
            observed_devices = sorted({str(row["device"]) for row in observed_events})
            observed_pids = {int(row["pid"]) for row in observed_events}
            inferred = "/".join(observed_devices) if observed_devices else "未记录（可能命中缓存）"
            monitor_text = (
                f"；耗时 {elapsed_seconds:.1f}s"
                f"；速度 {completed / elapsed_seconds:.2f} 页/s"
                f"；模型设备 {inferred}"
                f"；模型实例进程 {len(observed_pids)}"
            )
            if cpu_pool:
                monitor_text += f"；CPU 工作进程配置 {cpu_pool_workers}"
            elif gpu_staged:
                monitor_text += "；GPU 推理生产者 1 / CPU 消费者最多 2"
            elif method in {"paddleocr", "combined"}:
                monitor_text += "；OCR 页面串行调度"
            if observed_events:
                observed_dnn = sorted({
                    str(row["mkldnn"]) for row in observed_events
                    if row.get("device") == "cpu"
                })
                if observed_dnn:
                    monitor_text += f"；oneDNN 配置 {'/'.join(observed_dnn)}"
            quality_text += monitor_text
            from .quality.draw_performance_profile import (
                enabled as profiling_enabled, recent_profiles, export_batch_report,
            )
            if profiling_enabled():
                page_names = {str(project.images[i]) for i in indices}
                stage_rows = recent_profiles(batch_started_at, pages=page_names)
                try:
                    report_path = export_batch_report(
                        stage_rows, label=label, elapsed_seconds=elapsed_seconds,
                        completed=completed, settings=settings,
                    )
                except Exception as exc:
                    quality_text += f"；性能报告导出失败：{exc}"
                else:
                    quality_text += (
                        f"；性能报告已保存：{report_path}"
                        if stage_rows else
                        f"；性能报告已保存（没有匹配到逐页计时数据）：{report_path}"
                    )
            suffix = "（强制重新识别）" if method in {"paddleocr", "combined"} and force_refresh else ""
            skipped = int(getattr(self, "_batch_skipped_count", 0))
            skip_text = f"，人工锁定跳过 {skipped} 页" if skipped else ""
            if stopped:
                self.status_var.set(
                    f"{label}{suffix}已停止：处理进度 {completed}/{total}{skip_text}；"
                    f"结果已保留{quality_text}"
                )
            else:
                self.status_var.set(
                    f"{label}{suffix}完成：{completed}/{total}{skip_text}{quality_text}"
                )

        if gpu_staged:
            from .ordinary.gpu_pipeline import (
                prepare_gpu_layout_job, detect_entries_staged_job,
            )
            started = self._start_parallel_batch_task(
                label, indices, detect_entries_staged_job,
                lambda index, _position, _total: (
                    str(project.images[index]), settings, pages_info[index], index,
                ),
                result_consumer=lambda index, count: {
                    "index": int(index), "count": int(count),
                },
                on_done=done,
                item_label=lambda index: project.images[index].name,
                max_workers=ordinary_workers,
                foreground_page_edit=True,
                page_indexer=lambda index: int(index),
                gpu_preflight_func=prepare_gpu_layout_job,
                gpu_job_builder=lambda index, _position, _total: (
                    str(project.images[index]), settings, index,
                ),
            )
        elif cpu_pool and cpu_pool_workers > 1:
            from .ordinary.cpu_pool import cpu_ordinary_page_job
            started = self._start_parallel_batch_task(
                label, indices, cpu_ordinary_page_job,
                lambda index, _position, _total: (
                    str(project.images[index]), settings,
                    pages_info[index], index, cpu_inference_threads,
                ),
                result_consumer=lambda index, count: {
                    "index": int(index), "count": int(count),
                },
                on_done=done,
                item_label=lambda index: project.images[index].name,
                max_workers=cpu_pool_workers,
                foreground_page_edit=True,
                page_indexer=lambda index: int(index),
            )
        elif method == "left_edge" and ordinary_workers > 1:
            # Dormant legacy parallel path: the ordinary_draw_workers safety
            # policy always returns 1 unless a separately validated design
            # deliberately changes it. No duplicate GPU inference permitted.
            started = self._start_parallel_batch_task(
                label, indices, detect_entries_job,
                lambda index, _position, _total: (
                    str(project.images[index]), settings, pages_info[index], index,
                ),
                result_consumer=lambda index, count: {
                    "index": int(index), "count": int(count),
                },
                on_done=done,
                item_label=lambda index: project.images[index].name,
                max_workers=ordinary_workers,
                foreground_page_edit=True,
                page_indexer=lambda index: int(index),
            )
        else:
            started = self._start_batch_task(
                label, indices, worker, done,
                item_label=lambda index: project.images[index].name,
                foreground_page_edit=True, page_indexer=lambda index: int(index),
            )
        if not started and normal_executor is not None:
            normal_executor.shutdown(wait=False, cancel_futures=True)

    def clear_entries(self) -> None:
        if self.guard() and messagebox.askyesno("清除画线", "清除当前页全部词条标记？", parent=self):
            self.entries.clear(); self.redraw()

    def clear_text(self) -> None:
        from .proofreading.pdic_text_cleanup import clear_selected_scope
        clear_selected_scope(self)


    def _ordered_entries_reading_order(self) -> list[WordEntry]:
        """Return entries in reading order without mutation."""
        image = self.__dict__.get("image")
        entries = list(self.__dict__.get("entries") or [])
        settings = self.__dict__.get("settings")
        if image is None or settings is None or not entries:
            return entries
        return sort_entries_reading_order(
            entries, self._get_cached_display_geometry(), self.page_sections,
        )

    def _sort_entries_reading_order(self) -> None:
        """Keep manual and OCR entries in one geometry-based reading order."""
        entries = self.__dict__.get("entries")
        if entries is None:
            return
        entries[:] = self._ordered_entries_reading_order()

    def pages_tuple(self, index: int | None = None) -> tuple[str, str, str]:
        assert self.project
        i = self.current_index if index is None else index
        current = self.project.images[i].stem
        previous = self.project.images[i - 1].stem if i > 0 else "@"
        following = self.project.images[i + 1].stem if i + 1 < len(self.project.images) else "@"
        return current, previous, following

    def save_pdic(self, silent: bool = False, sync_editors: bool = True) -> None:
        if not self.project or not self.current_page or self.image is None: return
        if self.__dict__.get("_batch_active", False) and not self._can_save_current_during_batch_navigation():
            return
        from .proofreading.transactions import _recovery_path
        if _recovery_path(self.current_page).exists():
            raise RuntimeError("Unresolved R3 transaction; refusing PDIC save")
        if self.__dict__.get("_deferred_save_uncertain", False):
            raise RuntimeError("R3 PDIC write outcome uncertain; reload/recover before saving")
        # Commit live state; cancel any older queued checkbox snapshot.
        deferred_job = self.__dict__.get("_deferred_save_job")
        if deferred_job is not None:
            try:
                self.after_cancel(deferred_job)
            except tk.TclError:
                pass
        self.__dict__["_deferred_save_job"] = None
        # Keep the queued snapshot until the actual PDIC publication succeeds.
        from .proofreading.save_safety import protect_app_pdic_commit
        with protect_app_pdic_commit(self):
            # Review edits bypass stale main-canvas editor values.
            if sync_editors:
                self._sync_entry_editor_texts()
            self._sort_entries_reading_order()
            changed = write_pdic(pdic_path(self.current_page), self.entries, self.image.width, self.pages_tuple())
        self.__dict__["_deferred_save_snapshot"] = None
        self.__dict__["_deferred_save_page"] = None
        self.__dict__["_deferred_save_uncertain"] = False
        self._last_pdic_write_changed = changed
        self._flush_pending_manual_override()
        self._flush_proofreading_candidate_evidence()
        self._flush_proofreading_add_evidence()
        if changed:
            self._refresh_word_fill_check_from_line_count(self.current_index, len(self.entries), persist=True)
            self._update_page_row(self.current_index)
        if not silent: self.status_var.set(f"已保存 {pdic_path(self.current_page).name}" if changed else "内容无变化，无需保存")

    def _sync_entry_editor_texts(self) -> None:
        """Commit editor values to the exact Entry objects they were created for."""
        active_ids = {id(entry) for entry in self.entries}
        for editor, entry in self.entry_editor_bindings:
            if id(entry) not in active_ids:
                continue
            try:
                entry.word = editor.get().strip()
            except tk.TclError:
                # A redraw may already have destroyed the old widget.
                continue

    def save_all(self) -> None:
        if not self.guard(): return
        self.save_pdic()
        self._save_normalized_ppp()

    def save_settings(self) -> None:
        if self.project:
            self.settings.to_json(settings_path(self.project.root))
            self.status_var.set("参数已保存")

    def toggle_autosave(self) -> None:
        if self.autosave_job:
            self.after_cancel(self.autosave_job)
            self.autosave_job = None
        if self.autosave_var.get():
            delay = max(1, round(self.settings.batch_interval * 1000))
            self.autosave_job = self.after(delay, self.autosave_tick)

    def autosave_tick(self) -> None:
        self.autosave_job = None
        if not self.autosave_var.get():
            return
        try:
            # Autosave PDIC only for editable batch pages; never autosave PPP
            # while a background batch owns the current page.
            if self._batch_active and not self._can_save_current_during_batch_navigation():
                return
            if self.project and self.current_page:
                self._last_pdic_write_changed = False
                review = self.review_window
                review_saved = False
                if review is not None:
                    try:
                        if review.winfo_exists():
                            review_saved = bool(review.autosave_commit())
                        else:
                            self.review_window = None
                    except tk.TclError:
                        self.review_window = None
                if not review_saved:
                    self.save_pdic(silent=True)
                polygon_changed = False if self._batch_active else self._save_normalized_ppp()
                if self._last_pdic_write_changed or polygon_changed:
                    self.status_var.set("已自动保存")
        except (OSError, RuntimeError, ValueError) as exc:
            # In particular, never fall back to stale main-canvas buffers when
            # ReviewWindow's PDIC transaction failed.
            self.status_var.set(f"自动保存失败，校对修改仍保留：{exc}")
        finally:
            # Failed I/O must not silently disable the next autosave tick.
            self.toggle_autosave()

    def open_settings(self, initial_tab: str | None = None) -> None:
        # Pull unsaved quick-panel values (notably OCR language) into the settings
        # object first so language-dependent options are immediately correct.
        if not self.apply_quick_settings(show_status=False, persist=False):
            return
        existing = self.__dict__.get("_settings_dialog")
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.select_tab(initial_tab)
                    existing.deiconify()
                    existing.lift()
                    return
            except tk.TclError:
                pass
        dialog = SettingsDialog(self, initial_tab=initial_tab)
        self._settings_dialog = dialog
        dialog.bind(
            "<Destroy>",
            lambda event, w=dialog: self.__dict__.pop("_settings_dialog", None)
            if event.widget is w else None,
            add="+",
        )

    def open_project_profile(self, new_project: bool = False) -> None:
        if not self.project:
            messagebox.showinfo("尚未打开", "请先打开或新建词典项目。", parent=self)
            return
        if self._batch_active:
            self.status_var.set("批量任务运行中，结束或停止后再打开 Project Profile。")
            return
        # Keep the wizard's working copy aligned with any unsaved/debounced
        # quick-panel edits made immediately before opening Project Profile.
        if not self.apply_quick_settings(show_status=False, persist=False, silent_errors=True):
            return
        existing = self.__dict__.get("_project_profile_wizard")
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_force()
                    return
            except tk.TclError:
                pass
        wizard = ProjectProfileWizard(self, new_project=new_project)
        self._project_profile_wizard = wizard
        wizard.bind(
            "<Destroy>",
            lambda event, w=wizard: self.__dict__.pop("_project_profile_wizard", None)
            if event.widget is w else None,
            add="+",
        )

    def open_project_details(self) -> None:
        self.open_settings(initial_tab="project")

    def ocr_current(self) -> None:
        """Backward-compatible current-page OCR, executed off the Tk thread."""
        if self._batch_active:
            self.status_var.set("后台画线任务运行中，暂不启动前台 OCR；可进行人工文本校对。")
            return
        if not self.guard() or not self.entries:
            return
        if not self._guard_transformed_geometry("OCR"):
            return

        project = self.project
        page = self.current_page
        page_index = int(self.current_index)
        settings = replace(self.settings)
        ordered_entries = [replace(entry) for entry in self._ordered_entries_reading_order()]
        page_sections = list(self.page_sections)
        pages_meta = self.pages_tuple(page_index)
        rules_path = replace_rules_path(project.root)
        ocred_path = qt_root(project.root) / f"{page.stem}.OCRed"
        engine_name = OCR_ENGINE_LABELS.get(settings.ocr_engine, settings.ocr_engine)

        def worker(_item, _position: int, _total: int):
            rules = load_replace_rules(rules_path)
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            texts = ocr_entries(
                image, ordered_entries, settings, rules,
                profile_page_index=page_index, page_sections=page_sections,
            )
            for entry, text in zip(ordered_entries, texts):
                entry.word = text
            export_ocred(ocred_path, texts)
            write_pdic(pdic_path(page), ordered_entries, image.width, pages_meta)
            return texts

        def done(_completed, _total, stopped, results, error):
            if error is not None or stopped or not results:
                return
            if self.project is not project or self.current_page != page:
                return
            texts = list(results[-1])
            current = self._ordered_entries_reading_order()
            if len(current) == len(texts):
                for entry, text in zip(current, texts):
                    entry.word = text
                self.redraw()
            else:
                self._request_page_load(
                    page_index, current_already_saved=True, force=True,
                )
            self.status_var.set(f"{engine_name} OCR 完成：{len(texts)} 个词条")

        self._start_batch_task(
            "当前页 OCR", [page_index], worker, done,
            item_label=lambda _item: page.name,
        )

    def _export_controller_for_call(self) -> ExportController:
        controller = self.__dict__.get("export_controller")
        if controller is None:
            controller = ExportController(self)
            self.__dict__["export_controller"] = controller
        return controller

    def export_text(self) -> None:
        self._export_controller_for_call().export_text()

    def import_text(self) -> None:
        self._export_controller_for_call().import_text()

    def _crop_controller_for_call(self) -> CropController:
        controller = self.__dict__.get("crop_controller")
        if controller is None:
            controller = CropController(self)
            self.__dict__["crop_controller"] = controller
        return controller

    def split_lines_current(self) -> None:
        self._crop_controller_for_call().split_lines_current()

    def split_single_lines_selected_scope(self) -> None:
        self._crop_controller_for_call().split_single_lines_selected_scope()

    def export_unlined_rows_selected_scope(self) -> None:
        self._crop_controller_for_call().export_unlined_rows_selected_scope()

    def split_whole_current(self) -> None:
        self._crop_controller_for_call().split_whole_current()

    def _crop_settings_defaults(self) -> dict:
        return _normalize_crop_settings_payload(None, self.settings)

    def _load_crop_settings(self) -> dict:
        if not self.project:
            return self._crop_settings_defaults()
        from .crop.settings import load_crop_settings
        return load_crop_settings(self.project.root, self.settings)


    def open_crop_settings(self) -> None:
        """Open the integrated Settings Center crop-settings tab."""
        self.open_settings(initial_tab="crop")

    def split_entries_selected_scope(self) -> None:
        self._crop_controller_for_call().split_entries_selected_scope()

    def _illustration_controller_for_call(self) -> IllustrationController:
        controller = self.__dict__.get("illustration_controller")
        if controller is None:
            controller = IllustrationController(self)
            self.__dict__["illustration_controller"] = controller
        return controller

    def detect_illustrations_selected_scope(self) -> None:
        self._illustration_controller_for_call().detect_illustrations_selected_scope()

    def split_illustrations_selected_scope(self) -> None:
        self._illustration_controller_for_call().split_illustrations_selected_scope()

    def _start_illustration_crop(self, indices: list[int], config: dict) -> None:
        """Start PPP illustration export from the shared crop-settings snapshot."""
        self._illustration_controller_for_call()._start_illustration_crop(indices, config)

    def build_picdic(self) -> None:
        self._export_controller_for_call().build_picdic()

    def _order_key(self, word: str) -> tuple:
        return collation_key(
            word,
            getattr(self.settings, "headword_sort_mode", "auto"),
            getattr(self.settings, "ocr_language", "eng"),
            getattr(self.settings, "headword_custom_order", LATIN_ORDER),
            getattr(self.settings, "headword_custom_fold_accents", True),
        )

    def _order_display_key(self, word: str) -> str:
        return display_key(
            word,
            getattr(self.settings, "headword_sort_mode", "auto"),
            getattr(self.settings, "ocr_language", "eng"),
            getattr(self.settings, "headword_custom_order", LATIN_ORDER),
            getattr(self.settings, "headword_custom_fold_accents", True),
        )

    def check_headword_order(self, all_pages: bool = False) -> None:
        self._review_controller_for_call().check_headword_order(all_pages)

    def _show_text_report(self, title: str, text: str) -> None:
        win = tk.Toplevel(self); win.title(title); fit_window_to_work_area(win, 900, 650, min_width=640, min_height=460)
        frame = ttk.Frame(win, padding=6); frame.pack(fill="both", expand=True)
        box = tk.Text(frame, wrap="none", font=(preferred_font_family(win, ("Consolas", "Menlo", "DejaVu Sans Mono"), fallback_named_font="TkFixedFont"), 11))
        ybar = ttk.Scrollbar(frame, orient="vertical", command=box.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=box.xview)
        box.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        box.grid(row=0, column=0, sticky="nsew"); ybar.grid(row=0, column=1, sticky="ns"); xbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        box.insert("1.0", text); box.configure(state="disabled")

    def batch_auto_detect(self, force_paddle_refresh: bool = False) -> None:
        self._detection_controller_for_call().batch_auto_detect(force_paddle_refresh)

    def batch_ocr(self) -> None:
        self._detection_controller_for_call().batch_ocr()

    def batch_split_whole(self) -> None:
        self._crop_controller_for_call().batch_split_whole()

    def repair_pdic_order_selected_scope(self) -> None:
        self._export_controller_for_call().repair_pdic_order_selected_scope()

    def export_picdic_index(self) -> None:
        self._export_controller_for_call().export_picdic_index()

    def backup_pdic(self) -> None:
        self._export_controller_for_call().backup_pdic()

    def restore_from_pdic_backup(self) -> None:
        self._export_controller_for_call().restore_from_pdic_backup()

    def restore_from_merged_pdic(self) -> None:
        """Backward-compatible alias for old integrations."""
        self.restore_from_pdic_backup()

    def _headword_controller_for_call(self) -> HeadwordController:
        controller = self.__dict__.get("headword_controller")
        if controller is None:
            controller = HeadwordController(
                self,
                parse_words_of_pages_text=_parse_words_of_pages_text,
                fill_page_entries=_fill_page_entries,
            )
            self.__dict__["headword_controller"] = controller
        return controller

    def select_existing_headwords_file(self) -> None:
        self._headword_controller_for_call().select_existing_headwords_file()

    def fill_existing_headwords(self) -> None:
        self._headword_controller_for_call().fill_existing_headwords()

    def import_legacy_words(self) -> bool:
        """Import legacy words in a sequential background batch.

        The return value now means that an import task was started; completion is
        reported asynchronously in the status bar.
        """
        if not self.project or self._batch_active:
            return False
        project = self.project
        path = words_of_pages_default_path(project.root)
        if not path.exists():
            path_text = filedialog.askopenfilename(
                title="选择 _WordsOfPages.txt",
                filetypes=[("文本", "*.txt"), ("全部", "*")],
                parent=self,
            )
            if not path_text:
                return False
            path = Path(path_text)

        pages = list(project.images)
        pages_meta = [
            (
                page.stem,
                pages[i - 1].stem if i > 0 else "@",
                pages[i + 1].stem if i + 1 < len(pages) else "@",
            )
            for i, page in enumerate(pages)
        ]
        holder: dict[str, object] = {
            "lines": None, "rich": False, "groups": None, "words": None, "cursor": 0,
        }
        items: list[object] = ["__parse__"] + list(range(len(pages)))

        def ensure_parsed() -> None:
            if holder["lines"] is not None:
                return
            text_data, _encoding = read_text_detected(path)
            lines = [line for line in text_data.splitlines() if line.strip()]
            rich = [line for line in lines if line.count("#") >= 7]
            holder["lines"] = lines
            if len(rich) == len(lines):
                groups: dict[str, list[str]] = {}
                for line in rich:
                    groups.setdefault(line.split("#")[5], []).append(line)
                holder["rich"] = True
                holder["groups"] = groups
            else:
                holder["words"] = [line.split("#", 1)[0].strip() for line in lines]

        def worker(item, _position: int, _total: int):
            ensure_parsed()
            if item == "__parse__":
                return {"parsed": len(holder["lines"] or [])}
            index = int(item)
            page = pages[index]
            changed = False
            if bool(holder["rich"]):
                groups = holder["groups"] if isinstance(holder["groups"], dict) else {}
                rows = list(groups.get(page.stem, []))
                if rows:
                    write_text_atomic(
                        pdic_path(page), "\n".join(rows) + "\n", encoding="utf-8",
                    )
                    changed = True
            else:
                words = holder["words"] if isinstance(holder["words"], list) else []
                cursor = int(holder["cursor"])
                entries = read_pdic(pdic_path(page))
                for entry in entries:
                    if cursor >= len(words):
                        break
                    entry.word = str(words[cursor])
                    cursor += 1
                holder["cursor"] = cursor
                if entries:
                    with Image.open(page) as opened:
                        width = int(opened.width)
                    write_pdic(pdic_path(page), entries, width, pages_meta[index])
                    changed = True
            return {"index": index, "changed": changed}

        def done(_completed, _total, stopped, results, error):
            if error is not None:
                return
            changed_indices = {
                int(row["index"]) for row in results
                if isinstance(row, dict) and row.get("changed") and "index" in row
            }
            if self.project is project and self.current_index in changed_indices:
                self._request_page_load(
                    self.current_index, current_already_saved=True, force=True,
                )
            count = len(holder["lines"] or [])
            suffix = "（提前停止）" if stopped else ""
            self.status_var.set(f"已导入旧版数据：{count} 条{suffix}")

        started = self._start_batch_task(
            "导入旧版数据", items, worker, done,
            item_label=lambda item: (
                f"解析 {path.name}" if item == "__parse__"
                else pages[int(item)].name
            ),
        )
        return bool(started)

    def _default_old_new_compare_source(self) -> Path | None:
        """Return the best initial file suggestion for 【新旧比较】."""
        candidates: list[Path] = []
        if self._old_new_compare_source_path is not None:
            candidates.append(self._old_new_compare_source_path)
        if self._word_fill_source_path is not None:
            candidates.append(self._word_fill_source_path)
        if self.project is not None:
            candidates.append(resolve_wordslist_path(self.project.root, self.settings.wordslist_path))
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
        return candidates[0] if candidates else None

    def _looks_page_aware_compare_source(self, path: Path) -> bool:
        """Cheaply recognize whether a TXT carries page boundaries for comparison."""
        if not self.project or not path.is_file():
            return False
        page_stems = [page.stem for page in self.project.images]
        lookup = _build_words_page_lookup(page_stems)
        checked = 0
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                for raw in handle:
                    stripped = raw.strip()
                    if not stripped or raw.lstrip().startswith("'"):
                        continue
                    checked += 1
                    fields = raw.rstrip("\r\n").split("#")
                    if len(fields) >= 8 and _resolve_words_page_token(fields[5], page_stems, lookup) is not None:
                        return True
                    tab_fields = raw.rstrip("\r\n").split("\t", 1)
                    if len(tab_fields) == 2 and _resolve_words_page_token(tab_fields[0], page_stems, lookup) is not None:
                        return True
                    match = re.match(r"^\[([^\]]+)\]$", stripped)
                    if not match:
                        match = re.match(r"^(?:page|页码|頁碼|页|頁)\s*[:：]?\s*(\S+)\s*$", stripped, re.I)
                    if match and _resolve_words_page_token(match.group(1), page_stems, lookup) is not None:
                        return True
                    if checked >= 1200:
                        break
        except (OSError, UnicodeError):
            return False
        return False

    def compare_old_new_selected_scope(self, force_choose: bool = False) -> None:
        """Compare selected-range current PDIC headwords with a page-aware wordslist.

        ``PDIC`` is treated as the new/current version; the chosen TXT is the old
        version.  Both are reduced to the exact ``page<TAB>headword`` representation
        before exact line-sequence comparison, page by page.
        """
        if not self.project or not self.current_page or self.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
            return
        if self._batch_active:
            messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=self)
            return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc)
            return
        if not indices:
            return

        source = self._old_new_compare_source_path
        suggested = self._default_old_new_compare_source()
        if not force_choose and (source is None or not source.is_file()):
            if suggested is not None and self._looks_page_aware_compare_source(suggested):
                source = suggested
                self._old_new_compare_source_path = source
        if force_choose or source is None or not source.is_file():
            initialdir = self.project.root
            initialfile = "wordslist.txt"
            if suggested is not None:
                initialdir = suggested.parent
                initialfile = suggested.name
            chosen = filedialog.askopenfilename(
                parent=self,
                title="选择用于新旧比较的 wordslist.txt（需含页码）",
                initialdir=str(initialdir),
                initialfile=initialfile,
                filetypes=[("文本", "*.txt"), ("PDIC/文本", "*.pdic *.txt"), ("全部", "*")],
            )
            if not chosen:
                return
            source = Path(chosen)
            self._old_new_compare_source_path = source

        if source is None or not source.is_file():
            messagebox.showerror("新旧比较", "所选 wordslist 文件不存在，请重新选择。", parent=self)
            self._old_new_compare_source_path = None
            return

        try:
            # Make the visible editor the authoritative newest PDIC before the
            # background comparison starts. Other pages are already on disk.
            self._flush_deferred_page_save()
            self._sync_entry_editor_texts()
            self.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            self.show_error("新旧比较准备失败", exc)
            return

        project = self.project
        pages = list(project.images)
        all_page_stems = [page.stem for page in pages]
        selected_stems = [pages[index].stem for index in indices]
        selected_set = set(selected_stems)
        holder: dict[str, object] = {"mapping": None, "present": None}

        def ensure_old_mapping() -> tuple[dict[str, list[str]], set[str]]:
            mapping = holder.get("mapping")
            present = holder.get("present")
            if isinstance(mapping, dict) and isinstance(present, set):
                return mapping, present
            text_data, _encoding = read_text_detected(source)
            present_pages: set[str] = set()
            parsed = _parse_words_of_pages_text(text_data, all_page_stems, present_pages=present_pages)
            if not (present_pages & selected_set):
                raise ValueError(
                    "所选 wordslist 中没有当前页面范围的页码记录。\n"
                    "新旧比较需要 page\\t词条、完整 8 字段 PDIC/_WordsOfPages，或 [页码] 分组格式。"
                )
            holder["mapping"] = parsed
            holder["present"] = present_pages
            return parsed, present_pages

        def worker(index: int, _position: int, _total: int):
            old_mapping, present_pages = ensure_old_mapping()
            page = pages[index]
            entries = read_pdic(pdic_path(page))
            new_words = [str(entry.word or "").strip() for entry in entries]
            old_words = list(old_mapping.get(page.stem, []))
            return {
                "index": index,
                "page": page.stem,
                "old": old_words,
                "new": new_words,
                "old_present": page.stem in present_pages,
            }

        def done(completed: int, total: int, stopped: bool, results, error) -> None:
            if error is not None:
                # If parsing never succeeded, make the next click ask for another
                # old wordslist rather than repeatedly retrying a wrong file.
                if holder.get("mapping") is None:
                    self._old_new_compare_source_path = None
                return
            if stopped:
                return
            by_index = {
                int(item.get("index")): item for item in results if isinstance(item, dict) and "index" in item
            }
            old_mapping: dict[str, list[str]] = {}
            new_mapping: dict[str, list[str]] = {}
            missing_old_pages: list[str] = []
            for index, stem in zip(indices, selected_stems):
                item = by_index.get(index, {})
                old_mapping[stem] = list(item.get("old", []))
                new_mapping[stem] = list(item.get("new", []))
                if not bool(item.get("old_present", False)):
                    missing_old_pages.append(stem)

            changes, counts = _compare_page_word_mappings(selected_stems, old_mapping, new_mapping)
            payload: dict[str, object] = {
                "source": str(source),
                "page_order": selected_stems,
                "old_mapping": old_mapping,
                "new_mapping": new_mapping,
                "old_text": _page_word_mapping_text(selected_stems, old_mapping),
                "new_text": _page_word_mapping_text(selected_stems, new_mapping),
                "changes": changes,
                "counts": counts,
                "missing_old_pages": missing_old_pages,
            }
            old_window = self.old_new_compare_window
            if old_window is not None:
                try:
                    if old_window.winfo_exists():
                        old_window.destroy()
                except tk.TclError:
                    pass
            window = OldNewComparisonWindow(self, payload)
            self.old_new_compare_window = window
            diff_total = counts["新增"] + counts["删除"] + counts["修改"]
            self.status_var.set(
                f"新旧比较完成：{len(selected_stems)} 页｜旧 {counts['old_rows']} 行｜"
                f"新 {counts['new_rows']} 行｜差异 {diff_total} 条"
            )

        started = self._start_batch_task(
            "新旧比较", indices, worker, done,
            item_label=lambda index: pages[index].name,
            foreground_page_edit=False,
            refresh_page_quality=False,
        )
        if started:
            self.status_var.set(
                f"正在比较 {len(indices)} 页：当前 PDIC（新） ↔ {source.name}（旧）；可暂停或停止。"
            )

    def open_review(self) -> None:
        if not (self.guard() and self.entries):
            return
        if self.review_window is not None:
            try:
                if self.review_window.winfo_exists():
                    self.review_window.lift()
                    self.review_window.focus_force()
                    return
            except tk.TclError:
                pass
            self.review_window = None
        # Capture any text still being edited on the main canvas before the
        # review window starts using the shared Entry objects.
        self._sync_entry_editor_texts()
        # Keep the established behavior: proofreading starts with both main
        # canvas OCR aids disabled, even though their controls now live in the
        # main Auxiliary Options section.
        self.settings.review_main_show_ocr_choices = False
        self.settings.review_main_show_ocr_background = False
        if hasattr(self, "quick_bool_vars"):
            for name in ("review_main_show_ocr_choices", "review_main_show_ocr_background"):
                if name in self.quick_bool_vars:
                    self.quick_bool_vars[name].set(False)
        review = ReviewWindow(self)
        self.review_window = review
        # Proofreading owns OCR selection while it is open, so simplify the
        # main canvas immediately (unless the user re-enables either aid).
        self.redraw()

    def show_error(self, title: str, exc: Exception) -> None:
        self.status_var.set(f"{title}：{exc}")
        messagebox.showerror(title, f"{exc}\n\n详细信息已输出到终端。", parent=self)
        traceback.print_exc()


def main() -> int:
    multiprocessing.freeze_support()
    app = PictureCaptureApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
