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
from .ui import review_selection_workflow as _review_selection
from .ui import main_entry_actions as _main_entry_actions
from .ui import selected_marker_actions as _selected_marker_actions
from .ui import lexicon_compare_workflow as _lexicon_compare
from .ui import page_scope_workflow as _page_scope
from .ui import page_index_workflow as _page_index
from .ui import word_fill_status_workflow as _word_fill_status
from .ui import review_appearance_workflow as _review_appearance
from .ui import focused_filter_workflow as _focused_filter
from .proofreading import focused_pdic_updates as _focused_pdic
from .ui import main_canvas_render_workflow as _main_canvas_render
from .ui import main_display_cache as _main_display_cache
from .ui import main_pdic_persistence as _main_pdic_persistence
from .ui import main_dialog_lifecycle as _main_dialog_lifecycle
from .ui import canvas_pointer_workflow as _canvas_pointer
from .ui import main_appearance_policy as _main_appearance_policy
from .ui import main_sidebar_sections as _sidebar_sections
from .ui import review_crop_geometry as _review_crop_geometry
from .ui import main_app_lifecycle as _main_app_lifecycle
from .ui import ocr_current_workflow as _main_ocr_current
from .ui import quick_settings_apply as _quick_settings_apply
from .ui import detection_batch_execution as _detection_batch_execution
from .ui import main_workspace_build as _main_workspace_build
from .ui.settings import interactive_panels as _interactive_settings_panels
from .ui.settings import field_form_runtime as _settings_field_form
from .ui import review_style_policy as _review_style_policy
from .ui import background_job_runtime as _background_job_runtime
from .ui import quick_settings_sync as _quick_settings_sync
from .ui import paddle_environment_report as _paddle_environment_report
from .ui import main_action_buttons as _main_action_buttons
from .ui.settings import dialog_initialization as _settings_dialog_initialization
from .ui import review_window_initialization as _review_window_initialization
from .ui import review_layout_events as _review_layout_events
from .ui import main_app_initialization as _main_app_initialization
from .ui import controller_lifecycle as _controller_lifecycle
from .ui import appearance_resolution as _appearance_resolution
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
from .profile import language_policy as _project_language_policy
from .profile.semantics import (
    effective_page_settings, entry_allowed_by_page_template, page_template_analysis_image,
)
from .preprocess.analysis_image import normalize_page_rgb
from .ui import preprocess_workflow as _preprocess_ui
from .ui import batch_workflow as _batch_workflow
from .preprocess.pipeline import (
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

# Stable public aliases; canonical language vocabulary and policy live in Profile.
PROJECT_LANGUAGE_CODES = _project_language_policy.PROJECT_LANGUAGE_CODES
OCR_TO_PROJECT_LANGUAGE = _project_language_policy.OCR_TO_PROJECT_LANGUAGE


def project_language_from_ocr(ocr_language: str) -> str:
    """Historical app API with call-time OCR mapping for monkeypatch users."""
    return _project_language_policy.project_language_from_ocr(
        ocr_language, mapping=OCR_TO_PROJECT_LANGUAGE,
    )

def transformed_geometry_pending(settings: AppSettings) -> bool:
    """Historical app safety API; resolve the current UI owner on each call."""
    return _main_app_lifecycle.transformed_geometry_pending(settings)

OCR_SCOPE_LABELS = {"current": "当前页", "all": "全部页面"}
OCR_SCOPE_VALUES = {label: value for value, label in OCR_SCOPE_LABELS.items()}
OCR_REFRESH_LABELS = {
    "reuse": "复用缓存（参数变化自动重算）",
    "force": "强制重新识别",
}
OCR_REFRESH_VALUES = {label: value for value, label in OCR_REFRESH_LABELS.items()}

def _review_crop_settings(image: Image.Image, settings: AppSettings, viewer_width: int) -> AppSettings:
    """Public compatibility entrypoint with call-time patched collaborators."""
    return _review_crop_geometry._review_crop_settings(image, settings, viewer_width, deps={"replace": replace})

def _review_crop_context(
    image: Image.Image,
    settings: AppSettings,
    viewer_width: int,
    page_index: int = 0,
):
    """Public compatibility entrypoint with call-time patched collaborators."""
    return _review_crop_geometry._review_crop_context(image, settings, viewer_width, page_index=page_index, deps={"effective_page_settings": effective_page_settings, "page_template_analysis_image": page_template_analysis_image, "_review_crop_settings": _review_crop_settings, "derive_geometry": derive_geometry})

def _is_cjk_review_index(settings: AppSettings) -> bool:
    """Public compatibility entrypoint with call-time patched collaborators."""
    return _review_crop_geometry._is_cjk_review_index(settings, deps={})

def _effective_review_single_cjk_line_height(settings: AppSettings) -> int:
    """Public compatibility entrypoint with call-time patched collaborators."""
    return _review_crop_geometry._effective_review_single_cjk_line_height(settings, deps={"_is_cjk_review_index": _is_cjk_review_index})

def _effective_review_regular_crop_height(settings: AppSettings) -> int:
    """Public compatibility entrypoint with call-time patched collaborators."""
    return _review_crop_geometry._effective_review_regular_crop_height(settings, deps={})

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
    """Public compatibility entrypoint with call-time patched collaborators."""
    return _review_crop_geometry._review_line_box(entry, geometry, image, settings, next_entry, ordinary_height_only=ordinary_height_only, editor_text=editor_text, deps={"replace": replace, "line_box": line_box, "_effective_review_regular_crop_height": _effective_review_regular_crop_height, "_effective_review_single_cjk_line_height": _effective_review_single_cjk_line_height, "_focused_review_is_single_character": _focused_review_is_single_character})

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
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _settings_field_form._setting_var(self, name, deps={"tk": tk, "_format_layout_percent": _format_layout_percent, "_column_pixels_to_percent": _column_pixels_to_percent, "LAYOUT_PERCENT_AXES": LAYOUT_PERCENT_AXES, "_layout_pixels_to_percent": _layout_pixels_to_percent})

    def _setting_widget(self, parent: ttk.Frame, name: str) -> tk.Widget:
        """Historical setting field widget factory."""
        return _settings_field_form.setting_widget(
            self, parent, name, deps={
                "ttk": ttk,
                "tk": tk,
                "font": font,
                "PROJECT_LANGUAGE_CODES": PROJECT_LANGUAGE_CODES,
                "AUTO_FONT_FAMILY": AUTO_FONT_FAMILY,
                "_settings_color_ui": _settings_color_ui,
            },
        )


    def _add_setting_group(
        self, parent: ttk.Frame, title: str,
        names: tuple[str, ...] | list[str], *,
        intro: str = "", help_images: bool = False,
        single_line_labels: bool = False,
    ) -> ttk.LabelFrame:
        """Historical responsive parameter group construction."""
        return _settings_field_form.add_setting_group(
            self, parent, title, names, intro=intro,
            help_images=help_images,
            single_line_labels=single_line_labels, deps={
                "ttk": ttk,
                "font": font,
            },
        )


    def _add_check_group(
        self,
        parent: ttk.Frame,
        title: str,
        checks: tuple[tuple[str, str], ...] | list[tuple[str, str]],
        *,
        intro: str = "",
    ) -> ttk.LabelFrame:
        """Historical settings check group with contextual help callbacks."""
        return _interactive_settings_panels.add_check_group(
            self, parent, title, checks, intro=intro,
            deps={"ttk": ttk, "tk": tk},
        )


    def _add_collapsible_settings(
        self,
        parent: ttk.Frame,
        title: str,
        names: tuple[str, ...] | list[str],
        checks: tuple[tuple[str, str], ...] | list[tuple[str, str]] = (),
    ) -> None:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _interactive_settings_panels._add_collapsible_settings(self, parent,title,names,checks, deps={"tk": tk, "ttk": ttk})

    def _scrollable_settings_page(self, tab: ttk.Frame) -> ttk.Frame:
        """Historical responsive settings page with nested help and scrolling."""
        return _interactive_settings_panels.scrollable_settings_page(
            self, tab, deps={"ttk": ttk, "tk": tk},
        )


    def _settings_intro(self, parent: ttk.Frame, title: str, text: str) -> None:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _interactive_settings_panels._settings_intro(self, parent,title,text, deps={"ttk": ttk})

    def __init__(self, parent: "PictureCaptureApp", initial_tab: str | None = None) -> None:
        """Stable SettingsDialog constructor; preserve Tk's original super() semantics."""
        super().__init__(parent)
        return _settings_dialog_initialization.initialize_settings_dialog(
            self, parent, initial_tab, deps={
                "tk": tk,
                "ttk": ttk,
                "Image": Image,
                "fit_window_to_work_area": fit_window_to_work_area,
                "_build_modern_dialog_heading": _build_modern_dialog_heading,
                "effective_project_profile_id": effective_project_profile_id,
                "project_profile_path": project_profile_path,
                "LATIN_ORDER": LATIN_ORDER,
                "preferred_font_family": preferred_font_family,
                "_settings_illustration_ui": _settings_illustration_ui,
                "_settings_ref_box_ui": _settings_ref_box_ui,
                "_settings_inference_ui": _settings_inference_ui,
                "DETECTION_LABELS": DETECTION_LABELS,
                "LENS_MODE_LABELS": LENS_MODE_LABELS,
                "LENS_MODE_VALUES": LENS_MODE_VALUES,
                "APPEARANCE_MODE_VALUES": APPEARANCE_MODE_VALUES,
                "OCR_ENGINE_LABELS": OCR_ENGINE_LABELS,
                "OCR_ENGINE_VALUES": OCR_ENGINE_VALUES,
                "_project_templates": _project_templates,
            },
        )

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
        """Historical validated settings save with Profile, rules and redraw."""
        return _settings_field_form.save_settings(
            self, close=close, show_errors=show_errors,
            deps={
                "_settings_lifecycle_ui": _settings_lifecycle_ui,
                "_settings_color_ui": _settings_color_ui,
                "_column_percent_to_pixels": _column_percent_to_pixels,
                "LAYOUT_PERCENT_AXES": LAYOUT_PERCENT_AXES,
                "_layout_percent_to_pixels": _layout_percent_to_pixels,
                "DETECTION_VALUES": DETECTION_VALUES,
                "OCR_ENGINE_VALUES": OCR_ENGINE_VALUES,
                "LENS_MODE_VALUES": LENS_MODE_VALUES,
                "language_effective_settings": language_effective_settings,
                "normalize_content_font_setting": normalize_content_font_setting,
                "parse_custom_order": parse_custom_order,
                "parse_headword_filter_rules": parse_headword_filter_rules,
                "settings_path": settings_path,
                "write_project_profile": write_project_profile,
                "project_profile_path": project_profile_path,
                "headword_filter_rules_path": headword_filter_rules_path,
                "HEADWORD_FILTER_RULES_FILENAME": HEADWORD_FILTER_RULES_FILENAME,
                "messagebox": messagebox,
            },
        )


    def check_ocr_engines(self) -> None:
        """Open the shared environment center instead of a transient status dialog."""
        self.parent.show_environment_center()

def _review_window_dimensions(screen_w: int, screen_h: int) -> tuple[int, int]:
    """Historical app API; dispatch to the current review UI owner."""
    return _review_layout_events.review_window_dimensions(screen_w, screen_h)

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
        """Stable ReviewWindow constructor; preserve Tk's original super() semantics."""
        super().__init__(parent)
        return _review_window_initialization.initialize_review_window(
            self, parent, deps={
                "tk": tk,
                "font": font,
                "ImageTk": ImageTk,
                "_review_window_dimensions": _review_window_dimensions,
                "_format_layout_percent": _format_layout_percent,
                "normalize_content_font_setting": normalize_content_font_setting,
                "_review_editor_font_size": _review_editor_font_size,
                "_format_review_height_percent": _format_review_height_percent,
                "_effective_review_regular_crop_height": _effective_review_regular_crop_height,
                "_effective_review_single_cjk_line_height": _effective_review_single_cjk_line_height,
                "OCR_COMPARE_KEY_TO_LABEL": self.OCR_COMPARE_KEY_TO_LABEL,
                "WORDSLIST_LOCATOR_KEY_TO_LABEL": self.WORDSLIST_LOCATOR_KEY_TO_LABEL,
                "LexicalLookupResult": LexicalLookupResult,
                "threading": threading,
                "queue": queue,
            },
        )

    def _configure_review_styles(self) -> None:
        """Historical dense proofreading styles with live theme globals."""
        return _review_style_policy.configure_review_styles(
            self, deps={
                "ttk": ttk,
                "appearance_palette": appearance_palette,
            },
        )


    def _review_flat_button(
        self, parent: tk.Misc, text: str, command, *, role: str = "neutral",
        width: int | None = None, anchor: str = "center",
    ) -> tk.Button:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _review_layout_events._review_flat_button(self, parent,text,command,role=role,width=width,anchor=anchor, deps={"tk": tk})

    def _review_collapsible_section(
        self, parent: tk.Misc, key: str, title: str, *, padding: int = 6,
        fill: str = "x", expand: bool = False, pady=(0, 6),
    ) -> ttk.Frame:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _review_layout_events._review_collapsible_section(self, parent,key,title,padding=padding,fill=fill,expand=expand,pady=pady, deps={"tk": tk, "ttk": ttk})

    def _toggle_review_right_section(self, key: str) -> None:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _review_layout_events._toggle_review_right_section(self, key, deps={})

    def _toggle_focused_panel(self) -> None:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _review_layout_events._toggle_focused_panel(self, deps={})

    def _fit_review_left_pane_to_toolbar(self) -> None:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _review_layout_events._fit_review_left_pane_to_toolbar(self, deps={"tk": tk})

    def _initialize_review_layout_and_rows(self) -> None:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _review_layout_events._initialize_review_layout_and_rows(self, deps={"tk": tk})

    def _review_image_area_width(self, canvas_width: int | None = None) -> int:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _review_layout_events._review_image_area_width(self, canvas_width=canvas_width, deps={"tk": tk})

    def _review_canvas_configured(self, event: tk.Event) -> None:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _review_layout_events._review_canvas_configured(self, event, deps={"tk": tk})

    def _apply_auto_review_zoom_resize(self) -> None:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _review_layout_events._apply_auto_review_zoom_resize(self, deps={})

    def _stored_review_zoom_percent(self) -> float:
        """Stable Tk callback; full behavior is owned by its UI domain module."""
        return _review_layout_events._stored_review_zoom_percent(self, deps={})

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


def _selected_marker_actions_deps() -> _selected_marker_actions.SelectedMarkerActionsDeps:
    """Snapshot patchable import bindings afresh for each Tk action."""
    return _selected_marker_actions.SelectedMarkerActionsDeps(
        replace=replace,
        messagebox=messagebox,
        guard_ocr_action_selection=guard_ocr_action_selection,
        read_pdic=read_pdic,
        pdic_path=pdic_path,
        load_replace_rules=load_replace_rules,
        replace_rules_path=replace_rules_path,
        headword_filter_rules_path=headword_filter_rules_path,
        HEADWORD_FILTER_RULES_FILENAME=HEADWORD_FILTER_RULES_FILENAME,
        PROFILE_FILENAME=PROFILE_FILENAME,
        Image=Image,
        normalize_page_rgb=normalize_page_rgb,
        read_page_sections=read_page_sections,
        ocr_existing_entry_words_from_markers=ocr_existing_entry_words_from_markers,
        write_pdic=write_pdic,
        export_ocred=export_ocred,
        qt_root=qt_root,
    )


def _main_entry_actions_deps() -> _main_entry_actions.MainEntryActionsDeps:
    """Capture live GUI collaborators on each main-entry event."""
    return _main_entry_actions.MainEntryActionsDeps(
        release_alpha_line_photos=release_alpha_line_photos,
        tk=tk,
        parameter_scale=parameter_scale,
        VerticalWordText=VerticalWordText,
        resolve_wordslist_path=resolve_wordslist_path,
        _candidate_choice_rows=_candidate_choice_rows,
        _has_distinct_ocr_alternatives=_has_distinct_ocr_alternatives,
        simplified_entry_key=simplified_entry_key,
        simplified_review_path_for_image=simplified_review_path_for_image,
        read_simplified_records=read_simplified_records,
        write_simplified_records=write_simplified_records,
    )


def _review_selection_deps() -> _review_selection.ReviewSelectionDeps:
    """Capture live GUI bindings for review, deferred saves and evidence callbacks."""
    return _review_selection.ReviewSelectionDeps(
        tk=tk,
        json=json,
        replace=replace,
        WordEntry=WordEntry,
        ocr_cache_root=ocr_cache_root,
        read_pdic=read_pdic,
        pdic_path=pdic_path,
        _review_crop_settings=_review_crop_settings,
        _review_line_box=_review_line_box,
        OCRConflictReviewDialog=OCRConflictReviewDialog,
    )


def _page_scope_deps() -> _page_scope.PageScopeDeps:
    """Snapshot original module references afresh at each native callback."""
    return _page_scope.PageScopeDeps(
        re=re,
        bookmarked_page_indices=bookmarked_page_indices,
        messagebox=messagebox,
        ocr_cache_root=ocr_cache_root,
        compact_ocr_cache_file=compact_ocr_cache_file,
        json=json,
    )


def _lexicon_compare_deps() -> _lexicon_compare.LexiconCompareDeps:
    """Snapshot original module references afresh at each native callback."""
    return _lexicon_compare.LexiconCompareDeps(
        resolve_wordslist_path=resolve_wordslist_path,
        read_noncomment_lines=read_noncomment_lines,
        settings_path=settings_path,
        words_of_pages_default_path=words_of_pages_default_path,
        filedialog=filedialog,
        Path=Path,
        read_text_detected=read_text_detected,
        write_text_atomic=write_text_atomic,
        pdic_path=pdic_path,
        read_pdic=read_pdic,
        Image=Image,
        write_pdic=write_pdic,
        _build_words_page_lookup=_build_words_page_lookup,
        _resolve_words_page_token=_resolve_words_page_token,
        re=re,
        messagebox=messagebox,
        tk=tk,
        _parse_words_of_pages_text=_parse_words_of_pages_text,
        _compare_page_word_mappings=_compare_page_word_mappings,
        _page_word_mapping_text=_page_word_mapping_text,
        OldNewComparisonWindow=OldNewComparisonWindow,
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
        """Keep original Tk constructor and dynamic global-patching contract."""
        super().__init__()
        return _main_app_initialization.initialize_main_app(
            self, deps={
                "ImageTk": ImageTk,
                "Path": Path,
                "Image": Image,
                "tk": tk,
                "fit_window_to_work_area": fit_window_to_work_area,
                "AppSettings": AppSettings,
                "AuxiliaryLineEdits": AuxiliaryLineEdits,
                "queue": queue,
                "threading": threading,
                "SessionController": SessionController,
                "normalize_appearance_preference": normalize_appearance_preference,
                "APPEARANCE_MODE_LABELS": APPEARANCE_MODE_LABELS,
                "ttk": ttk,
                "font": font,
                "AuxiliaryLineController": AuxiliaryLineController,
                "CanvasController": CanvasController,
                "CropController": CropController,
                "DetectionController": DetectionController,
                "ExportController": ExportController,
                "HeadwordController": HeadwordController,
                "_parse_words_of_pages_text": _parse_words_of_pages_text,
                "_fill_page_entries": _fill_page_entries,
                "IllustrationController": IllustrationController,
                "RefBoxController": RefBoxController,
                "ProjectController": ProjectController,
                "PageController": PageController,
                "ReviewController": ReviewController,
                "attach_nonbmp_unicode_input": attach_nonbmp_unicode_input,
                "app_module_file": __file__,
            },
        )

    def destroy(self) -> None:
        close_nonbmp_unicode_input(self)
        super().destroy()


    def _app_icon_toplevel_mapped(self, event: tk.Event) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _main_appearance_policy._app_icon_toplevel_mapped(self, event, deps={"tk": tk})

    def _maximize_main_window(self) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _main_appearance_policy._maximize_main_window(self, deps={"tk": tk, "_screen_work_area": _screen_work_area})

    def _ensure_sidebar_navigation_width(self) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _sidebar_sections._ensure_sidebar_navigation_width(self, deps={"tk": tk})

    def _ui_worker_key_active(self, key: str) -> bool:
        """Legacy API; physical behavior now owned by its UI module."""
        return _background_job_runtime._ui_worker_key_active(self, key, deps={})

    def _start_ui_worker(
        self, key: str, worker, on_done, on_error=None, *, wait_on_close: bool = False,
    ) -> int:
        """Historical nonblocking generation-safe Tk worker entrypoint."""
        return _background_job_runtime.start_ui_worker(
            self, key, worker, on_done, on_error, wait_on_close=wait_on_close,
            deps={"threading": threading, "traceback": traceback},
        )


    def _invalidate_ui_worker(self, key: str) -> None:
        """Legacy API; physical behavior now owned by its UI module."""
        return _background_job_runtime._invalidate_ui_worker(self, key, deps={})

    def _poll_ui_worker_queue(self) -> None:
        """Historical Tk-thread result queue polling with deferred close."""
        return _background_job_runtime.poll_ui_worker_queue(
            self, deps={"tk": tk, "queue": queue, "traceback": traceback},
        )


    def _configure_global_appearance(self) -> None:
        """Historical main-window theme installer with current patched UI providers."""
        return _main_appearance_policy.configure_global_appearance(
            self, deps={
                "ttk": ttk, "tk": tk,
                "normalize_appearance_mode": normalize_appearance_mode,
                "appearance_palette": appearance_palette,
            },
        )

    def _apply_current_appearance(self, root: tk.Misc) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _main_appearance_policy._apply_current_appearance(self, root, deps={"tk": tk, "apply_classic_widget_appearance": apply_classic_widget_appearance, "apply_native_titlebar_appearance": apply_native_titlebar_appearance})

    def _appearance_toplevel_mapped(self, event: tk.Event) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _main_appearance_policy._appearance_toplevel_mapped(self, event, deps={"tk": tk})

    def _appearance_mode_selected(self, _event: tk.Event | None = None) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _main_appearance_policy._appearance_mode_selected(self, _event, deps={"APPEARANCE_MODE_VALUES": APPEARANCE_MODE_VALUES})

    def _cancel_system_appearance_poll(self) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _main_appearance_policy._cancel_system_appearance_poll(self, deps={"tk": tk})

    def _schedule_system_appearance_poll(self, delay_ms: int = 2500) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _main_appearance_policy._schedule_system_appearance_poll(self, delay_ms=delay_ms, deps={"tk": tk})

    def _poll_system_appearance(self) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _main_appearance_policy._poll_system_appearance(self, deps={"detect_system_appearance_mode": detect_system_appearance_mode, "normalize_appearance_mode": normalize_appearance_mode})

    def set_appearance_mode(self, mode: object, *, persist: bool = True) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _main_appearance_policy.set_appearance_mode(self, mode,persist=persist, deps={"normalize_appearance_preference": normalize_appearance_preference, "APPEARANCE_MODE_LABELS": APPEARANCE_MODE_LABELS})

    def _apply_resolved_appearance(self, mode: object) -> None:
        """Historical public appearance entrypoint with live UI dependencies."""
        return _appearance_resolution.apply_resolved_appearance(
            self, mode, deps={
                "normalize_appearance_mode": normalize_appearance_mode,
                "appearance_palette": appearance_palette,
                "tk": tk,
            },
        )

    def _configure_main_workspace_styles(self) -> None:
        """Historical scoped PC.* workspace style installer."""
        return _main_appearance_policy.configure_main_workspace_styles(
            self, deps={"ttk": ttk, "appearance_palette": appearance_palette},
        )

    def _sidebar_action_button(
        self, parent: tk.Misc, text: str, command, *, role: str = "neutral"
    ) -> tk.Widget:
        """Historical compact sidebar action button with live ttk/tk providers."""
        return _main_action_buttons.sidebar_action_button_impl(
            self, parent, text, command, role=role,
            deps={"ttk": ttk, "tk": tk},
        )


    def _footer_action_button(
        self, parent: tk.Misc, text: str, command, *, role: str
    ) -> tk.Button:
        """Historical emphasized footer button with live Tk provider."""
        return _main_action_buttons.footer_action_button_impl(
            self, parent, text, command, role=role, deps={"tk": tk},
        )


    def _section_frame(
        self, parent: tk.Misc, title: str, padding: int = 5, *, section_key: str | None = None
    ) -> ttk.LabelFrame:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _sidebar_sections._section_frame(self, parent,title,padding,section_key=section_key, deps={"tk": tk, "ttk": ttk})

    def _set_section_expanded(self, section: ttk.LabelFrame, expanded: bool, *, persist: bool = True) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _sidebar_sections._set_section_expanded(self, section,expanded,persist=persist, deps={"tk": tk})

    def _toggle_section(self, section: ttk.LabelFrame) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _sidebar_sections._toggle_section(self, section, deps={})

    def _apply_initial_section_states(self) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _sidebar_sections._apply_initial_section_states(self, deps={})

    def _apply_new_project_sidebar_defaults(self) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _sidebar_sections._apply_new_project_sidebar_defaults(self, deps={})

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
        """Public compatibility entrypoint with call-time patched collaborators."""
        return _main_app_lifecycle.on_close(self, deps={"messagebox": messagebox, "tk": tk, "settings_path": settings_path})

    def _build_ui(self) -> None:
        """Historical main workspace construction with current Tk bindings."""
        return _main_workspace_build.build_ui(
            self, deps={"tk": tk, "ttk": ttk,
                        "PageListGrid": PageListGrid,
                        "PageThumbnailController": PageThumbnailController,
                        "bind_context_menu": bind_context_menu},
        )


    def _pointer_over_sidebar(self) -> bool:
        """Legacy API; physical behavior now owned by its UI module."""
        return _sidebar_sections._pointer_over_sidebar(self, deps={"tk": tk})

    def _resize_sidebar_content(self, event: tk.Event | None = None) -> None:
        return _page_index._resize_sidebar_content(self, _page_index_deps(), event)

    def _sidebar_mousewheel(self, event: tk.Event) -> str | None:
        """Legacy API; physical behavior now owned by its UI module."""
        return _sidebar_sections._sidebar_mousewheel(self, event, deps={})

    def _sidebar_linux_mousewheel(self, _event: tk.Event, direction: int) -> str | None:
        """Legacy API; physical behavior now owned by its UI module."""
        return _sidebar_sections._sidebar_linux_mousewheel(self, _event, direction, deps={})

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
        """Legacy API; physical behavior now owned by its UI module."""
        return _page_index._list_mousewheel(self, event, deps={})

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
        """Legacy API; physical behavior now owned by its UI module."""
        return _page_index._select_page_from_lined_overlay(self, index, deps={})

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
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _quick_settings_apply._style_color_button(button, color, deps={"tk": tk})

    def choose_overlay_color(self, setting_name: str, button: tk.Button) -> None:
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _quick_settings_apply.choose_overlay_color(self, setting_name, button, deps={"colorchooser": colorchooser})

    def _quick_percent_parameter_changed(self, name: str) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _quick_settings_apply._quick_percent_parameter_changed(self, name, deps={"_layout_percent_to_pixels": _layout_percent_to_pixels})

    def _quick_pixel_parameter_changed(self, name: str) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _quick_settings_apply._quick_pixel_parameter_changed(self, name, deps={"_layout_pixels_to_percent": _layout_pixels_to_percent, "_format_layout_percent": _format_layout_percent})

    def _quick_parameter_changed(self, *_args, immediate: bool = False) -> None:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _quick_settings_apply._quick_parameter_changed(self, *_args,immediate=immediate, deps={"tk": tk})

    def _apply_overlay_visibility_toggle(self, setting_name: str, variable: tk.BooleanVar) -> None:
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _quick_settings_apply._apply_overlay_visibility_toggle(self, setting_name, variable)

    def _run_quick_autosave(self) -> None:
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _quick_settings_apply._run_quick_autosave(self)

    def _quick_geometry_value(self, name: str) -> int:
        """Stable main-window Tk callback, physically implemented under ui/."""
        return _quick_settings_apply._quick_geometry_value(self, name, deps={})

    def _refresh_quick_coordinate_labels(self) -> None:
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _quick_settings_apply._refresh_quick_coordinate_labels(self)

    def sync_quick_settings(self) -> None:
        """Historical quick-control sync in original page-pixel coordinates."""
        return _quick_settings_sync.sync_quick_settings_impl(
            self, deps={
                "LAYOUT_PERCENT_AXES": LAYOUT_PERCENT_AXES,
                "_format_layout_percent": _format_layout_percent,
                "_layout_pixels_to_percent": _layout_pixels_to_percent,
                "normalize_content_font_setting": normalize_content_font_setting,
                "LENS_MODE_LABELS": LENS_MODE_LABELS,
            },
        )


    def apply_quick_settings(self, show_status: bool = True, persist: bool = False, silent_errors: bool = False) -> bool:
        """Historical quick-settings conversion and side-effect API."""
        return _quick_settings_apply.apply_quick_settings(
            self, show_status, persist, silent_errors,
            deps={
                "LAYOUT_PERCENT_AXES": LAYOUT_PERCENT_AXES,
                "_layout_percent_to_pixels": _layout_percent_to_pixels,
                "normalize_content_font_setting": normalize_content_font_setting,
                "language_effective_settings": language_effective_settings,
                "LENS_MODE_VALUES": LENS_MODE_VALUES, "re": re,
            },
        )

    def save_main_parameters(self) -> None:
        self.apply_quick_settings(persist=True)

    def _save_current_page_files(self, *, sync_editors: bool = True) -> tuple[Path, Path] | None:
        """Legacy Tk callback; real implementation lives in the UI domain."""
        return _main_pdic_persistence._save_current_page_files(self, sync_editors=sync_editors, deps={"pdic_path": pdic_path})

    def _save_current_page_by_mode(self, *, sync_editors: bool = True) -> Path | None:
        """Legacy Tk callback; real implementation lives in the UI domain."""
        return _main_pdic_persistence._save_current_page_by_mode(self, sync_editors=sync_editors, deps={"pdic_path": pdic_path})

    def save_current_page(self) -> None:
        """Legacy Tk callback; real implementation lives in the UI domain."""
        return _main_pdic_persistence.save_current_page(self, deps={})

    def export_training_package(self) -> None:
        self._export_controller_for_call().export_training_package()

    def show_help_dialog(self) -> None:
        """Legacy Tk callback; real implementation lives in the UI domain."""
        return _main_dialog_lifecycle.show_help_dialog(self, deps={"tk": tk, "UsageGuideWindow": UsageGuideWindow})

    @staticmethod
    def _distribution_version(name: str) -> str | None:
        """Legacy API; physical behavior now owned by its UI module."""
        return _paddle_environment_report._distribution_version(name, deps={"importlib_metadata": importlib_metadata})

    @staticmethod
    def _version_at_least(version: str | None, minimum: tuple[int, ...]) -> bool:
        """Legacy API; physical behavior now owned by its UI module."""
        return _paddle_environment_report._version_at_least(version, minimum, deps={"re": re})

    def _paddle_environment_text(self, settings: AppSettings | None = None) -> str:
        """Historical PP-OCR environment diagnostic and runtime status text."""
        return _paddle_environment_report.paddle_environment_text_impl(
            self, settings,
            deps={
                "importlib_util": importlib_util,
                "resolve_paddle_device": resolve_paddle_device,
            },
        )


    def show_environment_center(self) -> None:
        """Legacy Tk callback; real implementation lives in the UI domain."""
        return _main_dialog_lifecycle.show_environment_center(self, deps={"tk": tk, "EnvironmentCenterWindow": EnvironmentCenterWindow})

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
        return _page_scope._page_number(_page_scope_deps(), path)


    def _parse_page_spec(self, spec: str) -> list[int]:
        return _page_scope._parse_page_spec(self, _page_scope_deps(), spec)


    def selected_page_indices(self) -> list[int]:
        return _page_scope.selected_page_indices(self, _page_scope_deps())


    @staticmethod
    def _paddle_temp_matches_page(path: Path, page_stem: str) -> bool:
        return _page_scope._paddle_temp_matches_page(_page_scope_deps(), path, page_stem)


    def cleanup_paddleocr_temp_selected_scope(self) -> None:
        return _page_scope.cleanup_paddleocr_temp_selected_scope(self, _page_scope_deps())


    def jump_to_page_spec(self) -> None:
        return _page_scope.jump_to_page_spec(self, _page_scope_deps())


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
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _main_app_lifecycle.guard(self, deps={"messagebox": messagebox})

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
        return _lexicon_compare.reload_wordslist_reference(self, _lexicon_compare_deps(), selected_path, persist=persist, redraw=redraw)


    def _request_wordslist_reload(
        self, selected_path: Path | None = None, *, persist: bool = True,
        redraw: bool = True, on_done=None, on_error=None,
    ) -> None:
        return _lexicon_compare._request_wordslist_reload(self, _lexicon_compare_deps(), selected_path, persist=persist, redraw=redraw, on_done=on_done, on_error=on_error)


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
    ) -> bool | None:
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
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_display_cache._get_cached_display_photo(self, size, deps={"Image": Image, "ImageTk": ImageTk, "binary_preview_image": binary_preview_image, "themed_display_image": themed_display_image})

    def _canvas_controller_for_call(self) -> CanvasController:
        """Preserve lazy controller identity and live constructor patchpoints."""
        return _controller_lifecycle.get_or_create_controller(
            self, "canvas_controller", CanvasController,
        )

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
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_display_cache._current_effective_profile_settings(self, deps={"effective_page_settings": effective_page_settings})

    def _display_geometry_key(self) -> tuple:
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_display_cache._display_geometry_key(self, deps={})

    def _get_cached_display_geometry(self):
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_display_cache._get_cached_display_geometry(self, deps={"page_template_analysis_image": page_template_analysis_image, "derive_geometry": derive_geometry})

    def _main_ocr_review_option_enabled(self, setting_name: str) -> bool:
        """Return the persisted visibility of a main-canvas OCR aid."""
        return bool(getattr(self.settings, setting_name, False))

    # One entry's canvas/editor widgets are owned by the dedicated UI module.
    # Importing as a class attribute preserves method binding and call sites.
    from .ui.entry_overlay_builder import draw_entry_overlay as _draw_entry_overlay
    from .ui.entry_move_controller import move_entry_via_dialog as _move_entry_via_dialog

    def _remove_entry_overlay(self, entry: WordEntry) -> None:
        return _main_entry_actions._remove_entry_overlay(self, _main_entry_actions_deps(), entry)


    @staticmethod
    def _entry_sequence_text(index: int, total: int) -> str:
        return _main_entry_actions._entry_sequence_text(_main_entry_actions_deps(), index, total)


    def _refresh_entry_index_labels(self) -> None:
        return _main_entry_actions._refresh_entry_index_labels(self, _main_entry_actions_deps())


    def _update_entry_overlays_local(
        self, *, removed: list[WordEntry] | None = None, added: list[WordEntry] | None = None,
    ) -> None:
        return _main_entry_actions._update_entry_overlays_local(self, _main_entry_actions_deps(), removed=removed, added=added)


    def _toggle_crop_preview(self) -> None:
        self._canvas_controller_for_call().toggle_crop_preview()


    def _current_page_crop_plan(self):
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_canvas_render._current_page_crop_plan(self, deps={"build_page_crop_plan": build_page_crop_plan})

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
        """Stable Tk/public API; implementation owned by its UI domain."""
        return self._canvas_controller_for_call().fit_single_column_width()

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
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _canvas_pointer._polygon_display_name(region, index, deps={"label_text": label_text})

    def _set_polygon_display_name(self, region: PolygonRegion, name: str) -> None:
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _canvas_pointer._set_polygon_display_name(self, region, name, deps={"user_edited_link": user_edited_link})

    def _update_polygon_label(self, region: PolygonRegion, widget: tk.Entry) -> None:
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _canvas_pointer._update_polygon_label(self, region, widget, deps={"tk": tk, "label_text": label_text})

    def _commit_polygon_label_return(self, region: PolygonRegion, widget: tk.Entry) -> str:
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _canvas_pointer._commit_polygon_label_return(self, region, widget, deps={"tk": tk})

    def _sync_polygon_label_texts(self) -> None:
        return _canvas_pointer._sync_polygon_label_texts(self, _canvas_pointer_deps())

    def _nearest_polygon_vertex(self, x: int, y: int, radius_screen: float = 11.0) -> tuple[int, int] | None:
        return _canvas_pointer._nearest_polygon_vertex(self, _canvas_pointer_deps(), x, y, radius_screen)

    @staticmethod
    def _rectangle_bounds(region: PolygonRegion, tolerance: int = 2) -> tuple[int, int, int, int] | None:
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _canvas_pointer._rectangle_bounds(region, tolerance)

    def _nearest_polygon_edge(self, x: int, y: int, radius_screen: float = 9.0) -> tuple[int, str] | None:
        return _canvas_pointer._nearest_polygon_edge(self, _canvas_pointer_deps(), x, y, radius_screen)

    @staticmethod
    def _set_rectangle_side(region: PolygonRegion, side: str, value: int) -> None:
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _canvas_pointer._set_rectangle_side(region, side, value, deps={"PictureCaptureApp": PictureCaptureApp})

    def _delete_polygon_region(self, region: PolygonRegion) -> None:
        return _canvas_pointer._delete_polygon_region(self, _canvas_pointer_deps(), region)

    @staticmethod
    @staticmethod
    def _external_polygon_label_position(
        min_x: float, min_y: float, max_x: float, max_y: float,
        label_width: int, label_height: int, canvas_width: float, canvas_height: float,
        gap: int = 6,
    ) -> tuple[float, float]:
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _canvas_pointer._external_polygon_label_position(min_x, min_y, max_x, max_y, label_width, label_height, canvas_width, canvas_height, gap)

    def _polygon_label_canvas_position(self, region: PolygonRegion, widget: tk.Widget) -> tuple[float, float]:
        return _canvas_pointer._polygon_label_canvas_position(self, _canvas_pointer_deps(), region, widget)

    def _update_polygon_canvas_geometry(self, region_index: int) -> None:
        return _canvas_pointer._update_polygon_canvas_geometry(self, _canvas_pointer_deps(), region_index)

    def _persist_current_page_sections(self) -> None:
        """Legacy Tk callback; real implementation lives in the UI domain."""
        return _main_pdic_persistence._persist_current_page_sections(self, deps={"LayoutTransform": LayoutTransform, "write_page_sections": write_page_sections})

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
        """Stable Tk/public API; implementation owned by its UI domain."""
        return _canvas_pointer._section_gap_entry_count(self, deps={"v_is_inside_sections": v_is_inside_sections})

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
        return _main_entry_actions._confidence_bg(self, _main_entry_actions_deps(), confidence)


    def _style_entry_editor(
        self, widget: tk.Entry | VerticalWordText, entry: WordEntry, displayed_word: str | None = None
    ) -> None:
        return _main_entry_actions._style_entry_editor(self, _main_entry_actions_deps(), widget, entry, displayed_word)


    def _entry_overlay_style(
        self, entry: WordEntry, displayed_word: str | None = None,
    ) -> tuple[str, str, int]:
        return _main_entry_actions._entry_overlay_style(self, _main_entry_actions_deps(), entry, displayed_word)


    def _candidate_for_entry(self, entry: WordEntry) -> dict | None:
        return _main_entry_actions._candidate_for_entry(self, _main_entry_actions_deps(), entry)


    @staticmethod
    def _short_ocr_menu_word(word: str, limit: int = 12) -> str:
        return _main_entry_actions._short_ocr_menu_word(_main_entry_actions_deps(), word, limit)


    def _fill_main_entry_from_ocr(
        self, entry: WordEntry, editor: tk.Entry | VerticalWordText, candidate: dict,
        engine: str, word: str, menu_button: tk.Menubutton | None = None,
    ) -> None:
        return _main_entry_actions._fill_main_entry_from_ocr(self, _main_entry_actions_deps(), entry, editor, candidate, engine, word, menu_button)


    def _create_main_ocr_menu(
        self, entry: WordEntry, editor: tk.Entry | VerticalWordText, candidate: dict | None,
    ) -> tk.Menubutton | None:
        return _main_entry_actions._create_main_ocr_menu(self, _main_entry_actions_deps(), entry, editor, candidate)


    def _paddle_cache_path(self) -> Path | None:
        return _review_selection._paddle_cache_path(self, _review_selection_deps())


    def _manual_selection_path(self) -> Path | None:
        return _review_selection._manual_selection_path(self, _review_selection_deps())


    def _review_controller_for_call(self) -> ReviewController:
        """Preserve lazy controller identity and live constructor patchpoints."""
        return _controller_lifecycle.get_or_create_controller(
            self, "review_controller", ReviewController,
        )

    def _load_ocr_review_candidates(self) -> None:
        self._review_controller_for_call().load_ocr_review_candidates()


    def get_review_candidate(self, candidate_id: str) -> dict | None:
        return self._review_controller_for_call().get_review_candidate(candidate_id)


    def _candidate_is_selected(self, cand: dict) -> bool:
        return self._review_controller_for_call().candidate_is_selected(cand)


    def _read_manual_overrides(self) -> dict:
        return _review_selection._read_manual_overrides(self, _review_selection_deps())


    def _flush_pending_manual_override(self) -> None:
        return _review_selection._flush_pending_manual_override(self, _review_selection_deps())


    def _write_manual_override(
        self, cand: dict, *, selected: bool, word: str | None = None,
        engine: str | None = None, defer: bool = False,
    ) -> None:
        return _review_selection._write_manual_override(self, _review_selection_deps(), cand, selected=selected, word=word, engine=engine, defer=defer)


    def _queue_proofreading_add_evidence(self, x: int, y: int) -> None:
        return _review_selection._queue_proofreading_add_evidence(self, _review_selection_deps(), x, y)


    def _flush_proofreading_add_evidence(self) -> None:
        return _review_selection._flush_proofreading_add_evidence(self, _review_selection_deps())


    def _queue_proofreading_candidate_evidence(self, cand: dict, selected: bool) -> None:
        return _review_selection._queue_proofreading_candidate_evidence(self, _review_selection_deps(), cand, selected)


    def _flush_proofreading_candidate_evidence(self) -> None:
        return _review_selection._flush_proofreading_candidate_evidence(self, _review_selection_deps())


    def _schedule_deferred_page_save(self, *, sync_editors: bool = True) -> None:
        return _review_selection._schedule_deferred_page_save(self, _review_selection_deps(), sync_editors=sync_editors)


    def _flush_deferred_page_save(self) -> None:
        """Flush pending PDIC edits without discarding a failed snapshot."""
        from .proofreading.deferred_save import flush_deferred_page_save
        flush_deferred_page_save(self, write_pdic=write_pdic, pdic_path=pdic_path)

    def _entry_for_candidate(self, cand: dict) -> WordEntry | None:
        return self._review_controller_for_call().entry_for_candidate(cand)


    def set_candidate_selected(self, cand: dict, selected: bool) -> bool:
        return _review_selection.set_candidate_selected(self, _review_selection_deps(), cand, selected)


    def apply_candidate_choice(self, cand: dict, engine: str, word: str) -> None:
        return _review_selection.apply_candidate_choice(self, _review_selection_deps(), cand, engine, word)


    def candidate_checkbox_changed(self, candidate_id: str, var: tk.BooleanVar) -> None:
        return _review_selection.candidate_checkbox_changed(self, _review_selection_deps(), candidate_id, var)


    def clear_review_entry_highlight(self) -> None:
        self._review_controller_for_call().clear_review_entry_highlight()


    def highlight_review_entry(self, entry: WordEntry) -> None:
        self._review_controller_for_call().highlight_review_entry(entry)


    def _scroll_review_entry_into_view(self, entry: WordEntry) -> None:
        return _review_selection._scroll_review_entry_into_view(self, _review_selection_deps(), entry)


    def _draw_review_entry_highlight(self, geometry=None) -> None:
        return _main_canvas_render._draw_review_entry_highlight(self, _main_canvas_render_deps(), geometry)

    def jump_to_review_candidate(self, cand: dict) -> None:
        self._review_controller_for_call().jump_to_review_candidate(cand)


    def open_ocr_conflict_review(self) -> None:
        return _review_selection.open_ocr_conflict_review(self, _review_selection_deps())


    def _current_page_quality_text(self) -> str:
        return _review_selection._current_page_quality_text(self, _review_selection_deps())


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
        return _review_selection._restore_entry_ocr_metadata(self, _review_selection_deps(), payload)


    def update_entry(self, entry: WordEntry, widget: tk.Entry | VerticalWordText) -> None:
        return _main_entry_actions.update_entry(self, _main_entry_actions_deps(), entry, widget)


    def focus_next(self, widget: tk.Widget) -> str:
        return _main_entry_actions.focus_next(self, _main_entry_actions_deps(), widget)


    def focus_previous(self, widget: tk.Widget) -> str:
        return _main_entry_actions.focus_previous(self, _main_entry_actions_deps(), widget)


    def _delete_aligned_simplified_entry(self, entry: WordEntry) -> None:
        return _main_entry_actions._delete_aligned_simplified_entry(self, _main_entry_actions_deps(), entry)


    def delete_entry(self, entry: WordEntry) -> str:
        return _main_entry_actions.delete_entry(self, _main_entry_actions_deps(), entry)


    def _guard_transformed_geometry(self, action: str) -> bool:
        """Legacy API; physical behavior now owned by its UI module."""
        return _main_app_lifecycle._guard_transformed_geometry(self, action, deps={"transformed_geometry_pending": transformed_geometry_pending})

    def auto_detect_current(
        self, clicked_x: int | None = None, force_paddle_refresh: bool = False,
    ) -> None:
        self._detection_controller_for_call().auto_detect_current(
            clicked_x=clicked_x,
            force_paddle_refresh=force_paddle_refresh,
        )

    def _detection_controller_for_call(self) -> DetectionController:
        """Preserve lazy controller identity and live constructor patchpoints."""
        return _controller_lifecycle.get_or_create_controller(
            self, "detection_controller", DetectionController,
        )

    def paddle_detect_current(self, force_refresh: bool = False) -> None:
        self._detection_controller_for_call().paddle_detect_current(force_refresh)


    def refine_lines_selected_scope(self, *, fixed_half_gutter: bool = False) -> None:
        return _selected_marker_actions.refine_lines_selected_scope(self, _selected_marker_actions_deps(), fixed_half_gutter=fixed_half_gutter)


    def ocr_ordinary_lines_text_selected_scope(self) -> None:
        return _selected_marker_actions.ocr_ordinary_lines_text_selected_scope(self, _selected_marker_actions_deps())


    def run_combined_draw_action(self) -> None:
        self._detection_controller_for_call().run_combined_draw_action()


    def run_ocr_draw_action(self) -> None:
        self._detection_controller_for_call().run_ocr_draw_action()


    def run_normal_draw_action(self) -> None:
        self._detection_controller_for_call().run_normal_draw_action()

    def run_ocr_draw(self, scope: str, force_refresh: bool) -> None:
        self._detection_controller_for_call().run_ocr_draw(scope, force_refresh)


    def _detect_pages(self, indices: list[int], *, method: str, force_refresh: bool) -> None:
        """Historical multi-page ordinary/OCR/combined batch API."""
        return _detection_batch_execution.detect_pages(
            self, indices, method=method, force_refresh=force_refresh,
            deps={
                "messagebox": messagebox,
                "replace": replace,
                "os": os,
                "headword_filter_rules_path": headword_filter_rules_path,
                "HEADWORD_FILTER_RULES_FILENAME": HEADWORD_FILTER_RULES_FILENAME,
                "ProcessPoolExecutor": ProcessPoolExecutor,
                "multiprocessing": multiprocessing,
                "project_profile_path": project_profile_path,
                "replace_rules_path": replace_rules_path,
                "pdic_path": pdic_path,
                "ocr_cache_root": ocr_cache_root,
                "normalize_page_rgb": normalize_page_rgb,
                "read_page_sections": read_page_sections,
                "detect_entries": detect_entries,
                "ocr_existing_entry_words_from_markers": ocr_existing_entry_words_from_markers,
                "load_replace_rules": load_replace_rules,
                "write_pdic": write_pdic,
                "detect_entries_job": detect_entries_job,
                "statistics": statistics,
                "Image": Image,
            },
        )

    def clear_entries(self) -> None:
        """Legacy Tk callback; confirmation and mutation live in UI lifecycle."""
        return _main_app_lifecycle.clear_entries(
            self, deps={"messagebox": messagebox},
        )

    def clear_text(self) -> None:
        from .proofreading.pdic_text_cleanup import clear_selected_scope
        clear_selected_scope(self)


    def _ordered_entries_reading_order(self) -> list[WordEntry]:
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_pdic_persistence._ordered_entries_reading_order(self, deps={"sort_entries_reading_order": sort_entries_reading_order})

    def _sort_entries_reading_order(self) -> None:
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_pdic_persistence._sort_entries_reading_order(self, deps={})

    def pages_tuple(self, index: int | None = None) -> tuple[str, str, str]:
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_pdic_persistence.pages_tuple(self, index=index, deps={})

    def save_pdic(self, silent: bool = False, sync_editors: bool = True) -> None:
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_pdic_persistence.save_pdic(self, silent=silent,sync_editors=sync_editors, deps={"tk": tk, "pdic_path": pdic_path, "write_pdic": write_pdic})

    def _sync_entry_editor_texts(self) -> None:
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_pdic_persistence._sync_entry_editor_texts(self, deps={"tk": tk})

    def save_all(self) -> None:
        """Preserve guard-first PDIC then PPP save transaction."""
        return _main_pdic_persistence.save_all(self)

    def save_settings(self) -> None:
        """Persist current settings only for a project, without a schema change."""
        return _main_pdic_persistence.save_settings(
            self, deps={"settings_path": settings_path},
        )

    def toggle_autosave(self) -> None:
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_pdic_persistence.toggle_autosave(self, deps={})

    def autosave_tick(self) -> None:
        """Legacy Tk callback/API; physical algorithm lives in the UI owner."""
        return _main_pdic_persistence.autosave_tick(self, deps={"tk": tk})

    def open_settings(self, initial_tab: str | None = None) -> None:
        """Legacy Tk callback; real implementation lives in the UI domain."""
        return _main_dialog_lifecycle.open_settings(self, initial_tab, deps={"tk": tk, "SettingsDialog": SettingsDialog})

    def open_project_profile(self, new_project: bool = False) -> None:
        """Legacy Tk callback; real implementation lives in the UI domain."""
        return _main_dialog_lifecycle.open_project_profile(self, new_project, deps={"tk": tk, "messagebox": messagebox, "ProjectProfileWizard": ProjectProfileWizard})

    def open_project_details(self) -> None:
        self.open_settings(initial_tab="project")

    def ocr_current(self) -> None:
        """Public compatibility entrypoint with call-time patched collaborators."""
        return _main_ocr_current.ocr_current(self, deps={"replace": replace, "replace_rules_path": replace_rules_path, "qt_root": qt_root, "OCR_ENGINE_LABELS": OCR_ENGINE_LABELS, "load_replace_rules": load_replace_rules, "Image": Image, "normalize_page_rgb": normalize_page_rgb, "ocr_entries": ocr_entries, "export_ocred": export_ocred, "write_pdic": write_pdic, "pdic_path": pdic_path})

    def _export_controller_for_call(self) -> ExportController:
        """Preserve lazy controller identity and live constructor patchpoints."""
        return _controller_lifecycle.get_or_create_controller(
            self, "export_controller", ExportController,
        )

    def export_text(self) -> None:
        self._export_controller_for_call().export_text()

    def import_text(self) -> None:
        self._export_controller_for_call().import_text()

    def _crop_controller_for_call(self) -> CropController:
        """Preserve lazy controller identity and live constructor patchpoints."""
        return _controller_lifecycle.get_or_create_controller(
            self, "crop_controller", CropController,
        )

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
        """Preserve lazy controller identity and live constructor patchpoints."""
        return _controller_lifecycle.get_or_create_controller(
            self, "illustration_controller", IllustrationController,
        )

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
        return _main_pdic_persistence.order_key(
            self, word, key_func=collation_key, latin_order=LATIN_ORDER,
        )

    def _order_display_key(self, word: str) -> str:
        return _main_pdic_persistence.order_display_key(
            self, word, key_func=display_key, latin_order=LATIN_ORDER,
        )

    def check_headword_order(self, all_pages: bool = False) -> None:
        self._review_controller_for_call().check_headword_order(all_pages)

    def _show_text_report(self, title: str, text: str) -> None:
        """Legacy Tk report entrypoint; build the report on the calling UI thread."""
        return _main_dialog_lifecycle.show_text_report(
            self, title, text, deps={
                "tk": tk, "ttk": ttk,
                "fit_window_to_work_area": fit_window_to_work_area,
                "preferred_font_family": preferred_font_family,
            },
        )

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
        """Retain live parsing/fill callbacks during lazy Headword creation."""
        return _controller_lifecycle.get_or_create_controller(
            self, "headword_controller", HeadwordController,
            parse_words_of_pages_text=_parse_words_of_pages_text,
            fill_page_entries=_fill_page_entries,
        )

    def select_existing_headwords_file(self) -> None:
        self._headword_controller_for_call().select_existing_headwords_file()

    def fill_existing_headwords(self) -> None:
        self._headword_controller_for_call().fill_existing_headwords()

    def import_legacy_words(self) -> bool:
        return _lexicon_compare.import_legacy_words(self, _lexicon_compare_deps())


    def _default_old_new_compare_source(self) -> Path | None:
        return _lexicon_compare._default_old_new_compare_source(self, _lexicon_compare_deps())


    def _looks_page_aware_compare_source(self, path: Path) -> bool:
        return _lexicon_compare._looks_page_aware_compare_source(self, _lexicon_compare_deps(), path)


    def compare_old_new_selected_scope(self, force_choose: bool = False) -> None:
        return _lexicon_compare.compare_old_new_selected_scope(self, _lexicon_compare_deps(), force_choose)


    def open_review(self) -> None:
        """Legacy Tk callback; real implementation lives in the UI domain."""
        return _main_dialog_lifecycle.open_review(self, deps={"tk": tk, "ReviewWindow": ReviewWindow})

    def show_error(self, title: str, exc: Exception) -> None:
        return _main_app_lifecycle.show_error(
            self, title, exc,
            deps={"messagebox": messagebox, "traceback": traceback},
        )


def main() -> int:
    multiprocessing.freeze_support()
    app = PictureCaptureApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
