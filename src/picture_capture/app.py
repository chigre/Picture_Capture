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
from . import project_parameter_templates as _project_templates
from .appearance import (
    appearance_palette,
    apply_classic_widget_appearance,
    apply_native_titlebar_appearance,
    detect_system_appearance_mode,
    normalize_appearance_mode,
    normalize_appearance_preference,
    themed_display_image,
    usage_guide_palette,
)
from .gui_io import pdic_path, read_pdic, read_ppp, write_pdic, write_ppp, write_text_atomic
from .ocr_action_guard import LENS_MODE_LABELS, LENS_MODE_VALUES, guard_ocr_action_selection
from .models import (
    AppSettings, Entry as WordEntry, PolygonRegion, ProjectState, project_page_images,
    read_noncomment_lines, resolve_wordslist_path, resolved_tesseract_language,
)
from .pdic_restore import (
    build_page_lookup as _build_words_page_lookup,
    parse_merged_pdic_text as _parse_merged_pdic_text,
    resolve_page_token as _resolve_words_page_token,
    write_pdic_atomic as _write_pdic_atomic,
)

from .page_word_mapping import (
    _compare_page_word_mappings,
    _compare_page_word_sequences,
    _fill_page_entries,
    _page_word_mapping_text,
    _parse_words_of_pages_text,
)

from .review_text_helpers import (
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

from .layout_percent_helpers import (
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

from .page_list_helpers import (
    _fill_status_cell_style,
    _natural_text_key,
    _sorted_page_list_rows,
)

from .overlay_layout_helpers import (
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
    DEFAULT_HEADWORD_FILTER_RULES,
    HEADWORD_FILTER_RULES_FILENAME,
    compact_ocr_cache_file,
    parse_headword_filter_rules,
)
from .environment_center import EnvironmentCenterWindow
from .runtime_environment import legacy_user_config_files, resolve_paddle_device, user_config_root
from .ui_compat import (
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
from .ui.settings import project as _settings_project_ui
from .ui.settings import illustration as _settings_illustration_ui
from .ui.controllers import (
    CanvasController, CropController, DetectionController, ExportController,
    HeadwordController, IllustrationController, PageController, ProjectController,
    ReviewController, SESSION_STATE_FILENAME, SessionController,
)
from .ui.text_wrap import (
    _label_measure, _mixed_ui_wrap_tokens, _normalize_ui_paragraphs,
    _wrap_mixed_ui_text,
)
from .ui.dialogs.usage_guide import UsageGuideWindow
from .ui.dialogs.common import _build_modern_dialog_heading
from .ui.dialogs.old_new_comparison import OldNewComparisonWindow
from .ui.dialogs.ocr_conflict import OCRConflictReviewDialog
from .ui.dialogs.crop_settings import CropSettingsDialog
from .layout_detection import detect_layout_consistency, detect_layout_parameters
from .layout_transform import LayoutTransform
from .coordinate_space import SOURCE_COORDINATE_SPACE, coordinate_contract
from .crop.settings import (
    CROP_SETTINGS_VERSION,
    normalize_crop_settings_payload as _normalize_crop_settings_payload,
)
from .collation import (
    LATIN_ORDER, available_profile_labels, collation_key, display_key,
    parse_custom_order, profile_label,
)
from .dictionary_profile import (
    DEFAULT_PROFILE_ID, PROFILE_FILENAME, available_dictionary_profiles,
    dictionary_profile_preset,
    effective_project_profile_id,
    language_effective_settings, managed_profile_setting_names, profile_effective_settings,
    profile_layout_summary, write_project_profile,
)
from .profile_wizard import ProjectProfileWizard, _screen_work_area
from .profile_semantics import (
    effective_page_settings, entry_allowed_by_page_template, page_template_analysis_image,
)
from .image_utils import normalize_page_rgb
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
from .preprocess_geometry import perspective_from_quad
from .page_sections import (
    PageSection, read_page_sections, write_page_sections, v_is_inside_sections,
)
from .reference_index import contains_cjk, reference_sort_key
from .network_lookup import LexicalLookupResult, lookup_word_free, web_search_url
from .cc_cedict import (
    DOWNLOAD_PAGE_URL as CC_CEDICT_DOWNLOAD_PAGE_URL,
    install_from_file as install_cc_cedict_from_file,
    simplified_candidates as cc_cedict_simplified_candidates,
    status as cc_cedict_status,
)
from .chinese_simplify import simplify_text
from .simplified_review import entry_key as simplified_entry_key, read_records as read_simplified_records, write_records as write_simplified_records
from .training_export import (
    TrainingExportCancelled, copy_project_context, export_training_page,
    make_training_zip, write_training_manifest,
)
from .text_encoding import read_text_detected
from .unicode_nonbmp_input import (
    attach_nonbmp_unicode_input, close_nonbmp_unicode_input,
)
from .overlay_opacity import (
    add_quick_opacity_control, clear_alpha_line_photos,
    create_alpha_canvas_line, release_alpha_line_photos,
)
from .illustration_polygon_edit import nearest_polygon_segment
from .illustration_fill_opacity import (
    add_quick_illustration_fill_opacity_control, clear_alpha_polygon_records,
    create_alpha_canvas_polygon, refresh_alpha_polygon_fill,
)
from .ocr_crop_preview_ui import (
    add_ocr_crop_preview_control,
    draw_ocr_crop_preview,
)
from .layout_visualization_ui_v3 import (
    add_layout_visualization_controls,
    draw_layout_visualization_if_enabled,
)
from .auxiliary_line_controller import AuxiliaryLineController
from .auxiliary_lines import AuxiliaryLineEdits
from .entry_classification import classified_entry_crop_height
from .review_entry_classification_ui import (
    initialize_review_entry_classification,
    sync_review_entry_classification,
)
from .project_storage import (
    STORAGE_DIRNAME, ensure_project_storage, exports_root, has_legacy_project_data,
    headword_filter_rules_path, is_managed_project, migrate_legacy_project,
    ocr_cache_root, ppp_read_path_for_image, ppp_write_path_for_image, simplified_review_path_for_image,
    profile_path as project_profile_path, qt_root, replace_rules_path, settings_path,
    training_exports_root, word_fill_status_path, words_of_pages_default_path,
)
from .recent_projects import (
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

# ISO 639-1 codes for project metadata. Common dictionary languages are kept at
# the front of the readonly selectors; the rest remain alphabetized.
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
) -> tuple[int, int, int, int]:
    """Return a proofreading crop box using canonical Entry classification."""
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
    height = classified_entry_crop_height(
        entry,
        settings,
        regular_height=regular_height,
        oversized_height=oversized_height,
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
    """Apply filtered-review edits using exact original-image X/Y only."""
    target_path = pdic_path(page)
    original_entries = read_pdic(target_path)
    working = [replace(entry) for entry in original_entries]
    used: set[int] = set()
    planned: list[tuple[int, int, int, str]] = []
    conflicts: list[str] = []
    for change in changes:
        x, y = int(change["x"]), int(change["y"])
        original_word = str(change.get("original_word") or "")
        new_word = (
            str(change.get("new_word") or "")
            .replace("\r", " ").replace("\n", " ").replace("#", "＃").strip()
        )
        exact = [
            i for i, entry in enumerate(working)
            if i not in used and int(entry.x) == x and int(entry.y) == y
        ]
        if len(exact) > 1:
            preferred = [i for i in exact if working[i].word == original_word]
            exact = preferred or exact
        if len(exact) != 1:
            conflicts.append(f"{page.name}: ({x},{y}) {original_word}")
            continue
        entry_index = exact[0]
        used.add(entry_index)
        working[entry_index].word = new_word
        planned.append((int(page_index), x, y, new_word))
    if conflicts:
        return [], conflicts
    with Image.open(page) as opened:
        image_width = int(opened.width)
    page_links = (
        page.stem,
        pages[page_index - 1].stem if page_index > 0 else "@",
        pages[page_index + 1].stem if page_index + 1 < len(pages) else "@",
    )
    try:
        _write_pdic_atomic(target_path, working, image_width, page_links)
        verified = read_pdic(target_path)
        if len(verified) != len(working):
            raise RuntimeError("保存后 PDIC 行数发生变化")
        expected = {(row[1], row[2]): row[3] for row in planned}
        actual: dict[tuple[int, int], list[str]] = {}
        for entry in verified:
            actual.setdefault((int(entry.x), int(entry.y)), []).append(entry.word)
        for key, value in expected.items():
            if actual.get(key, []).count(value) != 1:
                raise RuntimeError(f"保存后坐标 {key} 的文本校验失败")
    except Exception:
        _write_pdic_atomic(target_path, original_entries, image_width, page_links)
        raise
    return planned, []


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
        if name in {"main_entry_font_family", "review_entry_font_family"}:
            families = (
                AUTO_FONT_FAMILY,
                *tuple(sorted(set(font.families()), key=str.casefold)),
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
        return ttk.Entry(parent, textvariable=var, width=28)

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
        help_body = ttk.Label(
            help_box,
            text=self._settings_help_body_var.get(),
            foreground="#555b63",
            justify="left",
        )
        help_body._pc_wrap_source = _normalize_ui_paragraphs(
            self._settings_help_body_var.get()
        )
        self._settings_help_body_label = help_body
        help_body.pack(anchor="w", fill="x", padx=(0, 8), pady=(7, 0))
        help_image = ttk.Label(help_box, anchor="center")
        help_separator = ttk.Separator(help_box, orient="horizontal")
        help_separator.pack(fill="x", pady=(14, 10))
        self._settings_help_image_widgets.append(
            (help_image, help_separator, help_box)
        )
        help_hint = ttk.Label(
            help_box,
            text="把鼠标停在设置项上、点击 ⓘ，或用 Tab/鼠标进入输入框时，"
                 "右侧会显示完整说明与版面图解；左侧只保留参数、单位和必要状态。",
            foreground="#7a8088",
            justify="left",
        )
        help_hint.pack(anchor="w", fill="x", padx=(0, 6))
        self._bind_responsive_labels(
            help_box,
            help_body,
            help_hint,
            horizontal_padding=34,
            min_wrap=120,
        )
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
            (illustration_tab, "插图"),
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
            "illustration": illustration_tab,
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

        # Reuse the project profile without duplicating the wizard.
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

        _settings_illustration_ui.build_illustration_settings_tab(self, illustration_tab)

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
        # Scroll regions update on Configure; keep the dialog modeless.
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
                    # Respect an explicit advanced backend override made in this
                    # dialog; only stale values inherited from the old language
                    # are replaced automatically.
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
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(560, width), min(420, height))
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
        self.review_right_section_expanded = {
            key: tk.BooleanVar(value=(key not in {"digit", "accent"}))
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
        for _var in self.digit_map_vars:
            _var.trace_add("write", lambda *_args: self._save_digit_map())
        initialize_review_entry_classification(self)

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

    def _review_image_area_width(self) -> int:
        """Return the usable crop-image width inside the proofreading left pane."""
        try:
            canvas_width = int(self.canvas.winfo_width())
        except (AttributeError, tk.TclError, TypeError, ValueError):
            return 1
        # Crop labels use padx=6 on both sides. Keeping that 12 px outside the
        # 99% image target prevents a nominally fitted strip from overflowing.
        return max(1, canvas_width - 12)

    def _review_canvas_configured(self, event: tk.Event) -> None:
        try:
            self.canvas.itemconfigure(self.rows_window, width=event.width)
        except tk.TclError:
            return
        if not self.review_zoom_auto:
            return
        usable_width = max(1, int(event.width) - 12)
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
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)
        self.review_panes = panes
        left = ttk.Frame(panes, style="PCR.Surface.TFrame")
        right = ttk.Frame(panes, padding=(8, 6), style="PCR.Surface.TFrame")
        panes.add(left, weight=0)
        panes.add(right, weight=1)

        # Left: high-frequency review actions first; low-frequency helpers stay folded.
        controls = ttk.Frame(left, padding=(7, 6, 7, 4), style="PCR.Toolbar.TFrame")
        controls.pack(fill="x")
        row1 = ttk.Frame(controls, style="PCR.Toolbar.TFrame")
        row1.pack(fill="x", pady=(0, 4))
        self.review_control_row = row1
        self._review_flat_button(row1, "保存", self.save, role="primary").pack(side="left")
        self._sync_autosave_label()
        ttk.Checkbutton(
            row1, textvariable=self.autosave_label_var, variable=self.parent.autosave_var,
            command=self._toggle_shared_autosave,
        ).pack(side="left", padx=(6, 0))
        ttk.Label(row1, text="校对模式：", style="PCR.Toolbar.TLabel").pack(side="left", padx=(8, 0))
        ttk.Radiobutton(
            row1, text="单页", variable=self.review_mode_var, value="single",
            command=self._change_review_mode,
        ).pack(side="left", padx=(2, 0))
        ttk.Radiobutton(
            row1, text="筛选", variable=self.review_mode_var, value="filter",
            command=self._change_review_mode,
        ).pack(side="left", padx=(2, 0))
        ttk.Button(
            row1, text="排序规则", command=self.open_sort_rules, style="PCR.Compact.TButton"
        ).pack(side="left", padx=(10, 0))
        ttk.Radiobutton(
            row1, text="当前页", variable=self.order_scope_var, value="current"
        ).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(
            row1, text="所有页", variable=self.order_scope_var, value="all"
        ).pack(side="left", padx=(4, 0))
        ttk.Button(
            row1, text="排序检查", width=7, command=self.run_order_check,
            style="PCR.Compact.TButton",
        ).pack(side="left", padx=(5, 0))
        ttk.Separator(controls, orient="horizontal").pack(fill="x", pady=(5, 0))

        focused = ttk.Frame(
            left, padding=(7, 3), style="PCR.Surface.TFrame"
        )
        focused.pack(fill="x", padx=(7, 7), pady=(0, 5))
        self.focused_panel_title = tk.StringVar(value="▸ 重点筛选校对")
        self.focused_panel_toggle = ttk.Label(
            focused, textvariable=self.focused_panel_title,
            style="PCR.Header.TLabel", cursor="hand2",
        )
        self.focused_panel_toggle.pack(fill="x")
        self.focused_panel_toggle.bind("<Button-1>", lambda _event: self._toggle_focused_panel())
        ttk.Separator(focused, orient="horizontal").pack(fill="x", pady=(3, 0))
        self.focused_panel_body = ttk.Frame(focused, style="PCR.Surface.TFrame")
        filter_row1 = ttk.Frame(self.focused_panel_body, style="PCR.Surface.TFrame")
        filter_row1.pack(fill="x")
        ttk.Button(
            filter_row1, text="筛选", command=self.run_focused_filter,
            style="PCR.Compact.TButton",
        ).pack(side="left")
        ttk.Label(filter_row1, text="页面范围").pack(side="left", padx=(7, 2))
        ttk.Entry(
            filter_row1, textvariable=self.focused_page_range_var, width=12,
            style="PCR.Compact.TEntry",
        ).pack(side="left")
        ttk.Checkbutton(
            filter_row1, text="OCR不匹配", variable=self.focused_include_mismatch_var,
        ).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            filter_row1, text="含特定字符", variable=self.focused_include_characters_var,
        ).pack(side="left", padx=(7, 0))
        ttk.Checkbutton(
            filter_row1, text="排除单字符", variable=self.focused_exclude_single_var,
        ).pack(side="left", padx=(7, 0))
        ttk.Checkbutton(
            filter_row1, text="排除参考词表", variable=self.focused_exclude_reference_var,
        ).pack(side="left", padx=(7, 0))

        filter_row2 = ttk.Frame(self.focused_panel_body, style="PCR.Surface.TFrame")
        filter_row2.pack(fill="x", pady=(4, 0))
        ttk.Label(filter_row2, text="特定字符（用','分隔）：").pack(side="left")
        ttk.Entry(
            filter_row2, textvariable=self.focused_characters_var,
            style="PCR.Compact.TEntry",
        ).pack(side="left", fill="x", expand=True, padx=(3, 8))
        ttk.Label(filter_row2, text="单批显示数量：").pack(side="left")
        ttk.Spinbox(
            filter_row2, from_=1, to=500, increment=1, width=6,
            textvariable=self.focused_batch_size_var, style="PCR.Compact.TSpinbox",
        ).pack(side="left")
        # Main review strip: vertical previous/next buttons flank the scrollable rows.
        strip = ttk.Frame(left, style="PCR.Surface.TFrame")
        strip.pack(fill="both", expand=True, padx=(4, 4), pady=(0, 4))
        # Page navigation is intentionally a little darker than ordinary
        # controls so it remains easy to find while proofreading without
        # competing visually with the crop/text rows.
        review_nav_bg = "#d7d7d7"
        review_nav_active_bg = "#c8c8c8"
        self.prev_page_button = tk.Button(
            strip, text="上\n一\n页", width=3, command=lambda: self.change_page(-1),
            bg=review_nav_bg, activebackground=review_nav_active_bg,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
        )
        self.prev_page_button.pack(side="left", fill="y", padx=(0, 4))
        editor_area = ttk.Frame(strip, style="PCR.Surface.TFrame")
        editor_area.pack(side="left", fill="both", expand=True)
        self.review_editor_area = editor_area
        self.next_page_button = tk.Button(
            strip, text="下\n一\n页", width=3, command=lambda: self.change_page(1),
            bg=review_nav_bg, activebackground=review_nav_active_bg,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
        )
        self.next_page_button.pack(side="right", fill="y", padx=(4, 0))

        self.canvas = tk.Canvas(
            editor_area,
            highlightthickness=0,
            borderwidth=0,
            bg="#f6f7f9",
        )
        scroll = ttk.Scrollbar(editor_area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.rows = ttk.Frame(self.canvas, style="PCR.Surface.TFrame")
        self.rows_window = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")
        self.rows.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._review_canvas_configured)
        for widget in (self.canvas, self.rows):
            widget.bind("<MouseWheel>", self.scroll_rows)
            widget.bind("<Button-4>", lambda e: self.scroll_rows_linux(-1))
            widget.bind("<Button-5>", lambda e: self.scroll_rows_linux(1))

        # Right: every logical block is collapsible; all start expanded.
        review_info = self._review_collapsible_section(
            right, "display", "显示设置", padding=6, fill="x", pady=(0, 6)
        )

        def add_review_height_control(
            label: str,
            percent_var: tk.StringVar,
            pixel_var: tk.StringVar,
            *,
            allow_zero: bool = False,
        ) -> ttk.Spinbox:
            control_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
            control_row.pack(fill="x", pady=(0, 3))
            ttk.Label(control_row, text=label).pack(side="left")
            percent_spin = ttk.Spinbox(
                control_row,
                from_=0.0 if allow_zero else 0.01,
                to=100.0,
                increment=0.01,
                width=6,
                textvariable=percent_var,
                style="PCR.Compact.TSpinbox",
            )
            percent_spin.pack(side="left")
            ttk.Label(control_row, text="%").pack(side="left", padx=(2, 6))
            ttk.Spinbox(
                control_row,
                from_=0 if allow_zero else 1,
                to=500,
                increment=1,
                width=6,
                textvariable=pixel_var,
                style="PCR.Compact.TSpinbox",
            ).pack(side="left")
            ttk.Label(control_row, text="px").pack(side="left", padx=(2, 0))
            return percent_spin

        self.review_line_height_spin = add_review_height_control(
            "普通字/行高：", self.review_line_height_var, self.review_line_height_px_var
        )
        add_review_height_control(
            "行间空：",
            self.review_row_padding_var,
            self.review_row_padding_px_var,
            allow_zero=True,
        )
        add_review_height_control(
            "普通词条行切图高：",
            self.review_regular_crop_height_var,
            self.review_regular_crop_height_px_var,
        )
        self.review_single_cjk_line_height_spin = add_review_height_control(
            "大字头切图高：",
            self.review_single_cjk_line_height_var,
            self.review_single_cjk_line_height_px_var,
        )

        zoom_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
        zoom_row.pack(fill="x")
        ttk.Label(zoom_row, text="词条切图显示大小：").pack(side="left")
        ttk.Button(
            zoom_row, text="−", width=3, command=lambda: self.change_review_zoom(0.8),
            style="PCR.Tool.TButton",
        ).pack(side="left")
        review_zoom_entry = ttk.Entry(
            zoom_row, textvariable=self.review_zoom_var, width=10, justify="center",
            style="PCR.Compact.TEntry",
        )
        review_zoom_entry.pack(side="left", padx=2)
        review_zoom_entry.bind("<Return>", self.apply_review_zoom_text)
        review_zoom_entry.bind("<FocusOut>", self.apply_review_zoom_text)
        ttk.Button(
            zoom_row, text="+", width=3, command=lambda: self.change_review_zoom(1.25),
            style="PCR.Tool.TButton",
        ).pack(side="left")
        ttk.Button(
            zoom_row, text="自动", width=5, command=self.reset_review_zoom,
            style="PCR.Compact.TButton",
        ).pack(side="left", padx=(4, 0))

        padding_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
        padding_row.pack(fill="x", pady=(4, 0))
        ttk.Label(
            padding_row, text="文本左边距：", style="PCR.Black.TLabel"
        ).pack(side="left")
        self.review_left_padding_spin = ttk.Spinbox(
            padding_row, from_=0, to=80, increment=1, width=4,
            textvariable=self.review_left_padding_var, style="PCR.Compact.TSpinbox",
        )
        self.review_left_padding_spin.pack(side="left")
        ttk.Label(
            padding_row, text="px", style="PCR.Body.TLabel"
        ).pack(side="left", padx=(2, 9))
        ttk.Label(
            padding_row, text="上下边距：", style="PCR.Black.TLabel"
        ).pack(side="left")
        self.review_vertical_padding_spin = ttk.Spinbox(
            padding_row, from_=0, to=30, increment=1, width=4,
            textvariable=self.review_vertical_padding_var, style="PCR.Compact.TSpinbox",
        )
        self.review_vertical_padding_spin.pack(side="left")
        ttk.Label(
            padding_row, text="px", style="PCR.Body.TLabel"
        ).pack(side="left", padx=(2, 0))

        font_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
        font_row.pack(fill="x", pady=(5, 0))
        ttk.Label(font_row, text="词条字体：").pack(side="left")
        review_families = (AUTO_FONT_FAMILY, *tuple(sorted(set(font.families()), key=str.casefold)))
        self.review_font_combo = ttk.Combobox(
            font_row, textvariable=self.review_font_family_var, values=review_families,
            state="normal", width=15, style="PCR.Compact.TCombobox",
        )
        self.review_font_combo.pack(side="left")
        ttk.Label(font_row, text="字号：").pack(side="left", padx=(7, 2))
        self.review_font_size_spin = ttk.Spinbox(
            font_row, from_=6, to=96, increment=1, width=4,
            textvariable=self.review_font_size_var, style="PCR.Compact.TSpinbox",
        )
        self.review_font_size_spin.pack(side="left")
        ttk.Checkbutton(font_row, text="粗体", variable=self.review_font_bold_var).pack(side="left", padx=(7, 0))
        ttk.Checkbutton(font_row, text="斜体", variable=self.review_font_italic_var).pack(side="left", padx=(5, 0))

        simplified_font_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
        simplified_font_row.pack(fill="x", pady=(4, 0))
        ttk.Label(simplified_font_row, text="简体字体：").pack(side="left")
        self.review_simplified_font_combo = ttk.Combobox(
            simplified_font_row, textvariable=self.review_simplified_font_family_var,
            values=review_families, state="normal", width=15,
            style="PCR.Compact.TCombobox",
        )
        self.review_simplified_font_combo.pack(side="left")
        ttk.Label(simplified_font_row, text="字号：").pack(side="left", padx=(7, 2))
        self.review_simplified_font_size_spin = ttk.Spinbox(
            simplified_font_row, from_=6, to=96, increment=1, width=4,
            textvariable=self.review_simplified_font_size_var, style="PCR.Compact.TSpinbox",
        )
        self.review_simplified_font_size_spin.pack(side="left")
        ttk.Checkbutton(
            simplified_font_row, text="粗体", variable=self.review_simplified_font_bold_var
        ).pack(side="left", padx=(7, 0))
        ttk.Checkbutton(
            simplified_font_row, text="斜体", variable=self.review_simplified_font_italic_var
        ).pack(side="left", padx=(5, 0))

        digit_box = self._review_collapsible_section(
            right, "digit", "数字替换映射", padding=6, fill="x", pady=(0, 6)
        )
        digit_rows = [
            ttk.Frame(digit_box, style="PCR.Surface.TFrame"),
            ttk.Frame(digit_box, style="PCR.Surface.TFrame"),
        ]
        digit_rows[0].pack(fill="x")
        digit_rows[1].pack(fill="x", pady=(3, 0))
        ttk.Checkbutton(
            digit_rows[0], text="启用", variable=self.replace_digits,
            style="PCR.Body.TCheckbutton",
        ).pack(side="left", padx=(0, 8))
        for index, digit in enumerate(self.DIGIT_KEYS):
            host = digit_rows[0 if index < 5 else 1]
            ttk.Label(host, text=f"{digit}→").pack(side="left", padx=(2, 0))
            ttk.Entry(
                host, textvariable=self.digit_map_vars[index], width=3, justify="center",
                style="PCR.Compact.TEntry",
            ).pack(side="left", padx=(0, 5))

        accent_box = self._review_collapsible_section(
            right, "accent", "变音字符", padding=6, fill="x", pady=(0, 6)
        )
        ttk.Label(
            accent_box, text="左键输入；右键复制", style="PCR.Muted.TLabel",
        ).pack(anchor="w", pady=(0, 3))
        for label, chars in self.ACCENT_GROUPS:
            accent_row = ttk.Frame(accent_box, style="PCR.Surface.TFrame")
            accent_row.pack(fill="x", pady=1)
            ttk.Label(accent_row, text=label, width=4, anchor="e").pack(side="left", padx=(0, 4))
            for char in chars:
                accent_button = ttk.Button(
                    accent_row, text=char, width=3,
                    command=lambda c=char: self.insert_char(c),
                    style="PCR.Tool.TButton",
                )
                accent_button.pack(side="left", padx=1)
                accent_button.bind(
                    "<Button-3>", lambda _event, c=char: self.copy_char(c), add="+"
                )
        # Keep the four OCR sources on a single compact line. Each available
        # result remains clickable, preserving the previous quick-fill workflow.
        ocr_box = self._review_collapsible_section(
            right, "ocr", "OCR结果", padding=6, fill="x", pady=(0, 6)
        )
        ocr_compare_row = ttk.Frame(ocr_box, style="PCR.Surface.TFrame")
        ocr_compare_row.pack(fill="x")
        ttk.Label(
            ocr_compare_row, text="与OCR比较：", style="PCR.Body.TLabel"
        ).pack(side="left")
        self.review_ocr_compare_combo = ttk.Combobox(
            ocr_compare_row, textvariable=self.review_ocr_compare_var,
            values=tuple(self.OCR_COMPARE_LABEL_TO_KEY), state="readonly", width=10,
            style="PCR.Compact.TCombobox",
        )
        self.review_ocr_compare_combo.pack(side="left", padx=(2, 0))
        self.review_ocr_compare_combo.bind(
            "<<ComboboxSelected>>", self._change_review_ocr_compare_source
        )
        ttk.Checkbutton(
            ocr_compare_row, text="简体化词条", variable=self.review_show_simplified_var,
            command=self._toggle_review_simplified, style="PCR.Body.TCheckbutton",
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            ocr_compare_row, text="重新简体化", command=self.regenerate_simplified_current_page,
            style="PCR.Compact.TButton",
        ).pack(side="left", padx=(6, 0))

        ocr_row = ttk.Frame(ocr_box, style="PCR.Surface.TFrame")
        ocr_row.pack(fill="x", pady=(4, 0))
        self.ocr_options = ttk.Frame(ocr_row, style="PCR.Surface.TFrame")
        self.ocr_options.pack(side="left", fill="x", expand=True)

        network_box = self._review_collapsible_section(
            right, "network", "词条联网核验结果",
            padding=6, fill="x", pady=(0, 6),
        )
        network_actions = ttk.Frame(network_box, style="PCR.Surface.TFrame")
        network_actions.pack(fill="x")
        ttk.Checkbutton(
            network_actions, text="自动检查", variable=self.network_lookup_enabled_var,
            command=self._toggle_network_lookup,
        ).pack(side="left")
        ttk.Button(
            network_actions, text="立即",
            command=lambda: self._schedule_network_lookup(force=True),
            style="PCR.Compact.TButton",
        ).pack(side="left", padx=(5, 0))
        self.cc_cedict_lookup_button = ttk.Button(
            network_actions, textvariable=self.cc_cedict_lookup_var,
            command=self.manage_cc_cedict, style="PCR.Tool.TButton",
        )
        self.cc_cedict_lookup_button.pack(side="left", padx=(5, 0))
        self.cc_simplified_compare_button = ttk.Button(
            network_actions, textvariable=self.cc_simplified_compare_var,
            command=self.show_cc_simplified_comparison, style="PCR.Tool.TButton",
        )
        self.cc_simplified_compare_button.pack(side="left", padx=(5, 0))

        network_actions_more = ttk.Frame(network_box, style="PCR.Surface.TFrame")
        network_actions_more.pack(fill="x", pady=(4, 0))
        ttk.Button(
            network_actions_more, textvariable=self.moedict_lookup_var,
            command=lambda: self.open_lookup_source("萌典"), style="PCR.Tool.TButton",
        ).pack(side="left")
        ttk.Button(
            network_actions_more, textvariable=self.wiktionary_lookup_var,
            command=lambda: self.open_lookup_source("维基词典"), style="PCR.Tool.TButton",
        ).pack(side="left", padx=(5, 0))
        ttk.Button(
            network_actions_more, text="网络搜索", command=self.open_network_web_search,
            style="PCR.Tool.TButton",
        ).pack(side="left", padx=(5, 0))
        self.network_status_label = tk.Label(
            network_box,
            textvariable=self.network_lookup_status_var,
            anchor="w",
            justify="left",
            fg="#555555",
            bg="#f6f7f9",
        )
        self.network_status_label.pack(fill="x", pady=(4, 0))
        self._refresh_cc_cedict_button_idle()

        ref_box = self._review_collapsible_section(
            right, "reference", "参考词表",
            padding=6, fill="both", expand=True, pady=(0, 0),
        )
        ref_actions = ttk.Frame(ref_box, style="PCR.Surface.TFrame")
        ref_actions.pack(fill="x", pady=(0, 3))
        ttk.Button(
            ref_actions, text="选择文件", command=self.choose_wordslist_file,
            style="PCR.Compact.TButton",
        ).pack(side="left")
        ttk.Label(ref_actions, text="定位：").pack(side="left", padx=(8, 2))
        self.wordslist_locator_combo = ttk.Combobox(
            ref_actions, textvariable=self.wordslist_locator_var,
            values=tuple(self.WORDSLIST_LOCATOR_LABEL_TO_KEY), state="readonly", width=18,
            style="PCR.Compact.TCombobox",
        )
        self.wordslist_locator_combo.pack(side="left")
        self.wordslist_locator_combo.bind("<<ComboboxSelected>>", self._change_wordslist_locator_mode)
        ttk.Button(
            ref_actions, text="从所选词开始填充至本页结束", command=self.fill_words,
            style="PCR.Compact.TButton",
        ).pack(side="left", padx=(8, 0))

        word_nav = ttk.Frame(ref_box, style="PCR.Surface.TFrame")
        word_nav.pack(fill="x", pady=(0, 0))
        self.word_window_var = tk.StringVar(value="wordslist.txt | 0-0 / 0")
        ttk.Label(
            word_nav, textvariable=self.word_window_var, style="PCR.Body.TLabel"
        ).pack(side="left", fill="x", expand=True)
        word_nav_buttons = ttk.Frame(word_nav, style="PCR.Surface.TFrame")
        word_nav_buttons.pack(side="right")
        ttk.Button(
            word_nav_buttons, text="前100", width=7, command=lambda: self.shift_wordslist_window(-1),
            style="PCR.Tool.TButton",
        ).pack(side="left")
        ttk.Button(
            word_nav_buttons, text="后100", width=7, command=lambda: self.shift_wordslist_window(1),
            style="PCR.Tool.TButton",
        ).pack(side="left", padx=(4, 0))

        word_family = preferred_font_family(
            self, ("Cambria", "Times New Roman", "Times", "DejaVu Serif")
        )
        number_family = preferred_font_family(
            self, ("Segoe UI", "Arial", "Helvetica", "DejaVu Sans")
        )
        self.word_list = tk.Text(
            ref_box,
            exportselection=False,
            font=(word_family, 14),
            wrap="none",
            state="disabled",
            cursor="hand2",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#d8dde5",
            highlightcolor="#d8dde5",
            selectbackground="#dce8f7",
            selectforeground="#30343b",
        )
        self.word_list.tag_configure(
            "wordslist_number", font=(number_family, 10), foreground="#6b7280"
        )
        self.word_list.tag_configure("wordslist_word", font=(word_family, 14))
        self.word_list.tag_configure(
            "wordslist_target", background="#d9d9d9", foreground="#111827"
        )
        # The reference list owns its row highlighting and mixed typography.
        self.word_list._pc_skip_classic_appearance = True
        self.word_list.pack(fill="both", expand=True, pady=(4, 0))
        self._configure_word_list_appearance()
        self.word_list.bind("<ButtonRelease-1>", self.use_selected_word)
        self.refresh_wordslist_display()

    def _change_review_mode(self) -> None:
        """Switch modes without running a filter merely because 筛选 was selected."""
        if self.review_mode_var.get() != "single":
            self.parent.status_var.set("已选择筛选模式；设置条件后点击【筛选】才会刷新工作区。")
            return
        self._flush_focused_changes_now()
        self._filter_rows_active = False
        self._set_filter_navigation(False)
        self.parent._invalidate_ui_worker(f"focused-filter-scan-{id(self)}")
        self.parent._invalidate_ui_worker(f"focused-filter-scan-rest-{id(self)}")
        self.parent._invalidate_ui_worker(f"focused-filter-render-{id(self)}")
        self.parent._invalidate_ui_worker(f"focused-filter-prefetch-{id(self)}")
        self._filter_batch_render_cache.clear()
        self._filter_prefetch_key = None
        self._filter_scan_complete = True
        self._request_render_rows(focus_index=0, reset_scroll=True)

    def _set_filter_navigation(self, active: bool) -> None:
        """Reuse the normal side navigation as batch navigation in filter mode."""
        try:
            self.prev_page_button.configure(text=("上\n一\n批" if active else "上\n一\n页"))
            self.next_page_button.configure(text=("下\n一\n批" if active else "下\n一\n页"))
        except tk.TclError:
            return

    def _persist_focused_filter_settings(self) -> None:
        settings = self.parent.settings
        settings.focused_review_include_ocr_mismatch = bool(
            self.focused_include_mismatch_var.get()
        )
        settings.focused_review_include_characters = bool(
            self.focused_include_characters_var.get()
        )
        settings.focused_review_exclude_single_character = bool(
            self.focused_exclude_single_var.get()
        )
        settings.focused_review_exclude_reference_words = bool(
            self.focused_exclude_reference_var.get()
        )
        settings.focused_review_characters = self.focused_characters_var.get().strip()
        try:
            batch_size = int(self.focused_batch_size_var.get().strip())
        except ValueError as exc:
            raise ValueError("单批显示数量必须是整数。") from exc
        settings.focused_review_batch_size = max(1, min(500, batch_size))
        self.focused_batch_size_var.set(str(settings.focused_review_batch_size))
        self.parent.save_settings()

    def _clear_review_workspace(self, message: str = "") -> None:
        for child in self.rows.winfo_children():
            child.destroy()
        self.vars.clear()
        self.row_entries.clear()
        self.editors.clear()
        self.editor_frames.clear()
        self.simplified_vars.clear()
        self.simplified_editors.clear()
        self.simplified_search_buttons.clear()
        self.simplified_actual_values.clear()
        self.simplified_manual_flags.clear()
        self.simplified_auto_refresh_flags.clear()
        self.editor_crop_widths.clear()
        self.thumbnails.clear()
        self.filter_vars = []
        self.filter_editors = []
        self.filter_thumbnails = []
        self._filter_current_batch_targets = []
        if message:
            ttk.Label(
                self.rows, text=message, style="PCR.Body.TLabel",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=24)
            self.rows.columnconfigure(0, weight=1)

    def run_focused_filter(self) -> None:
        """Render the first batch early, then stream and pre-render later batches."""
        project = self.parent.project
        if project is None:
            return
        try:
            # Reuse the main-window 【指定】 parser exactly. This preserves
            # filename-number matching, leading zeroes, mixed comma ranges and
            # all accepted hyphen/tilde variants without a second parser.
            indices = self.parent._parse_page_spec(
                self.focused_page_range_var.get()
            )
            self._persist_focused_filter_settings()
        except Exception as exc:
            messagebox.showerror("筛选条件无效", str(exc), parent=self)
            return

        include_mismatch = bool(self.focused_include_mismatch_var.get())
        include_chars = bool(self.focused_include_characters_var.get())
        exclude_single = bool(self.focused_exclude_single_var.get())
        exclude_reference = bool(self.focused_exclude_reference_var.get())
        tokens = _focused_review_character_tokens(self.focused_characters_var.get())
        if include_chars and not tokens:
            messagebox.showinfo(
                "特定字符为空",
                "已勾选【含特定字符】，请先输入至少一个字符。",
                parent=self,
            )
            return

        if not getattr(self, "_filter_rows_active", False):
            self.save(redraw_main=False)
        self.review_mode_var.set("filter")
        self._filter_rows_active = True
        self._set_filter_navigation(True)
        self.parent._invalidate_ui_worker(self._review_render_worker_key)
        self.parent._invalidate_ui_worker(f"focused-filter-scan-rest-{id(self)}")
        self.parent._invalidate_ui_worker(f"focused-filter-render-{id(self)}")
        self.parent._invalidate_ui_worker(f"focused-filter-prefetch-{id(self)}")
        self._filter_batch_render_cache.clear()
        self._filter_prefetch_key = None
        self._filter_scan_complete = False
        self.filtered_targets = []
        self.filtered_batch_index = 0
        self._clear_review_workspace("正在快速筛选首批…")
        self.filter_batch_var.set("正在筛选首批…")
        self._filter_scan_serial += 1
        serial = self._filter_scan_serial

        pages = list(project.images)
        project_root = project.root
        reference_words = set(self.parent._project_words) if exclude_reference else set()
        y_tolerance = max(
            6, round(max(1, int(self.parent.settings.character_height)) * 0.55)
        )
        ocr_compare_key = self.OCR_COMPARE_LABEL_TO_KEY.get(
            self.review_ocr_compare_var.get(), "fusion"
        )
        first_batch_size = self._focused_batch_size()

        def scan_page(page_index: int) -> tuple[list[dict], bool]:
            """Fast filter pass using only PDIC and OCR JSON, never page pixels."""
            page = pages[page_index]
            entries = read_pdic(pdic_path(page))
            if not entries:
                return [], False

            candidates: list[dict] = []
            missing_ocr = False
            cache = ocr_cache_root(project_root) / f"{page.stem}.json"
            if cache.exists():
                try:
                    payload = json.loads(cache.read_text(encoding="utf-8"))
                    if isinstance(payload, dict):
                        candidates = [
                            row for row in payload.get("review_candidates", [])
                            if isinstance(row, dict)
                        ]
                except Exception:
                    candidates = []
            elif include_mismatch:
                missing_ocr = True

            targets: list[dict] = []
            has_positive_filter = include_mismatch or include_chars
            for entry in entries:
                word = str(entry.word or "").strip()
                if exclude_single and _focused_review_is_single_character(word):
                    continue
                if exclude_reference and word in reference_words:
                    continue

                candidate = _candidate_for_entry_from_list(
                    entry, candidates, y_tolerance=y_tolerance
                )
                ocr_words = {
                    source: _candidate_word_for_ocr_source(candidate, source)
                    for source in ("fusion", "paddle", "tesseract", "lens")
                }
                ocr_word = ocr_words.get(ocr_compare_key, "")
                mismatch = bool(
                    include_mismatch
                    and ocr_word
                    and _review_similarity_key(word)
                    != _review_similarity_key(ocr_word)
                )
                matched_tokens = tuple(
                    token for token in tokens if token and token in word
                ) if include_chars else ()
                if has_positive_filter and not mismatch and not matched_tokens:
                    continue

                reasons: list[str] = []
                if mismatch:
                    reasons.append(f"OCR不匹配（OCR结果：{ocr_word}）")
                if matched_tokens:
                    reasons.append("含字符：" + "、".join(matched_tokens))
                if not has_positive_filter:
                    reasons.append("符合排除条件后的剩余词条")
                targets.append({
                    "page_index": int(page_index),
                    "page_name": page.name,
                    "page_stem": page.stem,
                    # Filled from reading-order geometry only when the row is
                    # actually rendered; this keeps the scan path image-free.
                    "column_number": 1,
                    "sequence_number": 0,
                    "x": int(entry.x),
                    "y": int(entry.y),
                    "original_word": word,
                    "current_word": word,
                    "ocr_source_key": ocr_compare_key,
                    "ocr_word": ocr_word,
                    "ocr_words": ocr_words,
                    "reasons": tuple(reasons),
                })
            return targets, missing_ocr

        def first_worker():
            targets: list[dict] = []
            pages_without_ocr = 0
            next_position = len(indices)
            for position, page_index in enumerate(indices):
                page_targets, missing_ocr = scan_page(page_index)
                targets.extend(page_targets)
                pages_without_ocr += int(missing_ocr)
                # Stop at a page boundary as soon as one complete UI batch is
                # available. Later pages are streamed in batch-sized chunks.
                if len(targets) >= first_batch_size:
                    next_position = position + 1
                    break
            return targets, pages_without_ocr, next_position

        def start_remaining_scan(
            start_position: int, pages_without_ocr: int, initial_count: int,
        ) -> None:
            if start_position >= len(indices):
                self._filter_scan_complete = True
                self._update_filter_batch_indicator()
                extra = (
                    f"；{pages_without_ocr} 页无 OCR 缓存"
                    if include_mismatch and pages_without_ocr else ""
                )
                self.parent.status_var.set(
                    f"筛选完成：{len(indices)} 页共 {len(self.filtered_targets)} 条{extra}"
                )
                self._update_title()
                self._schedule_filter_next_batch_preload()
                return

            # If the previous page crossed a batch boundary, keep its overflow.
            # Scan only until the next complete batch is available, then hand
            # that batch back to the UI immediately so its crops can pre-render.
            remainder = int(initial_count) % first_batch_size
            needed_for_next = first_batch_size - remainder if remainder else first_batch_size

            def remaining_worker():
                additions: list[dict] = []
                missing_total = pages_without_ocr
                next_position = len(indices)
                for position in range(start_position, len(indices)):
                    page_index = indices[position]
                    page_targets, missing_ocr = scan_page(page_index)
                    additions.extend(page_targets)
                    missing_total += int(missing_ocr)
                    if len(additions) >= needed_for_next:
                        next_position = position + 1
                        break
                return additions, missing_total, next_position

            def remaining_done(payload) -> None:
                if (
                    serial != self._filter_scan_serial
                    or not getattr(self, "_filter_rows_active", False)
                ):
                    return
                additions, missing_total, next_position = payload
                had_available = self._filter_available_target_count()
                self.filtered_targets.extend(additions)
                self._filter_scan_complete = next_position >= len(indices)
                available_now = self._filter_available_target_count()
                self._update_filter_batch_indicator()
                self._update_title()

                if self._filter_scan_complete:
                    extra = (
                        f"；{missing_total} 页无 OCR 缓存"
                        if include_mismatch and missing_total else ""
                    )
                    self.parent.status_var.set(
                        f"筛选完成：{len(indices)} 页共 {len(self.filtered_targets)} 条{extra}"
                    )
                else:
                    self.parent.status_var.set(
                        f"后台筛选中：已扫描 {next_position}/{len(indices)} 页，"
                        f"当前命中 {len(self.filtered_targets)} 条"
                    )

                if had_available <= 0 < available_now:
                    self.filtered_batch_index = 0
                    self._request_filter_batch_render()
                else:
                    self._schedule_filter_next_batch_preload()

                if not self._filter_scan_complete:
                    start_remaining_scan(
                        next_position, missing_total, len(self.filtered_targets)
                    )

            def remaining_failed(exc, detail) -> None:
                if detail:
                    print(detail)
                if serial != self._filter_scan_serial:
                    return
                self.parent.status_var.set(f"后续页面筛选失败：{exc}")

            self.parent._start_ui_worker(
                f"focused-filter-scan-rest-{id(self)}",
                remaining_worker, remaining_done, remaining_failed,
            )

        def first_done(payload) -> None:
            if (
                serial != self._filter_scan_serial
                or not getattr(self, "_filter_rows_active", False)
            ):
                return
            targets, pages_without_ocr, next_position = payload
            self.filtered_targets = list(targets)
            self.filtered_batch_index = 0
            self._filter_scan_complete = next_position >= len(indices)
            self._update_title()

            if self.filtered_targets:
                if self._filter_scan_complete:
                    extra = (
                        f"；{pages_without_ocr} 页无 OCR 缓存"
                        if include_mismatch and pages_without_ocr else ""
                    )
                    self.parent.status_var.set(
                        f"筛选完成：{len(indices)} 页共 {len(self.filtered_targets)} 条{extra}"
                    )
                else:
                    self.parent.status_var.set(
                        f"首批已就绪：已扫描 {next_position}/{len(indices)} 页，"
                        f"当前命中 {len(self.filtered_targets)} 条；后台准备下一批…"
                    )
                self._request_filter_batch_render()
            elif self._filter_scan_complete:
                self._request_filter_batch_render()
            else:
                self._clear_review_workspace("首段暂无命中，正在继续筛选…")

            if not self._filter_scan_complete:
                start_remaining_scan(
                    next_position, pages_without_ocr, len(self.filtered_targets)
                )

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            if serial != self._filter_scan_serial:
                return
            self._filter_scan_complete = True
            self.filter_batch_var.set("筛选失败")
            self._clear_review_workspace(f"筛选失败：{exc}")
            messagebox.showerror("重点筛选失败", str(exc), parent=self)

        self.parent._start_ui_worker(
            f"focused-filter-scan-{id(self)}", first_worker, first_done, failed
        )

    def _focused_batch_size(self) -> int:
        try:
            return max(1, min(500, int(self.focused_batch_size_var.get().strip())))
        except ValueError:
            return 40

    def _filter_available_target_count(self) -> int:
        """Expose only complete batches while the background scan is unfinished."""
        total = len(self.filtered_targets)
        if self._filter_scan_complete:
            return total
        batch_size = self._focused_batch_size()
        return (total // batch_size) * batch_size

    def _update_filter_batch_indicator(self) -> None:
        available_total = self._filter_available_target_count()
        if available_total <= 0:
            self.filter_batch_var.set(
                "0 / 0" if self._filter_scan_complete else "正在准备下一批…"
            )
            return
        batch_size = self._focused_batch_size()
        batch_count = max(1, (available_total + batch_size - 1) // batch_size)
        batch_index = max(0, min(batch_count - 1, int(self.filtered_batch_index)))
        start = batch_index * batch_size
        end = min(available_total, start + batch_size)
        total_text = str(available_total) if self._filter_scan_complete else f"{available_total}+"
        self.filter_batch_var.set(
            f"第 {batch_index + 1}/{batch_count} 批 · "
            f"{start + 1}-{end} / {total_text}"
        )

    def _filter_batch_snapshot(self, batch_index: int):
        """Capture all Tk-derived values before a filter-batch worker starts."""
        project = self.parent.project
        if project is None:
            return None
        available_total = self._filter_available_target_count()
        batch_size = self._focused_batch_size()
        start = int(batch_index) * batch_size
        if start < 0 or start >= available_total:
            return None
        end = min(available_total, start + batch_size)
        targets = [dict(target) for target in self.filtered_targets[start:end]]
        pages = list(project.images)
        settings = replace(self.parent.settings)
        viewer_width = max(1, int(self.parent.canvas.winfo_width()))
        available_width = max(240, self._review_image_area_width())
        review_zoom_auto = bool(self.review_zoom_auto)
        review_zoom = max(0.01, float(self.review_zoom))
        target_signature = tuple(
            (
                int(target["page_index"]),
                int(target["x"]),
                int(target["y"]),
                str(target.get("original_word") or ""),
            )
            for target in targets
        )
        render_signature = (
            target_signature,
            repr(settings),
            viewer_width,
            available_width,
            review_zoom_auto,
            None if review_zoom_auto else round(review_zoom, 6),
        )
        cache_key = (int(batch_index), render_signature)
        return (
            cache_key, targets, pages, settings, viewer_width, available_width,
            review_zoom, review_zoom_auto,
        )

    @staticmethod
    def _prepare_filter_batch_payload(
        targets: list[dict], pages: list[Path], settings: AppSettings,
        viewer_width: int, available_width: int, review_zoom: float,
        review_zoom_auto: bool,
    ) -> tuple[list[Image.Image], float, list[tuple[int, int]]]:
        """Build filter crops off Tk so a prefetched batch can display immediately."""
        raw_crops: list[Image.Image] = []
        display_meta: list[tuple[int, int]] = []
        page_cache: dict[int, tuple[Image.Image, object, list[WordEntry]]] = {}
        for target in targets:
            page_index = int(target["page_index"])
            if page_index not in page_cache:
                page = pages[page_index]
                with Image.open(page) as opened:
                    image = normalize_page_rgb(opened)
                review_settings, geometry = _review_crop_context(
                    image, settings, viewer_width, page_index,
                )
                ordered = sort_entries_reading_order(
                    read_pdic(pdic_path(page)), geometry, read_page_sections(page)
                )
                page_cache[page_index] = (image, (review_settings, geometry), ordered)
            image, context, ordered = page_cache[page_index]
            review_settings, geometry = context
            matches = [
                i for i, entry in enumerate(ordered)
                if int(entry.x) == int(target["x"])
                and int(entry.y) == int(target["y"])
            ]
            if len(matches) > 1:
                preferred = [
                    i for i in matches
                    if str(ordered[i].word) == str(target.get("original_word") or "")
                ]
                matches = preferred or matches
            if len(matches) != 1:
                raw_crops.append(
                    Image.new("RGB", (max(40, available_width // 2), 36), "white")
                )
                display_meta.append((
                    int(target.get("column_number", 1) or 1),
                    int(target.get("sequence_number", 0) or 0),
                ))
                continue
            row = matches[0]
            entry = ordered[row]
            try:
                column_number = column_index(
                    int(entry.x), geometry, int(entry.y)
                ) + 1
            except Exception:
                column_number = 1
            display_meta.append((int(column_number), int(row + 1)))
            next_entry = ordered[row + 1] if row + 1 < len(ordered) else None
            box = _review_line_box(
                entry, geometry, image, review_settings, next_entry
            )
            raw_crops.append(image.crop(box).convert("RGB"))

        effective_zoom = max(0.01, float(review_zoom))
        if review_zoom_auto and raw_crops:
            widest = max(crop.width for crop in raw_crops)
            effective_zoom = review_auto_fit_zoom(
                widest, available_width, 0.99
            )
        crops = [
            crop.resize(
                (
                    max(1, round(crop.width * effective_zoom)),
                    max(1, round(crop.height * effective_zoom)),
                ),
                Image.Resampling.LANCZOS,
            )
            for crop in raw_crops
        ]
        return crops, effective_zoom, display_meta

    def _cache_filter_batch_payload(self, cache_key: tuple[int, tuple], payload: tuple) -> None:
        self._filter_batch_render_cache.pop(cache_key, None)
        self._filter_batch_render_cache[cache_key] = payload
        while len(self._filter_batch_render_cache) > 4:
            oldest = next(iter(self._filter_batch_render_cache))
            self._filter_batch_render_cache.pop(oldest, None)

    def _apply_filter_batch_payload(
        self, batch_index: int, cache_key: tuple[int, tuple], payload: tuple,
    ) -> bool:
        if (
            not getattr(self, "_filter_rows_active", False)
            or int(self.filtered_batch_index) != int(batch_index)
        ):
            return False
        snapshot = self._filter_batch_snapshot(batch_index)
        if snapshot is None or snapshot[0] != cache_key:
            return False
        _key, _targets_copy, _pages, _settings, _viewer_width, _available_width, _zoom, _auto = snapshot
        batch_size = self._focused_batch_size()
        start = int(batch_index) * batch_size
        end = min(self._filter_available_target_count(), start + batch_size)
        targets = self.filtered_targets[start:end]

        crops, effective_zoom, display_meta = payload
        if len(crops) != len(targets) or len(display_meta) != len(targets):
            return False
        for target, (column_number, sequence_number) in zip(targets, display_meta):
            target["column_number"] = int(column_number)
            target["sequence_number"] = int(sequence_number)
        if self.review_zoom_auto:
            self.review_zoom = max(0.01, float(effective_zoom))
            self.review_zoom_var.set(f"自动 {_format_layout_percent(self.review_zoom * 100.0)}%")
        self._update_filter_batch_indicator()
        self._render_filter_batch(targets, crops)
        self._reset_rows_scroll_top()
        self._schedule_filter_next_batch_preload()
        return True

    def _schedule_filter_next_batch_preload(self) -> None:
        """Prepare N+1 while the user proofreads N."""
        if not getattr(self, "_filter_rows_active", False):
            return
        next_index = int(self.filtered_batch_index) + 1
        snapshot = self._filter_batch_snapshot(next_index)
        if snapshot is None:
            return
        (
            cache_key, targets, pages, settings, viewer_width, available_width,
            review_zoom, review_zoom_auto,
        ) = snapshot
        if cache_key in self._filter_batch_render_cache:
            return
        if self._filter_prefetch_key == cache_key:
            return
        self._filter_prefetch_key = cache_key
        worker_key = f"focused-filter-prefetch-{id(self)}"

        def worker(
            local_targets=targets, local_pages=pages, local_settings=settings,
            local_viewer_width=viewer_width, local_available_width=available_width,
            local_review_zoom=review_zoom, local_review_zoom_auto=review_zoom_auto,
        ):
            return ReviewWindow._prepare_filter_batch_payload(
                local_targets, local_pages, local_settings,
                local_viewer_width, local_available_width,
                local_review_zoom, local_review_zoom_auto,
            )

        def done(payload, local_key=cache_key, local_index=next_index) -> None:
            if self._filter_prefetch_key == local_key:
                self._filter_prefetch_key = None
            if not getattr(self, "_filter_rows_active", False):
                return
            self._cache_filter_batch_payload(local_key, payload)
            # If the user clicked 【下一批】 while this worker was still running,
            # complete that navigation immediately from the freshly built cache.
            if int(self.filtered_batch_index) == int(local_index):
                self._apply_filter_batch_payload(local_index, local_key, payload)

        def failed(exc, detail, local_key=cache_key) -> None:
            if detail:
                print(detail)
            if self._filter_prefetch_key == local_key:
                self._filter_prefetch_key = None

        self.parent._start_ui_worker(
            worker_key, worker, done, failed,
        )

    def change_filter_batch(self, delta: int) -> None:
        if not self._filter_rows_active or not self.filtered_targets:
            return
        available_total = self._filter_available_target_count()
        if available_total <= 0:
            return
        batch_size = self._focused_batch_size()
        batch_count = max(1, (available_total + batch_size - 1) // batch_size)
        requested = self.filtered_batch_index + int(delta)
        target = max(0, min(batch_count - 1, requested))
        if target == self.filtered_batch_index:
            if int(delta) > 0 and not self._filter_scan_complete:
                self.parent.status_var.set("下一批仍在后台筛选与预生成，请继续校对当前批次。")
                self._schedule_filter_next_batch_preload()
            return
        self._flush_focused_changes_now()
        self.filtered_batch_index = target
        self._request_filter_batch_render()

    def _request_filter_batch_render(self) -> None:
        if not getattr(self, "_filter_rows_active", False):
            return
        available_total = self._filter_available_target_count()
        if available_total <= 0:
            if self._filter_scan_complete:
                self.filter_batch_var.set("0 / 0")
                self._clear_review_workspace("当前条件没有筛选出词条。")
            else:
                self.filter_batch_var.set("正在准备下一批…")
                self._clear_review_workspace("正在后台筛选下一批…")
            return

        batch_size = self._focused_batch_size()
        batch_count = max(1, (available_total + batch_size - 1) // batch_size)
        self.filtered_batch_index = max(
            0, min(batch_count - 1, int(self.filtered_batch_index))
        )
        self._update_filter_batch_indicator()
        self._set_filter_navigation(True)
        snapshot = self._filter_batch_snapshot(self.filtered_batch_index)
        if snapshot is None:
            return
        (
            cache_key, targets, pages, settings, viewer_width, available_width,
            review_zoom, review_zoom_auto,
        ) = snapshot

        self._filter_render_serial += 1
        serial = self._filter_render_serial
        cached = self._filter_batch_render_cache.get(cache_key)
        if cached is not None:
            self._apply_filter_batch_payload(
                self.filtered_batch_index, cache_key, cached
            )
            return

        if self._filter_prefetch_key == cache_key:
            self._clear_review_workspace("下一批已在后台预生成，即将显示…")
            return

        self._clear_review_workspace("正在异步生成本批切词行…")

        def worker(
            local_targets=targets, local_pages=pages, local_settings=settings,
            local_viewer_width=viewer_width, local_available_width=available_width,
            local_review_zoom=review_zoom, local_review_zoom_auto=review_zoom_auto,
        ):
            return ReviewWindow._prepare_filter_batch_payload(
                local_targets, local_pages, local_settings,
                local_viewer_width, local_available_width,
                local_review_zoom, local_review_zoom_auto,
            )

        def done(payload, local_index=int(self.filtered_batch_index), local_key=cache_key) -> None:
            if (
                serial != self._filter_render_serial
                or not getattr(self, "_filter_rows_active", False)
            ):
                return
            self._cache_filter_batch_payload(local_key, payload)
            self._apply_filter_batch_payload(local_index, local_key, payload)

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            if serial != self._filter_render_serial:
                return
            self._clear_review_workspace(f"本批切词行生成失败：{exc}")

        self.parent._start_ui_worker(
            f"focused-filter-render-{id(self)}", worker, done, failed
        )

    def _render_filter_batch(
        self, targets: list[dict], crops: list[Image.Image],
    ) -> None:
        for child in self.rows.winfo_children():
            child.destroy()
        self.filter_vars = []
        self.filter_editors = []
        self.filter_thumbnails = []
        self._filter_current_batch_targets = list(targets)
        if not targets:
            self._clear_review_workspace("当前批次为空。")
            return

        family = resolve_content_font_family(
            self, self.parent.settings.review_entry_font_family,
            self.parent.settings.ocr_language,
        )
        font_size = _review_editor_font_size(self.parent.settings)
        font_spec = _entry_font_spec(
            family, font_size,
            self.parent.settings.review_entry_font_bold,
            self.parent.settings.review_entry_font_italic,
        )
        reference_words = set(self.parent._project_words)
        for index, target in enumerate(targets):
            row = ttk.Frame(
                self.rows, padding=(6, 4), style="PCR.Surface.TFrame"
            )
            row.grid(row=index, column=0, sticky="ew", padx=4, pady=(2, 5))
            row.columnconfigure(0, weight=1)

            header = ttk.Frame(row, style="PCR.Surface.TFrame")
            header.grid(row=0, column=0, sticky="ew")
            reason = "；".join(str(value) for value in target.get("reasons", ())) or "—"
            ttk.Label(
                header,
                text=(
                    f"{target['page_name']} | 第{int(target.get('column_number', 1))}栏 | "
                    f"序号 {int(target.get('sequence_number', index + 1))} | 原因：{reason}"
                ),
                style="PCR.Header.TLabel",
            ).pack(side="left")

            crop = crops[index] if index < len(crops) else Image.new("RGB", (320, 36), "white")
            photo = ImageTk.PhotoImage(
                themed_display_image(crop, self.parent.appearance_mode)
            )
            self.filter_thumbnails.append(photo)
            ttk.Label(
                row, image=photo, style="PCR.Crop.TLabel",
            ).grid(row=1, column=0, sticky="ew", pady=(4, 2))

            value = str(target.get("current_word", target.get("original_word", "")))
            variable = tk.StringVar(value=value)
            self.filter_vars.append(variable)
            editor_bg, editor_fg, selection_bg, selection_fg = (
                self._review_membership_colors(value in reference_words)
            )
            editor_row = ttk.Frame(row, style="PCR.Surface.TFrame")
            editor_row.grid(row=2, column=0, sticky="ew")
            editor = tk.Entry(
                editor_row, textvariable=variable, font=font_spec,
                bg=editor_bg, foreground=editor_fg, insertbackground=editor_fg,
                selectbackground=selection_bg, selectforeground=selection_fg,
                relief="flat", bd=0, highlightthickness=1,
                highlightbackground=editor_bg, highlightcolor=editor_bg,
            )
            editor._pc_skip_classic_appearance = True
            editor.pack(
                side="left", fill="x", expand=True,
                ipady=max(0, int(self.parent.settings.review_entry_vertical_padding)),
            )
            ttk.Button(
                editor_row, text="填充OCR结果",
                command=lambda i=index: self._fill_filter_ocr_result(i),
                style="PCR.Compact.TButton",
            ).pack(side="right", padx=(5, 0))
            self.filter_editors.append(editor)
            editor.bind("<FocusIn>", lambda _event, i=index: self._set_filter_active(i))
            editor.bind("<KeyRelease>", lambda event, i=index: self._on_filter_key(event, i))
            editor.bind("<Return>", lambda _event, i=index: self._focus_filter_index(i + 1))
            editor.bind("<Up>", lambda _event, i=index: self._focus_filter_index(i - 1))
            editor.bind("<Down>", lambda _event, i=index: self._focus_filter_index(i + 1))
            editor.bind("<MouseWheel>", self.scroll_rows)
            editor.bind("<Button-4>", lambda e: self.scroll_rows_linux(-1))
            editor.bind("<Button-5>", lambda e: self.scroll_rows_linux(1))
        self.rows.columnconfigure(0, weight=1)
        self.filter_active_local_index = 0
        if self.filter_editors:
            self.filter_editors[0].focus_set()

    def _set_filter_active(self, index: int) -> None:
        if 0 <= int(index) < len(getattr(self, "filter_editors", [])):
            self.filter_active_local_index = int(index)

    def _focus_filter_index(self, index: int) -> str:
        editors = getattr(self, "filter_editors", [])
        if editors:
            target = max(0, min(len(editors) - 1, int(index)))
            self.filter_active_local_index = target
            editors[target].focus_set()
            editors[target].icursor("end")
            try:
                self.canvas.yview_moveto(
                    max(0.0, min(1.0, target / max(1, len(editors) - 1)))
                )
            except tk.TclError:
                pass
        return "break"

    def _filter_ocr_word(self, target: dict) -> str:
        key = self.OCR_COMPARE_LABEL_TO_KEY.get(
            self.review_ocr_compare_var.get(), "fusion"
        )
        words = target.get("ocr_words") or {}
        if not isinstance(words, dict):
            return ""
        return str(words.get(key) or "").strip()

    def _fill_filter_ocr_result(self, index: int) -> None:
        if not (0 <= index < len(getattr(self, "filter_vars", []))):
            return
        target = self._filter_current_batch_targets[index]
        ocr_word = self._filter_ocr_word(target)
        if not ocr_word:
            source = self.review_ocr_compare_var.get()
            self.parent.status_var.set(f"当前词条没有 {source} 结果可填充")
            return
        self.filter_vars[index].set(ocr_word)
        self.filter_editors[index].focus_set()
        self.filter_editors[index].icursor("end")
        self._commit_filter_editor_value(index)

    def _commit_filter_editor_value(self, index: int) -> None:
        if not (0 <= index < len(getattr(self, "filter_vars", []))):
            return
        target = self._filter_current_batch_targets[index]
        editor = self.filter_editors[index]
        value = self.filter_vars[index].get().strip()
        target["current_word"] = value
        in_reference = value in set(self.parent._project_words)
        color = "#b3fddd" if in_reference else "#fce5e8"
        try:
            editor.configure(
                bg=color, foreground="#111827", insertbackground="#111827",
                highlightbackground=color, highlightcolor=color,
            )
        except tk.TclError:
            pass
        self._queue_focused_change(target, value)

    def _on_filter_key(self, event: tk.Event, index: int) -> None:
        if not (0 <= index < len(getattr(self, "filter_vars", []))):
            return
        self._set_filter_active(index)
        char = getattr(event, "char", "")
        editor = self.filter_editors[index]
        if self.replace_digits.get() and char in self.DIGIT_KEYS:
            replacement = self.digit_map_vars[self.DIGIT_KEYS.index(char)].get()
            if replacement:
                pos = editor.index("insert")
                text = editor.get()
                start = max(0, pos - 1)
                editor.delete(0, "end")
                editor.insert(0, text[:start] + replacement + text[pos:])
                editor.icursor(start + len(replacement))
        self._commit_filter_editor_value(index)

    def _queue_focused_change(self, target: dict, value: str) -> None:
        page_index = int(target["page_index"])
        key = (int(target["x"]), int(target["y"]))
        original = str(target.get("original_word") or "")
        clean = (
            str(value or "").replace("\r", " ").replace("\n", " ")
            .replace("#", "＃").strip()
        )
        target["current_word"] = clean
        if clean == original:
            page_changes = self._filter_pending_changes.get(page_index)
            if page_changes is not None:
                page_changes.pop(key, None)
                if not page_changes:
                    self._filter_pending_changes.pop(page_index, None)
        else:
            self._filter_pending_changes.setdefault(page_index, {})[key] = {
                "page_index": page_index,
                "x": key[0], "y": key[1],
                "original_word": original,
                "new_word": clean,
            }
        if self._filter_save_job is not None:
            try:
                self.after_cancel(self._filter_save_job)
            except tk.TclError:
                pass
        self._filter_save_job = self.after(160, self._flush_focused_changes)

    def _flush_focused_changes_now(self) -> None:
        if self._filter_save_job is not None:
            try:
                self.after_cancel(self._filter_save_job)
            except tk.TclError:
                pass
            self._filter_save_job = None
        self._flush_focused_changes()

    def _flush_focused_changes(self) -> None:
        self._filter_save_job = None
        if self._filter_save_running or not self._filter_pending_changes:
            return
        project = self.parent.project
        if project is None:
            return
        snapshot = {
            page_index: list(changes.values())
            for page_index, changes in self._filter_pending_changes.items()
            if changes
        }
        if not snapshot:
            return
        self._filter_pending_changes.clear()
        self._filter_save_running = True
        pages = list(project.images)

        def worker():
            saved: list[tuple[int, int, int, str]] = []
            conflicts: list[str] = []
            for page_index, changes in sorted(snapshot.items()):
                page_saved, page_conflicts = _apply_focused_review_page_updates(
                    pages[page_index], pages, page_index, changes
                )
                saved.extend(page_saved)
                conflicts.extend(page_conflicts)
            return saved, conflicts

        def done(payload) -> None:
            self._filter_save_running = False
            saved, conflicts = payload
            saved_map = {
                (int(page_index), int(x), int(y)): str(word)
                for page_index, x, y, word in saved
            }
            for target in self.filtered_targets:
                key = (
                    int(target["page_index"]), int(target["x"]), int(target["y"])
                )
                if key in saved_map:
                    target["original_word"] = saved_map[key]
            # Pending edits made while this worker was running must use the new
            # on-disk word as their ambiguity guard on the next serialized write.
            for page_index, changes in self._filter_pending_changes.items():
                for key, change in changes.items():
                    saved_word = saved_map.get((int(page_index), int(key[0]), int(key[1])))
                    if saved_word is not None:
                        change["original_word"] = saved_word

            current_index = int(self.parent.current_index)
            current_saved = {
                (x, y): word
                for page_index, x, y, word in saved
                if int(page_index) == current_index
            }
            if current_saved:
                for entry in self.parent.entries:
                    value = current_saved.get((int(entry.x), int(entry.y)))
                    if value is not None:
                        entry.word = value
                        entry.confidence = None
                        entry.ocr_source = "manual"
                        entry.final_engine = "manual"
                        entry.manually_selected = True

            if conflicts:
                messagebox.showwarning(
                    "部分筛选词条未保存",
                    "以下词条的 PDIC 坐标已变化或存在歧义，因此未写入：\n\n"
                    + "\n".join(conflicts[:20])
                    + ("\n…" if len(conflicts) > 20 else ""),
                    parent=self,
                )
            self.parent.status_var.set(
                f"筛选校对已保存 {len(saved)} 条修改"
                + (f"；{len(conflicts)} 条冲突" if conflicts else "")
            )
            if self._filter_pending_changes:
                self._filter_save_job = self.after(1, self._flush_focused_changes)
            elif self._filter_close_after_save:
                self._filter_close_after_save = False
                self._finish_close_review()

        def failed(exc, detail) -> None:
            self._filter_save_running = False
            # Put the snapshot back so a later explicit save can retry.
            for page_index, changes in snapshot.items():
                target = self._filter_pending_changes.setdefault(page_index, {})
                for change in changes:
                    target[(int(change["x"]), int(change["y"]))] = change
            if detail:
                print(detail)
            self.parent.status_var.set(f"筛选校对保存失败：{exc}")
            messagebox.showerror("筛选校对保存失败", str(exc), parent=self)

        self.parent._start_ui_worker(
            f"focused-filter-save-{id(self)}",
            worker, done, failed, wait_on_close=True,
        )

    def copy_char(self, char: str) -> str:
        try:
            self.clipboard_clear()
            self.clipboard_append(str(char))
            self.update_idletasks()
            self.parent.status_var.set(f"已复制变音字符：{char}")
        except tk.TclError:
            pass
        return "break"

    def _review_membership_colors(
        self, in_wordslist: bool,
    ) -> tuple[str, str, str, str]:
        palette = appearance_palette(self.parent.appearance_mode)
        background = palette["review_present_bg"] if in_wordslist else palette["review_absent_bg"]
        return (
            background,
            palette["review_membership_fg"],
            palette["review_membership_select_bg"],
            palette["review_membership_select_fg"],
        )

    def _configure_word_list_appearance(self) -> None:
        palette = appearance_palette(self.parent.appearance_mode)
        dark = self.parent.appearance_mode == "dark"
        selection_bg = "#d9d9d9" if dark else "#dce8f7"
        try:
            self.word_list.configure(
                background=palette["input_bg"],
                foreground=palette["input_fg"],
                selectbackground=selection_bg,
                selectforeground="#111827",
                highlightbackground=palette["border"],
                highlightcolor=palette["border"],
            )
            self.word_list.tag_configure("wordslist_number", foreground=palette["muted"])
            self.word_list.tag_configure(
                "wordslist_target", background="#d9d9d9", foreground="#111827"
            )
        except tk.TclError:
            return
        self.word_list_default_bg = palette["input_bg"]
        self.word_list_default_fg = palette["input_fg"]

    def _clear_word_list_rows(self) -> None:
        self.word_selected_local_index = None
        try:
            self.word_list.configure(state="normal")
            self.word_list.delete("1.0", "end")
            self.word_list.configure(state="disabled")
        except tk.TclError:
            return

    def _render_word_list_rows(self, words: list[str]) -> None:
        self.word_selected_local_index = None
        try:
            self.word_list.configure(state="normal")
            self.word_list.delete("1.0", "end")
            digits = max(1, len(str(len(words))))
            for offset, global_index in enumerate(self.word_window_indices):
                self.word_list.insert(
                    "end", f"{global_index + 1:>{digits}}", ("wordslist_number",)
                )
                self.word_list.insert(
                    "end", f"  {words[global_index]}", ("wordslist_word",)
                )
                if offset + 1 < len(self.word_window_indices):
                    self.word_list.insert("end", "\n")
            self.word_list.configure(state="disabled")
        except tk.TclError:
            return

    def _set_word_list_highlight(self, local: int | None) -> None:
        try:
            self.word_list.tag_remove("wordslist_target", "1.0", "end")
            if local is None or not (0 <= int(local) < len(self.word_window_indices)):
                return
            line = int(local) + 1
            self.word_list.tag_add(
                "wordslist_target", f"{line}.0", f"{line}.end"
            )
            self.word_list.tag_raise("wordslist_target")
            self.word_list.see(f"{line}.0")
        except tk.TclError:
            return

    def _word_list_local_index_from_event(self, event: tk.Event) -> int | None:
        try:
            line = int(str(self.word_list.index(f"@{event.x},{event.y}")).split(".", 1)[0])
        except (tk.TclError, ValueError):
            return None
        local = line - 1
        if not (0 <= local < len(self.word_window_indices)):
            return None
        return local


    def _toggle_review_panel(self, panel: str) -> None:
        if panel == "digit":
            expanded = not self.digit_map_expanded.get()
            self.digit_map_expanded.set(expanded)
            self.digit_panel_title.set(("▾ " if expanded else "▸ ") + "数字替换映射")
            if expanded:
                self.digit_panel_body.pack(fill="x")
            else:
                self.digit_panel_body.pack_forget()
            return
        expanded = not self.accent_panel_expanded.get()
        self.accent_panel_expanded.set(expanded)
        self.accent_panel_title.set(("▾ " if expanded else "▸ ") + "变音字符")
        if expanded:
            self.accent_panel_body.pack(fill="x")
        else:
            self.accent_panel_body.pack_forget()

    def _sync_autosave_label(self) -> None:
        seconds = max(1.0, float(getattr(self.parent.settings, "batch_interval", 1.0)))
        value = f"{seconds:g}"
        self.autosave_label_var.set(f"自动：{value} s")

    def _toggle_shared_autosave(self) -> None:
        self._sync_autosave_label()
        self.parent.toggle_autosave()

    def open_sort_rules(self) -> None:
        # Reuse the same modeless Settings Center so the main image remains
        # available for reference while settings are edited.
        self.parent.open_settings(initial_tab="sort")

    def run_order_check(self) -> None:
        self.check_order(self.order_scope_var.get() == "all")

    def _update_title(self) -> None:
        page = self.parent.current_page.name if self.parent.current_page else ""
        if getattr(self, "_filter_rows_active", False):
            total = len(self.filtered_targets)
            self.title(f"词条校对 — 筛选模式 — 共 {total} 条")
            return
        total = len(self.editors)
        current = self.active_index + 1 if total else 0
        remaining = max(0, total - current)
        self.title(f"词条校对 — {page} — 当前: {current} 剩余: {remaining} 合计: {total}")

    def _finish_close_review(self) -> None:
        if self.parent.review_window is self:
            self.parent.review_window = None
        self._prefetch_closed = True
        self.parent._invalidate_ui_worker(self._review_render_worker_key)
        self.parent._invalidate_ui_worker(f"focused-filter-scan-{id(self)}")
        self.parent._invalidate_ui_worker(f"focused-filter-scan-rest-{id(self)}")
        self.parent._invalidate_ui_worker(f"focused-filter-render-{id(self)}")
        self.parent._invalidate_ui_worker(f"focused-filter-prefetch-{id(self)}")
        self._filter_batch_render_cache.clear()
        self._filter_prefetch_key = None
        if self._filter_save_job is not None:
            try:
                self.after_cancel(self._filter_save_job)
            except tk.TclError:
                pass
            self._filter_save_job = None
        if self._review_auto_zoom_job is not None:
            try:
                self.after_cancel(self._review_auto_zoom_job)
            except tk.TclError:
                pass
            self._review_auto_zoom_job = None
        self._network_lookup_serial += 1
        if self._network_lookup_job is not None:
            try:
                self.after_cancel(self._network_lookup_job)
            except tk.TclError:
                pass
            self._network_lookup_job = None
        if self._network_poll_job is not None:
            try:
                self.after_cancel(self._network_poll_job)
            except tk.TclError:
                pass
            self._network_poll_job = None
        self._network_pending_serials.clear()
        with self._prefetch_lock:
            self._prefetched_pages.clear()
        self.parent.clear_review_entry_highlight()
        self.destroy()
        self.parent.redraw()

    def _close_review(self) -> None:
        if getattr(self, "_filter_rows_active", False):
            self._flush_focused_changes_now()
            if self._filter_save_running or self._filter_pending_changes:
                self._filter_close_after_save = True
                self.parent.status_var.set("正在保存筛选校对修改，完成后关闭校对窗口。")
                return
            self._finish_close_review()
            return
        try:
            self.save()
        finally:
            self._finish_close_review()

    def autosave_commit(self) -> bool:
        """Commit review edits for the shared main-window autosave timer."""
        if getattr(self, "_filter_rows_active", False):
            self._flush_focused_changes_now()
            return True
        if not self.parent.project or not self.parent.current_page:
            return False
        state = self.parent._foreground_batch_state(self.parent.current_index)
        if state == "processing":
            return True
        row_entries = self._bound_row_entries()
        word_dirty = any(
            i < len(row_entries) and self.vars[i].get().strip() != row_entries[i].word
            for i in range(min(len(self.vars), len(row_entries)))
        )
        current_stem = self.parent.current_page.stem
        simplified_dirty = current_stem in self._simplified_dirty_pages
        dirty = word_dirty or simplified_dirty
        if state == "pending" and dirty and not self.parent._claim_page_for_manual_edit():
            return True
        if not dirty:
            return True
        self._commit_edits()
        self.parent.settings.review_zoom_percent = self._stored_review_zoom_percent()
        self.parent.save_pdic(silent=True, sync_editors=False)
        self._persist_simplified_page(current_stem)
        return True

    def _effective_wordslist_locator_mode(self) -> str:
        """Resolve the auxiliary-list locator without assuming page alignment.

        Chinese projects default to a sorted external-index workflow because a
        one-word-per-line index copied from another dictionary can contain many
        missing/extra entries. Latin projects keep the historical sequential
        behaviour unless the user explicitly selects the external-index mode.
        """
        settings = getattr(self.parent, "settings", None)
        mode = str(getattr(settings, "wordslist_locator_mode", "auto") or "auto").lower()
        if mode in {"sorted", "sequential"}:
            return mode
        if settings is not None and _is_cjk_review_index(settings):
            return "sorted"
        return "sequential"

    def _change_wordslist_locator_mode(self, _event: tk.Event | None = None) -> None:
        key = self.WORDSLIST_LOCATOR_LABEL_TO_KEY.get(self.wordslist_locator_var.get(), "auto")
        self.parent.settings.wordslist_locator_mode = key
        self.parent.save_settings()
        self._previous_reference_base_cache = None
        self.refresh_wordslist_display()

    def _refresh_cc_cedict_button_idle(self) -> None:
        try:
            state = cc_cedict_status()
        except Exception:
            state = None
        if state is not None and state.installed:
            self.cc_cedict_lookup_var.set("CC-CEDICT(?)")
            self.cc_simplified_compare_var.set("CC简(?)")
        else:
            self.cc_cedict_lookup_var.set("CC-CEDICT(未装)")
            self.cc_simplified_compare_var.set("CC简(未装)")

    def _set_lookup_source_states(self, *, pending: bool = False, empty: bool = False) -> None:
        """Reset the compact source badges shown in the review toolbar."""
        cjk = contains_cjk(self._network_lookup_word)
        try:
            cedict_installed = cc_cedict_status().installed
        except Exception:
            cedict_installed = False
        if empty:
            self.cc_cedict_lookup_var.set("CC-CEDICT(未装)" if not cedict_installed else "CC-CEDICT(?)")
            self.moedict_lookup_var.set("萌(?)")
            self.wiktionary_lookup_var.set("Wiki(?)")
            return
        if pending:
            if cjk:
                self.cc_cedict_lookup_var.set("CC-CEDICT(…)" if cedict_installed else "CC-CEDICT(未装)")
                self.moedict_lookup_var.set("萌(…)")
            else:
                self.cc_cedict_lookup_var.set("CC-CEDICT(—)")
                self.moedict_lookup_var.set("萌(—)")
            self.wiktionary_lookup_var.set("Wiki(…)")

    def manage_cc_cedict(self) -> None:
        """Install/update a user-downloaded CC-CEDICT archive.

        MDBG's website disallows scripted access, so Picture Capture never
        scrapes or silently downloads it. The user downloads the official
        archive in a browser, then selects that local file here.
        """
        try:
            state = cc_cedict_status()
        except Exception:
            state = None
        installed_text = ""
        if state is not None and state.installed:
            installed_text = f"\n\n当前已安装：{state.entry_count:,} 条\n{state.path}"
        choose_local = messagebox.askyesno(
            "CC-CEDICT 安装 / 更新",
            "是否已经从 CC-CEDICT 官方下载页取得数据文件？\n\n"
            "【是】选择本地 ZIP / GZ / TXT / U8 文件并安装\n"
            "【否】打开官方下载页" + installed_text,
            parent=self,
        )
        if not choose_local:
            try:
                webbrowser.open(CC_CEDICT_DOWNLOAD_PAGE_URL)
            except Exception as exc:
                messagebox.showerror("无法打开下载页", str(exc), parent=self)
            return
        source = filedialog.askopenfilename(
            parent=self,
            title="选择已下载的 CC-CEDICT 数据文件",
            filetypes=[
                ("CC-CEDICT 数据", "*.zip *.gz *.txt *.u8"),
                ("ZIP", "*.zip"),
                ("GZip", "*.gz"),
                ("文本", "*.txt *.u8"),
                ("所有文件", "*.*"),
            ],
        )
        if not source:
            return
        try:
            installed = install_cc_cedict_from_file(source)
        except Exception as exc:
            messagebox.showerror("CC-CEDICT 安装失败", str(exc), parent=self)
            return
        self._network_lookup_cache.clear()
        self.cc_cedict_lookup_var.set("CC-CEDICT(?)")
        self.cc_simplified_compare_var.set("CC简(?)")
        messagebox.showinfo(
            "CC-CEDICT 已安装",
            f"已安装 {installed.entry_count:,} 条。\n\n位置：\n{installed.path}\n\n"
            "该词典为所有 Picture Capture 项目共用，无需每个项目重复安装。",
            parent=self,
        )
        if self._active_review_word():
            self._refresh_cc_simplified_comparison(self.active_index)
            self._schedule_network_lookup(force=True)

    def _cc_simplified_comparison_details(self, index: int | None = None) -> dict[str, object]:
        """Compare OpenCC output with CC-CEDICT's Simplified field.

        CC-CEDICT is evidence, not an authoritative converter: a missing entry
        is reported as missing rather than treated as an OpenCC error.
        """
        i = self.active_index if index is None else int(index)
        if not (0 <= i < len(self.vars)):
            return {"state": "empty", "original": "", "opencc": "", "current": "", "candidates": tuple()}
        original = self.vars[i].get().strip()
        if not original or not contains_cjk(original):
            return {"state": "na", "original": original, "opencc": "", "current": "", "candidates": tuple()}
        mapping = cc_cedict_simplified_candidates(original)
        opencc_value = simplify_text(original)
        current_value = self._simplified_query_for_index(i) if i < len(self.simplified_vars) else (opencc_value or "")
        candidates = tuple(mapping.candidates)
        if mapping.found is None:
            state = "uninstalled" if "未安装" in (mapping.detail or "") else "unavailable"
        elif not candidates:
            state = "missing"
        elif opencc_value is None:
            state = "opencc_unavailable"
        elif opencc_value in candidates:
            state = "match"
        else:
            state = "mismatch"
        return {
            "state": state, "original": original, "opencc": opencc_value or "",
            "current": current_value or "", "candidates": candidates,
            "matched_as": mapping.matched_as, "detail": mapping.detail,
        }

    def _refresh_cc_simplified_comparison(self, index: int | None = None) -> None:
        try:
            info = self._cc_simplified_comparison_details(index)
        except Exception:
            self.cc_simplified_compare_var.set("CC简(?)")
            return
        state = str(info.get("state", ""))
        candidates = tuple(info.get("candidates", ()))
        if state == "match":
            text = "CC简(√)"
        elif state == "mismatch":
            if len(candidates) == 1:
                candidate = str(candidates[0])
                text = f"CC简:{candidate}"
                if len(text) > 14:
                    text = "CC简(1候选)"
            else:
                text = f"CC简({len(candidates)}候选)"
        elif state == "missing":
            text = "CC简(×)"
        elif state == "uninstalled":
            text = "CC简(未装)"
        elif state == "na":
            text = "CC简(—)"
        else:
            text = "CC简(?)"
        self.cc_simplified_compare_var.set(text)

    def show_cc_simplified_comparison(self) -> None:
        try:
            info = self._cc_simplified_comparison_details(self.active_index)
        except Exception as exc:
            messagebox.showerror("CC-CEDICT 简体比较", str(exc), parent=self)
            return
        state = str(info.get("state", ""))
        if state == "uninstalled":
            self.manage_cc_cedict()
            return
        original = str(info.get("original", ""))
        opencc_value = str(info.get("opencc", "")) or "（不可用）"
        current_value = str(info.get("current", "")) or "（空）"
        candidates = tuple(str(v) for v in info.get("candidates", ()))
        candidate_text = "、".join(candidates) if candidates else "（未找到繁→简映射）"
        if state == "match":
            verdict = "OpenCC 与 CC-CEDICT 的简体词形一致。"
        elif state == "mismatch":
            verdict = "OpenCC 与 CC-CEDICT 的简体词形不一致，建议人工复核。"
        elif state == "missing":
            verdict = "CC-CEDICT 未提供该词的繁→简映射；这不代表 OpenCC 转换错误。"
        elif state == "na":
            verdict = "当前词条不适用中文繁简比较。"
        else:
            verdict = "暂时无法完成 CC-CEDICT 与 OpenCC 比较。"
        current_note = ""
        if candidates and current_value not in {"（空）", "（不可用）"}:
            current_note = (
                "\n当前简体与 CC-CEDICT：" +
                ("一致" if current_value in candidates else "不一致")
            )
        messagebox.showinfo(
            "CC-CEDICT 简体比较",
            f"原词条：{original}\nOpenCC：{opencc_value}\n当前简体：{current_value}\n"
            f"CC-CEDICT 简体：{candidate_text}\n\n{verdict}{current_note}",
            parent=self,
        )

    def open_lookup_source(self, name: str) -> None:
        url = self._network_source_urls.get(name, "")
        if not url:
            if self._active_review_word():
                self._schedule_network_lookup(force=True)
            return
        try:
            webbrowser.open(url)
        except Exception as exc:
            messagebox.showerror("无法打开词典页面", str(exc), parent=self)

    def _toggle_network_lookup(self) -> None:
        enabled = bool(self.network_lookup_enabled_var.get())
        self.parent.settings.review_network_lookup_enabled = enabled
        self.parent.save_settings()
        if enabled:
            self._schedule_network_lookup(force=True)
        else:
            self._network_lookup_serial += 1
            if self._network_lookup_job is not None:
                try:
                    self.after_cancel(self._network_lookup_job)
                except tk.TclError:
                    pass
                self._network_lookup_job = None
            self.network_lookup_status_var.set("网络词汇核验：自动检查已关闭")
            try:
                self.network_status_label.configure(fg="#666666")
            except tk.TclError:
                pass
            self._set_lookup_source_states(empty=True)

    def _active_review_word(self) -> str:
        if 0 <= self.active_index < len(self.vars):
            return self.vars[self.active_index].get().strip()
        return ""

    def _schedule_network_lookup(self, word: str | None = None, *, force: bool = False) -> None:
        if not force and not bool(self.network_lookup_enabled_var.get()):
            return
        value = (self._active_review_word() if word is None else str(word)).strip()
        self._network_lookup_word = value
        self._network_lookup_serial += 1
        serial = self._network_lookup_serial
        if self._network_lookup_job is not None:
            try:
                self.after_cancel(self._network_lookup_job)
            except tk.TclError:
                pass
            self._network_lookup_job = None
        if not value:
            self.network_lookup_status_var.set("网络词汇核验：当前词条为空")
            try:
                self.network_status_label.configure(fg="#666666")
            except tk.TclError:
                pass
            self._network_source_urls.clear()
            self._set_lookup_source_states(empty=True)
            return
        cached = self._network_lookup_cache.get(value)
        if cached is not None:
            self._apply_network_lookup_result(serial, value, cached)
            return
        self.network_lookup_status_var.set(f"网络词汇核验：正在查询“{value}”…")
        self._network_source_urls.clear()
        self._set_lookup_source_states(pending=True)
        try:
            self.network_status_label.configure(fg="#555555")
        except tk.TclError:
            pass
        delay = 0 if force else 550
        self._network_lookup_job = self.after(delay, lambda: self._start_network_lookup(serial, value))

    def _start_network_lookup(self, serial: int, word: str) -> None:
        self._network_lookup_job = None
        if serial != self._network_lookup_serial or not word:
            return
        self._network_pending_serials.add(serial)
        if self._network_poll_job is None:
            self._network_poll_job = self.after(100, self._poll_network_lookup_results)

        def worker() -> None:
            try:
                result: LexicalLookupResult | None = lookup_word_free(word)
            except Exception:
                result = None
            self._network_result_queue.put((serial, word, result))

        threading.Thread(target=worker, name="picture-capture-network-lookup", daemon=True).start()

    def _poll_network_lookup_results(self) -> None:
        self._network_poll_job = None
        while True:
            try:
                serial, word, result = self._network_result_queue.get_nowait()
            except queue.Empty:
                break
            self._network_pending_serials.discard(serial)
            if result is not None:
                self._network_lookup_cache[word] = result
            if serial == self._network_lookup_serial and word == self._network_lookup_word:
                self._apply_network_lookup_result(serial, word, result)
        if self._network_pending_serials:
            self._network_poll_job = self.after(100, self._poll_network_lookup_results)

    def _apply_network_lookup_result(
        self, serial: int, word: str, result: LexicalLookupResult | None,
    ) -> None:
        if serial != self._network_lookup_serial or word != self._network_lookup_word:
            return
        if result is None:
            self.network_lookup_status_var.set(
                "⚠ 网络词汇核验暂时失败；可点“网络搜索”手工确认。"
            )
            try:
                self.network_status_label.configure(fg="#9a6700")
            except tk.TclError:
                pass
            self._set_lookup_source_states(empty=True)
            return

        self._network_source_urls = {item.name: item.url for item in result.sources if item.url}
        by_name = {item.name: item for item in result.sources}

        def marker(item_name: str) -> str:
            item = by_name.get(item_name)
            if item is None:
                return "—"
            if item.found is True:
                return "√"
            if item.found is False:
                return "×"
            if item_name == "CC-CEDICT" and "未安装" in (item.detail or ""):
                return "未装"
            return "?"

        if contains_cjk(word):
            self.cc_cedict_lookup_var.set(f"CC-CEDICT({marker('CC-CEDICT')})")
            self.moedict_lookup_var.set(f"萌({marker('萌典')})")
        else:
            self.cc_cedict_lookup_var.set("CC-CEDICT(—)")
            self.moedict_lookup_var.set("萌(—)")
        self.wiktionary_lookup_var.set(f"Wiki({marker('维基词典')})")

        found_names = [item.name for item in result.sources if item.found is True]
        if result.found is True:
            self.network_lookup_status_var.set(
                "✓ 有词典收录：" + "、".join(found_names)
            )
            status_color = "#1b7f3a"
        elif result.found is False:
            self.network_lookup_status_var.set(
                "○ 各可用词典均未检出精确词条（不代表该词不存在）"
            )
            status_color = "#8a5a00"
        else:
            self.network_lookup_status_var.set(
                "⚠ 部分词典未安装或网络来源暂不可用；可继续网络搜索。"
            )
            status_color = "#9a6700"
        try:
            self.network_status_label.configure(fg=status_color)
        except tk.TclError:
            pass

    def open_network_web_search(self) -> None:
        # Keep the manual browser search aligned with the most recent lookup.
        # This matters when a row-level “网查” button queried the editable
        # simplified companion rather than the original headword.
        word = (self._network_lookup_word or self._active_review_word()).strip()
        if not word:
            self.network_lookup_status_var.set("网络词汇核验：当前词条为空")
            return
        try:
            webbrowser.open(web_search_url(word))
        except Exception as exc:
            messagebox.showerror("无法打开网页搜索", str(exc), parent=self)

    @staticmethod
    def _wordslist_lookup_key(word: str) -> str:
        """Cheap lookup key for the auxiliary list, not for dictionary order validation.

        Full collation_key() intentionally supports custom alphabets and multi-letter
        collation units, but compiling that machinery 190k times is unnecessary for
        merely positioning the review helper near an OCR word. Exact spelling lookup
        is attempted first; this folded key is only the fallback.
        """
        text = unicodedata.normalize("NFKD", (word or "").casefold().strip())
        return "".join(ch for ch in text if not unicodedata.combining(ch) and ch.isalnum())

    def refresh_wordslist_display(self) -> None:
        reference_words = self.parent.project.words if self.parent.project else []
        self._clear_word_list_rows()
        self.word_highlight_index = None
        self.word_window_start = 0
        self.word_window_indices = []

        # Build the lookup structures once when the file changes.  This is O(n)
        # plus one sort, but unlike the old implementation it never creates
        # 190k Tk list items.  Exact lookup is the common path during review.
        self.word_keys = [self._wordslist_lookup_key(word) for word in reference_words]
        self.word_exact_index = {}
        self.word_exact_indices = {}
        for i, word in enumerate(reference_words):
            key = word.strip().casefold()
            self.word_exact_index.setdefault(key, i)
            self.word_exact_indices.setdefault(key, []).append(i)
        # Keep the historical lightweight folded index for Latin/sequential
        # fallback.  Do NOT precompute pinyin for a 100k–200k Chinese index:
        # sorted external-index lookup below performs a lazy O(log n) binary
        # search and caches only the handful of probed pinyin keys.
        if self.word_keys and all(self.word_keys[i - 1] <= self.word_keys[i] for i in range(1, len(self.word_keys))):
            self.sorted_word_keys = self.word_keys
            self.sorted_word_indices = list(range(len(self.word_keys)))
        else:
            lightweight_pairs = sorted((key, i) for i, key in enumerate(self.word_keys))
            self.sorted_word_keys = [key for key, _i in lightweight_pairs]
            self.sorted_word_indices = [i for _key, i in lightweight_pairs]
        self.word_sort_key_cache = {}

        if self.parent.project:
            path = resolve_wordslist_path(self.parent.project.root, self.parent.settings.wordslist_path)
            self.word_window_var.set(f"{path.name} | 0-0 / {len(reference_words)}")
        else:
            self.word_window_var.set("未选择 | 0-0 / 0")
        if reference_words:
            if self.vars and 0 <= self.active_index < len(self.vars):
                self.locate_reference_word(self.vars[self.active_index].get())
            else:
                self._show_wordslist_window(0)

    def _show_wordslist_window(self, target: int) -> None:
        """Render only a small window around one global wordslist index."""
        words = self.parent.project.words if self.parent.project else []
        if not words:
            self._clear_word_list_rows()
            self.word_window_indices = []
            self.word_window_start = 0
            self.word_highlight_index = None
            if hasattr(self, "word_window_var"):
                if self.parent.project:
                    path = resolve_wordslist_path(
                        self.parent.project.root, self.parent.settings.wordslist_path
                    )
                    self.word_window_var.set(f"{path.name} | 0-0 / 0")
                else:
                    self.word_window_var.set("未选择 | 0-0 / 0")
            return
        target = max(0, min(int(target), len(words) - 1))
        span = self.word_window_radius * 2 + 1
        start = max(0, target - self.word_window_radius)
        start = min(start, max(0, len(words) - span))
        end = min(len(words), start + span)
        self.word_window_start = start
        self.word_window_indices = list(range(start, end))
        if hasattr(self, "word_window_var"):
            path = resolve_wordslist_path(
                self.parent.project.root, self.parent.settings.wordslist_path
            )
            self.word_window_var.set(
                f"{path.name} | {start + 1}-{end} / {len(words)}"
            )
        self._render_word_list_rows(words)
        local = target - start
        self.word_highlight_index = local
        self._set_word_list_highlight(local)

    def shift_wordslist_window(self, direction: int) -> None:
        """Browse the large reference list by 100 rows without bulk rendering."""
        words = self.parent.project.words if self.parent.project else []
        if not words:
            return
        span = self.word_window_radius * 2 + 1
        step = 100
        start = max(
            0,
            min(
                self.word_window_start + int(direction) * step,
                max(0, len(words) - span),
            ),
        )
        target = min(
            len(words) - 1,
            start + min(self.word_window_radius, max(0, len(words) - 1 - start)),
        )
        self._show_wordslist_window(target)

    def choose_wordslist_file(self) -> None:
        if not self.parent.project:
            return
        current = resolve_wordslist_path(self.parent.project.root, self.parent.settings.wordslist_path)
        chosen = filedialog.askopenfilename(
            parent=self, title="选择 wordslist 参考词表",
            initialdir=str(current.parent if current.parent.exists() else self.parent.project.root),
            initialfile=current.name if current.name else "wordslist.txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not chosen:
            return
        self.word_window_var.set(f"{Path(chosen).name} | 正在读取…")

        def loaded(path: Path, count: int) -> None:
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return
            self.refresh_wordslist_display()
            words = self.parent._project_words
            for i, _editor in enumerate(self.editors):
                self._set_editor_membership_color(i, self.vars[i].get().strip() in words)
            self.parent.status_var.set(
                f"已选择 wordslist：{path}｜{count} 条；校对右侧参考词表已更新。"
            )

        def failed(exc: Exception) -> None:
            try:
                if self.winfo_exists():
                    self.refresh_wordslist_display()
                    messagebox.showerror("wordslist 读取失败", str(exc), parent=self)
            except tk.TclError:
                pass

        self.parent._request_wordslist_reload(
            Path(chosen), persist=True, redraw=True,
            on_done=loaded, on_error=failed,
        )

    def _commit_edits(self) -> None:
        from .review_main_editor_sync import commit_proofread_entries
        commit_proofread_entries(self)

    def _bound_row_entries(self) -> list[WordEntry]:
        """Return stable rendered-row bindings, with compatibility fallback."""
        bound = getattr(self, "row_entries", None)
        return list(bound) if bound is not None else self.parent._ordered_entries_reading_order()

    def _simplified_page_records(self, page_stem: str | None = None) -> dict[str, dict]:
        stem = str(page_stem or (self.parent.current_page.stem if self.parent.current_page else ""))
        if not stem:
            return {}
        if stem not in self._simplified_page_cache:
            page = None
            if self.parent.project:
                for candidate in self.parent.project.images:
                    if candidate.stem == stem:
                        page = candidate
                        break
            if page is None and self.parent.current_page and self.parent.current_page.stem == stem:
                page = self.parent.current_page
            records = read_simplified_records(simplified_review_path_for_image(page)) if page else {}
            self._simplified_page_cache[stem] = records
        return self._simplified_page_cache[stem]

    @staticmethod
    def _simplified_display_from_value(original: str, value: str | None, manual: bool) -> str:
        if value is None:
            return "OpenCC不可用"
        if not manual and value == original:
            return "√"
        return value

    def _auto_simplified_value(self, original: str, fallback: str | None = None) -> str | None:
        converted = simplify_text(original)
        if converted is None:
            return fallback
        return converted

    def _capture_simplified_edits(self, page_stem: str | None = None) -> None:
        stem = str(page_stem or "")
        if not stem or not getattr(self, "simplified_vars", []):
            return
        records = self._simplified_page_records(stem)
        # Preserve rendered row identities across section-order changes.
        rendered_entries = self._bound_row_entries()
        # Only capture against the currently rendered page.  During navigation
        # parent.current_page may already refer to the next page while the old
        # widgets are still being destroyed.
        if self.parent.current_page and self.parent.current_page.stem != stem:
            return
        for i, entry in enumerate(rendered_entries[:len(self.simplified_vars)]):
            key = simplified_entry_key(entry.x, entry.y)
            manual = bool(self.simplified_manual_flags[i]) if i < len(self.simplified_manual_flags) else False
            actual = self.simplified_actual_values[i] if i < len(self.simplified_actual_values) else None
            display = self.simplified_vars[i].get().strip()
            expected = self._simplified_display_from_value(entry.word, actual, False)
            if not manual and display != expected:
                manual = True
                if i < len(self.simplified_manual_flags):
                    self.simplified_manual_flags[i] = True
                self._simplified_dirty_pages.add(stem)
            if manual:
                actual = entry.word if display == "√" else display
                if i < len(self.simplified_actual_values):
                    self.simplified_actual_values[i] = actual
            records[key] = {
                "x": int(entry.x), "y": int(entry.y),
                "source_word": entry.word, "text": "" if actual is None else str(actual),
                "manual": manual,
            }

    def _persist_simplified_page(self, page_stem: str | None = None) -> None:
        stem = str(page_stem or (self.parent.current_page.stem if self.parent.current_page else ""))
        if not stem or not self.parent.project:
            return
        page = next((item for item in self.parent.project.images if item.stem == stem), None)
        if page is None:
            return
        records = self._simplified_page_records(stem)
        write_simplified_records(simplified_review_path_for_image(page), stem, records)
        self._simplified_dirty_pages.discard(stem)

    def _simplified_query_for_index(self, index: int) -> str:
        if not (0 <= index < len(self.vars)):
            return ""
        if index < len(self.simplified_actual_values):
            value = self.simplified_actual_values[index]
            if value is not None and str(value).strip():
                return str(value).strip()
        shown = self.simplified_vars[index].get().strip() if index < len(self.simplified_vars) else ""
        if shown == "√":
            return self.vars[index].get().strip()
        if shown and shown != "OpenCC不可用":
            return shown
        return ""

    def lookup_simplified_online(self, index: int) -> None:
        if not (0 <= index < len(self.vars)):
            return
        self.set_active(index)
        word = self._simplified_query_for_index(index)
        if not word:
            self.network_lookup_status_var.set("网络词汇核验：简化词条为空")
            return
        self._schedule_network_lookup(word, force=True)

    def _focus_simplified_editor(self, index: int) -> None:
        self.set_active(index)
        if not (0 <= index < len(self.simplified_editors)):
            return
        # Auto placeholders are scan-friendly but awkward to type over. Select
        # them on focus so the first keystroke replaces √/OpenCC提示 directly.
        if self.simplified_vars[index].get() in {"√", "OpenCC不可用"}:
            try:
                self.simplified_editors[index].selection_range(0, "end")
            except tk.TclError:
                pass


    def _claim_simplified_clipboard_edit(self, index: int) -> str | None:
        if not self.parent._claim_page_for_manual_edit():
            return "break"
        self.after_idle(lambda i=index: self.on_simplified_key(type("_Event", (), {})(), i))
        return None

    def on_simplified_key(self, _event: tk.Event, index: int) -> None:
        if not (0 <= index < len(self.simplified_vars)):
            return
        value = self.simplified_vars[index].get().strip()
        already_manual = bool(self.simplified_manual_flags[index]) if index < len(self.simplified_manual_flags) else False
        if not already_manual:
            original = self.vars[index].get().strip() if index < len(self.vars) else ""
            auto_refresh = (
                bool(self.simplified_auto_refresh_flags[index])
                if index < len(self.simplified_auto_refresh_flags) else True
            )
            if auto_refresh:
                expected_actual = self._auto_simplified_value(
                    original,
                    fallback=(self.simplified_actual_values[index] if index < len(self.simplified_actual_values) else None),
                )
            else:
                expected_actual = (
                    self.simplified_actual_values[index]
                    if index < len(self.simplified_actual_values) else None
                )
            expected = self._simplified_display_from_value(original, expected_actual, False)
            # Arrow/Home/End/etc. do not turn an untouched saved/OpenCC value
            # into a manual override merely because a KeyRelease event occurred.
            if value == expected:
                return
        if not self.parent._claim_page_for_manual_edit():
            return
        actual = self.vars[index].get().strip() if value == "√" else value
        if index < len(self.simplified_actual_values):
            self.simplified_actual_values[index] = actual
        if index < len(self.simplified_manual_flags):
            self.simplified_manual_flags[index] = True
        stem = self._rendered_page_stem
        if stem:
            ordered = self.parent._ordered_entries_reading_order()
            if index < len(ordered):
                entry = ordered[index]
                records = self._simplified_page_records(stem)
                records[simplified_entry_key(entry.x, entry.y)] = {
                    "x": int(entry.x), "y": int(entry.y),
                    "source_word": self.vars[index].get().strip(),
                    "text": actual, "manual": True,
                }
                self._simplified_dirty_pages.add(stem)
        if index == self.active_index:
            self._refresh_cc_simplified_comparison(index)

    def _schedule_review_font_apply(self) -> None:
        """Apply review-font edits quickly while coalescing rapid Spinbox typing."""
        if self._review_font_apply_job is not None:
            try:
                self.after_cancel(self._review_font_apply_job)
            except tk.TclError:
                pass
        self._review_font_apply_job = self.after(120, self._apply_review_font_settings)

    def _apply_review_font_settings(self) -> None:
        self._review_font_apply_job = None
        family = normalize_content_font_setting(self.review_font_family_var.get())
        try:
            size = int(float(self.review_font_size_var.get().strip()))
        except (TypeError, ValueError):
            return
        size = max(6, min(96, size))
        # Normalize the visible value after clamping, but avoid recursive work
        # unless the text actually differs.
        if self.review_font_size_var.get() != str(size):
            self.review_font_size_var.set(str(size))
            return
        bold = bool(self.review_font_bold_var.get())
        italic = bool(self.review_font_italic_var.get())
        settings = self.parent.settings
        settings.review_entry_font_family = family
        settings.review_entry_font_size = size
        settings.review_font_semantics_version = 2
        settings.review_entry_font_bold = bold
        settings.review_entry_font_italic = italic

        resolved_family = resolve_content_font_family(
            self, family, self.parent.settings.ocr_language,
        )
        spec = _entry_font_spec(resolved_family, size, bold, italic)
        measure_font = font.Font(
            family=resolved_family, size=size,
            weight="bold" if bold else "normal",
            slant="italic" if italic else "roman",
        )
        char_px = max(1, measure_font.measure("0"))
        for index, editor in enumerate(self.editors):
            width_px = self.editor_crop_widths[index] if index < len(self.editor_crop_widths) else 0
            width_chars = max(8, min(140, round(width_px / char_px))) if width_px else int(editor.cget("width"))
            try:
                editor.configure(font=spec, width=width_chars)
            except tk.TclError:
                pass
        self.parent.save_settings()

    def _schedule_review_simplified_font_apply(self) -> None:
        """Coalesce edits to the Simplified companion typography."""
        if self._review_simplified_font_apply_job is not None:
            try:
                self.after_cancel(self._review_simplified_font_apply_job)
            except tk.TclError:
                pass
        self._review_simplified_font_apply_job = self.after(120, self._apply_review_simplified_font_settings)

    def _apply_review_simplified_font_settings(self) -> None:
        self._review_simplified_font_apply_job = None
        family = normalize_content_font_setting(self.review_simplified_font_family_var.get())
        try:
            size = int(float(self.review_simplified_font_size_var.get().strip()))
        except (TypeError, ValueError):
            return
        size = max(6, min(96, size))
        if self.review_simplified_font_size_var.get() != str(size):
            self.review_simplified_font_size_var.set(str(size))
            return
        bold = bool(self.review_simplified_font_bold_var.get())
        italic = bool(self.review_simplified_font_italic_var.get())
        settings = self.parent.settings
        settings.review_simplified_font_family = family
        settings.review_simplified_font_size = size
        settings.review_simplified_font_bold = bold
        settings.review_simplified_font_italic = italic

        resolved_family = resolve_content_font_family(
            self, family, self.parent.settings.ocr_language,
        )
        spec = _entry_font_spec(resolved_family, size, bold, italic)
        measure_font = font.Font(
            family=resolved_family, size=size,
            weight="bold" if bold else "normal",
            slant="italic" if italic else "roman",
        )
        char_px = max(1, measure_font.measure("0"))
        for index, editor in enumerate(self.simplified_editors):
            width_px = self.editor_crop_widths[index] if index < len(self.editor_crop_widths) else 0
            width_chars = max(8, min(140, round(width_px / char_px))) if width_px else int(editor.cget("width"))
            try:
                editor.configure(font=spec, width=width_chars)
            except tk.TclError:
                pass
        self.parent.save_settings()

    def _schedule_review_padding_apply(self) -> None:
        if self._review_padding_apply_job is not None:
            try:
                self.after_cancel(self._review_padding_apply_job)
            except tk.TclError:
                pass
        self._review_padding_apply_job = self.after(120, self._apply_review_padding_setting)

    def _apply_review_padding_setting(self) -> None:
        self._review_padding_apply_job = None
        try:
            padding = int(float(self.review_left_padding_var.get().strip()))
        except (TypeError, ValueError):
            return
        padding = max(0, min(80, padding))
        if self.review_left_padding_var.get() != str(padding):
            self.review_left_padding_var.set(str(padding))
            return
        self.parent.settings.review_entry_left_padding = padding
        for editor in self.editors:
            try:
                editor.pack_configure(padx=(padding, 0))
            except tk.TclError:
                pass
        self.parent.save_settings()

    def _schedule_review_vertical_padding_apply(self) -> None:
        if self._review_vertical_padding_apply_job is not None:
            try:
                self.after_cancel(self._review_vertical_padding_apply_job)
            except tk.TclError:
                pass
        self._review_vertical_padding_apply_job = self.after(120, self._apply_review_vertical_padding_setting)

    def _apply_review_vertical_padding_setting(self) -> None:
        self._review_vertical_padding_apply_job = None
        try:
            padding = int(float(self.review_vertical_padding_var.get().strip()))
        except (TypeError, ValueError):
            return
        padding = max(0, min(30, padding))
        if self.review_vertical_padding_var.get() != str(padding):
            self.review_vertical_padding_var.set(str(padding))
            return
        self.parent.settings.review_entry_vertical_padding = padding
        for editor in self.editors:
            try:
                editor.pack_configure(ipady=padding)
            except tk.TclError:
                pass
        self.parent.save_settings()

    def _review_height_pixels_from_percent_var(
        self,
        variable: tk.StringVar,
        *,
        minimum: int,
        maximum: int,
    ) -> tuple[int, str]:
        raw = variable.get().strip().rstrip("%").strip()
        percent = float(raw)
        percent = max(0.0, min(100.0, percent))
        pixels = _review_height_percent_to_pixels(self.parent.image, percent)
        pixels = max(minimum, min(maximum, pixels))
        normalized = _format_review_height_percent(self.parent.image, pixels)
        return pixels, normalized

    @staticmethod
    def _review_height_pixels_from_pixel_var(
        variable: tk.StringVar,
        *,
        minimum: int,
        maximum: int,
    ) -> tuple[int, str]:
        pixels = int(round(float(variable.get().strip().rstrip("px").strip())))
        pixels = max(minimum, min(maximum, pixels))
        return pixels, str(pixels)

    def _sync_review_height_vars(self) -> None:
        """Refresh linked % + px controls without changing persisted pixel values."""
        self._syncing_review_height_vars = True
        try:
            values = (
                (
                    self.review_line_height_var,
                    self.review_line_height_px_var,
                    max(1, int(self.parent.settings.character_height)),
                ),
                (
                    self.review_row_padding_var,
                    self.review_row_padding_px_var,
                    max(0, int(self.parent.settings.row_padding)),
                ),
                (
                    self.review_regular_crop_height_var,
                    self.review_regular_crop_height_px_var,
                    _effective_review_regular_crop_height(self.parent.settings),
                ),
                (
                    self.review_single_cjk_line_height_var,
                    self.review_single_cjk_line_height_px_var,
                    _effective_review_single_cjk_line_height(self.parent.settings),
                ),
            )
            for percent_var, pixel_var, pixels in values:
                rendered_percent = _format_review_height_percent(self.parent.image, pixels)
                rendered_pixels = str(int(pixels))
                if percent_var.get() != rendered_percent:
                    percent_var.set(rendered_percent)
                if pixel_var.get() != rendered_pixels:
                    pixel_var.set(rendered_pixels)
            self._review_height_edit_source.clear()
        finally:
            self._syncing_review_height_vars = False

    def _schedule_review_line_height_apply(self, source: str = "percent") -> None:
        if self._syncing_review_height_vars:
            return
        self._review_height_edit_source["line_height"] = source
        if self._review_line_height_apply_job is not None:
            try:
                self.after_cancel(self._review_line_height_apply_job)
            except tk.TclError:
                pass
        self._review_line_height_apply_job = self.after(160, self._apply_review_line_height_setting)

    def _apply_review_line_height_setting(self) -> None:
        self._review_line_height_apply_job = None
        try:
            if self._review_height_edit_source.get("line_height") == "pixel":
                line_height, _normalized = self._review_height_pixels_from_pixel_var(
                    self.review_line_height_px_var, minimum=1, maximum=500
                )
            else:
                line_height, _normalized = self._review_height_pixels_from_percent_var(
                    self.review_line_height_var, minimum=1, maximum=500
                )
        except (TypeError, ValueError):
            return
        self.parent.settings.character_height = line_height
        self._sync_review_height_vars()
        self.parent.sync_quick_settings()
        self.parent.save_settings()
        self._commit_edits()
        active = self.active_index
        self._request_render_rows(focus_index=active)
        self.parent.redraw()

    def _schedule_review_row_padding_apply(self, source: str = "percent") -> None:
        if self._syncing_review_height_vars:
            return
        self._review_height_edit_source["row_padding"] = source
        if self._review_row_padding_apply_job is not None:
            try:
                self.after_cancel(self._review_row_padding_apply_job)
            except tk.TclError:
                pass
        self._review_row_padding_apply_job = self.after(160, self._apply_review_row_padding_setting)

    def _apply_review_row_padding_setting(self) -> None:
        self._review_row_padding_apply_job = None
        try:
            if self._review_height_edit_source.get("row_padding") == "pixel":
                padding, _normalized = self._review_height_pixels_from_pixel_var(
                    self.review_row_padding_px_var, minimum=0, maximum=200
                )
            else:
                padding, _normalized = self._review_height_pixels_from_percent_var(
                    self.review_row_padding_var, minimum=0, maximum=200
                )
        except (TypeError, ValueError):
            return
        self.parent.settings.row_padding = padding
        self._sync_review_height_vars()
        self.parent.sync_quick_settings()
        self.parent.save_settings()
        self._commit_edits()
        self._request_render_rows(focus_index=self.active_index)
        self.parent.redraw()

    def _schedule_review_regular_crop_height_apply(self, source: str = "percent") -> None:
        if self._syncing_review_height_vars:
            return
        self._review_height_edit_source["regular_crop_height"] = source
        if self._review_regular_crop_height_apply_job is not None:
            try:
                self.after_cancel(self._review_regular_crop_height_apply_job)
            except tk.TclError:
                pass
        self._review_regular_crop_height_apply_job = self.after(
            160, self._apply_review_regular_crop_height_setting
        )

    def _apply_review_regular_crop_height_setting(self) -> None:
        self._review_regular_crop_height_apply_job = None
        try:
            if self._review_height_edit_source.get("regular_crop_height") == "pixel":
                height, _normalized = self._review_height_pixels_from_pixel_var(
                    self.review_regular_crop_height_px_var, minimum=1, maximum=500
                )
            else:
                height, _normalized = self._review_height_pixels_from_percent_var(
                    self.review_regular_crop_height_var, minimum=1, maximum=500
                )
        except (TypeError, ValueError):
            return
        self.parent.settings.review_regular_crop_height = height
        self._sync_review_height_vars()
        self.parent.save_settings()
        self._commit_edits()
        self._request_render_rows(focus_index=self.active_index)

    def _schedule_review_single_cjk_height_apply(self, source: str = "percent") -> None:
        if self._syncing_review_height_vars:
            return
        self._review_height_edit_source["single_cjk_height"] = source
        if self._review_single_cjk_height_apply_job is not None:
            try:
                self.after_cancel(self._review_single_cjk_height_apply_job)
            except tk.TclError:
                pass
        self._review_single_cjk_height_apply_job = self.after(160, self._apply_review_single_cjk_height_setting)

    def _apply_review_single_cjk_height_setting(self) -> None:
        self._review_single_cjk_height_apply_job = None
        try:
            if self._review_height_edit_source.get("single_cjk_height") == "pixel":
                line_height, _normalized = self._review_height_pixels_from_pixel_var(
                    self.review_single_cjk_line_height_px_var, minimum=1, maximum=500
                )
            else:
                line_height, _normalized = self._review_height_pixels_from_percent_var(
                    self.review_single_cjk_line_height_var, minimum=1, maximum=500
                )
        except (TypeError, ValueError):
            return
        self.parent.settings.review_single_cjk_line_height = line_height
        self._sync_review_height_vars()
        self.parent.save_settings()
        self._commit_edits()
        active = self.active_index
        self._request_render_rows(focus_index=active)

    def _apply_review_main_ocr_display_options(self) -> None:
        self.parent.settings.review_main_show_ocr_choices = bool(self.review_main_ocr_choices_var.get())
        self.parent.settings.review_main_show_ocr_background = bool(self.review_main_ocr_background_var.get())
        self.parent.save_settings()
        self.parent.redraw()

    def change_review_zoom(self, factor: float) -> None:
        self._commit_edits()
        self.review_zoom_auto = False
        self.review_zoom = max(0.20, min(2.5, self.review_zoom * factor))
        self.parent.settings.review_zoom_percent = self._stored_review_zoom_percent()
        self.parent.save_settings()
        self.review_zoom_var.set(f"{_format_layout_percent(self.review_zoom * 100.0)}%")
        active = self.active_index
        self._request_render_rows(focus_index=active)

    def apply_review_zoom_text(self, _event=None) -> None:
        raw = self.review_zoom_var.get().strip()
        if not raw or raw.casefold().startswith(("自动", "auto")):
            if self.review_zoom_auto:
                return
            self.reset_review_zoom()
            return
        try:
            percent = float(raw.rstrip("%"))
        except ValueError:
            self.review_zoom_var.set(
                f"自动 {_format_layout_percent(self.review_zoom * 100.0)}%"
                if self.review_zoom_auto else f"{_format_layout_percent(self.review_zoom * 100.0)}%"
            )
            return
        self._commit_edits()
        self.review_zoom_auto = False
        self.review_zoom = min(2.5, max(0.20, percent / 100.0))
        self.parent.settings.review_zoom_percent = self._stored_review_zoom_percent()
        self.parent.save_settings()
        self.review_zoom_var.set(f"{_format_layout_percent(self.review_zoom * 100.0)}%")
        active = self.active_index
        self._request_render_rows(focus_index=active)

    def reset_review_zoom(self) -> None:
        self._commit_edits()
        self.review_zoom_auto = True
        self.parent.settings.review_zoom_percent = 0.0
        self.parent.save_settings()
        self.review_zoom_var.set("自动")
        self._review_auto_zoom_width = self._review_image_area_width()
        active = self.active_index
        self._request_render_rows(focus_index=active)

    def _exact_reference_position(self, word: str, near: int | None = None) -> int | None:
        key = (word or "").strip().casefold()
        if not key:
            return None
        positions = self.word_exact_indices.get(key, [])
        if not positions:
            return None
        if near is None:
            return positions[0]
        return min(positions, key=lambda value: abs(value - near))

    def _previous_page_reference_target(self, active_index: int) -> int | None:
        """Infer a current-page reference position from preceding PDIC tail anchors."""
        project = self.parent.project
        current_page_index = int(self.parent.current_index)
        if not project or current_page_index <= 0:
            return None
        cached = self._previous_reference_base_cache
        if cached is not None and cached[0] == current_page_index:
            return None if cached[1] is None else cached[1] + max(0, active_index)

        # Compute the expected reference index of the first entry on this page
        # once, then reuse it for consecutive empty/error entries.
        skipped_entries = 0
        base: int | None = None
        for page_index in range(current_page_index - 1, max(-1, current_page_index - 6), -1):
            try:
                entries = read_pdic(pdic_path(project.images[page_index]))
            except Exception:
                entries = []
            for local_index in range(len(entries) - 1, -1, -1):
                pos = self._exact_reference_position(entries[local_index].word)
                if pos is None:
                    continue
                distance_to_first = (len(entries) - local_index) + skipped_entries
                base = pos + distance_to_first
                break
            if base is not None:
                break
            skipped_entries += len(entries)
        self._previous_reference_base_cache = (current_page_index, base)
        return None if base is None else base + max(0, active_index)

    def _current_wordslist_global_target(self) -> int | None:
        if self.word_window_indices and self.word_highlight_index is not None:
            local = min(max(0, int(self.word_highlight_index)), len(self.word_window_indices) - 1)
            return self.word_window_indices[local]
        return None

    def _sorted_reference_position(self, word: str) -> int | None:
        """Binary-search the native page-less list by pinyin/alphabet key lazily."""
        stripped = (word or "").strip()
        words = self.parent.project.words if self.parent.project else []
        if not stripped or not words:
            return None
        # Use the primary pinyin/alphabet key only. Chinese dictionaries often
        # use their own secondary rule (tone, stroke count, radical, etc.) for
        # homophones, so imposing Unicode as a secondary comparison could make
        # an otherwise pinyin-sorted external list appear non-monotonic. Exact
        # spelling lookup above still places a known word precisely.
        key = reference_sort_key(stripped)[0]
        lo, hi = 0, len(words)
        cache = self.word_sort_key_cache
        while lo < hi:
            mid = (lo + hi) // 2
            mid_key = cache.get(mid)
            if mid_key is None:
                mid_key = reference_sort_key(words[mid])
                cache[mid] = mid_key
            if mid_key[0] < key:
                lo = mid + 1
            else:
                hi = mid
        return min(max(0, lo), len(words) - 1)

    def _infer_sorted_reference_target(self, active_index: int, current_word: str) -> int:
        """Locate an external page-less index by exact word / collation, not row offset."""
        words = self.parent.project.words if self.parent.project else []
        if not words:
            return 0

        near = self._current_wordslist_global_target()
        current_exact = self._exact_reference_position(current_word, near=near)
        if current_exact is not None:
            return current_exact

        previous_anchor: tuple[int, int] | None = None
        next_anchor: tuple[int, int] | None = None
        for index in range(active_index - 1, -1, -1):
            if index >= len(self.vars):
                continue
            pos = self._exact_reference_position(self.vars[index].get(), near=near)
            if pos is not None:
                previous_anchor = (index, pos)
                break
        for index in range(active_index + 1, len(self.vars)):
            pos = self._exact_reference_position(self.vars[index].get(), near=near)
            if pos is not None:
                next_anchor = (index, pos)
                break

        stripped = (current_word or "").strip()
        if stripped:
            target = self._sorted_reference_position(stripped)
            if target is not None:
                # Exact neighbouring terms are useful bounds, but never assume
                # one row in this dictionary equals one row in the external one.
                if previous_anchor and next_anchor and previous_anchor[1] <= next_anchor[1]:
                    return max(previous_anchor[1], min(next_anchor[1], target))
                if previous_anchor and target < previous_anchor[1]:
                    return previous_anchor[1]
                if next_anchor and target > next_anchor[1]:
                    return next_anchor[1]
                return target

        if previous_anchor and next_anchor and previous_anchor[1] <= next_anchor[1]:
            return round((previous_anchor[1] + next_anchor[1]) / 2)
        if previous_anchor:
            return previous_anchor[1]
        if next_anchor:
            return next_anchor[1]
        if near is not None:
            return near
        return 0

    def _infer_reference_target(self, active_index: int, current_word: str) -> int:
        words = self.parent.project.words if self.parent.project else []
        if not words:
            return 0
        if self._effective_wordslist_locator_mode() == "sorted":
            return self._infer_sorted_reference_target(active_index, current_word)

        # Do not trust the current OCR/edit field first: it may be empty or a
        # valid-looking but wrong word. Neighbouring already-verified words are
        # stronger anchors for locating the auxiliary dictionary list.
        previous_anchor: tuple[int, int] | None = None
        next_anchor: tuple[int, int] | None = None
        for index in range(active_index - 1, -1, -1):
            if index >= len(self.vars):
                continue
            pos = self._exact_reference_position(self.vars[index].get())
            if pos is not None:
                previous_anchor = (index, pos)
                break
        for index in range(active_index + 1, len(self.vars)):
            pos = self._exact_reference_position(self.vars[index].get())
            if pos is not None:
                next_anchor = (index, pos)
                break

        if previous_anchor and next_anchor:
            prev_i, prev_pos = previous_anchor
            next_i, next_pos = next_anchor
            prev_estimate = prev_pos + (active_index - prev_i)
            next_estimate = next_pos - (next_i - active_index)
            if prev_pos < next_pos:
                target = round((prev_estimate + next_estimate) / 2)
                return max(prev_pos, min(next_pos, target))
            # If the two anchors conflict, the preceding verified entry is the
            # more natural typing direction and therefore wins.
            return prev_estimate
        if previous_anchor:
            prev_i, prev_pos = previous_anchor
            return prev_pos + (active_index - prev_i)
        if next_anchor:
            next_i, next_pos = next_anchor
            return next_pos - (next_i - active_index)

        # No usable surrounding word on this page. Use current content only now.
        current_exact = self._exact_reference_position(current_word)
        if current_exact is not None:
            return current_exact

        previous_page = self._previous_page_reference_target(active_index)
        if previous_page is not None:
            return previous_page

        # Last-resort fuzzy/collation position for a non-empty OCR result. Keep
        # the current virtual-list position for a blank field rather than jumping
        # back to the beginning of a 190k-word list.
        stripped = (current_word or "").strip()
        if stripped and self.sorted_word_keys:
            key = self._wordslist_lookup_key(stripped)
            pos = bisect.bisect_left(self.sorted_word_keys, key)
            pos = min(max(0, pos), len(self.sorted_word_indices) - 1)
            return self.sorted_word_indices[pos]
        if self.word_window_indices and self.word_highlight_index is not None:
            local = min(max(0, self.word_highlight_index), len(self.word_window_indices) - 1)
            return self.word_window_indices[local]
        return 0

    def locate_reference_word(self, word: str, active_index: int | None = None) -> None:
        if not self.parent.project or not self.parent.project.words:
            return
        words = self.parent.project.words
        index = self.active_index if active_index is None else int(active_index)
        target = self._infer_reference_target(index, word)
        target = max(0, min(int(target), len(words) - 1))

        if target not in self.word_window_indices:
            self._show_wordslist_window(target)
            return
        local = target - self.word_window_start
        self.word_highlight_index = local
        self._set_word_list_highlight(local)

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
        sync_review_entry_classification(self)
        if getattr(self, "_filter_rows_active", False):
            return
        project = getattr(self.parent, "project", None)
        current_page = getattr(self.parent, "current_page", None)
        parent_image = getattr(self.parent, "image", None)
        if project is None or current_page is None or parent_image is None:
            # Keep lightweight unit/embedding stubs compatible without ever
            # making the production path fall back to synchronous image work.
            fallback = self.__dict__.get("render_rows")
            if callable(fallback):
                fallback()
            return
        if focus_index is None:
            focus_index = self.active_index
        self._review_render_focus_index = max(0, int(focus_index))

        page = self.parent.current_page
        page_index = int(self.parent.current_index)
        settings = replace(self.parent.settings)
        requested_auto_zoom = bool(self.review_zoom_auto)
        review_zoom = max(0.01, float(self.review_zoom))
        auto_image_area_width = self._review_image_area_width()
        viewer_width = max(1, int(self.parent.canvas.winfo_width()))
        ordered_snapshot = [
            replace(entry) for entry in self.parent._ordered_entries_reading_order()
        ]
        signature = tuple(
            (int(entry.x), int(entry.y), str(entry.word))
            for entry in ordered_snapshot
        )
        page_stem = page.stem

        def worker():
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            review_settings, geometry = _review_crop_context(
                image, settings, viewer_width, page_index,
            )
            raw_crops: list[Image.Image] = []
            for index, entry in enumerate(ordered_snapshot):
                next_entry = (
                    ordered_snapshot[index + 1]
                    if index + 1 < len(ordered_snapshot) else None
                )
                box = _review_line_box(
                    entry, geometry, image, review_settings, next_entry,
                )
                raw_crops.append(image.crop(box).convert("RGB"))
            effective_zoom = review_zoom
            if requested_auto_zoom and raw_crops:
                widest_crop = max(crop.width for crop in raw_crops)
                effective_zoom = review_auto_fit_zoom(
                    widest_crop, auto_image_area_width, 0.99,
                )
            crops = [
                crop.resize(
                    (
                        max(1, round(crop.width * effective_zoom)),
                        max(1, round(crop.height * effective_zoom)),
                    ),
                    Image.Resampling.LANCZOS,
                )
                for crop in raw_crops
            ]
            return page_stem, signature, crops, effective_zoom, requested_auto_zoom

        def done(payload) -> None:
            try:
                if not self.winfo_exists() or self._prefetch_closed:
                    return
            except tk.TclError:
                return
            result_stem, result_signature, crops, effective_zoom, requested_auto_zoom = payload
            if requested_auto_zoom != bool(self.review_zoom_auto):
                self._request_render_rows(focus_index=self._review_render_focus_index)
                return
            if not self.parent.current_page or self.parent.current_page.stem != result_stem:
                return
            current_signature = tuple(
                (int(entry.x), int(entry.y), str(entry.word))
                for entry in self.parent._ordered_entries_reading_order()
            )
            if current_signature != result_signature:
                self._request_render_rows(focus_index=self._review_render_focus_index)
                return
            if requested_auto_zoom:
                self.review_zoom = max(0.01, float(effective_zoom))
                self.review_zoom_var.set(f"自动 {_format_layout_percent(self.review_zoom * 100.0)}%")
                self.parent.settings.review_zoom_percent = 0.0
            target_focus = self._review_render_focus_index
            self.render_rows(preloaded_crops=crops)
            if reset_scroll:
                self._reset_rows_scroll_top()
            if self.editors:
                self.focus_index(min(target_focus, len(self.editors) - 1))

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            try:
                if not self.winfo_exists() or self._prefetch_closed:
                    return
            except tk.TclError:
                return
            self.parent.status_var.set(f"校对裁剪生成失败：{exc}")
            if not self.rows.winfo_children():
                ttk.Label(
                    self.rows, text=f"校对裁剪生成失败：{exc}",
                ).grid(row=0, column=0, sticky="ew", padx=8, pady=20)

        self.parent._start_ui_worker(
            self._review_render_worker_key, worker, done, failed,
        )

    def render_rows(self, preloaded_crops: list[Image.Image] | None = None) -> None:
        if getattr(self, "_filter_rows_active", False):
            return
        if preloaded_crops is None:
            self._request_render_rows(focus_index=self.active_index)
            return
        current_stem = self.parent.current_page.stem if self.parent.current_page else ""
        if self._rendered_page_stem and self._rendered_page_stem == current_stem:
            self._capture_simplified_edits(self._rendered_page_stem)
        for child in self.rows.winfo_children():
            child.destroy()
        self.vars.clear(); self.row_entries.clear(); self.editors.clear(); self.editor_frames.clear(); self.simplified_vars.clear(); self.simplified_editors.clear(); self.simplified_search_buttons.clear(); self.simplified_actual_values.clear(); self.simplified_manual_flags.clear(); self.simplified_auto_refresh_flags.clear(); self.editor_crop_widths.clear(); self.thumbnails.clear()
        self._rendered_page_stem = current_stem
        simplified_records = self._simplified_page_records(current_stem) if current_stem else {}
        if not self.parent.image:
            return
        ordered = self.parent._ordered_entries_reading_order()
        if len(preloaded_crops) < len(ordered):
            self._request_render_rows(focus_index=self.active_index)
            return
        words = self.parent._project_words if self.parent.project else set()
        for index, entry in enumerate(ordered):
            next_entry = ordered[index + 1] if index + 1 < len(ordered) else None
            # Crop and LANCZOS resize are completed by a worker before this
            # UI-only materialization step. ImageTk creation stays on Tk.
            crop = preloaded_crops[index]
            photo = ImageTk.PhotoImage(themed_display_image(crop, self.parent.appearance_mode))
            self.thumbnails.append(photo)
            self.editor_crop_widths.append(crop.width)
            picture = ttk.Label(self.rows, image=photo, style="PCR.Crop.TLabel")
            picture.grid(row=index * 2, column=0, sticky="ew", padx=6, pady=(8, 0))
            var = tk.StringVar(value=entry.word)
            # Review zoom changes only the cropped line image.  Text-entry font
            # size is a user setting and remains fixed while zooming the image.
            editor_font_size = _review_editor_font_size(self.parent.settings)
            review_family = resolve_content_font_family(
                self,
                self.parent.settings.review_entry_font_family,
                self.parent.settings.ocr_language,
            )
            review_weight = "bold" if self.parent.settings.review_entry_font_bold else "normal"
            review_slant = "italic" if self.parent.settings.review_entry_font_italic else "roman"
            simplified_family = resolve_content_font_family(
                self,
                getattr(
                    self.parent.settings,
                    "review_simplified_font_family",
                    self.parent.settings.review_entry_font_family,
                ),
                self.parent.settings.ocr_language,
            )
            simplified_font_size = max(6, int(getattr(self.parent.settings, "review_simplified_font_size", editor_font_size)))
            simplified_bold = bool(getattr(self.parent.settings, "review_simplified_font_bold", self.parent.settings.review_entry_font_bold))
            simplified_italic = bool(getattr(self.parent.settings, "review_simplified_font_italic", self.parent.settings.review_entry_font_italic))
            measure_font = font.Font(
                family=review_family, size=editor_font_size, weight=review_weight, slant=review_slant
            )
            char_px = max(1, measure_font.measure("0"))
            editor_width_chars = max(8, min(140, round(crop.width / char_px)))
            editor_bg, editor_fg, selection_bg, selection_fg = (
                self._review_membership_colors(entry.word in words)
            )
            editor_frame = tk.Frame(
                self.rows,
                bg=editor_bg,
                bd=0,
                relief="flat",
                highlightthickness=1,
                highlightbackground=editor_bg,
                highlightcolor=editor_bg,
            )
            # Membership colors are intentionally pale status colors in both
            # themes. Keep this frame out of the generic dark mapper.
            editor_frame._pc_skip_classic_appearance = True
            delete_button = tk.Button(
                editor_frame, text="[X]", width=3, takefocus=False,
                relief="flat", bd=0, padx=1, pady=0, cursor="hand2",
                fg="#8b1a1a", bg="#f3eeee", activebackground="#f4d9d9",
                command=lambda i=index: self.delete_review_entry(i),
            )
            delete_button.grid(row=0, column=0, sticky="nsw", padx=(0, 2))
            editor = tk.Entry(
                editor_frame, textvariable=var, width=1,
                font=_entry_font_spec(
                    review_family, editor_font_size,
                    self.parent.settings.review_entry_font_bold, self.parent.settings.review_entry_font_italic,
                ),
                bg=editor_bg,
                disabledbackground=editor_bg,
                foreground=editor_fg,
                disabledforeground=editor_fg,
                insertbackground=editor_fg,
                selectbackground=selection_bg,
                selectforeground=selection_fg,
                relief="flat",
                bd=0,
                highlightthickness=0,
            )
            # Membership surfaces use theme-aware status colours.
            editor._pc_skip_classic_appearance = True
            editor.grid(
                row=0, column=1, sticky="nsew",
                padx=(max(0, int(self.parent.settings.review_entry_left_padding)), 0),
                ipady=max(0, int(self.parent.settings.review_entry_vertical_padding)),
            )
            simplified_key = simplified_entry_key(entry.x, entry.y)
            saved_simplified = simplified_records.get(simplified_key)
            saved_manual = bool(saved_simplified.get("manual", False)) if saved_simplified else False
            saved_text = str(saved_simplified.get("text", "")) if saved_simplified is not None else None
            # v2.12.11: once a simplified record exists on disk, its text is the
            # source of truth on reopen, regardless of whether it was originally
            # generated by OpenCC or manually edited.  OpenCC is only used to
            # seed rows that have no persisted record yet.
            auto_refresh = saved_simplified is None
            if saved_simplified is not None:
                simplified_actual = saved_text
            else:
                simplified_actual = self._auto_simplified_value(entry.word)
            simplified_var = tk.StringVar(
                value=self._simplified_display_from_value(entry.word, simplified_actual, saved_manual)
            )
            simplified_editor = tk.Entry(
                editor_frame, textvariable=simplified_var, width=1,
                font=_entry_font_spec(
                    simplified_family, simplified_font_size, simplified_bold, simplified_italic,
                ),
                bg="#f4f4f4", foreground="#303030",
                relief="flat", bd=0, highlightthickness=0, justify="left",
            )
            simplified_editor.grid(
                row=0, column=2, sticky="nsew", padx=(6, 0),
                ipady=max(0, int(self.parent.settings.review_entry_vertical_padding)),
            )
            simplified_search_button = tk.Button(
                editor_frame, text="网查", width=4, takefocus=False,
                relief="flat", bd=0, padx=2, pady=0, cursor="hand2",
                bg="#eceff3", activebackground="#e1e5ea", foreground="#30343b",
                command=lambda i=index: self.lookup_simplified_online(i),
            )
            simplified_search_button.grid(row=0, column=3, sticky="ns", padx=(4, 0))
            editor_frame.columnconfigure(1, weight=1, uniform=f"review_pair_{index}")
            editor_frame.columnconfigure(2, weight=1, uniform=f"review_pair_{index}")
            editor_frame.columnconfigure(3, weight=0)
            editor_frame.grid(row=index * 2 + 1, column=0, sticky="ew", padx=6, pady=(2, 8))
            if not self.review_show_simplified_var.get():
                simplified_editor.grid_remove()
                simplified_search_button.grid_remove()
                editor_frame.columnconfigure(2, weight=0, uniform="")
            if self.parent._foreground_batch_state(self.parent.current_index) == "processing":
                delete_button.configure(state="disabled")
                editor.configure(state="disabled", disabledforeground="#555555")
                simplified_editor.configure(state="disabled", disabledforeground="#666666")
                simplified_search_button.configure(state="disabled")
            editor.bind("<FocusIn>", lambda _e, i=index: self.set_active(i))
            editor.bind("<KeyPress-grave>", lambda _e, i=index: self.delete_review_entry(i))
            editor.bind("<KeyPress>", self.parent._entry_keypress_batch_guard)
            editor.bind("<<Paste>>", lambda _e: None if self.parent._claim_page_for_manual_edit() else "break")
            editor.bind("<<Cut>>", lambda _e: None if self.parent._claim_page_for_manual_edit() else "break")
            editor.bind("<KeyRelease>", lambda e, i=index: self.on_key(e, i))
            editor.bind("<Return>", lambda _e, i=index: self.focus_index(i + 1))
            editor.bind("<Up>", lambda _e, i=index: self.focus_index(i - 1))
            editor.bind("<Down>", lambda _e, i=index: self.focus_index(i + 1))
            simplified_editor.bind("<FocusIn>", lambda _e, i=index: self._focus_simplified_editor(i))
            simplified_editor.bind("<KeyPress-grave>", lambda _e, i=index: self.delete_review_entry(i))
            simplified_editor.bind("<KeyPress>", self.parent._entry_keypress_batch_guard)
            simplified_editor.bind("<<Paste>>", lambda _e, i=index: self._claim_simplified_clipboard_edit(i))
            simplified_editor.bind("<<Cut>>", lambda _e, i=index: self._claim_simplified_clipboard_edit(i))
            simplified_editor.bind("<KeyRelease>", lambda e, i=index: self.on_simplified_key(e, i))
            simplified_editor.bind("<Return>", lambda _e, i=index: self.focus_index(i + 1))
            for widget in (picture, delete_button, editor_frame, editor, simplified_editor, simplified_search_button):
                widget.bind("<MouseWheel>", self.scroll_rows)
                widget.bind("<Button-4>", lambda e: self.scroll_rows_linux(-1))
                widget.bind("<Button-5>", lambda e: self.scroll_rows_linux(1))
            self.vars.append(var); self.row_entries.append(entry); self.editors.append(editor); self.editor_frames.append(editor_frame)
            self.simplified_vars.append(simplified_var); self.simplified_editors.append(simplified_editor)
            self.simplified_search_buttons.append(simplified_search_button)
            self.simplified_actual_values.append(simplified_actual)
            self.simplified_manual_flags.append(saved_manual)
            self.simplified_auto_refresh_flags.append(auto_refresh)
            materialized_record = {
                "x": int(entry.x), "y": int(entry.y), "source_word": entry.word,
                "text": "" if simplified_actual is None else str(simplified_actual), "manual": saved_manual,
            }
            # Materialize OpenCC only when this row has never had a saved
            # simplified record.  Merely reopening a page must not rewrite an
            # existing automatic or manual value.
            if saved_simplified is None:
                simplified_records[simplified_key] = materialized_record
                self._simplified_dirty_pages.add(current_stem)
        self.rows.columnconfigure(0, weight=1)
        self._update_title()
        self._refresh_editor_ocr_compare()
        if self.editors:
            self.editors[0].focus_set()
            self.set_active(0)
        self._schedule_adjacent_preload()
        self.parent._apply_current_appearance(self.rows)
        # Re-apply theme-aware membership colours after generic theming.
        for row_index, row_entry in enumerate(self.row_entries):
            self._set_editor_membership_color(
                row_index, row_entry.word in words
            )

    def _candidate_for_entry(self, entry: WordEntry) -> dict | None:
        return self.parent._candidate_for_entry(entry)

    def _refresh_simplified_for_index(self, index: int) -> None:
        if not (0 <= index < len(self.vars) and index < len(self.simplified_vars)):
            return
        # Any simplified value already persisted before this page was opened
        # is independent data, even when it was originally generated by OpenCC.
        # Only never-saved rows are allowed to follow original-headword edits
        # automatically during the current session.
        manual = bool(self.simplified_manual_flags[index]) if index < len(self.simplified_manual_flags) else False
        refresh_flags = getattr(self, "simplified_auto_refresh_flags", [])
        auto_refresh = bool(refresh_flags[index]) if index < len(refresh_flags) else True
        if manual or not auto_refresh:
            if index == getattr(self, "active_index", -1):
                self._refresh_cc_simplified_comparison(index)
            return
        original = self.vars[index].get().strip()
        fallback = self.simplified_actual_values[index] if index < len(self.simplified_actual_values) else None
        actual = self._auto_simplified_value(original, fallback=fallback)
        if index < len(self.simplified_actual_values):
            self.simplified_actual_values[index] = actual
        self.simplified_vars[index].set(self._simplified_display_from_value(original, actual, False))
        stem = self._rendered_page_stem
        row_entries = self._bound_row_entries()
        if stem and index < len(row_entries):
            entry = row_entries[index]
            self._simplified_page_records(stem)[simplified_entry_key(entry.x, entry.y)] = {
                "x": int(entry.x), "y": int(entry.y),
                "source_word": original, "text": "" if actual is None else str(actual),
                "manual": False,
            }
            self._simplified_dirty_pages.add(stem)
        if index == getattr(self, "active_index", -1):
            self._refresh_cc_simplified_comparison(index)

    def _refresh_all_simplified(self) -> None:
        for index in range(min(len(self.vars), len(self.simplified_vars))):
            self._refresh_simplified_for_index(index)

    def regenerate_simplified_current_page(self) -> None:
        """Force OpenCC regeneration for every simplified headword on the current page."""
        if not self.parent.current_page or not self.vars:
            return
        row_entries = self._bound_row_entries()
        count = min(len(self.vars), len(self.simplified_vars), len(row_entries))
        if count <= 0:
            return
        originals = [self.vars[index].get().strip() for index in range(count)]
        regenerated = [simplify_text(original) for original in originals]
        if any(value is None for value in regenerated):
            messagebox.showerror(
                "重新简体化",
                "OpenCC不可用，未覆盖本页已有的简体化结果。",
                parent=self,
            )
            return
        if not self.parent._claim_page_for_manual_edit():
            return

        stem = self._rendered_page_stem or self.parent.current_page.stem
        records = self._simplified_page_records(stem)
        for index, (entry, original, actual) in enumerate(
            zip(row_entries[:count], originals, regenerated)
        ):
            if index < len(self.simplified_actual_values):
                self.simplified_actual_values[index] = actual
            if index < len(self.simplified_manual_flags):
                self.simplified_manual_flags[index] = False
            if index < len(self.simplified_auto_refresh_flags):
                self.simplified_auto_refresh_flags[index] = False
            self.simplified_vars[index].set(
                self._simplified_display_from_value(original, actual, False)
            )
            records[simplified_entry_key(entry.x, entry.y)] = {
                "x": int(entry.x),
                "y": int(entry.y),
                "source_word": original,
                "text": str(actual),
                "manual": False,
            }

        self._simplified_dirty_pages.add(stem)
        self._persist_simplified_page(stem)
        self._refresh_cc_simplified_comparison(self.active_index)
        self.parent.status_var.set(
            f"已重新简体化当前页：{self.parent.current_page.name}｜覆盖 {count} 条简体结果"
        )

    def _apply_simplified_visibility(self) -> None:
        show = bool(self.review_show_simplified_var.get())
        for index, (frame, widget) in enumerate(zip(self.editor_frames, self.simplified_editors)):
            button = self.simplified_search_buttons[index] if index < len(self.simplified_search_buttons) else None
            try:
                if show:
                    self._refresh_simplified_for_index(index)
                    frame.columnconfigure(1, weight=1, uniform=f"review_pair_{index}")
                    frame.columnconfigure(2, weight=1, uniform=f"review_pair_{index}")
                    widget.grid()
                    if button is not None:
                        button.grid()
                else:
                    widget.grid_remove()
                    if button is not None:
                        button.grid_remove()
                    frame.columnconfigure(1, weight=1, uniform="")
                    frame.columnconfigure(2, weight=0, uniform="")
            except tk.TclError:
                pass

    def _toggle_review_simplified(self) -> None:
        self.parent.settings.review_show_simplified = bool(self.review_show_simplified_var.get())
        self.parent.save_settings()
        self._apply_simplified_visibility()

    def _change_review_ocr_compare_source(self, _event: tk.Event | None = None) -> None:
        key = self.OCR_COMPARE_LABEL_TO_KEY.get(self.review_ocr_compare_var.get(), "fusion")
        self.parent.settings.review_ocr_compare_source = key
        self.parent.save_settings()
        self._refresh_editor_ocr_compare()
        if getattr(self, "_filter_rows_active", False):
            self.parent.status_var.set(
                "已切换筛选 OCR 比较来源；点击【筛选】可按新来源重新筛选 OCR 不匹配。"
            )

    def _ocr_compare_word(self, candidate: dict | None) -> str:
        key = self.OCR_COMPARE_LABEL_TO_KEY.get(self.review_ocr_compare_var.get(), "fusion")
        return _candidate_word_for_ocr_source(candidate, key)

    def _refresh_editor_ocr_compare(self, index: int | None = None) -> None:
        """Outline review editors in red when they differ from the selected OCR source.

        A missing result for the selected OCR engine is neutral: no mismatch
        outline is shown. Comparison uses the same normalized text key as the
        coloured OCR-result buttons, so spacing/full-width/punctuation noise
        does not create a false red border.
        """
        if not self.editor_frames or not self.vars:
            return
        ordered = self.parent._ordered_entries_reading_order()
        indices = [index] if index is not None else list(range(min(len(self.vars), len(ordered))))
        for i in indices:
            if i is None or not (0 <= i < len(self.editor_frames)) or i >= len(ordered):
                continue
            candidate = self._candidate_for_entry(ordered[i])
            ocr_word = self._ocr_compare_word(candidate)
            editor_word = self.vars[i].get()
            mismatch = bool(ocr_word) and _review_similarity_key(editor_word) != _review_similarity_key(ocr_word)
            frame = self.editor_frames[i]
            normal_bg = str(frame.cget("bg"))
            border = "#d32f2f" if mismatch else normal_bg
            try:
                frame.configure(
                    highlightthickness=(2 if mismatch else 1),
                    highlightbackground=border,
                    highlightcolor=border,
                )
            except tk.TclError:
                pass

    def _show_ocr_options(self, candidate: dict | None) -> None:
        """Render Paddle/Tesseract/Lens/fused OCR results on one compact line."""
        for child in self.ocr_options.winfo_children():
            child.destroy()
        self.ocr_result_buttons = []
        self.active_candidate = candidate

        current_word = self.vars[self.active_index].get() if 0 <= self.active_index < len(self.vars) else ""
        values: dict[str, str] = {"paddle": "", "tesseract": "", "lens": "", "fusion": ""}
        if candidate:
            for engine, _label, word, _confidence, is_final in _candidate_choice_rows(candidate):
                if is_final:
                    values["fusion"] = word
                elif engine in values:
                    values[engine] = word

        slots = (("P", "paddle"), ("T", "tesseract"), ("L", "lens"), ("融", "fusion"))
        for slot_index, (short_label, key) in enumerate(slots):
            word = values.get(key, "")
            if word:
                bg = _review_similarity_color(_review_text_similarity(current_word, word))
                button = tk.Button(
                    self.ocr_options, text=f"{short_label}: {word}",
                    command=lambda value=word: self.use_ocr_word(value),
                    anchor="w", justify="left", relief="flat", bd=0, padx=5, pady=2,
                    bg=bg, activebackground=bg, foreground="#202020",
                    highlightthickness=1, highlightbackground=bg,
                )
                button.grid(row=0, column=slot_index, sticky="ew", padx=((0 if slot_index == 0 else 3), 0))
                self.ocr_result_buttons.append((button, word))
            else:
                button = tk.Button(
                    self.ocr_options, text=f"{short_label}: -", state="disabled",
                    anchor="w", justify="left", relief="flat", bd=0, padx=5, pady=2,
                    bg="#f1f2f4", activebackground="#f1f2f4",
                    disabledforeground="#777777", highlightthickness=1,
                    highlightbackground="#e1e4e8",
                )
                button.grid(row=0, column=slot_index, sticky="ew", padx=((0 if slot_index == 0 else 3), 0))
            self.ocr_options.columnconfigure(slot_index, weight=1)

    def _refresh_ocr_similarity_colors(self) -> None:
        """Recolour OCR choices against the currently edited headword."""
        if not self.ocr_result_buttons:
            return
        current_word = self.vars[self.active_index].get() if 0 <= self.active_index < len(self.vars) else ""
        for button, candidate_word in self.ocr_result_buttons:
            color = _review_similarity_color(_review_text_similarity(current_word, candidate_word))
            try:
                button.configure(bg=color, activebackground=color)
            except tk.TclError:
                pass

    def use_ocr_word(self, word: str) -> None:
        if not self.editors or not self.parent._claim_page_for_manual_edit():
            return
        self.vars[self.active_index].set(word)
        self.editors[self.active_index].icursor("end")
        self.on_key(type("_Event", (), {"char": ""})(), self.active_index)

    def set_active(self, index: int) -> None:
        self.active_index = index
        self._update_title()
        ordered = self.parent._ordered_entries_reading_order()
        candidate = self._candidate_for_entry(ordered[index]) if 0 <= index < len(ordered) else None
        self._show_ocr_options(candidate)
        if 0 <= index < len(ordered):
            self.parent.highlight_review_entry(ordered[index])
        if 0 <= index < len(self.vars):
            self.locate_reference_word(self.vars[index].get(), index)
            self._refresh_cc_simplified_comparison(index)
            self._schedule_network_lookup(self.vars[index].get())
        sync_review_entry_classification(self)

    def _scroll_editor_into_view(self, index: int) -> None:
        if not (0 <= index < len(self.editors)):
            return
        try:
            self.update_idletasks()
            row_box = self.rows.grid_bbox(0, index * 2)
            if row_box and row_box[3] > 0:
                target_top = max(0, int(row_box[1]) - 6)
            else:
                target_top = max(0, self.editor_frames[index].winfo_y() - 40)
            target_bottom = self.editor_frames[index].winfo_y() + self.editor_frames[index].winfo_height() + 8
            view_top = float(self.canvas.canvasy(0))
            view_height = max(1, self.canvas.winfo_height())
            total_height = max(1, self.rows.winfo_reqheight())
            if target_top < view_top:
                self.canvas.yview_moveto(max(0.0, min(1.0, target_top / total_height)))
            elif target_bottom > view_top + view_height:
                new_top = max(0, target_bottom - view_height)
                self.canvas.yview_moveto(max(0.0, min(1.0, new_top / total_height)))
        except tk.TclError:
            pass

    def focus_index(self, index: int) -> str:
        if 0 <= index < len(self.editors):
            self.editors[index].focus_set()
            self.editors[index].icursor("end")
            self.editors[index].xview_moveto(1.0)
            self._scroll_editor_into_view(index)
        return "break"

    def on_key(self, event: tk.Event, index: int) -> None:
        char = getattr(event, "char", "")
        if self.replace_digits.get() and char in self.DIGIT_KEYS:
            replacement = self.digit_map_vars[self.DIGIT_KEYS.index(char)].get()
            if replacement:
                editor = self.editors[index]
                pos = editor.index("insert")
                text = editor.get()
                start = max(0, pos - 1)
                editor.delete(0, "end")
                editor.insert(0, text[:start] + replacement + text[pos:])
                editor.icursor(start + len(replacement))
        words = self.parent._project_words if self.parent.project else set()
        self._set_editor_membership_color(index, self.vars[index].get().strip() in words)
        self._refresh_simplified_for_index(index)
        self._refresh_editor_ocr_compare(index)
        if index == self.active_index:
            self._refresh_ocr_similarity_colors()
            self._refresh_cc_simplified_comparison(index)
            self.locate_reference_word(self.vars[index].get(), index)
            self._schedule_network_lookup(self.vars[index].get())

    def _set_editor_membership_color(self, index: int, in_wordslist: bool) -> None:
        color, foreground, selection_bg, selection_fg = (
            self._review_membership_colors(in_wordslist)
        )
        if 0 <= index < len(self.editors):
            try:
                self.editors[index].configure(
                    bg=color,
                    disabledbackground=color,
                    foreground=foreground,
                    disabledforeground=foreground,
                    insertbackground=foreground,
                    selectbackground=selection_bg,
                    selectforeground=selection_fg,
                )
            except tk.TclError:
                pass
        if 0 <= index < len(self.editor_frames):
            try:
                frame = self.editor_frames[index]
                current_border = str(frame.cget("highlightbackground"))
                mismatch_border = current_border.lower() == "#d32f2f"
                frame.configure(
                    bg=color,
                    highlightbackground=("#d32f2f" if mismatch_border else color),
                    highlightcolor=("#d32f2f" if mismatch_border else color),
                )
            except tk.TclError:
                pass

    def delete_review_entry(self, index: int) -> str:
        """Delete one proofreading row and mirror the deletion on the main page.

        The review window and main canvas share ``parent.entries``.  Commit all
        visible proofreading text before removing the selected Entry so deleting
        a middle row cannot shift later text onto the wrong headword.  Persist the
        PDIC immediately and redraw both views; the grave/backtick shortcut uses
        the same path as the visible [X] button.
        """
        row_entries = self._bound_row_entries()
        if not (0 <= int(index) < len(row_entries)):
            return "break"
        if not self.parent._claim_page_for_manual_edit():
            return "break"

        self._commit_edits()
        entry = row_entries[int(index)]
        simplified_key = simplified_entry_key(entry.x, entry.y)
        rendered_stem = getattr(self, "_rendered_page_stem", "")
        if rendered_stem and hasattr(self, "_simplified_page_cache"):
            self._simplified_page_records(rendered_stem).pop(simplified_key, None)
            self._simplified_dirty_pages.add(rendered_stem)

        # When the row came from a named OCR review candidate, remember the
        # deletion as an explicit deselection so reopening/reprocessing the page
        # does not silently resurrect a manually removed headword.
        if entry.candidate_id:
            candidate = self.parent.get_review_candidate(entry.candidate_id)
            if candidate is not None:
                candidate["selected"] = False
                check_var = self.parent.candidate_check_vars.get(str(entry.candidate_id))
                if check_var is not None:
                    check_var.set(False)
                self.parent._write_manual_override(
                    candidate, selected=False, word=entry.word, engine="review_delete"
                )

        if entry in self.parent.entries:
            self.parent.entries.remove(entry)
        self.parent._sort_entries_reading_order()
        self.parent.clear_review_entry_highlight()
        # Do not sync stale main-canvas Entry widgets back into the shared model:
        # the proofreading text above is the newest source of truth.
        self.parent.save_pdic(silent=True, sync_editors=False)
        if getattr(self, "_rendered_page_stem", "") and hasattr(self, "_simplified_page_cache"):
            self._persist_simplified_page(self._rendered_page_stem)
        self.parent.redraw()

        next_index = min(int(index), max(0, len(self.parent.entries) - 1))
        deleted_word = entry.word or "（空白词条）"
        self.active_index = next_index if self.parent.entries else 0
        self._request_render_rows(focus_index=self.active_index)
        if not self.parent.entries:
            self._show_ocr_options(None)
            self._update_title()
        self.parent.status_var.set(f"已删除词条：{deleted_word}")
        return "break"

    def _save_digit_map(self) -> None:
        values = [var.get() for var in self.digit_map_vars]
        self.parent.settings.review_digit_map = values[:10]
        self.parent.save_settings()

    def insert_char(self, char: str) -> None:
        if self._filter_rows_active and getattr(self, "filter_editors", []):
            index = max(
                0, min(
                    len(self.filter_editors) - 1,
                    int(getattr(self, "filter_active_local_index", 0)),
                )
            )
            editor = self.filter_editors[index]
            editor.insert("insert", char)
            self._on_filter_key(type("_Event", (), {"char": ""})(), index)
            return
        if self.editors and self.parent._claim_page_for_manual_edit():
            self.editors[self.active_index].insert("insert", char)
            self.on_key(type("_Event", (), {"char": ""})(), self.active_index)

    def _selected_wordslist_global_index(self) -> int | None:
        local = self.word_selected_local_index
        if local is not None and 0 <= int(local) < len(self.word_window_indices):
            return self.word_window_indices[int(local)]
        return None

    def use_selected_word(self, event: tk.Event | None = None) -> None:
        if event is not None:
            self.word_selected_local_index = self._word_list_local_index_from_event(event)
        source = self._selected_wordslist_global_index()
        words = self.parent.project.words if self.parent.project else []
        if source is None or source >= len(words) or not self.editors:
            return
        if not self.parent._claim_page_for_manual_edit():
            return
        index = self.active_index
        self.vars[index].set(words[source])
        self.on_key(type("_Event", (), {"char": ""})(), index)
        # A single click fills the active box but intentionally does not advance;
        # the user can verify the image/text pair before pressing Return.
        self.after_idle(lambda i=index: self.focus_index(i))

    def fill_words(self) -> None:
        if self._effective_wordslist_locator_mode() == "sorted":
            messagebox.showinfo(
                "外部索引模式",
                "当前 wordslist 按外部排序索引定位。来自另一部词典时可能存在增词/漏词，"
                "因此不做连续批量填充；请单击参考词逐条填入。\n\n"
                "若该词表与当前词典逐条对应，请把定位模式改为“同源连续词表”。",
                parent=self,
            )
            return
        start = self._selected_wordslist_global_index()
        if start is None:
            messagebox.showinfo("请选择", "请先在右侧词表中选择起始词。", parent=self)
            return
        if not self.parent._claim_page_for_manual_edit():
            return
        words = self.parent.project.words if self.parent.project else []
        for offset in range(self.active_index, len(self.vars)):
            source = start + offset - self.active_index
            if source >= len(words):
                break
            old = self.vars[offset].get()
            if any(marker in old for marker in ("【", "|", "\\")):
                continue
            self.vars[offset].set(words[source])
            self._set_editor_membership_color(offset, True)
            self._refresh_simplified_for_index(offset)
        self._refresh_ocr_similarity_colors()

    def check_order(self, all_pages: bool) -> None:
        self.save()
        self.parent.check_headword_order(all_pages)

    def save(self, *, redraw_main: bool = True) -> None:
        if getattr(self, "_filter_rows_active", False):
            self._flush_focused_changes_now()
            return
        state = self.parent._foreground_batch_state(self.parent.current_index)
        if state == "processing":
            self.parent.status_var.set("当前页正在后台处理，校对窗口保持只读，未写入 PDIC。")
            return
        if state == "pending":
            row_entries = self._bound_row_entries()
            word_dirty = any(
                i < len(row_entries) and self.vars[i].get().strip() != row_entries[i].word
                for i in range(len(self.vars))
            )
            simplified_dirty = bool(self.parent.current_page and self.parent.current_page.stem in self._simplified_dirty_pages)
            dirty = word_dirty or simplified_dirty
            if not dirty:
                # Browsing a pending page must not accidentally reserve it.
                self.parent.settings.review_zoom_percent = self._stored_review_zoom_percent()
                return
            if not self.parent._claim_page_for_manual_edit():
                return
        self._commit_edits()
        self.parent.settings.review_zoom_percent = self._stored_review_zoom_percent()
        self.parent.save_pdic(sync_editors=False)
        if self.parent.current_page:
            self._persist_simplified_page(self.parent.current_page.stem)
        if self.parent.project:
            try:
                self.parent.settings.to_json(settings_path(self.parent.project.root))
            except OSError:
                pass
        if redraw_main:
            self.parent.redraw()

    def _reset_rows_scroll_top(self) -> None:
        """Return the proofreading crop/text viewport to its first row."""
        try:
            self.canvas.yview_moveto(0.0)
        except tk.TclError:
            return
        # render_rows() rebuilds row widgets and their final scrollregion is
        # established on idle; repeat once then so a previous page's scroll
        # position cannot be restored by the pending geometry update.
        def reset_after_layout() -> None:
            try:
                if self.canvas.winfo_exists():
                    self.canvas.yview_moveto(0.0)
            except tk.TclError:
                pass
        self.after_idle(reset_after_layout)

    @staticmethod
    def _prefetch_path_signature(path: Path) -> tuple[bool, int, int]:
        try:
            stat = path.stat()
            return True, int(stat.st_size), int(stat.st_mtime_ns)
        except OSError:
            return False, 0, 0

    @classmethod
    def _page_prefetch_signature_for(cls, project_root: Path, page: Path) -> tuple:
        cache = ocr_cache_root(project_root) / f"{page.stem}.json"
        ppp = ppp_read_path_for_image(page)
        return (
            cls._prefetch_path_signature(page),
            cls._prefetch_path_signature(pdic_path(page)),
            cls._prefetch_path_signature(ppp),
            cls._prefetch_path_signature(cache),
        )

    def _page_prefetch_signature(self, page: Path) -> tuple:
        project = self.parent.project
        if project is None:
            return ()
        return self._page_prefetch_signature_for(project.root, page)

    def _review_prefetch_key(self) -> tuple:
        # repr(AppSettings) intentionally includes every persisted geometry and
        # review option.  Invalidation is conservative: an unrelated setting
        # change may discard a prefetched crop, but a stale crop is never used.
        viewer_width = max(1, int(self.parent.canvas.winfo_width()))
        return (
            repr(self.parent.settings),
            round(float(self.review_zoom), 6),
            round(float(self.parent.view_scale), 6),
            viewer_width,
        )

    def _take_prefetched_page(self, index: int) -> dict | None:
        if not self.parent.project or not (0 <= index < len(self.parent.project.images)):
            return None
        with self._prefetch_lock:
            payload = self._prefetched_pages.pop(index, None)
        if payload is None:
            return None
        page = self.parent.project.images[index]
        if payload.get("project_root") != str(self.parent.project.root):
            return None
        if payload.get("signature") != self._page_prefetch_signature(page):
            return None
        return payload

    def _schedule_adjacent_preload(self) -> None:
        project = self.parent.project
        if project is None or self.parent.current_index < 0 or self.parent.image is None:
            return
        # Capture every Tk-derived value on the UI thread. The worker below
        # touches only filesystem/PIL/pure-Python geometry functions.
        settings_snapshot = replace(self.parent.settings)
        review_zoom = max(0.01, float(self.review_zoom))
        view_scale = float(self.parent.view_scale)
        viewer_width = max(1, int(self.parent.canvas.winfo_width()))
        review_key = self._review_prefetch_key()
        project_root = str(project.root)
        anchor_index = int(self.parent.current_index)
        targets = [
            i for i in (anchor_index - 1, anchor_index + 1)
            if 0 <= i < len(project.images)
        ]
        for index in targets:
            page = project.images[index]
            signature = self._page_prefetch_signature(page)
            with self._prefetch_lock:
                cached = self._prefetched_pages.get(index)
                if cached is not None and cached.get("signature") == signature and cached.get("review_key") == review_key:
                    continue
                if index in self._prefetch_inflight:
                    continue
                self._prefetch_inflight.add(index)

            def worker(
                page_index=index, page_path=page, expected_signature=signature,
                local_settings=settings_snapshot, local_review_zoom=review_zoom,
                local_view_scale=view_scale, local_viewer_width=viewer_width,
                local_review_key=review_key, local_project_root=project_root,
                local_ppp_path=ppp_read_path_for_image(page),
                local_anchor_index=anchor_index,
            ) -> None:
                payload = None
                try:
                    with Image.open(page_path) as opened:
                        image = normalize_page_rgb(opened)
                    entries = read_pdic(pdic_path(page_path))
                    effective_settings = effective_page_settings(
                        local_settings, image.size, page_index,
                    )
                    analysis_image = page_template_analysis_image(
                        image, effective_settings, page_index,
                    )
                    geometry = derive_geometry(analysis_image, effective_settings)
                    sections = read_page_sections(page_path)
                    entries = sort_entries_reading_order(entries, geometry, sections)
                    polygons = read_ppp(local_ppp_path)
                    cache_path = ocr_cache_root(Path(local_project_root)) / f"{page_path.stem}.json"
                    ocr_payload: dict = {}
                    if cache_path.exists():
                        try:
                            loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                            if isinstance(loaded, dict):
                                ocr_payload = loaded
                        except Exception:
                            ocr_payload = {}

                    review_settings, review_geometry = _review_crop_context(
                        image, local_settings, local_viewer_width, page_index
                    )
                    review_crops: list[Image.Image] = []
                    for row, entry in enumerate(entries):
                        next_entry = entries[row + 1] if row + 1 < len(entries) else None
                        box = _review_line_box(entry, review_geometry, image, review_settings, next_entry)
                        crop = image.crop(box).convert("RGB")
                        crop = crop.resize(
                            (
                                max(1, round(crop.width * local_review_zoom)),
                                max(1, round(crop.height * local_review_zoom)),
                            ),
                            Image.Resampling.LANCZOS,
                        )
                        review_crops.append(crop)

                    display_size = (
                        max(1, round(image.width * local_view_scale)),
                        max(1, round(image.height * local_view_scale)),
                    )
                    display_image = image.resize(display_size, Image.Resampling.LANCZOS)
                    # A file rewritten while it was being prefetched is rejected
                    # rather than exposing a mixed old/new page snapshot.
                    if expected_signature == self._page_prefetch_signature_for(
                        Path(local_project_root), page_path,
                    ):
                        payload = {
                            "project_root": local_project_root,
                            "index": page_index,
                            "signature": expected_signature,
                            "review_key": local_review_key,
                            "image": image,
                            "entries": entries,
                            "polygons": polygons,
                            "ocr_payload": ocr_payload,
                            "review_crops": review_crops,
                            "display_size": display_size,
                            "display_image": display_image,
                            "view_scale": local_view_scale,
                        }
                except Exception:
                    payload = None
                finally:
                    with self._prefetch_lock:
                        self._prefetch_inflight.discard(page_index)
                        if payload is not None and not self._prefetch_closed:
                            self._prefetched_pages[page_index] = payload
                            # Keep memory bounded to nearby pages even if the
                            # user navigates rapidly back and forth.
                            while len(self._prefetched_pages) > 4:
                                stale = max(
                                    self._prefetched_pages,
                                    key=lambda i: abs(i - local_anchor_index),
                                )
                                self._prefetched_pages.pop(stale, None)

            threading.Thread(
                target=worker, name=f"ReviewPrefetch-{page.stem}", daemon=True
            ).start()

    def change_page(self, delta: int) -> None:
        if getattr(self, "_filter_rows_active", False):
            self.change_filter_batch(delta)
            return
        target = self.parent.current_index + delta
        # Commit review edits without repainting the page we are about to leave.
        # The parent is told that the current PDIC has already been saved, which
        # also prevents stale main-canvas Entry widgets from overwriting the
        # newer proofreading text during navigation.
        self.save(redraw_main=False)
        preloaded = self._take_prefetched_page(target)
        if self.parent.change_page(
            delta, preloaded=preloaded, current_already_saved=True, async_allowed=False
        ):
            self._sync_review_height_vars()
            crops = None
            if (
                not self.review_zoom_auto
                and preloaded is not None
                and preloaded.get("review_key") == self._review_prefetch_key()
            ):
                crops = list(preloaded.get("review_crops") or [])
            if crops is None:
                self._request_render_rows(focus_index=0, reset_scroll=True)
            else:
                self.render_rows(preloaded_crops=crops)
                self._reset_rows_scroll_top()
            self._update_title()



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
        self.image_metadata_status_var = tk.StringVar(value="—×— px｜DPI —")
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
        # Long-running multi-page work runs in a worker thread so Tk remains
        # responsive. Pause/stop are cooperative and take effect at the next
        # safe page boundary; the page currently being processed is allowed to
        # finish so PDIC/PPP/cache files are never left half-written.
        self._batch_queue: queue.Queue = queue.Queue()
        self._batch_thread: threading.Thread | None = None
        self._batch_pause_event = threading.Event()
        self._batch_pause_event.set()
        self._batch_stop_event = threading.Event()
        self._batch_active = False
        self._batch_parallel = False
        # v2.8.17: sequential drawing/OCR batches may coexist with foreground
        # manual review. Page states are protected so background PDIC writes
        # never race a user's edits on the same page.
        self._batch_foreground_pages = False
        # Read-only preprocessing batches may keep the page list navigable;
        # mutating batches leave this False.
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
        self.project_controller = ProjectController(self)
        self.page_controller = PageController(self)
        self.review_controller = ReviewController(self)
        self._build_ui()
        self.bind_class("Toplevel", "<Map>", self._appearance_toplevel_mapped, add="+")
        self.set_appearance_mode(requested_appearance, persist=False)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.toggle_autosave()
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
        """Keep the left pane wide enough to show the complete page-nav row."""
        paned = self.__dict__.get("main_paned")
        row = self.__dict__.get("page_size_row")
        if paned is None or row is None:
            return
        try:
            self.update_idletasks()
            required = max(520, int(row.winfo_reqwidth()) + 28)
            available = max(0, int(self.winfo_width()) - 420)
            paned.sashpos(0, min(required, available) if available else required)
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
            apply_classic_widget_appearance(root, self.appearance_mode)
        except tk.TclError:
            pass
        if isinstance(root, (tk.Tk, tk.Toplevel)):
            apply_native_titlebar_appearance(root, self.appearance_mode)
            # Theme switches can happen while secondary windows are already
            # mapped. Refresh every descendant Toplevel as well; the <Map> hook
            # below handles windows created after the switch.
            stack = list(root.winfo_children())
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
            self.after_idle(apply_mapped_appearance)
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
        self._apply_current_appearance(self)
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
        style.configure("PC.PageNav.TButton", padding=(2, 2))
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
                    write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
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
        self.sidebar_scrollbar = ttk.Scrollbar(
            sidebar_host, orient="vertical", command=self.sidebar_canvas.yview
        )
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scrollbar.set)
        self.sidebar_scrollbar.pack(side="right", fill="y")
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)
        sidebar = ttk.Frame(
            self.sidebar_canvas, padding=(7, 7, 6, 5), style="PC.Sidebar.TFrame"
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

        page_panel = ttk.Frame(sidebar, padding=(2, 2, 2, 0), style="PC.Sidebar.TFrame")
        self.page_panel = page_panel
        page_panel.grid(row=0, column=0, rowspan=2, sticky="nsew", pady=(5, 0))
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
        for label, mode in (("当前页", "current"), ("当前页至末页", "to_end"),
                            ("当前页至指定页", "to_specified")):
            ttk.Radiobutton(range_row, text=label, variable=self.page_range_var,
                            value=mode).pack(side="left", padx=(0, 3))
        spec_row = ttk.Frame(nav_area)
        spec_row.pack(fill="x", pady=(0, 4))
        ttk.Radiobutton(spec_row, text="指定范围：", variable=self.page_range_var,
                        value="specified").pack(side="left")
        page_range_entry = ttk.Entry(spec_row, textvariable=self.page_range_spec_var, width=12)
        page_range_entry.pack(side="left", fill="x", expand=True, padx=(3, 4))
        page_range_entry.bind("<Return>", lambda _event: self.jump_to_page_spec())
        jump_button = ttk.Button(spec_row, text="跳转", width=5,
                                 command=self.jump_to_page_spec, style="PC.PageNav.TButton")
        jump_button.pack(side="left")
        self._attach_tooltip(jump_button, "跳转到指定页面的第一个有效页面")

        size_row = ttk.Frame(nav_area)
        self.page_size_row = size_row
        size_row.pack(fill="x", pady=(0, 4))
        for symbol, command, tip in (
            ("−", lambda: self.zoom(0.87), "缩小显示"),
            ("+", lambda: self.zoom(1.15), "放大显示"),
            ("⇔", self.fit_page_width, "占满宽度"),
            ("⇕", self.fit_page_height, "占满高度"),
        ):
            if symbol == "+":
                view_zoom_entry = ttk.Entry(
                    size_row, textvariable=self.view_zoom_var, width=6, justify="center",
                    style="PC.Compact.TEntry",
                )
                view_zoom_entry.pack(side="left", padx=2)
                view_zoom_entry.bind("<Return>", self.apply_view_zoom_text)
                view_zoom_entry.bind("<FocusOut>", self.apply_view_zoom_text)
            button = ttk.Button(size_row, text=symbol, width=3, command=command,
                                style="PC.Tool.TButton")
            button.pack(side="left", padx=(0, 3))
            self._attach_tooltip(button, tip)

        nav_row = ttk.Frame(nav_area)
        nav_row.pack(fill="x")
        for symbol, command, tip in (
            ("⨇", lambda: self.jump_to_bookmark(-1), "跳转到上一书签"),
            ("⨈", lambda: self.jump_to_bookmark(1), "跳转到下一书签"),
            ("上页", lambda: self.change_page(-1), "切换到上页"),
            ("下页", lambda: self.change_page(1), "切换到下页"),
        ):
            button = ttk.Button(nav_row, text=symbol, width=4 if len(symbol) == 1 else 5,
                                command=command, style="PC.PageNav.TButton")
            button.pack(side="left", padx=(0, 4))
            self._attach_tooltip(button, tip)
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
            "bookmark": "●", "page": "页面", "section": "区块",
            "lined": "画线", "fill_status": "填充状态", "illustrations": "插图",
        }
        self.page_list.heading("bookmark", text="●", anchor="center")
        self.page_list.heading("page", text="页面", anchor="center")
        self.page_list.heading("section", text="区块", anchor="center")
        self.page_list.heading("lined", text="画线", anchor="center")
        self.page_list.heading("fill_status", text="填充状态", anchor="center")
        self.page_list.heading("illustrations", text="插图", anchor="center")
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
        page_hscroll = ttk.Scrollbar(list_frame, orient="horizontal", command=self.page_list.xview)
        self.page_list.configure(yscrollcommand=self._page_list_yscroll,
                                 xscrollcommand=page_hscroll.set)
        self.page_list.grid(row=0, column=0, sticky="nsew")
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

        self.canvas = tk.Canvas(
            viewer, bg=self._main_ui_colors["canvas"], highlightthickness=0
        )
        hbar = ttk.Scrollbar(viewer, orient="horizontal", command=self.canvas.xview)
        vbar = ttk.Scrollbar(viewer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns"); hbar.grid(row=1, column=0, sticky="ew")
        viewer.rowconfigure(0, weight=1); viewer.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self.canvas_left_click)
        self.canvas.bind("<Control-z>", self._auxiliary_controller.undo)
        self.canvas.bind("<Double-Button-1>", self.canvas_left_double_click)
        self.canvas.bind("<B1-Motion>", self.canvas_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_left_release)
        bind_context_menu(self.canvas, self.canvas_right_click)
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
        """Fill unused sidebar height while retaining scrolling when necessary."""
        canvas = self.__dict__.get("sidebar_canvas")
        sidebar = self.__dict__.get("sidebar")
        window = self.__dict__.get("_sidebar_window")
        if canvas is None or sidebar is None or window is None:
            return
        try:
            viewport_width = max(1, canvas.winfo_width())
            viewport_height = max(1, canvas.winfo_height())
            requested_height = max(1, sidebar.winfo_reqheight())
            canvas.itemconfigure(
                window,
                width=viewport_width,
                height=max(viewport_height, requested_height),
            )
            canvas.configure(scrollregion=canvas.bbox("all"))
        except tk.TclError:
            return

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
        """Apply optional Treeview columns while keeping 页面 permanently visible."""
        if not hasattr(self, "page_list"):
            return
        columns = ["bookmark", "page", "lined"]

        if getattr(self, "_page_column_vars", {}).get("illustrations") is None or self._page_column_vars["illustrations"].get():
            columns.append("illustrations")
        columns.append("section")
        if getattr(self, "_page_column_vars", {}).get("fill_status") is None or self._page_column_vars["fill_status"].get():
            columns.append("fill_status")
        self.page_list.configure(displaycolumns=tuple(columns))
        self.after_idle(self._fit_page_list_columns)
        if hasattr(self, "settings"):
            self.settings.page_list_show_lined = True
            self.settings.page_list_show_fill_status = "fill_status" in columns
            self.settings.page_list_show_illustrations = "illustrations" in columns
            if save and self.project is not None:
                try:
                    self.settings.to_json(settings_path(self.project.root))
                except Exception:
                    pass
        self._schedule_page_cell_overlay_refresh()

    def _page_list_configured(self, _event=None) -> None:
        """Keep visible page-list columns filling the full Treeview width."""
        self._fit_page_list_columns()
        self._schedule_page_cell_overlay_refresh()

    def _fit_page_list_columns(self) -> None:
        if not hasattr(self, "page_list"):
            return
        try:
            raw = self.page_list.cget("displaycolumns")
            visible = tuple(self.tk.splitlist(raw))
            if not visible or visible == ("#all",):
                visible = tuple(self.tk.splitlist(self.page_list.cget("columns")))
            if not visible:
                return
            available = max(1, int(self.page_list.winfo_width()) - 2)
        except (tk.TclError, ValueError):
            return

        header_font = font.nametofont("TkHeadingFont")
        body_font = font.nametofont("TkDefaultFont")
        # Size to content instead of giving "page" a disproportionate share
        # of the entire sidebar width. Keep long filenames scrollable.
        page_names = (
            page.stem for page in getattr(self.project, "images", ())
        ) if self.project else ()
        page_width = max(
            (body_font.measure(name) for name in page_names), default=0
        ) + 10
        base = {
            "bookmark": 25, "page": max(52, page_width),
            "section": 36, "lined": 36,
            "illustrations": 36, "fill_status": 68,
        }
        for column in visible:
            label = self._page_list_heading_labels.get(column, column)
            width = max(base.get(column, 60), header_font.measure(label) + 6)
            self.page_list.column(column, width=width, anchor="center", stretch=False)

    def _hide_page_list_section_heading_hint(self, _event=None) -> None:
        popup = getattr(self, "_page_list_section_heading_hint", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
        self._page_list_section_heading_hint = None

    def _page_list_section_heading_motion(self, event: tk.Event) -> None:
        """Show the SECTION edit hint only while the pointer is over its heading."""
        try:
            over_section = (
                self.page_list.identify_region(event.x, event.y) == "heading"
                and self._page_list_column_at(event.x) == "section"
            )
        except tk.TclError:
            over_section = False
        if not over_section:
            self._hide_page_list_section_heading_hint()
            return
        if getattr(self, "_page_list_section_heading_hint", None) is not None:
            return
        tip = tk.Toplevel(self.page_list)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 18}")
        ttk.Label(
            tip,
            text="双击进入Section编辑模式",
            padding=(7, 4),
            relief="solid",
        ).pack()
        self._page_list_section_heading_hint = tip

    def _page_list_right_click(self, event: tk.Event) -> str | None:
        """Right-click a heading to choose which optional list columns are visible."""
        if not hasattr(self, "page_list") or self.page_list.identify_region(event.x, event.y) != "heading":
            return None
        menu = tk.Menu(self, tearoff=False)
        self._apply_current_appearance(menu)
        bookmark_var = tk.BooleanVar(value=True)
        menu.add_checkbutton(label="●", variable=bookmark_var, state="disabled")
        page_var = tk.BooleanVar(value=True)
        menu.add_checkbutton(label="页面", variable=page_var, state="disabled")
        section_var = tk.BooleanVar(value=True)
        menu.add_checkbutton(label="区块", variable=section_var, state="disabled")
        menu.add_checkbutton(label="画线", state="disabled")
        menu.add_checkbutton(
            label="插图", variable=self._page_column_vars["illustrations"],
            command=lambda: self._apply_page_list_display_columns(save=True),
        )
        menu.add_checkbutton(
            label="填充状态", variable=self._page_column_vars["fill_status"],
            command=lambda: self._apply_page_list_display_columns(save=True),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try: menu.grab_release()
            except tk.TclError: pass
        return "break"

    def _schedule_page_cell_overlay_refresh(self) -> None:
        """Coalesce Treeview cell-overlay repaints into one idle callback.

        Treeview can emit many yscroll/configure callbacks while rows are being
        inserted or metadata is filled.  Scheduling a repaint for each callback
        made large projects appear to hang during startup.
        """
        if not hasattr(self, "page_list"):
            return
        if self._page_overlay_refresh_job is not None:
            return

        def run() -> None:
            self._page_overlay_refresh_job = None
            self._refresh_lined_cell_overlays()

        self._page_overlay_refresh_job = self.after_idle(run)

    def _list_mousewheel(self, event: tk.Event) -> str:
        self.page_list.yview_scroll((-1 if event.delta > 0 else 1) * 3, "units")
        self._schedule_page_cell_overlay_refresh()
        return "break"

    def _page_list_scroll(self, *args) -> None:
        self.page_list.yview(*args)
        self._schedule_page_cell_overlay_refresh()

    def _page_list_yscroll(self, first: str, last: str) -> None:
        if hasattr(self, "page_scroll"):
            self.page_scroll.set(first, last)
        self._schedule_page_cell_overlay_refresh()

    def _update_page_list_sort_headings(self) -> None:
        if not hasattr(self, "page_list"):
            return
        labels = getattr(self, "_page_list_heading_labels", {
            "bookmark": "🔖", "page": "页面", "section": "区块",
            "lined": "画线", "fill_status": "填充状态", "illustrations": "插图",
        })
        active = self._page_list_sort_column
        arrow = " ▼" if self._page_list_sort_descending else " ▲"
        for column, label in labels.items():
            self.page_list.heading(column, text=label + (arrow if column == active else ""))

    def _apply_page_list_sort(self, *, ensure_current_visible: bool = False) -> None:
        if not hasattr(self, "page_list") or not self._page_list_sort_column:
            return
        rows = [(iid, tuple(self.page_list.item(iid, "values"))) for iid in self.page_list.get_children("")]
        ordered = _sorted_page_list_rows(
            rows, self._page_list_sort_column, self._page_list_sort_descending
        )
        for position, (iid, _values) in enumerate(ordered):
            self.page_list.move(iid, "", position)
        self._update_page_list_sort_headings()
        self._schedule_page_cell_overlay_refresh()
        # Background metadata refreshes may re-sort the list many times.  Never
        # force the viewport back to the selected row in that path: doing so
        # makes mouse-wheel browsing snap back to the page the user clicked.
        # Only an explicit header sort asks to reveal the current page again.
        if ensure_current_visible and self.current_index >= 0:
            iid = str(self.current_index)
            if self.page_list.exists(iid):
                self.page_list.see(iid)
                self._center_page_list_iid(iid)

    def _schedule_page_list_resort(self) -> None:
        if not self._page_list_sort_column or not hasattr(self, "page_list"):
            return
        if self._page_list_sort_job is not None:
            return
        def run() -> None:
            self._page_list_sort_job = None
            self._apply_page_list_sort(ensure_current_visible=False)
        self._page_list_sort_job = self.after(80, run)

    def _sort_page_list(self, column: str) -> None:
        if column not in {"bookmark", "page", "section", "lined", "fill_status", "illustrations"}:
            return
        if self._page_list_sort_column == column:
            self._page_list_sort_descending = not self._page_list_sort_descending
        else:
            self._page_list_sort_column = column
            self._page_list_sort_descending = False
        if self._page_list_sort_job is not None:
            try:
                self.after_cancel(self._page_list_sort_job)
            except tk.TclError:
                pass
            self._page_list_sort_job = None
        self._apply_page_list_sort(ensure_current_visible=True)

    def _page_list_column_at(self, x: int) -> str | None:
        """Return the logical Treeview column under a display-space X coordinate."""
        token = str(self.page_list.identify_column(x) or "")
        try:
            display_index = int(token.lstrip("#")) - 1
        except ValueError:
            return None
        raw = self.page_list.cget("displaycolumns")
        display = tuple(self.tk.splitlist(raw))
        if not display or display == ("#all",):
            display = tuple(self.tk.splitlist(self.page_list.cget("columns")))
        return str(display[display_index]) if 0 <= display_index < len(display) else None

    def _page_section_count_text(self, index: int) -> str:
        if not self.project or not (0 <= index < len(self.project.images)):
            return "0"
        try:
            return str(len(read_page_sections(self.project.images[index])))
        except (TypeError, ValueError, OSError, AttributeError):
            return "0"

    def _set_page_section_count(self, index: int, count: int) -> None:
        """Set a page's explicit SECTION count, preserving bounds when count is unchanged."""
        if not self.project or not (0 <= index < len(self.project.images)):
            return
        count = max(0, min(10, int(count)))
        page = self.project.images[index]
        existing = read_page_sections(page)

        if index == self.current_index and self.current_page == page and self.image is not None:
            image = self.image
            geometry = self._get_cached_display_geometry()
            effective_settings = effective_page_settings(self.settings, image.size, index)
        else:
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            effective_settings = effective_page_settings(self.settings, image.size, index)
            analysis_image = page_template_analysis_image(image, effective_settings, index)
            geometry = derive_geometry(analysis_image, effective_settings)

        if count == 0:
            sections: list[PageSection] = []
        elif len(existing) == count:
            sections = existing
        else:
            span = max(1, int(geometry.bottom) - int(geometry.top))
            bounds = [
                round(int(geometry.top) + span * item / count)
                for item in range(count + 1)
            ]
            sections = [
                PageSection(bounds[item], max(bounds[item] + 1, bounds[item + 1]))
                for item in range(count)
            ]

        transform = LayoutTransform(
            str(getattr(effective_settings, "layout_transform", "identity") or "identity")
        )
        canonical_width, canonical_height = transform.canonical_size(image.size)
        write_page_sections(
            page, sections,
            canonical_width=canonical_width,
            canonical_height=canonical_height,
            layout_transform=transform.kind,
        )
        iid = str(index)
        if hasattr(self, "page_list") and self.page_list.exists(iid):
            self.page_list.set(iid, "section", str(count))
            if self._page_list_sort_column == "section":
                self._schedule_page_list_resort()

        if index == self.current_index and self.current_page == page:
            self.page_sections = list(sections)
            self._sort_entries_reading_order()
            self._set_section_editing(count > 0)
            self.redraw()
            if count > 0:
                self.status_var.set(
                    f"SECTION 编辑：当前页 {count} 个；拖动虚线定位Section，双击左键确认并退出编辑。"
                )
            else:
                self.status_var.set("当前页 SECTION 已关闭（Section = 0）")
            return

        self._pending_section_editor_index = index if count > 0 else None
        self._request_page_load(index, force=True)

    def _page_list_section_double_click(self, event: tk.Event) -> str | None:
        """Edit the page-level Section count directly from the page list."""
        if self._preprocess_mode_active():
            self.status_var.set("预处理模式中：SECTION 编辑已锁定。")
            return "break"
        if self.page_list.identify_region(event.x, event.y) != "cell":
            return None
        if self._page_list_column_at(event.x) != "section":
            return None
        iid = self.page_list.identify_row(event.y)
        if not iid or not self.project:
            return "break"
        try:
            index = int(iid)
            page = self.project.images[index]
        except (TypeError, ValueError, IndexError):
            return "break"

        if index == self.current_index and self._section_editing:
            self._finish_section_editing()
            return "break"

        current_count = len(read_page_sections(page))
        count = simpledialog.askinteger(
            "Section",
            f"{page.name}\nSection 数量（0 = 关闭；1–10 = 启用）：\n\n"
            "确认后：拖动虚线定位Section，双击左键确认并退出编辑。",
            parent=self, initialvalue=current_count, minvalue=0, maxvalue=10,
        )
        if count is None:
            return "break"
        self._set_page_section_count(index, count)
        return "break"

    def _bookmark_stems(self) -> set[str]:
        settings = self.__dict__.get("settings")
        return {
            str(stem) for stem in getattr(settings, "page_bookmarks", [])
            if str(stem).strip()
        }

    def _page_list_bookmark_click(self, event: tk.Event) -> str | None:
        """Toggle only the bookmark cell; never swallow ordinary page clicks."""
        # This handler is bound to every left click on the Treeview. Determine
        # whether the click actually targets the bookmark column *before*
        # applying the preprocess read-only guard. Otherwise returning "break"
        # in preprocess mode suppresses Treeview selection on the 页面 column and
        # makes the page list appear frozen while analysis is running.
        if self.page_list.identify_region(event.x, event.y) != "cell":
            return None
        if self.page_list.identify_column(event.x) != "#1":
            return None
        if self._preprocess_mode_active():
            self.status_var.set("预处理模式中：仅保留页面浏览，不修改书签或其他项目数据。")
            return "break"
        iid = self.page_list.identify_row(event.y)
        if not iid or not self.project:
            return "break"
        try:
            index = int(iid)
            stem = self.project.images[index].stem
        except (TypeError, ValueError, IndexError):
            return "break"
        bookmarks = self._bookmark_stems()
        if stem in bookmarks:
            bookmarks.remove(stem)
        else:
            bookmarks.add(stem)
        self.settings.page_bookmarks = sorted(bookmarks, key=_natural_text_key)
        self.project.settings.page_bookmarks = list(self.settings.page_bookmarks)
        self.settings.to_json(settings_path(self.project.root))
        self._update_page_row(index)
        return "break"

    def jump_to_bookmark(self, direction: int) -> None:
        """Jump to the nearest bookmarked page before or after this page."""
        if not self.project or self.current_index < 0:
            return
        bookmarks = self._bookmark_stems()
        bookmarked = [
            index for index, page in enumerate(self.project.images)
            if page.stem in bookmarks
        ]
        candidates = (
            [index for index in bookmarked if index < self.current_index]
            if direction < 0 else
            [index for index in bookmarked if index > self.current_index]
        )
        if not candidates:
            self.status_var.set("当前页之前没有书签" if direction < 0 else "当前页之后没有书签")
            return
        self._request_page_load(max(candidates) if direction < 0 else min(candidates))

    def _center_page_list_iid(self, iid: str) -> None:
        """Place one page row as close as possible to the vertical viewport center."""
        try:
            children = tuple(self.page_list.get_children(""))
            if not children or iid not in children:
                return
            self.page_list.update_idletasks()
            first, last = self.page_list.yview()
            visible_fraction = max(0.0, min(1.0, float(last) - float(first)))
            if visible_fraction <= 0.0:
                return
            position = children.index(iid)
            row_center = (position + 0.5) / len(children)
            target = row_center - visible_fraction / 2.0
            max_start = max(0.0, 1.0 - visible_fraction)
            self.page_list.yview_moveto(max(0.0, min(max_start, target)))
            self._schedule_page_cell_overlay_refresh()
        except (AttributeError, ValueError, tk.TclError):
            return

    def _set_page_list_selection(self, index: int, *, ensure_visible: bool = True) -> None:
        """Synchronize the Treeview to exactly one page iid.

        Programmatic page changes must replace, not accumulate, Treeview
        selection.  A stale first selected iid can otherwise be replayed by a
        later ``<<TreeviewSelect>>`` callback after sorting.
        """
        if not hasattr(self, "page_list"):
            return
        iid = str(index)
        if not self.page_list.exists(iid):
            return
        selected = tuple(self.page_list.selection())
        stale = tuple(value for value in selected if value != iid)
        if stale:
            self.page_list.selection_remove(*stale)
        if iid not in selected:
            self.page_list.selection_set(iid)
        if self.page_list.focus() != iid:
            self.page_list.focus(iid)
        if ensure_visible:
            self.page_list.see(iid)
            self._center_page_list_iid(iid)

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
        for mapping_name in ("_page_lined_overlays", "_page_fill_status_overlays"):
            mapping = self.__dict__.get(mapping_name, {})
            for widget in mapping.values():
                try:
                    widget.destroy()
                except tk.TclError:
                    pass
            mapping.clear()

    def _visible_page_list_iids(self) -> list[str]:
        """Return only rows currently intersecting the Treeview viewport.

        Cell coloring uses child Labels because ttk.Treeview has no per-cell tag
        colors.  Scanning every page on every repaint is unnecessarily expensive;
        only visible rows can have an overlay, so walk forward from the first
        visible row and stop as soon as ``bbox`` leaves the viewport.
        """
        if not hasattr(self, "page_list"):
            return []
        try:
            height = max(1, int(self.page_list.winfo_height()))
            iid = self.page_list.identify_row(1)
            if not iid:
                iid = self.page_list.identify_row(min(height - 1, 20))
            if not iid:
                return []
            visible: list[str] = []
            while iid:
                bbox = self.page_list.bbox(iid)
                if not bbox:
                    break
                _x, y, _width, row_height = bbox
                if y >= height:
                    break
                if y + row_height > 0:
                    visible.append(str(iid))
                iid = self.page_list.next(iid)
            return visible
        except tk.TclError:
            return []

    def _refresh_lined_cell_overlays(self) -> None:
        """Paint semantic colors only for visible page-list cells.

        Tk/ttk Treeview tags color whole rows rather than individual cells, so
        child Labels are placed over the relevant cells.  v2.9.13 keeps the
        v2.9.12 color semantics but repaints only visible rows and coalesces
        callbacks, preventing large projects from stalling during list startup.
        """
        if not hasattr(self, "page_list"):
            return
        self._clear_lined_cell_overlays()
        visible_iids = self._visible_page_list_iids()
        if not visible_iids:
            return

        # Legacy quick warning: only mismatched line-count cells are pale red.
        for iid in visible_iids:
            try:
                index = int(iid)
            except (TypeError, ValueError):
                continue
            if index not in self._word_fill_mismatch_pages:
                continue
            bbox = self.page_list.bbox(iid, "lined")
            if not bbox:
                continue
            x, y, width, height = bbox
            text = str(self.page_list.set(iid, "lined"))
            label = tk.Label(
                self.page_list, text=text, bg="#f8d7da", fg="#6b1f25",
                bd=0, highlightthickness=0, anchor="w", padx=4, pady=0,
            )
            label.place(x=x, y=y, width=width, height=height)
            label.bind("<Button-1>", lambda _e, i=index: self._select_page_from_lined_overlay(i))
            label.bind("<MouseWheel>", self._list_mousewheel)
            self._page_lined_overlays[index] = label

        # The fill-status cell itself carries the semantic status color.
        if "_page_fill_status_overlays" not in self.__dict__:
            self._page_fill_status_overlays = {}
        if not self.project:
            return
        for iid in visible_iids:
            try:
                index = int(iid)
            except (TypeError, ValueError):
                continue
            status_text = str(self.page_list.set(iid, "fill_status") or "")
            style = _fill_status_cell_style(status_text)
            if style is None:
                continue
            bbox = self.page_list.bbox(iid, "fill_status")
            if not bbox:
                continue
            x, y, width, height = bbox
            bg, fg = style
            label = tk.Label(
                self.page_list, text=status_text, bg=bg, fg=fg,
                bd=0, highlightthickness=0, anchor="w", padx=4, pady=0,
            )
            label.place(x=x, y=y, width=width, height=height)
            label.bind("<Button-1>", lambda _e, i=index: self._select_page_from_lined_overlay(i))
            label.bind("<MouseWheel>", self._list_mousewheel)
            self._page_fill_status_overlays[index] = label
        self._apply_current_appearance(self.page_list)

    def _word_fill_status_path(self) -> Path | None:
        if not self.project:
            return None
        return word_fill_status_path(self.project.root)

    def _load_word_fill_status(self) -> None:
        """Restore persisted TXT-vs-line count checks for the current project."""
        self._word_fill_check_status = {}
        self._word_fill_mismatch_pages.clear()
        path = self._word_fill_status_path()
        if path is None or not path.exists() or not self.project:
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw_pages = payload.get("pages", {}) if isinstance(payload, dict) else {}
            if not isinstance(raw_pages, dict):
                return
            known = {page.stem: i for i, page in enumerate(self.project.images)}
            for stem, raw in raw_pages.items():
                if stem not in known or not isinstance(raw, dict):
                    continue
                try:
                    line_count = max(0, int(raw.get("line_count", 0)))
                    word_count = max(0, int(raw.get("word_count", 0)))
                except (TypeError, ValueError):
                    continue
                # v1 sidecars had only mismatch. Infer their state so old projects
                # open cleanly, while v2 sidecars retain stale/no-data states.
                state = str(raw.get("state", "")).strip().lower()
                if state not in {"match", "mismatch", "stale", "no_data"}:
                    state = "mismatch" if bool(raw.get("mismatch", line_count != word_count)) else "match"
                mismatch = state == "mismatch"
                item = {
                    "line_count": line_count,
                    "word_count": word_count,
                    "mismatch": mismatch,
                    "state": state,
                    "source": str(raw.get("source", "")),
                }
                self._word_fill_check_status[stem] = item
                if mismatch:
                    self._word_fill_mismatch_pages.add(known[stem])
        except Exception:
            # A damaged optional UI-status sidecar must never block opening the
            # dictionary itself. The next successful fill rewrites it.
            self._word_fill_check_status = {}
            self._word_fill_mismatch_pages.clear()

    def _persist_word_fill_status(self) -> None:
        """Atomically save persistent line-count comparison results."""
        path = self._word_fill_status_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 2, "pages": self._word_fill_check_status}
        temp = path.with_name(f".{path.name}.tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(temp, path)
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass

    def _word_fill_status_text(self, index: int) -> str:
        """Return the compact per-page text shown in the new fill-status column."""
        if not self.project or not (0 <= index < len(self.project.images)):
            return "未核对"
        stem = self.project.images[index].stem
        item = self.__dict__.get("_word_fill_check_status", {}).get(stem)
        if not item:
            return "未核对"
        state = str(item.get("state", "")).lower()
        if state == "no_data":
            return "无资料"
        if state == "stale":
            return "待重新核对"
        line_count = max(0, int(item.get("line_count", 0) or 0))
        word_count = max(0, int(item.get("word_count", 0) or 0))
        diff = line_count - word_count
        if diff == 0 and state != "mismatch":
            return "一致"
        if diff < 0:
            return f"少 {abs(diff)}"
        if diff > 0:
            return f"多 {diff}"
        return "一致"

    def _record_word_fill_check(
        self, index: int, line_count: int, word_count: int, *, source: str = "",
        has_data: bool = True, persist: bool = False, refresh_overlay: bool = True,
        refresh_row: bool = True,
    ) -> None:
        if not self.project or not (0 <= index < len(self.project.images)):
            return
        stem = self.project.images[index].stem
        line_count = max(0, int(line_count))
        word_count = max(0, int(word_count))
        state = "no_data" if not has_data else ("match" if line_count == word_count else "mismatch")
        mismatch = state == "mismatch"
        if "_word_fill_check_status" not in self.__dict__:
            self._word_fill_check_status = {}
        if "_word_fill_mismatch_pages" not in self.__dict__:
            self._word_fill_mismatch_pages = set()
        previous = self._word_fill_check_status.get(stem, {})
        self._word_fill_check_status[stem] = {
            "line_count": line_count,
            "word_count": word_count,
            "mismatch": mismatch,
            "state": state,
            "source": str(source or previous.get("source", "")),
        }
        if mismatch:
            self._word_fill_mismatch_pages.add(index)
        else:
            self._word_fill_mismatch_pages.discard(index)
        if persist:
            self._persist_word_fill_status()
        if refresh_row and "page_list" in self.__dict__:
            self._update_page_row(index)
        if refresh_overlay and "page_list" in self.__dict__:
            self._schedule_page_cell_overlay_refresh()

    def _refresh_word_fill_check_from_line_count(
        self, index: int, line_count: int, *, persist: bool = False,
    ) -> None:
        """Mark a prior fill check stale only when the number of lines changed.

        Editing OCR/headword text does not invalidate a count check. Adding or
        deleting a line does: the page then shows ``待重新核对`` until the user
        runs “填充词条” again.
        """
        if not self.project or not (0 <= index < len(self.project.images)):
            return
        stem = self.project.images[index].stem
        previous = self.__dict__.get("_word_fill_check_status", {}).get(stem)
        if not previous:
            return
        line_count = max(0, int(line_count))
        old_line_count = max(0, int(previous.get("line_count", 0) or 0))
        state = str(previous.get("state", "")).lower()
        # No source data remains no source data; changing PDIC lines cannot make
        # a page suddenly appear in the selected TXT.
        if state == "no_data":
            if line_count != old_line_count:
                previous["line_count"] = line_count
                if persist:
                    self._persist_word_fill_status()
                if "page_list" in self.__dict__:
                    self._update_page_row(index)
            return
        if line_count == old_line_count:
            return
        previous = dict(previous)
        previous["line_count"] = line_count
        previous["state"] = "stale"
        previous["mismatch"] = False
        self._word_fill_check_status[stem] = previous
        self._word_fill_mismatch_pages.discard(index)
        if persist:
            self._persist_word_fill_status()
        if "page_list" in self.__dict__:
            self._update_page_row(index)
        if "page_list" in self.__dict__:
            self._schedule_page_cell_overlay_refresh()

    def _clear_word_fill_checks_for_indices(self, indices, *, persist: bool = False) -> None:
        if not self.project:
            return
        if "_word_fill_check_status" not in self.__dict__:
            self._word_fill_check_status = {}
        if "_word_fill_mismatch_pages" not in self.__dict__:
            self._word_fill_mismatch_pages = set()
        changed = False
        changed_indices: list[int] = []
        for index in indices:
            if not (0 <= int(index) < len(self.project.images)):
                continue
            i = int(index)
            stem = self.project.images[i].stem
            if stem in self._word_fill_check_status:
                self._word_fill_check_status.pop(stem, None)
                changed = True
                changed_indices.append(i)
            if i in self._word_fill_mismatch_pages:
                self._word_fill_mismatch_pages.discard(i)
                changed = True
                if i not in changed_indices:
                    changed_indices.append(i)
        if changed and persist:
            self._persist_word_fill_status()
        if changed and "page_list" in self.__dict__:
            for i in changed_indices:
                self._update_page_row(i)
            self._schedule_page_cell_overlay_refresh()

    def _build_quick_settings(self, parent: ttk.Frame) -> None:
        self.quick_vars: dict[str, tk.Variable] = {}
        self.quick_pixel_vars: dict[str, tk.StringVar] = {}
        self._quick_geometry_edit_source: dict[str, str] = {}
        self.quick_bool_vars: dict[str, tk.BooleanVar] = {}
        self.quick_field_casts: dict[str, type] = {}
        self.quick_field_labels: dict[str, ttk.Label] = {}

        def add_field(
            panel: ttk.Frame, row: int, col: int, label: str, name: str, cast: type,
            width: int = 7,
        ) -> None:
            label_widget = ttk.Label(
                panel, text=label, style="PC.FieldLabel.TLabel"
            )
            label_widget.grid(
                row=row, column=col, sticky="e", padx=(0, 3), pady=1
            )
            self.quick_field_labels[name] = label_widget
            var = tk.StringVar(value=str(getattr(self.settings, name)))
            self.quick_vars[name] = var
            self.quick_field_casts[name] = cast
            if name in LAYOUT_PERCENT_AXES:
                value_frame = ttk.Frame(panel)
                value_frame.grid(
                    row=row, column=col + 1, sticky="ew", padx=(0, 6), pady=1
                )
                ttk.Entry(
                    value_frame,
                    textvariable=var,
                    width=max(5, width - 1),
                    justify="left",
                    style="PC.Compact.TEntry",
                ).pack(side="left")
                ttk.Label(value_frame, text="%").pack(side="left", padx=(2, 4))
                pixel_var = tk.StringVar(value=str(int(getattr(self.settings, name))))
                self.quick_pixel_vars[name] = pixel_var
                ttk.Spinbox(
                    value_frame,
                    from_=0,
                    to=100000,
                    increment=1,
                    width=6,
                    textvariable=pixel_var,
                ).pack(side="left")
                ttk.Label(value_frame, text="px").pack(side="left", padx=(2, 0))
            else:
                ttk.Entry(
                    panel,
                    textvariable=var,
                    width=width,
                    justify="left",
                    style="PC.Compact.TEntry",
                ).grid(row=row, column=col + 1, sticky="ew", padx=(0, 6), pady=1)

        preprocess = self._section_frame(
            parent, "图片预处理(前置)", padding=5, section_key="preprocess"
        )
        self.preprocess_panel = preprocess
        preprocess.pack(fill="x")
        preprocess.columnconfigure(0, weight=1)

        preprocess_mode_row = ttk.Frame(preprocess)
        preprocess_mode_row.grid(row=0, column=0, sticky="ew")
        self.preprocess_mode_button = ttk.Button(
            preprocess_mode_row,
            text="进入预处理模式",
            command=self.toggle_preprocess_mode,
            style="PC.Compact.TButton",
        )
        self.preprocess_mode_button.pack(side="left", fill="x", expand=True)
        ttk.Checkbutton(
            preprocess_mode_row,
            text="自动纠偏",
            variable=self.preprocess_auto_deskew_var,
            command=self._preprocess_settings_changed,
        ).pack(side="left", padx=(6, 0))
        ttk.Label(preprocess_mode_row, text="安全边界：").pack(side="left", padx=(8, 2))
        safety_spin = ttk.Spinbox(
            preprocess_mode_row,
            from_=0, to=500, increment=5, width=6,
            textvariable=self.preprocess_safety_var,
        )
        safety_spin.pack(side="left")
        ttk.Label(preprocess_mode_row, text="px").pack(side="left", padx=(2, 0))
        safety_spin.bind("<Return>", self._preprocess_settings_changed)
        safety_spin.bind("<FocusOut>", self._preprocess_settings_changed)

        preprocess_geometry_row = ttk.Frame(preprocess)
        preprocess_geometry_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Label(preprocess_geometry_row, text="几何纠正：").pack(side="left")
        geometry_combo = ttk.Combobox(
            preprocess_geometry_row,
            textvariable=self.preprocess_geometry_var,
            values=(
                "自动几何（推荐）",
                "轻量：旋转+裁边",
                "自动透视",
                "UVDoc展平（Paddle高级）",
            ),
            state="readonly",
            width=22,
        )
        geometry_combo.pack(side="left", fill="x", expand=True)
        geometry_combo.bind("<<ComboboxSelected>>", self._preprocess_settings_changed)
        manual_corner_button = ttk.Button(
            preprocess_geometry_row,
            text="手动四角",
            command=self.edit_preprocess_corners,
            style="PC.Compact.TButton",
        )
        manual_corner_button.pack(side="left", padx=(6, 0))
        reset_corner_button = ttk.Button(
            preprocess_geometry_row,
            text="重置四角",
            command=self.reset_preprocess_corners,
            style="PC.Compact.TButton",
        )
        reset_corner_button.pack(side="left", padx=(4, 0))
        self._attach_tooltip(
            manual_corner_button,
            "在原始整页图上拖动左上、右上、右下、左下四个控制点；手动四角优先于自动透视，也可在 UVDoc 前先做人工透视校正。",
        )
        self._attach_tooltip(
            reset_corner_button,
            "删除当前页的手动四角覆盖，恢复自动几何纠正。",
        )

        preprocess_action_row = ttk.Frame(preprocess)
        preprocess_action_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        for col in range(4):
            preprocess_action_row.columnconfigure(col, weight=1, uniform="preprocess-actions")
        for col, (text_value, command) in enumerate((
            ("分析所选范围", self.analyze_preprocess_selected),
            ("上一需检查", lambda: self.jump_preprocess_review(-1)),
            ("下一需检查", lambda: self.jump_preprocess_review(1)),
            ("诊断信息", self.show_preprocess_diagnostics),
        )):
            ttk.Button(
                preprocess_action_row, text=text_value, command=command,
                style="PC.Compact.TButton",
            ).grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 4, 0))

        preprocess_canvas_row = ttk.Frame(preprocess)
        preprocess_canvas_row.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        ttk.Checkbutton(
            preprocess_canvas_row,
            text="统一最终页面",
            variable=self.preprocess_export_canvas_var,
            command=self._preprocess_export_settings_changed,
        ).pack(side="left")
        canvas_mode_combo = ttk.Combobox(
            preprocess_canvas_row,
            textvariable=self.preprocess_export_canvas_mode_var,
            values=("本批最大裁剪尺寸", "自定义尺寸"),
            state="readonly",
            width=15,
        )
        canvas_mode_combo.pack(side="left", padx=(6, 0))
        canvas_mode_combo.bind(
            "<<ComboboxSelected>>", self._preprocess_export_settings_changed
        )
        ttk.Label(preprocess_canvas_row, text="页面宽×高：").pack(side="left", padx=(8, 2))
        canvas_width_spin = ttk.Spinbox(
            preprocess_canvas_row,
            from_=0, to=100000, increment=10, width=7,
            textvariable=self.preprocess_export_canvas_width_var,
        )
        canvas_width_spin.pack(side="left")
        ttk.Label(preprocess_canvas_row, text="×").pack(side="left", padx=2)
        canvas_height_spin = ttk.Spinbox(
            preprocess_canvas_row,
            from_=0, to=100000, increment=10, width=7,
            textvariable=self.preprocess_export_canvas_height_var,
        )
        canvas_height_spin.pack(side="left")
        for widget in (canvas_width_spin, canvas_height_spin):
            widget.bind("<Return>", self._preprocess_export_settings_changed)
            widget.bind("<FocusOut>", self._preprocess_export_settings_changed)

        preprocess_margin_row = ttk.Frame(preprocess)
        preprocess_margin_row.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        ttk.Label(preprocess_margin_row, text="页边空(px)：").pack(side="left")
        margin_widgets = []
        for label, variable in (
            ("上", self.preprocess_export_margin_top_var),
            ("左", self.preprocess_export_margin_left_var),
            ("下", self.preprocess_export_margin_bottom_var),
            ("右", self.preprocess_export_margin_right_var),
        ):
            ttk.Label(preprocess_margin_row, text=f"{label}：").pack(
                side="left", padx=(5, 1)
            )
            spin = ttk.Spinbox(
                preprocess_margin_row,
                from_=0, to=100000, increment=5, width=5,
                textvariable=variable,
            )
            spin.pack(side="left")
            margin_widgets.append(spin)
        for widget in margin_widgets:
            widget.bind("<Return>", self._preprocess_export_settings_changed)
            widget.bind("<FocusOut>", self._preprocess_export_settings_changed)

        preprocess_align_row = ttk.Frame(preprocess)
        preprocess_align_row.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        ttk.Label(preprocess_align_row, text="内容框排版 X：").pack(side="left")
        align_x_combo = ttk.Combobox(
            preprocess_align_row,
            textvariable=self.preprocess_export_align_x_var,
            values=("左对齐", "居中", "右对齐"),
            state="readonly",
            width=8,
        )
        align_x_combo.pack(side="left")
        align_x_combo.bind(
            "<<ComboboxSelected>>", self._preprocess_export_settings_changed
        )
        ttk.Label(preprocess_align_row, text="Y：").pack(side="left", padx=(8, 2))
        align_y_combo = ttk.Combobox(
            preprocess_align_row,
            textvariable=self.preprocess_export_align_y_var,
            values=("顶端对齐", "居中", "底部对齐"),
            state="readonly",
            width=8,
        )
        align_y_combo.pack(side="left")
        align_y_combo.bind(
            "<<ComboboxSelected>>", self._preprocess_export_settings_changed
        )
        ttk.Label(
            preprocess_align_row,
            text="内容框在版心内排版；不足部分填白",
            style="PC.FieldLabel.TLabel",
        ).pack(side="left", padx=(10, 0))

        preprocess_export_row = ttk.Frame(preprocess)
        preprocess_export_row.grid(row=6, column=0, sticky="ew", pady=(4, 0))
        for col in range(3):
            preprocess_export_row.columnconfigure(
                col, weight=1, uniform="preprocess-export"
            )
        ttk.Button(
            preprocess_export_row, text="导出检查小图",
            command=self.export_preprocess_previews,
            style="PC.Compact.TButton",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            preprocess_export_row, text="导出预处理图片",
            command=self.export_preprocess_images,
            style="PC.Compact.TButton",
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        promote_button = ttk.Button(
            preprocess_export_row, text="所选设为工作图片",
            command=self.promote_preprocessed_working_images,
            style="PC.Compact.TButton",
        )
        promote_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self._attach_tooltip(
            promote_button,
            "仅处理当前页面范围：所选页需已有 processed 导出。原扫描图"
            "逐批移动到 __before__，处理后图片以原文件名成为后续工作图片；"
            "未选页面保持不变，__before__ 中同名原图绝不覆盖。",
        )

        self._attach_tooltip(
            self.preprocess_mode_button,
            "进入后锁定画线/OCR/SECTION/后期制作，只保留预处理、翻页和缩放。原扫描图不会被覆盖。",
        )

        normal = self._section_frame(
            parent,
            "一、版面参数",
            padding=5,
            section_key="normal",
        )
        normal.pack(fill="x")
        add_field(normal, 0, 0, "正文栏数：", "columns", int)
        add_field(normal, 0, 2, "正文起始Y：", "start_y", float)
        add_field(normal, 0, 4, "首栏X：", "manual_x", float)
        add_field(normal, 1, 0, "单栏宽：", "column_width", float)
        add_field(normal, 1, 2, "栏间空：", "gutter", float)

        row = ttk.Frame(normal); row.grid(row=2, column=0, columnspan=8, sticky="ew", pady=(4, 0))
        detect_layout_button = ttk.Button(
            row, text="检测版面参数", command=self.detect_layout_current,
            style="PC.Compact.TButton",
        )
        detect_layout_button.pack(side="left", fill="x", expand=True)
        self._attach_tooltip(
            detect_layout_button,
            "若所选页面数量≥2，参数为稳健中位数",
        )
        consistency_button = ttk.Button(
            row, text="检测版面一致性", command=self.detect_layout_consistency_selected,
            style="PC.Compact.TButton",
        )
        consistency_button.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self._attach_tooltip(
            consistency_button,
            "快速扫描所选至少 2 页的页眉边界和正文左缘，生成一致性报告；不修改版面参数。",
        )
        ordinary_settings_button = ttk.Button(
            row, text="普通画线设置…",
            command=lambda: self.open_settings(initial_tab="normal"),
            style="PC.Compact.TButton",
        )
        ordinary_settings_button.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self._attach_tooltip(
            ordinary_settings_button,
            "打开普通画线的专属参数；融合模式会直接复用这些几何参数。",
        )
        for col in (1, 3, 5, 7): normal.columnconfigure(col, weight=1)

        aux = self._section_frame(parent, "二、显示设置", padding=5, section_key="aux")
        aux.pack(fill="x", pady=(4, 0))
        ruler_var = tk.BooleanVar(value=bool(self.settings.show_rulers))
        section_var = tk.BooleanVar(value=bool(self.settings.show_page_sections))
        guide_var = tk.BooleanVar(value=bool(self.settings.show_column_guides))
        marker_var = tk.BooleanVar(value=bool(self.settings.show_headword_markers))
        self.quick_bool_vars["show_rulers"] = ruler_var
        self.quick_bool_vars["show_page_sections"] = section_var
        self.quick_bool_vars["show_column_guides"] = guide_var
        self.quick_bool_vars["show_headword_markers"] = marker_var
        self.quick_color_buttons: dict[str, tk.Button] = {}
        self.quick_color_vars: dict[str, tk.StringVar] = {
            "ruler_color": tk.StringVar(value=self.settings.ruler_color),
            "page_section_color": tk.StringVar(value=self.settings.page_section_color),
            "guide_color": tk.StringVar(value=self.settings.guide_color),
            "headword_marker_color": tk.StringVar(value=self.settings.headword_marker_color),
            "illustration_outline_color": tk.StringVar(value=self.settings.illustration_outline_color),
            "illustration_fill_color": tk.StringVar(value=self.settings.illustration_fill_color),
            "illustration_label_border_color": tk.StringVar(value=self.settings.illustration_label_border_color),
            "illustration_label_fill_color": tk.StringVar(value=self.settings.illustration_label_fill_color),
            "main_entry_default_color": tk.StringVar(value=self.settings.main_entry_default_color),
        }

        def color_button(row: ttk.Frame, name: str) -> tk.Button:
            button = tk.Button(row, text="", width=2, padx=0, pady=0, bd=1, highlightthickness=0)
            button.configure(command=lambda n=name, b=button: self.choose_overlay_color(n, b))
            button.pack(side="left", padx=(2, 5), fill="y")
            self.quick_color_buttons[name] = button
            self._style_color_button(button, str(self.quick_color_vars[name].get()))
            color_tips = {
                "ruler_color": "选择标尺线和刻度数字颜色。",
                "page_section_color": "选择 SECTION 边界线颜色。",
                "guide_color": "选择栏左垂线颜色。",
                "headword_marker_color": "选择词头横线颜色。",
                "illustration_outline_color": "选择插图轮廓颜色。",
                "illustration_fill_color": "选择插图区域背景色。",
                "illustration_label_border_color": "选择插图标签外框颜色。",
                "illustration_label_fill_color": "选择插图标签背景色。",
                "main_entry_default_color": "选择主画布词条文本框默认背景色。",
            }
            self._attach_tooltip(button, color_tips.get(name, "点击选择颜色。"))
            return button

        section_row = ttk.Frame(aux); section_row.grid(row=0, column=0, columnspan=4, sticky="ew")
        ttk.Checkbutton(
            section_row, text="显示标尺", variable=ruler_var,
            command=lambda: self._apply_overlay_visibility_toggle("show_rulers", ruler_var),
        ).pack(side="left")
        color_button(section_row, "ruler_color")
        ttk.Checkbutton(
            section_row, text="显示Section", variable=section_var,
            command=lambda: self._apply_overlay_visibility_toggle("show_page_sections", section_var),
        ).pack(side="left", padx=(6, 0))
        color_button(section_row, "page_section_color")
        ttk.Label(section_row, text="粗细：").pack(side="left")
        section_width_var = tk.StringVar(value=str(self.settings.page_section_width))
        self.quick_vars["page_section_width"] = section_width_var
        self.quick_field_casts["page_section_width"] = int
        ttk.Entry(
            section_row, textvariable=section_width_var, width=4, justify="left"
        ).pack(side="left", padx=(2, 10))
        add_ocr_crop_preview_control(self, section_row)

        line_row = ttk.Frame(aux); line_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(2, 0))
        ttk.Checkbutton(line_row, text="栏左垂线", variable=guide_var, command=self._quick_parameter_changed).pack(side="left")
        color_button(line_row, "guide_color")
        ttk.Label(line_row, text="宽度：").pack(side="left")
        guide_value = tk.StringVar(value=str(self.settings.guide_width)); self.quick_vars["guide_width"] = guide_value; self.quick_field_casts["guide_width"] = int
        ttk.Entry(
            line_row, textvariable=guide_value, width=5, justify="left"
        ).pack(side="left", padx=(2, 10))
        add_quick_opacity_control(self, line_row, name="guide_opacity")
        ttk.Checkbutton(line_row, text="插图形状：轮廓", variable=self.polygon_var, command=self.redraw).pack(side="left")
        color_button(line_row, "illustration_outline_color")
        ttk.Label(line_row, text="粗细").pack(side="left")
        outline_width_var = tk.StringVar(value=str(self.settings.illustration_outline_width)); self.quick_vars["illustration_outline_width"] = outline_width_var; self.quick_field_casts["illustration_outline_width"] = int
        ttk.Entry(
            line_row, textvariable=outline_width_var, width=4, justify="left"
        ).pack(side="left", padx=(2, 5))
        ttk.Label(line_row, text="背景").pack(side="left")
        color_button(line_row, "illustration_fill_color")
        add_quick_illustration_fill_opacity_control(self, line_row)

        marker_row = ttk.Frame(aux); marker_row.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(2, 0))
        ttk.Checkbutton(marker_row, text="词头横线", variable=marker_var, command=self._quick_parameter_changed).pack(side="left")
        color_button(marker_row, "headword_marker_color")
        ttk.Label(marker_row, text="高度：").pack(side="left")
        marker_value = tk.StringVar(value=str(self.settings.marker_height)); self.quick_vars["marker_height"] = marker_value; self.quick_field_casts["marker_height"] = int
        ttk.Entry(
            marker_row, textvariable=marker_value, width=5, justify="left"
        ).pack(side="left", padx=(2, 10))
        add_quick_opacity_control(self, marker_row, name="headword_marker_opacity")
        label_visible_var = tk.BooleanVar(value=bool(self.settings.show_illustration_labels))
        self.quick_bool_vars["show_illustration_labels"] = label_visible_var
        ttk.Checkbutton(marker_row, text="显示插图标签", variable=label_visible_var, command=lambda: self._apply_overlay_visibility_toggle("show_illustration_labels", label_visible_var)).pack(side="left")
        color_button(marker_row, "illustration_label_border_color")
        ttk.Label(marker_row, text="粗细").pack(side="left")
        label_width_var = tk.StringVar(value=str(self.settings.illustration_label_border_width)); self.quick_vars["illustration_label_border_width"] = label_width_var; self.quick_field_casts["illustration_label_border_width"] = int
        ttk.Entry(
            marker_row, textvariable=label_width_var, width=4, justify="left"
        ).pack(side="left", padx=(2, 5))
        ttk.Label(marker_row, text="背景").pack(side="left")
        color_button(marker_row, "illustration_label_fill_color")

        entry_row = ttk.Frame(aux); entry_row.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(2, 0))
        ttk.Label(entry_row, text="词条文本框：宽度(字符)").pack(side="left")
        for name, width in (("main_entry_width_chars", 5), ("main_entry_x_ratio", 5)):
            shown = getattr(self.settings, name) * 100 if name == "main_entry_x_ratio" else getattr(self.settings, name)
            var = tk.StringVar(value=str(round(shown) if name == "main_entry_x_ratio" else shown)); self.quick_vars[name] = var; self.quick_field_casts[name] = int if name.endswith("chars") else float
            if name == "main_entry_x_ratio": ttk.Label(entry_row, text="偏移%").pack(side="left", padx=(8, 2))
            ttk.Entry(
                entry_row, textvariable=var, width=width, justify="left"
            ).pack(side="left")
        follow_var = tk.BooleanVar(value=bool(self.settings.main_entry_follow_zoom)); self.quick_bool_vars["main_entry_follow_zoom"] = follow_var
        ttk.Checkbutton(entry_row, text="跟随缩放", variable=follow_var).pack(side="left", padx=(8, 0))
        ttk.Label(entry_row, text="默认").pack(side="left", padx=(8, 0))
        color_button(entry_row, "main_entry_default_color")

        font_row = ttk.Frame(aux); font_row.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(2, 0))
        ttk.Label(font_row, text="词条字体").pack(side="left")
        family_var = tk.StringVar(value=normalize_content_font_setting(self.settings.main_entry_font_family)); self.quick_vars["main_entry_font_family"] = family_var; self.quick_field_casts["main_entry_font_family"] = str
        content_font_values = (AUTO_FONT_FAMILY, *tuple(sorted(set(font.families()), key=str.casefold)))
        ttk.Combobox(font_row, textvariable=family_var, values=content_font_values, width=18).pack(side="left")
        ttk.Label(font_row, text="字号").pack(side="left", padx=(8, 2))
        size_var = tk.StringVar(value=str(self.settings.main_entry_font_size)); self.quick_vars["main_entry_font_size"] = size_var; self.quick_field_casts["main_entry_font_size"] = int
        ttk.Entry(
            font_row, textvariable=size_var, width=5, justify="left"
        ).pack(side="left")
        for label, name in (("粗体", "main_entry_font_bold"), ("斜体", "main_entry_font_italic")):
            var = tk.BooleanVar(value=bool(getattr(self.settings, name))); self.quick_bool_vars[name] = var
            ttk.Checkbutton(font_row, text=label, variable=var).pack(side="left", padx=(7, 0))

        label_font_row = ttk.Frame(aux); label_font_row.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(2, 0))
        ttk.Label(label_font_row, text="标签字体").pack(side="left")
        label_family_var = tk.StringVar(value=normalize_content_font_setting(self.settings.illustration_label_font_family)); self.quick_vars["illustration_label_font_family"] = label_family_var; self.quick_field_casts["illustration_label_font_family"] = str
        ttk.Combobox(label_font_row, textvariable=label_family_var, values=content_font_values, width=18).pack(side="left")
        ttk.Label(label_font_row, text="字号").pack(side="left", padx=(8, 2))
        label_size_var = tk.StringVar(value=str(self.settings.illustration_label_font_size)); self.quick_vars["illustration_label_font_size"] = label_size_var; self.quick_field_casts["illustration_label_font_size"] = int
        ttk.Entry(
            label_font_row, textvariable=label_size_var, width=5, justify="left"
        ).pack(side="left")
        for label, name in (("粗体", "illustration_label_font_bold"), ("斜体", "illustration_label_font_italic")):
            var = tk.BooleanVar(value=bool(getattr(self.settings, name))); self.quick_bool_vars[name] = var
            ttk.Checkbutton(label_font_row, text=label, variable=var).pack(side="left", padx=(7, 0))

        from .crop_preview_display_settings import add_crop_preview_font_controls
        add_crop_preview_font_controls(self, aux, content_font_values, normalize_content_font_setting)

        ocr_display_row = ttk.Frame(aux); ocr_display_row.grid(row=6, column=0, columnspan=4, sticky="ew")
        for label, name in (("显示OCR内容选择", "review_main_show_ocr_choices"), ("显示OCR对比底色结果", "review_main_show_ocr_background")):
            var = tk.BooleanVar(value=bool(getattr(self.settings, name))); self.quick_bool_vars[name] = var
            ttk.Checkbutton(
                ocr_display_row, text=label, variable=var,
                command=lambda n=name, v=var: self._apply_overlay_visibility_toggle(n, v),
            ).pack(side="left", padx=(0, 8))

        candidate_var = tk.BooleanVar(value=bool(self.settings.paddle_show_candidate_checkboxes)); self.quick_bool_vars["paddle_show_candidate_checkboxes"] = candidate_var
        ttk.Checkbutton(
            ocr_display_row, text="显示单行候选框", variable=candidate_var,
            command=lambda: self._apply_overlay_visibility_toggle(
                "paddle_show_candidate_checkboxes", candidate_var,
            ),
        ).pack(side="left", padx=(0, 8))

        option_row = ttk.Frame(aux); option_row.grid(row=7, column=0, columnspan=4, sticky="ew")
        ttk.Checkbutton(
            option_row, text="隐藏线框(插图除外)", variable=self.hide_var,
            command=self._toggle_hide_overlays,
        ).pack(side="left")
        ttk.Label(option_row, text="显示模式：").pack(side="left", padx=(10, 2))
        display_mode_combo = ttk.Combobox(
            option_row,
            textvariable=self.display_mode_var,
            values=("原图+标注", "二值+标注", "仅原图", "仅二值", "切图预览"),
            state="readonly",
            width=10,
        )
        display_mode_combo.pack(side="left", padx=(0, 8))
        display_mode_combo.bind("<<ComboboxSelected>>", self._apply_display_mode)
        ttk.Label(option_row, text="颜色模式：").pack(side="left")
        appearance_combo = ttk.Combobox(
            option_row, textvariable=self.appearance_mode_var,
            values=tuple(APPEARANCE_MODE_VALUES), state="readonly", width=8,
        )
        appearance_combo.pack(side="left")
        appearance_combo.bind("<<ComboboxSelected>>", self._appearance_mode_selected)
        self._attach_tooltip(
            appearance_combo,
            "浅色=正常界面；深色=夜间界面；跟随系统=自动响应 Windows/macOS/Linux 的系统颜色模式。",
        )
        save_row = ttk.Frame(aux); save_row.grid(row=8, column=0, columnspan=4, sticky="ew")
        ttk.Checkbutton(save_row, text="自动保存", variable=self.autosave_var, command=self.toggle_autosave).pack(side="left")
        ttk.Label(save_row, text="间隔时间(秒)").pack(side="left", padx=(8, 2))
        interval_var = tk.StringVar(value=str(self.settings.batch_interval)); self.quick_vars["batch_interval"] = interval_var; self.quick_field_casts["batch_interval"] = float
        ttk.Entry(
            save_row, textvariable=interval_var, width=6, justify="left"
        ).pack(side="left")
        ttk.Label(save_row, text="向右比例%").pack(side="left", padx=(10, 2))
        ratio_var = tk.StringVar(value=str(self.settings.right_ratio)); self.quick_vars["right_ratio"] = ratio_var; self.quick_field_casts["right_ratio"] = float
        ttk.Entry(
            save_row, textvariable=ratio_var, width=6, justify="left"
        ).pack(side="left")

        aux.columnconfigure(1, weight=1); aux.columnconfigure(3, weight=1)
        add_layout_visualization_controls(self, aux)

        ocr = self._section_frame(parent, "三、共享 OCR 通道 / OCR画线", padding=5, section_key="ocr")
        ocr.pack(fill="x", pady=(4, 0))
        self.ocr_refresh_var = tk.StringVar(value="reuse")
        ttk.Label(ocr, text="识别策略：").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            ocr, text="使用有效缓存（推荐）",
            variable=self.ocr_refresh_var, value="reuse",
        ).grid(row=0, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(
            ocr, text="重新OCR（模型/图像改变时）",
            variable=self.ocr_refresh_var, value="force",
        ).grid(row=0, column=3, columnspan=3, sticky="w")
        add_field(ocr, 1, 0, "OCR语言：", "ocr_language", str, 8)
        add_field(ocr, 1, 2, "识别带宽%：", "paddle_band_width_ratio", float, 7)
        add_field(ocr, 1, 4, "左缘容差：", "paddle_left_tolerance", int, 7)
        engine_row = ttk.Frame(ocr); engine_row.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(4, 1))
        ttk.Label(engine_row, text="OCR引擎：").pack(side="left")
        for text, name in (("PaddleOCR", "paddle_use_paddleocr"), ("Tesseract", "paddle_compare_tesseract"), ("Google Lens", "paddle_enable_lens")):
            var = tk.BooleanVar(value=bool(getattr(self.settings, name))); self.quick_bool_vars[name] = var
            ttk.Checkbutton(engine_row, text=text, variable=var).pack(side="left", padx=(0, 5))
        self.lens_mode_var = tk.StringVar(
            value=LENS_MODE_LABELS.get(self.settings.paddle_lens_mode, LENS_MODE_LABELS["off"])
        )
        lens_row = ttk.Frame(ocr); lens_row.grid(row=3, column=0, columnspan=6, sticky="ew")
        ttk.Label(lens_row, text="Lens模式：").pack(side="left")
        ttk.Combobox(
            lens_row, textvariable=self.lens_mode_var, values=tuple(LENS_MODE_VALUES),
            state="readonly", width=34,
        ).pack(side="left", fill="x", expand=True)
        ttk.Label(lens_row, text="  Y安全空间：").pack(side="left")
        safety_var = tk.StringVar(value=str(self.settings.paddle_separator_safety_px))
        self.quick_vars["paddle_separator_safety_px"] = safety_var
        self.quick_field_casts["paddle_separator_safety_px"] = int
        ttk.Entry(
            lens_row, textvariable=safety_var, width=4, justify="left"
        ).pack(side="left", padx=(2, 2))
        ttk.Label(lens_row, text="px").pack(side="left")
        ocr_tools = ttk.Frame(ocr)
        ocr_tools.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(4, 0))
        environment_button = ttk.Button(
            ocr_tools, text="环境中心", command=self.check_ocr_engines,
            style="PC.Compact.TButton",
        )
        environment_button.pack(side="left", fill="x", expand=True)
        self._attach_tooltip(
            environment_button,
            "检查 PaddleOCR / PaddlePaddle、Tesseract、Lens、OpenCC 等运行环境。",
        )
        ocr_settings_button = ttk.Button(
            ocr_tools, text="OCR画线设置…",
            command=lambda: self.open_settings(initial_tab="ocr"),
            style="PC.Compact.TButton",
        )
        ocr_settings_button.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self._attach_tooltip(
            ocr_settings_button,
            "打开 OCR画线参数和高级候选规则；建议先在代表页确认具体错误模式。",
        )
        for col in (1, 3, 5): ocr.columnconfigure(col, weight=1)

        actions = self._section_frame(
            parent, "四、画线 / OCR / 插图 / 校对",
            padding=5, section_key="actions",
        )
        actions.pack(fill="x", pady=(4, 0))
        action_tooltips = {
            "普通画线": "只运行高速左缘几何画线；适合正文缩进稳定的词典，不调用 OCR 来决定词条位置。",
            "仅OCR": "只对已有画线调用共享 OCR 通道做局部文字识别；普通行与大字行使用不同高度框，不新增、删除或移动画线，默认仅填空白词条。",
            "融合画线+OCR": "普通几何与 OCR 候选先融合、救漏和去重，再对仍为空白的普通救漏线自动做局部 OCR 补字。",
            "OCR画线(默认)": "默认画线方式：由 OCR / parser / 视觉候选链识别词头并确定画线，同时得到 OCR 文字。",
            "清除画线": "清除当前页全部词条画线；不会删除扫描图片。",
            "清除文本": "清空当前页画线中的词条文字，但保留画线位置。",
            "精修画线": "仅在所选范围微调已有画线的 Y 位置，不新增或删除词条。",
            "新旧比较": "比较所选范围当前 PDIC 与页码-词条文本，定位新增、缺失或顺序差异。",
            "词条校对": "打开连续校对窗口，结合扫描图、OCR候选、简体和参考词表逐条核对。",
            "选择词条文件": "选择带页码的既有词条 TXT，供后续【填充词条】重复使用。",
            "填充词条": "按当前页面范围，用已选页码词条文件填充对应 PDIC 词条文本。",
            "修复排序": "按栏号 → Y 修复所选范围 PDIC 记录顺序；不重新 OCR、不改变词条坐标配对。",
            "备份PDIC": "将项目现有 PDIC 汇总为时间戳备份，适合批量修改前留档。",
            "恢复PDIC": "从备份文本覆盖恢复主界面所选范围的 PDIC；执行前请确认页面范围。",
            "插图识别": "在所选页面范围自动识别插图并写入 PPP；人工多边形会保留。",
            "编辑插图": "进入/退出插图多边形编辑模式，可新增、移动顶点并修改标签。",
            "压缩OCR缓存": "压缩当前页面范围的 PaddleOCR 缓存并删除可再生诊断副本；保留可复用 OCR 原始记录和人工选择，不需要重新 OCR。",
            "保存当前页": "立即保存当前页的画线/词条或插图编辑结果。",
        }
        rows = [
            (
                ("普通画线", self.run_normal_draw_action),
                ("仅OCR", self.ocr_ordinary_lines_text_selected_scope),
                ("融合画线+OCR", self.run_combined_draw_action),
                ("OCR画线(默认)", self.run_ocr_draw_action),
            ),
            (("清除画线", self.clear_entries), ("清除文本", self.clear_text), ("精修画线", self.refine_lines_selected_scope), ("新旧比较", self.compare_old_new_selected_scope), ("词条校对", self.open_review)),
            (("选择词条文件", self.select_existing_headwords_file), ("填充词条", self.fill_existing_headwords), ("修复排序", self.repair_pdic_order_selected_scope), ("备份PDIC", self.backup_pdic), ("恢复PDIC", self.restore_from_pdic_backup)),
            (
                ("插图识别", self.detect_illustrations_selected_scope),
                ("编辑插图", self.toggle_polygon_drawing),
                ("压缩OCR缓存", self.cleanup_paddleocr_temp_selected_scope),
                ("保存当前页", self.save_current_page),
            ),
        ]
        for ri, specs in enumerate(rows):
            row = ttk.Frame(actions)
            row.grid(row=ri, column=0, sticky="ew", pady=(0 if ri == 0 else 3, 0))
            for bi in range(len(specs)):
                row.columnconfigure(bi, weight=1, uniform=f"actions-row-{ri}")
            for bi, (text, command) in enumerate(specs):
                role = (
                    "primary" if text == "OCR画线(默认)"
                    else "success" if text == "保存当前页"
                    else "primary" if text == "词条校对"
                    else "neutral"
                )
                button = self._sidebar_action_button(row, text, command, role=role)
                tooltip = action_tooltips.get(text)
                if tooltip:
                    self._attach_tooltip(button, tooltip)
                if text == "编辑插图":
                    self.polygon_draw_button = button
                button.grid(
                    row=0, column=bi, sticky="ew",
                    padx=(0 if bi == 0 else 4, 0),
                )
        actions.columnconfigure(0, weight=1)
        aux_row = ttk.Frame(actions)
        aux_row.grid(row=len(rows), column=0, sticky="w", pady=3)
        ttk.Checkbutton(aux_row, text="辅助线模式", variable=self.auxiliary_mode_var,
                        command=self.toggle_auxiliary_mode).pack(side="left")
        ttk.Button(aux_row, text="撤销辅助线",
                   command=self._auxiliary_controller.undo).pack(side="left", padx=8)

        postproduction = self._section_frame(
            parent, "五、后期词典制作", padding=5, section_key="postproduction"
        )
        postproduction.pack(fill="x", pady=(4, 0))
        production_tooltips = {
            "单行切图": (
                "将【选定范围】内各页按校对界面相同的单行裁切逻辑批量输出到 QT/PSW；"
                "可在【设置中心 → 切图】选择是否按页合并，并复用切图并行进程数。"
            ),
            "未画线行导出": (
                "将【选定范围】内 Layout 已恢复、但当前 PDIC 没有横线的文字行导出到 QT/PSW_UNLINED。"
                "可在【设置中心 → 切图】启用【未画线行导出过滤 → 空白】只检查近空白候选；"
                "不以 entry/body 角色决定是否导出，并复用按页合并和切图并行进程设置。"
            ),
            "词条切图": "按所选页面范围和【设置中心 → 切图】生成完整词条切图。",
            "插图切图": "按所选范围导出需要独立输出的 PPP 插图。",
            "项目详情": "编辑词典名称、语言、正文页码范围等项目级元数据。",
            "导出PicDic索引": "从项目已保存 PDIC 导出“词条 / X% / Y% / 页码”文本索引。",
            "PicDic制作": "使用已生成的词条切图制作 PicDic DSL 与图片包。",
            "导出训练标记包": "导出已人工确认的 PDIC/PPP、OCR候选和坐标上下文，供模型或规则验证。",
        }
        production_rows = [
            (("单行切图", self.split_single_lines_selected_scope), ("未画线行导出", self.export_unlined_rows_selected_scope), ("词条切图", self.split_entries_selected_scope), ("插图切图", self.split_illustrations_selected_scope)),
            (("项目详情", self.open_project_details), ("导出PicDic索引", self.export_picdic_index), ("PicDic制作", self.build_picdic)),
            (("导出训练标记包", self.export_training_package),),
        ]
        for ri, specs in enumerate(production_rows):
            row = ttk.Frame(postproduction)
            row.grid(row=ri, column=0, sticky="ew", pady=(0 if ri == 0 else 3, 0))
            for bi in range(len(specs)):
                row.columnconfigure(bi, weight=1, uniform=f"postproduction-row-{ri}")
            for bi, (text, command) in enumerate(specs):
                button = self._sidebar_action_button(row, text, command)
                if text == "单行切图":
                    self._pc_single_line_crop_button = button
                elif text == "未画线行导出":
                    self._pc_unlined_export_button = button
                tooltip = production_tooltips.get(text)
                if tooltip:
                    self._attach_tooltip(button, tooltip)
                button.grid(
                    row=0, column=bi, sticky="ew",
                    padx=(0 if bi == 0 else 4, 0),
                )
        postproduction.columnconfigure(0, weight=1)

        # Main-panel parameters are live: after a short debounce, valid values
        # are applied and persisted without requiring a separate Apply step.
        for _name, _var in self.quick_vars.items():
            try:
                if _name in self.quick_pixel_vars:
                    _var.trace_add(
                        "write",
                        lambda *_args, n=_name: self._quick_percent_parameter_changed(n),
                    )
                else:
                    _var.trace_add("write", lambda *_args: self._quick_parameter_changed())
            except Exception:
                pass
        for _name, _var in self.quick_pixel_vars.items():
            try:
                _var.trace_add(
                    "write",
                    lambda *_args, n=_name: self._quick_pixel_parameter_changed(n),
                )
            except Exception:
                pass
        for _var in self.quick_bool_vars.values():
            try:
                _var.trace_add("write", lambda *_args: self._quick_parameter_changed())
            except Exception:
                pass
        self.lens_mode_var.trace_add("write", lambda *_args: self._quick_parameter_changed())
        self._quick_trace_ready = True

    def _preprocess_mode_active(self) -> bool:
        return bool(
            hasattr(self, "preprocess_mode_var") and self.preprocess_mode_var.get()
        )

    def _preprocess_config(self) -> tuple[int, bool, str]:
        try:
            safety = int(round(float(str(self.preprocess_safety_var.get()).strip())))
        except (TypeError, ValueError):
            safety = int(getattr(self.settings, "preprocess_safety_margin_px", 20))
        safety = max(0, min(500, safety))
        geometry_label = str(self.preprocess_geometry_var.get() or "").strip()
        geometry_mode = {
            "自动几何（推荐）": "auto",
            "轻量：旋转+裁边": "deskew",
            "自动透视": "perspective",
            "UVDoc展平（Paddle高级）": "uvdoc",
        }.get(geometry_label, "auto")
        return safety, bool(self.preprocess_auto_deskew_var.get()), geometry_mode

    def _preprocess_export_config(
        self,
    ) -> tuple[bool, str, int, int, int, int, int, int, str, str]:
        enabled = bool(self.preprocess_export_canvas_var.get())
        mode_label = str(self.preprocess_export_canvas_mode_var.get() or "").strip()
        mode = {
            "本批最大裁剪尺寸": "batch_max",
            "自定义尺寸": "custom",
        }.get(mode_label, "batch_max")

        def bounded_int(variable, setting_name: str) -> int:
            try:
                value = int(round(float(str(variable.get()).strip())))
            except (TypeError, ValueError):
                value = int(getattr(self.settings, setting_name, 0) or 0)
            return max(0, min(100000, value))

        width = bounded_int(
            self.preprocess_export_canvas_width_var,
            "preprocess_export_canvas_width",
        )
        height = bounded_int(
            self.preprocess_export_canvas_height_var,
            "preprocess_export_canvas_height",
        )
        margin_top = bounded_int(
            self.preprocess_export_margin_top_var,
            "preprocess_export_margin_top",
        )
        margin_bottom = bounded_int(
            self.preprocess_export_margin_bottom_var,
            "preprocess_export_margin_bottom",
        )
        margin_left = bounded_int(
            self.preprocess_export_margin_left_var,
            "preprocess_export_margin_left",
        )
        margin_right = bounded_int(
            self.preprocess_export_margin_right_var,
            "preprocess_export_margin_right",
        )
        align_x = {
            "左对齐": "left",
            "居中": "center",
            "右对齐": "right",
        }.get(str(self.preprocess_export_align_x_var.get() or "").strip(), "center")
        align_y = {
            "顶端对齐": "top",
            "居中": "center",
            "底部对齐": "bottom",
        }.get(str(self.preprocess_export_align_y_var.get() or "").strip(), "top")
        return (
            enabled, mode, width, height,
            margin_top, margin_bottom, margin_left, margin_right,
            align_x, align_y,
        )

    def _preprocess_export_settings_changed(self, _event=None) -> None:
        (
            enabled, mode, width, height,
            margin_top, margin_bottom, margin_left, margin_right,
            align_x, align_y,
        ) = self._preprocess_export_config()
        self.preprocess_export_canvas_width_var.set(str(width))
        self.preprocess_export_canvas_height_var.set(str(height))
        self.preprocess_export_margin_top_var.set(str(margin_top))
        self.preprocess_export_margin_bottom_var.set(str(margin_bottom))
        self.preprocess_export_margin_left_var.set(str(margin_left))
        self.preprocess_export_margin_right_var.set(str(margin_right))
        self.settings.preprocess_export_canvas_enabled = enabled
        self.settings.preprocess_export_canvas_mode = mode
        self.settings.preprocess_export_canvas_width = width
        self.settings.preprocess_export_canvas_height = height
        self.settings.preprocess_export_margin_top = margin_top
        self.settings.preprocess_export_margin_bottom = margin_bottom
        self.settings.preprocess_export_margin_left = margin_left
        self.settings.preprocess_export_margin_right = margin_right
        self.settings.preprocess_export_align_x = align_x
        self.settings.preprocess_export_align_y = align_y
        if self.project is not None:
            self.project.settings.preprocess_export_canvas_enabled = enabled
            self.project.settings.preprocess_export_canvas_mode = mode
            self.project.settings.preprocess_export_canvas_width = width
            self.project.settings.preprocess_export_canvas_height = height
            self.project.settings.preprocess_export_margin_top = margin_top
            self.project.settings.preprocess_export_margin_bottom = margin_bottom
            self.project.settings.preprocess_export_margin_left = margin_left
            self.project.settings.preprocess_export_margin_right = margin_right
            self.project.settings.preprocess_export_align_x = align_x
            self.project.settings.preprocess_export_align_y = align_y
            try:
                self.settings.to_json(settings_path(self.project.root))
            except OSError:
                pass
        if self._preprocess_mode_active():
            self._set_current_preprocess_status(
                self._preprocess_result_for_page(self.current_index)
            )

    def _preprocess_settings_changed(self, _event=None) -> None:
        safety, auto_deskew, geometry_mode = self._preprocess_config()
        self.preprocess_safety_var.set(str(safety))
        self.settings.preprocess_safety_margin_px = safety
        self.settings.preprocess_auto_deskew = auto_deskew
        self.settings.preprocess_geometry_mode = geometry_mode
        if self.project is not None:
            self.project.settings.preprocess_safety_margin_px = safety
            self.project.settings.preprocess_auto_deskew = auto_deskew
            self.project.settings.preprocess_geometry_mode = geometry_mode
            try:
                self.settings.to_json(settings_path(self.project.root))
            except OSError:
                pass
        self._preprocess_photo = None
        self._preprocess_photo_cache_key = None
        if self._preprocess_mode_active() and self.project and self.current_page:
            self.preprocess_status_var.set("预处理参数已改变；当前页结果需要重新分析。")
            self.analyze_preprocess_current(silent=True)

    def _set_workspace_preprocess_locked(self, locked: bool) -> None:
        """Disable ordinary-edit controls while preserving page navigation."""
        section_keys = ("normal", "aux", "ocr", "actions", "postproduction")
        if locked:
            if self._preprocess_locked_widgets:
                return
            for key in section_keys:
                section = self._collapsible_sections.get(key)
                if section is None:
                    continue
                stack = list(section.winfo_children())
                while stack:
                    widget = stack.pop()
                    try:
                        stack.extend(widget.winfo_children())
                    except tk.TclError:
                        pass
                    if isinstance(widget, ttk.Widget):
                        try:
                            was_disabled = "disabled" in widget.state()
                            widget.state(["disabled"])
                            self._preprocess_locked_widgets.append((widget, was_disabled))
                        except tk.TclError:
                            pass
                    else:
                        try:
                            if "state" in widget.keys():
                                old_state = widget.cget("state")
                                widget.configure(state="disabled")
                                self._preprocess_locked_widgets.append((widget, old_state))
                        except tk.TclError:
                            pass
            for widget in getattr(self, "project_footer_buttons", ()):
                try:
                    was_disabled = "disabled" in widget.state()
                    widget.state(["disabled"])
                    self._preprocess_locked_widgets.append((widget, was_disabled))
                except tk.TclError:
                    pass
            return

        remembered = self._preprocess_locked_widgets
        self._preprocess_locked_widgets = []
        for widget, previous in remembered:
            try:
                if isinstance(widget, ttk.Widget):
                    widget.state(["disabled" if bool(previous) else "!disabled"])
                else:
                    widget.configure(state=previous)
            except tk.TclError:
                pass

    def _preprocess_blocking_window_name(self) -> str | None:
        candidates = (
            ("review_window", "词条校对"),
            ("ocr_review_window", "OCR词头冲突复核"),
            ("old_new_compare_window", "新旧比较"),
            ("_settings_dialog", "设置中心"),
            ("_project_profile_wizard", "项目Profile"),
        )
        for attr, label in candidates:
            window = self.__dict__.get(attr)
            if window is None:
                continue
            try:
                if window.winfo_exists():
                    return label
            except tk.TclError:
                continue
        return None

    def toggle_preprocess_mode(self) -> None:
        self._set_preprocess_mode(not self._preprocess_mode_active())

    def _set_preprocess_mode(self, active: bool, *, analyze: bool = True) -> None:
        active = bool(active)
        if active and (not self.project or self.current_page is None or self.image is None):
            self.preprocess_mode_var.set(False)
            messagebox.showinfo(
                "图片预处理", "请先打开包含扫描图片的项目目录。", parent=self,
            )
            return
        if active:
            blocker = self._preprocess_blocking_window_name()
            if blocker is not None:
                self.preprocess_mode_var.set(False)
                messagebox.showinfo(
                    "图片预处理",
                    f"请先关闭【{blocker}】，再进入预处理模式。\n\n"
                    "预处理模式不会与其他可修改项目数据的窗口并行运行。",
                    parent=self,
                )
                return
        if active and self._batch_active:
            self.preprocess_mode_var.set(False)
            self.status_var.set("当前批量任务运行中；结束后再进入预处理模式。")
            return

        self.preprocess_mode_var.set(active)
        if self.preprocess_mode_button is not None:
            self.preprocess_mode_button.configure(
                text="退出预处理模式" if active else "进入预处理模式"
            )
        if active:
            self._section_editing = False
            self._drag_section_boundary = None
            self.polygon_draw_var.set(False)
            self.new_polygon.clear()
            self._set_workspace_preprocess_locked(True)
            section = self._collapsible_sections.get("preprocess")
            if section is not None:
                self._set_section_expanded(section, True)
            self.status_var.set(
                "已进入预处理模式：几何纠正后重新检测版面并裁边；画线、OCR、SECTION 和后期制作已锁定。"
            )
            self.redraw()
            if analyze:
                self.analyze_preprocess_current(silent=True)
        else:
            self._invalidate_ui_worker("preprocess-current")
            self._set_workspace_preprocess_locked(False)
            self._preprocess_photo = None
            self._preprocess_photo_cache_key = None
            self.preprocess_status_var.set("未进入预处理模式")
            if self.image is not None:
                self.redraw()
            self.status_var.set("已退出预处理模式，恢复普通编辑功能。")

    @staticmethod
    def _default_preprocess_corner_quad(image: Image.Image) -> tuple[float, ...]:
        width, height = image.size
        inset = max(4, round(min(width, height) * 0.012))
        return (
            float(inset), float(inset),
            float(max(inset + 1, width - 1 - inset)), float(inset),
            float(max(inset + 1, width - 1 - inset)),
            float(max(inset + 1, height - 1 - inset)),
            float(inset), float(max(inset + 1, height - 1 - inset)),
        )

    def edit_preprocess_corners(self) -> None:
        if not self.project or self.current_page is None or self.image is None:
            messagebox.showinfo("手动四角", "请先打开包含扫描图片的项目。", parent=self)
            return
        if self._ui_worker_key_active("preprocess-current") or self._batch_active:
            self.status_var.set("预处理任务正在运行；完成后再编辑手动四角。")
            return
        if not self._preprocess_mode_active():
            self._set_preprocess_mode(True, analyze=False)
            if not self._preprocess_mode_active():
                return

        project = self.project
        page = self.current_page
        source = normalize_page_rgb(self.image)
        existing = load_manual_perspective_quad(project.root, page)
        initial = existing or self._default_preprocess_corner_quad(source)
        points = [
            [float(initial[index]), float(initial[index + 1])]
            for index in range(0, 8, 2)
        ]

        window = tk.Toplevel(self)
        window.title(f"手动四角透视｜{page.name}")
        window.transient(self)
        work_x, work_y, work_w, work_h = _screen_work_area(self)
        max_w = max(640, min(1280, work_w - 120))
        max_h = max(520, min(920, work_h - 180))
        scale = min(
            1.0,
            max_w / max(1, source.width),
            (max_h - 90) / max(1, source.height),
        )
        display_size = (
            max(1, round(source.width * scale)),
            max(1, round(source.height * scale)),
        )

        body = ttk.Frame(window, padding=8)
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(
            body,
            width=display_size[0],
            height=display_size[1],
            highlightthickness=1,
            highlightbackground="#888888",
            cursor="crosshair",
        )
        canvas.pack(fill="both", expand=True)
        photo = ImageTk.PhotoImage(
            source.resize(display_size, Image.Resampling.LANCZOS)
        )
        canvas.create_image(0, 0, image=photo, anchor="nw", tags=("page",))
        window._manual_corner_photo = photo  # type: ignore[attr-defined]

        labels = ("左上", "右上", "右下", "左下")
        drag_state: dict[str, int | None] = {"index": None}

        def redraw_handles() -> None:
            canvas.delete("manual-corners")
            coords = [
                coordinate * scale
                for point in points
                for coordinate in point
            ]
            canvas.create_polygon(
                *coords,
                fill="",
                outline="#ff7a00",
                width=3,
                tags=("manual-corners",),
            )
            radius = 7
            for index, (x, y) in enumerate(points):
                cx = x * scale
                cy = y * scale
                canvas.create_oval(
                    cx - radius, cy - radius,
                    cx + radius, cy + radius,
                    fill="#ff7a00",
                    outline="white",
                    width=2,
                    tags=("manual-corners",),
                )
                canvas.create_text(
                    cx + 11, cy - 11,
                    text=labels[index],
                    fill="#d35400",
                    anchor="sw",
                    font=(AUTO_FONT_FAMILY, 10, "bold"),
                    tags=("manual-corners",),
                )

        def nearest_handle(event: tk.Event) -> int | None:
            best: tuple[float, int] | None = None
            for index, (x, y) in enumerate(points):
                dx = float(event.x) - x * scale
                dy = float(event.y) - y * scale
                distance = dx * dx + dy * dy
                if best is None or distance < best[0]:
                    best = (distance, index)
            if best is not None and best[0] <= 22.0 * 22.0:
                return best[1]
            return None

        def press(event: tk.Event) -> str:
            drag_state["index"] = nearest_handle(event)
            return "break"

        def drag(event: tk.Event) -> str:
            index = drag_state.get("index")
            if index is None:
                return "break"
            x = max(0.0, min(float(source.width - 1), float(event.x) / max(scale, 1e-9)))
            y = max(0.0, min(float(source.height - 1), float(event.y) / max(scale, 1e-9)))
            points[int(index)] = [x, y]
            redraw_handles()
            return "break"

        def release(_event: tk.Event) -> str:
            drag_state["index"] = None
            return "break"

        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", release)
        redraw_handles()

        ttk.Label(
            body,
            text=(
                "拖动四个橙色控制点到页面/正文平面的四角。坐标保存在原扫描图上；"
                "小角度纠偏后会同步变换四点，再做透视纠正，最后重新检测版面并裁边。"
            ),
            wraplength=max(560, display_size[0]),
            anchor="w",
        ).pack(fill="x", pady=(7, 4))

        controls = ttk.Frame(body)
        controls.pack(fill="x")

        def reset_handles() -> None:
            defaults = self._default_preprocess_corner_quad(source)
            for index in range(4):
                points[index] = [
                    float(defaults[index * 2]),
                    float(defaults[index * 2 + 1]),
                ]
            redraw_handles()

        def apply_handles() -> None:
            quad = tuple(coordinate for point in points for coordinate in point)
            try:
                perspective_from_quad(quad, source.size)
            except Exception as exc:
                messagebox.showerror(
                    "手动四角无效", str(exc), parent=window,
                )
                return
            save_manual_perspective_quad(project.root, page, quad)
            self._preprocess_results.pop(page.name, None)
            self._preprocess_photo = None
            self._preprocess_photo_cache_key = None
            window.destroy()
            self.status_var.set(f"已保存 {page.name} 手动四角；正在重新分析。")
            self.analyze_preprocess_current(silent=True)

        ttk.Button(
            controls, text="恢复整页四角", command=reset_handles,
            style="PC.Compact.TButton",
        ).pack(side="left")
        ttk.Button(
            controls, text="取消", command=window.destroy,
            style="PC.Compact.TButton",
        ).pack(side="right")
        ttk.Button(
            controls, text="应用四角", command=apply_handles,
            style="PC.Primary.TButton",
        ).pack(side="right", padx=(0, 6))

        window.update_idletasks()
        target_w = min(work_w, max(660, window.winfo_reqwidth()))
        target_h = min(work_h, max(560, window.winfo_reqheight()))
        x = work_x + max(0, (work_w - target_w) // 2)
        y = work_y + max(0, (work_h - target_h) // 2)
        window.geometry(f"{target_w}x{target_h}+{x}+{y}")
        window.grab_set()
        window.focus_force()

    def reset_preprocess_corners(self) -> None:
        if not self.project or self.current_page is None:
            return
        page = self.current_page
        clear_manual_perspective_quad(self.project.root, page)
        self._preprocess_results.pop(page.name, None)
        self._preprocess_photo = None
        self._preprocess_photo_cache_key = None
        self.status_var.set(f"已重置 {page.name} 手动四角；恢复自动几何纠正。")
        if self._preprocess_mode_active():
            self.analyze_preprocess_current(silent=True)

    def _preprocess_result_for_page(self, index: int) -> PreprocessAnalysis | None:
        if not self.project or not (0 <= index < len(self.project.images)):
            return None
        page = self.project.images[index]
        safety, auto_deskew, geometry_mode = self._preprocess_config()
        manual_quad = load_manual_perspective_quad(self.project.root, page)
        cached = self._preprocess_results.get(page.name)
        if cached is not None and preprocess_analysis_is_current(
            cached, page,
            safety_margin_px=safety,
            auto_deskew=auto_deskew,
            geometry_mode=geometry_mode,
            manual_perspective_quad=manual_quad,
        ):
            return cached
        loaded = load_preprocess_analysis(self.project.root, page)
        if loaded is not None and preprocess_analysis_is_current(
            loaded, page,
            safety_margin_px=safety,
            auto_deskew=auto_deskew,
            geometry_mode=geometry_mode,
            manual_perspective_quad=manual_quad,
        ):
            self._preprocess_results[page.name] = loaded
            return loaded
        self._preprocess_results.pop(page.name, None)
        return None

    def _set_current_preprocess_status(self, analysis: PreprocessAnalysis | None) -> None:
        if analysis is None:
            self.preprocess_status_var.set("当前页尚未分析")
            return
        warning = ""
        if analysis.warnings:
            warning = "｜" + "；".join(analysis.warnings[:2])
            if len(analysis.warnings) > 2:
                warning += f"；另 {len(analysis.warnings) - 2} 项"
        x0, y0, x1, y1 = analysis.crop_box
        content_width = max(1, int(x1) - int(x0))
        content_height = max(1, int(y1) - int(y0))
        layout_note = f"｜内容框 {content_width}×{content_height}px"
        try:
            (
                canvas_enabled, canvas_mode, page_width, page_height,
                margin_top, margin_bottom, margin_left, margin_right,
                _align_x, _align_y,
            ) = self._preprocess_export_config()
        except (AttributeError, tk.TclError):
            canvas_enabled = False
        if canvas_enabled:
            if canvas_mode == "custom" and page_width > 0 and page_height > 0:
                effective_width = max(
                    page_width, content_width + margin_left + margin_right
                )
                effective_height = max(
                    page_height, content_height + margin_top + margin_bottom
                )
                layout_note += (
                    f"｜页面 {effective_width}×{effective_height}px"
                    f"｜版心 {effective_width - margin_left - margin_right}"
                    f"×{effective_height - margin_top - margin_bottom}px"
                )
            else:
                layout_note += "｜页面=按本批最大内容框+页边空"
        self.preprocess_status_var.set(
            preprocess_result_summary(analysis) + layout_note + warning
        )

    def analyze_preprocess_current(self, *, silent: bool = False) -> None:
        if not self.project or self.current_page is None:
            if not silent:
                messagebox.showinfo("图片预处理", "请先打开项目。", parent=self)
            return
        if not self._preprocess_mode_active():
            self._set_preprocess_mode(True, analyze=False)
            if not self._preprocess_mode_active():
                return
        if self._batch_active:
            self.status_var.set("批量任务运行中，当前页分析将在任务结束后进行。")
            return

        page = self.current_page
        page_index = self.current_index
        project = self.project
        settings = replace(self.settings)
        safety, auto_deskew, geometry_mode = self._preprocess_config()
        manual_quad = load_manual_perspective_quad(project.root, page)
        current = self._preprocess_result_for_page(page_index)
        if current is not None:
            self._set_current_preprocess_status(current)
            self.redraw()
            return

        if self._ui_worker_key_active("preprocess-current"):
            self.preprocess_status_var.set(
                f"{page.name} 尚未分析｜正在完成上一页分析，完成后将继续当前页。"
            )
            return

        self.preprocess_status_var.set(f"正在分析 {page.name}…")
        self.status_var.set(f"图片预处理：正在后台分析 {page.name}…")

        def worker():
            return analyze_preprocess_path(
                page, settings,
                safety_margin_px=safety,
                auto_deskew=auto_deskew,
                geometry_mode=geometry_mode,
                manual_perspective_quad=manual_quad,
            )

        def done(analysis: PreprocessAnalysis) -> None:
            if self.project is not project:
                return
            save_preprocess_analysis(project.root, page, analysis)
            self._preprocess_results[page.name] = analysis
            if self.current_index == page_index and self.current_page == page:
                self._preprocess_photo = None
                self._preprocess_photo_cache_key = None
                self._set_current_preprocess_status(analysis)
                self.redraw()
                self.status_var.set(
                    f"图片预处理分析完成：{page.name}｜{preprocess_result_summary(analysis)}"
                )
            elif self._preprocess_mode_active() and self.current_page is not None:
                self.after_idle(lambda: self.analyze_preprocess_current(silent=True))

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            if self.project is project and self.current_page == page:
                self.preprocess_status_var.set(f"分析失败：{exc}")
                if not silent:
                    self.show_error("图片预处理分析失败", exc)
            elif self.project is project and self._preprocess_mode_active():
                self.after_idle(lambda: self.analyze_preprocess_current(silent=True))

        self._start_ui_worker("preprocess-current", worker, done, failed)

    def analyze_preprocess_selected(self) -> None:
        if not self.project:
            messagebox.showinfo("图片预处理", "请先打开项目。", parent=self)
            return
        if not self._preprocess_mode_active():
            self._set_preprocess_mode(True, analyze=False)
            if not self._preprocess_mode_active():
                return
        if self._ui_worker_key_active("preprocess-current"):
            self.status_var.set("当前页预处理分析仍在进行；完成后再启动范围分析。")
            return
        try:
            indices = self.selected_page_indices()
        except ValueError as exc:
            self.show_error("页面范围无效", exc)
            return
        project = self.project
        settings = replace(self.settings)
        safety, auto_deskew, geometry_mode = self._preprocess_config()

        def worker(index, _position, _total):
            page = project.images[int(index)]
            manual_quad = load_manual_perspective_quad(project.root, page)
            analysis = analyze_preprocess_path(
                page, settings,
                safety_margin_px=safety,
                auto_deskew=auto_deskew,
                geometry_mode=geometry_mode,
                manual_perspective_quad=manual_quad,
            )
            save_preprocess_analysis(project.root, page, analysis)
            return int(index), analysis

        def done(_completed, _total, _stopped, results, error):
            if error is not None or self.project is not project:
                return
            normal = 0
            review = 0
            for index, analysis in results:
                page = project.images[int(index)]
                self._preprocess_results[page.name] = analysis
                if analysis.status == "review":
                    review += 1
                else:
                    normal += 1
            current = self._preprocess_result_for_page(self.current_index)
            self._preprocess_photo = None
            self._preprocess_photo_cache_key = None
            self._set_current_preprocess_status(current)
            self.redraw()
            self.status_var.set(
                f"预处理分析完成：正常 {normal} 页｜需检查 {review} 页。"
            )

        self._start_batch_task(
            "图片预处理分析", indices, worker,
            on_done=done,
            item_label=lambda index: project.images[int(index)].name,
            refresh_page_quality=False,
            allow_page_navigation=True,
        )

    def show_preprocess_diagnostics(self) -> None:
        """Show the current page's detailed preprocessing diagnostics on demand."""
        if not self.project or self.current_page is None:
            messagebox.showinfo("诊断信息", "请先打开项目。", parent=self)
            return
        analysis = self._preprocess_result_for_page(self.current_index)
        if analysis is None:
            messagebox.showinfo(
                "诊断信息",
                "当前页尚无预处理结果。请先执行【分析所选范围】。",
                parent=self,
            )
            return

        existing = getattr(self, "_preprocess_diagnostics_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.destroy()
            except tk.TclError:
                pass

        window = tk.Toplevel(self)
        self._preprocess_diagnostics_window = window
        window.title(f"预处理诊断信息｜{self.current_page.name}")
        window.transient(self)
        fit_window_to_work_area(
            window, 920, 720, min_width=700, min_height=500,
        )

        body = ttk.Frame(window, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        ttk.Label(
            body,
            text=preprocess_result_summary(analysis),
            style="PC.FieldLabel.TLabel",
            wraplength=860,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        text_frame = ttk.Frame(body)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        text_widget = tk.Text(
            text_frame,
            wrap="none",
            undo=False,
            padx=8,
            pady=8,
        )
        yscroll = ttk.Scrollbar(
            text_frame, orient="vertical", command=text_widget.yview,
        )
        xscroll = ttk.Scrollbar(
            text_frame, orient="horizontal", command=text_widget.xview,
        )
        text_widget.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        text_widget.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        warnings = list(analysis.warnings or ())
        header_lines = [
            f"页面：{self.current_page.name}",
            f"状态：{'需检查' if analysis.status == 'review' else '正常'}",
            f"方法：{analysis.method}",
            f"几何模式：{analysis.geometry_mode}",
        ]

        valid_indices = tuple(
            int(value)
            for value in analysis.perspective_row_valid_column_indices
        )
        if valid_indices:
            header_lines.extend(
                [
                    "",
                    "分栏水平诊断（before → after）：",
                ]
            )
            top_before = analysis.perspective_row_before_column_top_angles_deg
            top_after = analysis.perspective_row_after_column_top_angles_deg
            mid_before = analysis.perspective_row_before_column_middle_angles_deg
            mid_after = analysis.perspective_row_after_column_middle_angles_deg
            bottom_before = analysis.perspective_row_before_column_bottom_angles_deg
            bottom_after = analysis.perspective_row_after_column_bottom_angles_deg
            trend_before = analysis.perspective_row_before_column_trends_deg
            trend_after = analysis.perspective_row_after_column_trends_deg
            row_counts = analysis.perspective_row_column_row_counts
            for pos, column_index in enumerate(valid_indices):
                def value(seq, default=0.0):
                    return float(seq[pos]) if pos < len(seq) else float(default)

                rows = (
                    int(row_counts[column_index])
                    if 0 <= column_index < len(row_counts)
                    else 0
                )
                header_lines.append(
                    f"- 第 {column_index + 1} 栏"
                    f"（{rows} 行）："
                    f"上 {value(top_before):+.3f}°→{value(top_after):+.3f}°；"
                    f"中 {value(mid_before):+.3f}°→{value(mid_after):+.3f}°；"
                    f"下 {value(bottom_before):+.3f}°→{value(bottom_after):+.3f}°；"
                    f"趋势 {value(trend_before):+.3f}°→{value(trend_after):+.3f}°"
                )
            header_lines.append(
                "最差残余区域："
                f"{analysis.perspective_row_after_worst_region_deg:.3f}°"
                + (
                    f"（第 {analysis.perspective_row_after_worst_column_index + 1} 栏）"
                    if analysis.perspective_row_after_worst_column_index >= 0
                    else ""
                )
            )
            if analysis.perspective_horizontal_vp_column_spread_deg > 0:
                header_lines.append(
                    "各栏 VP 方向分歧 P90："
                    f"{analysis.perspective_horizontal_vp_column_spread_deg:.3f}°"
                )
        elif analysis.line_geometry_valid_columns:
            indices = tuple(
                int(value)
                for value in analysis.line_geometry_valid_column_indices
            )
            header_lines.extend(["", "原始分栏行几何："])
            for pos, column_index in enumerate(indices):
                rows = (
                    int(analysis.line_geometry_column_row_counts[column_index])
                    if 0 <= column_index < len(analysis.line_geometry_column_row_counts)
                    else 0
                )
                trend = (
                    float(analysis.line_geometry_column_trends_deg[pos])
                    if pos < len(analysis.line_geometry_column_trends_deg)
                    else 0.0
                )
                header_lines.append(
                    f"- 第 {column_index + 1} 栏：{rows} 行，趋势 {trend:+.3f}°"
                )
            header_lines.append(
                "最差局部角："
                f"{analysis.line_geometry_worst_region_angle_deg:.3f}°"
            )

        header_lines.extend(
            [
                "",
                "警告：" if warnings else "警告：无",
            ]
        )
        if warnings:
            header_lines.extend(f"- {item}" for item in warnings)
        header_lines.extend(
            [
                "",
                "完整诊断参数（JSON）：",
                json.dumps(
                    analysis.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
            ]
        )
        diagnostic_text = "\n".join(header_lines)
        text_widget.insert("1.0", diagnostic_text)
        text_widget.configure(state="disabled")

        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, sticky="e", pady=(8, 0))

        def copy_all() -> None:
            try:
                self.clipboard_clear()
                self.clipboard_append(diagnostic_text)
                self.status_var.set(
                    f"已复制预处理诊断信息：{self.current_page.name}"
                )
            except tk.TclError:
                pass

        ttk.Button(
            buttons, text="复制全部", command=copy_all,
            style="PC.Compact.TButton",
        ).pack(side="left")
        ttk.Button(
            buttons, text="关闭", command=window.destroy,
            style="PC.Compact.TButton",
        ).pack(side="left", padx=(6, 0))
        window.bind("<Escape>", lambda _event: window.destroy())
        window.protocol("WM_DELETE_WINDOW", window.destroy)

    def promote_preprocessed_working_images(self) -> None:
        """Replace root working scans with the verified processed export set."""
        if not self.project:
            messagebox.showinfo("设为工作图片", "请先打开项目。", parent=self)
            return
        if self._batch_active or self._ui_worker_key_active("preprocess-current"):
            self.status_var.set("预处理任务仍在运行；完成后再设为工作图片。")
            return

        project = self.project
        try:
            indices = self.selected_page_indices()
        except ValueError as exc:
            self.show_error("页面范围无效", exc)
            return
        pages = [project.images[int(index)] for index in indices]
        if not pages:
            return

        # Any existing coordinate-bearing work may no longer match after crop/
        # projective correction. Warn explicitly, but do not silently delete it.
        ordinary_data_pages = 0
        for page in pages:
            try:
                has_data = (
                    pdic_path(page).is_file()
                    or ppp_read_path_for_image(page).is_file()
                    or (ocr_cache_root(project.root) / f"{page.stem}.json").is_file()
                )
            except OSError:
                has_data = False
            if has_data:
                ordinary_data_pages += 1

        warning = (
            "\n\n注意：检测到 "
            f"{ordinary_data_pages} 页已有 PDIC/PPP/OCR 坐标数据。"
            "预处理会改变页面坐标，这些旧坐标可能不再适用；软件不会自动删除它们。"
            if ordinary_data_pages
            else ""
        )
        confirmed = messagebox.askyesno(
            "设为工作图片",
            "将只把当前所选范围的预处理图片设为后续工作图片。\n\n"
            f"所选页面：{len(pages)} 页\n"
            "所选原扫描图：移动到项目根目录下的 __before__\n"
            "所选处理后图片：以相同文件名写回项目根目录\n"
            "未选页面：保持原样，可之后采用其他预处理方式\n"
            "预处理导出和诊断文件：继续保留，不会删除\n\n"
            "__before__ 可逐批累积不同页面的首代原图；"
            "其中已经存在的同名页面绝不覆盖。"
            f"{warning}\n\n"
            "确认继续吗？",
            parent=self,
        )
        if not confirmed:
            return

        root = project.root
        target_page = self.current_page.name if self.current_page is not None else None
        target_index = self.current_index
        target_view_scale = float(self.view_scale)
        suffix = str(self.settings.image_suffix or "").strip() or None

        try:
            backup, promoted = promote_processed_pages(root, pages)
        except Exception as exc:
            self.show_error("设为工作图片失败", exc)
            return

        messagebox.showinfo(
            "设为工作图片",
            f"已切换所选 {len(promoted)} 页。\n\n"
            f"这些页面的原扫描图已保存在：{backup}\n"
            "处理后图片现在位于项目根目录，并将作为这些页面后续 OCR、画线和切图的工作图片；"
            "其他未选页面保持原样。\n\n"
            "建议接下来重新检测版面参数；旧坐标型结果如来自原图，应重新生成。",
            parent=self,
        )

        # Reload the same project from disk so page dimensions, thumbnails and
        # all downstream geometry use the promoted images immediately.
        if self._preprocess_mode_active():
            self._set_preprocess_mode(False, analyze=False)
        self._preprocess_results.clear()
        self.current_page = None
        self.image = None
        self.photo = None
        self.current_index = -1
        self.project = None
        self._load_project(
            root,
            requested_suffix=suffix,
            target_page=target_page,
            target_index=target_index,
            target_view_scale=target_view_scale,
        )

    def jump_preprocess_review(self, delta: int) -> None:
        if not self.project:
            return
        if not self._preprocess_mode_active():
            self._set_preprocess_mode(True, analyze=False)
            if not self._preprocess_mode_active():
                return
        step = -1 if int(delta) < 0 else 1
        start = self.current_index + step
        stop = -1 if step < 0 else len(self.project.images)
        for index in range(start, stop, step):
            analysis = self._preprocess_result_for_page(index)
            if analysis is not None and analysis.status == "review":
                self._request_page_load(index)
                return
        self.status_var.set(
            "后面没有已分析的“需检查”页面。" if step > 0
            else "前面没有已分析的“需检查”页面。"
        )

    def _preprocess_analysis_for_export(
        self, project: ProjectState, page: Path, settings: AppSettings,
        safety: float, auto_deskew: bool, geometry_mode: str,
    ) -> PreprocessAnalysis:
        manual_quad = load_manual_perspective_quad(project.root, page)
        analysis = load_preprocess_analysis(project.root, page)
        if analysis is None or not preprocess_analysis_is_current(
            analysis, page,
            safety_margin_px=safety,
            auto_deskew=auto_deskew,
            geometry_mode=geometry_mode,
            manual_perspective_quad=manual_quad,
        ):
            analysis = analyze_preprocess_path(
                page, settings,
                safety_margin_px=safety,
                auto_deskew=auto_deskew,
                geometry_mode=geometry_mode,
                manual_perspective_quad=manual_quad,
            )
            save_preprocess_analysis(project.root, page, analysis)
        return analysis

    def export_preprocess_previews(self) -> None:
        if not self.project:
            messagebox.showinfo("图片预处理", "请先打开项目。", parent=self)
            return
        if self._ui_worker_key_active("preprocess-current"):
            self.status_var.set("当前页预处理分析仍在进行；完成后再导出检查小图。")
            return
        try:
            indices = self.selected_page_indices()
        except ValueError as exc:
            self.show_error("页面范围无效", exc)
            return
        project = self.project
        settings = replace(self.settings)
        safety, auto_deskew, geometry_mode = self._preprocess_config()
        output = preprocess_preview_output_root(project.root)

        def worker(index, _position, _total):
            page = project.images[int(index)]
            analysis = self._preprocess_analysis_for_export(
                project, page, settings, safety, auto_deskew, geometry_mode,
            )
            destination = output / f"{page.stem}_preview.jpg"
            save_review_preview(page, analysis, destination)
            return int(index), analysis, destination

        def done(_completed, _total, _stopped, results, error):
            if error is not None or self.project is not project:
                return
            for index, analysis, _destination in results:
                self._preprocess_results[project.images[int(index)].name] = analysis
            self.status_var.set(f"检查小图已导出：{output}")

        self._start_batch_task(
            "导出预处理检查小图", indices, worker,
            on_done=done,
            item_label=lambda index: project.images[int(index)].name,
            refresh_page_quality=False,
            allow_page_navigation=True,
        )

    def export_preprocess_images(self) -> None:
        if not self.project:
            messagebox.showinfo("图片预处理", "请先打开项目。", parent=self)
            return
        if self._ui_worker_key_active("preprocess-current"):
            self.status_var.set("当前页预处理分析仍在进行；完成后再导出预处理图片。")
            return
        try:
            indices = self.selected_page_indices()
        except ValueError as exc:
            self.show_error("页面范围无效", exc)
            return

        project = self.project
        settings = replace(self.settings)
        safety, auto_deskew, geometry_mode = self._preprocess_config()
        (
            canvas_enabled,
            canvas_mode,
            canvas_width,
            canvas_height,
            margin_top,
            margin_bottom,
            margin_left,
            margin_right,
            align_x,
            align_y,
        ) = self._preprocess_export_config()
        if canvas_enabled and canvas_mode == "custom":
            if canvas_width <= 0 or canvas_height <= 0:
                messagebox.showerror(
                    "统一最终页面",
                    "指定页面尺寸时，宽度和高度都必须大于 0 px。",
                    parent=self,
                )
                return

        output = preprocess_processed_output_root(project.root)
        metadata_output = preprocess_metadata_output_root(project.root)

        # Stage 1 analyzes every page before writing images. This makes it
        # possible to resolve one common batch canvas that is guaranteed to fit
        # the largest retained crop, even when a custom requested size is too
        # small. No scan content is rescaled.
        def analyze_worker(index, _position, _total):
            page = project.images[int(index)]
            analysis = self._preprocess_analysis_for_export(
                project, page, settings, safety, auto_deskew, geometry_mode,
            )
            return int(index), analysis

        def analyzed(_completed, _total, stopped, results, error):
            if error is not None or self.project is not project:
                return
            for index, analysis in results:
                self._preprocess_results[project.images[int(index)].name] = analysis
            if stopped or not results:
                self.status_var.set("预处理图片导出已停止在分析阶段；尚未写入最终图片。")
                return

            analysis_by_index = {
                int(index): analysis for index, analysis in results
            }
            content_widths = [
                max(1, analysis.crop_box[2] - analysis.crop_box[0])
                for analysis in analysis_by_index.values()
            ]
            content_heights = [
                max(1, analysis.crop_box[3] - analysis.crop_box[1])
                for analysis in analysis_by_index.values()
            ]
            max_content_width = max(content_widths)
            max_content_height = max(content_heights)

            minimum_page_width = (
                max_content_width + margin_left + margin_right
            )
            minimum_page_height = (
                max_content_height + margin_top + margin_bottom
            )
            if canvas_enabled:
                if canvas_mode == "batch_max":
                    requested_width = minimum_page_width
                    requested_height = minimum_page_height
                else:
                    requested_width = canvas_width
                    requested_height = canvas_height
                effective_width = max(requested_width, minimum_page_width)
                effective_height = max(requested_height, minimum_page_height)
            else:
                requested_width = 0
                requested_height = 0
                effective_width = 0
                effective_height = 0

            export_items = [
                int(index) for index, _analysis in results
            ]

            def export_worker(index, _position, _total):
                page = project.images[int(index)]
                analysis = analysis_by_index[int(index)]
                canvas = output_canvas_info(
                    analysis,
                    enabled=canvas_enabled,
                    mode=canvas_mode,
                    requested_width=requested_width,
                    requested_height=requested_height,
                    canvas_width=effective_width if canvas_enabled else None,
                    canvas_height=effective_height if canvas_enabled else None,
                    margin_top=margin_top,
                    margin_bottom=margin_bottom,
                    margin_left=margin_left,
                    margin_right=margin_right,
                    align_x=align_x,
                    align_y=align_y,
                )
                destination = output / page.name
                save_processed_page(
                    page, analysis, destination, canvas=canvas,
                )
                metadata_destination = (
                    metadata_output / f"{page.stem}.preprocess.json"
                )
                export_diagnostic_json(
                    page,
                    analysis,
                    metadata_destination,
                    output_path=destination,
                    canvas=canvas,
                    settings=settings,
                )
                return (
                    int(index), analysis, destination, canvas,
                    metadata_destination,
                )

            def exported(_done, _export_total, export_stopped, export_results, export_error):
                if export_error is not None or self.project is not project:
                    return
                summary_records = []
                for (
                    index,
                    analysis,
                    destination,
                    canvas,
                    _metadata_destination,
                ) in sorted(export_results, key=lambda item: int(item[0])):
                    page = project.images[int(index)]
                    self._preprocess_results[page.name] = analysis
                    summary_records.append(
                        (page, analysis, destination, canvas)
                    )
                summary_path = output.parent / "preprocess_summary.csv"
                export_summary_csv(summary_records, summary_path)

                canvas_note = ""
                if canvas_enabled:
                    body_width = (
                        effective_width - margin_left - margin_right
                    )
                    body_height = (
                        effective_height - margin_top - margin_bottom
                    )
                    canvas_note = (
                        f"｜最终页面 {effective_width}×{effective_height}px"
                        f"｜版心 {body_width}×{body_height}px"
                        f"（页边 上{margin_top}/左{margin_left}/"
                        f"下{margin_bottom}/右{margin_right}px；"
                        f"X {self.preprocess_export_align_x_var.get()} / "
                        f"Y {self.preprocess_export_align_y_var.get()}）"
                    )
                    if (
                        canvas_mode == "custom"
                        and (
                            effective_width > requested_width
                            or effective_height > requested_height
                        )
                    ):
                        canvas_note += (
                            f"｜自定义 {requested_width}×{requested_height}px "
                            "不足，已整批扩容且未缩放正文"
                        )
                stop_note = "｜已安全停止，汇总仅含已完成页" if export_stopped else ""
                self.status_var.set(
                    f"预处理图片已导出：{output}"
                    f"｜诊断参数：{metadata_output}"
                    f"｜汇总：{summary_path.name}"
                    f"{canvas_note}{stop_note}｜原扫描图未修改。"
                )

            def start_export_stage() -> None:
                self._start_batch_task(
                    "导出预处理图片", export_items, export_worker,
                    on_done=exported,
                    item_label=lambda index: project.images[int(index)].name,
                    refresh_page_quality=False,
                    allow_page_navigation=True,
                )

            # _finish_batch_task clears the current batch callback/thread after
            # invoking us, so schedule stage 2 for the next Tk turn instead of
            # starting it re-entrantly inside the stage-1 completion callback.
            self.after_idle(start_export_stage)

        self._start_batch_task(
            "分析预处理导出范围", indices, analyze_worker,
            on_done=analyzed,
            item_label=lambda index: project.images[int(index)].name,
            refresh_page_quality=False,
            allow_page_navigation=True,
        )

    def _get_preprocess_display_photo(
        self, size: tuple[int, int], analysis: PreprocessAnalysis | None,
    ) -> ImageTk.PhotoImage:
        if self.image is None:
            raise RuntimeError("没有可显示的页面图像")
        analysis_key = (
            None if analysis is None else round(float(analysis.applied_angle_deg), 4),
            None if analysis is None else analysis.geometry_mode,
            None if analysis is None else round(float(analysis.geometry_strength_px), 3),
            None if analysis is None else tuple(int(value) for value in analysis.crop_box),
        )
        key = (
            id(self.image), int(size[0]), int(size[1]),
            analysis_key, self.appearance_mode,
        )
        if self._preprocess_photo is not None and self._preprocess_photo_cache_key == key:
            return self._preprocess_photo

        if analysis is not None:
            corrected_key = (id(self.image), id(analysis))
            if (
                self._preprocess_corrected_image is None
                or self._preprocess_corrected_image_key != corrected_key
            ):
                self._preprocess_corrected_image = geometry_corrected_image(
                    self.image, analysis,
                )
                self._preprocess_corrected_image_key = corrected_key
            display = self._preprocess_corrected_image.resize(
                size, Image.Resampling.LANCZOS
            )
        else:
            self._preprocess_corrected_image = None
            self._preprocess_corrected_image_key = None
            display = self.image.resize(size, Image.Resampling.LANCZOS)
        display = themed_display_image(display, self.appearance_mode)
        if analysis is not None:
            sx = size[0] / max(1, analysis.source_width)
            sy = size[1] / max(1, analysis.source_height)
            x0, y0, x1, y1 = analysis.crop_box
            display = overlay_excluded_regions(
                display,
                (
                    round(x0 * sx), round(y0 * sy),
                    round(x1 * sx), round(y1 * sy),
                ),
            )
        self._preprocess_photo = ImageTk.PhotoImage(display)
        self._preprocess_photo_cache_key = key
        return self._preprocess_photo

    def _redraw_preprocess_preview(self, size: tuple[int, int]) -> None:
        analysis = self._preprocess_result_for_page(self.current_index)
        photo = self._get_preprocess_display_photo(size, analysis)
        self.canvas.create_image(0, 0, image=photo, anchor="nw", tags="page")
        self.canvas.configure(scrollregion=(0, 0, size[0], size[1]))
        self._set_current_preprocess_status(analysis)

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
            for name, var in self.quick_bool_vars.items(): setattr(self.settings, name, bool(var.get()))
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
        write_ppp(ppp, self.polygons, self.current_page.stem)
        self._update_page_row(self.current_index)
        return pdic_path(self.current_page), ppp

    def _save_current_page_by_mode(self, *, sync_editors: bool = True) -> Path | None:
        """ save current page by mode."""
        if not self.project or not self.current_page or self.image is None:
            return None
        if self.polygon_draw_var.get() and not getattr(self, "_batch_allow_pdic_edits", False):
            target = self._ppp_write_path(self.current_page)
            write_ppp(target, self.polygons, self.current_page.stem)
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
        if not self.guard() or not self.apply_quick_settings(show_status=False): return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc); return
        names = [self.project.images[i].name for i in indices]
        if not messagebox.askyesno(
            "选择检测页面范围",
            f"将按页面列表上方当前选择的范围检测 {len(indices)} 页。\n"
            f"范围：{names[0]}" + (f" ～ {names[-1]}" if len(names) > 1 else "") +
            "\n\n多页数值参数将取稳健中位数；分栏数按多数页面的栏数确定。"
            "检测结果会填充分栏/起始Y/首栏X/栏宽/栏间空/行高/行间空；"
            "页底不再作为手工参数写入。是否继续？",
            parent=self,
        ):
            return
        settings = replace(self.settings)
        pages = list(self.project.images)

        def worker(index: int, _position: int, _total: int):
            with Image.open(pages[index]) as opened:
                return detect_layout_parameters(opened, settings)

        def done(_completed, _total, stopped, results, error) -> None:
            if error or not results:
                return
            from .layout_detection import aggregate_layout_estimates
            values, consistency = aggregate_layout_estimates(
                results,
                columns_policy=self.settings.layout_columns_policy,
                fixed_columns=self.settings.columns,
            )
            old_character_height = max(1, int(self.settings.character_height))
            body_indent_was_auto = int(self.settings.body_indent) == old_character_height
            horizontal_tolerance_was_auto = (
                int(self.settings.horizontal_tolerance)
                == max(1, round(old_character_height / 2.0))
            )
            for name, value in values.items():
                if name == "bottom_y":
                    continue
                setattr(self.settings, name, value)
            if "character_height" in values:
                new_character_height = max(1, int(self.settings.character_height))
                if body_indent_was_auto:
                    self.settings.body_indent = new_character_height
                if horizontal_tolerance_was_auto:
                    self.settings.horizontal_tolerance = max(
                        1, round(new_character_height / 2.0)
                    )
            self.sync_quick_settings(); self.save_settings(); self.redraw()
            suffix = "（任务提前停止，按已完成页面计算）" if stopped else ""
            summary = "稳健中位数" if len(results) >= 2 else "单页检测值"
            self.status_var.set(f"版面参数检测完成：{consistency}；数值参数使用{summary}{suffix}")

        self._start_batch_task("检测版面参数", indices, worker, done, item_label=lambda i: pages[i].name)

    def detect_layout_consistency_selected(self) -> None:
        if not self.guard() or not self.apply_quick_settings(show_status=False): return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc); return
        if len(indices) < 2:
            messagebox.showwarning(
                "检测版面一致性",
                "版面一致性检测至少需要选择 2 页；当前页面范围不足 2 页，未执行检测。",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "检测版面一致性",
            f"将快速扫描当前所选 {len(indices)} 页，输出原图 X/Y 中的页眉边界与正文左缘。\n\n"
            "此任务使用灰度投影而非 PaddleVL/OCR，以便高效处理数千页。是否继续？",
            parent=self,
        ):
            return
        project = self.project
        pages = list(project.images); settings = replace(self.settings)
        range_name = pages[indices[0]].stem if len(indices) == 1 else f"{pages[indices[0]].stem}-{pages[indices[-1]].stem}"
        range_name = re.sub(r'[^0-9A-Za-z_.-]+', "_", range_name)

        def worker(index: int, _position: int, _total: int):
            with Image.open(pages[index]) as opened:
                image_size = opened.size
                estimate = detect_layout_consistency(opened, settings)
            transform_kind = str(getattr(settings, "layout_transform", "identity") or "identity")
            transform = LayoutTransform(transform_kind)
            canonical_width, canonical_height = transform.canonical_size(image_size)
            header_segment = None
            if estimate.header_rule_y is not None:
                header_segment = transform.canonical_marker_to_source(
                    (0, int(estimate.header_rule_y)),
                    (max(0, canonical_width - 1), int(estimate.header_rule_y)),
                    image_size,
                )
            left_segment = None
            if estimate.body_left_x is not None:
                left_segment = transform.canonical_marker_to_source(
                    (int(estimate.body_left_x), 0),
                    (int(estimate.body_left_x), max(0, canonical_height - 1)),
                    image_size,
                )
            header_y = (
                int(header_segment[0][1])
                if header_segment and int(header_segment[0][1]) == int(header_segment[1][1])
                else None
            )
            left_x = (
                int(left_segment[0][0])
                if left_segment and int(left_segment[0][0]) == int(left_segment[1][0])
                else None
            )
            return (
                pages[index].name, header_segment, left_segment,
                header_y, left_x, estimate.is_blank, transform_kind,
            )

        def done(_completed, _total, stopped, results, error) -> None:
            if error or not results:
                return
            rows = list(results)
            stopped_early = bool(stopped)
            export_dir = exports_root(project.root)
            self.status_var.set("版面扫描完成；正在后台生成 CSV 与统计报告…")

            def finalize_report():
                base = f"layout_consistency_{range_name}_{datetime.now():%Y%m%d_%H%M%S_%f}"
                target = export_dir / f"{base}.csv"
                report = export_dir / f"{base}_report.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                temp_csv = target.with_name(f".{target.name}.tmp")
                temp_report = report.with_name(f".{report.name}.tmp")

                def segment_text(segment) -> str:
                    if not segment:
                        return ""
                    (x0, y0), (x1, y1) = segment
                    return f"{x0},{y0}->{x1},{y1}"

                try:
                    with temp_csv.open("w", encoding="utf-8-sig", newline="") as handle:
                        writer = csv.writer(handle)
                        writer.writerow((
                            "page",
                            "header_rule_source_segment_xyxy",
                            "body_left_source_segment_xyxy",
                            "header_rule_source_y",
                            "body_left_source_x",
                            "coordinate_space",
                            "layout_transform_internal",
                            "status",
                        ))
                        writer.writerows((
                            row[0], segment_text(row[1]), segment_text(row[2]),
                            row[3], row[4], SOURCE_COORDINATE_SPACE, row[6],
                            "blank_skipped" if row[5] else "analyzed",
                        ) for row in rows)

                    analyzed = [row for row in rows if not row[5]]
                    blanks = [row[0] for row in rows if row[5]]
                    header_values = [row[3] for row in analyzed if row[3] is not None]
                    left_values = [row[4] for row in analyzed if row[4] is not None]

                    def summary(values) -> str:
                        return (
                            "无可比较的同轴值" if not values
                            else f"均值 {statistics.fmean(values):.1f}，范围 {min(values)}–{max(values)}，标准差 {statistics.pstdev(values):.1f}"
                        )

                    def outliers(column: int) -> list[str]:
                        pairs = [(row[0], row[column]) for row in analyzed if row[column] is not None]
                        if len(pairs) < 3:
                            return []
                        values = [value for _name, value in pairs]
                        mean = statistics.fmean(values)
                        deviation = statistics.pstdev(values)
                        tolerance = max(3.0, deviation * 2.5)
                        return [name for name, value in pairs if abs(value - mean) > tolerance]

                    abnormal = sorted(set(outliers(3) + outliers(4)))
                    header_summary = summary(header_values)
                    left_summary = summary(left_values)
                    report_text = (
                        f"页面范围：{range_name}\n总页数：{len(rows)}\n有效分析：{len(analyzed)}\n"
                        f"空白页跳过：{len(blanks)}（{', '.join(blanks) or '无'}）\n"
                        f"页眉横线 Y（原图px）：{header_summary}\n"
                        f"正文左缘 X（原图px）：{left_summary}\n"
                        f"异常页面：{', '.join(abnormal) or '无'}\n"
                    )
                    temp_report.write_text(report_text, encoding="utf-8-sig")
                    temp_csv.replace(target)
                    try:
                        temp_report.replace(report)
                    except Exception:
                        target.unlink(missing_ok=True)
                        raise
                    return {
                        "target": target, "report": report,
                        "analyzed": len(analyzed), "blanks": len(blanks),
                        "header_summary": header_summary, "left_summary": left_summary,
                        "abnormal": abnormal, "total": len(rows),
                    }
                except Exception:
                    temp_csv.unlink(missing_ok=True)
                    temp_report.unlink(missing_ok=True)
                    target.unlink(missing_ok=True)
                    report.unlink(missing_ok=True)
                    raise

            def finalized(payload) -> None:
                if self.project is not project:
                    return
                abnormal_text = ", ".join(payload["abnormal"]) or "无"
                messagebox.showinfo(
                    "版面一致性统计",
                    f"完成 {payload['total']} 页，有效 {payload['analyzed']} 页，跳过空白页 {payload['blanks']} 页"
                    f"{'（提前停止）' if stopped_early else ''}\n"
                    f"页眉横线 Y（原图px）：{payload['header_summary']}\n"
                    f"正文左缘 X（原图px）：{payload['left_summary']}\n"
                    f"异常页面：{abnormal_text}\n\n"
                    "CSV 只保存原图 X/Y 边界线段与可直接比较的 source X/Y 数值。\n"
                    f"结果：{payload['target']}\n报告：{payload['report']}",
                    parent=self,
                )
                self.status_var.set(f"版面一致性检测完成：{payload['target'].name}")

            def finalize_failed(exc, detail) -> None:
                if detail:
                    print(detail)
                if self.project is project:
                    self.show_error("生成版面一致性报告失败", exc)

            self._start_ui_worker(
                "layout-consistency-finalize",
                finalize_report, finalized, finalize_failed,
                wait_on_close=True,
            )

        self._start_batch_task("检测版面一致性", indices, worker, done, item_label=lambda i: pages[i].name)

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
        if index is None:
            index = self.current_index
        if not self._batch_active or not self._batch_foreground_pages:
            return ""
        with self._batch_state_lock:
            return self._batch_page_states.get(int(index), "")

    def _set_foreground_batch_state(self, index: int, state: str) -> None:
        with self._batch_state_lock:
            if index in self._batch_page_states:
                self._batch_page_states[index] = state

    def _claim_page_for_manual_edit(self, index: int | None = None) -> bool:
        """ claim page for manual edit."""
        if index is None:
            index = self.current_index
        if not self._batch_active:
            return True
        if not self._batch_foreground_pages:
            if getattr(self, "_batch_allow_pdic_edits", False) and not self.polygon_draw_var.get():
                return True
            self.status_var.set("批量任务正在运行；该任务不支持同时编辑页面。")
            return False
        with self._batch_state_lock:
            state = self._batch_page_states.get(int(index), "")
            if state == "processing":
                self.status_var.set("当前页正在后台处理，暂时只读；完成后即可校对。")
                return False
            if state == "pending":
                self._batch_page_states[int(index)] = "manual_locked"
                state = "manual_locked"
        if state == "manual_locked":
            self._update_page_row(int(index))
            self.status_var.set("当前页已人工锁定：本轮后台批处理将跳过此页，可安全校对。")
        return True

    def _can_save_current_during_batch_navigation(self) -> bool:
        if not self._batch_active or not self._batch_foreground_pages:
            return True
        state = self._foreground_batch_state(self.current_index)
        # Never write an old foreground copy over a page that the worker owns or
        # has not yet started. Pending pages are saved only after a manual edit
        # atomically converts them to manual_locked.
        return state not in {"pending", "processing"}

    def _entry_keypress_batch_guard(self, event: tk.Event) -> str | None:
        """Claim a pending page before a key can mutate a foreground Entry."""
        if not self._batch_active or not self._batch_foreground_pages:
            return None
        keysym = str(getattr(event, "keysym", ""))
        # Cursor/navigation/focus keys do not constitute a manual edit.
        non_edit = {"Left", "Right", "Up", "Down", "Home", "End", "Tab", "ISO_Left_Tab",
                    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                    "Escape", "Return"}
        if keysym in non_edit:
            return None
        if not self._claim_page_for_manual_edit():
            return "break"
        return None

    def _start_batch_task(
        self, title: str, items, worker, on_done=None, item_label=None,
        *, foreground_page_edit: bool = False, page_indexer=None,
        refresh_page_quality: bool = True,
        allow_page_navigation: bool = False,
        allow_pdic_edits: bool = False,
    ) -> bool:
        """ start batch task."""
        if self._batch_active:
            messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=self)
            return False
        if self._ui_worker_key_active("project-load"):
            self.status_var.set("项目仍在后台打开；完成后再启动批量任务。")
            return False
        if self._ui_worker_key_active("profile-validation"):
            self.status_var.set("Project Profile 测试仍在运行或安全结束中；完成后再启动批量任务。")
            return False
        if self._ui_worker_key_active("headword-order-finalize"):
            self.status_var.set("全项目词头顺序报告仍在汇总；完成后再启动新的批量任务。")
            return False
        if self._ui_close_requested:
            return False
        self._flush_deferred_page_save()
        items = list(items)
        if not items:
            self.status_var.set("没有需要处理的页面")
            return False

        self._batch_active = True
        self._batch_refresh_page_quality = bool(refresh_page_quality)
        self._batch_foreground_pages = bool(foreground_page_edit)
        self._batch_allow_page_navigation = bool(allow_page_navigation)
        self._batch_allow_pdic_edits = bool(allow_pdic_edits)
        self._batch_skipped_count = 0
        indexer = page_indexer or (lambda item: int(item))
        with self._batch_state_lock:
            self._batch_page_states = {indexer(item): "pending" for item in items} if foreground_page_edit else {}
        self._batch_title = title
        self._batch_on_done = on_done
        self._batch_stop_event.clear()
        self._batch_pause_event.set()
        self._batch_in_item = False
        self.batch_progress_var.set(0.0)
        self.batch_progress.configure(maximum=100.0)
        self.batch_text_var.set(f"{title}：准备开始 0/{len(items)}")
        self.batch_pause_button.configure(text="暂停", state="normal")
        self.batch_stop_button.configure(text="停止", state="normal")
        if not self.batch_bar.winfo_manager():
            self.batch_bar.pack(side="right", fill="x")
        self.status_var.set(
            f"{title}开始：共 {len(items)} 页。" +
            ("可切换并校对其他页面；人工修改的待处理页会自动锁定并由后台跳过。" if foreground_page_edit
             else "可随时暂停或停止；操作在当前页完成后生效。")
        )
        if foreground_page_edit:
            for item in items:
                try:
                    self._update_page_row(indexer(item))
                except Exception:
                    pass

        # Drop stale events from a previous task before starting a new one.
        try:
            while True:
                self._batch_queue.get_nowait()
        except queue.Empty:
            pass

        total = len(items)
        labeler = item_label or (lambda item: str(item))

        def runner() -> None:
            results = []
            completed = 0
            try:
                for position, item in enumerate(items, 1):
                    while not self._batch_pause_event.wait(0.10):
                        if self._batch_stop_event.is_set():
                            break
                    if self._batch_stop_event.is_set():
                        break
                    label = labeler(item)
                    item_index = indexer(item) if foreground_page_edit else None
                    if foreground_page_edit:
                        with self._batch_state_lock:
                            state = self._batch_page_states.get(item_index, "pending")
                            if state == "manual_locked":
                                self._batch_skipped_count += 1
                                completed += 1
                                self._batch_queue.put(("skipped", completed, total, label, item_index))
                                continue
                            self._batch_page_states[item_index] = "processing"
                    self._batch_queue.put(("item", position, total, label, item_index))
                    result = worker(item, position, total)
                    results.append(result)
                    completed += 1
                    if foreground_page_edit:
                        with self._batch_state_lock:
                            if self._batch_page_states.get(item_index) == "processing":
                                self._batch_page_states[item_index] = "done"
                    self._batch_queue.put(("progress", completed, total, label, result, item_index))
                    if self._batch_stop_event.is_set():
                        break
                self._batch_queue.put(("done", completed, total, self._batch_stop_event.is_set(), results))
            except Exception as exc:
                self._batch_queue.put(("error", completed, total, exc, traceback.format_exc(), results))

        self._batch_thread = threading.Thread(target=runner, name=f"PictureCapture-{title}", daemon=True)
        self._batch_thread.start()
        self._batch_poll_job = self.after(80, self._poll_batch_queue)
        return True

    def _start_parallel_batch_task(
        self, title: str, items, worker_func, job_builder, result_consumer=None,
        on_done=None, item_label=None, max_workers: int = 0,
        *, allow_page_navigation: bool = False, allow_pdic_edits: bool = False,
    ) -> bool:
        """ start parallel batch task."""
        if self._batch_active:
            messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=self)
            return False
        if self._ui_worker_key_active("project-load"):
            self.status_var.set("项目仍在后台打开；完成后再启动批量任务。")
            return False
        if self._ui_worker_key_active("profile-validation"):
            self.status_var.set("Project Profile 测试仍在运行或安全结束中；完成后再启动批量任务。")
            return False
        if self._ui_worker_key_active("headword-order-finalize"):
            self.status_var.set("全项目词头顺序报告仍在汇总；完成后再启动新的批量任务。")
            return False
        if self._ui_close_requested:
            return False
        self._flush_deferred_page_save()
        items = list(items)
        if not items:
            self.status_var.set("没有需要处理的页面")
            return False

        workers = resolve_crop_worker_count(max_workers)
        # A one-worker request is intentionally routed through the existing
        # sequential runner, useful for low-memory machines and diagnostics.
        if workers <= 1:
            def serial_worker(item, position, total):
                args = job_builder(item, position, total)
                raw = worker_func(*args)
                return result_consumer(item, raw) if result_consumer is not None else raw
            return self._start_batch_task(
                title, items, serial_worker, on_done, item_label,
                allow_page_navigation=allow_page_navigation,
                allow_pdic_edits=allow_pdic_edits,
            )

        self._batch_active = True
        self._batch_parallel = True
        self._batch_allow_page_navigation = bool(allow_page_navigation)
        self._batch_allow_pdic_edits = bool(allow_pdic_edits)
        self._batch_title = title
        self._batch_on_done = on_done
        self._batch_stop_event.clear()
        self._batch_pause_event.set()
        self._batch_in_item = False
        self.batch_progress_var.set(0.0)
        self.batch_progress.configure(maximum=100.0)
        self.batch_text_var.set(f"{title}：准备并行处理 0/{len(items)}（{workers}进程）")
        self.batch_pause_button.configure(text="暂停", state="normal")
        self.batch_stop_button.configure(text="停止", state="normal")
        if not self.batch_bar.winfo_manager():
            self.batch_bar.pack(side="top", fill="x")
        self.status_var.set(
            f"{title}开始：共 {len(items)} 页，CPU并行 {workers} 进程。暂停/停止不会再派发新页面。"
        )

        try:
            while True:
                self._batch_queue.get_nowait()
        except queue.Empty:
            pass

        total = len(items)
        labeler = item_label or (lambda item: str(item))

        def runner() -> None:
            results = []
            completed = 0
            next_index = 0
            futures = {}
            context = multiprocessing.get_context("spawn")
            executor = ProcessPoolExecutor(max_workers=workers, mp_context=context)
            try:
                while True:
                    # Fill only the currently free worker slots. This is what
                    # makes pause/stop meaningful instead of pre-queuing all pages.
                    while (
                        self._batch_pause_event.is_set()
                        and not self._batch_stop_event.is_set()
                        and next_index < total
                        and len(futures) < workers
                    ):
                        item = items[next_index]
                        position = next_index + 1
                        label = labeler(item)
                        args = job_builder(item, position, total)
                        future = executor.submit(worker_func, *args)
                        futures[future] = (item, position, label)
                        next_index += 1
                        self._batch_queue.put((
                            "parallel_state", completed, total, len(futures), label, workers
                        ))

                    if not futures:
                        if self._batch_stop_event.is_set() or next_index >= total:
                            break
                        # Paused before all pages have been dispatched.
                        self._batch_pause_event.wait(0.10)
                        continue

                    done_set, _ = wait(tuple(futures), timeout=0.10, return_when=FIRST_COMPLETED)
                    if not done_set:
                        continue
                    for future in done_set:
                        item, _position, label = futures.pop(future)
                        raw = future.result()
                        result = result_consumer(item, raw) if result_consumer is not None else raw
                        results.append(result)
                        completed += 1
                        self._batch_queue.put((
                            "parallel_progress", completed, total, label, result, len(futures), workers
                        ))

                self._batch_queue.put((
                    "done", completed, total, self._batch_stop_event.is_set(), results
                ))
            except Exception as exc:
                self._batch_stop_event.set()
                self._batch_queue.put((
                    "error", completed, total, exc, traceback.format_exc(), results
                ))
            finally:
                executor.shutdown(wait=True, cancel_futures=True)

        self._batch_thread = threading.Thread(
            target=runner, name=f"PictureCapture-{title}-parallel", daemon=True
        )
        self._batch_thread.start()
        self._batch_poll_job = self.after(80, self._poll_batch_queue)
        return True

    def _poll_batch_queue(self) -> None:
        self._batch_poll_job = None
        finished = False
        # Limit both elapsed time and events per Tk callback.
        from .batch_progress_budget import (
            SATURATED_BATCH_POLL_DELAY_MS, batch_poll_should_yield,
            start_batch_poll_budget,
        )
        processed_events = 0
        poll_started = start_batch_poll_budget()
        yielded = False
        while True:
            try:
                event = self._batch_queue.get_nowait()
            except queue.Empty:
                break
            processed_events += 1
            kind = event[0]
            if kind == "item":
                _kind, position, total, label, item_index = event
                self._batch_in_item = True
                if item_index is not None:
                    self._update_page_row(int(item_index))
                    if int(item_index) == self.current_index:
                        self.redraw()
                self.batch_text_var.set(f"{self._batch_title} {position}/{total}：{label}")
                if self._batch_foreground_pages:
                    self.status_var.set(f"{self._batch_title} {position}/{total}：{label}（可同时校对其他页面）")
                else:
                    self.status_var.set(f"{self._batch_title} {position}/{total}：{label}（可暂停或停止）")
            elif kind == "skipped":
                _kind, completed, total, label, item_index = event
                self.batch_progress_var.set(100.0 * completed / max(1, total))
                self._update_page_row(int(item_index))
                self.batch_text_var.set(f"{self._batch_title}：{completed}/{total}，人工锁定跳过 {label}")
                self.status_var.set(f"后台已跳过人工锁定页 {label}；你的校对内容不会被覆盖。")
            elif kind == "progress":
                _kind, completed, total, label, _result, item_index = event
                self._batch_in_item = False
                self.batch_progress_var.set(100.0 * completed / max(1, total))
                if item_index is not None:
                    self._update_page_row(int(item_index))
                    if int(item_index) == self.current_index and self._foreground_batch_state(int(item_index)) == "done":
                        # Same index reload does not save the stale foreground copy.
                        self.load_page(int(item_index))
                if not self._batch_pause_event.is_set() and not self._batch_stop_event.is_set():
                    self.batch_text_var.set(f"{self._batch_title}：已暂停 {completed}/{total}")
                    self.status_var.set(f"{self._batch_title}已暂停：完成 {completed}/{total} 页；点击“继续”恢复。")
                elif self._batch_stop_event.is_set():
                    self.batch_text_var.set(f"{self._batch_title}：正在安全停止 {completed}/{total}")
                else:
                    self.batch_text_var.set(f"{self._batch_title}：已完成 {completed}/{total}：{label}")
                    self.status_var.set(f"{self._batch_title}：已完成 {completed}/{total} 页，最近完成 {label}")
            elif kind == "parallel_state":
                _kind, completed, total, active, label, workers = event
                self._batch_in_item = active > 0
                self.batch_text_var.set(
                    f"{self._batch_title}：{completed}/{total}，并行 {active}/{workers} 页"
                )
                self.status_var.set(
                    f"{self._batch_title}并行处理中：完成 {completed}/{total}，当前 {active} 页运行；最近派发 {label}"
                )
            elif kind == "parallel_progress":
                _kind, completed, total, label, _result, active, workers = event
                self._batch_in_item = active > 0
                self.batch_progress_var.set(100.0 * completed / max(1, total))
                if not self._batch_pause_event.is_set() and not self._batch_stop_event.is_set():
                    if active:
                        self.batch_text_var.set(
                            f"{self._batch_title}：暂停中 {completed}/{total}（等待 {active} 页完成）"
                        )
                        self.status_var.set("暂停请求已生效：不再派发新页面；已启动页面完成后完全暂停。")
                    else:
                        self.batch_text_var.set(f"{self._batch_title}：已暂停 {completed}/{total}")
                        self.status_var.set(f"{self._batch_title}已暂停：完成 {completed}/{total} 页；点击“继续”恢复。")
                elif self._batch_stop_event.is_set():
                    self.batch_text_var.set(
                        f"{self._batch_title}：正在安全停止 {completed}/{total}（剩余运行 {active} 页）"
                    )
                else:
                    self.batch_text_var.set(
                        f"{self._batch_title}：已完成 {completed}/{total}（并行 {active}/{workers} 页）"
                    )
            elif kind == "done":
                _kind, completed, total, stopped, results = event
                finished = True
                self._finish_batch_task(completed, total, stopped, results, None)
            elif kind == "error":
                _kind, completed, total, exc, detail, results = event
                finished = True
                self._finish_batch_task(completed, total, True, results, (exc, detail))

            if not finished and batch_poll_should_yield(processed_events, poll_started):
                yielded = True
                break

        if self._batch_active and not finished:
            # Let Tk service button clicks before draining the backlog.
            delay = SATURATED_BATCH_POLL_DELAY_MS if yielded else 80
            self._batch_poll_job = self.after(delay, self._poll_batch_queue)

    def _finish_batch_task(self, completed: int, total: int, stopped: bool, results, error) -> None:
        callback = self._batch_on_done
        title = self._batch_title
        self._batch_active = False
        self._batch_in_item = False
        self._batch_parallel = False
        self._batch_pause_event.set()
        self.batch_pause_button.configure(text="暂停", state="disabled")
        self.batch_stop_button.configure(text="停止", state="disabled")
        if error is None:
            self.batch_progress_var.set(100.0 * completed / max(1, total))
            if stopped:
                self.batch_text_var.set(f"{title}：已停止，完成 {completed}/{total}")
                self.status_var.set(f"{title}已安全停止：已完成 {completed}/{total} 页，已完成结果均已保留。")
            else:
                self.batch_text_var.set(f"{title}：完成 {completed}/{total}")
        else:
            exc, detail = error
            self.batch_text_var.set(f"{title}：发生错误，完成 {completed}/{total}")
            print(detail)
            self.show_error(f"{title}失败", exc)

        if callback is not None:
            try:
                callback(completed, total, stopped, results, error)
            except Exception as callback_exc:
                self.show_error(f"{title}完成处理失败", callback_exc)

        self._batch_thread = None
        self._batch_on_done = None
        self._batch_title = ""
        self._batch_foreground_pages = False
        self._batch_allow_page_navigation = False
        self._batch_allow_pdic_edits = False
        with self._batch_state_lock:
            self._batch_page_states = {}
        if getattr(self, "_batch_refresh_page_quality", True):
            self._refresh_page_quality_colors()
        self._batch_refresh_page_quality = True
        self.after(1800, self._hide_batch_bar_if_idle)
        if self._batch_close_after_stop:
            self._batch_close_after_stop = False
            self.after_idle(self.on_close)

    def _hide_batch_bar_if_idle(self) -> None:
        if not self._batch_active and self.batch_bar.winfo_manager():
            self.batch_bar.pack_forget()

    def _toggle_batch_pause(self) -> None:
        if not self._batch_active:
            return
        if self._batch_pause_event.is_set():
            self._batch_pause_event.clear()
            self.batch_pause_button.configure(text="继续")
            if getattr(self, "_batch_in_item", False):
                self.batch_text_var.set(f"{self._batch_title}：暂停请求已发出")
                if getattr(self, "_batch_parallel", False):
                    self.status_var.set("暂停请求已发出：不再派发新页面；已启动的并行页面完成后暂停。")
                else:
                    self.status_var.set("暂停请求已发出：当前页处理完成后暂停，不会中断正在写入的文件。")
            else:
                self.batch_text_var.set(f"{self._batch_title}：已暂停")
                self.status_var.set("批量任务已暂停；点击“继续”恢复。")
        else:
            self._batch_pause_event.set()
            self.batch_pause_button.configure(text="暂停")
            self.batch_text_var.set(f"{self._batch_title}：继续处理中…")
            self.status_var.set("批量任务继续运行。")

    def _request_batch_stop(self) -> None:
        if not self._batch_active:
            return
        self._batch_stop_event.set()
        # Wake a task that is currently paused so the worker can observe stop.
        self._batch_pause_event.set()
        self.batch_pause_button.configure(state="disabled")
        self.batch_stop_button.configure(state="disabled")
        self.batch_text_var.set(f"{self._batch_title}：停止请求已发出")
        if getattr(self, "_batch_parallel", False):
            self.status_var.set("停止请求已发出：不再派发新页面；已启动页面完成后安全停止，已完成结果保留。")
        else:
            self.status_var.set("停止请求已发出：当前页处理完成后安全停止；已完成页面结果会保留。")

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
        dialog = tk.Toplevel(self)
        dialog.title("项目中心")
        dialog.transient(self)
        self._recent_projects_dialog = dialog

        screen_w = max(900, int(dialog.winfo_screenwidth()))
        screen_h = max(650, int(dialog.winfo_screenheight()))
        width = min(screen_w - 80, max(780, int(screen_w * 0.58)))
        height = min(screen_h - 100, max(520, int(screen_h * 0.68)))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.minsize(min(760, width), min(460, height))

        default_font = font.nametofont("TkDefaultFont").copy()
        title_font = default_font.copy()
        title_font.configure(size=max(14, abs(int(default_font.cget("size"))) + 6), weight="bold")
        card_title_font = default_font.copy()
        card_title_font.configure(size=max(11, abs(int(default_font.cget("size"))) + 2), weight="bold")
        meta_font = default_font.copy()
        meta_size = int(default_font.cget("size"))
        meta_font.configure(size=max(8, abs(meta_size) - 1) * (-1 if meta_size < 0 else 1))

        host = ttk.Frame(dialog, padding=(20, 16, 20, 18))
        host.pack(fill="both", expand=True)
        host.columnconfigure(0, weight=1)
        host.rowconfigure(3, weight=1)

        header = ttk.Frame(host)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="最近项目", font=title_font).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            header,
            text="继续上次工作；最近打开的项目排在最前。路径失效的记录可从列表清理，不会删除项目文件。",
            foreground="#666666",
            wraplength=max(520, width - 80),
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        tools = ttk.Frame(host)
        tools.grid(row=1, column=0, sticky="ew", pady=(14, 8))
        tools.columnconfigure(1, weight=1)
        search_var = tk.StringVar(value="")
        ttk.Label(tools, text="搜索项目").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(tools, textvariable=search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 10))
        count_var = tk.StringVar(value="")
        ttk.Label(tools, textvariable=count_var, foreground="#666666").grid(
            row=0, column=2, sticky="e"
        )

        def create_new_project() -> None:
            try:
                dialog.destroy()
            finally:
                self.open_project()

        ttk.Separator(host, orient="horizontal").grid(
            row=2, column=0, sticky="ew", pady=(0, 10)
        )

        list_host = ttk.Frame(host)
        list_host.grid(row=3, column=0, sticky="nsew")
        list_host.columnconfigure(0, weight=1)
        list_host.rowconfigure(0, weight=1)
        canvas = tk.Canvas(list_host, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(list_host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        cards = ttk.Frame(canvas)
        cards.columnconfigure(0, weight=1)
        cards_window = canvas.create_window((0, 0), window=cards, anchor="nw")
        cards.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(cards_window, width=event.width),
        )

        state: dict[str, object] = {
            "rows": [], "details": [], "cover_images": {}, "cover_photos": [],
        }

        def open_selected(root: Path, row: dict[str, object]) -> None:
            if not root.is_dir():
                messagebox.showerror(
                    "无法打开项目", f"项目路径不存在：\n{root}", parent=dialog
                )
                return
            try:
                self._load_project(
                    root,
                    target_page=str(row.get("last_page") or "").strip() or None,
                    target_index=row.get("last_page_index"),
                )
            except Exception as exc:
                messagebox.showerror("无法打开项目", str(exc), parent=dialog)
                return
            dialog.destroy()

        from .project_folder_launcher import add_open_folder_button

        def copy_path(root: Path) -> None:
            dialog.clipboard_clear()
            dialog.clipboard_append(str(root))
            self.status_var.set("项目路径已复制")

        def remove_one(root: Path) -> None:
            remove_recent_project(root)
            refresh_recent_data()

        def remove_missing() -> None:
            missing = [
                Path(str(detail["path"]))
                for detail in state.get("details", [])
                if not bool(detail["exists"])
            ]
            if not missing:
                return
            if not messagebox.askyesno(
                "清理失效项目",
                f"从最近项目列表移除 {len(missing)} 个路径失效的记录？\n\n"
                "只清理列表记录，不会删除任何项目文件。",
                parent=dialog,
            ):
                return
            for root in missing:
                remove_recent_project(root)
            refresh_recent_data()

        cleanup_button = ttk.Button(
            tools, text="清理失效项", command=remove_missing, state="disabled"
        )
        cleanup_button.grid(row=0, column=3, sticky="e", padx=(10, 0))
        ttk.Button(
            tools, text="新建项目", command=create_new_project
        ).grid(row=0, column=4, sticky="e", padx=(8, 0))

        def bind_open(widget, root: Path, row: dict[str, object]) -> None:
            try:
                widget.configure(cursor="hand2")
            except tk.TclError:
                pass
            widget.bind(
                "<Button-1>",
                lambda _event, p=root, r=dict(row): open_selected(p, r),
            )

        def card_menu(button: ttk.Button, root: Path) -> None:
            pinned = any(
                str(row.get("path")) == str(root) and bool(row.get("pinned"))
                for row in state["rows"]
            )
            menu = tk.Menu(dialog, tearoff=False)
            self._apply_current_appearance(menu)
            menu.add_command(label="复制项目路径", command=lambda: copy_path(root))
            menu.add_command(
                label="取消置顶" if pinned else "置顶项目",
                command=lambda: (set_recent_project_pinned(root, not pinned), refresh_recent_data()),
            )
            menu.add_separator()
            from .project_center_metadata_cache import clear_cached_details
            menu.add_command(
                label="重新扫描项目元数据",
                command=lambda p=root: (clear_cached_details(p), refresh_recent_data()),
            )
            menu.add_command(
                label="从最近项目移除（不删除文件）",
                command=lambda: remove_one(root),
            )
            menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())

        def rebuild(*_args) -> None:
            for child in cards.winfo_children():
                child.destroy()
            state["cover_photos"] = []

            rows = list(state.get("rows", []))
            details = list(state.get("details", []))
            covers = dict(state.get("cover_images", {}))
            query = search_var.get().strip().casefold()

            paired = []
            for row, detail in zip(rows, details):
                haystack = " ".join((
                    str(detail["full_name"]),
                    str(detail["abbreviation"]),
                    str(detail["path"]),
                    str(detail.get("last_page") or ""),
                )).casefold()
                if query and query not in haystack:
                    continue
                paired.append((row, detail))

            missing_count = sum(1 for detail in details if not bool(detail["exists"]))
            count_var.set(
                f"{len(paired)} 个项目"
                + (f" · {missing_count} 个路径失效" if missing_count else "")
            )
            cleanup_button.configure(state="normal" if missing_count else "disabled")

            if not paired:
                empty = ttk.Frame(cards, padding=(18, 50))
                empty.grid(row=0, column=0, sticky="ew")
                ttk.Label(empty, text="没有匹配的项目" if query else "还没有最近项目", font=card_title_font).pack()
                ttk.Label(
                    empty,
                    text="换一个关键词试试。" if query else "打开或新建项目后，它会出现在这里。",
                    foreground="#777777",
                ).pack(pady=(6, 0))
                return

            for row_index, (row, detail) in enumerate(paired):
                root = Path(str(detail["path"]))
                exists = bool(detail["exists"])
                card = ttk.Frame(cards, padding=(14, 11), relief="solid", borderwidth=1)
                card.grid(row=row_index, column=0, sticky="ew", padx=(2, 8), pady=(0, 9))
                card.columnconfigure(1, weight=1)

                full_name = str(detail["full_name"] or root.name)
                abbreviation = str(detail["abbreviation"] or "").strip()
                tile_text = (abbreviation or full_name or "?")[:2].upper()
                cover_source = str(detail.get("cover_source") or "none")
                tile_holder = tk.Frame(
                    card, width=76, height=96,
                    bg="#f4f6f8" if exists else "#f2f2f2", bd=0, relief="flat",
                )
                tile_holder.grid_propagate(False)
                tile = tk.Label(
                    tile_holder, bg="#f4f6f8" if exists else "#f2f2f2",
                    fg="#315a97" if exists else "#777777", font=card_title_font,
                    bd=0, relief="flat", compound="center",
                )
                tile.place(x=0, y=0, relwidth=1, relheight=1)
                cover_image = covers.get(str(root))
                if isinstance(cover_image, Image.Image):
                    cover_photo = ImageTk.PhotoImage(
                        themed_display_image(cover_image, self.appearance_mode)
                    )
                    state["cover_photos"].append(cover_photo)
                    tile.configure(image=cover_photo)
                else:
                    tile.configure(text=tile_text, bg="#eaf0fb" if exists else "#f2f2f2")
                tile_holder.grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, 12))

                if cover_source == "cover":
                    cover_tip = "项目封面。可替换项目图片文件夹中的 _cover.jpg（也支持 PNG/JPEG/WebP；兼容旧名 _project_cover.*）；该文件不会计入正文图片。"
                elif cover_source == "first_page":
                    cover_tip = "当前用项目第一张图片作为预览。可在项目图片文件夹放置 _cover.jpg（也支持 PNG/JPEG/WebP；兼容旧名 _project_cover.*）作为项目封面；该文件不会计入正文图片。"
                else:
                    cover_tip = "暂无封面预览。可在项目图片文件夹放置 _cover.jpg（也支持 PNG/JPEG/WebP；兼容旧名 _project_cover.*）作为项目封面；该文件不会计入正文图片。"
                self._attach_tooltip(tile_holder, cover_tip)
                self._attach_tooltip(tile, cover_tip)

                content = ttk.Frame(card)
                content.grid(row=0, column=1, rowspan=3, sticky="nsew")
                content.columnconfigure(0, weight=1)
                title_row = ttk.Frame(content)
                title_row.grid(row=0, column=0, sticky="ew")
                name_label = ttk.Label(title_row, text=("📌 " if row.get("pinned") else "") + full_name, font=card_title_font)
                name_label.pack(side="left")
                if abbreviation:
                    ttk.Label(title_row, text=f"  ·  {abbreviation}", foreground="#666666").pack(side="left")
                status = tk.Label(
                    title_row, text="检查中" if detail.get("checking") else ("可用" if exists else "路径失效"), padx=8, pady=2,
                    bg="#e9f6ee" if exists else "#fff0ee", fg="#247245" if exists else "#b42318",
                    font=meta_font,
                )
                status.pack(side="left", padx=(10, 0))
                image_count = int(detail["image_count"])
                position_text = str(detail.get("position_text") or "—")
                last_page = str(detail.get("last_page") or "").strip()
                resume = f"{last_page} · {position_text}" if last_page and position_text != last_page else position_text
                meta_text = f"{image_count:,} 张图片    ·    上次停留：{resume}    ·    最近活动：{detail['last_edited'] or '—'}"
                meta_label = ttk.Label(content, text=meta_text, foreground="#555555")
                meta_label.grid(row=1, column=0, sticky="w", pady=(5, 0))
                path_label = ttk.Label(content, text=str(root), foreground="#888888" if exists else "#b42318", font=meta_font)
                path_label.grid(row=2, column=0, sticky="ew", pady=(5, 0))

                actions = ttk.Frame(card)
                actions.grid(row=0, column=2, rowspan=3, sticky="ne", padx=(12, 0))
                open_button = ttk.Button(
                    actions, text="打开", command=lambda p=root, r=dict(row): open_selected(p, r),
                    state="normal" if exists else "disabled", width=8,
                )
                open_button.pack(side="left")
                add_open_folder_button(actions, root, dialog, exists)
                more_button = ttk.Button(actions, text="⋯", width=3)
                more_button.configure(command=lambda b=more_button, p=root: card_menu(b, p))
                more_button.pack(side="left", padx=(5, 0))
                if exists:
                    for widget in (card, tile_holder, tile, content, title_row, name_label, meta_label, path_label):
                        bind_open(widget, root, row)

                def update_wrap(_event=None, label=path_label, owner=content) -> None:
                    try:
                        label.configure(wraplength=max(240, owner.winfo_width() - 10))
                    except tk.TclError:
                        pass
                content.bind("<Configure>", update_wrap, add="+")
                self._attach_tooltip(path_label, "项目路径；单击打开项目。" if exists else "该路径当前不存在。")
            canvas.yview_moveto(0.0)
            self._apply_current_appearance(dialog)

        def refresh_recent_data() -> None:
            count_var.set("正在后台读取最近项目…")
            cleanup_button.configure(state="disabled")
            key = f"recent-projects-{id(dialog)}"
            # A previous refresh may still be decoding preview images.
            self._invalidate_ui_worker(f"{key}-previews")
            self._invalidate_ui_worker(f"{key}-details")

            def worker():
                return load_recent_projects()

            from .project_center_preview_cache import load_project_center_previews

            def alive() -> bool:
                try:
                    return bool(dialog.winfo_exists())
                except tk.TclError:
                    return False

            def previews_done(covers) -> None:
                if not alive():
                    return
                state["cover_images"] = covers
                rebuild()

            from .project_center_metadata_cache import details_with_cache

            def details_done(details) -> None:
                if not alive():
                    return
                state["details"] = details
                rebuild()
                self._start_ui_worker(
                    f"{key}-previews",
                    lambda: load_project_center_previews(details),
                    previews_done,
                )

            def done(rows) -> None:
                if not alive():
                    return
                state["rows"] = rows
                state["details"] = [recent_project_stub_details(row) for row in rows]
                state["cover_images"] = {}
                # First paint is independent of per-project directory scanning.
                rebuild()
                self._start_ui_worker(
                    f"{key}-details",
                    lambda: details_with_cache(rows),
                    details_done,
                    failed,
                )

            def failed(exc, detail) -> None:
                if detail:
                    print(detail)
                if alive():
                    count_var.set(f"读取最近项目失败：{exc}")
            self._start_ui_worker(key, worker, done, failed)

        self._recent_projects_rebuild = rebuild

        def clear_recent_refs(event=None) -> None:
            if event is not None and getattr(event, "widget", None) is not dialog:
                return
            if self.__dict__.get("_recent_projects_dialog") is dialog:
                self.__dict__.pop("_recent_projects_dialog", None)
                self.__dict__.pop("_recent_projects_rebuild", None)

        dialog.bind("<Destroy>", clear_recent_refs, add="+")
        search_var.trace_add("write", rebuild)
        search_entry.bind("<Escape>", lambda _event: search_var.set(""))
        dialog.bind(
            "<MouseWheel>",
            lambda event: canvas.yview_scroll(
                (-1 if int(getattr(event, "delta", 0) or 0) > 0 else 1) * 3,
                "units",
            ),
            add="+",
        )
        dialog.bind(
            "<Button-4>", lambda _event: canvas.yview_scroll(-3, "units"), add="+"
        )
        dialog.bind(
            "<Button-5>", lambda _event: canvas.yview_scroll(3, "units"), add="+"
        )

        refresh_recent_data()
        search_entry.focus_set()


    @staticmethod
    def _attach_tooltip(widget: tk.Widget, message: str) -> None:
        """Attach a lightweight native Tk tooltip without external dependencies."""
        popup: list[tk.Toplevel | None] = [None]

        def show(_event=None) -> None:
            if popup[0] is not None:
                return
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{widget.winfo_rootx() + 12}+{widget.winfo_rooty() + widget.winfo_height() + 4}")
            ttk.Label(tip, text=message, padding=(6, 3), relief="solid").pack()
            popup[0] = tip

        def hide(_event=None) -> None:
            if popup[0] is not None:
                popup[0].destroy()
                popup[0] = None

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<Destroy>", hide, add="+")

    def _project_controller_for_call(self) -> ProjectController:
        controller = self.__dict__.get("project_controller")
        if controller is None:
            controller = ProjectController(self)
            self.__dict__["project_controller"] = controller
        return controller

    def _choose_new_project_image_suffix(self, root: Path) -> str | None:
        return self._project_controller_for_call().choose_new_project_image_suffix(root)


    def open_project(self) -> None:
        self._project_controller_for_call().open_project()


    def _load_project(
        self, root: Path, *, requested_suffix: str | None = None,
        target_page: str | None = None, target_index: object = None,
        target_view_scale: float | None = None,
        launch_profile_setup: bool = False,
        parameter_template_root: Path | None = None,
    ) -> None:
        """Prepare project files off-thread and commit the prepared state on Tk."""
        if self._batch_active:
            self.status_var.set("批量任务运行中，结束或停止后再切换项目。")
            return
        if self._ui_worker_key_active("project-load"):
            self.status_var.set("已有项目正在后台打开，请完成后再选择其他项目。")
            return
        if self._ui_worker_key_active("profile-validation"):
            self.status_var.set("Project Profile 测试仍在安全结束；完成后再切换项目。")
            return
        if self._preprocess_mode_active():
            self._set_preprocess_mode(False, analyze=False)
        root = root.expanduser().resolve()
        if self.project is not None and root == Path(self.project.root).expanduser().resolve():
            self.status_var.set("当前项目已经打开；保留当前编辑状态，不执行后台重载。")
            return
        self._flush_deferred_page_save()
        for job_name in ("_page_meta_job", "_page_list_sort_job"):
            job = getattr(self, job_name, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, job_name, None)
        self._page_meta_generation = int(getattr(self, "_page_meta_generation", 0)) + 1
        pending_quick_job = getattr(self, "_quick_autosave_job", None)
        if pending_quick_job is not None:
            try:
                self.after_cancel(pending_quick_job)
            except tk.TclError:
                pass
            self._quick_autosave_job = None
            if self.project is not None:
                self.apply_quick_settings(show_status=False, persist=True, silent_errors=True)
        if self.project and self.current_page and self.image is not None:
            self.save_pdic(silent=True)
            write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
            self.settings.to_json(settings_path(self.project.root))

        migrate = False
        if has_legacy_project_data(root) and not is_managed_project(root):
            migrate = messagebox.askyesno(
                "整理旧版项目",
                "检测到旧版 Picture Capture 项目结构。\n\n"
                f"建议把软件生成的数据集中整理到 {STORAGE_DIRNAME} 文件夹。"
                "原始扫描图片和 wordslist.txt 等用户文件不会移动。\n\n"
                "选择“是”将在后台安全整理；选择“否”则本次继续使用旧目录结构。",
                parent=self,
            )
        canvas_available = max(500, int(self.canvas.winfo_width()) - 24)
        appearance_mode = self.appearance_mode
        self.status_var.set(f"正在后台打开项目：{root}")

        def worker():
            migration_detail = ""
            if migrate:
                from . import __version__
                report = migrate_legacy_project(root, __version__)
                migration_detail = f"已整理 {report.files_copied} 个文件到 {STORAGE_DIRNAME}"
                if report.warnings:
                    migration_detail += f"；{len(report.warnings)} 项旧文件未能清理，可稍后手工检查"
            project = ProjectState.open(root)
            if launch_profile_setup:
                _project_templates.apply_parameters_to_project(project, parameter_template_root)
            if not project.images:
                raise ValueError("目录中没有 tif/tiff/png/jpg/jpeg/bmp 图片")
            suffix = PictureCaptureApp._normalize_suffix(requested_suffix) if requested_suffix else PictureCaptureApp._normalize_suffix(project.settings.image_suffix)
            matching = [page for page in project.images if page.suffix.lower() == suffix]
            if matching:
                project.images = matching
                project.settings.image_suffix = suffix
            else:
                project.settings.image_suffix = project.images[0].suffix.lower()

            selected_index = 0
            if target_page:
                for index, page in enumerate(project.images):
                    if page.name == target_page or page.stem == Path(target_page).stem:
                        selected_index = index
                        break
                else:
                    try:
                        numeric = int(target_index)
                        if 0 <= numeric < len(project.images):
                            selected_index = numeric
                    except (TypeError, ValueError):
                        pass
            else:
                try:
                    numeric = int(target_index)
                    if 0 <= numeric < len(project.images):
                        selected_index = numeric
                except (TypeError, ValueError):
                    pass

            page = project.images[selected_index]
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            entries = read_pdic(pdic_path(page))
            polygons = read_ppp(ppp_read_path_for_image(page))
            page_sections = read_page_sections(page)
            cache_path = ocr_cache_root(project.root) / f"{page.stem}.json"
            ocr_payload: dict = {}
            if cache_path.exists():
                try:
                    loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        ocr_payload = loaded
                except Exception:
                    ocr_payload = {}
            if target_view_scale is None:
                view_scale = min(1.0, canvas_available / max(1, image.width))
            else:
                view_scale = min(3.0, max(0.08, float(target_view_scale)))
            display_size = (
                max(1, round(image.width * view_scale)),
                max(1, round(image.height * view_scale)),
            )
            display_image = themed_display_image(
                image.resize(display_size, Image.Resampling.LANCZOS),
                appearance_mode,
            )
            payload = {
                "project_root": str(project.root), "index": selected_index, "image": image,
                "entries": entries, "polygons": polygons, "page_sections": page_sections,
                "ocr_payload": ocr_payload,
                "display_size": display_size, "display_image": display_image,
                "view_scale": view_scale, "appearance_mode": appearance_mode,
            }
            try:
                touch_recent_project(project.root)
                recent_warning = ""
            except (OSError, ValueError, TypeError) as exc:
                recent_warning = str(exc)
            return project, selected_index, payload, view_scale, migration_detail, recent_warning

        def done(result) -> None:
            project, selected_index, payload, view_scale, migration_detail, recent_warning = result
            if self.project and self.current_page and self.image is not None:
                self._flush_deferred_page_save()
                self.save_pdic(silent=True)
                write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
                self.settings.to_json(settings_path(self.project.root))
            self._pending_page_index = None
            self._invalidate_ui_worker("page-load")
            self.current_page = None
            self.image = None
            self.entries = []
            self.polygons = []
            self.page_sections = []
            self._section_editing = False
            self._drag_section_boundary = None
            self._pending_section_editor_index = None
            self.current_index = -1
            self.ocr_review_candidates = []
            self.candidate_check_vars = {}
            self._display_photo_cache_key = None
            self._display_geometry_cache = None
            self._display_geometry_cache_key = None
            self.project = project
            self._project_words = set(project.words)
            self.settings = project.settings
            self._preprocess_results.clear()
            self._preprocess_photo = None
            self._preprocess_photo_cache_key = None
            self.preprocess_auto_deskew_var.set(
                bool(self.settings.preprocess_auto_deskew)
            )
            self.preprocess_safety_var.set(
                str(int(self.settings.preprocess_safety_margin_px))
            )
            self.preprocess_geometry_var.set(
                {
                    "deskew": "轻量：旋转+裁边",
                    "perspective": "自动透视",
                    "dewarp": "UVDoc展平（Paddle高级）",
                    "uvdoc": "UVDoc展平（Paddle高级）",
                    "auto": "自动几何（推荐）",
                }.get(
                    str(
                        getattr(
                            self.settings, "preprocess_geometry_mode", "auto"
                        ) or "auto"
                    ),
                    "自动几何（推荐）",
                )
            )
            self.preprocess_export_canvas_var.set(
                bool(
                    getattr(
                        self.settings,
                        "preprocess_export_canvas_enabled",
                        False,
                    )
                )
            )
            self.preprocess_export_canvas_mode_var.set(
                {
                    "batch_max": "本批最大裁剪尺寸",
                    "custom": "自定义尺寸",
                }.get(
                    str(
                        getattr(
                            self.settings,
                            "preprocess_export_canvas_mode",
                            "batch_max",
                        ) or "batch_max"
                    ),
                    "本批最大裁剪尺寸",
                )
            )
            self.preprocess_export_canvas_width_var.set(
                str(
                    int(
                        getattr(
                            self.settings,
                            "preprocess_export_canvas_width",
                            0,
                        ) or 0
                    )
                )
            )
            self.preprocess_export_canvas_height_var.set(
                str(
                    int(
                        getattr(
                            self.settings,
                            "preprocess_export_canvas_height",
                            0,
                        ) or 0
                    )
                )
            )
            self.preprocess_export_margin_top_var.set(
                str(int(getattr(self.settings, "preprocess_export_margin_top", 0) or 0))
            )
            self.preprocess_export_margin_bottom_var.set(
                str(int(getattr(self.settings, "preprocess_export_margin_bottom", 0) or 0))
            )
            self.preprocess_export_margin_left_var.set(
                str(int(getattr(self.settings, "preprocess_export_margin_left", 0) or 0))
            )
            self.preprocess_export_margin_right_var.set(
                str(int(getattr(self.settings, "preprocess_export_margin_right", 0) or 0))
            )
            self.preprocess_export_align_x_var.set(
                {
                    "left": "左对齐",
                    "center": "居中",
                    "right": "右对齐",
                }.get(
                    str(
                        getattr(
                            self.settings,
                            "preprocess_export_align_x",
                            "center",
                        ) or "center"
                    ),
                    "居中",
                )
            )
            self.preprocess_export_align_y_var.set(
                {
                    "top": "顶端对齐",
                    "center": "居中",
                    "bottom": "底部对齐",
                }.get(
                    str(
                        getattr(
                            self.settings,
                            "preprocess_export_align_y",
                            "top",
                        ) or "top"
                    ),
                    "顶端对齐",
                )
            )
            self.preprocess_status_var.set("未分析")
            if recent_warning:
                self._recent_projects_warning = recent_warning
            if hasattr(self, "_page_column_vars"):
                self._page_column_vars["lined"].set(bool(getattr(self.settings, "page_list_show_lined", True)))
                self._page_column_vars["fill_status"].set(bool(getattr(self.settings, "page_list_show_fill_status", False)))
                self._page_column_vars["illustrations"].set(bool(getattr(self.settings, "page_list_show_illustrations", True)))
                self._apply_page_list_display_columns(save=False)
            self.hide_var.set(bool(self.settings.hide_overlays))
            self.polygon_var.set(bool(self.settings.polygon_mode))
            self.polygon_draw_var.set(False)
            if self.polygon_draw_button is not None:
                self.polygon_draw_button.configure(text="编辑插图", style="PC.Compact.TButton")
            trace_was_ready = self._quick_trace_ready
            self._quick_trace_ready = False
            try:
                self.sync_quick_settings()
            finally:
                self._quick_trace_ready = trace_was_ready
            self._display_geometry_cache = None
            self._display_geometry_cache_key = None
            self._page_meta_generation += 1
            generation = self._page_meta_generation
            self._word_fill_mismatch_pages.clear()
            self._word_fill_check_status = {}
            self._word_fill_source_path = None
            self._old_new_compare_source_path = None
            old_compare = self.old_new_compare_window
            if old_compare is not None:
                try:
                    if old_compare.winfo_exists():
                        old_compare.destroy()
                except tk.TclError:
                    pass
                self.old_new_compare_window = None
            self._word_fill_source_signature = None
            self._word_fill_source_mapping = None
            self._word_fill_source_present_pages = None
            self._load_word_fill_status()
            self._clear_lined_cell_overlays()
            for item in self.page_list.get_children():
                self.page_list.delete(item)
            for index, page in enumerate(project.images):
                self.page_list.insert(
                    "", "end", iid=str(index), values=(
                        "●" if page.stem in self._bookmark_stems() else "",
                        page.stem, self._page_section_count_text(index),
                        "", self._word_fill_status_text(index), "",
                    ),
                )
            if self._page_list_sort_column:
                self._apply_page_list_sort(ensure_current_visible=False)
            else:
                self._update_page_list_sort_headings()
            self._page_meta_job = self.after_idle(lambda g=generation: self._refresh_page_metadata_step(g, 0))
            self.view_scale = view_scale
            self._set_page_list_selection(selected_index, ensure_visible=True)
            self.load_page(selected_index, preloaded=payload, skip_current_save=True)
            self._save_session_state()
            if launch_profile_setup:
                # A new project starts from the documented release workspace even
                # when the previous project/session left other sections expanded.
                # Existing projects still restore the user's remembered session.
                self._apply_new_project_sidebar_defaults()
            storage_hint = f"｜数据目录 {STORAGE_DIRNAME}" if is_managed_project(project.root) else "｜旧版目录结构"
            prefix = f"{migration_detail}｜" if migration_detail else ""
            self.status_var.set(
                f"{prefix}已打开 {project.root}｜{len(project.images)} 页｜图片后缀 {self.settings.image_suffix}｜词表 {len(project.words)} 条{storage_hint}"
            )
            if launch_profile_setup:
                self.after_idle(lambda: self.open_project_profile(new_project=True))

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            self.show_error("无法打开项目", exc)

        self._start_ui_worker(
            "project-load", worker, done, failed, wait_on_close=True,
        )

    def on_page_select(self, _event: tk.Event) -> None:
        self.page_controller.on_page_select(_event)

    def _request_page_load(
        self, index: int, *, reset_zoom: bool = False,
        current_already_saved: bool = False, force: bool = False,
    ) -> bool:
        return self.page_controller.request_page_load(
            index,
            reset_zoom=reset_zoom,
            current_already_saved=current_already_saved,
            force=force,
        )

    def load_page(
        self, index: int, reset_zoom: bool = False, *,
        preloaded: dict | None = None, skip_current_save: bool = False,
    ) -> None:
        if not self.project or not (0 <= index < len(self.project.images)):
            return
        self._pending_page_index = None
        self._invalidate_ui_worker("page-load")
        self._flush_deferred_page_save()
        if (
            self.current_page and self.image and index != self.current_index
            and not skip_current_save and not self._preprocess_mode_active()
        ):
            if self._can_save_current_during_batch_navigation():
                self._save_current_page_by_mode()
        self.current_index = index; self.current_page = self.project.images[index]
        self._auxiliary_controller.load_page(self.current_page)
        use_preloaded = bool(
            preloaded
            and preloaded.get("index") == index
            and preloaded.get("project_root") == str(self.project.root)
            and isinstance(preloaded.get("image"), Image.Image)
        )
        from .image_metadata_status import image_dpi, image_status
        if use_preloaded:
            source_dpi = preloaded.get("source_dpi")
            self.image = preloaded["image"]
            self.page_sections = list(preloaded.get("page_sections") or [])
            self.entries = list(preloaded.get("entries") or [])
            self._sort_entries_reading_order()
            ocr_payload = preloaded.get("ocr_payload") if isinstance(preloaded.get("ocr_payload"), dict) else {}
            self.ocr_review_candidates = list(ocr_payload.get("review_candidates") or [])
            self._restore_entry_ocr_metadata(ocr_payload)
            self.polygons = list(preloaded.get("polygons") or [])
        else:
            with Image.open(self.current_page) as opened:
                source_dpi = image_dpi(opened.info)
                self.image = normalize_page_rgb(opened)
            self.page_sections = read_page_sections(self.current_page)
            self.entries = read_pdic(pdic_path(self.current_page))
            self._sort_entries_reading_order()
            self._restore_entry_ocr_metadata()
            self._load_ocr_review_candidates()
            self.polygons = read_ppp(self._ppp_read_path(self.current_page))
        self.image_metadata_status_var.set(image_status(self.image.width, self.image.height, source_dpi))
        self.new_polygon = []
        self._preprocess_photo = None
        self._preprocess_photo_cache_key = None
        self._section_editing = False
        self._drag_section_boundary = None
        self.update_idletasks()
        if reset_zoom:
            available = max(500, self.canvas.winfo_width() - 24)
            self.view_scale = min(1.0, available / self.image.width)

        if self.settings.bottom_y <= 0:
            self.settings.bottom_y = int(self.image.height)
        self.cursor_canvas_xy = None
        self.sync_quick_settings()
        self._update_view_zoom_label()
        if use_preloaded and not reset_zoom:
            expected_size = (
                max(1, round(self.image.width * self.view_scale)),
                max(1, round(self.image.height * self.view_scale)),
            )
            if (
                preloaded.get("display_size") == expected_size
                and abs(float(preloaded.get("view_scale", -1.0)) - float(self.view_scale)) < 1e-9
                and isinstance(preloaded.get("display_image"), Image.Image)
                and normalize_appearance_mode(preloaded.get("appearance_mode")) == self.appearance_mode
                and not self.binary_preview_var.get()
            ):
                self.photo = ImageTk.PhotoImage(preloaded["display_image"])
                self._display_photo_cache_key = (
                    id(self.image), expected_size[0], expected_size[1], False, self.appearance_mode,
                )
        self.redraw()
        self._set_idle_cursor_status()
        # Reset scroll, preserving zoom.
        self.canvas.xview_moveto(0.0)
        self.canvas.yview_moveto(0.0)
        self._set_page_list_selection(index, ensure_visible=True)
        quality = self._current_page_quality_text()
        suffix = f"｜{quality}" if quality else ""
        self.status_var.set(f"{self.current_page.name}｜{self.image.width}×{self.image.height}｜{len(self.entries)} 个词条{suffix}")
        if self._preprocess_mode_active():
            existing_preprocess = self._preprocess_result_for_page(index)
            self._set_current_preprocess_status(existing_preprocess)
            if existing_preprocess is None:
                self.after_idle(lambda: self.analyze_preprocess_current(silent=True))
        if self._pending_section_editor_index == index:
            self._pending_section_editor_index = None
            if self.page_sections:
                self._set_section_editing(True)
                self.redraw()
                self.status_var.set(
                    f"SECTION 编辑：当前页 {len(self.page_sections)} 个；拖动虚线定位Section，双击左键确认并退出编辑。"
                )
        try:
            touch_recent_project(
                self.project.root,
                last_page=self.current_page.name,
                last_page_index=self.current_index,
            )
        except (OSError, ValueError, TypeError):
            pass
        self._save_session_state()

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

    def _draw_entry_overlay(
        self, entry: WordEntry, index: int, geometry, size: tuple[int, int],
        overlay_scale: float, *, processing_readonly: bool | None = None,
    ) -> None:
        """Draw one editable headword row without rebuilding the whole canvas."""
        if self.image is None or self.hide_var.get():
            return
        if processing_readonly is None:
            processing_readonly = self._foreground_batch_state(self.current_index) == "processing"
        entry_u, entry_v = geometry.source_to_canonical(entry.x, entry.y)
        col = column_index(entry.x, geometry, entry.y)
        canonical_x = geometry.x_at(col, entry_v)
        width = geometry.column_widths[col] * self.view_scale
        record = {"widgets": [], "canvas_items": [], "index_widget": None}
        marker_start, marker_end = geometry.transform.canonical_marker_to_source(
            (canonical_x, entry_v),
            (canonical_x + round(geometry.column_widths[col] * 0.95), entry_v),
            geometry.source_size,
        )

        marker_line_width = scaled_overlay_line_width(self.settings.marker_height, overlay_scale)
        show_markers = (
            self.quick_bool_vars.get("show_headword_markers").get()
            if hasattr(self, "quick_bool_vars") and "show_headword_markers" in self.quick_bool_vars
            else self.settings.show_headword_markers
        )
        if show_markers:
            item = create_alpha_canvas_line(
                self,
                (
                    marker_start[0] * self.view_scale,
                    marker_start[1] * self.view_scale,
                    marker_end[0] * self.view_scale,
                    marker_end[1] * self.view_scale,
                ),
                fill=self.settings.headword_marker_color,
                width=marker_line_width,
                opacity=self.settings.headword_marker_opacity,
            )
            record["canvas_items"].append(item)

        editor_font_size = effective_main_overlay_font_size(
            self.image.width, self.view_scale, self.settings,
        )
        horizontal = self.settings.layout_writing_mode == "horizontal-tb"
        vertical = not horizontal
        rtl = horizontal and self.settings.layout_text_direction == "rtl"
        main_family = resolve_content_font_family(
            self.canvas,
            self.settings.main_entry_font_family,
            self.settings.ocr_language,
        )
        editor_font = _entry_font_spec(
            main_family, editor_font_size,
            self.settings.main_entry_font_bold, self.settings.main_entry_font_italic,
        )
        if horizontal:
            editor = tk.Entry(
                self.canvas,
                width=max(4, int(self.settings.main_entry_width_chars)),
                font=editor_font,
                relief="flat",
            )
        else:
            # Use a real child widget, not a Canvas rectangle/text proxy.  The
            # narrow Text widget wraps by character, so CJK/kana display
            # top-to-bottom while remaining directly clickable and editable.
            editor = VerticalWordText(
                self.canvas,
                width=2,
                height=max(4, int(self.settings.main_entry_width_chars)),
                font=editor_font,
                wrap="char",
                relief="flat",
                borderwidth=0,
                padx=2,
                pady=1,
                spacing1=0,
                spacing2=0,
                spacing3=0,
                undo=False,
                cursor="xterm",
                exportselection=False,
            )
        editor.insert(0, entry.word)
        self._style_entry_editor(editor, entry)
        if processing_readonly:
            if isinstance(editor, VerticalWordText):
                editor.configure(state="disabled", foreground="#555555")
            else:
                editor.configure(state="disabled", disabledforeground="#555555")
        editor.bind("<FocusOut>", lambda _e, e=entry, w=editor: self.update_entry(e, w))
        editor.bind("<KeyPress>", self._entry_keypress_batch_guard)
        editor.bind("<<Paste>>", lambda _e: None if self._claim_page_for_manual_edit() else "break")
        editor.bind("<<Cut>>", lambda _e: None if self._claim_page_for_manual_edit() else "break")
        editor.bind(
            "<KeyRelease>",
            lambda _e, e=entry, w=editor: self._style_entry_editor(w, e, w.get().strip()),
        )
        editor.bind("<Return>", lambda e: self.focus_next(e.widget))
        editor.bind("<Tab>", lambda e: self.focus_next(e.widget))
        editor.bind("<Shift-Tab>", lambda e: self.focus_previous(e.widget))
        editor.bind("<Down>", lambda e: self.focus_next(e.widget))
        editor.bind("<Up>", lambda e: self.focus_previous(e.widget))
        editor.bind("<Delete>", lambda _e, e=entry: self.delete_entry(e))
        editor.bind("<KeyPress-grave>", lambda _e, e=entry: self.delete_entry(e))
        self.overlay_widgets.append(editor)
        record["widgets"].append(editor)
        self.entry_editor_bindings.append((editor, entry))
        editor_req_width = max(1, editor.winfo_reqwidth())
        editor_req_height = max(1, editor.winfo_reqheight())
        editor_anchor = "nw"
        horizontal_index: tuple[float, float] | None = None
        horizontal_index_anchor = "nw"
        if horizontal:
            (editor_x, editor_y), editor_anchor, horizontal_index, horizontal_index_anchor = (
                horizontal_overlay_layout(
                    geometry.transform, canonical_x, entry_v, geometry.column_widths[col],
                    float(self.settings.main_entry_x_ratio), geometry.source_size,
                    self.view_scale, rtl=rtl,
                )
            )
        else:
            # Match horizontal semantics: apply main_entry_x_ratio within the
            # 当前栏 first, then transform that point to source space.
            editor_x, editor_y = transformed_entry_anchor(
                geometry.transform, canonical_x, entry_v, geometry.column_widths[col],
                float(self.settings.main_entry_x_ratio), geometry.source_size, self.view_scale,
            )
        
        if rtl:
            editor.configure(justify="right")
        
        vertical_box: tuple[int, int, int, int] | None = None
        vertical_index: tuple[float, float] | None = None
        vertical_index_anchor_name = "nw"
        if vertical:
            # Touch the visible marker stroke with no empty gap.  editor_x is
            # the marker centreline, so offset by exactly half the painted line
            # width to place the widget border against the marker edge.
            marker_gap = vertical_marker_contact_gap(marker_line_width)
            (
                vertical_box,
                vertical_window,
                vertical_window_anchor,
                vertical_index,
                vertical_index_anchor_name,
            ) = vertical_overlay_layout(
                editor_x, editor_y, editor_req_width, editor_req_height,
                self.settings.layout_writing_mode, gap=marker_gap,
            )
            # The Text widget is permanently present.  Unlike the old Canvas
            # proxy, it receives mouse/key events exactly like a horizontal
            # Entry, so no click routing or temporary popup is involved.
            item = self.canvas.create_window(
                *vertical_window,
                window=editor,
                anchor=vertical_window_anchor,
                width=vertical_box[2] - vertical_box[0],
                height=vertical_box[3] - vertical_box[1],
            )
            record["canvas_items"].append(item)
        else:
            item = self.canvas.create_window(
                editor_x, editor_y,
                window=editor,
                anchor=editor_anchor,
            )
            record["canvas_items"].append(item)

        candidate = self._candidate_for_entry(entry)
        ocr_menu = (
            self._create_main_ocr_menu(entry, editor, candidate)
            if self._main_ocr_review_option_enabled("review_main_show_ocr_choices")
            else None
        )

        if ocr_menu is not None:
            if processing_readonly:
                ocr_menu.configure(state="disabled")

            self.overlay_widgets.append(ocr_menu)
            record["widgets"].append(ocr_menu)

            menu_req_width = max(1, ocr_menu.winfo_reqwidth())

            if vertical and vertical_box:
                ocr_x, ocr_y, ocr_anchor = vertical_ocr_menu_layout(
                    vertical_box, menu_req_width,
                    self.settings.layout_writing_mode, size[0],
                )
            else:
                ocr_x, ocr_y, ocr_anchor = horizontal_ocr_menu_layout(
                    editor_x, editor_y, editor_req_width, rtl=rtl,
                )
                if not rtl and ocr_x + menu_req_width > size[0] - 2:
                    ocr_x = max(0, size[0] - menu_req_width - 2)
                elif rtl and ocr_x - menu_req_width < 2:
                    ocr_x = menu_req_width + 2

            item = self.canvas.create_window(
                ocr_x,
                ocr_y,
                window=ocr_menu,
                anchor=ocr_anchor,
            )
            record["canvas_items"].append(item)

        # The sequence number belongs to the entry editor rather than to the
        # column edge. Use a real Label so its background can exactly follow the
        # editor background (including optional OCR-confidence colouring).
        index_x, index_y, index_anchor = entry_index_label_layout(
            editor_x,
            editor_y,
            editor_req_width,
            editor_req_height,
            horizontal=horizontal,
            rtl=rtl,
            vertical_box=vertical_box,
        )
        index_label = tk.Label(
            self.canvas,
            text=self._entry_sequence_text(index, len(self.entries)),
            bg="#e6e6e6",
            fg="#000000",
            bd=0,
            padx=2,
            pady=0,
            font=_entry_font_spec(
                main_family, max(8, round(editor_font_size * 0.65)), False, False,
            ),
        )
        # Sequence numbers intentionally use a neutral light-gray control style;
        # the delete control remains red to preserve its destructive meaning.
        index_label._pc_skip_classic_appearance = True
        self.overlay_widgets.append(index_label)
        record["widgets"].append(index_label)
        record["index_widget"] = index_label
        index_window = self.canvas.create_window(
            index_x, index_y, window=index_label, anchor=index_anchor,
        )
        record["canvas_items"].append(index_window)

        index_width = max(1, index_label.winfo_reqwidth())
        index_height = max(1, index_label.winfo_reqheight())
        if horizontal:
            delete_x = float(index_x - index_width - 1) if index_anchor == "ne" else float(index_x - 1)
            delete_y = float(index_y)
            delete_anchor = "ne"
        else:
            delete_x = float(index_x - index_width / 2.0 - 1)
            delete_y = float(index_y - index_height / 2.0)
            delete_anchor = "e"
        delete_button = tk.Button(
            self.canvas,
            text="[X]",
            width=3,
            takefocus=False,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=1,
            pady=0,
            cursor="hand2",
            fg="#ffffff",
            bg="#9d042f",
            activeforeground="#ffffff",
            activebackground="#9d042f",
            command=lambda e=entry: self.delete_entry(e),
        )
        delete_button._pc_skip_classic_appearance = True
        if processing_readonly:
            delete_button.configure(state="disabled")
        self._attach_tooltip(delete_button, "点击删除该画线!")
        self.overlay_widgets.append(delete_button)
        record["widgets"].append(delete_button)
        record["delete_widget"] = delete_button
        delete_window = self.canvas.create_window(
            delete_x, delete_y, window=delete_button, anchor=delete_anchor,
        )
        record["canvas_items"].append(delete_window)

        if self.crop_preview_var.get():
            left, top, right, bottom = line_box(entry, geometry, self.image, self.settings)
            item = self.canvas.create_rectangle(
                left * self.view_scale, top * self.view_scale,
                right * self.view_scale, bottom * self.view_scale,
                outline="#00acc1", width=1, dash=(5, 3),
            )
            record["canvas_items"].append(item)

        self._entry_visuals[id(entry)] = record

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
            auxiliary_lines=list(self._auxiliary_edits.lines),
        )

    def _draw_crop_plan_preview(self) -> None:
        """Overlay the exact entry/PPP crop plan on the main page image."""
        if self.image is None:
            draw_layout_visualization_if_enabled(self)
            return
        try:
            plan = self._current_page_crop_plan()
        except Exception as exc:
            self.status_var.set(f"切图预览生成失败：{exc}")
            return
        if plan is None:
            return
        from .crop_preview_labels import draw_crop_preview_label, format_crop_preview_entry_label
        scale = self.view_scale
        illustrated_entries = {p.entry_ref_index for p in plan.entry_pieces if p.source_mode == "linked_original" and p.entry_ref_index is not None}
        from .crop_preview_display_settings import crop_preview_font_spec
        preview_font = crop_preview_font_spec(
            self, scale, resolve_content_font_family, _entry_font_spec,
        )
        for piece in plan.entry_pieces:
            x0,y0,x1,y1=piece.box
            if piece.entry_ref_index in illustrated_entries:
                color = "#2e7d32"
                dash = ()
            else:
                color = "#00acc1"
                dash = (6, 4)
            self.canvas.create_rectangle(x0*scale,y0*scale,x1*scale,y1*scale,outline=color,width=2,dash=dash,tags=("crop-plan",))
            filename = entry_crop_piece_filename(self.current_page.stem, piece)
            label = format_crop_preview_entry_label(piece.word, filename)
            draw_crop_preview_label(
                self.canvas, ((x0+x1)/2)*scale, (y0+3)*scale,
                text=label, outline=color, anchor="n", justify="center",
                font=preview_font,
            )
            if piece.merge_polygon_indices:
                for pi in piece.merge_polygon_indices:
                    if 0 <= pi < len(self.polygons):
                        region=self.polygons[pi]
                        coords=[v*scale for pt in region.points for v in pt]
                        if len(coords)>=6:
                            self.canvas.create_polygon(*coords,fill="",outline="#ef6c00",width=3,tags=("crop-plan",))
        # PPP decisions: green/orange travel with headword; magenta/red are
        # standalone and will be whitened before ordinary headword cropping.
        standalone_count=linked_count=partial_count=0
        for dec in plan.illustrations:
            if not (0 <= dec.polygon_index < len(self.polygons)):
                continue
            region=self.polygons[dec.polygon_index]
            coords=[v*scale for pt in region.points for v in pt]
            if len(coords)<6: continue
            if dec.relation=="contained": color="#2e7d32"; text="随词条｜完整包含"; linked_count+=1
            elif dec.relation=="partial":
                if plan.integrate_illustrations:
                    color="#ef6c00"; text="随词条｜部分相交→联合"
                else:
                    color="#8e24aa"; text="独立PPP｜部分超出词条（未综合插图）"; standalone_count+=1
                partial_count+=1
            elif dec.associated_entry_index is not None: color="#8e24aa"; text="独立PPP｜关联词条外部"; standalone_count+=1
            else: color="#d32f2f"; text="独立PPP｜未关联"; standalone_count+=1
            self.canvas.create_polygon(*coords,fill="",outline=color,width=3,tags=("crop-plan",))
            minx=min(p[0] for p in region.points); miny=min(p[1] for p in region.points)
            label=f"{dec.name}  {text}" + (f"  [{dec.associated_word}]" if dec.associated_word else "")
            draw_crop_preview_label(
                self.canvas, (minx+4)*scale, (miny+4)*scale, text=label,
                outline=color, anchor="nw",
                font=("Microsoft YaHei", max(7, round(9*scale)), "bold"),
            )
        mode = "综合插图" if plan.integrate_illustrations else "仅词条矩形"
        self.status_var.set(
            f"切图预览｜{mode}｜词条切图片段 {len(plan.entry_pieces)}｜随词条PPP {linked_count}｜部分相交 {partial_count}｜独立PPP {standalone_count}"
        )

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
        clear_alpha_line_photos(self)
        clear_alpha_polygon_records(self)
        self._sync_polygon_label_texts()
        self.canvas.delete("all")
        for widget in self.overlay_widgets:
            widget.destroy()
        self.overlay_widgets.clear()
        self.entry_editor_bindings.clear()
        self.polygon_label_bindings.clear()
        self._polygon_canvas_items.clear()
        self.candidate_check_vars.clear()
        self._entry_visuals.clear()
        if self.image is None:
            return
        size = (max(1, round(self.image.width * self.view_scale)), max(1, round(self.image.height * self.view_scale)))
        if self._preprocess_mode_active():
            self._redraw_preprocess_preview(size)
            draw_layout_visualization_if_enabled(self)
            return
        photo = self._get_cached_display_photo(size)
        self.canvas.create_image(0, 0, image=photo, anchor="nw", tags="page")
        if self.crop_preview_var.get():
            self._draw_crop_plan_preview()
            crop_geometry = self._get_cached_display_geometry()
            self._draw_page_sections(crop_geometry)
            self._auxiliary_controller.redraw()
            self._draw_percentage_rulers(crop_geometry)
            ruler_margin = 28 if self._rulers_visible() else 0
            self.canvas.configure(
                scrollregion=(-ruler_margin, 0, size[0] + ruler_margin, size[1] + ruler_margin)
            )
            if self.cursor_canvas_xy is not None:
                self.draw_cursor_guides(*self.cursor_canvas_xy)
            draw_ocr_crop_preview(self)
            draw_layout_visualization_if_enabled(self)
            return
        hidden = bool(self.hide_var.get())
        geometry = self._get_cached_display_geometry()
        overlay_scale = self.view_scale / parameter_scale(self.image, self.settings)
        self._draw_review_entry_highlight(geometry)
        show_guides = (
            self.quick_bool_vars.get("show_column_guides").get()
            if hasattr(self, "quick_bool_vars") and "show_column_guides" in self.quick_bool_vars
            else self.settings.show_column_guides
        )
        if show_guides:
            for path in geometry.column_paths:
                source_points = [geometry.canonical_to_source(x, y) for y, x in path.points]
                coords = [coordinate * self.view_scale for point in source_points for coordinate in point]
                if len(coords) >= 4:
                    create_alpha_canvas_line(
                        self,
                        tuple(coords),
                        fill=self.settings.guide_color,
                        width=scaled_overlay_line_width(self.settings.guide_width, overlay_scale),
                        opacity=self.settings.guide_opacity,
                        smooth=True,
                    )
        self._draw_page_sections(geometry)
        self._auxiliary_controller.redraw()
        self._draw_percentage_rulers(geometry)
        if not hidden:
            processing_readonly = self._foreground_batch_state(self.current_index) == "processing"
            for index, entry in enumerate(self._ordered_entries_reading_order()):
                self._draw_entry_overlay(
                    entry, index, geometry, size, overlay_scale,
                    processing_readonly=processing_readonly,
                )

        # v2.0: expose every OCR left-edge candidate as a right-side checkbox.
        # Rejected lemma rows can therefore be promoted manually without
        # changing parser thresholds or adding a special filter rule.
        show_candidates = (
            self.quick_bool_vars.get("paddle_show_candidate_checkboxes").get()
            if hasattr(self, "quick_bool_vars") and "paddle_show_candidate_checkboxes" in self.quick_bool_vars
            else self.settings.paddle_show_candidate_checkboxes
        )
        if show_candidates:
            for cand in self.ocr_review_candidates:
                try:
                    col = max(0, min(len(geometry.column_starts) - 1, int(cand.get("column", 0))))
                    cy_source = int(cand.get("source_y", 0))
                except (TypeError, ValueError):
                    continue
                if cy_source <= 0:
                    continue
                cx_source = int(cand.get("source_x", 0))
                _cand_u, cand_v = geometry.source_to_canonical(cx_source, cy_source)
                control_source = geometry.canonical_to_source(
                    geometry.x_at(col, cand_v) + round(geometry.column_widths[col] * 0.955),
                    cand_v,
                )
                cx = control_source[0] * self.view_scale
                cy = control_source[1] * self.view_scale
                cid = str(cand.get("candidate_id", ""))
                if not cid:
                    continue
                var = tk.BooleanVar(value=self._candidate_is_selected(cand))
                self.candidate_check_vars[cid] = var
                conf = cand.get("confidence")
                try:
                    conf_value = float(conf) if conf is not None else None
                except (TypeError, ValueError):
                    conf_value = None
                is_original_y = str(cand.get("position_variant", "refined")) in {"original", "anchor"}
                bg = "#d9ecff" if is_original_y else self._confidence_bg(conf_value)
                outline = "#1976d2" if is_original_y else ("#d84315" if cand.get("issue_types") else "#9e9e9e")
                check = tk.Checkbutton(
                    self.canvas, variable=var, bg=bg, activebackground=bg,
                    selectcolor=bg, bd=0, highlightthickness=1,
                    highlightbackground=outline,
                    command=lambda c=cid, v=var: self.candidate_checkbox_changed(c, v),
                )
                self.overlay_widgets.append(check)
                self.canvas.create_window(cx, cy, window=check, anchor="nw")
        show_shapes = bool(self.polygon_var.get() or self.polygon_draw_var.get())
        show_labels = bool(self.settings.show_illustration_labels)
        if show_shapes or show_labels:
            for region_index, region in enumerate(self.polygons):
                coords = [value * self.view_scale for point in region.points for value in point]
                if len(coords) < 6:
                    continue
                polygon_item = None
                if show_shapes:
                    polygon_item = create_alpha_canvas_polygon(
                        self,
                        tuple(coords),
                        outline=self.settings.illustration_outline_color,
                        fill=self.settings.illustration_fill_color,
                        width=scaled_overlay_line_width(self.settings.illustration_outline_width, overlay_scale),
                        opacity=self.settings.illustration_fill_opacity,
                        tags=("ppp-overlay", f"ppp-region-{region_index}"),
                    )
                handles: list[int] = []
                edge_handles: dict[str, int] = {}
                if self.polygon_draw_var.get():
                    radius = 5
                    for point_index, (px, py) in enumerate(region.points):
                        cx, cy = px * self.view_scale, py * self.view_scale
                        handles.append(self.canvas.create_oval(
                            cx - radius, cy - radius, cx + radius, cy + radius,
                            fill="#ffffff", outline=self.settings.illustration_outline_color, width=2,
                            tags=("ppp-overlay", f"ppp-handle-{region_index}-{point_index}"),
                        ))
                    bounds = self._rectangle_bounds(region)
                    if bounds is not None:
                        x0, y0, x1, y1 = bounds
                        mids = {
                            "left": (x0, (y0 + y1) / 2),
                            "right": (x1, (y0 + y1) / 2),
                            "top": ((x0 + x1) / 2, y0),
                            "bottom": ((x0 + x1) / 2, y1),
                        }
                        for side, (mx, my) in mids.items():
                            cx, cy = mx * self.view_scale, my * self.view_scale
                            edge_handles[side] = self.canvas.create_rectangle(
                                cx - radius, cy - radius, cx + radius, cy + radius,
                                fill=self.settings.illustration_outline_color, outline="#ffffff", width=1,
                                tags=("ppp-overlay", f"ppp-edge-{region_index}-{side}"),
                            )

                label_item = None
                label_frame = None
                if show_labels:
                    label_frame = tk.Frame(
                        self.canvas, bg=self.settings.illustration_label_fill_color,
                        bd=0, highlightthickness=max(0, int(self.settings.illustration_label_border_width)),
                        highlightbackground=self.settings.illustration_label_border_color,
                        highlightcolor=self.settings.illustration_label_border_color,
                    )
                    label_entry = tk.Entry(
                        label_frame, width=18, relief="flat", bd=0, highlightthickness=0,
                        bg=self.settings.illustration_label_fill_color,
                        font=_entry_font_spec(
                            resolve_content_font_family(
                                self.canvas,
                                self.settings.illustration_label_font_family,
                                self.settings.ocr_language,
                            ),
                            max(7, round(self.settings.illustration_label_font_size * self.view_scale)),
                            self.settings.illustration_label_font_bold,
                            self.settings.illustration_label_font_italic,
                        ),
                    )
                    label_entry.insert(0, self._polygon_display_name(region, region_index))
                    label_entry.bind("<FocusOut>", lambda _e, r=region, w=label_entry: self._update_polygon_label(r, w))
                    label_entry.bind("<Return>", lambda _e, r=region, w=label_entry: self._commit_polygon_label_return(r, w))
                    label_entry.pack(side="left")
                    delete_button = tk.Button(
                        label_frame, text="×", width=2, height=1, padx=0, pady=0, relief="flat",
                        bg=self.settings.illustration_label_fill_color,
                        activebackground=self.settings.illustration_label_fill_color,
                        highlightthickness=0, bd=0,
                        command=lambda r=region: self._delete_polygon_region(r),
                    )
                    delete_button.pack(side="left", padx=(2, 0))
                    self.overlay_widgets.append(label_frame)
                    self.polygon_label_bindings.append((label_entry, region))
                    label_frame.update_idletasks()
                    label_x, label_y = self._polygon_label_canvas_position(region, label_frame)
                    label_item = self.canvas.create_window(
                        label_x, label_y, window=label_frame, anchor="nw", tags=("ppp-overlay",)
                    )
                self._polygon_canvas_items[region_index] = {
                    "polygon": polygon_item,
                    "handles": handles,
                    "edge_handles": edge_handles,
                    "label_window": label_item,
                    "label_frame": label_frame,
                }
            if self.new_polygon:
                coords = [value * self.view_scale for point in self.new_polygon for value in point]
                if len(coords) >= 4:
                    self.canvas.create_line(*coords, fill="#00aa55", width=2, tags=("ppp-overlay",))
                for px, py in self.new_polygon:
                    cx, cy = px * self.view_scale, py * self.view_scale
                    self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#ffffff", outline="#00aa55", width=2, tags=("ppp-overlay",))
        ruler_margin = 28 if self._rulers_visible() else 0
        self.canvas.configure(
            scrollregion=(-ruler_margin, 0, size[0] + ruler_margin, size[1] + ruler_margin)
        )
        if self.cursor_canvas_xy is not None:
            self.draw_cursor_guides(*self.cursor_canvas_xy)

        self._apply_current_appearance(self.canvas)
        draw_ocr_crop_preview(self)
        draw_layout_visualization_if_enabled(self)

    def _update_view_zoom_label(self) -> None:
        self._canvas_controller_for_call().update_view_zoom_label()


    def zoom(self, factor: float) -> None:
        self._canvas_controller_for_call().zoom(factor)


    def apply_view_zoom_text(self, _event=None) -> None:
        self._canvas_controller_for_call().apply_view_zoom_text(_event)


    def fit_page_width(self) -> None:
        self._canvas_controller_for_call().fit_page_width()


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
        label = str(region.label or "").strip()
        fields = label.split("|")
        if len(fields) >= 3 and fields[1].strip():
            return fields[1].strip()
        return label or f"P_{index + 1:02d}"

    def _set_polygon_display_name(self, region: PolygonRegion, name: str) -> None:
        name = re.sub(r"[\t\r\n|]+", "_", str(name or "").strip())
        if not name:
            return
        label = str(region.label or "")
        fields = label.split("|")
        if len(fields) >= 4:
            fields[1] = name
            region.label = "|".join(fields)
        else:
            region.label = name

    def _update_polygon_label(self, region: PolygonRegion, widget: tk.Entry) -> None:
        if self._batch_active and self._batch_allow_pdic_edits:
            return
        try:
            name = widget.get().strip()
        except tk.TclError:
            return
        before = region.label
        self._set_polygon_display_name(region, name)
        if region.label != before and self.current_page is not None:
            try:
                write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
                self.status_var.set(f"PPP名称已更新：{name}")
            except Exception as exc:
                self.show_error("保存PPP名称失败", exc)

    def _commit_polygon_label_return(self, region: PolygonRegion, widget: tk.Entry) -> str:
        self._update_polygon_label(region, widget)
        try:
            self.canvas.focus_set()
        except tk.TclError:
            pass
        return "break"

    def _sync_polygon_label_texts(self) -> None:
        for widget, region in list(getattr(self, "polygon_label_bindings", [])):
            try:
                self._set_polygon_display_name(region, widget.get())
            except tk.TclError:
                continue

    def _nearest_polygon_vertex(self, x: int, y: int, radius_screen: float = 11.0) -> tuple[int, int] | None:
        if not self.polygons:
            return None
        radius_source = radius_screen / max(self.view_scale, 1e-6)
        best = None; best_d2 = radius_source * radius_source
        for ri, region in enumerate(self.polygons):
            for pi, (px, py) in enumerate(region.points):
                d2 = (px - x) ** 2 + (py - y) ** 2
                if d2 <= best_d2:
                    best = (ri, pi); best_d2 = d2
        return best

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
        """Hit-test the four draggable sides of rectangular PPP regions."""
        radius_source = radius_screen / max(self.view_scale, 1e-6)
        best: tuple[int, str] | None = None
        best_distance = radius_source + 1
        for ri, region in enumerate(self.polygons):
            bounds = self._rectangle_bounds(region)
            if bounds is None:
                continue
            x0, y0, x1, y1 = bounds
            candidates = []
            if y0 - radius_source <= y <= y1 + radius_source:
                candidates.extend(((abs(x - x0), "left"), (abs(x - x1), "right")))
            if x0 - radius_source <= x <= x1 + radius_source:
                candidates.extend(((abs(y - y0), "top"), (abs(y - y1), "bottom")))
            for distance, side in candidates:
                if distance <= radius_source and distance < best_distance:
                    best = (ri, side)
                    best_distance = distance
        return best

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
        if self._batch_active and self._batch_allow_pdic_edits:
            self.status_var.set("插图识别期间暂不修改 PPP。")
            return
        if self.current_page is None:
            return
        try:
            index = next(i for i, candidate in enumerate(self.polygons) if candidate is region)
        except StopIteration:
            return
        name = self._polygon_display_name(region, index)
        if not messagebox.askyesno("删除PPP插图", f"删除插图：{name}？\n\n只删除当前这一个 PPP 区域。", parent=self):
            return
        self._sync_polygon_label_texts()
        try:
            self.polygons.pop(index)
            self._drag_polygon_vertex = None
            self._drag_polygon_edge = None
            write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
            self._update_page_row(self.current_index)
            self.redraw()
            self.status_var.set(f"已删除 PPP 插图：{name}")
        except Exception as exc:
            self.show_error("删除PPP插图失败", exc)

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
        if not region.points:
            return 2.0, 2.0
        min_x = min(p[0] for p in region.points) * self.view_scale
        min_y = min(p[1] for p in region.points) * self.view_scale
        max_x = max(p[0] for p in region.points) * self.view_scale
        max_y = max(p[1] for p in region.points) * self.view_scale
        try:
            label_width = max(widget.winfo_reqwidth(), 1)
            label_height = max(widget.winfo_reqheight(), 1)
        except tk.TclError:
            label_width, label_height = 150, 24
        if self.image is not None:
            canvas_width = self.image.width * self.view_scale
            canvas_height = self.image.height * self.view_scale
        else:
            canvas_width = max(self.canvas.winfo_width(), 1)
            canvas_height = max(self.canvas.winfo_height(), 1)
        return self._external_polygon_label_position(
            min_x, min_y, max_x, max_y, label_width, label_height, canvas_width, canvas_height
        )

    def _update_polygon_canvas_geometry(self, region_index: int) -> None:
        if not (0 <= region_index < len(self.polygons)):
            return
        region = self.polygons[region_index]
        record = self._polygon_canvas_items.get(region_index)
        if not record:
            return
        coords = [value * self.view_scale for point in region.points for value in point]
        try:
            self.canvas.coords(record["polygon"], *coords)
            for point_index, handle in enumerate(record.get("handles", [])):
                if point_index >= len(region.points):
                    break
                px, py = region.points[point_index]
                cx, cy = px * self.view_scale, py * self.view_scale
                r = 5
                self.canvas.coords(handle, cx - r, cy - r, cx + r, cy + r)
            bounds = self._rectangle_bounds(region)
            edge_handles = record.get("edge_handles", {})
            if bounds is not None:
                x0, y0, x1, y1 = bounds
                mids = {
                    "left": (x0, (y0 + y1) / 2),
                    "right": (x1, (y0 + y1) / 2),
                    "top": ((x0 + x1) / 2, y0),
                    "bottom": ((x0 + x1) / 2, y1),
                }
                r = 5
                for side, item in edge_handles.items():
                    mx, my = mids[side]
                    cx, cy = mx * self.view_scale, my * self.view_scale
                    self.canvas.coords(item, cx - r, cy - r, cx + r, cy + r)
            if region.points and record.get("label_window") is not None:
                label_frame = record.get("label_frame")
                if label_frame is not None:
                    label_x, label_y = self._polygon_label_canvas_position(region, label_frame)
                    self.canvas.coords(record["label_window"], label_x, label_y)
        except tk.TclError:
            pass
        refresh_alpha_polygon_fill(self, region_index)

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
        was_editing = bool(getattr(self, "_section_editing", False))
        self._section_editing = bool(active)
        self._drag_section_boundary = None
        try:
            self.canvas.configure(cursor="hand2" if self._section_editing else "")
        except tk.TclError:
            pass
        if self._section_editing:
            # SECTION dragging uses the page boundary lines themselves as the
            # pointer target. Hide the ordinary coordinate crosshair so it
            # cannot be confused with a SECTION boundary.
            self.cursor_canvas_xy = None
            try:
                self.canvas.delete("cursor-guide")
            except tk.TclError:
                pass
        elif was_editing:
            # Restore the ordinary pointer and coordinate crosshair immediately
            # at the current pointer position; the user should not have to move
            # the mouse once just to make the guides reappear.
            try:
                self.after_idle(self._restore_cursor_guides_after_section_edit)
            except tk.TclError:
                pass

    def _restore_cursor_guides_after_section_edit(self) -> None:
        if self._section_editing or self.image is None:
            return
        try:
            self.canvas.configure(cursor="")
            widget_x = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx()
            widget_y = self.canvas.winfo_pointery() - self.canvas.winfo_rooty()
            if not (
                0 <= widget_x < self.canvas.winfo_width()
                and 0 <= widget_y < self.canvas.winfo_height()
            ):
                return
            canvas_x = self.canvas.canvasx(widget_x)
            canvas_y = self.canvas.canvasy(widget_y)
            display_width = self.image.width * self.view_scale
            display_height = self.image.height * self.view_scale
            if not (0 <= canvas_x < display_width and 0 <= canvas_y < display_height):
                return
            self.cursor_canvas_xy = (canvas_x, canvas_y)
            self.draw_cursor_guides(canvas_x, canvas_y)
        except tk.TclError:
            return

    def _finish_section_editing(self) -> bool:
        if not self._section_editing:
            return False
        self._persist_current_page_sections()
        self._set_section_editing(False)
        self.status_var.set(
            f"SECTION 编辑完成：当前页 {len(self.page_sections)} 个 SECTION"
        )
        self.redraw()
        return True

    def _draw_page_sections(self, geometry=None) -> None:
        """Draw page-local SECTION bounds in source space on the main canvas."""
        self.canvas.delete("page-section-overlay")
        if not self.page_sections or self.image is None:
            return
        show_sections = bool(getattr(self.settings, "show_page_sections", True))
        if not show_sections and not self._section_editing:
            return
        geometry = geometry or self._get_cached_display_geometry()
        canonical_width, _canonical_height = geometry.transform.canonical_size(self.image.size)
        overlay_scale = self.view_scale / parameter_scale(self.image, self.settings)
        line_width = scaled_overlay_line_width(
            int(getattr(self.settings, "page_section_width", 2) or 2),
            overlay_scale,
        )
        line_fill = str(getattr(self.settings, "page_section_color", "#1976d2") or "#1976d2")
        for index, section in enumerate(self.page_sections):
            for side, v in (("top", section.top_v), ("bottom", section.bottom_v)):
                start = geometry.canonical_to_source(0, int(v))
                end = geometry.canonical_to_source(canonical_width, int(v))
                self.canvas.create_line(
                    start[0] * self.view_scale, start[1] * self.view_scale,
                    end[0] * self.view_scale, end[1] * self.view_scale,
                    fill=line_fill, width=line_width, dash=(7, 4),
                    tags=("page-section-overlay", f"page-section-{index}-{side}"),
                )
            # Keep the SECTION badge centered above that SECTION's starting
            # boundary. This makes the label read as the caption of the top
            # boundary rather than as content inside the SECTION.
            top_start = geometry.canonical_to_source(0, int(section.top_v))
            top_end = geometry.canonical_to_source(canonical_width, int(section.top_v))
            label_x = ((top_start[0] + top_end[0]) / 2.0) * self.view_scale
            label_y = min(top_start[1], top_end[1]) * self.view_scale - max(
                4, round(4 * self.view_scale)
            )
            text_item = self.canvas.create_text(
                label_x,
                label_y,
                text=f"SECTION {index + 1}",
                fill="#ffffff", anchor="s",
                font=("Microsoft YaHei", max(8, round(10 * self.view_scale)), "bold"),
                tags=("page-section-overlay",),
            )
            bbox = self.canvas.bbox(text_item)
            if bbox:
                pad_x, pad_y = 4, 2
                label_bg = self.canvas.create_rectangle(
                    bbox[0] - pad_x, bbox[1] - pad_y,
                    bbox[2] + pad_x, bbox[3] + pad_y,
                    fill=line_fill, outline=line_fill,
                    tags=("page-section-overlay",),
                )
                self.canvas.tag_lower(label_bg, text_item)
        try:
            self.canvas.tag_raise("page-section-overlay")
        except tk.TclError:
            pass

    def _nearest_section_boundary(self, source_x: int, source_y: int) -> tuple[int, str] | None:
        if not self.page_sections or self.image is None:
            return None
        geometry = self._get_cached_display_geometry()
        _u, v = geometry.source_to_canonical(int(source_x), int(source_y))
        tolerance = max(4, round(10 / max(self.view_scale, 0.05)))
        candidates: list[tuple[int, int, str]] = []
        for index, section in enumerate(self.page_sections):
            candidates.append((abs(v - section.top_v), index, "top"))
            candidates.append((abs(v - section.bottom_v), index, "bottom"))
        distance, index, side = min(candidates, default=(10**9, -1, "top"))
        return (index, side) if distance <= tolerance else None

    def _drag_page_section_boundary_to(self, source_x: int, source_y: int) -> None:
        target = self._drag_section_boundary
        if target is None or self.image is None:
            return
        index, side = target
        if not (0 <= index < len(self.page_sections)):
            return
        geometry = self._get_cached_display_geometry()
        _u, v = geometry.source_to_canonical(int(source_x), int(source_y))
        sections = list(self.page_sections)
        current = sections[index]
        min_height = max(6, round((geometry.bottom - geometry.top) * 0.005))
        if side == "top":
            lower = geometry.top if index == 0 else sections[index - 1].bottom_v
            upper = current.bottom_v - min_height
            new_top = max(lower, min(upper, int(v)))
            sections[index] = PageSection(new_top, current.bottom_v)
        else:
            lower = current.top_v + min_height
            upper = geometry.bottom if index + 1 == len(sections) else sections[index + 1].top_v
            new_bottom = max(lower, min(upper, int(v)))
            sections[index] = PageSection(current.top_v, new_bottom)
        self.page_sections = sections
        self._draw_page_sections(geometry)

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
        self._auxiliary_controller.toggle_mode()

    def toggle_polygon_drawing(self) -> None:
        if self._batch_active and self._batch_allow_pdic_edits:
            self.status_var.set("插图识别期间可编辑 PDIC；PPP 编辑请等待识别结束。")
            return
        if not self.guard(): return
        active = not self.polygon_draw_var.get()
        self.polygon_draw_var.set(active)
        if active:
            if self._section_editing:
                self._set_section_editing(False)
            # Drawing must remain visible even if the ordinary display checkbox
            # was previously off. Keep saved polygons visible as context.
            self.polygon_var.set(True)
            if self.polygon_draw_button is not None:
                self.polygon_draw_button.configure(
                    text="结束编辑插图", style="PC.EditActive.TButton"
                )
            self.status_var.set("插图编辑：Shift+单击边线加顶点；拖动调整，右键闭合新图形。")
        else:
            self.new_polygon.clear()
            if self.polygon_draw_button is not None:
                self.polygon_draw_button.configure(
                    text="编辑插图", style="PC.Compact.TButton"
                )
            self.status_var.set("已退出插图多边形绘制模式")
        self.redraw()

    def canvas_left_double_click(self, event: tk.Event) -> str | None:
        """Finish SECTION editing by double-clicking anywhere on the page image."""
        if self._preprocess_mode_active():
            return "break"
        if not self._section_editing or self.image is None:
            return None
        x, y = self.original_xy(event)
        if not (0 <= x < self.image.width and 0 <= y < self.image.height):
            return None
        self._finish_section_editing()
        return "break"

    def canvas_left_click(self, event: tk.Event) -> None:
        if not self.guard():
            return
        x, y = self.original_xy(event)
        if not (0 <= x < self.image.width and 0 <= y < self.image.height):
            return
        if self._section_editing:
            target = self._nearest_section_boundary(x, y)
            if target is None:
                self.status_var.set("SECTION 编辑：请按住并拖动蓝色虚线上下边界。")
                return
            self._drag_section_boundary = target
            section_index, side = target
            side_text = "上边界" if side == "top" else "下边界"
            self.status_var.set(f"正在调整 SECTION {section_index + 1} {side_text}")
            return
        if self.auxiliary_mode_var.get():
            self._auxiliary_controller.click(x, y)
            return
        if self.polygon_draw_var.get():
            existing = self._nearest_polygon_vertex(x, y)
            if existing is not None:
                self._drag_polygon_vertex = existing
                self._drag_polygon_edge = None
                ri, pi = existing
                self.status_var.set(f"正在编辑PPP：拖动插图 {ri + 1} 的顶点 {pi + 1}")
                return
            if event.state & 1:
                segment = nearest_polygon_segment(self.polygons, x, y, view_scale=self.view_scale)
                if segment:
                    ri, index, point = segment
                    self.polygons[ri].points.insert(index, point)
                    self._drag_polygon_vertex = (ri, index)
                    self._drag_polygon_edge = None
                    self.redraw()
                    self.status_var.set("PPP顶点已增加；拖动并松开保存")
                    return
            edge = self._nearest_polygon_edge(x, y)
            if edge is not None:
                self._drag_polygon_edge = edge
                self._drag_polygon_vertex = None
                ri, side = edge
                side_name = {"left": "左边", "right": "右边", "top": "上边", "bottom": "下边"}.get(side, side)
                self.status_var.set(f"正在编辑PPP：拖动插图 {ri + 1} 的{side_name}")
                return
            self.new_polygon.append((x, y))
            self.redraw()
            return
        effective = self._current_effective_profile_settings()
        if not entry_allowed_by_page_template(
            x, y, self.image.size, effective, max(0, int(self.current_index)),
        ):
            self.status_var.set("该位置属于 Project Profile 的页边排除区，不添加词条。")
            return
        geometry = self._get_cached_display_geometry()
        canonical_x, canonical_y = geometry.source_to_canonical(x, y)
        if canonical_y < geometry.top or canonical_y >= geometry.bottom:
            self.status_var.set("该位置位于正文区域之外，不添加词条。")
            return
        if self.page_sections and not v_is_inside_sections(
            canonical_y, self.page_sections, geometry.top, geometry.bottom,
        ):
            self.status_var.set("该位置位于 SECTION 间空白区，不添加词条。")
            return
        col = column_index_for_click(x, geometry, y)
        source_x, source_y = geometry.canonical_to_source(geometry.column_starts[col], canonical_y)
        self.entries.append(WordEntry("", source_x, source_y))
        self._sort_entries_reading_order()
        self.redraw()

    def canvas_left_drag(self, event: tk.Event) -> str | None:
        if self._preprocess_mode_active():
            return "break"
        if self.image is None:
            return None
        x, y = self.original_xy(event)
        if self._drag_section_boundary is not None:
            x = max(0, min(self.image.width - 1, x))
            y = max(0, min(self.image.height - 1, y))
            self._drag_page_section_boundary_to(x, y)
            return "break"
        if self.auxiliary_mode_var.get():
            self._auxiliary_controller.drag(x, y)
            return "break"
        if not self.polygon_draw_var.get():
            return None
        x = max(0, min(self.image.width - 1, x))
        y = max(0, min(self.image.height - 1, y))
        if self._drag_polygon_vertex is not None:
            ri, pi = self._drag_polygon_vertex
            if not (0 <= ri < len(self.polygons) and 0 <= pi < len(self.polygons[ri].points)):
                self._drag_polygon_vertex = None
                return None
            self.polygons[ri].points[pi] = (x, y)
            self._update_polygon_canvas_geometry(ri)
            return "break"
        if self._drag_polygon_edge is not None:
            ri, side = self._drag_polygon_edge
            if not (0 <= ri < len(self.polygons)):
                self._drag_polygon_edge = None
                return None
            self._set_rectangle_side(self.polygons[ri], side, x if side in {"left", "right"} else y)
            self._update_polygon_canvas_geometry(ri)
            return "break"
        return None

    def canvas_left_release(self, _event: tk.Event) -> str | None:
        if self._preprocess_mode_active():
            return "break"
        if self.auxiliary_mode_var.get():
            self._auxiliary_controller.release()
            return "break"
        if self._drag_section_boundary is not None:
            self._drag_section_boundary = None
            try:
                self._persist_current_page_sections()
                self._sort_entries_reading_order()
                gap_count = self._section_gap_entry_count()
                self.redraw()
                if gap_count:
                    self.status_var.set(
                        f"SECTION 边界已保存；有 {gap_count} 条现有词条落在 SECTION 间空白，请调整边界。"
                    )
                else:
                    self.status_var.set("SECTION 边界已保存")
            except Exception as exc:
                self.show_error("保存 SECTION 边界失败", exc)
            return "break"
        target_vertex = self._drag_polygon_vertex
        target_edge = self._drag_polygon_edge
        if target_vertex is None and target_edge is None:
            return None
        self._drag_polygon_vertex = None
        self._drag_polygon_edge = None
        if self.current_page is not None:
            try:
                self._sync_polygon_label_texts()
                write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
                self.status_var.set("PPP轮廓已调整并保存")
            except Exception as exc:
                self.show_error("保存PPP轮廓失败", exc)
        return "break"

    def canvas_right_click(self, event: tk.Event) -> None:
        if self.auxiliary_mode_var.get():
            if self.guard():
                self._auxiliary_controller.delete_at(*self.original_xy(event))
            return
        if self._section_editing:
            self.status_var.set("SECTION 编辑中；点击【结束SECTION】保存并退出。")
            return
        if self.polygon_draw_var.get():
            if not self.guard(): return
            if len(self.new_polygon) >= 3:
                label = simpledialog.askstring("插图标注", "多边形标签（可留空）：", parent=self) or ""
                self.polygons.append(PolygonRegion(label, self.new_polygon.copy()))
                self._update_page_row(self.current_index)
            self.new_polygon.clear(); self.redraw(); return
        if not self.project or not self.current_page or self.image is None:
            return
        # Navigation must not claim/lock a pending OCR-batch page. Only actual
        # foreground edits reserve pages from the background runner.
        self.change_page(1)

    def canvas_motion(self, event: tk.Event) -> None:
        if self.image:
            canvas_x = self.canvas.canvasx(event.x)
            canvas_y = self.canvas.canvasy(event.y)
            display_width = self.image.width * self.view_scale
            display_height = self.image.height * self.view_scale
            if 0 <= canvas_x < display_width and 0 <= canvas_y < display_height:
                if self._section_editing or self._preprocess_mode_active():
                    self.cursor_canvas_xy = None
                    self.canvas.delete("cursor-guide")
                else:
                    self.cursor_canvas_xy = (canvas_x, canvas_y)
                    self.draw_cursor_guides(canvas_x, canvas_y)
                source_x = round(canvas_x / self.view_scale)
                source_y = round(canvas_y / self.view_scale)
                if (
                    not self._section_editing
                    and not self._preprocess_mode_active()
                    and self._ruler_hit_id(source_x, source_y) is not None
                ):
                    self._show_ruler_hint(event)
                else:
                    self._hide_ruler_hint()
                if self._preprocess_mode_active():
                    self.cursor_status_var.set(
                        f"预处理预览 X,Y {source_x}, {source_y}｜"
                        f"缩放 {round(self.view_scale * 100)}%"
                    )
                else:
                    self.cursor_status_var.set(
                        f"原图 X,Y {source_x}, {source_y}｜"
                        f"缩放 {round(self.view_scale * 100)}%｜词条 {len(self.entries)}"
                    )
            else:
                self.cursor_canvas_xy = None
                self.canvas.delete("cursor-guide")
                self._hide_ruler_hint()
                self._set_idle_cursor_status()

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
        if not rows or candidate is None:
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
        """Commit queued checkbox edits before any page/batch ownership change."""
        if self._deferred_save_job is not None:
            try:
                self.after_cancel(self._deferred_save_job)
            except tk.TclError:
                pass
        self._deferred_save_job = None
        snapshot = getattr(self, "_deferred_save_snapshot", None)
        self._deferred_save_snapshot = None
        self._deferred_save_page = None
        if snapshot is not None:
            page, entries, image_width, pages, page_index = snapshot
            write_pdic(pdic_path(page), entries, image_width, pages)
            if self.project and 0 <= page_index < len(self.project.images) and self.project.images[page_index] == page:
                self._refresh_word_fill_check_from_line_count(page_index, len(entries), persist=True)
                self._update_page_row(page_index)
        self._flush_pending_manual_override()

    def _entry_for_candidate(self, cand: dict) -> WordEntry | None:
        return self._review_controller_for_call().entry_for_candidate(cand)


    def set_candidate_selected(self, cand: dict, selected: bool) -> bool:
        if not self._claim_page_for_manual_edit():
            return False
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


    def _draw_review_entry_highlight(self, geometry=None) -> None:
        self._review_entry_highlight_photo = None
        try:
            self.canvas.delete("proofread-entry-highlight")
        except tk.TclError:
            return
        target = self._review_entry_highlight_target
        if self.image is None or target is None or target[0] != self.current_index:
            return
        _page_index, x_source, y_source = target
        ordered = self._ordered_entries_reading_order()
        entry = min(
            ordered,
            key=lambda item: abs(int(item.x) - x_source) + abs(int(item.y) - y_source),
            default=None,
        )
        if entry is None or abs(int(entry.x) - x_source) > 30 or abs(int(entry.y) - y_source) > 30:
            return
        if geometry is None:
            geometry = self._get_cached_display_geometry()
        # Use exactly the same crop geometry as the proofreading row. Ordinary
        # entries therefore start half a row-gap above the marker and use
        # ``character_height + row_padding``; single-CJK entries retain the
        # review window's independent single-character height.
        review_settings = _review_crop_settings(
            self.image, self.settings, self.canvas.winfo_width()
        )
        left, top, right, bottom = _review_line_box(
            entry, geometry, self.image, review_settings
        )
        # Tk Canvas rectangle fills have no real alpha channel; the previous
        # ``gray50`` stipple therefore looked grainy/frosted.  Use a tiny RGBA
        # PhotoImage instead so the marker is a genuinely translucent pale-yellow
        # highlighter and the scanned text remains clearly visible underneath.
        x0 = int(round(left * self.view_scale))
        y0 = int(round(top * self.view_scale))
        x1 = int(round(right * self.view_scale))
        y1 = int(round(bottom * self.view_scale))
        overlay = Image.new(
            "RGBA",
            (max(1, x1 - x0), max(1, y1 - y0)),
            (255, 238, 128, 92),
        )
        self._review_entry_highlight_photo = ImageTk.PhotoImage(overlay)
        item = self.canvas.create_image(
            x0, y0, anchor="nw", image=self._review_entry_highlight_photo,
            tags=("proofread-entry-highlight",),
        )
        # Keep the highlight above the scanned page but below all editable
        # overlays, so it reads as a line-level marker rather than a cover.
        try:
            self.canvas.tag_raise(item, "page")
        except tk.TclError:
            pass

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
        if not self.project or not (0 <= index < len(self.project.images)):
            return ""
        page = self.project.images[index]
        if index == self.current_index and self.current_page is not None:
            return str(len(self.entries))
        try:
            return str(len(read_pdic(pdic_path(page))))
        except (OSError, ValueError):
            return "0"

    def _page_illustration_count_text(self, index: int) -> str:
        """Return the effective PPP region count for one page, blank for zero.

        The current page uses the in-memory polygon list so manual additions and
        deletions are reflected immediately without disk I/O. Other pages are
        read lazily during the existing metadata refresh; no page image pixels
        are opened or decoded for this column.
        """
        if not self.project or not (0 <= index < len(self.project.images)):
            return ""
        current_index = self.__dict__.get("current_index", -1)
        current_page = self.__dict__.get("current_page")
        if index == current_index and current_page is not None:
            count = len(self.__dict__.get("polygons", []))
        else:
            try:
                count = len(read_ppp(self._ppp_read_path(self.project.images[index])))
            except (AttributeError, OSError, TypeError, ValueError):
                count = 0
        return str(count) if count > 0 else ""

    def _update_page_row(self, index: int) -> None:
        if not self.project or not hasattr(self, "page_list") or not (0 <= index < len(self.project.images)):
            return
        iid = str(index)
        if not self.page_list.exists(iid):
            return
        old_values = tuple(self.page_list.item(iid, "values"))
        section = self._page_section_count_text(index)
        lined = self._page_metadata(index)
        fill_status = self._word_fill_status_text(index)
        illustrations = self._page_illustration_count_text(index)
        page = self.project.images[index]
        page_stem = str(getattr(page, "stem", Path(str(page.name)).stem))
        bookmark = "●" if page_stem in self._bookmark_stems() else ""
        new_values = (bookmark, page_stem, section, lined, fill_status, illustrations)
        self.page_list.item(iid, values=new_values)
        active_column = self._page_list_sort_column
        if active_column:
            new_index = {
                "bookmark": 0, "page": 1, "section": 2, "lined": 3,
                "fill_status": 4, "illustrations": 5,
            }.get(active_column, 1)
            if len(old_values) >= 6:
                old_mapping = {
                    "bookmark": 0, "page": 1, "section": 2, "lined": 3,
                    "fill_status": 4, "illustrations": 5,
                }
            elif len(old_values) >= 5:
                old_mapping = {"bookmark": 0, "page": 1, "lined": 2, "fill_status": 3, "illustrations": 4}
            else:
                old_mapping = {"page": 0, "lined": 1, "fill_status": 2, "illustrations": 3}
            old_index = old_mapping.get(active_column, 0)
            old_value = old_values[old_index] if old_index < len(old_values) else ""
            new_value = new_values[new_index]
            if str(old_value) != str(new_value):
                self._schedule_page_list_resort()
        self._schedule_page_cell_overlay_refresh()

    def _refresh_page_metadata_step(self, generation: int, start: int) -> None:
        if generation != self._page_meta_generation or not self.project:
            return
        batch = 8
        stop = min(len(self.project.images), start + batch)
        for index in range(start, stop):
            self._update_page_row(index)
        if stop < len(self.project.images):
            self._page_meta_job = self.after(1, lambda g=generation, s=stop: self._refresh_page_metadata_step(g, s))
        else:
            self._page_meta_job = None

    def _refresh_page_quality_colors(self) -> None:
        """Refresh the lightweight '画线' state without reading OCR confidence caches."""
        if not self.project:
            return
        self._page_meta_generation += 1
        generation = self._page_meta_generation
        if self._page_meta_job:
            try: self.after_cancel(self._page_meta_job)
            except tk.TclError: pass
        self._page_meta_job = self.after_idle(lambda g=generation: self._refresh_page_metadata_step(g, 0))

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


    def refine_lines_selected_scope(self) -> None:
        """Re-run only Y refinement for existing PDIC markers in the selected range.

        This operation never detects new headwords and never deletes rows.  Each
        existing marker is treated as the coarse position and may move only
        within the refiner's local search radius, which is the hard safety bound.
        """
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
            "精修画线",
            f"将重新调用现有 Y 精修逻辑处理所选 {len(indices)} 页：\n"
            f"{first}" + (f" → {last}" if len(indices) > 1 else "") +
            "\n\n只允许移动已有画线，不会新增或删除任何画线；"
            "每条线的 Y 移动量不会超过当前精修搜索半径。是否继续？",
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
        # The explicit button means "run refinement now" even if automatic
        # refinement was disabled for normal detection.
        settings.paddle_refine_separator_y = True
        pages_info = {i: self.pages_tuple(i) for i in indices}

        def worker(index: int, _position: int, _total: int):
            page = pages[index]
            entries = read_pdic(pdic_path(page))
            original_count = len(entries)
            original_words = [entry.word for entry in entries]
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            refined, stats = refine_existing_entries(
                image, entries, settings, profile_page_index=index,
            )
            if len(refined) != original_count:
                raise RuntimeError(
                    f"{page.name} 精修前后画线数变化：{original_count} → {len(refined)}"
                )
            if [entry.word for entry in refined] != original_words:
                raise RuntimeError(f"{page.name} 精修意外修改了词条文本")
            write_pdic(pdic_path(page), refined, image.width, pages_info[index])
            return {
                "index": index,
                "page": page.name,
                **stats,
            }

        def done(completed, total, stopped, results, error) -> None:
            if error is not None:
                return
            moved = sum(int((row or {}).get("moved", 0)) for row in results)
            limited = sum(int((row or {}).get("limited", 0)) for row in results)
            max_delta = max(
                [int((row or {}).get("max_delta", 0)) for row in results] or [0]
            )
            if self.current_index in indices:
                self.load_page(self.current_index, skip_current_save=True)
            suffix = f"，{limited} 条触及安全界限" if limited else ""
            stopped_text = f"（提前停止：{completed}/{total} 页）" if stopped else ""
            self.status_var.set(
                f"精修画线完成{stopped_text}：移动 {moved} 条；"
                f"单条最大安全 Y 差值 {max_delta}px{suffix}"
            )

        self._start_batch_task(
            "精修画线",
            indices,
            worker,
            done,
            item_label=lambda i: pages[i].name,
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
            "只填充空白词条；已有文字和人工校对内容保持不变；"
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
                if str(entry.word or "").strip() or bool(entry.manually_selected)
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
                only_blank=True,
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
                    raise RuntimeError(f"{page.name} OCR文字意外覆盖了已有/人工文本")
            write_pdic(pdic_path(page), updated, image.width, pages_info[index])
            export_ocred(
                qt_root(project.root) / f"{page.stem}.OCRed",
                [entry.word for entry in updated],
            )
            return {"index": int(index), **stats}

        def done(completed, total, stopped, results, error):
            if error is not None:
                return
            if self.current_index in existing:
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
                f"{prefix}；填入 {filled} 条"
                f"（普通框 {regular}，大字框 {large}）"
                f"；未识别 {failed} 条；保护已有/人工文本 {skipped} 条"
            )

        self._start_batch_task(
            "普通画线后OCR文字",
            existing,
            worker,
            done,
            item_label=lambda index: project.images[index].name,
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
        self.save_pdic(silent=True)
        self.settings.detection_method = method
        settings = replace(self.settings)
        project = self.project
        pages_info = {i: self.pages_tuple(i) for i in indices}
        filter_path = headword_filter_rules_path(project.root, HEADWORD_FILTER_RULES_FILENAME)
        normal_executor = (
            ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
            if method == "left_edge" else None
        )

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            if normal_executor is not None:
                count = normal_executor.submit(
                    detect_entries_job, str(page), settings, pages_info[index], index
                ).result()
                return {"index": int(index), "count": int(count)}
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            cache_path = ocr_cache_root(project.root) / f"{page.stem}.json" if method in {"paddleocr", "combined"} else None
            sections = read_page_sections(page)
            entries, _geometry = detect_entries(
                image, settings, paddle_cache_path=cache_path,
                force_paddle_refresh=force_refresh,
                paddle_filter_rules_path=filter_path,
                profile_page_index=index,
                page_sections=sections,
            )
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
            write_pdic(pdic_path(page), entries, image.width, pages_info[index])
            result = {"index": int(index), "count": len(entries)}
            if text_stats:
                result.update({
                    "text_filled": int(text_stats.get("filled", 0)),
                    "text_regular": int(text_stats.get("regular", 0)),
                    "text_large": int(text_stats.get("large", 0)),
                    "text_failed": int(text_stats.get("failed", 0)),
                })
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
        from .pdic_text_cleanup import clear_selected_scope
        clear_selected_scope(self)


    def _ordered_entries_reading_order(self) -> list[WordEntry]:
        """Return current entries in canonical visual reading order without mutating them."""
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
        # Commit live state; cancel any older queued checkbox snapshot.
        deferred_job = self.__dict__.get("_deferred_save_job")
        if deferred_job is not None:
            try:
                self.after_cancel(deferred_job)
            except tk.TclError:
                pass
        self.__dict__["_deferred_save_job"] = None
        self.__dict__["_deferred_save_snapshot"] = None
        self.__dict__["_deferred_save_page"] = None
        # Review edits bypass stale main-canvas editor values.
        if sync_editors:
            self._sync_entry_editor_texts()
        self._sort_entries_reading_order()
        changed = write_pdic(pdic_path(self.current_page), self.entries, self.image.width, self.pages_tuple())
        self._last_pdic_write_changed = changed
        self._flush_pending_manual_override()
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
        write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)

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
        if self.autosave_var.get():
            # Avoid overwriting an in-flight batch page.
            if self._batch_active:
                if not self._batch_foreground_pages or not self._can_save_current_during_batch_navigation():
                    self.toggle_autosave()
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
                polygon_changed = write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
                if self._last_pdic_write_changed or polygon_changed:
                    self.status_var.set("已自动保存")
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
        default_bottom = self.settings.bottom_y if self.settings.crop_to_bottom_y else 0
        return {
            "version": CROP_SETTINGS_VERSION,
            "coordinate_space": SOURCE_COORDINATE_SPACE,
            "general_top_y": int(self.settings.start_y),
            "general_bottom_y": int(default_bottom),
            "entry_left_padding_x": 0,
            "entry_right_padding_x": 0,
            "integrate_illustrations": True,
            "polygon_margin": 0,
            "parallel_workers": int(self.settings.crop_parallel_workers),
            "special_pages": {},
        }

    def _load_crop_settings(self) -> dict:
        if not self.project:
            return self._crop_settings_defaults()
        path = qt_root(self.project.root) / CropSettingsDialog.CONFIG_NAME
        raw: dict = {}
        if path.exists():
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(candidate, dict):
                    raw = candidate
            except (OSError, ValueError, TypeError):
                raw = {}
        return _normalize_crop_settings_payload(raw, self.settings)


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
