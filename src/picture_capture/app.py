from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import bisect
import csv
import difflib
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

from PIL import Image, ImageOps, ImageTk

from . import __version__
from .appearance import (
    appearance_palette,
    apply_classic_widget_appearance,
    apply_native_titlebar_appearance,
    normalize_appearance_mode,
    themed_display_image,
    usage_guide_palette,
)
from .formats import pdic_path, read_pdic, read_ppp, write_pdic, write_ppp, write_text_atomic, read_picdic_index_records
from .models import (
    AppSettings, Entry as WordEntry, PolygonRegion, ProjectState,
    natural_text_key, read_noncomment_lines, resolve_wordslist_path, resolved_tesseract_language,
)
from .paddle_headwords import (
    DEFAULT_HEADWORD_FILTER_RULES,
    HEADWORD_FILTER_RULES_FILENAME,
    parse_headword_filter_rules,
)
from .environment_center import EnvironmentCenterWindow
from .runtime_environment import legacy_user_config_files, resolve_paddle_device, user_config_root
from .ui_compat import bind_context_menu, fit_window_to_work_area, preferred_font_family
from .layout_detection import detect_layout_consistency, detect_layout_parameters
from .layout_transform import LayoutTransform
from .coordinate_space import (
    CANONICAL_COORDINATE_SPACE,
    CANONICAL_REFERENCE_SPACE,
    REFERENCE_CANONICAL_WIDTH,
    SOURCE_COORDINATE_SPACE,
    canonical_geometry_to_stored,
    coordinate_contract,
    geometry_uses_canonical_pixels,
    legacy_parameter_scale,
    stored_geometry_to_canonical,
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
from .profile_setup import ProjectProfileWizard, _screen_work_area
from .profile_semantics import (
    effective_page_settings, entry_allowed_by_page_template, page_template_analysis_image,
)
from .picdic import PicDicBuildCancelled, build_picdic_package
from .image_utils import normalize_page_rgb
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
from .project_storage import (
    STORAGE_DIRNAME, ensure_project_storage, exports_root, has_legacy_project_data,
    headword_filter_rules_path, is_managed_project, migrate_legacy_project,
    ocr_cache_root, ppp_read_path_for_image, ppp_write_path_for_image, simplified_review_path_for_image,
    profile_path as project_profile_path, qt_root, replace_rules_path, settings_path,
    training_exports_root, word_fill_status_path, words_of_pages_default_path,
)
from .recent_projects import (
    load_recent_projects, recent_project_details, remove_recent_project, touch_recent_project,
)
from .processing import (
    append_crop_log,
    append_illustration_crop_log,
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
    split_single_lines,
    split_whole_entries,
    split_illustrations,
    illustration_crop_bounds,
    illustration_polygon_box,
    entry_crop_column_boxes,
    entry_crop_piece_filename,
    resolve_crop_worker_count,
    refine_existing_entries,
    split_whole_entries_job,
    split_illustrations_job,
    detect_illustrations_job,
)


DETECTION_LABELS = {
    "paddleocr": "PaddleOCR（推荐｜词头＋坐标）",
    "left_edge": "左缘规则（备用）",
}
DETECTION_VALUES = {label: value for value, label in DETECTION_LABELS.items()}
OCR_ENGINE_LABELS = {"tesseract": "Tesseract", "paddleocr": "PaddleOCR"}
OCR_ENGINE_VALUES = {label: value for value, label in OCR_ENGINE_LABELS.items()}
LENS_MODE_LABELS = {
    "off": "① 关闭",
    "diagnostic": "② 仅诊断对照",
    "conflict": "③ 冲突/低可信时调用（推荐）",
    "full": "④ 全页参与三OCR融合",
}
LENS_MODE_VALUES = {label: value for value, label in LENS_MODE_LABELS.items()}
SESSION_STATE_FILENAME = "session_state.json"

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


CROP_SETTINGS_VERSION = 6


def _geometry_reference_width(settings: AppSettings) -> int:
    """Return the persisted canonical reference-page width for project rules."""
    value = int(getattr(settings, "geometry_reference_width", 0) or 0)
    if value > 0:
        return value
    legacy = int(getattr(settings, "parameter_display_width", 0) or 0)
    return legacy if legacy > 0 else REFERENCE_CANONICAL_WIDTH


def _normalize_crop_settings_payload(
    raw: dict | None, settings: AppSettings,
) -> dict:
    """Normalize historical crop settings to the v6 reference-page contract."""
    raw = raw if isinstance(raw, dict) else {}
    reference_width = _geometry_reference_width(settings)
    default_bottom = int(settings.bottom_y) if settings.crop_to_bottom_y else 0

    if not raw:
        return {
            "version": CROP_SETTINGS_VERSION,
            "coordinate_space": CANONICAL_REFERENCE_SPACE,
            "geometry_reference_width": reference_width,
            "general_top_v": int(settings.start_y),
            "general_bottom_v": default_bottom,
            "entry_left_padding_u": 0,
            "entry_right_padding_u": 0,
            "integrate_illustrations": True,
            "polygon_margin": 0,
            "parallel_workers": int(settings.crop_parallel_workers),
            "special_pages": {},
        }

    version = int(raw.get("version", 0) or 0)
    source_space = str(raw.get("coordinate_space") or "")
    source_reference = int(raw.get("geometry_reference_width", 0) or 0)

    if version >= CROP_SETTINGS_VERSION and source_space == CANONICAL_REFERENCE_SPACE:
        source_reference = source_reference if source_reference > 0 else reference_width
        factor = reference_width / max(1, source_reference)
        old_names = False
    else:
        # Crop Settings <= v5 used the same legacy display-pixel convention as
        # old layout geometry. ProjectState may already have migrated AppSettings,
        # but parameter_display_width is intentionally retained for this adapter.
        factor = 1.0 / max(
            0.01, legacy_parameter_scale(reference_width, settings),
        )
        old_names = True

    def scalar(new_name: str, old_name: str, default: int = 0) -> int:
        key = old_name if old_names else new_name
        if key not in raw:
            return int(default)
        try:
            value = int(raw.get(key, 0) or 0)
        except (TypeError, ValueError):
            return int(default)
        if value == 0:
            return 0
        return max(0, round(value * factor))

    specials_raw = raw.get("special_pages")
    specials: dict[str, dict[str, int]] = {}
    if isinstance(specials_raw, dict):
        for page, values in specials_raw.items():
            if not isinstance(values, dict):
                continue
            if old_names:
                top = values.get("top_y", 0)
                bottom = values.get("bottom_y", 0)
            else:
                top = values.get("top_v", 0)
                bottom = values.get("bottom_v", 0)
            try:
                top_v = max(0, round(int(top or 0) * factor))
                bottom_v = max(0, round(int(bottom or 0) * factor))
            except (TypeError, ValueError):
                continue
            specials[str(page)] = {"top_v": top_v, "bottom_v": bottom_v}

    return {
        "version": CROP_SETTINGS_VERSION,
        "coordinate_space": CANONICAL_REFERENCE_SPACE,
        "geometry_reference_width": reference_width,
        "general_top_v": scalar("general_top_v", "general_top_y", int(settings.start_y)),
        "general_bottom_v": scalar("general_bottom_v", "general_bottom_y", default_bottom),
        "entry_left_padding_u": scalar("entry_left_padding_u", "entry_left_padding", 0),
        "entry_right_padding_u": scalar("entry_right_padding_u", "entry_right_padding", 0),
        "integrate_illustrations": bool(raw.get("integrate_illustrations", True)),
        "polygon_margin": scalar("polygon_margin", "polygon_margin", 0),
        "parallel_workers": int(raw.get("parallel_workers", settings.crop_parallel_workers) or 0),
        "special_pages": specials,
    }

OCR_SCOPE_LABELS = {"current": "当前页", "all": "全部页面"}
OCR_SCOPE_VALUES = {label: value for value, label in OCR_SCOPE_LABELS.items()}
OCR_REFRESH_LABELS = {
    "reuse": "复用缓存（参数变化自动重算）",
    "force": "强制重新识别",
}
OCR_REFRESH_VALUES = {label: value for value, label in OCR_REFRESH_LABELS.items()}

def _natural_text_key(value: object) -> tuple:
    """Natural, case-insensitive key used by the sortable page list.

    Numeric runs are compared as integers so e.g. page2 sorts before page10.
    The tagged tuple parts keep text and integer components mutually comparable.
    """
    return natural_text_key(value)


def effective_main_overlay_font_size(
    image_width: int, view_scale: float, settings: AppSettings,
) -> int:
    """Return the main overlay font size.

    1400 px displayed page width corresponds to the configured base font size.
    """

    base_size = max(5, int(settings.main_entry_font_size))

    if settings.main_entry_follow_zoom:
        displayed_page_width = max(1.0, image_width * view_scale)
        scale = displayed_page_width / 1400.0
        font_size = round(base_size * scale)
    else:
        font_size = base_size

    return max(5, min(72, font_size))


def binary_preview_image(source: Image.Image) -> Image.Image:
    """Create a display-only Otsu black/white preview without mutating source."""
    gray = ImageOps.grayscale(source)
    histogram = gray.histogram()
    total = sum(histogram)
    weighted = sum(i * count for i, count in enumerate(histogram))
    background = 0
    weight_background = 0
    best_variance = -1.0
    threshold = 127
    for value, count in enumerate(histogram):
        weight_background += count
        if not weight_background:
            continue
        weight_foreground = total - weight_background
        if not weight_foreground:
            break
        background += value * count
        mean_background = background / weight_background
        mean_foreground = (weighted - background) / weight_foreground
        variance = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2
        if variance > best_variance:
            best_variance = variance
            threshold = value
    return gray.point(lambda pixel: 255 if pixel > threshold else 0, mode="1").convert("RGB")


class VerticalWordText(tk.Text):
    """A real editable Tk widget that presents a headword as a narrow vertical column.

    It intentionally exposes the small subset of Entry-like methods used by the
    main overlay code, so OCR fill, autosave, wordslist styling, and manual edit
    persistence share the same code path as horizontal Entry widgets.
    """

    @staticmethod
    def _entry_index(index) -> str:
        if index in {"end", tk.END}:
            return "end-1c"
        if isinstance(index, int):
            return f"1.{max(0, index)}"
        if str(index) == "0":
            return "1.0"
        return str(index)

    def get(self, *args):
        if args:
            return super().get(*args)
        # Main-overlay words are single logical strings.  A pasted newline must
        # not become part of the dictionary headword.
        return super().get("1.0", "end-1c").replace("\n", "")

    def delete(self, first=0, last=None):
        first_index = self._entry_index(first)
        if last is None:
            return super().delete(first_index)
        return super().delete(first_index, self._entry_index(last))

    def insert(self, index, chars, *args):
        return super().insert(self._entry_index(index), chars, *args)

    def icursor(self, index) -> None:
        target = self._entry_index(index)
        self.mark_set("insert", target)
        self.see(target)

    def selection_range(self, start, end) -> None:
        self.tag_remove("sel", "1.0", "end")
        self.tag_add("sel", self._entry_index(start), self._entry_index(end))


def vertical_marker_contact_gap(marker_line_width: int) -> int:
    """Offset from marker centreline so the editor border touches its painted edge."""
    return max(1, (max(1, int(marker_line_width)) + 1) // 2)


def vertical_overlay_layout(
    marker_x: float,
    marker_y: float,
    editor_width: int,
    editor_height: int,
    writing_mode: str,
    *,
    gap: int = 3,
) -> tuple[
    tuple[int, int, int, int],
    tuple[float, float],
    str,
    tuple[float, float],
    str,
]:
    """Return a fixed-size real vertical editor layout around the marker.

    editor_width/editor_height are the actual requested dimensions of the
    vertical Text widget. For vertical-rl the widget stays entirely to the
    left of the marker; vertical-lr is the exact opposite.
    """
    proxy_width = max(1, int(round(editor_width)))
    proxy_height = max(1, int(round(editor_height)))
    gap = max(0, int(gap))
    top = int(round(marker_y))

    if writing_mode == "vertical-rl":
        right = int(round(marker_x - gap))
        left = right - proxy_width
        popup = (float(right), float(top))
        popup_anchor = "ne"
        index = (float(left - 3), float(top))
        index_anchor = "ne"
    elif writing_mode == "vertical-lr":
        left = int(round(marker_x + gap))
        right = left + proxy_width
        popup = (float(left), float(top))
        popup_anchor = "nw"
        index = (float(right + 3), float(top))
        index_anchor = "nw"
    else:
        raise ValueError(f"Not a vertical writing mode: {writing_mode}")

    box = (left, top, right, top + proxy_height)
    return box, popup, popup_anchor, index, index_anchor


def vertical_ocr_menu_layout(
    entry_box: tuple[int, int, int, int],
    menu_width: int,
    writing_mode: str,
    canvas_width: int,
) -> tuple[float, float, str]:
    """Place the OCR selector outside the vertical entry box on the same side."""
    left, top, right, _bottom = entry_box
    menu_width = max(1, int(menu_width))
    if writing_mode == "vertical-rl":
        x = left - 3
        if x - menu_width < 2:
            x = menu_width + 2
        return float(x), float(top), "ne"
    if writing_mode == "vertical-lr":
        x = right + 3
        if x + menu_width > canvas_width - 2:
            x = max(0, canvas_width - menu_width - 2)
        return float(x), float(top), "nw"
    raise ValueError(f"Not a vertical writing mode: {writing_mode}")


def transformed_entry_anchor(
    transform, canonical_x: float, canonical_y: float, column_width: float,
    x_ratio: float, source_size: tuple[int, int], view_scale: float,
) -> tuple[float, float]:
    """Apply the entry offset in canonical space, then map it to the source."""
    source_x, source_y = transform.canonical_to_source_point(
        round(canonical_x + column_width * x_ratio), round(canonical_y), source_size,
    )
    return source_x * view_scale, source_y * view_scale


def horizontal_overlay_layout(
    transform, canonical_x: float, canonical_y: float, column_width: float,
    x_ratio: float, source_size: tuple[int, int], view_scale: float, *, rtl: bool,
) -> tuple[tuple[float, float], str, tuple[float, float], str]:
    """Return mirror-equivalent editor/index anchors for horizontal writing."""
    editor = transformed_entry_anchor(
        transform, canonical_x, canonical_y, column_width, x_ratio,
        source_size, view_scale,
    )
    index_source = transform.canonical_to_source_point(
        round(canonical_x + column_width), round(canonical_y), source_size,
    )
    index = (index_source[0] * view_scale + (-3 if rtl else 3), index_source[1] * view_scale)
    return editor, ("ne" if rtl else "nw"), index, ("ne" if rtl else "nw")


def horizontal_ocr_menu_layout(
    editor_x: float, editor_y: float, editor_width: int, *, rtl: bool,
) -> tuple[float, float, str]:
    """Place the OCR selector outside the editor in its reading direction."""
    if rtl:
        return editor_x - editor_width - 3, editor_y, "ne"
    return editor_x + editor_width + 3, editor_y, "nw"


def _sorted_page_list_rows(rows: list[tuple[str, tuple]], column: str, descending: bool = False) -> list[tuple[str, tuple]]:
    """Sort Treeview-like page rows without changing their stable page iids.

    ``rows`` contains ``(iid, values)`` pairs. Empty cells stay at the bottom in
    either direction, while visible values use natural text ordering.
    """
    # Accept older four/five-value rows in unit callers/session migrations.
    max_values = max((len(values) for _iid, values in rows), default=0)
    has_section = max_values >= 6
    has_bookmark = max_values >= 5
    if has_section:
        mapping = {
            "bookmark": 0, "page": 1, "section": 2, "lined": 3,
            "fill_status": 4, "illustrations": 5,
        }
    elif has_bookmark:
        mapping = {"bookmark": 0, "page": 1, "lined": 2, "fill_status": 3, "illustrations": 4}
    else:
        mapping = {"page": 0, "lined": 1, "fill_status": 2, "illustrations": 3}
    column_index = mapping.get(column, 1 if has_bookmark else 0)
    populated: list[tuple[str, tuple]] = []
    empty: list[tuple[str, tuple]] = []
    for row in rows:
        values = row[1]
        value = values[column_index] if column_index < len(values) else ""
        (populated if str(value).strip() else empty).append(row)
    populated.sort(
        key=lambda row: _natural_text_key(row[1][column_index] if column_index < len(row[1]) else ""),
        reverse=descending,
    )
    return populated + empty

def _fill_status_cell_style(status_text: object) -> tuple[str, str] | None:
    """Return semantic (background, foreground) colors for fill-status cells.

    ``未核对`` deliberately uses the native Treeview background, so it returns
    ``None`` and no overlay is created.
    """
    text = str(status_text or "").strip()
    if text == "一致":
        return "#d9ead3", "#245b2a"
    if text.startswith("少 " ) or text.startswith("多 " ) or text in {"少", "多"}:
        return "#f8d7da", "#6b1f25"
    if text == "待重新核对":
        return "#fff3cd", "#6b5714"
    if text == "无资料":
        return "#e9ecef", "#495057"
    return None


def _review_crop_settings(image: Image.Image, settings: AppSettings, viewer_width: int) -> AppSettings:
    """Return stable single-line crop geometry for the review panel.

    Modern projects already store full-resolution canonical geometry, so review
    crops must not depend on the viewer width. The fitted-display reference is
    retained only for an unmigrated legacy settings object.
    """
    local = replace(settings)
    if not geometry_uses_canonical_pixels(local):
        available = max(500, int(viewer_width) - 24)
        fit_scale = min(1.0, available / max(1, image.width))
        local.parameter_display_width = max(1, round(image.width * fit_scale))
    return local


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


def _is_single_cjk_review_headword(value: object) -> bool:
    """Return True for a single CJK ideograph used as a review headword.

    Single-character display headwords in classical CJK dictionaries are often
    typeset substantially taller than ordinary multi-character entries.  They
    therefore need a review-only vertical allowance without changing the
    project's global character-height setting.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    chars = [ch for ch in text if not ch.isspace() and not unicodedata.category(ch).startswith("P")]
    if len(chars) != 1:
        return False
    code = ord(chars[0])
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x3134F
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
    """Return a proofreading crop box with an explicit single-CJK height.

    Normal rows use the shared ``character_height`` exactly as the main window
    does. A one-character CJK headword uses the independent review-only height.
    We intentionally do not cap it at the next marker: hand-drawn separator Y
    positions are not perfectly uniform, and that old cap could re-clip a tall
    display character even after increasing its requested row height.
    """
    if not _is_single_cjk_review_headword(entry.word):
        if geometry.transform.kind != "identity":
            regular_settings = replace(settings)
            regular_settings.character_height = _effective_review_regular_crop_height(settings)
            return line_box(entry, geometry, image, regular_settings)
        left, _old_top, right, _bottom = line_box(entry, geometry, image, settings)
        canonical_width = geometry.transform.canonical_size(image.size)[0]
        row_padding = stored_geometry_to_canonical(
            max(0, int(settings.row_padding)), canonical_width, settings,
        )
        regular_height = stored_geometry_to_canonical(
            _effective_review_regular_crop_height(settings),
            canonical_width,
            settings,
        )
        half_spacing = round(0.5 * row_padding)
        # Identity layout: source Y and canonical V are the same coordinate.
        top = max(geometry.top, int(entry.y) - half_spacing)
        return left, top, right, min(image.height, top + max(1, regular_height))

    single_settings = replace(settings)
    single_settings.character_height = _effective_review_single_cjk_line_height(settings)
    return line_box(entry, geometry, image, single_settings)

def _review_editor_font_size(settings: AppSettings) -> int:
    """Review text font is fixed; image zoom must not resize editor typography."""
    return max(5, int(settings.review_entry_font_size))


def _entry_font_spec(family: str, size: int, bold: bool = False, italic: bool = False) -> tuple:
    """Return a Tk font tuple while keeping main/review typography independent."""
    styles: list[str] = []
    if bold:
        styles.append("bold")
    if italic:
        styles.append("italic")
    return (str(family or "TkDefaultFont"), int(size), *styles)


def _review_similarity_key(value: object) -> str:
    """Normalize a review/OCR string for visual similarity comparison.

    Full/half-width forms and case are normalized, while whitespace and
    punctuation are ignored. Letters (including accents), CJK characters and
    digits remain significant.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    kept: list[str] = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch.isspace() or category.startswith("P") or category.startswith("Z"):
            continue
        kept.append(ch)
    return "".join(kept)


def _review_text_similarity(left: object, right: object) -> float | None:
    """Return 0..1 OCR/editor similarity, or None when either side is blank."""
    a = _review_similarity_key(left)
    b = _review_similarity_key(right)
    if not a or not b:
        return None
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _review_similarity_color(score: float | None) -> str:
    """Semantic background colour for one OCR option in the review panel."""
    if score is None:
        return "#f2f2f2"
    if score >= 0.98:
        return "#b7e1cd"
    if score >= 0.85:
        return "#d9ead3"
    if score >= 0.65:
        return "#fff2cc"
    if score >= 0.40:
        return "#fce5cd"
    return "#f4cccc"


def _candidate_choice_rows(candidate: dict | None) -> list[tuple[str, str, str, float | None, bool]]:
    """Return compact, deterministic OCR choices for one review candidate.

    The last boolean marks the fused/final row.  Engine rows are deliberately
    retained even when they recognize the same lemma: seeing agreement between
    PaddleOCR, Tesseract and Lens is useful context when editing on the page.
    """
    if not candidate:
        return []
    rows: list[tuple[str, str, str, float | None, bool]] = []
    for engine, label in (("paddle", "PaddleOCR"), ("tesseract", "Tesseract"), ("lens", "Google Lens")):
        side = candidate.get(engine, {}) or {}
        word = str(side.get("lemma") or "").strip()
        if not word:
            continue
        confidence = side.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        rows.append((engine, label, word, confidence_value, False))
    final_word = str(candidate.get("word") or "").strip()
    if final_word:
        rows.append((str(candidate.get("final_engine") or "fusion"), "融合结果", final_word, None, True))
    return rows


def _build_words_page_lookup(page_stems: list[str]) -> tuple[dict[str, str], dict[int, str], dict[int, str]]:
    """Build O(1) lookup tables for large page-aware word lists.

    v2.9.5 resolved every single TXT row by rebuilding an exact-name dict and
    rescanning all project page stems.  On a 7,822-page / 190k-word dictionary
    that becomes effectively O(words × pages) and can look like a hung GUI.
    The tables below are built once, preserving the old ambiguity rules.
    """
    exact: dict[str, str] = {}
    numeric_candidates: dict[int, list[str]] = {}
    suffix_candidates: dict[int, list[str]] = {}
    for stem in page_stems:
        exact[stem.casefold()] = stem
        if stem.isdigit():
            numeric_candidates.setdefault(int(stem), []).append(stem)
        match = re.search(r"(\d+)$", stem)
        if match:
            suffix_candidates.setdefault(int(match.group(1)), []).append(stem)
    numeric = {number: values[0] for number, values in numeric_candidates.items() if len(values) == 1}
    suffix = {number: values[0] for number, values in suffix_candidates.items() if len(values) == 1}
    return exact, numeric, suffix


def _resolve_words_page_token(
    token: str, page_stems: list[str],
    lookup: tuple[dict[str, str], dict[int, str], dict[int, str]] | None = None,
) -> str | None:
    """Resolve a page token from legacy text to one project page stem."""
    cleaned = Path(str(token).strip()).stem.strip()
    if not cleaned:
        return None
    exact, numeric, suffix = lookup or _build_words_page_lookup(page_stems)
    hit = exact.get(cleaned.casefold())
    if hit:
        return hit
    if cleaned.isdigit():
        number = int(cleaned)
        hit = numeric.get(number)
        if hit:
            return hit
        return suffix.get(number)
    return None


def _parse_words_of_pages_text(
    text: str, page_stems: list[str], *, present_pages: set[str] | None = None,
) -> dict[str, list[str]]:
    """Parse page-aware legacy headword text without cross-page spillover.

    Supported forms are full PDIC records (page stem in field 6), tab-delimited
    ``page<TAB>word`` rows, and explicit page sections such as ``[0012]`` or
    ``页码: 0012``. A plain undivided word list is deliberately rejected: once
    page boundaries are unknown, distributing by cursor would recreate the exact
    spillover bug this importer is intended to prevent.
    """
    mapping: dict[str, list[str]] = {stem: [] for stem in page_stems}
    lookup = _build_words_page_lookup(page_stems)
    raw_lines = text.splitlines()
    nonblank = [line for line in raw_lines if line.strip()]
    if not nonblank:
        return mapping

    rich_hits = 0
    for raw in nonblank:
        fields = raw.split("#")
        if len(fields) >= 8:
            page = _resolve_words_page_token(fields[5], page_stems, lookup)
            if page is not None:
                mapping[page].append(fields[0].strip())
                if present_pages is not None:
                    present_pages.add(page)
                rich_hits += 1
    if rich_hits:
        return mapping

    tab_hits = 0
    tab_mapping: dict[str, list[str]] = {stem: [] for stem in page_stems}
    for raw in nonblank:
        fields = raw.split("\t", 1)
        if len(fields) != 2:
            continue
        page = _resolve_words_page_token(fields[0], page_stems, lookup)
        if page is not None:
            tab_mapping[page].append(fields[1].strip())
            if present_pages is not None:
                present_pages.add(page)
            tab_hits += 1
    if tab_hits:
        return tab_mapping

    section_mapping: dict[str, list[str]] = {stem: [] for stem in page_stems}
    current: str | None = None
    saw_section = False
    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped:
            continue
        match = re.match(r"^\[([^\]]+)\]$", stripped)
        if not match:
            match = re.match(r"^(?:page|页码|頁碼|页|頁)\s*[:：]?\s*(\S+)\s*$", stripped, re.I)
        if match:
            page = _resolve_words_page_token(match.group(1), page_stems, lookup)
            if page is None:
                raise ValueError(f"TXT 中找不到对应项目页面：{match.group(1)}")
            current = page
            if present_pages is not None:
                present_pages.add(page)
            saw_section = True
            continue
        if current is not None:
            section_mapping[current].append(stripped.split("#", 1)[0].strip())
    if saw_section:
        return section_mapping

    raise ValueError(
        "该 TXT 没有可识别的页码边界。请使用完整 PDIC/_WordsOfPages 记录、"
        "page\t词条，或 [页码] 分组格式；为避免错页，本功能不会把无分页的词表顺序灌入下一页。"
    )


def _fill_page_entries(entries: list[WordEntry], words: list[str]) -> tuple[int, int, int]:
    """Fill only the words belonging to one page and never borrow from neighbours."""
    ordered = list(entries)
    count = min(len(ordered), len(words))
    for entry, word in zip(ordered[:count], words[:count]):
        entry.word = str(word).strip()
    return count, len(ordered), len(words)


def _parse_merged_pdic_text(
    text: str, page_stems: list[str],
) -> tuple[dict[str, list[WordEntry]], dict[str, int]]:
    """Parse a whole-dictionary PDIC text into independent per-page entries.

    A merged PDIC is simply a concatenation of normal 8-field PDIC records.
    Field 6 (index 5) identifies the source page.  Records are resolved against
    the current project's page stems with the same leading-zero/numeric rules
    used by the page-aware headword importer.  Unknown pages are ignored rather
    than spilled into a neighbouring page; malformed PDIC rows are rejected.
    """
    mapping: dict[str, list[WordEntry]] = {stem: [] for stem in page_stems}
    lookup = _build_words_page_lookup(page_stems)
    matched = 0
    unmatched = 0
    nonblank = 0
    for line_no, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        nonblank += 1
        fields = raw.split("#")
        if len(fields) < 8:
            raise ValueError(f"整体 PDIC 第 {line_no} 行字段不足 8 个，不是有效 PDIC 记录")
        try:
            x = int(float(fields[1]))
            y = int(float(fields[2]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"整体 PDIC 第 {line_no} 行坐标无效") from exc
        page = _resolve_words_page_token(fields[5], page_stems, lookup)
        if page is None:
            unmatched += 1
            continue
        mapping[page].append(
            WordEntry(
                word=str(fields[0]),
                x=x,
                y=y,
                current_page=page,
                previous_page=str(fields[6] or "@"),
                next_page=str(fields[7] or "@"),
            )
        )
        matched += 1
    if nonblank == 0:
        raise ValueError("整体 PDIC 文件为空，没有可用于恢复的记录。")
    if matched == 0:
        raise ValueError("整体 PDIC 中没有任何记录能对应当前项目页面，请核对是否选择了正确文件。")
    return mapping, {"records": nonblank, "matched": matched, "unmatched": unmatched}


def _write_pdic_atomic(
    target: Path, entries: list[WordEntry], image_width: int, pages: tuple[str, str, str],
) -> None:
    """Atomically replace one page PDIC so stop/crash never leaves a half file."""
    temp = target.with_name(f".{target.name}.restore.tmp")
    try:
        write_pdic(temp, entries, image_width, pages)
        os.replace(temp, target)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def _page_word_mapping_text(page_order: list[str], mapping: dict[str, list[str]]) -> str:
    """Render page-aware headwords as ``page<TAB>word`` text in page order."""
    rows: list[str] = []
    for page in page_order:
        for raw_word in mapping.get(page, []):
            word = str(raw_word or "").replace("\t", " ").replace("\r", " ").replace("\n", " ")
            rows.append(f"{page}\t{word}")
    return "\n".join(rows) + ("\n" if rows else "")


def _compare_page_word_sequences(page: str, old_words: list[str], new_words: list[str]) -> list[dict[str, object]]:
    """Return line-oriented additions, deletions and replacements for one page.

    The comparison is exact after the surrounding page-aware parsers have
    stripped line endings/outer whitespace.  ``SequenceMatcher`` first anchors
    unchanged headwords, so a newly inserted row normally appears as an insert
    rather than turning every following row into a false modification.
    """
    changes: list[dict[str, object]] = []
    matcher = difflib.SequenceMatcher(a=list(old_words), b=list(new_words), autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for old_index in range(i1, i2):
                changes.append({
                    "kind": "删除", "page": page,
                    "old_index": old_index + 1, "old": old_words[old_index],
                    "new_index": None, "new": "",
                })
            continue
        if tag == "insert":
            for new_index in range(j1, j2):
                changes.append({
                    "kind": "新增", "page": page,
                    "old_index": None, "old": "",
                    "new_index": new_index + 1, "new": new_words[new_index],
                })
            continue

        paired = min(i2 - i1, j2 - j1)
        for offset in range(paired):
            old_index = i1 + offset
            new_index = j1 + offset
            changes.append({
                "kind": "修改", "page": page,
                "old_index": old_index + 1, "old": old_words[old_index],
                "new_index": new_index + 1, "new": new_words[new_index],
            })
        for old_index in range(i1 + paired, i2):
            changes.append({
                "kind": "删除", "page": page,
                "old_index": old_index + 1, "old": old_words[old_index],
                "new_index": None, "new": "",
            })
        for new_index in range(j1 + paired, j2):
            changes.append({
                "kind": "新增", "page": page,
                "old_index": None, "old": "",
                "new_index": new_index + 1, "new": new_words[new_index],
            })
    return changes


def _compare_page_word_mappings(
    page_order: list[str], old_mapping: dict[str, list[str]], new_mapping: dict[str, list[str]],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Compare old/new page-aware word mappings and return changes + totals."""
    changes: list[dict[str, object]] = []
    counts = {"新增": 0, "删除": 0, "修改": 0, "old_rows": 0, "new_rows": 0}
    for page in page_order:
        old_words = list(old_mapping.get(page, []))
        new_words = list(new_mapping.get(page, []))
        counts["old_rows"] += len(old_words)
        counts["new_rows"] += len(new_words)
        page_changes = _compare_page_word_sequences(page, old_words, new_words)
        changes.extend(page_changes)
        for item in page_changes:
            kind = str(item.get("kind") or "")
            if kind in {"新增", "删除", "修改"}:
                counts[kind] += 1
    return changes, counts


def _build_modern_dialog_heading(
    parent: tk.Misc, title: str, subtitle: str,
) -> ttk.Frame:
    """Shared heading block for secondary work windows."""
    block = ttk.Frame(parent)
    block.pack(fill="x", pady=(0, 12))
    base = font.nametofont("TkDefaultFont").copy()
    heading_font = base.copy()
    heading_font.configure(
        size=max(13, abs(int(base.cget("size"))) + 4),
        weight="bold",
    )
    ttk.Label(block, text=title, font=heading_font).pack(anchor="w")
    subtitle_label = ttk.Label(
        block,
        text=subtitle,
        foreground="#666666",
        justify="left",
    )
    subtitle_label.pack(anchor="w", fill="x", pady=(3, 0))

    def resize_subtitle(event: tk.Event) -> None:
        try:
            subtitle_label.configure(wraplength=max(160, int(event.width) - 4))
        except tk.TclError:
            pass

    block.bind("<Configure>", resize_subtitle, add="+")
    return block


class UsageGuideWindow(tk.Toplevel):
    """Modern, task-oriented in-app guide for the main Picture Capture workflow."""

    PAGES = (
        (
            "quick",
            "快速开始",
            "第一次使用时，按这条路径走最稳妥：先确定结构，再做代表页验证，最后批量处理。",
            (
                (
                    "01", "建立项目并完成【项目Profile】",
                    "用【新建项目】或【已有项目】进入词典目录。新项目先完成词典信息、阅读方式、页面模板、"
                    "词头结构和代表页测试。Project Profile 是配置入口，不建议一开始就逐个修改高级参数。"
                ),
                (
                    "02", "先检测版面，再看结果是否合理",
                    "在【一、普通版面参数】选择有代表性的页面范围，运行【检测版面参数】。重点检查分栏数、"
                    "页眉/页尾、首栏 X、单栏宽和栏间空；检测值应先通过肉眼确认，再进入批量画线。"
                ),
                (
                    "03", "默认先用 OCR画线验证代表页",
                    "先在 1–3 张典型页面运行【运行OCR画线（推荐）】。OCR画线是主流程；"
                    "普通画线仅作为左缘极稳定版式或 OCR 暂不可用时的备用方案。模型和原图没有变化时保留“使用有效缓存（推荐）”。"
                ),
                (
                    "04", "先校对误差模式，再决定是否调参",
                    "用【词条校对】检查漏检、误检、OCR 拼写和顺序。若只是少量个案，直接校对通常比继续调全局参数更安全；"
                    "只有出现稳定、重复的错误模式时，再到【设置中心】针对性调整。"
                ),
                (
                    "05", "正式切图前一定先预览",
                    "进入【切图设置】确认上下边界、左右留白和插图关系，再使用“切图预览”检查完整 Crop Plan。"
                    "确认无误后再执行【词条切图】或【插图切图】。"
                ),
                (
                    "06", "最后生成索引、PicDic 或训练资料",
                    "完成校对和切图后，再使用【导出PicDic索引】、【PicDic制作】或【导出训练标记包】。"
                    "需要阶段性留档时可用【备份PDIC】。"
                ),
            ),
        ),
        (
            "drawing",
            "画线与 OCR",
            "OCR画线是默认推荐模式；普通画线降为备用，只在左缘极稳定的简单版式或 OCR 暂不可用时优先考虑。",
            (
                (
                    "A", "OCR画线：默认推荐",
                    "优先运行【OCR画线】。它同时利用词头文字、左缘位置、粗体/字高、词性和特殊符号等证据，"
                    "比单纯依赖栏左墨迹更适合真实词典中的复杂版式；默认只启用 PaddleOCR；Tesseract 与 Google Lens 按需手动开启。"
                ),
                (
                    "B", "有效缓存：OCR 不必每次重跑",
                    "保持“使用有效缓存（推荐）”即可。缓存会在真正影响原始 OCR 的设置、模型或图像变化时自动失效；"
                    "仅调整候选判定参数时通常无需强制重新识别。"
                ),
                (
                    "C", "普通画线：备用而不是默认",
                    "普通画线只依赖栏位置、墨迹和行高。它适合词头始终紧贴栏左、正文缩进稳定的简单版式，"
                    "或 OCR 环境暂不可用时快速应急；若 OCR 可用，建议仍以 OCR画线作为主流程。"
                ),
                (
                    "D", "页面范围会影响批量任务",
                    "页面列表上方可选“当前页 / 当前页至末页 / 指定范围”。检测版面、画线、插图识别和切图等批量操作"
                    "都会读取这里的范围；指定范围可使用类似 12~18,23,31 的写法。"
                ),
                (
                    "E", "主画布是最后的人工控制层",
                    "左键可手动增加词条线；Delete 或反引号键可删除当前词条。普通模式下右键进入下一页。"
                    "鼠标滚轮纵向滚动，Shift + 滚轮横向滚动，Ctrl + 滚轮缩放。"
                ),
                (
                    "F", "不要把高级参数当作第一步",
                    "候选置信度、最低候选分、同行合并等参数已经移到【设置中心 → OCR画线 → 高级设置】。"
                    "先通过代表页判断具体错误类型，再调整对应参数，避免为解决一个个案破坏整本词典的稳定性。"
                ),
            ),
        ),
        (
            "review",
            "校对与词表",
            "校对窗口的目标不是重新做 OCR，而是把“图像—候选—词条—简体—参考词表”集中到一个连续工作流里。",
            (
                (
                    "01", "进入【词条校对】后逐条处理",
                    "左侧查看对应切图，右侧直接编辑词条。PaddleOCR / Tesseract / Lens 的可用候选会集中显示，"
                    "需要时单击候选即可填入；主界面 OCR 辅助显示会默认收起，减少重复信息。"
                ),
                (
                    "02", "参考词表用于定位，不代替人工判断",
                    "加载 wordslist 后，右侧只显示当前词附近的窗口。自动定位会根据同源连续顺序或外部索引排序选择策略；"
                    "如果词条确实缺失或词表不同源，不应为了“对齐词表”而强行改写扫描页内容。"
                ),
                (
                    "03", "繁简与网络核验是辅助证据",
                    "简体栏使用 OpenCC 生成初始结果，人工修改后会独立保存。CC-CEDICT、萌典、维基词典和网络搜索用于快速核验，"
                    "其中“未检出”只表示当前来源没有精确命中，不等于词条不存在。"
                ),
                (
                    "04", "删除和保存保持联动",
                    "校对行左侧【X】和反引号快捷键都会删除当前词条，并同步清理对应简化记录。"
                    "自动保存、翻页、关闭校对窗口都会保存当前修改，避免只改了显示但没有落盘。"
                ),
                (
                    "05", "完成一段后再做顺序检查",
                    "词头顺序核对会根据 OCR 语言选择相应排序预设，也支持 Unicode 和自定义多字符排序单元。"
                    "顺序异常更适合用于发现跳词、误识别或重复词，而不是自动删除候选。"
                ),
            ),
        ),
        (
            "illustration",
            "插图与切图",
            "插图、词条和 Crop Plan 使用同一套页面坐标关系；先确认关联，再切图。",
            (
                (
                    "01", "插图识别先生成 PPP，再人工修正",
                    "【插图识别】按当前页面范围检测插图并写入 PPP。自动区域使用 AUTO 标签；重复识别只替换旧 AUTO 区域，"
                    "人工绘制的多边形会保留。"
                ),
                (
                    "02", "【编辑插图】负责精修关系",
                    "可新增多边形、拖动现有顶点或矩形边，并修改 PPP 名称。名称与词头一致时会被视为关联插图；"
                    "关联是否正确会直接影响后续词条切图与独立插图导出。"
                ),
                (
                    "03", "先用【切图设置】统一边界",
                    "词条切图和插图切图共用切图上/下边界、外扩和特殊页面覆盖。注意：切图边界和 OCR 的页眉/正文边界是两套独立参数。"
                ),
                (
                    "04", "用“切图预览”检查最终关系",
                    "关联 PPP 完整位于或部分相交于词条范围时，会按当前 Crop Plan 并入词条切图；完全位于词条外部时，"
                    "才单独生成 (P数字) 图片。预览正确后再批量切图。"
                ),
            ),
        ),
        (
            "post",
            "后期制作",
            "这里处理的是已经校对过的项目成果：切图、索引、PicDic、备份与训练数据。",
            (
                (
                    "01", "【词条切图】生成 PWW",
                    "按页面范围读取当前 PDIC、PPP 和切图设置，生成完整词条图片。批量切图可使用 CPU 多进程；"
                    "底部任务条会显示进度，并提供暂停和停止。"
                ),
                (
                    "02", "【插图切图】处理独立插图",
                    "仅对 Crop Plan 判断为独立导出的插图生成图片；与词条关联的插图会按设置并入词条，不重复导出。"
                ),
                (
                    "03", "【PicDic制作】以切图结果为准",
                    "PicDic 制作读取已经生成的完整词条切图及 manifest，并处理跨页连续词条。"
                    "如果切图尚未完成或图片缺失，应先回到切图阶段，而不是直接修改索引。"
                ),
                (
                    "04", "PDIC 备份用于阶段性回退",
                    "在大批量校对、自动填充或规则调整前可先【备份PDIC】。需要恢复时使用【恢复PDIC】，"
                    "恢复范围仍受主界面当前页面范围约束。"
                ),
                (
                    "05", "训练标记包是独立输出",
                    "【导出训练标记包】会收集页面、标记与项目上下文，用于后续模型/规则验证；它不会替代日常 PDIC/PPP 保存。"
                ),
            ),
        ),
        (
            "navigation",
            "导航与排错",
            "先分清“版面不对、OCR 环境不对、候选规则不对、还是个别词条不对”，排错会快很多。",
            (
                (
                    "⌨", "常用鼠标与快捷操作",
                    "主画布：左键加线；Delete / 反引号删除；普通模式右键下一页；滚轮纵向滚动；"
                    "Shift + 滚轮横向滚动；Ctrl + 滚轮缩放。校对窗口中反引号可删除当前行。"
                ),
                (
                    "1", "整页位置都偏：先查版面参数",
                    "如果整页的栏位置、页眉、行距或切线整体偏移，优先重新检测/检查【普通版面参数】和 Project Profile 页面模板，"
                    "不要先调候选置信度。"
                ),
                (
                    "2", "OCR 完全不可用：先检测环境",
                    "点击【环境中心】查看 PaddleOCR / PaddlePaddle、Tesseract、Google Lens、OpenCC 和 CC-CEDICT 状态。"
                    "环境问题应先修复安装或设备配置，再判断识别算法。"
                ),
                (
                    "3", "稳定漏检/误检：再查 OCR 高级设置",
                    "只有当多页重复出现同一种漏检或误检时，才值得进入【设置中心 → OCR画线 → 高级设置】调整结构门槛。"
                    "调整后只在代表页重新验证，不要直接全书重跑。"
                ),
                (
                    "4", "只有少量拼写错：直接校对",
                    "如果画线位置正确，只是个别 OCR 拼写错误，直接在【词条校对】选择候选或人工修改通常更高效，"
                    "没有必要为了几个词重新改变全局参数。"
                ),
                (
                    "5", "设置中心的保存规则",
                    "设置中心会自动保存有效输入；Ctrl+S 用于立即校验并保存，Esc 或关闭窗口也会先校验。"
                    "如果底部提示“当前输入暂未保存”，先修正无效值再关闭。"
                ),
            ),
        ),
    )

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.parent_app = parent
        self.title("Picture Capture · 使用指南")
        screen_w = max(900, self.winfo_screenwidth())
        screen_h = max(650, self.winfo_screenheight())
        work_x, work_y, work_w, work_h = _screen_work_area(self)
        width = min(work_w, 1040, int(screen_w * 0.82))
        height = min(work_h, 780, int(screen_h * 0.86))
        x = work_x + max(0, (work_w - width) // 2)
        y = work_y + max(0, (work_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(820, width), min(600, height))
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())

        self._colors = usage_guide_palette("light")
        self.configure(bg=self._colors["bg"])
        base = font.nametofont("TkDefaultFont").copy()
        self._title_font = base.copy()
        self._title_font.configure(size=max(16, abs(int(base.cget("size"))) + 7), weight="bold")
        self._page_title_font = base.copy()
        self._page_title_font.configure(size=max(14, abs(int(base.cget("size"))) + 5), weight="bold")
        self._card_title_font = base.copy()
        self._card_title_font.configure(size=max(10, abs(int(base.cget("size"))) + 1), weight="bold")
        self._meta_font = base.copy()
        self._meta_font.configure(size=max(8, abs(int(base.cget("size"))) - 1))

        self._page_map = {item[0]: item for item in self.PAGES}
        self._nav_buttons: dict[str, tk.Button] = {}
        self._wrap_labels: list[tk.Label] = []
        self._current_page = "quick"
        self._build()
        self._show_page("quick")
        self._refresh_context()
        self.bind("<FocusIn>", lambda _event: self._refresh_context(), add="+")

    def refresh_appearance(self) -> None:
        """Refresh the guide palette without losing the current page/search."""
        self._colors = usage_guide_palette("light")
        self.configure(bg=self._colors["bg"])
        query = self.search_var.get().strip()
        if query:
            self._search_changed()
        else:
            self._show_page(self._current_page)
        self.parent_app._apply_current_appearance(self)

    def _build(self) -> None:
        colors = self._colors
        shell = tk.Frame(self, bg=colors["bg"])
        shell.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(shell, bg=colors["bg"])
        header.pack(fill="x", pady=(0, 14))
        tk.Label(
            header, text="使用指南", bg=colors["bg"], fg=colors["text"],
            font=self._title_font, anchor="w",
        ).pack(anchor="w")
        tk.Label(
            header,
            text="按真实工作流组织：从 Project Profile、画线和校对，到切图、PicDic 与常见排错。",
            bg=colors["bg"], fg=colors["muted"], anchor="w", justify="left",
        ).pack(anchor="w", pady=(4, 0))
        self._context_var = tk.StringVar()
        tk.Label(
            header, textvariable=self._context_var, bg=colors["bg"], fg=colors["accent"],
            font=self._meta_font, anchor="w",
        ).pack(anchor="w", pady=(7, 0))

        body = tk.Frame(shell, bg=colors["bg"])
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(
            body, bg=colors["sidebar"], width=190,
            highlightthickness=1, highlightbackground=colors["border"],
        )
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        sidebar.grid_propagate(False)

        search_block = tk.Frame(sidebar, bg=colors["sidebar"])
        search_block.pack(fill="x", padx=12, pady=(13, 8))
        tk.Label(
            search_block, text="查找", bg=colors["sidebar"], fg=colors["muted"],
            font=self._meta_font, anchor="w",
        ).pack(anchor="w", pady=(0, 4))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_block, textvariable=self.search_var)
        search_entry.pack(fill="x")
        self.search_var.trace_add("write", lambda *_args: self._search_changed())

        nav = tk.Frame(sidebar, bg=colors["sidebar"])
        nav.pack(fill="x", padx=8, pady=(2, 8))
        for key, title, _subtitle, _cards in self.PAGES:
            button = tk.Button(
                nav, text=title, command=lambda k=key: self._select_page(k),
                anchor="w", relief="flat", bd=0, padx=10, pady=8,
                bg=colors["sidebar"], fg=colors["text"],
                activebackground=colors["accent_soft"], activeforeground=colors["accent"],
                highlightthickness=0, takefocus=False, cursor="hand2",
            )
            # Navigation buttons manage their palette directly because their
            # selected state changes frequently. Skipping the generic reversible
            # classic mapper avoids a light-palette flash on every page switch.
            button._pc_skip_classic_appearance = True
            button.pack(fill="x", pady=1)
            self._nav_buttons[key] = button

        tk.Frame(sidebar, bg=colors["border"], height=1).pack(fill="x", padx=12, pady=(4, 8))
        tk.Label(
            sidebar, text="遇到问题时", bg=colors["sidebar"], fg=colors["muted"],
            font=self._meta_font, anchor="w",
        ).pack(fill="x", padx=14)
        tk.Label(
            sidebar,
            text="先判断是版面、OCR 环境、规则，还是单个词条问题，再进入对应页面。",
            bg=colors["sidebar"], fg=colors["muted"], justify="left", anchor="nw",
            wraplength=158,
        ).pack(fill="x", padx=14, pady=(4, 12))

        content_shell = tk.Frame(
            body, bg=colors["surface"],
            highlightthickness=1, highlightbackground=colors["border"],
        )
        content_shell.grid(row=0, column=1, sticky="nsew")
        content_shell.grid_rowconfigure(0, weight=1)
        content_shell.grid_columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            content_shell, bg=colors["surface"], highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(content_shell, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._content = tk.Frame(self._canvas, bg=colors["surface"])
        self._content_window = self._canvas.create_window(
            (0, 0), window=self._content, anchor="nw",
        )
        self._content.bind(
            "<Configure>",
            lambda _event: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
            add="+",
        )
        self._canvas.bind("<Configure>", self._resize_content, add="+")
        self.bind("<MouseWheel>", self._mousewheel, add="+")
        self.bind("<Button-4>", lambda _event: self._canvas.yview_scroll(-3, "units"), add="+")
        self.bind("<Button-5>", lambda _event: self._canvas.yview_scroll(3, "units"), add="+")

        footer = tk.Frame(shell, bg=colors["bg"])
        footer.pack(fill="x", pady=(12, 0))
        tk.Label(
            footer, text="常用入口", bg=colors["bg"], fg=colors["muted"],
            font=self._meta_font,
        ).pack(side="left")

        def action_button(label: str, command) -> tk.Button:
            button = tk.Button(
                footer, text=label, command=command,
                relief="flat", bd=0, padx=10, pady=5,
                bg="#e8edf3", fg=colors["text"],
                activebackground="#dce4ec", activeforeground=colors["text"],
                cursor="hand2",
            )
            button.pack(side="left", padx=(7, 0))
            return button

        self._profile_button = action_button("项目Profile", self.parent_app.open_project_profile)
        self._layout_button = action_button("检测版面参数", self.parent_app.detect_layout_current)
        action_button("环境中心", self.parent_app.check_ocr_engines)
        action_button("设置中心", self.parent_app.open_settings)
        tk.Button(
            footer, text="关闭", command=self.destroy,
            relief="flat", bd=0, padx=12, pady=5,
            bg=colors["accent"], fg="#ffffff",
            activebackground="#416A94", activeforeground="#ffffff",
            cursor="hand2",
        ).pack(side="right")

    def _refresh_context(self) -> None:
        project = getattr(self.parent_app, "project", None)
        if project is None:
            self._context_var.set("当前：尚未打开项目 · 可先从主界面的【新建项目】或【已有项目】开始")
            state = "disabled"
        else:
            settings = getattr(self.parent_app, "settings", None)
            full_name = str(getattr(settings, "dictionary_full_name", "") or "").strip()
            name = full_name or getattr(project.root, "name", str(project.root))
            total = len(getattr(project, "images", []) or [])
            index = int(getattr(self.parent_app, "current_index", 0) or 0)
            page = f"{index + 1}/{total}" if total else "—"
            self._context_var.set(f"当前项目：{name} · 当前页：{page}")
            state = "normal"
        for button in (self._profile_button, self._layout_button):
            try:
                button.configure(state=state)
            except tk.TclError:
                pass

    def _select_page(self, key: str) -> None:
        self._current_page = key
        if self.search_var.get():
            self.search_var.set("")
        self._show_page(key)

    def _search_changed(self) -> None:
        query = self.search_var.get().strip().casefold()
        if not query:
            self._show_page(self._current_page)
            return
        matches: list[tuple[str, str, str]] = []
        for _key, page_title, page_subtitle, cards in self.PAGES:
            if query in page_title.casefold() or query in page_subtitle.casefold():
                matches.extend((page_title, title, body) for _badge, title, body in cards)
                continue
            for _badge, title, body in cards:
                if query in title.casefold() or query in body.casefold():
                    matches.append((page_title, title, body))
        self._render_search(query, matches)

    def _set_nav_state(self, active: str | None) -> None:
        colors = usage_guide_palette(
            getattr(self.parent_app, "appearance_mode", "light")
        )
        for key, button in self._nav_buttons.items():
            selected = key == active
            button.configure(
                bg=colors["accent_soft"] if selected else colors["sidebar"],
                fg=colors["accent"] if selected else colors["text"],
                activebackground=colors["accent_soft"],
                activeforeground=colors["accent"],
                font=(font.nametofont("TkDefaultFont").actual("family"), 9, "bold" if selected else "normal"),
            )

    def _clear_content(self) -> None:
        for child in self._content.winfo_children():
            child.destroy()
        self._wrap_labels.clear()
        self._canvas.yview_moveto(0.0)

    def _show_page(self, key: str) -> None:
        page = self._page_map.get(key)
        if page is None:
            return
        self._set_nav_state(key)
        self._clear_content()
        _page_key, title, subtitle, cards = page
        self._add_page_heading(title, subtitle)
        if key == "quick":
            self._add_callout(
                "推荐原则",
                "先用代表页证明“版面 + Profile + OCR”组合可靠，再扩大页面范围。"
                "软件的高级设置用于解决稳定重复的问题，不是首次使用时必须逐项填写的清单。",
            )
        for badge, card_title, body in cards:
            self._add_card(badge, card_title, body)
        # Apply before returning to Tk's event loop so newly built guide content
        # is never painted once with the light palette in dark mode.
        self.parent_app._apply_current_appearance(self)

    def _render_search(self, query: str, matches: list[tuple[str, str, str]]) -> None:
        self._set_nav_state(None)
        self._clear_content()
        self._add_page_heading(
            f"搜索：{self.search_var.get().strip()}",
            f"在使用指南中找到 {len(matches)} 条匹配内容。",
        )
        if not matches:
            self._add_callout(
                "没有找到匹配内容",
                "可以尝试更短的关键词，例如“OCR”“校对”“切图”“插图”“PicDic”“缓存”或“版面”。",
            )
            self.parent_app._apply_current_appearance(self)
            return
        for page_title, title, body in matches:
            self._add_card(page_title[:6], title, body)
        self.parent_app._apply_current_appearance(self)

    def _add_page_heading(self, title: str, subtitle: str) -> None:
        colors = self._colors
        holder = tk.Frame(self._content, bg=colors["surface"])
        holder.pack(fill="x", padx=24, pady=(22, 12))
        tk.Label(
            holder, text=title, bg=colors["surface"], fg=colors["text"],
            font=self._page_title_font, anchor="w",
        ).pack(anchor="w")
        label = tk.Label(
            holder, text=subtitle, bg=colors["surface"], fg=colors["muted"],
            anchor="w", justify="left", wraplength=660,
        )
        label.pack(fill="x", pady=(5, 0))
        self._wrap_labels.append(label)

    def _add_callout(self, title: str, body: str) -> None:
        colors = self._colors
        border = tk.Frame(self._content, bg="#cfddeb")
        border.pack(fill="x", padx=24, pady=(0, 12))
        card = tk.Frame(border, bg="#f1f6fb")
        card.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(
            card, text=title, bg="#f1f6fb", fg=colors["accent"],
            font=self._card_title_font, anchor="w",
        ).pack(fill="x", padx=14, pady=(11, 3))
        label = tk.Label(
            card, text=body, bg="#f1f6fb", fg=colors["text"],
            justify="left", anchor="w", wraplength=660,
        )
        label.pack(fill="x", padx=14, pady=(0, 12))
        self._wrap_labels.append(label)

    def _add_card(self, badge: str, title: str, body: str) -> None:
        colors = self._colors
        border = tk.Frame(self._content, bg=colors["border"])
        border.pack(fill="x", padx=24, pady=(0, 10))
        card = tk.Frame(border, bg=colors["surface"])
        card.pack(fill="both", expand=True, padx=1, pady=1)
        card.grid_columnconfigure(1, weight=1)

        badge_label = tk.Label(
            card, text=badge, bg=colors["accent_soft"], fg=colors["accent"],
            font=self._meta_font, padx=7, pady=3,
        )
        badge_label.grid(row=0, column=0, sticky="nw", padx=(14, 10), pady=(13, 0))

        tk.Label(
            card, text=title, bg=colors["surface"], fg=colors["text"],
            font=self._card_title_font, anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(13, 3))

        label = tk.Label(
            card, text=body, bg=colors["surface"], fg=colors["muted"],
            justify="left", anchor="w", wraplength=620,
        )
        label.grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=(0, 13))
        self._wrap_labels.append(label)

    def _resize_content(self, event: tk.Event) -> None:
        width = max(420, int(event.width) - 2)
        self._canvas.itemconfigure(self._content_window, width=width)
        wrap = max(360, width - 105)
        for label in self._wrap_labels:
            try:
                label.configure(wraplength=wrap)
            except tk.TclError:
                pass

    def _mousewheel(self, event: tk.Event) -> str | None:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta:
            self._canvas.yview_scroll((-1 if delta > 0 else 1) * 3, "units")
            return "break"
        return None


class SettingsDialog(tk.Toplevel):
    FIELDS = [
        ("词典完整名称", "dictionary_full_name", str),
        ("词典缩写名称", "dictionary_abbreviation", str),
        ("ISBN", "dictionary_isbn", str),
        ("索引语言", "dictionary_index_language", str),
        ("内容语言", "dictionary_content_language", str),
        ("正文页码范围", "dictionary_body_page_range", str),
        ("自定义 Profile 名称", "dictionary_custom_profile_name", str),
        ("词典分栏", "columns", int), ("两栏中隔", "gutter", int),
        ("单栏宽距", "column_width", int), ("起始点 Y", "start_y", int),
        ("正文结束 Y", "bottom_y", int), ("首栏 X", "manual_x", int),
        ("正文缩进", "body_indent", int), ("单行字高", "character_height", int),
        ("行间空白", "row_padding", int), ("向右比例 %", "right_ratio", float),
        ("微调判距", "horizontal_tolerance", int), ("标记线高", "marker_height", int),
        ("垂直线宽", "guide_width", int), ("黑色阈值 RGB 和", "darkness_threshold", int),
        ("自动保存间隔（秒）", "batch_interval", float),
        ("插图自动识别外扩（px）", "illustration_detect_padding", int),
        ("插图自动识别右侧外扩（px）", "illustration_detect_right_padding", int),
        ("OCR 语言", "ocr_language", str),
        ("Tesseract 语言", "tesseract_language", str),
        ("书写模式", "layout_writing_mode", str),
        ("文字方向", "layout_text_direction", str),
        ("Canonical 变换", "layout_transform", str),
        ("栏数策略", "layout_columns_policy", str),
        ("中央分隔线", "layout_column_separator_mode", str),
        ("分析阈值", "analysis_threshold_mode", str),
        ("列跟踪搜索半径", "column_track_radius", int),
        ("列跟踪分块高度", "column_track_block_height", int),
        ("列跟踪最大步移", "column_track_max_step", int),
        ("PaddleOCR 语言", "paddle_language", str),
        ("PaddleOCR 模型版本", "paddle_ocr_version", str),
        ("OCR图像预处理", "paddle_preprocessing", str),
        ("OCR输入最大长边（px）", "paddle_max_input_side", int),
        ("候选带宽比例（%）", "paddle_band_width_ratio", int),
        ("候选带左侧余量", "paddle_band_left_margin", int),
        ("AI 左缘容差", "paddle_left_tolerance", int),
        ("AI 候选置信度", "paddle_rec_score_threshold", float),
        ("AI 同行合并Y比", "paddle_line_merge_y_ratio", float),
        ("AI 字高比阈值", "paddle_height_ratio", float),
        ("AI 粗体比阈值", "paddle_boldness_ratio", float),
        ("AI 行前空白比", "paddle_gap_ratio", float),
        ("AI 最低候选分", "paddle_min_candidate_score", float),
        ("AI 页眉横线搜索高度", "paddle_header_search_height", int),
        ("AI 页眉横线墨迹比例", "paddle_header_rule_ink_ratio", float),
        ("AI 页眉横线后余量", "paddle_header_rule_margin", int),
        ("AI 词性搜索字符数", "paddle_pos_search_chars", int),
        ("横线Y精修搜索范围（行高比）", "paddle_separator_search_ratio", float),
        ("横线Y精修安全带半径（px）", "paddle_separator_band_radius", int),
        ("横线Y精修安全空间（px）", "paddle_separator_safety_px", int),
        ("横线Y精修横向分析范围（%）", "paddle_separator_roi_width_ratio", int),
        ("横线Y精修栏边余量（px）", "paddle_separator_column_margin", int),
        ("Tesseract 对照 PSM", "paddle_tesseract_psm", int),
        ("Google Lens OCR语言", "paddle_lens_language", str),
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
        ("主界面词框宽度（字符）", "main_entry_width_chars", int),
        ("主界面词框横向位置（栏宽比例）", "main_entry_x_ratio", float),
        ("校对界面字体", "review_entry_font_family", str),
        ("校对界面字号", "review_entry_font_size", int),
        ("校对文本框上下边距（px）", "review_entry_vertical_padding", int),
        ("校对单字行高（0=中文自动2.5×）", "review_single_cjk_line_height", int),
        ("校对默认缩放（%）", "review_zoom_percent", int),
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
            "body_indent", "character_height", "row_padding", "right_ratio",
            "horizontal_tolerance", "darkness_threshold",
        ]),
        ("词条线显示", ["marker_height", "guide_width"]),
        ("主界面词条文本框", [
            "main_entry_font_family", "main_entry_font_size", "main_entry_width_chars", "main_entry_x_ratio",
        ]),
        ("词条校对文本框", [
            "review_entry_font_family", "review_entry_font_size", "review_entry_vertical_padding",
            "review_single_cjk_line_height", "review_zoom_percent",
        ]),
        ("辅助词表", ["wordslist_path"]),
        ("列跟踪", ["column_track_radius", "column_track_block_height", "column_track_max_step"]),
        ("插图识别", ["illustration_detect_padding", "illustration_detect_right_padding"]),
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
            "paddle_tesseract_psm", "paddle_lens_language", "paddle_lens_timeout",
            "paddle_lens_default_confidence", "paddle_alignment_y_tolerance_ratio",
            "paddle_alignment_min_similarity", "paddle_conflict_review_margin",
        ]),
        ("词头识别正则（高级）", ["paddle_headword_regex", "paddle_pos_regex", "paddle_special_symbol_regex"]),
    ]

    CHECK_GROUPS = [
        ("版面行为", [
            ("手动分栏", "manual_columns"),
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
            ("主界面显示 OCR 内容选择", "review_main_show_ocr_choices"),
            ("主界面按 OCR 置信度显示底色", "review_main_show_ocr_background"),
        ]),
    ]

    OCR_LANGUAGES = ("eng", "spa", "fra", "ita", "por", "deu", "chi_sim", "chi_tra", "jpn", "ara")

    # Human-facing setting metadata. Internal field names and persisted JSON stay
    # unchanged; this layer only reorganizes the settings experience.
    SETTING_LABELS = {
        "columns": "正文栏数",
        "start_y": "正文起始 V",
        "bottom_y": "正文结束 V",
        "manual_x": "第一栏左缘 U",
        "column_width": "单栏正文宽度",
        "gutter": "栏间空白",
        "character_height": "典型行高",
        "row_padding": "典型行间空白",
        "ocr_language": "词头 OCR 语言",
        "analysis_threshold_mode": "墨迹判断方式",
        "body_indent": "左缘检测宽度",
        "character_height": "典型单行字高",
        "row_padding": "典型行间空白",
        "darkness_threshold": "固定黑度阈值",
        "horizontal_tolerance": "横向微调容差",
        "paddle_band_width_ratio": "OCR 识别带宽",
        "paddle_left_tolerance": "词头左缘容差",
        "paddle_rec_score_threshold": "OCR 片段最低置信度",
        "paddle_min_candidate_score": "词头候选最低分",
        "paddle_separator_safety_px": "横线与文字安全距离",
        "paddle_line_merge_y_ratio": "同行碎片合并容差",
        "paddle_height_ratio": "字高提示阈值",
        "paddle_boldness_ratio": "粗体提示阈值",
        "paddle_gap_ratio": "行前空白提示阈值",
        "paddle_pos_search_chars": "词性提示搜索范围",
        "paddle_separator_search_ratio": "横线 Y 精修搜索范围",
        "paddle_separator_band_radius": "横线空白带平滑半径",
        "paddle_separator_roi_width_ratio": "横线精修横向范围",
        "paddle_separator_column_margin": "横线精修栏边余量",
        "paddle_max_input_side": "OCR 最大输入边长",
        "paddle_preprocessing": "OCR 图像预处理",
        "paddle_device": "PaddleOCR 运行设备",
        "paddle_ocr_version": "PaddleOCR 模型版本",
        "ocr_executable": "Tesseract 程序路径",
        "batch_interval": "自动保存间隔",
        "wordslist_path": "参考词表文件",
        "dictionary_custom_profile_name": "自定义 Profile 显示名称",
        "detection_method": "默认画线方式",
        "paddle_lens_mode": "Google Lens 运行模式",
        "ocr_engine": "普通文本 OCR 引擎",
        "headword_sort_mode": "词头排序预设",
        "headword_custom_order": "自定义排序单元",
        "headword_custom_fold_accents": "自定义排序重音折叠",
    }

    SETTING_HELP = {
        "columns": "作用：正文栏数，是版面几何、阅读顺序、OCR 候选带和后续切图共同使用的基础参数。若【栏数策略】为自动检测，程序会在版面分析时估计栏数；若为固定，则这里的值是权威值。\n\n调整：栏数设错会让栏左缘、词条归栏、阅读顺序和切图边界整体错位。优先用【检测当前页版面参数】和 Project Profile 的代表页结果确认，不建议为修一个局部页面临时改全项目栏数。",
        "gutter": "作用：相邻正文栏之间的典型空白宽度，保存为参考页规范坐标。它参与栏位置推导、栏间区域判断和部分切图边界计算；并不等同于印刷中央分隔线本身的线宽。\n\n调整：过小会让相邻栏靠得过近，过大则可能把正文有效区域压窄。不同分辨率页面会按参考页坐标自动换算，通常应由版面检测或 Profile 代表页确定。",
        "column_width": "作用：单栏正文的典型宽度，保存为参考页规范坐标。它决定栏几何的水平范围，并间接影响 OCR 候选带、词条矩形和相邻栏边界。\n\n调整：过小可能截掉长词头/释义并让切图偏窄；过大可能侵入栏间空白甚至邻栏。优先使用检测结果，不要用它去补偿单个页面的扫描偏移。",
        "start_y": "作用：正文在参考页 canonical 阅读坐标中的起始 V。横排、identity 页面上通常可直观理解为正文起始 Y；旋转/竖排项目应按 canonical V 理解，而不是原图 Y。\n\n生效：运行时会按当前页尺寸换算；若 Project Profile 明确设置页眉模式/页眉比例，页面模板得到的有效正文上界可覆盖这个基础值。它影响画线/OCR 的正文范围，不是【切图设置】里的最终切图上边界。",
        "bottom_y": "作用：正文在参考页 canonical 阅读坐标中的结束 V，用来限制版面分析和词头识别的有效正文区。横排时通常近似原图 Y，旋转/竖排时仍应按 canonical V 理解。\n\n调整：过小会漏掉页尾词条，过大可能把页码/脚注吸入正文。若 Project Profile 明确设置页尾模板，则有效页面下界可由模板覆盖；它也不是最终切图的下边界设置。",
        "manual_x": "作用：第一栏左缘在参考页 canonical 坐标中的 U 位置。其余栏位置会结合栏宽、栏间距、方向/变换等推导。\n\n注意：镜像、RTL、竖排或旋转项目中，U 是规范阅读坐标，不应直接把它理解为原图左上角系的 X。只有确认自动版面检测不能稳定定位栏左缘时才手动修改。",
        "body_indent": "作用：主要服务【普通画线（备用）】的栏左墨迹搜索，表示从栏左缘向正文内部允许检查的宽度。它也会参与列跟踪搜索区的右侧范围。\n\n调整：太小会漏掉缩进词头；太大则更容易把释义正文开头当成词头。OCR画线主要依赖文字/结构证据，本项不是其首要调节项。",
        "character_height": "作用：项目的典型单行字高（参考页规范坐标）。普通画线用它估计行尺度；OCR画线的行距/空白判断、横线 Y 精修和部分 CJK 视觉逻辑也会以它作为尺度基准。\n\n调整：应接近正文常规印刷行高，而不是某个特别大的词头字高。设得明显过大/过小会让行间关系、精修搜索尺度和部分切图高度失真。",
        "row_padding": "作用：典型行周围的额外留白尺度。它参与普通画线行盒、词条单行框高度以及 OCR 词头前空白/分隔位置等计算。\n\n调整：增大可给文字上下更多安全空间，但过大会让相邻行更容易重叠/合并；过小则可能让横线或单行切图贴字过紧。应和【典型行高】一起校准。",
        "right_ratio": "作用：词条单行矩形向右覆盖当前栏宽的百分比；当前实现会限制在 1%–100%。它主要影响词条矩形/单行切图的水平覆盖，不决定 OCR 是否把某行识别为词头。\n\n调整：减小可避免把过多释义或邻近内容纳入单行框；增大可保留更完整的同行上下文。它属于历史兼容参数，目前不在设置中心常用分组中，最终导出范围仍应以【切图设置】为准。",
        "horizontal_tolerance": "兼容状态：该字段仍随项目保存并参与旧坐标迁移，但当前 v2.13.3 的普通画线/OCR画线主算法没有读取它来做实际判定。\n\n因此：修改这里通常不会改变当前识别结果。保留它主要是为了旧项目兼容和配置格式稳定；若需要修正栏左偏移，应优先调整版面几何、列跟踪或 OCR 左缘容差，而不是依赖此项。",
        "analysis_threshold_mode": "作用：决定【普通画线（备用）】如何把页面灰度转换成“墨迹/背景”。auto 等同推荐的全页 Otsu；adaptive 适合底色、阴影或书脊亮度不均；fixed 使用固定 RGB 和阈值，主要用于旧项目或可控扫描。\n\n选择：普通扫描先用 auto/Otsu；只有明显局部底色不均时再试 adaptive。该项主要影响图像墨迹分析，不会改变 PaddleOCR 的文字模型。",
        "darkness_threshold": "作用：仅在【分析阈值 = fixed】时作为固定黑度阈值使用，以 RGB 三通道和判断像素是否属于墨迹。auto/Otsu/adaptive 模式下它基本不参与当前判定。\n\n调整：阈值提高会让更浅的灰字/污点也被当作墨迹，召回可能增加但噪声也增加；阈值降低则更严格，可能漏掉浅色印刷。除旧项目外通常无需手调。",
        "column_track_radius": "作用：开启【跟随栏左缘倾斜/弯曲】后，每个纵向分块允许在名义栏左缘附近向左右搜索真实墨迹边缘的半径，使用参考页规范坐标。\n\n调整：过小跟不上明显弯曲/斜拍；过大可能把搜索吸到正文内部或邻栏。平直扫描通常无需增加，先确认确实存在几何形变再改。",
        "column_track_block_height": "作用：开启列跟踪后，沿阅读轴把页面切成多高的块来重新估计栏左缘。块越小，路径能更细地跟随局部弯曲；块越大，路径更平滑稳定。\n\n调整：太小容易受单个粗字、插图、污点影响；太大则跟不上快速变化的书脊弯曲。应与搜索半径、最大步移一起理解。",
        "column_track_max_step": "作用：限制相邻列跟踪锚点之间允许的最大水平跳变，避免某个分块突然追到正文或邻栏。\n\n调整：过小会把真实的快速弯曲强行拉直；过大则失去防跳栏作用。仅在已开启列跟踪且诊断显示路径被过度限制/突然跳变时调整。",
        "ocr_language": "作用：项目的主要词头/OCR语言，是多个组件的上层语义入口：用于选择/映射 PaddleOCR 与 Tesseract 语言、Dictionary Profile 默认结构、排序预设以及部分 CJK/拉丁解析路径。\n\n调整：应填写词头语言而不是释义语言。改变后可能导致 OCR 模型、Profile 和排序语义变化，已有 OCR 缓存/结果不应默认视为仍可比较，稳定项目中不要频繁切换。",
        "paddle_device": "兼容字段：旧项目中的 CPU/GPU 值继续读取，但运行时设备现在由本机环境自动决定，不再作为可迁移的项目参数。高级用户可用 PICTURE_CAPTURE_PADDLE_DEVICE=cpu/gpu 临时强制本机设备。",
        "paddle_preprocessing": "作用：决定送入 PaddleOCR 前的图像预处理。original 保留原图；grayscale 转灰度；auto_contrast 拉伸对比度；binary 强制二值化。\n\n选择：默认优先 original，因为 OCR 模型通常能利用原始灰度/颜色信息。只有扫描发灰、底色不均或模型确有改善证据时再改；过度二值化可能损失细笔画和重音符号。",
        "paddle_max_input_side": "作用：限制送入 PaddleOCR 的图像最大长边，超出时按比例缩小。它主要平衡小字细节、推理速度、内存/显存和模型稳定性。\n\n调整：增大可保留更多细节，但会更慢、更占显存；减小更省资源但可能让小字号/附加符号变糊。改变此项会改变 OCR 输入图像，应视为可能需要重新 OCR，而不仅是重新评分候选。",
        "paddle_band_width_ratio": "作用：每栏左侧有多少百分比宽度进入 OCR 候选带。程序不是把整栏全文都送去做词头判断，而是优先截取栏左区域以减少正文干扰。\n\n调整：太小会截断长词头、性别变体或紧随其后的 POS；太大则会引入更多释义正文、增加耗时和误候选。先以“能完整覆盖词头 + 近邻语法标签”为目标。",
        "paddle_band_left_margin": "作用：在 OCR 候选带左侧额外向外扩出的参考像素（以 canonical 1400 宽基准缩放），用于保留略越出估计栏左缘、装饰符号或列跟踪误差附近的文字。\n\n调整：增加可救回被左边界裁切的词头；过大则会纳入页边线、污点或上一栏区域。它改变 OCR 输入带几何，必要时会导致 OCR 缓存失效。",
        "paddle_left_tolerance": "作用：词头候选允许偏离估计栏左缘的最大程度（固定 1400 canonical 宽下的参考像素，运行时按页尺度换算）。这是“候选位置是否仍算栏左”的关键阈值。\n\n调整：增大可容纳缩进词头，但也更容易把正文缩进行吸进候选；减小更严格，但可能漏掉真实缩进或版面轻微漂移。优先结合候选诊断里的 X/归栏信息判断。",
        "paddle_rec_score_threshold": "作用：在 OCR 碎片完成必要的同行/结构修复后，按识别置信度过滤低质量 OCR 行。低于阈值的行不会继续进入词头候选评分。\n\n调整：降低可提高召回、救回难字/粗体/重音符号，但会带入更多噪声；提高则更干净但更容易漏词。它和【词头候选最低分】不同：前者是 OCR 文字质量门槛，后者是综合结构评分门槛。",
        "paddle_line_merge_y_ratio": "作用：将同一印刷行被 OCR 拆成多个 box 时，允许多大的垂直差仍合并为一行。词头、性别变体和 POS 经常被模型拆成多个片段，因此这一步发生在后续语法解析之前。\n\n调整：增大可合并错开的碎片，但过大会把上下两行粘在一起；减小可避免串行，却可能让词头与 POS 分离。出现“同一行被拆开/上下行被合并”时才针对性调整。",
        "paddle_height_ratio": "作用：把候选行字高与页面候选行中位字高比较；达到该比例后获得“较大字”视觉提示并增加候选分。它是辅助证据，不是独立接受条件。\n\n调整：提高会让“字大”证据更难触发；降低会让更多正文也被视为大字。仅当词头确实通过字号区别于正文时才值得调，结构证据通常比字号更可靠。",
        "paddle_boldness_ratio": "作用：比较候选行前部墨迹密度与页面局部基准，达到该比例后获得“粗体/更黑”视觉提示并增加候选分。正文中的标签也可能粗体，所以它不是最强证据。\n\n调整：提高更严格、误触发少；降低更敏感，但扫描阴影/对比度变化会带来假粗体。应结合诊断中的 boldness_ratio，而不是仅凭肉眼猜测。",
        "paddle_gap_ratio": "作用：以“典型行高 + 行间空白”为尺度，判断当前候选前方是否存在足够大的纵向空白；满足时作为词条起始的弱视觉证据加分。\n\n调整：提高意味着需要更大的前置空白才算 separated；降低会让较小行距也触发该证据。它只贡献较弱分值，不应拿它替代 POS/变形等结构证据。",
        "paddle_min_candidate_score": "作用：候选在完成 lemma 解析、栏左位置、POS/变形/描述符、特殊符号、字高、粗体和行前空白等加权后，必须达到的综合最低分。\n\n调整：提高会减少误检但增加漏检；降低会提高召回但放入更多边缘候选。不要在不知道 reject_reason/score 构成时盲目下调；优先看 diagnostics 是缺结构、位置不对还是单纯分数不足。",
        "paddle_header_search_height": "作用：自动页眉横线检测只在页面顶部这段高度内搜索；单位是固定 1400 canonical 宽下的参考像素。超出范围的横线不会被当作页眉规则线。\n\n调整：页眉线较低时可增大；太大可能把正文中的表格线/装饰线误当页眉。若项目由 Profile 明确给出页眉模板，优先使用模板语义。",
        "paddle_header_rule_ink_ratio": "作用：在页眉搜索区逐行计算黑色墨迹占比，达到该比例的行才有资格被视为贯穿式页眉横线。当前实现会把输入限制在合理范围后使用。\n\n调整：提高更严格，需要更长/更实的横线；降低可识别断裂或浅色横线，但也更容易把文字行误判为横线。只有【自动忽略页眉横线以上】开启时才有意义。",
        "paddle_header_rule_margin": "作用：识别到页眉横线后，再向正文方向额外留出的安全距离，避免横线本身及其附近文字进入候选区；按 1400 canonical 宽参考像素缩放。\n\n调整：增大可避免页眉残留，但可能吃掉第一条正文词头；减小则更贴近横线。第一条词头被漏掉时应同时检查页眉线位置和这个余量。",
        "paddle_pos_search_chars": "作用：lemma 提取后，语法解析在其后的多长文本范围内寻找 POS/变形等结构提示。这样可利用近邻语法标签，同时避免把很后面的释义正文缩写误当词头证据。\n\n调整：长词头、长性别变体或 POS 距离较远时可适当增大；过大可能在定义正文里误命中缩写。存在活动 Dictionary Profile 时，POS 标签集合通常由 Profile 的 pos_labels 决定。",
        "paddle_separator_search_ratio": "作用：OCR 粗定位词头 Y 后，以典型行高为尺度，在其附近上下搜索更合理的空白带/分隔位置，从而把横线从文字框位置精修到视觉上的行间空白。\n\n调整：增大搜索更宽，能修正较大的 OCR Y 偏差，但更可能跳到相邻行；减小更保守。只有【自动精修横线 Y】开启时才直接影响结果。",
        "paddle_separator_band_radius": "作用：横线 Y 精修时，对局部墨迹/空白曲线做平滑的半径（1400 canonical 宽参考像素）。目的是降低单个字符笔画、噪点造成的尖锐波动。\n\n调整：增大更平滑但可能抹掉窄空白带；减小更敏感但更受噪声影响。一般不应单独调，除非诊断显示精修曲线过躁或过度平滑。",
        "paddle_separator_safety_px": "作用：横线精修后与当前词头墨迹之间保留的额外安全距离（1400 canonical 宽参考像素），防止横线压到字符。\n\n调整：文字被线贴住/穿过时增大；横线与词头间距明显过大时减小。它改变最终显示/词条边界位置，不改变 OCR 文本本身。",
        "paddle_separator_roi_width_ratio": "作用：横线 Y 精修时，只分析当前栏左侧一定百分比的横向区域，而不是整栏释义。这样可减少右侧长定义、插图或其他墨迹干扰。\n\n调整：减小更聚焦词头附近；太小可能只看到少量字符而不稳定。增大提供更多墨迹统计，但正文干扰也增加。",
        "paddle_separator_column_margin": "作用：横线精修分析时，从栏最左边缘跳过一小段区域，避免栏边线、装订阴影、竖直装饰线被误当作文字墨迹。\n\n调整：存在明显栏线/黑边时可增大；过大会跳过真正贴边的词头。单位按 1400 canonical 宽参考像素换算。",
        "paddle_tesseract_psm": "作用：Tesseract 对照 OCR 的 Page Segmentation Mode。当前词头候选带常见 PSM 6（单一均匀文本块）与 PSM 4（单栏但行/字号更灵活）；若开启【自动比较 PSM 4/6】，程序会自行比较，不必手动固定。\n\n调整：只有 Tesseract 对照结果明显分行错误且自动比较关闭时才改。它不影响 PaddleOCR。",
        "paddle_lens_language": "作用：发送给 Google Lens OCR 的语言提示，用于第三意见路径；只有 Lens 已启用且实际被调用时才生效。它不是项目的主 OCR 语言，也不会修改 Paddle/Tesseract 设置。\n\n调整：填写与词头文字最接近的语言提示。若 Lens 仅作诊断，修改它不会改变本地 OCR。",
        "paddle_lens_timeout": "作用：一次 Google Lens 网络 OCR 最长等待时间。超时后该次 Lens 结果会失败/缺失，但本地 Paddle/Tesseract 流程仍可继续。\n\n调整：网络慢而频繁超时时可增大；过大则在服务不可达时等待更久。Lens 是可选网络依赖，不建议用超长超时掩盖网络配置问题。",
        "paddle_lens_default_confidence": "作用：Lens 没有提供可直接比较的真实置信度时，给它一个用于多 OCR 质量比较的默认值。这个数会影响 Lens 在可投票模式下的相对权重。\n\n调整：提高会让无置信度 Lens 结果更容易与本地 OCR 竞争；降低则更保守。除非已系统评估 Lens 在本项目上的可靠性，否则保持默认。",
        "paddle_alignment_y_tolerance_ratio": "作用：Paddle 与 Tesseract/Lens 候选做跨引擎配对时，允许它们在 canonical 阅读轴 V 上相差多少个典型行高。只有位置足够接近的候选才可能被认为是同一词头。\n\n调整：增大可配对 Y 偏差较大的结果，但可能把相邻两条词头错配；减小更严格但会增加“各自独立候选”。",
        "paddle_alignment_min_similarity": "作用：跨 OCR 候选除位置外，lemma 文本相似度还需达到该最低值才优先视为同一候选。它帮助避免 Y 相近但实际上是不同词头的错误合并。\n\n调整：提高更严格、错配少但 OCR 字符误差较大时难配对；降低能容忍更多识别差异但可能错误合并。应结合 comparison/fusion 报告调。",
        "paddle_conflict_review_margin": "作用：当多个 OCR 给出的质量分接近时，用这个“质量差阈值”决定是否把结果标成需要人工复核。当前逻辑中，质量差小于该值更容易进入 review。\n\n调整：增大意味着更多近似甚至中等差异的冲突进入人工复核；减小则只有非常接近的结果才提示 review。它影响复核负担，不是 OCR 字符识别阈值。",
        "paddle_headword_regex": "作用：从每个合并后的 OCR 候选行开头提取 lemma（词头文字）。匹配成功后，若正则含捕获组，程序取第 1 个捕获组作为原始词头；它只是“词头像不像一个合法字符串”这一关，最终是否接受仍会结合栏左位置、词性/变形/符号、视觉分数和 Profile 规则。\n\n默认：允许行首空格及可选的 • ◆ ◇ ► ▶ * † ‡ § ¶；允许前/后置连字符、Unicode 字母、音节分隔点 · • ∙ ‧，并容忍 OCR 把分隔点识成 . : + -；也允许撇号连接。例如“• a·ga·rrón s. m.”提取 a·ga·rrón，“anti- adj.”提取 anti-。\n\n修改：第 1 捕获组应只包住 lemma。写得过宽会把逗号、POS/正文吞入词头；过窄会在后续评分前直接漏词。默认 Latin Profile 还会把通用 Unicode 字母范围收窄为拉丁字母；项目特例优先用 Profile 或过滤规则。",
        "paddle_pos_regex": "作用：识别 lemma 后面的 POS/语法标签，作为“这一行确实是词条起始行”的强结构证据；它不负责提取 lemma，搜索范围还受【AI 词性搜索字符数】限制。\n\n默认兼容：可覆盖 s.、s. m./f./amb./pl.、adj./adj. inv.、adv.、v./y.、v. prnl.、prep.、conj.、pron. 子类、det.、interj.、art.、num.、loc.、superlat. 等；y. 是容忍 OCR 把 v. 识成 y.。\n\n重要：主程序加载活动 Dictionary Profile 时，实际 POS 正则由 Profile 的 pos_labels 动态生成，本字段主要是兼容/低层 fallback。当前项目要增删词性缩写应优先改 Profile grammar。",
        "paddle_special_symbol_regex": "作用：判断 OCR 行首是否出现“可作为新词条起始证据”的项目符号。命中只增加一项结构证据，不会无条件把该行接受为词头。\n\n默认只在行首（允许前导空格）识别 • ◆ ◇ ► ▶ * † ‡ § ¶。正文中间出现同样符号不会命中。\n\n修改：只加入真正表示新词条/新条目起始的符号。词条内部释义标记、交叉引用或文章结构符号应交给 Dictionary Profile；例如某些词典中的 ■、□、||、~、→ 属于内部结构，不应因此触发新 lemma。",
        "ocr_executable": "兼容字段：旧项目中的 Tesseract 路径仍会作为发现提示读取，但新的可执行程序选择保存为本机 runtime 设置，不再随项目迁移。请在【环境中心】中选择或重新检测 Tesseract。",
        "paddle_ocr_version": "作用：选择 PaddleOCR 使用的模型系列/版本。不同模型可能改变文字框、识别字符、速度和缓存签名，因此它属于后端级设置而不是单纯阈值。\n\n调整：项目一旦稳定不建议频繁切换。更换模型后应重新生成 OCR，而不是继续沿用旧缓存来比较候选规则。",
        "tesseract_language": "作用：Tesseract 使用的语言包代码，可与项目 OCR 语言不同但通常应对应词头语言。它用于普通文本 OCR和 Tesseract 对照/补漏路径。\n\n调整：若语言包未安装，Tesseract 会不可用或报错；多语言可按 Tesseract 语法组合。仅使用 PaddleOCR 时不会因为这个值改变 Paddle 结果。",
        "batch_interval": "作用：自动保存/批量相关状态写盘的节流间隔，用来避免每次微小编辑都立即写文件。它影响保存频率，不是 OCR 批量任务“每隔几秒处理一页”的间隔。\n\n调整：过短增加磁盘写入和界面抖动风险；过长则异常退出时可能丢失更多最近改动。通常保持数秒级即可。",
        "marker_height": "作用：主界面词头横线的显示线宽/可视厚度，绘制时会按当前界面缩放和旧项目兼容比例调整。它影响视觉与点击辨识，不改变词头 Y 坐标或 OCR 判定。\n\n调整：高 DPI/高缩放下看不清可适当增大；过粗会遮挡文字。属于纯显示参数。",
        "guide_width": "作用：主界面栏左参考线/列路径的显示宽度。只控制视觉叠加层，不改变列跟踪、栏位置或切图数据。\n\n调整：为了在高分辨率屏幕上更易观察可增大；如果参考线遮挡正文则减小。识别结果不应随它变化。",
        "main_entry_font_family": "作用：主界面可编辑词条文本框与部分预览标签使用的字体族。只改变显示/编辑体验，不修改 PDIC 文本、OCR 结果或排序。\n\n选择：优先使用能完整覆盖项目字符集的字体；若出现方框/缺字，应换字体而不是修改 OCR。",
        "main_entry_font_size": "作用：主界面词条编辑框在 100% 视图下的基础字号；实际显示会结合当前视图缩放。只影响界面文字大小，不改变图像坐标、词条线或切图。\n\n调整：增大便于校对但会占更多画布空间；过小影响阅读。它与图片缩放是两套独立概念。",
        "main_entry_width_chars": "作用：主界面词条编辑控件的目标宽度，以字符数估算；横排时主要控制 Entry 宽度，竖排模式则用于窄 Text 控件的可见长度/高度语义。\n\n调整：长词头经常看不全可增大；过大会遮挡原图。只影响编辑控件，不改变词条内容。",
        "main_entry_x_ratio": "作用：主界面词条编辑框相对当前栏宽的横向放置比例，用来把文本框挪到更不遮挡原图的位置。位置换算会考虑 layout transform/RTL。\n\n调整：只改变 GUI 叠加位置；不会修改 entry.x/PDIC 坐标或识别结果。不同版式遮挡严重时再调。",
        "review_entry_font_family": "作用：校对窗口中“原词条”编辑框使用的字体，与主界面字体和简体伴随列字体相互独立。只影响显示和字符宽度测量。\n\n选择：应完整覆盖重音字母/CJK/特殊符号；字体变化可能改变编辑框按裁图宽度换算出的可见字符数，但不会修改保存文字。",
        "review_entry_font_size": "作用：校对窗口原词条编辑框固定字号；校对图片缩放不会自动把这个字号一起放大/缩小。这样可独立控制图片细节和文字编辑可读性。\n\n调整：增大便于阅读，但同一宽度能显示的字符数减少；减小反之。只影响界面。",
        "review_entry_vertical_padding": "作用：校对文本框内部上下对称留白（像素），主要用于避免重音、上标/下延部或特殊字体被单行 Entry 裁切。\n\n调整：字符顶/底被切时增大；过大会让每行校对控件显得过高。它不改变行高模型、图片裁图或 PDIC。",
        "review_single_cjk_line_height": "作用：校对窗口针对中文单字词条使用的特殊裁图行高。0 表示自动按项目典型行高的约 2.5 倍计算；非 0 时使用显式参考页规范高度。\n\n调整：单字大字头被上下裁掉时增大；留白过多时减小。只影响校对裁图展示，不改变词头检测位置。",
        "review_zoom_percent": "作用：校对窗口打开时词条切图片的默认缩放比例。它只改变图片显示尺寸；校对文本字体大小由独立字体设置控制。\n\n调整：高分辨率扫描可适当降低以一次看更多行，小字难辨可提高。不会改变实际切图文件或坐标。",
        "wordslist_path": "作用：指定参考 wordslist.txt，用于主界面/校对界面的“是否已在词表中”、定位和新旧比较等辅助判断。程序使用成员索引，不要求把整份大词表一次渲染到 GUI。\n\n路径：项目内文件优先保存相对路径便于迁移；项目外文件使用绝对路径。它是校对参考源，不会反向修改 OCR 识别结果。",
        "illustration_detect_padding": "作用：自动插图检测得到初始 PPP 轮廓/边界后，四周统一额外扩出的参考页规范像素，用于避免图像主体贴边被裁掉。\n\n调整：插图边缘经常缺失可增大；过大会吞入正文。它只影响自动生成的初始插图区域，之后人工编辑的 PPP 仍是最终依据。",
        "illustration_detect_right_padding": "作用：在通用插图外扩之外，右侧再额外扩展的参考页规范像素。用于某些词典插图常向栏间或右侧空白延伸的版式。\n\n调整：只在右侧经常被截时增加；过大会把邻近文字纳入插图。它不会修改已经人工确认过的 PPP 顶点，除非重新运行自动检测生成新的初始结果。",
        "dictionary_full_name": "作用：当前词典的完整名称，属于项目元数据，用于项目详情、后期词典制作和导出信息。不会改变 OCR、画线或排序算法。\n\n填写：建议使用正式书名而不是本地文件夹名；后续打包/共享项目时更容易识别来源。",
        "dictionary_abbreviation": "作用：词典缩写/短名，供 PicDic、导出命名或项目元数据使用。它不参与识别。\n\n填写：应稳定、简短且避免频繁变化；如果下游格式使用它作为标识，修改后需注意旧导出物与新导出物的一致性。",
        "dictionary_isbn": "作用：可选的 ISBN 项目资料，用于来源记录和后期词典元数据，不参与任何 OCR/版面判断。\n\n填写：没有 ISBN 或版本不确定时可留空；不要为了通过设置校验填伪值。",
        "dictionary_index_language": "作用：词头/索引语言的 ISO 639-1 两位代码，用于后期词典元数据、索引/排序语义等项目层信息。首次可根据 OCR 语言自动建议，但之后用户选择应被保留。\n\n注意：它描述“索引词是什么语言”，不等同于释义内容语言，也不直接替代 OCR 引擎自己的语言代码。",
        "dictionary_content_language": "作用：释义/正文内容语言的 ISO 639-1 两位代码，用于后期词典元数据。双语词典中它通常和索引语言不同。\n\n注意：它不负责选择 OCR 模型，也不会改变词头排序；请按词典内容语义填写。",
        "dictionary_body_page_range": "作用：记录词典正文的页码范围，例如 1-1250。Project Profile 选择代表页、批量工作流或后续制作步骤可据此区分正文与前后附页。\n\n填写：使用逻辑正文页范围，而不是操作系统文件序号；范围错误可能让代表页/批量流程包含封面、索引或附录。",
        "dictionary_custom_profile_name": "作用：仅给当前项目的“自定义结构”Profile 一个更易读的显示名称；底层 Profile key 仍保持 custom，解析器和持久化身份不会因此改变。\n\n适用：当你为某本特殊词典建立了自定义结构时，可用书名/版式名标记。它不是新建一个新的内置 Profile，也不会自动改变任何识别规则。",
        "layout_writing_mode": "作用：定义页面文字的书写轴，例如横排 horizontal-tb 或竖排。它决定 canonical 阅读坐标如何解释，并影响栏排序、阅读轴和若干几何转换。\n\n修改：应由 Project Profile 根据真实版式确定。错误设置会造成坐标轴、阅读顺序、OCR 配对和切图语义整体错误，不应作为局部识别率微调项。",
        "layout_text_direction": "作用：定义同一书写模式下的阅读方向，例如横排 LTR/RTL。它影响 canonical 栏顺序、阅读顺序和某些界面/导出排序，而不是把图片像素简单翻转。\n\n修改：应与词典实际阅读方向一致；阿拉伯/希伯来等 RTL 项目尤其重要。通常由 Project Profile 管理。",
        "layout_transform": "作用：把原始扫描页面映射到内部 canonical 阅读坐标的变换，例如 identity、mirror_x、rotate_ccw90/rotate_cw90。它是坐标契约的一部分。\n\n修改：一般由书写模式/方向自动推导，不建议手动试错。错误 transform 会让 source X/Y 与 canonical U/V 对应关系整体错位，属于高风险专家项。",
        "layout_columns_policy": "作用：决定栏数是由版面检测自动估计（detect）还是固定使用项目设置值（fixed）。\n\n选择：不同页面栏数稳定且检测容易受插图/空白干扰时可固定；版式可能变化或希望按实际页面估计时用 detect。fixed 下【正文栏数】尤为关键。",
        "layout_column_separator_mode": "作用：告诉版面检测中央/栏间是否存在明显分隔线：auto 自动判断，present 明确存在，absent 明确没有。该信息会改变栏边搜索区域和分隔线检测策略。\n\n选择：有稳定印刷竖线时 present 可减少歧义；明确无竖线时 absent 避免程序为不存在的线留搜索空间；不确定保持 auto。",
        "paddle_language": "作用：PaddleOCR 后端使用的语言/模型代码。通常由上层【OCR 语言】映射得到，属于后端专家覆盖项。\n\n修改：只有默认映射不适合当前模型或在调试 PaddleOCR 后端时才手动指定。与项目主语言不一致可能显著降低识别率，并可能改变 OCR 缓存签名。",
        "detection_method": "作用：设置主界面默认使用哪条“画线”路径。OCR画线（推荐）综合文字、栏左位置、词性/变形/符号和视觉证据；普通画线（备用）只依赖几何与墨迹。\n\n选择：大多数词典优先 OCR画线；只有左缘极稳定、无需文字结构或 OCR 环境不可用时再用普通画线。它决定默认操作路径，不会删除另一种模式。",
        "paddle_lens_mode": "作用：控制 Lens 在启用后的调用范围和是否参与融合。off 不调用；diagnostic 可全量获取但 Lens 不投票；conflict 只在 Paddle/Tesseract 冲突或缺失时调用；full 可对更多候选调用并影响非冲突决策。\n\n选择：推荐 conflict，能把网络调用集中在真正有价值的疑难项。full 最耗网络且会让 Lens 对更多最终结果产生影响。",
        "ocr_engine": "作用：这是“已有词条线后再识别整行文本”的普通 OCR 引擎设置，与 OCR画线的多引擎词头检测不是同一件事。\n\n选择：Tesseract/PaddleOCR 只影响普通文本填充路径；不要因为这里选了 Tesseract 就以为 OCR画线也只使用 Tesseract，后者由 OCR画线页的独立开关控制。",
        "headword_sort_mode": "作用：决定校对/索引检查采用的词头排序规则。可随 OCR 语言提供语言专用预设，也可使用通用 Unicode 或自定义字母表。\n\n注意：排序只改变比较/显示顺序和索引语义，不会改变扫描页面物理顺序、PDIC 坐标或 OCR 文字。",
        "headword_custom_order": "作用：当排序预设选择“自定义”时，这里定义词典自己的排序单元，空格分隔；允许 ch、ll、dz 等多字符单元。\n\n填写：顺序就是排序优先级。遗漏的字符会按后备规则处理，因此应覆盖该词典真正需要特殊排序的字母/多字符单元，而不是照抄无关语言字母表。",
        "headword_custom_fold_accents": "作用：仅在自定义排序中使用。开启后，没有在自定义顺序里单独列出的重音字母会按其基础字母折叠排序；关闭则保留它们的独立字符差异。\n\n选择：如果词典把 á/é/ñ 等视作独立排序单位，应显式列入自定义顺序或关闭折叠；若只把重音视作基本字母变体则可开启。",
    }

    COMMON_FIELDS = (
        "columns", "start_y", "bottom_y", "manual_x", "column_width", "gutter",
        "character_height", "row_padding", "ocr_language",
    )
    NORMAL_COMMON_FIELDS = (
        "analysis_threshold_mode", "body_indent", "character_height", "row_padding",
    )
    NORMAL_ADVANCED_FIELDS = (
        "darkness_threshold", "horizontal_tolerance",
        "column_track_radius", "column_track_block_height", "column_track_max_step",
    )
    OCR_COMMON_FIELDS = (
        "ocr_language", "paddle_preprocessing",
        "paddle_band_width_ratio", "paddle_left_tolerance",
        "paddle_separator_safety_px",
    )
    OCR_ADVANCED_FIELDS = (
        "paddle_max_input_side", "paddle_band_left_margin",
        "paddle_rec_score_threshold", "paddle_line_merge_y_ratio",
        "paddle_height_ratio", "paddle_boldness_ratio", "paddle_gap_ratio",
        "paddle_min_candidate_score", "paddle_header_search_height",
        "paddle_header_rule_ink_ratio", "paddle_header_rule_margin",
        "paddle_pos_search_chars", "paddle_separator_search_ratio",
        "paddle_separator_band_radius", "paddle_separator_roi_width_ratio",
        "paddle_separator_column_margin", "paddle_tesseract_psm",
        "paddle_alignment_y_tolerance_ratio", "paddle_alignment_min_similarity",
        "paddle_conflict_review_margin",
    )
    DISPLAY_FIELDS = (
        "marker_height", "guide_width",
        "main_entry_font_family", "main_entry_font_size",
        "main_entry_width_chars", "main_entry_x_ratio",
        "review_entry_font_family", "review_entry_font_size",
        "review_entry_vertical_padding", "review_single_cjk_line_height",
        "review_zoom_percent", "wordslist_path",
    )
    PROJECT_RUNTIME_FIELDS = (
        "batch_interval", "tesseract_language",
        "paddle_ocr_version", "paddle_max_input_side",
        "illustration_detect_padding", "illustration_detect_right_padding",
    )
    EXPERT_FIELDS = (
        "layout_writing_mode", "layout_text_direction", "layout_transform",
        "layout_columns_policy", "layout_column_separator_mode",
        "paddle_language", "paddle_lens_language", "paddle_lens_timeout",
        "paddle_lens_default_confidence",
        "paddle_headword_regex", "paddle_pos_regex", "paddle_special_symbol_regex",
    )

    SETTING_UNITS = {
        "columns": "栏",
        "start_y": "参考页规范px", "bottom_y": "参考页规范px", "manual_x": "参考页规范px",
        "column_width": "参考页规范px", "gutter": "参考页规范px", "body_indent": "参考页规范px",
        "character_height": "参考页规范px", "row_padding": "参考页规范px", "horizontal_tolerance": "参考页规范px",
        "darkness_threshold": "RGB 和", "column_track_radius": "参考页规范px",
        "column_track_block_height": "参考页规范px", "column_track_max_step": "参考页规范px",
        "paddle_band_width_ratio": "%", "paddle_band_left_margin": "参考px@1400",
        "paddle_left_tolerance": "参考页规范px", "paddle_max_input_side": "px",
        "paddle_separator_safety_px": "参考页规范px", "paddle_separator_band_radius": "参考px@1400",
        "paddle_separator_roi_width_ratio": "%", "paddle_separator_column_margin": "参考px@1400",
        "paddle_header_search_height": "参考px@1400", "paddle_header_rule_margin": "参考px@1400",
        "batch_interval": "秒", "illustration_detect_padding": "参考页规范px",
        "illustration_detect_right_padding": "参考页规范px", "main_entry_font_size": "pt",
        "review_entry_font_size": "pt", "review_entry_vertical_padding": "px",
        "review_single_cjk_line_height": "参考页规范px", "review_zoom_percent": "%",
    }
    SETTING_SPIN = {
        "columns": (1, 12, 1),
        "start_y": (0, 50000, 1), "bottom_y": (0, 50000, 1),
        "manual_x": (0, 50000, 1), "column_width": (1, 50000, 1),
        "gutter": (0, 10000, 1), "body_indent": (0, 10000, 1),
        "character_height": (1, 2000, 1), "row_padding": (0, 1000, 1),
        "horizontal_tolerance": (0, 5000, 1), "darkness_threshold": (0, 765, 1),
        "column_track_radius": (0, 5000, 1), "column_track_block_height": (1, 10000, 1),
        "column_track_max_step": (0, 5000, 1),
        "paddle_band_width_ratio": (1, 100, 1), "paddle_band_left_margin": (0, 5000, 1),
        "paddle_left_tolerance": (0, 5000, 1), "paddle_max_input_side": (256, 20000, 64),
        "paddle_separator_safety_px": (0, 1000, 1),
        "paddle_separator_band_radius": (0, 200, 1),
        "paddle_separator_roi_width_ratio": (10, 100, 1),
        "paddle_separator_column_margin": (0, 2000, 1),
        "paddle_header_search_height": (0, 5000, 1), "paddle_header_rule_margin": (0, 1000, 1),
        "batch_interval": (0.5, 3600, 0.5),
        "illustration_detect_padding": (0, 5000, 1),
        "illustration_detect_right_padding": (0, 5000, 1),
        "main_entry_font_size": (5, 200, 1), "review_entry_font_size": (6, 200, 1),
        "review_entry_vertical_padding": (0, 30, 1),
        "review_single_cjk_line_height": (0, 500, 1), "review_zoom_percent": (20, 250, 5),
    }

    SETTING_HELP_IMAGES = {
        "columns": "layout_col_number.png",
        "start_y": "layout_settings.png",
        "bottom_y": "layout_settings.png",
        "manual_x": "layout_settings.png",
        "column_width": "layout_settings.png",
        "gutter": "layout_settings.png",
        "character_height": "layout_settings.png",
        "row_padding": "layout_settings.png",
    }

    SETTING_CHOICES = {
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

    CHECK_HELP = {
        "manual_columns": "开启：普通画线/版面几何优先使用项目中保存的手工栏位置，而不是让每页自动估计。适合自动分栏被插图、装饰线或异常空白稳定干扰的项目。\n\n关闭（推荐默认）：按实际页面估计栏几何，对轻微扫描偏移更鲁棒。若开启后栏线整体错位，应先检查 manual_x、column_width、gutter，而不是继续调 OCR。",
        "follow_column_deformation": "开启：沿页面分块重新跟踪栏左缘，让栏路径可随书脊弯曲、斜拍或局部形变变化；会使用搜索半径、分块高度和最大步移三个高级参数。\n\n关闭：栏左缘按较直的几何路径处理，平直扫描更稳定也更简单。没有明显弯曲时不建议开启。",
        "paddle_use_paddleocr": "开启：PaddleOCR 作为 OCR画线的主文字识别来源。默认推荐，因为后续 grammar/parser、候选评分和多 OCR 融合都围绕结构化文字结果工作。\n\n关闭：仅用于专门测试其他引擎或故障排查；若同时没有可用 Tesseract/Lens，OCR画线将缺少主要文字来源。",
        "paddle_use_textline_orientation": "开启：让 PaddleOCR 额外处理文字行方向/旋转信息，适合文字行方向不稳定、局部旋转或特殊扫描。\n\n代价：通常增加计算并可能改变模型路径。普通已经规范化的横排/竖排页面不需要为了“更准”而默认开启，优先让 Project Profile 的页面变换处理整体方向。",
        "paddle_remove_syllable_separators": "开启：最终 lemma 归一化时去掉音节分隔点（如 ·、•、∙、‧），并对部分 OCR 分隔符误识别做保守清理；真正的单个词内连字符原则上保留。\n\n关闭：保留词头中的这些分隔符，适合词典索引本身就要求保留音节标记的项目。它改变输出 lemma 文本，不改变词头 Y。",
        "paddle_auto_header_rule": "开启：在页面顶部指定范围内寻找高横向墨迹占比的页眉横线，并把其上方内容排除出候选区。可减少 running header、页码等误词头。\n\n关闭：不做这套自动横线截断。若 Project Profile 已明确提供页眉模板，优先相信模板；第一条正文被误裁时检查搜索高度、墨迹比例和页眉后余量。",
        "paddle_enable_lens": "开启：允许 Google Lens 作为网络第三意见；实际何时调用、是否投票由【Lens 运行模式】决定。\n\n注意：会产生网络等待且依赖外部服务可用性。默认不应把 Lens 当成本地 OCR 的必需依赖，推荐仅在冲突模式下使用。",
        "paddle_require_visual_cue": "名称是历史遗留。当前实现并不是“必须有纯视觉证据”，而是要求候选至少有一个结构或视觉 fallback cue：POS/变形/描述符/特殊符号，或字高/粗体/行前空白之一。\n\n开启可抑制只有合法字母形态、却没有任何词条特征的正文行；关闭会放宽候选门槛，除非 diagnostics 明确显示真实词头因此被拒，否则不建议关闭。",
        "paddle_require_pos_or_symbol": "开启：普通词头候选必须具有至少一个强结构提示：POS、变形、结构描述符或可作为新词条证据的特殊符号。能显著抑制栏左正文误检。\n\n关闭：允许仅靠位置/视觉分数通过，召回更高但假阳性更多。对结构化拉丁词典通常建议开启；CJK/特殊 Profile 还会有自己的专用接受逻辑。",
        "paddle_refine_separator_y": "开启：OCR 先提供词头粗 Y，再在当前栏左局部墨迹中寻找更合理的行间空白位置，把横线精修到视觉分隔处。\n\n关闭：更接近直接使用 OCR 粗定位，速度/逻辑更简单但线可能贴字。若精修总跳到相邻行，再检查搜索范围、平滑半径、安全距离，而不是直接永久关闭。",
        "paddle_compare_tesseract": "开启：对同一候选带额外运行 Tesseract，作为 PaddleOCR 的第二意见并进入比较/诊断；需要 Tesseract 程序和相应语言包。\n\n影响：运行时间增加，但可暴露系统性字符差异。它本身不等于“允许 Tesseract 独有结果补线”，后者由【Tesseract 可补漏 Paddle】控制。",
        "paddle_tesseract_rescue": "开启：允许满足结构/位置条件的 Tesseract 独有候选补回 Paddle 漏掉的词头，而不只是做诊断对照。\n\n风险：可提高召回，也会引入 Tesseract 特有误检。建议先开启对照看 comparison/issues，再决定是否让其参与补漏。",
        "paddle_tesseract_auto_psm": "开启：程序自动比较 Tesseract PSM 4 与 PSM 6，选择更适合当前候选带的结果；减少手动猜 Page Segmentation Mode。\n\n关闭：固定使用【Tesseract 对照 PSM】。只有已验证某本词典某个 PSM 明显更稳定、且自动选择反复选错时才关闭。",
        "paddle_dual_ocr_arbitration": "开启：对 Paddle/Tesseract（以及可投票的 Lens）候选按 canonical V、lemma 相似度、结构与质量做融合/仲裁，而不是让某个引擎简单覆盖另一个。\n\n关闭：更接近单引擎/诊断式工作流。正常多 OCR 项目建议开启；需要复现实验性的单引擎结果时再关闭。",
        "paddle_show_candidate_checkboxes": "开启：主图为栏左 OCR 候选显示人工复选框，可把自动拒绝但合理的候选手工加入，也可取消自动接受结果；人工决定保存到独立 sidecar，便于追溯。\n\n关闭：界面更干净，但失去逐候选快速覆盖入口。只影响人工复核 UI，不重新运行 OCR。",
        "ocr_replace": "开启：普通文本 OCR 完成后执行项目替换规则，用于已知 OCR 拼写/字符归一化。这里说的是“已有词条线后的文本 OCR”，不是 OCR画线的词头 parser。\n\n关闭：保留 OCR 原始文本。排查替换规则是否误改内容时可暂时关闭。",
        "lowercase_ocr": "开启：普通文本 OCR 输出统一转为小写。只影响文本内容，不改变词头横线、坐标或 OCR画线候选。\n\n注意：专名、缩写或大小写具有词典意义的项目不应开启。它不是排序时的大小写折叠选项。",
        "review_main_show_ocr_choices": "开启：校对窗口打开时，主界面仍保留多 OCR 候选/选择控件，便于一边看校对行一边核对不同引擎结果。\n\n关闭：校对期间隐藏这些控件，使主界面更简洁。只影响显示，不清除候选数据。",
        "review_main_show_ocr_background": "开启：校对窗口打开时，主界面词条框仍按 OCR 置信度/状态显示底色，便于快速发现低可信项。\n\n关闭：校对期间使用更干净的统一显示。只改变视觉提示，不影响实际置信度或词条内容。",
        "main_entry_font_bold": "开启后主界面词条编辑框使用粗体；关闭为常规字重。只改变显示和预览字体，不会改变 OCR、PDIC、坐标或切图。",
        "main_entry_font_italic": "开启后主界面词条编辑框使用斜体；关闭为正体。仅影响显示。某些字体的斜体字宽会变化，可能让文本框视觉占用略有不同，但保存内容不变。",
        "review_entry_font_bold": "开启后校对窗口“原词条”编辑框使用粗体；关闭为常规字重。只影响校对文字显示和字体测量，不改变原图裁图或保存内容。",
        "review_entry_font_italic": "开启后校对窗口“原词条”编辑框使用斜体；关闭为正体。只影响显示；若某字体斜体导致字符更宽，可见字符数可能略变，但词条数据不变。",
    }

    NORMAL_CHECKS = (
        ("跟随栏左缘倾斜/弯曲", "follow_column_deformation"),
        ("手动分栏", "manual_columns"),
    )
    OCR_COMMON_CHECKS = (
        ("PaddleOCR 主识别", "paddle_use_paddleocr"),
        ("同时运行 Tesseract 对照", "paddle_compare_tesseract"),
        ("多 OCR 自动融合", "paddle_dual_ocr_arbitration"),
        ("要求结构/视觉提示", "paddle_require_visual_cue"),
        ("要求词性/变形/词条符号", "paddle_require_pos_or_symbol"),
        ("自动精修横线 Y", "paddle_refine_separator_y"),
    )
    OCR_ADVANCED_CHECKS = (
        ("启用文字行方向识别", "paddle_use_textline_orientation"),
        ("自动忽略页眉横线以上", "paddle_auto_header_rule"),
        ("去除词头音节分隔点", "paddle_remove_syllable_separators"),
        ("Tesseract 可补漏 Paddle", "paddle_tesseract_rescue"),
        ("Tesseract 自动比较 PSM 4/6", "paddle_tesseract_auto_psm"),
        ("显示每个 OCR 候选复选框", "paddle_show_candidate_checkboxes"),
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

    def _show_settings_help(
        self,
        title: str,
        body: str,
        image_name: str | None = None,
    ) -> None:
        if hasattr(self, "_settings_help_title_var"):
            self._settings_help_title_var.set(str(title or "设置说明"))
        if hasattr(self, "_settings_help_body_var"):
            self._settings_help_body_var.set(str(body or "不确定时保持当前值即可。"))
        self._settings_help_current_image = image_name
        self._schedule_settings_help_image_render()

    def _settings_help_image_path(self, image_name: str) -> Path:
        return (
            Path(__file__).resolve().parent
            / "data"
            / "layout_example"
            / image_name
        )

    def _load_settings_help_image(self, image_name: str) -> Image.Image | None:
        cached = self._settings_help_original_images.get(image_name)
        if cached is not None:
            return cached
        path = self._settings_help_image_path(image_name)
        try:
            with Image.open(path) as opened:
                image = opened.convert("RGBA").copy()
        except (OSError, ValueError):
            return None
        self._settings_help_original_images[image_name] = image
        return image

    def _schedule_settings_help_image_render(self) -> None:
        job = getattr(self, "_settings_help_image_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._settings_help_image_job = self.after_idle(self._render_settings_help_images)

    def _render_settings_help_images(self) -> None:
        self._settings_help_image_job = None
        image_name = getattr(self, "_settings_help_current_image", None)
        original = self._load_settings_help_image(image_name) if image_name else None

        for label, separator, help_box in self._settings_help_image_widgets:
            if original is None:
                try:
                    label.configure(image="")
                    label.image = None
                    label.pack_forget()
                except tk.TclError:
                    pass
                continue
            try:
                mapped = bool(help_box.winfo_ismapped())
            except tk.TclError:
                continue
            if not mapped:
                continue

            available_width = max(180, int(help_box.winfo_width()) - 28)
            max_width = min(380, available_width)
            max_height = 330
            scale = min(
                1.0,
                max_width / max(1, original.width),
                max_height / max(1, original.height),
            )
            width = max(1, int(round(original.width * scale)))
            height = max(1, int(round(original.height * scale)))
            rendered = original.resize((width, height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(themed_display_image(rendered, self.parent.appearance_mode))
            label.configure(image=photo)
            label.image = photo
            label.pack(
                anchor="center",
                fill="x",
                pady=(12, 2),
                before=separator,
            )

    def _show_setting_help(self, name: str, *, show_layout_image: bool = False) -> None:
        title = self.SETTING_LABELS.get(name, self._field_meta.get(name, (name, str))[0])
        body = self.SETTING_HELP.get(name, "专家参数；不确定时建议保持当前值。")
        unit = self.SETTING_UNITS.get(name, "")
        if unit:
            body += f"\n\n单位：{unit}"
        image_name = self.SETTING_HELP_IMAGES.get(name) if show_layout_image else None
        self._show_settings_help(title, body, image_name)

    def _show_check_help(self, label: str, name: str) -> None:
        self._show_settings_help(
            label,
            self.CHECK_HELP.get(name, "高级行为开关；不确定时保持默认。"),
        )

    def _bind_help_widget(self, widget: tk.Misc, callback) -> None:
        """Keep full explanations one glance away without filling every form row."""
        try:
            widget.bind("<Enter>", lambda _e: callback(), add="+")
            widget.bind("<FocusIn>", lambda _e: callback(), add="+")
        except tk.TclError:
            return
        try:
            for child in widget.winfo_children():
                self._bind_help_widget(child, callback)
        except tk.TclError:
            pass

    def _bind_responsive_labels(
        self,
        container: tk.Misc,
        *labels: ttk.Label,
        horizontal_padding: int = 12,
        min_wrap: int = 120,
    ) -> None:
        """Wrap descriptive text to the width it actually receives on screen."""

        def refresh(event=None) -> None:
            try:
                width = int(event.width) if event is not None else int(container.winfo_width())
            except (AttributeError, tk.TclError, TypeError, ValueError):
                return
            if width <= 1:
                return
            wraplength = max(min_wrap, width - horizontal_padding)
            for label in labels:
                try:
                    label.configure(wraplength=wraplength)
                except tk.TclError:
                    pass

        try:
            container.bind("<Configure>", refresh, add="+")
            self.after_idle(refresh)
        except tk.TclError:
            pass

    def _setting_var(self, name: str) -> tk.Variable:
        if name in self.vars:
            return self.vars[name]
        # Settings Center edits persisted project values. Layout geometry is
        # therefore shown in canonical reference-page pixels; the main workspace
        # separately shows current-page/source equivalents where appropriate.
        raw = getattr(self.parent.settings, name)
        choices = self.SETTING_CHOICES.get(name)
        if choices:
            reverse = {value: label for label, value in choices.items()}
            value = reverse.get(str(raw), str(raw))
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
            families = tuple(sorted(set(font.families()), key=str.casefold))
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
            info.bind("<Button-1>", lambda _e, n=name: self._show_setting_help(n), add="+")
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
        for label, name in checks:
            if name not in self.vars:
                self.vars[name] = tk.BooleanVar(value=bool(getattr(self.parent.settings, name)))
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
        help_title.pack(anchor="w", fill="x")
        help_body = ttk.Label(
            help_box,
            textvariable=self._settings_help_body_var,
            foreground="#555b63",
            justify="left",
        )
        help_body.pack(anchor="w", fill="x", pady=(7, 0))
        help_image = ttk.Label(help_box, anchor="center")
        help_separator = ttk.Separator(help_box, orient="horizontal")
        help_separator.pack(fill="x", pady=(14, 10))
        self._settings_help_image_widgets.append(
            (help_image, help_separator, help_box)
        )
        help_hint = ttk.Label(
            help_box,
            text="把鼠标停在设置项上，或用 Tab/鼠标进入输入框，"
                 "这里会显示完整说明。高级设置不确定时保持默认即可。",
            foreground="#7a8088",
            justify="left",
        )
        help_hint.pack(anchor="w", fill="x")
        self._bind_responsive_labels(
            help_box,
            help_title,
            help_body,
            help_hint,
            horizontal_padding=28,
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
            "按工作任务整理：第一次使用优先看“常用 / OCR画线（推荐）”；"
            "普通画线是备用方案，底层阈值、正则和后端参数集中在高级区，不确定时无需修改。",
        )
        self._configure_settings_appearance_styles()
        notebook = ttk.Notebook(outer, style="PC.Settings.TNotebook")
        self.notebook = notebook
        notebook.pack(fill="both", expand=True)
        self._settings_canvases: dict[str, tk.Canvas] = {}

        common_tab = ttk.Frame(notebook)
        normal_tab = ttk.Frame(notebook)
        ocr_tab = ttk.Frame(notebook)
        display_tab = ttk.Frame(notebook)
        project_tab = ttk.Frame(notebook)
        advanced_tab = ttk.Frame(notebook)
        sort_tab = ttk.Frame(notebook)
        rules_tab = ttk.Frame(notebook)
        for tab, label in (
            (common_tab, "常用"),
            (ocr_tab, "OCR画线（推荐）"),
            (normal_tab, "普通画线（备用）"),
            (display_tab, "显示 / 校对"),
            (project_tab, "项目 / 批量"),
            (advanced_tab, "高级"),
            (sort_tab, "排序"),
            (rules_tab, "过滤规则"),
        ):
            notebook.add(tab, text=label)

        self._settings_tabs = {
            "common": common_tab,
            "normal": normal_tab,
            "ocr": ocr_tab,
            "display": display_tab,
            "project": project_tab,
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

        # SettingsDialog no longer duplicates the normal Project Profile wizard.
        # Keep the active profile ID intact for save() while exposing a direct
        # button to the guided wizard from the common/advanced pages.
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
            "推荐流程：项目 Profile → 检测版面参数 → 当前页运行 OCR 画线 → "
            "确认无明显漏线/误线后再批量。OCR画线是默认推荐路径，会同时利用文字、位置和结构证据；"
            "普通画线保留为备用方案，主要用于左缘极稳定的简单版式或 OCR 暂不可用时。",
        )
        workflow = ttk.Frame(common)
        workflow.pack(fill="x", pady=(0, 10))
        ttk.Button(
            workflow, text="打开项目 Profile…", command=parent.open_project_profile
        ).pack(side="left")
        ttk.Button(
            workflow, text="检测当前页版面参数", command=parent.detect_layout_current
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            workflow, text="环境中心", command=self.check_ocr_engines
        ).pack(side="left", padx=(6, 0))

        mode_group = ttk.LabelFrame(common, text="默认画线方式", padding=(12, 9))
        mode_group.pack(fill="x", pady=(0, 10))
        mode_group.columnconfigure(1, weight=1)
        method_var = tk.StringVar(
            value=DETECTION_LABELS.get(
                parent.settings.detection_method, DETECTION_LABELS["paddleocr"]
            )
        )
        self.vars["detection_method"] = method_var

        ocr_mode = ttk.Radiobutton(
            mode_group,
            text="OCR画线（推荐）",
            variable=method_var,
            value=DETECTION_LABELS["paddleocr"],
        )
        ocr_mode.grid(row=0, column=0, sticky="w", pady=3)
        ocr_mode_help = ttk.Label(
            mode_group,
            text="默认推荐；结合文字、位置和结构证据，适合绝大多数词典项目。",
            foreground="#666666",
            justify="left",
        )
        ocr_mode_help.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=3)
        self._bind_responsive_labels(
            ocr_mode_help, ocr_mode_help, horizontal_padding=4, min_wrap=100
        )

        normal_mode = ttk.Radiobutton(
            mode_group,
            text="普通画线（备用）",
            variable=method_var,
            value=DETECTION_LABELS["left_edge"],
        )
        normal_mode.grid(row=1, column=0, sticky="w", pady=3)
        normal_mode_help = ttk.Label(
            mode_group,
            text="不识别文字；仅在左缘极稳定的简单版式或 OCR 暂不可用时优先考虑。",
            foreground="#666666",
            justify="left",
        )
        normal_mode_help.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=3)
        self._bind_responsive_labels(
            normal_mode_help, normal_mode_help, horizontal_padding=4, min_wrap=100
        )

        for widget, title, body in (
            (
                ocr_mode,
                "OCR画线（推荐）",
                "默认推荐路径：先在每栏左侧窄候选带运行 OCR，再把 lemma 结构、栏左位置、"
                "POS/变形/特殊符号、字高/粗体/行前空白等证据组合判断。首次推理更耗时，"
                "但未改变图像/模型/候选带时可复用 OCR 缓存；大多数词典应先调这条路径，而不是退回纯几何画线。",
            ),
            (
                normal_mode,
                "普通画线（备用）",
                "只看版面几何和栏左墨迹，不依赖文字识别。适合词头稳定贴近栏左、正文有一致缩进的简单版式，"
                "也可作为 OCR 环境不可用时的备用路径。正文同样贴边、缩进不稳定或需要 POS/符号语义时，"
                "它缺少文字结构证据，因此更容易误检或漏检。",
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
            intro="只有扫描页确实弯曲/倾斜或自动分栏失败时才需要改变。",
        )
        self._add_collapsible_settings(
            normal,
            "高级设置（普通画线异常时再展开）",
            self.NORMAL_ADVANCED_FIELDS,
        )

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
        ttk.Checkbutton(
            appearance_group,
            text="深色模式（夜间模式）",
            variable=self.parent.dark_mode_var,
            command=self.parent._toggle_dark_mode,
        ).pack(anchor="w")
        ttk.Label(
            appearance_group,
            text="同步主界面、校对/Profile/设置窗口，并对扫描图做仅显示层的夜间转换；"
                 "不会修改原图、OCR 输入、PDIC/PPP、切图或导出文件。",
            wraplength=720,
            justify="left",
        ).pack(anchor="w", fill="x", pady=(4, 0))
        self._add_setting_group(
            display,
            "界面与校对",
            self.DISPLAY_FIELDS,
            single_line_labels=True,
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

        advanced = self._scrollable_settings_page(advanced_tab)
        self._settings_intro(
            advanced,
            "高级 / 专家参数",
            "这里保留版面语义、OCR 后端和正则规则等底层控制。"
            "如果只是想提高某本词典的识别率，请优先回到“OCR画线（推荐）”页或 Project Profile；"
            "只有左缘高度规则的简单版式才优先考虑“普通画线（备用）”。",
        )
        ttk.Button(
            advanced, text="打开项目 Profile（推荐）…", command=parent.open_project_profile
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
        self.update_idletasks()
        for _canvas in self._settings_canvases.values():
            _bbox = _canvas.bbox("all")
            if _bbox:
                _canvas.configure(scrollregion=_bbox)
        # Keep Settings Center modeless: users often need to move the pointer
        # over the main image to read coordinates while entering layout values.
        # Do not use transient()/grab_set(), which would keep this window in
        # front and block interaction with the main workspace.

    def _configure_settings_appearance_styles(self) -> None:
        style = ttk.Style(self)
        base = appearance_palette(self.parent.appearance_mode)
        if self.parent.appearance_mode == "dark":
            selected_bg = base["surface"]
            active_bg = base["button_hover"]
            idle_bg = base["surface_alt"]
            selected_fg = base["text"]
            idle_fg = base["muted"]
        else:
            selected_bg = str(style.lookup("TFrame", "background") or "#f6f7f9")
            active_bg = "#f1f3f6"
            idle_bg = "#e6eaf0"
            selected_fg = "#111827"
            idle_fg = "#4b5563"
        style.configure(
            "PC.Settings.TNotebook",
            background=selected_bg,
            borderwidth=0,
            tabmargins=(0, 2, 0, 0),
        )
        style.configure(
            "PC.Settings.TNotebook.Tab",
            padding=(13, 7),
            borderwidth=1,
            relief="raised",
            background=idle_bg,
            foreground=idle_fg,
        )
        style.map(
            "PC.Settings.TNotebook.Tab",
            background=[
                ("selected", selected_bg),
                ("active", active_bg),
                ("!selected", idle_bg),
            ],
            foreground=[
                ("selected", selected_fg),
                ("active", selected_fg),
                ("!selected", idle_fg),
            ],
            relief=[("selected", "sunken"), ("!selected", "raised")],
        )

    def refresh_appearance(self) -> None:
        """Apply the global appearance without touching unsaved setting values."""
        self._configure_settings_appearance_styles()
        self.parent._apply_current_appearance(self)
        self._schedule_settings_help_image_render()

    def select_tab(self, key: str | None) -> None:
        """Select a requested settings task when reusing the modeless window."""
        if not hasattr(self, "notebook") or not hasattr(self, "_settings_tabs"):
            return
        tab = self._settings_tabs.get(key or "common", self._settings_tabs["common"])
        try:
            self.notebook.select(tab)
        except tk.TclError:
            pass

    def _build_project_details_tab(self, tab: ttk.Frame) -> None:
        """Build project metadata fields without mixing them into OCR controls."""
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
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="e", padx=(0, 8), pady=5)
            var = tk.StringVar(value=str(getattr(self.parent.settings, name)))
            self.vars[name] = var
            ttk.Entry(form, textvariable=var, width=42).grid(row=row, column=1, sticky="ew", pady=5)

        ocr_language = str(self.vars.get("ocr_language").get() if self.vars.get("ocr_language") else "")
        configured_index_language = str(self.parent.settings.dictionary_index_language).strip().lower()
        suggested_index_language = project_language_from_ocr(ocr_language)
        self._project_index_language_auto = not configured_index_language
        index_var = tk.StringVar(value=configured_index_language or suggested_index_language)
        content_var = tk.StringVar(value=str(self.parent.settings.dictionary_content_language).strip().lower())
        self.vars["dictionary_index_language"] = index_var
        self.vars["dictionary_content_language"] = content_var

        ttk.Label(form, text="索引语言：").grid(row=3, column=0, sticky="e", padx=(0, 8), pady=5)
        index_combo = ttk.Combobox(
            form, textvariable=index_var, values=PROJECT_LANGUAGE_CODES, state="readonly", width=12,
        )
        index_combo.grid(row=3, column=1, sticky="w", pady=5)
        index_combo.bind("<<ComboboxSelected>>", lambda _event: setattr(self, "_project_index_language_auto", False))
        ttk.Label(form, text="2 位语言代号；首次按 OCR 语言自动选择", foreground="#666666").grid(
            row=3, column=1, sticky="w", padx=(120, 0), pady=5
        )

        ttk.Label(form, text="内容语言：").grid(row=4, column=0, sticky="e", padx=(0, 8), pady=5)
        ttk.Combobox(
            form, textvariable=content_var, values=PROJECT_LANGUAGE_CODES, state="readonly", width=12,
        ).grid(row=4, column=1, sticky="w", pady=5)
        ttk.Label(form, text="2 位语言代号", foreground="#666666").grid(
            row=4, column=1, sticky="w", padx=(120, 0), pady=5
        )

        if "columns" not in self.vars:
            self.vars["columns"] = tk.StringVar(value=str(self.parent.settings.columns))
        ttk.Label(form, text="词典版面栏数：").grid(row=5, column=0, sticky="e", padx=(0, 8), pady=5)
        ttk.Spinbox(form, textvariable=self.vars["columns"], from_=1, to=12, width=10).grid(
            row=5, column=1, sticky="w", pady=5
        )

        page_range_var = tk.StringVar(value=str(self.parent.settings.dictionary_body_page_range))
        self.vars["dictionary_body_page_range"] = page_range_var
        ttk.Label(form, text="正文页码范围：").grid(row=6, column=0, sticky="e", padx=(0, 8), pady=5)
        ttk.Entry(form, textvariable=page_range_var, width=24).grid(row=6, column=1, sticky="w", pady=5)
        ttk.Label(form, text="例如：1-1250", foreground="#666666").grid(
            row=6, column=1, sticky="w", padx=(205, 0), pady=5
        )

        ocr_var = self.vars.get("ocr_language")
        if ocr_var is not None:
            def sync_index_language(*_args) -> None:
                if self._project_index_language_auto:
                    mapped = project_language_from_ocr(str(ocr_var.get()))
                    if mapped in PROJECT_LANGUAGE_CODES:
                        index_var.set(mapped)

            ocr_var.trace_add("write", sync_index_language)

        ttk.Label(
            tab,
            text="这些资料随当前项目保存在 _PictureCapture/settings.json 中。",
            foreground="#666666",
        ).grid(row=1, column=0, sticky="w", padx=18)

    def _build_profile_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        top = ttk.Frame(tab, padding=(14, 12, 14, 8))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        selected_key = effective_project_profile_id(
            self.parent.settings,
            project_profile_path(self.parent.project.root) if self.parent.project else None,
        )
        try:
            selected = dictionary_profile_preset(selected_key)
        except Exception:
            selected = dictionary_profile_preset(DEFAULT_PROFILE_ID)
            selected_key = selected.key
        self._active_profile_key = selected_key
        self._profile_selection_changed = False
        self.custom_profile_name_var = tk.StringVar(
            value=str(getattr(self.parent.settings, "dictionary_custom_profile_name", "") or "")
        )
        self.vars["dictionary_custom_profile_name"] = self.custom_profile_name_var
        self._profile_label_to_key = self._build_profile_choice_labels()
        self.profile_choice_var = tk.StringVar(value=self._profile_label_for_key(selected_key))
        ttk.Label(top, text="词头类型：").grid(row=0, column=0, sticky="e", padx=(0, 8), pady=4)
        self.profile_combo = ttk.Combobox(
            top, textvariable=self.profile_choice_var,
            values=tuple(self._profile_label_to_key.keys()), state="readonly", width=44,
        )
        self.profile_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        ttk.Button(top, text="恢复 Profile 默认值", command=self.restore_profile_defaults).grid(
            row=0, column=2, padx=(10, 0), pady=4
        )

        ttk.Label(top, text="自定义结构名称：").grid(
            row=1, column=0, sticky="e", padx=(0, 8), pady=4
        )
        self.custom_profile_name_entry = ttk.Entry(
            top, textvariable=self.custom_profile_name_var, width=32,
        )
        self.custom_profile_name_entry.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(
            top,
            text="仅修改当前项目中“自定义结构”的显示名称；底层 Profile key 仍为 custom。",
            foreground="#666666",
        ).grid(row=1, column=2, columnspan=2, sticky="w", padx=(10, 0), pady=4)
        self.custom_profile_name_var.trace_add(
            "write", lambda *_args: self.after_idle(self._on_custom_profile_name_changed)
        )

        self.profile_description_var = tk.StringVar(value="")
        self.profile_examples_var = tk.StringVar(value="")
        self.profile_layout_summary_var = tk.StringVar(value="")
        profile_description = ttk.Label(
            top, textvariable=self.profile_description_var, justify="left"
        )
        profile_description.grid(
            row=2, column=0, columnspan=4, sticky="ew", pady=(8, 2)
        )
        profile_examples = ttk.Label(
            top, textvariable=self.profile_examples_var, justify="left"
        )
        profile_examples.grid(
            row=3, column=0, columnspan=4, sticky="ew", pady=(2, 0)
        )
        self._bind_responsive_labels(
            top,
            profile_description,
            profile_examples,
            horizontal_padding=20,
            min_wrap=180,
        )
        ttk.Label(
            top, textvariable=self.profile_layout_summary_var,
            font=("TkDefaultFont", 10, "bold"), foreground="#245a86",
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(5, 0))
        self._sync_custom_profile_name_state()

        profile_scroll_host = ttk.Frame(tab)
        profile_scroll_host.grid(row=1, column=0, sticky="nsew")
        profile_scroll_host.rowconfigure(0, weight=1)
        profile_scroll_host.columnconfigure(0, weight=1)
        profile_canvas = tk.Canvas(profile_scroll_host, highlightthickness=0, borderwidth=0)
        self.profile_canvas = profile_canvas
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
        field_meta = self._field_meta
        for gi, (title, names) in enumerate(self.PROFILE_FIELD_GROUPS):
            group = ttk.LabelFrame(body, text=title, padding=(10, 7))
            group.grid(row=gi // 2, column=gi % 2, sticky="nsew", padx=(0 if gi % 2 == 0 else 6, 6 if gi % 2 == 0 else 0), pady=(0, 8))
            group.columnconfigure(1, weight=1)
            for row, name in enumerate(names):
                label, _cast = field_meta[name]
                ttk.Label(group, text=label).grid(row=row, column=0, sticky="e", padx=(0, 7), pady=3)
                if name not in self.vars:
                    self.vars[name] = tk.StringVar(value=str(getattr(self.parent.settings, name)))
                var = self.vars[name]
                if name == "ocr_language":
                    widget = ttk.Combobox(group, textvariable=var, values=self.OCR_LANGUAGES, state="normal", width=24)
                    widget.bind("<<ComboboxSelected>>", lambda _e: self._on_profile_language_changed())
                    widget.bind("<FocusOut>", lambda _e: self._on_profile_language_changed())
                    var.trace_add("write", lambda *_args: self.after_idle(self._refresh_sort_choices))
                elif name == "layout_writing_mode":
                    widget = ttk.Combobox(
                        group, textvariable=var, values=("horizontal-tb", "vertical-rl", "vertical-lr"),
                        state="readonly", width=24,
                    )
                    widget.bind("<<ComboboxSelected>>", lambda _e: self._sync_layout_semantics())
                elif name == "layout_text_direction":
                    widget = ttk.Combobox(group, textvariable=var, values=("ltr", "rtl"), state="readonly", width=24)
                    widget.bind("<<ComboboxSelected>>", lambda _e: self._sync_layout_semantics())
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
                    var.trace_add("write", lambda *_args: self.after_idle(self._refresh_profile_status))
                except tk.TclError:
                    pass

        check_group = ttk.LabelFrame(body, text="识别行为", padding=(10, 7))
        check_group.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        for row, (label, name) in enumerate(self.PROFILE_CHECKS):
            if name not in self.vars:
                self.vars[name] = tk.BooleanVar(value=bool(getattr(self.parent.settings, name)))
            ttk.Checkbutton(check_group, text=label, variable=self.vars[name]).grid(row=row, column=0, sticky="w", pady=3)
            try:
                self.vars[name].trace_add("write", lambda *_args: self.after_idle(self._refresh_profile_status))
            except tk.TclError:
                pass

        self.profile_status_var = tk.StringVar(value="")
        status = ttk.Frame(tab, padding=(14, 0, 14, 10))
        status.grid(row=2, column=0, sticky="ew")
        ttk.Label(status, textvariable=self.profile_status_var).pack(side="left")
        ttk.Label(
            status,
            text="Profile 默认值是起点；这里的手工调整会作为项目 overrides 保存，不会改写内置 Profile。",
        ).pack(side="right")
        self._refresh_profile_summary()
        self.after_idle(self._refresh_profile_status)

    def _build_profile_choice_labels(self) -> dict[str, str]:
        """Return numbered Profile labels, always keeping custom as the last item."""
        profiles = list(available_dictionary_profiles())
        profiles.sort(key=lambda profile: profile.key == "custom")
        custom_name = (
            str(self.custom_profile_name_var.get()).strip()
            if hasattr(self, "custom_profile_name_var") else ""
        )
        labels: dict[str, str] = {}
        for index, profile in enumerate(profiles, start=1):
            display_name = profile.display_name
            if profile.key == "custom" and custom_name:
                display_name = f"{custom_name}（自定义）"
            labels[f"{index}. {display_name}"] = profile.key
        return labels

    def _profile_label_for_key(self, key: str) -> str:
        for label, value in self._profile_label_to_key.items():
            if value == key:
                return label
        # Compatibility aliases use the display name of their visible base
        # profile; map them back to that numbered visible choice.
        try:
            wanted_name = dictionary_profile_preset(key).display_name
        except Exception:
            wanted_name = ""
        for label, value in self._profile_label_to_key.items():
            try:
                if dictionary_profile_preset(value).display_name == wanted_name:
                    return label
            except Exception:
                continue
        return next(iter(self._profile_label_to_key), "")

    def _profile_display_name(self, key: str) -> str:
        if key == "custom":
            custom_name = str(self.custom_profile_name_var.get()).strip()
            if custom_name:
                return f"{custom_name}（自定义）"
        return dictionary_profile_preset(key).display_name

    def _sync_custom_profile_name_state(self) -> None:
        if not hasattr(self, "custom_profile_name_entry"):
            return
        state = "normal" if self._current_profile_key() == "custom" else "disabled"
        self.custom_profile_name_entry.configure(state=state)

    def _on_custom_profile_name_changed(self) -> None:
        if not hasattr(self, "profile_combo"):
            return
        current_key = self._current_profile_key()
        self._profile_label_to_key = self._build_profile_choice_labels()
        self.profile_combo.configure(values=tuple(self._profile_label_to_key.keys()))
        self.profile_choice_var.set(self._profile_label_for_key(current_key))
        self._sync_custom_profile_name_state()
        self._refresh_profile_summary()
        self._refresh_profile_status()

    def _current_profile_key(self) -> str:
        if hasattr(self, "profile_choice_var"):
            return self._profile_label_to_key.get(
                self.profile_choice_var.get(), self._active_profile_key or DEFAULT_PROFILE_ID
            )
        return str(self._active_profile_key or self.parent.settings.dictionary_profile_id or DEFAULT_PROFILE_ID)

    def _refresh_profile_summary(self) -> None:
        profile = dictionary_profile_preset(self._current_profile_key())
        self.profile_description_var.set(profile.description)
        try:
            columns = max(1, int(self.vars.get("columns").get())) if self.vars.get("columns") else 1
        except (TypeError, ValueError, tk.TclError):
            columns = 1
        layout = {
            "writing_mode": str(self.vars.get("layout_writing_mode").get()) if self.vars.get("layout_writing_mode") else "horizontal-tb",
            "text_direction": str(self.vars.get("layout_text_direction").get()) if self.vars.get("layout_text_direction") else "ltr",
            "canonical_transform": str(self.vars.get("layout_transform").get()) if self.vars.get("layout_transform") else "identity",
            "columns": columns,
            "column_separator": str(self.vars.get("layout_column_separator_mode").get()) if self.vars.get("layout_column_separator_mode") else "auto",
        }
        language = str(self.vars.get("ocr_language").get()) if self.vars.get("ocr_language") else ""
        self.profile_layout_summary_var.set(
            f"{language} · {self._profile_display_name(profile.key)} · {profile_layout_summary(profile, layout)}"
        )
        if profile.examples:
            names = "；".join(example.dictionary for example in profile.examples)
            self.profile_examples_var.set(f"经典样例：{names}")
        else:
            self.profile_examples_var.set("经典样例：通用兼容型（当前未内置样页）")

    def _coerce_profile_var(self, name: str):
        var = self.vars.get(name)
        if var is None:
            return None
        value = var.get()
        if isinstance(var, tk.BooleanVar):
            return bool(value)
        cast = self._casts.get(name, str)
        try:
            return cast(value)
        except Exception:
            return value

    def _refresh_profile_status(self) -> None:
        if not hasattr(self, "profile_status_var"):
            return
        key = self._current_profile_key()
        current_language = str(self.vars.get("ocr_language").get() if self.vars.get("ocr_language") else "")
        defaults = profile_effective_settings(key, current_language=current_language)
        changed = []
        for name, expected in defaults.items():
            if name not in self.vars:
                continue
            if self._coerce_profile_var(name) != expected:
                changed.append(name)
        suffix = "（使用预设默认值）" if not changed else f"（项目调整 {len(changed)} 项）"
        self.profile_status_var.set(f"{self._profile_display_name(key)} {suffix}")

    def _apply_profile_defaults_to_vars(self, key: str, *, keep_supported_language: bool = True) -> None:
        current_language = ""
        if keep_supported_language and self.vars.get("ocr_language") is not None:
            current_language = str(self.vars["ocr_language"].get())
        defaults = profile_effective_settings(key, current_language=current_language)
        for name, value in defaults.items():
            if name not in self.vars:
                continue
            self.vars[name].set(value)
        self._active_profile_key = key
        self._refresh_profile_summary()
        self._on_profile_language_changed(update_profile_paddle=False)
        self._refresh_profile_status()

    def _on_profile_selected(self, _event=None) -> None:
        key = self._current_profile_key()
        self._profile_selection_changed = True
        self._sync_custom_profile_name_state()
        self._apply_profile_defaults_to_vars(key, keep_supported_language=True)

    def restore_profile_defaults(self) -> None:
        self._apply_profile_defaults_to_vars(self._current_profile_key(), keep_supported_language=True)

    def _on_profile_language_changed(self, update_profile_paddle: bool = True) -> None:
        key = self._current_profile_key()
        profile = dictionary_profile_preset(key)
        language = str(self.vars.get("ocr_language").get() if self.vars.get("ocr_language") else "")
        base = next((part.strip() for part in language.split("+") if part.strip()), "")
        if update_profile_paddle and self.vars.get("paddle_language") is not None:
            recommended = profile.paddle_language_by_language.get(base)
            if recommended:
                self.vars["paddle_language"].set(recommended)
        writing = str(self.vars.get("layout_writing_mode").get()) if self.vars.get("layout_writing_mode") else "horizontal-tb"
        for name, value in language_effective_settings(language, writing).items():
            if name in self.vars and (update_profile_paddle or name != "paddle_language"):
                self.vars[name].set(value)
        self._refresh_sort_choices()
        self._refresh_profile_summary()
        self._refresh_profile_status()

    def _sync_layout_semantics(self) -> None:
        writing = str(self.vars["layout_writing_mode"].get())
        direction = str(self.vars["layout_text_direction"].get())
        transform = "rotate_ccw90" if writing == "vertical-rl" else "rotate_cw90" if writing == "vertical-lr" else "mirror_x" if direction == "rtl" else "identity"
        self.vars["layout_transform"].set(transform)
        self._on_profile_language_changed()

    def _refresh_sort_choices(self, initial: bool = False) -> None:
        if not hasattr(self, "sort_combo"):
            return
        language = str(self.vars.get("ocr_language").get() if self.vars.get("ocr_language") else self.parent.settings.ocr_language).strip() or "eng"
        self.sort_language_var.set(language)
        mapping = available_profile_labels(language)
        self._sort_label_to_value = mapping
        self.sort_combo.configure(values=tuple(mapping.keys()))
        current_key = getattr(self.parent.settings, "headword_sort_mode", "auto") if initial else mapping.get(self.sort_mode_var.get(), "auto")
        # Preserve a currently selected key only if it belongs to the new language-specific menu.
        valid_values = set(mapping.values())
        if current_key not in valid_values:
            current_key = "auto"
        label = next((label for label, value in mapping.items() if value == current_key), next(iter(mapping)))
        self.sort_mode_var.set(label)
        self._toggle_custom_sort_state()

    def _toggle_custom_sort_state(self) -> None:
        key = self._sort_label_to_value.get(self.sort_mode_var.get(), "auto")
        state = "normal" if key == "custom" else "disabled"
        self.custom_order_entry.configure(state=state)
        self.custom_fold_check.configure(state=state)

    def _browse_wordslist_setting(self, var: tk.StringVar) -> None:
        initialdir = str(self.parent.project.root) if self.parent.project else None
        current = str(var.get()).strip()
        if self.parent.project and current:
            try:
                current_path = resolve_wordslist_path(self.parent.project.root, current)
                if current_path.parent.exists():
                    initialdir = str(current_path.parent)
            except Exception:
                pass
        chosen = filedialog.askopenfilename(
            parent=self, title="选择 wordslist 参考词表", initialdir=initialdir,
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not chosen:
            return
        path = Path(chosen)
        if self.parent.project:
            try:
                path_text = path.resolve().relative_to(self.parent.project.root.resolve()).as_posix()
            except ValueError:
                path_text = str(path.resolve())
        else:
            path_text = str(path)
        var.set(path_text)

    def _rules_path(self) -> Path | None:
        if self.parent.project:
            return headword_filter_rules_path(self.parent.project.root, HEADWORD_FILTER_RULES_FILENAME)
        return None

    def load_rules_editor(self) -> None:
        path = self._rules_path()
        if path and path.exists():
            text, _encoding = read_text_detected(path)
            self.rules_status_var.set(path.name)
        else:
            text = DEFAULT_HEADWORD_FILTER_RULES
            self.rules_status_var.set("尚未保存，将在保存参数时创建规则文件")
        self.rules_text.delete("1.0", "end"); self.rules_text.insert("1.0", text)

    def restore_default_rules(self) -> None:
        if not messagebox.askyesno("恢复默认规则", "将规则编辑框恢复为默认模板？保存参数前不会写入磁盘。", parent=self):
            return
        self.rules_text.delete("1.0", "end"); self.rules_text.insert("1.0", DEFAULT_HEADWORD_FILTER_RULES)
        self.rules_status_var.set("已恢复默认模板（尚未保存）")

    def import_rules(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="导入词头规则", filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            text, _encoding = read_text_detected(path); parse_headword_filter_rules(text, path)
        except Exception as exc:
            messagebox.showerror("规则无效", str(exc), parent=self); return
        self.rules_text.delete("1.0", "end"); self.rules_text.insert("1.0", text)
        self.rules_status_var.set(f"已导入 {Path(path).name}（尚未保存到项目）")

    def export_rules(self) -> None:
        text = self.rules_text.get("1.0", "end-1c")
        try:
            parse_headword_filter_rules(text, "规则编辑框")
        except Exception as exc:
            messagebox.showerror("规则无效", str(exc), parent=self); return
        path = filedialog.asksaveasfilename(parent=self, title="导出词头规则", defaultextension=".txt", initialfile=HEADWORD_FILTER_RULES_FILENAME, filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        Path(path).write_text(text.rstrip() + "\n", encoding="utf-8")
        self.rules_status_var.set(f"已导出 {Path(path).name}")

    def _schedule_autosave(self) -> None:
        if not getattr(self, "_autosave_ready", False):
            return
        if hasattr(self, "_settings_save_status_var"):
            self._settings_save_status_var.set("● 有改动，正在自动保存…")
        job = getattr(self, "_autosave_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._autosave_job = self.after(450, self._run_autosave)

    def _run_autosave(self) -> None:
        self._autosave_job = None
        ok = self.save(close=False, show_errors=False)
        if hasattr(self, "_settings_save_status_var"):
            self._settings_save_status_var.set(
                "✓ 已自动保存" if ok else "⚠ 当前输入暂未保存；关闭时会提示需要修正的项目"
            )

    def _validate_settings_now(self) -> bool:
        ok = self.save(close=False, show_errors=True)
        if hasattr(self, "_settings_save_status_var"):
            self._settings_save_status_var.set(
                "✓ 当前设置有效并已保存" if ok else "⚠ 请修正无效设置"
            )
        return ok

    def _close_validated(self) -> None:
        job = getattr(self, "_autosave_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            self._autosave_job = None
        self.save(close=True, show_errors=True)

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
                transform = LayoutTransform(
                    str(getattr(self.parent.settings, "layout_transform", "identity") or "identity")
                )
                canonical_width = transform.canonical_size(self.parent.image.size)[0]
                if (
                    "start_y" in self.vars
                    and str(getattr(self.parent.settings, "profile_header_mode", "auto") or "auto")
                    == "present"
                ):
                    source_y = stored_geometry_to_canonical(
                        int(self.parent.settings.start_y),
                        canonical_width,
                        self.parent.settings,
                    )
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
                    source_y = stored_geometry_to_canonical(
                        int(self.parent.settings.bottom_y),
                        canonical_width,
                        self.parent.settings,
                    )
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
            self.parent.settings.main_entry_font_family = str(self.parent.settings.main_entry_font_family).strip() or "DengXian"
            self.parent.settings.main_entry_font_size = max(5, int(self.parent.settings.main_entry_font_size))
            self.parent.settings.main_entry_width_chars = max(4, int(self.parent.settings.main_entry_width_chars))
            self.parent.settings.main_entry_x_ratio = min(1.25, max(0.0, float(self.parent.settings.main_entry_x_ratio)))
            self.parent.settings.review_entry_font_family = str(self.parent.settings.review_entry_font_family).strip() or "Cambria"
            self.parent.settings.review_entry_font_size = max(6, int(self.parent.settings.review_entry_font_size))
            self.parent.settings.review_entry_vertical_padding = min(30, max(0, int(self.parent.settings.review_entry_vertical_padding)))
            self.parent.settings.review_single_cjk_line_height = min(500, max(0, int(self.parent.settings.review_single_cjk_line_height)))
            self.parent.settings.review_zoom_percent = min(250, max(20, int(self.parent.settings.review_zoom_percent)))
            if not 0 <= int(self.parent.settings.crop_parallel_workers) <= 8:
                raise ValueError("切图并行进程数必须为 0–8；0 表示自动，1 表示串行。")
            if not 1 <= int(self.parent.settings.paddle_band_width_ratio) <= 100:
                raise ValueError("候选带宽比例必须在 1–100 之间；100 即原候选带宽。")
            if int(self.parent.settings.paddle_max_input_side) < 256:
                raise ValueError("OCR输入最大长边必须至少为 256 px。")
            if str(self.parent.settings.paddle_preprocessing) not in {
                "original", "grayscale", "auto_contrast", "binary",
            }:
                raise ValueError("OCR图像预处理必须为 original/grayscale/auto_contrast/binary 之一。")
            if not 10 <= int(self.parent.settings.paddle_separator_roi_width_ratio) <= 100:
                raise ValueError("Y精修横向分析范围必须在 10–100% 之间。")
            if not 1 <= float(self.parent.settings.right_ratio) <= 100:
                raise ValueError("向右比例必须在 1–100% 之间。")
            if self.parent.settings.headword_sort_mode == "custom":
                parse_custom_order(self.parent.settings.headword_custom_order)
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
        # Review zoom is intentionally independent from the main page viewer.
        # It persists per project so a comfortable crop size remains stable even
        # when the main page is repeatedly fitted to width/height.
        self.review_zoom = max(0.20, min(2.5, float(parent.settings.review_zoom_percent) / 100.0))
        self.review_zoom_var = tk.StringVar(value=f"{round(self.review_zoom * 100):d}%")
        # Review typography is deliberately independent from the image zoom.
        # Expose the same persisted font settings directly in the review window
        # so users do not need to return to the detailed-settings dialog.
        self.review_font_family_var = tk.StringVar(value=str(parent.settings.review_entry_font_family or "Cambria"))
        self.review_font_size_var = tk.StringVar(value=str(_review_editor_font_size(parent.settings)))
        self.review_font_bold_var = tk.BooleanVar(value=bool(parent.settings.review_entry_font_bold))
        self.review_font_italic_var = tk.BooleanVar(value=bool(parent.settings.review_entry_font_italic))
        self.review_simplified_font_family_var = tk.StringVar(
            value=str(getattr(parent.settings, "review_simplified_font_family", parent.settings.review_entry_font_family) or "Cambria")
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
        self.review_line_height_var = tk.StringVar(value=str(max(1, int(parent.settings.character_height))))
        self.review_row_padding_var = tk.StringVar(value=str(max(0, int(parent.settings.row_padding))))
        self.review_regular_crop_height_var = tk.StringVar(
            value=str(_effective_review_regular_crop_height(parent.settings))
        )
        self.review_single_cjk_line_height_var = tk.StringVar(
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
        self.digit_map_expanded = tk.BooleanVar(value=False)
        self.accent_panel_expanded = tk.BooleanVar(value=False)
        self.review_right_section_expanded = {
            key: tk.BooleanVar(value=True)
            for key in ("display", "ocr", "network", "reference")
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
        self.review_section_title_font = font.nametofont("TkDefaultFont").copy()
        self.review_section_title_font.configure(weight="bold")
        self._configure_review_styles()
        self._build()
        self.after_idle(self._fit_review_left_pane_to_toolbar)
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
        self.review_line_height_var.trace_add("write", lambda *_args: self._schedule_review_line_height_apply())
        self.review_row_padding_var.trace_add("write", lambda *_args: self._schedule_review_row_padding_apply())
        self.review_regular_crop_height_var.trace_add(
            "write", lambda *_args: self._schedule_review_regular_crop_height_apply()
        )
        self.review_single_cjk_line_height_var.trace_add("write", lambda *_args: self._schedule_review_single_cjk_height_apply())
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
        """Create one flat right-pane section; all sections start expanded."""
        frame = ttk.Frame(parent, padding=(padding, 2), style="PCR.Surface.TFrame")
        frame.pack(fill=fill, expand=expand, pady=pady)
        title_var = tk.StringVar(value=f"▾ {title}")
        toggle = ttk.Label(
            frame, textvariable=title_var, style="PCR.Header.TLabel", cursor="hand2",
        )
        toggle.pack(fill="x")
        toggle.bind(
            "<Button-1>", lambda _event, section_key=key: self._toggle_review_right_section(section_key)
        )
        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(3, 5))
        body = ttk.Frame(frame, style="PCR.Surface.TFrame")
        body.pack(fill="both", expand=True)
        self._review_right_sections[key] = {
            "frame": frame,
            "body": body,
            "title": title,
            "title_var": title_var,
            "expand_when_open": bool(expand),
        }
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
        ttk.Checkbutton(row1, text="数字替换映射", variable=self.replace_digits).pack(side="left", padx=(8, 0))
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

        # Default-collapsed numeric map.
        self.digit_panel = ttk.Frame(
            left, padding=(7, 1, 7, 2), style="PCR.Surface.TFrame"
        )
        self.digit_panel.pack(fill="x")
        self.digit_panel_title = tk.StringVar(value="▸ 数字替换映射")
        self.digit_panel_toggle = ttk.Label(
            self.digit_panel,
            textvariable=self.digit_panel_title,
            style="PCR.SectionTitle.TLabel",
            cursor="hand2",
        )
        self.digit_panel_toggle.pack(fill="x")
        self.digit_panel_toggle.bind(
            "<Button-1>", lambda _event: self._toggle_review_panel("digit")
        )
        self.digit_panel_body = ttk.Frame(
            self.digit_panel, padding=(5, 3), style="PCR.Surface.TFrame"
        )
        for index, digit in enumerate(self.DIGIT_KEYS):
            row = index // 5
            col = (index % 5) * 2
            ttk.Label(self.digit_panel_body, text=f"{digit}→").grid(row=row, column=col, padx=(2, 0), pady=1, sticky="e")
            ttk.Entry(
                self.digit_panel_body, textvariable=self.digit_map_vars[index], width=3, justify="center"
            ).grid(row=row, column=col + 1, padx=(0, 6), pady=1, sticky="w")

        # Default-collapsed grouped character palette.
        self.accent_panel = ttk.Frame(
            left, padding=(7, 0, 7, 4), style="PCR.Surface.TFrame"
        )
        self.accent_panel.pack(fill="x")
        self.accent_panel_title = tk.StringVar(value="▸ 变音字符")
        self.accent_panel_toggle = ttk.Label(
            self.accent_panel,
            textvariable=self.accent_panel_title,
            style="PCR.SectionTitle.TLabel",
            cursor="hand2",
        )
        self.accent_panel_toggle.pack(fill="x")
        self.accent_panel_toggle.bind(
            "<Button-1>", lambda _event: self._toggle_review_panel("accent")
        )
        self.accent_panel_body = ttk.Frame(
            self.accent_panel, padding=(5, 3), style="PCR.Surface.TFrame"
        )
        for group_index, (label, chars) in enumerate(self.ACCENT_GROUPS):
            row = group_index // 2
            base_col = (group_index % 2) * 7
            ttk.Label(self.accent_panel_body, text=label, width=4, anchor="e").grid(
                row=row, column=base_col, padx=((0 if base_col == 0 else 12), 4), pady=1
            )
            for offset, char in enumerate(chars, start=1):
                ttk.Button(
                    self.accent_panel_body, text=char, width=3, command=lambda c=char: self.insert_char(c)
                ).grid(row=row, column=base_col + offset, padx=1, pady=1, sticky="w")

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
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.rows_window, width=e.width))
        for widget in (self.canvas, self.rows):
            widget.bind("<MouseWheel>", self.scroll_rows)
            widget.bind("<Button-4>", lambda e: self.scroll_rows_linux(-1))
            widget.bind("<Button-5>", lambda e: self.scroll_rows_linux(1))

        # Right: every logical block is collapsible; all start expanded.
        review_info = self._review_collapsible_section(
            right, "display", "显示设置", padding=6, fill="x", pady=(0, 6)
        )

        height_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
        height_row.pack(fill="x")
        ttk.Label(height_row, text="单行高：").pack(side="left")
        self.review_line_height_spin = ttk.Spinbox(
            height_row, from_=1, to=500, increment=1, width=5,
            textvariable=self.review_line_height_var, style="PCR.Compact.TSpinbox",
        )
        self.review_line_height_spin.pack(side="left")
        ttk.Label(height_row, text="参考页px").pack(side="left", padx=(2, 9))
        ttk.Label(height_row, text="行间空：").pack(side="left")
        ttk.Spinbox(
            height_row, from_=0, to=200, increment=1, width=4,
            textvariable=self.review_row_padding_var, style="PCR.Compact.TSpinbox",
        ).pack(side="left")
        ttk.Label(height_row, text="参考页px").pack(side="left", padx=(2, 0))

        crop_height_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
        crop_height_row.pack(fill="x", pady=(3, 0))
        ttk.Label(crop_height_row, text="普通词条行切图高：").pack(side="left")
        ttk.Spinbox(
            crop_height_row, from_=1, to=500, increment=1, width=5,
            textvariable=self.review_regular_crop_height_var, style="PCR.Compact.TSpinbox",
        ).pack(side="left")
        ttk.Label(crop_height_row, text="参考页px").pack(side="left", padx=(2, 9))
        ttk.Label(crop_height_row, text="单字行高：").pack(side="left")
        self.review_single_cjk_line_height_spin = ttk.Spinbox(
            crop_height_row, from_=1, to=500, increment=1, width=5,
            textvariable=self.review_single_cjk_line_height_var, style="PCR.Compact.TSpinbox",
        )
        self.review_single_cjk_line_height_spin.pack(side="left")
        ttk.Label(crop_height_row, text="参考页px").pack(side="left", padx=(2, 0))

        zoom_row = ttk.Frame(review_info, style="PCR.Surface.TFrame")
        zoom_row.pack(fill="x")
        ttk.Label(zoom_row, text="词条切图显示大小：").pack(side="left")
        ttk.Button(
            zoom_row, text="−", width=3, command=lambda: self.change_review_zoom(0.8),
            style="PCR.Tool.TButton",
        ).pack(side="left")
        review_zoom_entry = ttk.Entry(
            zoom_row, textvariable=self.review_zoom_var, width=6, justify="center",
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
            zoom_row, text="100%", width=5, command=self.reset_review_zoom,
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
        review_families = tuple(sorted(set(font.families()), key=str.casefold))
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
        self._request_render_rows(focus_index=0)

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
        total = len(self.editors)
        current = self.active_index + 1 if total else 0
        remaining = max(0, total - current)
        self.title(f"词条校对 — {page} — 当前: {current} 剩余: {remaining} 合计: {total}")

    def _close_review(self) -> None:
        try:
            self.save()
        finally:
            if self.parent.review_window is self:
                self.parent.review_window = None
            self._prefetch_closed = True
            self.parent._invalidate_ui_worker(self._review_render_worker_key)
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

    def autosave_commit(self) -> bool:
        """Commit review edits for the shared main-window autosave timer."""
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
        self.parent.settings.review_zoom_percent = round(self.review_zoom * 100)
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
        for entry, var in zip(self._bound_row_entries(), self.vars):
            if entry not in self.parent.entries:
                continue
            entry.word = var.get().strip()
        self._capture_simplified_edits(getattr(self, "_rendered_page_stem", ""))

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
        ordered = self.parent._ordered_entries_reading_order()
        # Only capture against the currently rendered page.  During navigation
        # parent.current_page may already refer to the next page while the old
        # widgets are still being destroyed.
        if self.parent.current_page and self.parent.current_page.stem != stem:
            return
        for i, entry in enumerate(ordered[:len(self.simplified_vars)]):
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
        family = self.review_font_family_var.get().strip() or "Cambria"
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

        spec = _entry_font_spec(family, size, bold, italic)
        measure_font = font.Font(
            family=family, size=size,
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
        family = self.review_simplified_font_family_var.get().strip() or "Cambria"
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

        spec = _entry_font_spec(family, size, bold, italic)
        measure_font = font.Font(
            family=family, size=size,
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

    def _schedule_review_line_height_apply(self) -> None:
        if self._review_line_height_apply_job is not None:
            try:
                self.after_cancel(self._review_line_height_apply_job)
            except tk.TclError:
                pass
        self._review_line_height_apply_job = self.after(160, self._apply_review_line_height_setting)

    def _apply_review_line_height_setting(self) -> None:
        self._review_line_height_apply_job = None
        try:
            line_height = int(float(self.review_line_height_var.get().strip()))
        except (TypeError, ValueError):
            return
        line_height = max(1, min(500, line_height))
        if self.review_line_height_var.get() != str(line_height):
            self.review_line_height_var.set(str(line_height))
            return
        self.parent.settings.character_height = line_height
        # While the project still uses the automatic single-CJK height, keep
        # its visible value synchronized with the shared main-window line height.
        if int(getattr(self.parent.settings, "review_single_cjk_line_height", 0) or 0) <= 0:
            self._syncing_review_height_vars = True
            try:
                self.review_single_cjk_line_height_var.set(
                    str(_effective_review_single_cjk_line_height(self.parent.settings))
                )
            finally:
                self._syncing_review_height_vars = False
        if int(getattr(self.parent.settings, "review_regular_crop_height", 0) or 0) <= 0:
            self._syncing_review_height_vars = True
            try:
                self.review_regular_crop_height_var.set(
                    str(_effective_review_regular_crop_height(self.parent.settings))
                )
            finally:
                self._syncing_review_height_vars = False
        self.parent.sync_quick_settings()
        self.parent.save_settings()
        self._commit_edits()
        active = self.active_index
        self._request_render_rows(focus_index=active)
        self.parent.redraw()

    def _schedule_review_row_padding_apply(self) -> None:
        if self._syncing_review_height_vars:
            return
        if self._review_row_padding_apply_job is not None:
            try:
                self.after_cancel(self._review_row_padding_apply_job)
            except tk.TclError:
                pass
        self._review_row_padding_apply_job = self.after(160, self._apply_review_row_padding_setting)

    def _apply_review_row_padding_setting(self) -> None:
        self._review_row_padding_apply_job = None
        try:
            padding = max(0, min(200, int(float(self.review_row_padding_var.get().strip()))))
        except (TypeError, ValueError):
            return
        if self.review_row_padding_var.get() != str(padding):
            self.review_row_padding_var.set(str(padding))
            return
        self.parent.settings.row_padding = padding
        if int(getattr(self.parent.settings, "review_regular_crop_height", 0) or 0) <= 0:
            self._syncing_review_height_vars = True
            try:
                self.review_regular_crop_height_var.set(
                    str(_effective_review_regular_crop_height(self.parent.settings))
                )
            finally:
                self._syncing_review_height_vars = False
        self.parent.sync_quick_settings()
        self.parent.save_settings()
        self._commit_edits()
        self._request_render_rows(focus_index=self.active_index)
        self.parent.redraw()

    def _schedule_review_regular_crop_height_apply(self) -> None:
        if self._syncing_review_height_vars:
            return
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
            height = max(1, min(500, int(float(self.review_regular_crop_height_var.get().strip()))))
        except (TypeError, ValueError):
            return
        if self.review_regular_crop_height_var.get() != str(height):
            self.review_regular_crop_height_var.set(str(height))
            return
        self.parent.settings.review_regular_crop_height = height
        self.parent.save_settings()
        self._commit_edits()
        self._request_render_rows(focus_index=self.active_index)

    def _schedule_review_single_cjk_height_apply(self) -> None:
        if self._syncing_review_height_vars:
            return
        if self._review_single_cjk_height_apply_job is not None:
            try:
                self.after_cancel(self._review_single_cjk_height_apply_job)
            except tk.TclError:
                pass
        self._review_single_cjk_height_apply_job = self.after(160, self._apply_review_single_cjk_height_setting)

    def _apply_review_single_cjk_height_setting(self) -> None:
        self._review_single_cjk_height_apply_job = None
        try:
            line_height = int(float(self.review_single_cjk_line_height_var.get().strip()))
        except (TypeError, ValueError):
            return
        line_height = max(1, min(500, line_height))
        if self.review_single_cjk_line_height_var.get() != str(line_height):
            self.review_single_cjk_line_height_var.set(str(line_height))
            return
        self.parent.settings.review_single_cjk_line_height = line_height
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
        self.review_zoom = max(0.20, min(2.5, self.review_zoom * factor))
        self.parent.settings.review_zoom_percent = round(self.review_zoom * 100)
        self.review_zoom_var.set(f"{round(self.review_zoom * 100):d}%")
        active = self.active_index
        self._request_render_rows(focus_index=active)

    def apply_review_zoom_text(self, _event=None) -> None:
        try:
            percent = float(self.review_zoom_var.get().strip().rstrip("%"))
        except ValueError:
            self.review_zoom_var.set(f"{round(self.review_zoom * 100):d}%")
            return
        self._commit_edits()
        self.review_zoom = min(2.5, max(0.20, percent / 100.0))
        self.parent.settings.review_zoom_percent = round(self.review_zoom * 100)
        self.review_zoom_var.set(f"{round(self.review_zoom * 100):d}%")
        active = self.active_index
        self._request_render_rows(focus_index=active)

    def reset_review_zoom(self) -> None:
        self._commit_edits()
        self.review_zoom = 1.0
        self.parent.settings.review_zoom_percent = 100
        self.review_zoom_var.set("100%")
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
        review_zoom = max(0.05, min(2.5, float(self.review_zoom)))
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
            crops: list[Image.Image] = []
            for index, entry in enumerate(ordered_snapshot):
                next_entry = (
                    ordered_snapshot[index + 1]
                    if index + 1 < len(ordered_snapshot) else None
                )
                box = _review_line_box(
                    entry, geometry, image, review_settings, next_entry,
                )
                crop = image.crop(box).convert("RGB")
                crop = crop.resize(
                    (
                        max(1, round(crop.width * review_zoom)),
                        max(1, round(crop.height * review_zoom)),
                    ),
                    Image.Resampling.LANCZOS,
                )
                crops.append(crop)
            return page_stem, signature, crops

        def done(payload) -> None:
            try:
                if not self.winfo_exists() or self._prefetch_closed:
                    return
            except tk.TclError:
                return
            result_stem, result_signature, crops = payload
            if not self.parent.current_page or self.parent.current_page.stem != result_stem:
                return
            current_signature = tuple(
                (int(entry.x), int(entry.y), str(entry.word))
                for entry in self.parent._ordered_entries_reading_order()
            )
            if current_signature != result_signature:
                self._request_render_rows(focus_index=self._review_render_focus_index)
                return
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
            review_family = preferred_font_family(
                self,
                (
                    self.parent.settings.review_entry_font_family,
                    "Cambria", "Times New Roman", "Times", "Noto Serif CJK SC", "DejaVu Serif",
                ),
            )
            review_weight = "bold" if self.parent.settings.review_entry_font_bold else "normal"
            review_slant = "italic" if self.parent.settings.review_entry_font_italic else "roman"
            simplified_family = preferred_font_family(
                self,
                (
                    str(getattr(self.parent.settings, "review_simplified_font_family", review_family) or review_family),
                    "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Arial", "DejaVu Sans",
                ),
            )
            simplified_font_size = max(6, int(getattr(self.parent.settings, "review_simplified_font_size", editor_font_size)))
            simplified_bold = bool(getattr(self.parent.settings, "review_simplified_font_bold", self.parent.settings.review_entry_font_bold))
            simplified_italic = bool(getattr(self.parent.settings, "review_simplified_font_italic", self.parent.settings.review_entry_font_italic))
            measure_font = font.Font(
                family=review_family, size=editor_font_size, weight=review_weight, slant=review_slant
            )
            char_px = max(1, measure_font.measure("0"))
            editor_width_chars = max(8, min(140, round(crop.width / char_px)))
            editor_bg = "#b3fddd" if entry.word in words else "#fce5e8"
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
                foreground="#111827",
                disabledforeground="#111827",
                insertbackground="#111827",
                selectbackground="#c7d5e3",
                selectforeground="#111827",
                relief="flat",
                bd=0,
                highlightthickness=0,
            )
            # The light green/pink membership surface needs dark text even while
            # the rest of the proofreading window uses the dark palette.
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
        # Membership status intentionally uses pale green/red backgrounds even
        # in dark mode. Re-apply it after generic theming so the text remains
        # dark and legible instead of inheriting the dark-theme input foreground.
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

    def _ocr_compare_word(self, candidate: dict | None) -> str:
        if not candidate:
            return ""
        key = self.OCR_COMPARE_LABEL_TO_KEY.get(self.review_ocr_compare_var.get(), "fusion")
        if key == "fusion":
            return str(candidate.get("word") or "").strip()
        side = candidate.get(key, {}) or {}
        if not isinstance(side, dict):
            return ""
        return str(side.get("lemma") or "").strip()

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
        color = "#b3fddd" if in_wordslist else "#fce5e8"
        if 0 <= index < len(self.editors):
            try:
                self.editors[index].configure(
                    bg=color,
                    disabledbackground=color,
                    foreground="#111827",
                    disabledforeground="#111827",
                    insertbackground="#111827",
                    selectbackground="#c7d5e3",
                    selectforeground="#111827",
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
                self.parent.settings.review_zoom_percent = round(self.review_zoom * 100)
                return
            if not self.parent._claim_page_for_manual_edit():
                return
        self._commit_edits()
        self.parent.settings.review_zoom_percent = round(self.review_zoom * 100)
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
        review_zoom = max(0.05, min(2.5, float(self.review_zoom)))
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
            crops = None
            if preloaded is not None and preloaded.get("review_key") == self._review_prefetch_key():
                crops = list(preloaded.get("review_crops") or [])
            if crops is None:
                self._request_render_rows(focus_index=0, reset_scroll=True)
            else:
                self.render_rows(preloaded_crops=crops)
                self._reset_rows_scroll_top()
            self._update_title()

class OCRConflictReviewDialog(tk.Toplevel):
    """Review v2.1 multi-OCR decisions and jump directly to the page row."""

    def __init__(self, parent: "PictureCaptureApp") -> None:
        super().__init__(parent)
        self.parent = parent
        self.title("OCR词头冲突复核")
        fit_window_to_work_area(self, 1180, 680, min_width=900, min_height=520)
        self.only_issues = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="")
        self._row_ids: list[str] = []

        outer = ttk.Frame(self, padding=(18, 14, 18, 14))
        outer.pack(fill="both", expand=True)
        _build_modern_dialog_heading(
            outer,
            "OCR 词头冲突复核",
            "集中检查多 OCR 引擎意见不一致或需要人工确认的候选。先选中一行，再决定采用哪个结果。",
        )

        filter_bar = ttk.Frame(outer)
        filter_bar.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            filter_bar,
            text="只显示需要关注的候选",
            variable=self.only_issues,
            command=self.refresh,
        ).pack(side="left")
        ttk.Button(filter_bar, text="刷新", command=self.refresh).pack(
            side="left", padx=(8, 0)
        )

        action_bar = ttk.LabelFrame(
            outer, text="所选候选", padding=(10, 7),
        )
        action_bar.pack(fill="x", pady=(0, 10))
        ttk.Button(
            action_bar, text="选择 / 取消",
            command=self.toggle_selected,
        ).pack(side="left")
        ttk.Button(
            action_bar, text="手工词头…",
            command=self.choose_manual,
        ).pack(side="left", padx=(6, 0))
        ttk.Separator(action_bar, orient="vertical").pack(
            side="left", fill="y", padx=10
        )
        ttk.Button(
            action_bar, text="采用 Paddle",
            command=lambda: self.choose_engine("paddle"),
        ).pack(side="left")
        ttk.Button(
            action_bar, text="采用 Tesseract",
            command=lambda: self.choose_engine("tesseract"),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            action_bar, text="采用 Lens",
            command=lambda: self.choose_engine("lens"),
        ).pack(side="left", padx=(6, 0))

        frame = ttk.Frame(outer)
        frame.pack(fill="both", expand=True)
        cols = (
            "selected", "column", "y", "issues", "paddle", "tesseract",
            "lens", "final", "engine", "reason",
        )
        self.tree = ttk.Treeview(
            frame, columns=cols, show="headings", selectmode="browse"
        )
        labels = {
            "selected": "选中", "column": "栏", "y": "Y", "issues": "问题",
            "paddle": "Paddle", "tesseract": "Tesseract",
            "lens": "Google Lens", "final": "最终词头",
            "engine": "采用", "reason": "决策原因",
        }
        widths = {
            "selected": 55, "column": 45, "y": 70, "issues": 190,
            "paddle": 145, "tesseract": 145, "lens": 145,
            "final": 145, "engine": 85, "reason": 180,
        }
        for key in cols:
            self.tree.heading(key, text=labels[key])
            self.tree.column(key, width=widths[key], anchor="w")
        ybar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self.on_double_click)

        status_bar = ttk.Frame(outer)
        status_bar.pack(fill="x", pady=(8, 0))
        ttk.Label(
            status_bar, textvariable=self.status_var,
            foreground="#666666", anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(status_bar, text="关闭", command=self.destroy).pack(side="right")
        self.refresh()

    def _selected_candidate(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        cid = str(self.tree.item(selection[0], "tags")[0]) if self.tree.item(selection[0], "tags") else ""
        return self.parent.get_review_candidate(cid)

    def refresh(self) -> None:
        self.parent._load_ocr_review_candidates()
        for item in self.tree.get_children(): self.tree.delete(item)
        shown = 0
        for cand in self.parent.ocr_review_candidates:
            issues = list(cand.get("issue_types", []) or [])
            if self.only_issues.get() and not (issues or cand.get("needs_review")):
                continue
            p = cand.get("paddle", {}) or {}; t = cand.get("tesseract", {}) or {}; lens = cand.get("lens", {}) or {}
            values = (
                "✓" if self.parent._candidate_is_selected(cand) else "",
                int(cand.get("column", 0)) + 1,
                cand.get("source_y", ""),
                ",".join(issues),
                p.get("lemma", ""), t.get("lemma", ""), lens.get("lemma", ""), cand.get("word", ""),
                cand.get("final_engine", ""), cand.get("decision_reason", ""),
            )
            cid = str(cand.get("candidate_id", ""))
            self.tree.insert("", "end", values=values, tags=(cid,))
            shown += 1
        self.status_var.set(f"当前页显示 {shown} 条；双击任一行可跳到原图位置。")

    def on_double_click(self, _event=None) -> None:
        cand = self._selected_candidate()
        if cand:
            self.parent.jump_to_review_candidate(cand)

    def toggle_selected(self) -> None:
        cand = self._selected_candidate()
        if not cand: return
        self.parent.set_candidate_selected(cand, not self.parent._candidate_is_selected(cand))
        self.refresh()

    def choose_engine(self, engine: str) -> None:
        cand = self._selected_candidate()
        if not cand: return
        side = cand.get(engine, {}) or {}
        if side.get("y") is None:
            messagebox.showinfo("无此结果", f"该候选没有 {engine} 结果。", parent=self)
            return
        self.parent.apply_candidate_choice(cand, engine, str(side.get("lemma") or ""))
        self.refresh()

    def choose_manual(self) -> None:
        cand = self._selected_candidate()
        if not cand: return
        value = simpledialog.askstring("手工词头", "请输入最终 lemma：", initialvalue=str(cand.get("word", "")), parent=self)
        if value is None: return
        self.parent.apply_candidate_choice(cand, "manual", value.strip())
        self.refresh()



class CropSettingsDialog(tk.Toplevel):
    """Unified crop settings used by both whole-entry and PPP illustration export."""

    CONFIG_NAME = "_CropSettings.json"
    LEGACY_CONFIG_NAME = "_IllustrationCropSettings.json"

    def __init__(self, parent: "PictureCaptureApp", indices: list[int]) -> None:
        super().__init__(parent)
        self.parent = parent
        self.indices = list(indices)
        self.title("切图设置")
        fit_window_to_work_area(self, 780, 560, min_width=700, min_height=500)
        self.transient(parent)
        self.grab_set()
        self.general_top_var = tk.StringVar()
        self.general_bottom_var = tk.StringVar()
        self.entry_left_padding_var = tk.StringVar()
        self.entry_right_padding_var = tk.StringVar()
        self.integrate_illustrations_var = tk.BooleanVar(value=True)
        self.margin_var = tk.StringVar()
        self.workers_var = tk.StringVar()
        self.status_var = tk.StringVar(value="")
        self._load_initial_values()
        self._build()

    @property
    def _config_path(self) -> Path | None:
        if not self.parent.project:
            return None
        return qt_root(self.parent.project.root) / self.CONFIG_NAME

    @property
    def _legacy_config_path(self) -> Path | None:
        if not self.parent.project:
            return None
        return qt_root(self.parent.project.root) / self.LEGACY_CONFIG_NAME

    def _load_initial_values(self) -> None:
        saved = self.parent._load_crop_settings()
        self.general_top_var.set(str(saved.get("general_top_v", self.parent.settings.start_y)))
        default_bottom = self.parent.settings.bottom_y if self.parent.settings.crop_to_bottom_y else 0
        self.general_bottom_var.set(str(saved.get("general_bottom_v", default_bottom)))
        self.entry_left_padding_var.set(str(saved.get("entry_left_padding_u", 0)))
        self.entry_right_padding_var.set(str(saved.get("entry_right_padding_u", 0)))
        self.integrate_illustrations_var.set(bool(saved.get("integrate_illustrations", True)))
        self.margin_var.set(str(saved.get("polygon_margin", 0)))
        self.workers_var.set(str(saved.get("parallel_workers", self.parent.settings.crop_parallel_workers)))
        self._legacy_specials = (
            dict(saved.get("special_pages", {}))
            if isinstance(saved.get("special_pages", {}), dict) else {}
        )

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=(18, 14, 18, 12))
        outer.pack(fill="both", expand=True)
        _build_modern_dialog_heading(
            outer,
            "切图设置",
            "完整切图设置（词条切图 / 插图切图共用）。Section=0 页面使用通用上下边界；Section>0 页面由主界面 Section 边界接管。",
        )

        general = ttk.LabelFrame(
            outer, text="通用切图规则", padding=(12, 10),
        )
        general.pack(fill="x")
        ttk.Label(general, text="主界面页面范围：").grid(row=0, column=0, sticky="w")
        scope = f"{len(self.indices)} 页"
        if self.indices and self.parent.project:
            first = self.parent.project.images[self.indices[0]].stem
            last = self.parent.project.images[self.indices[-1]].stem
            scope += f"（{first} → {last}）"
        ttk.Label(general, text=scope).grid(row=0, column=1, columnspan=4, sticky="w")

        ttk.Label(general, text="一般页切图上边界 V（参考页）：").grid(row=1, column=0, sticky="w", pady=(7, 2))
        ttk.Entry(general, textvariable=self.general_top_var, width=10).grid(row=1, column=1, sticky="w", pady=(7, 2))
        ttk.Label(general, text="一般页切图下边界 V（参考页）：").grid(row=1, column=2, sticky="w", padx=(14, 0), pady=(7, 2))
        ttk.Entry(general, textvariable=self.general_bottom_var, width=10).grid(row=1, column=3, sticky="w", pady=(7, 2))
        ttk.Label(
            general,
            text="单位：参考页规范像素；0 = 页面底部。仅用于 Section=0 页面；Section>0 时以页面 Section 边界为准。",
            foreground="#666666",
        ).grid(row=2, column=0, columnspan=5, sticky="w")

        ttk.Label(general, text="词条 U 负向额外留白：").grid(row=3, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(general, textvariable=self.entry_left_padding_var, width=10).grid(row=3, column=1, sticky="w", pady=(8, 2))
        ttk.Label(general, text="词条 U 正向额外留白：").grid(row=3, column=2, sticky="w", padx=(14, 0), pady=(8, 2))
        ttk.Entry(general, textvariable=self.entry_right_padding_var, width=10).grid(row=3, column=3, sticky="w", pady=(8, 2))
        ttk.Label(
            general,
            text="单位：参考页规范像素；运行时按当前页面分辨率缩放。",
        ).grid(row=4, column=0, columnspan=5, sticky="w")

        ttk.Checkbutton(
            general,
            text="是否综合插图计算切图信息",
            variable=self.integrate_illustrations_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Label(
            general,
            text="关闭后：词条只按自身矩形切图；PPP不扩框/不联合/不参与词条切图顺序，词条内部插图仍自然保留",
            foreground="#666666",
        ).grid(row=5, column=2, columnspan=3, sticky="w", pady=(8, 2))

        ttk.Label(general, text="PPP多边形外扩（参考页）：").grid(row=6, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(general, textvariable=self.margin_var, width=10).grid(row=6, column=1, sticky="w", pady=(8, 2))
        ttk.Label(general, text="参考页像素（只影响插图导出，不改PPP原图坐标）").grid(row=6, column=2, columnspan=3, sticky="w", pady=(8, 2))
        ttk.Label(general, text="并行进程：").grid(row=7, column=0, sticky="w", pady=2)
        ttk.Entry(general, textvariable=self.workers_var, width=10).grid(row=7, column=1, sticky="w", pady=2)
        ttk.Label(general, text="0 = 自动；词条/插图切图共用").grid(row=7, column=2, columnspan=3, sticky="w", pady=2)

        section_info = ttk.LabelFrame(
            outer, text="特殊页面范围", padding=(12, 10),
        )
        section_info.pack(fill="x", pady=(10, 0))
        ttk.Label(
            section_info,
            text="特殊页面请在主界面【六、页面列表】的 Section 列双击设置；Section=1 可直接拖动单一上/下边界，Section≥2 可设置多个阅读区。",
            wraplength=720, justify="left",
        ).pack(anchor="w")
        if self._legacy_specials:
            ttk.Label(
                section_info,
                text=f"检测到 {len(self._legacy_specials)} 个旧版“特殊页面覆盖”。仅在对应页面 Section=0 时继续兼容生效；一旦设置 Section，Section 自动优先。",
                foreground="#8a5a00", wraplength=720, justify="left",
            ).pack(anchor="w", pady=(6, 0))

        bottom = ttk.Frame(self, padding=(18, 0, 18, 12))
        bottom.pack(fill="x")
        ttk.Label(
            bottom, textvariable=self.status_var,
            anchor="w", foreground="#666666",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="关闭", command=self.destroy).pack(side="right")
        ttk.Button(
            bottom, text="保存并关闭", command=self.save_settings
        ).pack(side="right", padx=(0, 6))

    @staticmethod
    def _nonnegative_int(value: str, label: str) -> int:
        try:
            number = int(str(value).strip() or "0")
        except ValueError as exc:
            raise ValueError(f"{label}必须是整数") from exc
        if number < 0:
            raise ValueError(f"{label}不能小于0")
        return number

    def _payload(self) -> dict:
        top = self._nonnegative_int(self.general_top_var.get(), "一般页眉Y")
        bottom = self._nonnegative_int(self.general_bottom_var.get(), "一般底部Y")
        entry_left = self._nonnegative_int(self.entry_left_padding_var.get(), "词条左侧额外留白")
        entry_right = self._nonnegative_int(self.entry_right_padding_var.get(), "词条右侧额外留白")
        margin = self._nonnegative_int(self.margin_var.get(), "PPP多边形外扩")
        workers = self._nonnegative_int(self.workers_var.get(), "并行进程数")
        if workers > 8:
            raise ValueError("并行进程数必须为 0–8")
        if bottom and bottom <= top:
            raise ValueError("一般底部Y必须大于页眉Y，或填0表示图片底部")
        return {
            "version": CROP_SETTINGS_VERSION,
            "coordinate_space": CANONICAL_REFERENCE_SPACE,
            "geometry_reference_width": _geometry_reference_width(self.parent.settings),
            "general_top_v": top,
            "general_bottom_v": bottom,
            "entry_left_padding_u": entry_left,
            "entry_right_padding_u": entry_right,
            "integrate_illustrations": bool(self.integrate_illustrations_var.get()),
            "polygon_margin": margin,
            "parallel_workers": workers,
            # Read-only compatibility for old projects. New per-page ranges live
            # in PageSections sidecars and take precedence during crop planning.
            "special_pages": dict(self._legacy_specials),
        }

    def save_settings(self) -> None:
        try:
            payload = self._payload()
            path = self._config_path
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            # Keep legacy AppSettings mirrors synchronized for backward compatibility,
            # but all user-facing crop controls live exclusively in 【切图设置】.
            self.parent.settings.crop_parallel_workers = int(payload["parallel_workers"])
            self.parent.save_settings()
            if self.parent.crop_preview_var.get():
                self.parent.redraw()
            self.parent.status_var.set("切图设置已保存；Section=0 页面使用通用边界，Section>0 页面使用各自 Section 边界。")
            self.destroy()
        except Exception as exc:
            messagebox.showerror("切图设置无效", str(exc), parent=self)


class OldNewComparisonWindow(tk.Toplevel):
    """Display page-aware differences between an old wordslist and current PDICs."""

    FILTERS = ("全部差异", "新增", "删除", "修改")

    def __init__(self, parent: "PictureCaptureApp", payload: dict[str, object]) -> None:
        super().__init__(parent)
        self.parent = parent
        self.payload = payload
        self.title("新旧比较")
        fit_window_to_work_area(self, 1180, 760, min_width=900, min_height=560)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)

        changes = list(payload.get("changes") or [])
        counts = dict(payload.get("counts") or {})
        page_order = list(payload.get("page_order") or [])
        source = Path(str(payload.get("source") or ""))
        missing_pages = list(payload.get("missing_old_pages") or [])

        outer = ttk.Frame(self, padding=(18, 14, 18, 12))
        outer.pack(fill="both", expand=True)
        _build_modern_dialog_heading(
            outer,
            "新旧比较",
            "将当前 PDIC 合集与旧词表按页面对齐比较。先确认比较来源，再查看差异、保存快照或导出报告。",
        )

        top = ttk.LabelFrame(outer, text="比较来源", padding=(10, 7))
        top.pack(fill="x")
        ttk.Label(top, text="旧词表：").pack(side="left")
        self.source_var = tk.StringVar(value=str(source))
        ttk.Entry(top, textvariable=self.source_var, state="readonly").pack(side="left", fill="x", expand=True, padx=(4, 8))
        ttk.Button(top, text="更换 wordslist…", command=self._choose_source_again).pack(side="left")
        ttk.Button(top, text="重新比较", command=self._refresh_from_parent).pack(side="left", padx=(6, 0))

        first = page_order[0] if page_order else "—"
        last = page_order[-1] if page_order else "—"
        diff_total = sum(int(counts.get(kind, 0) or 0) for kind in ("新增", "删除", "修改"))
        summary = (
            f"范围：{first} → {last}（{len(page_order)} 页）｜"
            f"旧 {int(counts.get('old_rows', 0) or 0)} 行｜新 {int(counts.get('new_rows', 0) or 0)} 行｜"
            f"差异 {diff_total}：新增 {int(counts.get('新增', 0) or 0)}，"
            f"删除 {int(counts.get('删除', 0) or 0)}，修改 {int(counts.get('修改', 0) or 0)}"
        )
        summary_box = ttk.LabelFrame(
            outer, text="比较摘要", padding=(10, 7),
        )
        summary_box.pack(fill="x", pady=(10, 6))
        ttk.Label(summary_box, text=summary, anchor="w").pack(fill="x")
        if missing_pages:
            preview = "、".join(missing_pages[:12])
            suffix = f" 等 {len(missing_pages)} 页" if len(missing_pages) > 12 else ""
            ttk.Label(
                outer,
                text=f"注意：旧词表未出现所选范围中的页面：{preview}{suffix}；这些页的当前 PDIC 词条会显示为新增。",
                foreground="#9a6700",
                wraplength=1120,
            ).pack(fill="x", pady=(0, 6))
        elif not changes:
            ttk.Label(outer, text="所选范围内文本完全一致。", foreground="#2d6a4f").pack(fill="x", pady=(0, 6))

        filter_row = ttk.Frame(outer)
        filter_row.pack(fill="x", pady=(4, 8))
        ttk.Label(filter_row, text="显示：").pack(side="left")
        self.filter_var = tk.StringVar(value="全部差异")
        combo = ttk.Combobox(filter_row, textvariable=self.filter_var, values=self.FILTERS, state="readonly", width=12)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_tree())
        self.visible_count_var = tk.StringVar(value="")
        ttk.Label(filter_row, textvariable=self.visible_count_var, foreground="#666666").pack(side="left", padx=(8, 0))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        diff_tab = ttk.Frame(notebook)
        notebook.add(diff_tab, text="差异")
        cols = ("kind", "page", "old_index", "old", "new_index", "new")
        self.tree = ttk.Treeview(diff_tab, columns=cols, show="headings", selectmode="browse")
        headings = {
            "kind": ("类型", 66, "center"),
            "page": ("页码", 92, "center"),
            "old_index": ("旧行", 58, "center"),
            "old": ("旧词条（wordslist）", 360, "w"),
            "new_index": ("新行", 58, "center"),
            "new": ("新词条（PDIC）", 360, "w"),
        }
        for key, (label, width, anchor_value) in headings.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=45, anchor=anchor_value, stretch=key in {"old", "new"})
        ybar = ttk.Scrollbar(diff_tab, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(diff_tab, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        diff_tab.rowconfigure(0, weight=1)
        diff_tab.columnconfigure(0, weight=1)
        self.refresh_appearance()

        self._add_text_tab(notebook, "当前 PDIC 合集", str(payload.get("new_text") or ""))
        self._add_text_tab(notebook, "旧 wordslist 片段", str(payload.get("old_text") or ""))

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(
            bottom, text="保存当前 PDIC 快照…",
            command=self._save_new_snapshot,
        ).pack(side="left")
        ttk.Button(
            bottom, text="导出差异报告…",
            command=self._save_diff_report,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(bottom, text="关闭", command=self._close).pack(side="right")

        self._refresh_tree()
        self.lift()
        try:
            self.focus_force()
        except tk.TclError:
            pass

    def refresh_appearance(self) -> None:
        if self.parent.appearance_mode == "dark":
            colors = {
                "新增": ("#21483b", "#d8f3dc"),
                "删除": ("#512f35", "#ffd7dc"),
                "修改": ("#51451f", "#ffe9a8"),
            }
        else:
            colors = {
                "新增": ("#e7f6ea", "#111827"),
                "删除": ("#fde8e7", "#111827"),
                "修改": ("#fff4d6", "#111827"),
            }
        for tag, (background, foreground) in colors.items():
            self.tree.tag_configure(tag, background=background, foreground=foreground)
        self.parent._apply_current_appearance(self)

    def _add_text_tab(self, notebook: ttk.Notebook, label: str, content: str) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=label)
        text_widget = tk.Text(frame, wrap="none", undo=False)
        ybar = ttk.Scrollbar(frame, orient="vertical", command=text_widget.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=text_widget.xview)
        text_widget.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        text_widget.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text_widget.insert("1.0", content)
        text_widget.configure(state="disabled")

    def _refresh_tree(self) -> None:
        selected = self.filter_var.get()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        shown = 0
        for index, item in enumerate(list(self.payload.get("changes") or [])):
            kind = str(item.get("kind") or "")
            if selected != "全部差异" and kind != selected:
                continue
            self.tree.insert(
                "", "end", iid=f"d{index}",
                values=(
                    kind,
                    str(item.get("page") or ""),
                    "" if item.get("old_index") is None else item.get("old_index"),
                    str(item.get("old") or ""),
                    "" if item.get("new_index") is None else item.get("new_index"),
                    str(item.get("new") or ""),
                ),
                tags=(kind,),
            )
            shown += 1
        self.visible_count_var.set(f"当前显示 {shown} 条")

    def _save_text_payload(self, *, title: str, initialfile: str, content: str) -> None:
        initialdir = exports_root(self.parent.project.root) if self.parent.project else Path.cwd()
        chosen = filedialog.asksaveasfilename(
            parent=self, title=title, initialdir=str(initialdir), initialfile=initialfile,
            defaultextension=".txt", filetypes=[("文本", "*.txt"), ("全部", "*")],
        )
        if not chosen:
            return
        Path(chosen).write_text(content, encoding="utf-8-sig")
        self.parent.status_var.set(f"已保存：{chosen}")

    def _save_new_snapshot(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._save_text_payload(
            title="保存当前 PDIC 合集",
            initialfile=f"PDIC_words_{stamp}.txt",
            content=str(self.payload.get("new_text") or ""),
        )

    def _save_diff_report(self) -> None:
        rows = ["类型\t页码\t旧行\t旧词条\t新行\t新词条"]
        for item in list(self.payload.get("changes") or []):
            values = [
                str(item.get("kind") or ""), str(item.get("page") or ""),
                "" if item.get("old_index") is None else str(item.get("old_index")),
                str(item.get("old") or "").replace("\t", " "),
                "" if item.get("new_index") is None else str(item.get("new_index")),
                str(item.get("new") or "").replace("\t", " "),
            ]
            rows.append("\t".join(values))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        page_order = [str(item) for item in list(self.payload.get("page_order") or []) if str(item)]
        first = page_order[0] if page_order else "unknown"
        last = page_order[-1] if page_order else first
        scope = first if first == last else f"{first}-{last}"
        # Windows-safe filename while preserving the visible page range.
        scope = re.sub(r'[<>:"/\\|?*]+', "_", scope).strip(" .") or "unknown"
        self._save_text_payload(
            title="保存新旧比较差异报告",
            initialfile=f"words_diff_{scope}_{stamp}.txt",
            content="\n".join(rows) + "\n",
        )

    def _refresh_from_parent(self) -> None:
        self.parent.compare_old_new_selected_scope(force_choose=False)

    def _choose_source_again(self) -> None:
        self.parent.compare_old_new_selected_scope(force_choose=True)

    def _close(self) -> None:
        if getattr(self.parent, "old_new_compare_window", None) is self:
            self.parent.old_new_compare_window = None
        self.destroy()


class PictureCaptureApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Picture Capture v{__version__} — OCR 词头定位")
        fit_window_to_work_area(self, 1440, 900, min_width=1080, min_height=680)
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
        self._pending_section_editor_index: int | None = None
        self.new_polygon: list[tuple[int, int]] = []
        self.overlay_widgets: list[tk.Widget] = []
        self.entry_editor_bindings: list[tuple[tk.Entry, WordEntry]] = []
        self.status_var = tk.StringVar(value="请选择一个词典扫描项目目录")
        self.cursor_status_var = tk.StringVar(value="坐标：—｜缩放 100%｜词条 0")
        self.hide_var = tk.BooleanVar(value=False)
        # polygon_var controls visibility of saved illustration polygons.
        # polygon_draw_var is a separate, explicit editing mode.
        self.polygon_var = tk.BooleanVar(value=False)
        self.polygon_draw_var = tk.BooleanVar(value=False)
        self.crop_preview_var = tk.BooleanVar(value=False)
        self.binary_preview_var = tk.BooleanVar(value=False)
        self.display_mode_var = tk.StringVar(value="原图+标注")
        self._display_mode_syncing = False
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
        self._session_path = self._default_session_state_path()
        self._last_session = self._read_session_state()
        requested_appearance = normalize_appearance_mode(self._last_session.get("appearance_mode"))
        # Build classic-Tk widgets from a stable light baseline. Persisted dark
        # mode is applied only after construction so light<->dark remains fully
        # reversible even for tk.Button/tk.Text/tk.Canvas widgets.
        self.appearance_mode = "light"
        self.dark_mode_var = tk.BooleanVar(value=False)
        self._light_ttk_theme = str(ttk.Style(self).theme_use())
        self._configure_global_appearance()
        self.section_expanded = {
            "normal": True,
            "ocr": True,
            "aux": True,
            "actions": True,
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
        self._build_ui()
        self.bind_class("Toplevel", "<Map>", self._appearance_toplevel_mapped, add="+")
        if requested_appearance == "dark":
            self.set_appearance_mode("dark", persist=False)
        else:
            self.after_idle(lambda: self._apply_current_appearance(self))
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.toggle_autosave()
        self.after_idle(self._maximize_main_window)
        self.after_idle(self._ensure_sidebar_navigation_width)
        self.after_idle(self.restore_last_session)

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
        try:
            self.after_idle(lambda w=widget: self._apply_current_appearance(w))
        except tk.TclError:
            pass

    def _toggle_dark_mode(self) -> None:
        self.set_appearance_mode("dark" if self.dark_mode_var.get() else "light")

    def set_appearance_mode(self, mode: object, *, persist: bool = True) -> None:
        """Switch the whole application appearance without changing project data."""
        normalized = normalize_appearance_mode(mode)
        self.appearance_mode = normalized
        if self.dark_mode_var.get() != (normalized == "dark"):
            self.dark_mode_var.set(normalized == "dark")

        self._configure_global_appearance()
        self._configure_main_workspace_styles()

        # First let the reversible classic-Tk mapper capture/restore the stable
        # light baselines. Only then apply the few surfaces whose desired dark
        # colour is intentionally different from the generic mapping.
        self._apply_current_appearance(self)
        palette = appearance_palette(normalized)
        for name, color_key in (
            ("sidebar_canvas", "bg"),
            ("canvas", "canvas"),
        ):
            widget = self.__dict__.get(name)
            if widget is not None:
                try:
                    widget.configure(bg=palette[color_key])
                except tk.TclError:
                    pass

        review = self.__dict__.get("review_window")
        if review is not None:
            try:
                if review.winfo_exists():
                    review._configure_word_list_appearance()
                    review._configure_review_styles()
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
        self._schedule_page_cell_overlay_refresh()
        if self.image is not None:
            self.redraw()
        if persist:
            self._save_session_state()


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
                "canvas": "#30343b",
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
            padding=(6, 5),
            relief="flat",
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
        self._set_section_expanded(section, not bool(self.section_expanded.get(key, True)))

    def _apply_initial_section_states(self) -> None:
        for key, section in self._collapsible_sections.items():
            self._set_section_expanded(section, bool(self.section_expanded.get(key, True)), persist=False)

    @staticmethod
    def _default_session_state_path() -> Path:
        return user_config_root() / SESSION_STATE_FILENAME

    def _read_session_state(self) -> dict:
        candidates = (self._session_path, *legacy_user_config_files(SESSION_STATE_FILENAME))
        for candidate in candidates:
            try:
                if candidate.exists():
                    raw = json.loads(candidate.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        return raw
            except (OSError, ValueError, TypeError):
                continue
        return {}

    def _save_session_state(self) -> None:
        try:
            self._session_path.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "last_project": str(self.project.root) if self.project else "",
                "last_page": self.current_page.name if self.current_page else "",
                "last_page_index": self.current_index,
                "image_suffix": self.settings.image_suffix if self.project else self.image_suffix_var.get().strip(),
                "page_range": self.page_range_var.get() if hasattr(self, "page_range_var") else "current",
                "page_range_spec": self.page_range_spec_var.get() if hasattr(self, "page_range_spec_var") else "",
                "view_zoom_percent": round(self.view_scale * 100),
                "appearance_mode": self.appearance_mode,
                "section_expanded": dict(self.section_expanded),
            }
            tmp = self._session_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._session_path)
            self._last_session = state
        except OSError:
            # Session restoration is a convenience feature; never block editing
            # because a locked-down Windows profile cannot persist it.
            pass

    def restore_last_session(self) -> None:
        state = self._last_session or {}
        root_text = str(state.get("last_project") or "").strip()
        if not root_text:
            return
        root = Path(root_text).expanduser()
        if not root.is_dir():
            self.status_var.set(f"上次项目不可用：{root}")
            return
        if state.get("page_range") in {"current", "to_end", "specified"}:
            self.page_range_var.set(str(state.get("page_range")))
        self.page_range_spec_var.set(str(state.get("page_range_spec") or ""))
        try:
            zoom_value = state.get("view_zoom_percent")
            try:
                target_view_scale = min(3.0, max(0.08, float(zoom_value) / 100.0)) if zoom_value is not None else None
            except (TypeError, ValueError):
                target_view_scale = None
            self.status_var.set(f"正在后台恢复上次项目：{root}")
            self._load_project(
                root,
                requested_suffix=str(state.get("image_suffix") or "").strip() or None,
                target_page=str(state.get("last_page") or "").strip() or None,
                target_index=state.get("last_page_index"),
                target_view_scale=target_view_scale,
            )
        except Exception as exc:
            self.status_var.set(f"无法恢复上次项目：{exc}")

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
        self.batch_bar = ttk.Frame(self.bottom_stack, padding=(8, 5), style="PC.Batch.TFrame")
        self.batch_text_var = tk.StringVar(value="")
        self.batch_progress_var = tk.DoubleVar(value=0.0)
        ttk.Label(
            self.batch_bar, textvariable=self.batch_text_var, anchor="w", style="PC.Batch.TLabel"
        ).pack(side="left", padx=(0, 8))
        self.batch_progress = ttk.Progressbar(
            self.batch_bar, variable=self.batch_progress_var, maximum=100.0, length=280, mode="determinate"
        )
        self.batch_progress.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.batch_pause_button = ttk.Button(
            self.batch_bar, text="暂停", width=8, command=self._toggle_batch_pause,
            style="PC.Compact.TButton",
        )
        self.batch_pause_button.pack(side="left", padx=(0, 5))
        self.batch_stop_button = ttk.Button(
            self.batch_bar, text="停止", width=8, command=self._request_batch_stop,
            style="PC.Compact.TButton",
        )
        self.batch_stop_button.pack(side="left")

        self.status_bar = ttk.Frame(self.bottom_stack, style="PC.Status.TFrame")
        self.status_bar.pack(side="bottom", fill="x")
        status_bar = self.status_bar
        ttk.Separator(status_bar, orient="horizontal").pack(side="top", fill="x")
        ttk.Label(
            status_bar,
            textvariable=self.status_var,
            anchor="w",
            padding=(8, 4),
            style="PC.Status.TLabel",
        ).pack(side="left", fill="x", expand=True)
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
        # Project actions are outside the scrollable/collapsible sidebar so
        # they remain fixed and visible at the bottom of the left pane.
        self.project_action_bar = ttk.Frame(
            sidebar_host, padding=(6, 5, 5, 6), style="PC.Footer.TFrame"
        )
        self.project_action_bar.pack(side="bottom", fill="x")
        ttk.Separator(self.project_action_bar, orient="horizontal").pack(
            side="top", fill="x", pady=(0, 6)
        )
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

        controls = ttk.Frame(sidebar, style="PC.Sidebar.TFrame")
        controls.grid(row=0, column=0, sticky="ew")
        self._build_quick_settings(controls)

        page_panel = self._section_frame(sidebar, "六、页面列表", padding=6, section_key="pages")
        self.page_panel = page_panel
        page_panel.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        page_panel.columnconfigure(0, weight=1)
        page_panel.rowconfigure(2, weight=1)

        self.page_range_var = tk.StringVar(value="current")
        self.page_range_spec_var = tk.StringVar(value="")
        self.view_zoom_var = tk.StringVar(value="100%")

        range_row = ttk.Frame(page_panel, style="PC.SectionBody.TFrame")
        range_row.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        ttk.Radiobutton(range_row, text="当前页", variable=self.page_range_var, value="current").pack(side="left")
        ttk.Radiobutton(range_row, text="当前至末页", variable=self.page_range_var, value="to_end").pack(side="left", padx=(4, 0))
        ttk.Radiobutton(range_row, text="指定：", variable=self.page_range_var, value="specified").pack(side="left", padx=(4, 0))
        ttk.Entry(
            range_row, textvariable=self.page_range_spec_var, width=14, justify="left"
        ).pack(side="left", fill="x", expand=True)
        size_row = ttk.Frame(page_panel, style="PC.SectionBody.TFrame")
        self.page_size_row = size_row
        size_row.grid(row=1, column=0, sticky="ew", pady=(0, 5))

        zoom_out_button = ttk.Button(
            size_row, text="−", width=3, command=lambda: self.zoom(0.87), style="PC.Tool.TButton"
        )
        zoom_out_button.pack(side="left")
        self._attach_tooltip(zoom_out_button, "缩小显示")
        view_zoom_entry = ttk.Entry(
            size_row, textvariable=self.view_zoom_var, width=6, justify="center",
            style="PC.Compact.TEntry",
        )
        view_zoom_entry.pack(side="left", padx=2)
        view_zoom_entry.bind("<Return>", self.apply_view_zoom_text)
        view_zoom_entry.bind("<FocusOut>", self.apply_view_zoom_text)
        zoom_in_button = ttk.Button(
            size_row, text="+", width=3, command=lambda: self.zoom(1.15), style="PC.Tool.TButton"
        )
        zoom_in_button.pack(side="left")
        self._attach_tooltip(zoom_in_button, "放大显示")
        ttk.Separator(size_row, orient="vertical").pack(side="left", fill="y", padx=4, pady=3)

        fit_width_button = ttk.Button(
            size_row, text="↔", width=3, command=self.fit_page_width, style="PC.Tool.TButton"
        )
        fit_width_button.pack(side="left", padx=(0, 2))
        self._attach_tooltip(fit_width_button, "适合宽度显示")
        fit_height_button = ttk.Button(
            size_row, text="↕", width=3, command=self.fit_page_height, style="PC.Tool.TButton"
        )
        fit_height_button.pack(side="left")
        self._attach_tooltip(fit_height_button, "适合高度显示")
        ttk.Separator(size_row, orient="vertical").pack(side="left", fill="y", padx=4, pady=3)

        previous_bookmark_button = ttk.Button(
            size_row, text="⨇", width=3, command=lambda: self.jump_to_bookmark(-1),
            style="PC.Tool.TButton",
        )
        previous_bookmark_button.pack(side="left", padx=(0, 2))
        self._attach_tooltip(previous_bookmark_button, "跳转到上一书签")
        next_bookmark_button = ttk.Button(
            size_row, text="⨈", width=3, command=lambda: self.jump_to_bookmark(1),
            style="PC.Tool.TButton",
        )
        next_bookmark_button.pack(side="left")
        self._attach_tooltip(next_bookmark_button, "跳转到下一书签")
        ttk.Separator(size_row, orient="vertical").pack(side="left", fill="y", padx=4, pady=3)

        jump_button = ttk.Button(
            size_row, text="跳转", width=6,
            command=self.jump_to_page_spec, style="PC.PageNav.TButton",
        )
        jump_button.pack(side="left", padx=(0, 3))
        self._attach_tooltip(jump_button, "跳转到指定页面的第一个有效页面")
        ttk.Button(
            size_row, text="上一页", width=6,
            command=lambda: self.change_page(-1), style="PC.PageNav.TButton",
        ).pack(side="left", padx=(0, 3))
        ttk.Button(
            size_row, text="下一页", width=6,
            command=lambda: self.change_page(1), style="PC.PageNav.TButton",
        ).pack(side="left")
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
            "bookmark": "书签", "page": "页面", "section": "Section",
            "lined": "画线", "fill_status": "填充状态", "illustrations": "插图",
        }
        self.page_list.heading("bookmark", text="书签", anchor="w")
        self.page_list.heading("page", text="页面", anchor="w")
        self.page_list.heading("section", text="Section", anchor="w")
        self.page_list.heading("lined", text="画线", anchor="w")
        self.page_list.heading("fill_status", text="填充状态", anchor="w")
        self.page_list.heading("illustrations", text="插图", anchor="w")
        self.page_list.heading("bookmark", command=lambda: self._sort_page_list("bookmark"))
        self.page_list.heading("page", command=lambda: self._sort_page_list("page"))
        self.page_list.heading("section", command=lambda: self._sort_page_list("section"))
        self.page_list.heading("lined", command=lambda: self._sort_page_list("lined"))
        self.page_list.heading("fill_status", command=lambda: self._sort_page_list("fill_status"))
        self.page_list.heading("illustrations", command=lambda: self._sort_page_list("illustrations"))
        self.page_list.column("bookmark", width=44, anchor="w", stretch=False)
        self.page_list.column("page", width=180, anchor="w", stretch=False)
        self.page_list.column("section", width=64, anchor="center", stretch=False)
        self.page_list.column("lined", width=68, anchor="w", stretch=False)
        self.page_list.column("fill_status", width=110, anchor="w", stretch=False)
        self.page_list.column("illustrations", width=58, anchor="w", stretch=False)
        self.page_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self._page_list_scroll)
        self.page_list.configure(yscrollcommand=self._page_list_yscroll)
        self.page_list.grid(row=0, column=0, sticky="nsew")
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

        project_row = ttk.Frame(self.project_action_bar, style="PC.Footer.TFrame")
        project_row.pack(fill="x")
        for col in range(4):
            project_row.columnconfigure(col, weight=1, uniform="project-footer-columns")
        for col, (label, command, role) in enumerate((
            ("新建项目", self.open_project, "project"),
            ("已有项目", self.open_recent_project, "project"),
            ("导出训练标记包", self.export_training_package, None),
        )):
            button = (
                self._footer_action_button(project_row, label, command, role=role)
                if role is not None
                else ttk.Button(
                    project_row, text=label, command=command, style="PC.Footer.TButton"
                )
            )
            button.grid(
                row=0, column=col, sticky="ew",
                padx=(0 if col == 0 else 4, 0),
            )

        suffix_cell = ttk.Frame(project_row, style="PC.Footer.TFrame")
        suffix_cell.grid(row=0, column=3, sticky="ew", padx=(4, 0))
        suffix_cell.columnconfigure(1, weight=1)
        ttk.Label(suffix_cell, text="图片后缀：", style="PC.Footer.TLabel").grid(
            row=0, column=0, sticky="e", padx=(0, 2)
        )
        self.image_suffix_var = tk.StringVar(value=self.settings.image_suffix)
        ttk.Entry(
            suffix_cell,
            textvariable=self.image_suffix_var,
            width=7,
            justify="left",
            style="PC.Footer.TEntry",
        ).grid(row=0, column=1, sticky="ew")
        self.image_suffix_var.trace_add("write", lambda *_args: self._quick_parameter_changed())

        parameter_row = ttk.Frame(self.project_action_bar, style="PC.Footer.TFrame")
        parameter_row.pack(fill="x", pady=(4, 0))
        for col in range(4):
            parameter_row.columnconfigure(col, weight=1, uniform="project-footer-columns")
        for col, (label, command, role) in enumerate((
            ("项目Profile", self.open_project_profile, "config"),
            ("设置中心", self.open_settings, "config"),
            ("保存参数", self.save_main_parameters, None),
            ("使用指南", self.show_help_dialog, None),
        )):
            button = (
                self._footer_action_button(parameter_row, label, command, role=role)
                if role is not None
                else ttk.Button(
                    parameter_row, text=label, command=command, style="PC.Footer.TButton"
                )
            )
            button.grid(
                row=0, column=col, sticky="ew",
                padx=(0 if col == 0 else 4, 0),
            )
            if label == "使用指南":
                self._attach_tooltip(button, "打开使用指南：推荐流程、各功能用途、快捷操作与常见排错。")
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
        columns = ["bookmark", "page", "section"]
        if getattr(self, "_page_column_vars", {}).get("lined") is None or self._page_column_vars["lined"].get():
            columns.append("lined")
        if getattr(self, "_page_column_vars", {}).get("illustrations") is None or self._page_column_vars["illustrations"].get():
            columns.append("illustrations")
        if getattr(self, "_page_column_vars", {}).get("fill_status") is None or self._page_column_vars["fill_status"].get():
            columns.append("fill_status")
        self.page_list.configure(displaycolumns=tuple(columns))
        self.after_idle(self._fit_page_list_columns)
        if hasattr(self, "settings"):
            self.settings.page_list_show_lined = "lined" in columns
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

        base = {
            "bookmark": 44, "page": 120, "section": 62,
            "lined": 58, "illustrations": 58, "fill_status": 88,
        }
        weights = {
            "bookmark": 0.4, "page": 4.0, "section": 0.8,
            "lined": 0.8, "illustrations": 0.8, "fill_status": 1.4,
        }
        minimum = [base.get(column, 60) for column in visible]
        base_total = sum(minimum)
        widths: list[int]
        if available <= base_total:
            # Extremely narrow panes still fill exactly; preserve relative widths.
            scale = available / max(1, base_total)
            widths = [max(24, int(round(value * scale))) for value in minimum]
        else:
            extra = available - base_total
            total_weight = sum(weights.get(column, 1.0) for column in visible) or 1.0
            widths = [
                minimum[index] + int(round(extra * weights.get(column, 1.0) / total_weight))
                for index, column in enumerate(visible)
            ]
        # Correct rounding so the visible headings span the full Treeview width.
        widths[-1] += available - sum(widths)
        if widths[-1] < 24:
            deficit = 24 - widths[-1]
            widths[-1] = 24
            for index in range(len(widths) - 2, -1, -1):
                spare = max(0, widths[index] - 24)
                take = min(spare, deficit)
                widths[index] -= take
                deficit -= take
                if deficit <= 0:
                    break
        for column, width in zip(visible, widths):
            self.page_list.column(column, width=max(24, int(width)), stretch=False)

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
        page_var = tk.BooleanVar(value=True)
        menu.add_checkbutton(label="页面", variable=page_var, state="disabled")
        section_var = tk.BooleanVar(value=True)
        menu.add_checkbutton(label="Section", variable=section_var, state="disabled")
        menu.add_checkbutton(
            label="画线", variable=self._page_column_vars["lined"],
            command=lambda: self._apply_page_list_display_columns(save=True),
        )
        menu.add_checkbutton(
            label="填充状态", variable=self._page_column_vars["fill_status"],
            command=lambda: self._apply_page_list_display_columns(save=True),
        )
        menu.add_checkbutton(
            label="插图", variable=self._page_column_vars["illustrations"],
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
            "bookmark": "书签", "page": "页面", "section": "Section",
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
        """Toggle the bookmark cell without changing the active page."""
        if self.page_list.identify_region(event.x, event.y) != "cell":
            return None
        if self.page_list.identify_column(event.x) != "#1":
            return None
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
        if selected:
            self.page_list.selection_remove(*selected)
        self.page_list.selection_set(iid)
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
            ttk.Entry(
                panel,
                textvariable=var,
                width=width,
                justify="left",
                style="PC.Compact.TEntry",
            ).grid(row=row, column=col + 1, sticky="ew", padx=(0, 6), pady=1)

        normal = self._section_frame(
            parent,
            "一、版面参数（规范全分辨率坐标；横排 U/X、V/Y 与原图一致）",
            padding=5,
            section_key="normal",
        )
        normal.pack(fill="x")
        add_field(normal, 0, 0, "分栏数：", "columns", int)
        add_field(normal, 0, 2, "页眉Y(原图)：", "start_y", int)
        add_field(normal, 0, 4, "页尾Y(原图)：", "bottom_y", int)
        add_field(normal, 0, 6, "首栏U：", "manual_x", int)
        add_field(normal, 1, 0, "单栏宽：", "column_width", int)
        add_field(normal, 1, 2, "栏间空：", "gutter", int)
        add_field(normal, 1, 4, "单行高：", "character_height", int)
        add_field(normal, 1, 6, "行间空：", "row_padding", int)
        row = ttk.Frame(normal); row.grid(row=2, column=0, columnspan=8, sticky="ew", pady=(4, 0))
        ttk.Button(
            row, text="检测版面参数", command=self.detect_layout_current,
            style="PC.Compact.TButton",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            row, text="检测版面一致性", command=self.detect_layout_consistency_selected,
            style="PC.Compact.TButton",
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        ttk.Button(
            row, text="普通画线设置（备用）…",
            command=lambda: self.open_settings(initial_tab="normal"),
            style="PC.Compact.TButton",
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        for col in (1, 3, 5, 7): normal.columnconfigure(col, weight=1)

        ocr = self._section_frame(parent, "二、OCR画线（推荐默认）", padding=5, section_key="ocr")
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
        add_field(ocr, 1, 2, "识别带宽%：", "paddle_band_width_ratio", int, 7)
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
        ttk.Label(lens_row, text="参考px@1400").pack(side="left")
        ocr_tools = ttk.Frame(ocr)
        ocr_tools.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(4, 0))
        ttk.Button(
            ocr_tools, text="环境中心", command=self.check_ocr_engines,
            style="PC.Compact.TButton",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            ocr_tools, text="OCR画线设置…",
            command=lambda: self.open_settings(initial_tab="ocr"),
            style="PC.Compact.TButton",
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))
        for col in (1, 3, 5): ocr.columnconfigure(col, weight=1)

        aux = self._section_frame(parent, "三、辅助选项及框线色块", padding=5, section_key="aux")
        aux.pack(fill="x", pady=(4, 0))
        section_var = tk.BooleanVar(value=bool(self.settings.show_page_sections))
        guide_var = tk.BooleanVar(value=bool(self.settings.show_column_guides))
        marker_var = tk.BooleanVar(value=bool(self.settings.show_headword_markers))
        self.quick_bool_vars["show_page_sections"] = section_var
        self.quick_bool_vars["show_column_guides"] = guide_var
        self.quick_bool_vars["show_headword_markers"] = marker_var
        self.quick_color_buttons: dict[str, tk.Button] = {}
        self.quick_color_vars: dict[str, tk.StringVar] = {
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
            return button

        section_row = ttk.Frame(aux); section_row.grid(row=0, column=0, columnspan=4, sticky="ew")
        ttk.Checkbutton(
            section_row, text="显示Section", variable=section_var,
            command=lambda: self._apply_overlay_visibility_toggle("show_page_sections", section_var),
        ).pack(side="left")
        color_button(section_row, "page_section_color")
        ttk.Label(section_row, text="粗细：").pack(side="left")
        section_width_var = tk.StringVar(value=str(self.settings.page_section_width))
        self.quick_vars["page_section_width"] = section_width_var
        self.quick_field_casts["page_section_width"] = int
        ttk.Entry(
            section_row, textvariable=section_width_var, width=4, justify="left"
        ).pack(side="left", padx=(2, 10))

        line_row = ttk.Frame(aux); line_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(2, 0))
        ttk.Checkbutton(line_row, text="栏左垂线", variable=guide_var, command=self._quick_parameter_changed).pack(side="left")
        color_button(line_row, "guide_color")
        ttk.Label(line_row, text="宽度：").pack(side="left")
        guide_value = tk.StringVar(value=str(self.settings.guide_width)); self.quick_vars["guide_width"] = guide_value; self.quick_field_casts["guide_width"] = int
        ttk.Entry(
            line_row, textvariable=guide_value, width=5, justify="left"
        ).pack(side="left", padx=(2, 10))
        ttk.Checkbutton(line_row, text="插图形状：轮廓", variable=self.polygon_var, command=self.redraw).pack(side="left")
        color_button(line_row, "illustration_outline_color")
        ttk.Label(line_row, text="粗细").pack(side="left")
        outline_width_var = tk.StringVar(value=str(self.settings.illustration_outline_width)); self.quick_vars["illustration_outline_width"] = outline_width_var; self.quick_field_casts["illustration_outline_width"] = int
        ttk.Entry(
            line_row, textvariable=outline_width_var, width=4, justify="left"
        ).pack(side="left", padx=(2, 5))
        ttk.Label(line_row, text="背景").pack(side="left")
        color_button(line_row, "illustration_fill_color")

        marker_row = ttk.Frame(aux); marker_row.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(2, 0))
        ttk.Checkbutton(marker_row, text="词头横线", variable=marker_var, command=self._quick_parameter_changed).pack(side="left")
        color_button(marker_row, "headword_marker_color")
        ttk.Label(marker_row, text="高度：").pack(side="left")
        marker_value = tk.StringVar(value=str(self.settings.marker_height)); self.quick_vars["marker_height"] = marker_value; self.quick_field_casts["marker_height"] = int
        ttk.Entry(
            marker_row, textvariable=marker_value, width=5, justify="left"
        ).pack(side="left", padx=(2, 10))
        label_visible_var = tk.BooleanVar(value=bool(self.settings.show_illustration_labels))
        self.quick_bool_vars["show_illustration_labels"] = label_visible_var
        ttk.Checkbutton(marker_row, text="插图标签：外框", variable=label_visible_var).pack(side="left")
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
        family_var = tk.StringVar(value=self.settings.main_entry_font_family); self.quick_vars["main_entry_font_family"] = family_var; self.quick_field_casts["main_entry_font_family"] = str
        ttk.Combobox(font_row, textvariable=family_var, values=tuple(sorted(set(font.families()), key=str.casefold)), width=16).pack(side="left")
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
        label_family_var = tk.StringVar(value=self.settings.illustration_label_font_family); self.quick_vars["illustration_label_font_family"] = label_family_var; self.quick_field_casts["illustration_label_font_family"] = str
        ttk.Combobox(label_font_row, textvariable=label_family_var, values=tuple(sorted(set(font.families()), key=str.casefold)), width=16).pack(side="left")
        ttk.Label(label_font_row, text="字号").pack(side="left", padx=(8, 2))
        label_size_var = tk.StringVar(value=str(self.settings.illustration_label_font_size)); self.quick_vars["illustration_label_font_size"] = label_size_var; self.quick_field_casts["illustration_label_font_size"] = int
        ttk.Entry(
            label_font_row, textvariable=label_size_var, width=5, justify="left"
        ).pack(side="left")
        for label, name in (("粗体", "illustration_label_font_bold"), ("斜体", "illustration_label_font_italic")):
            var = tk.BooleanVar(value=bool(getattr(self.settings, name))); self.quick_bool_vars[name] = var
            ttk.Checkbutton(label_font_row, text=label, variable=var).pack(side="left", padx=(7, 0))

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
            option_row, text="显示切图预览", variable=self.crop_preview_var,
            command=self._toggle_crop_preview,
        ).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            option_row, text="隐藏线框(插图除外)", variable=self.hide_var,
            command=self._toggle_hide_overlays,
        ).pack(side="left", padx=(8, 0))
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

        view_mode_row = ttk.Frame(aux); view_mode_row.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(2, 0))
        ttk.Label(view_mode_row, text="显示模式：").pack(side="left")
        display_mode_combo = ttk.Combobox(
            view_mode_row,
            textvariable=self.display_mode_var,
            values=("原图+标注", "二值+标注", "仅原图", "仅二值", "切图预览"),
            state="readonly",
            width=10,
        )
        display_mode_combo.pack(side="left", padx=(0, 8))
        display_mode_combo.bind("<<ComboboxSelected>>", self._apply_display_mode)
        dark_toggle = ttk.Checkbutton(
            view_mode_row,
            text="深色模式",
            variable=self.dark_mode_var,
            command=self._toggle_dark_mode,
        )
        dark_toggle.pack(side="left")
        self._attach_tooltip(
            dark_toggle,
            "夜间显示：同步深色界面和扫描图夜间预览；不修改原图、OCR、PDIC/PPP 或导出文件。",
        )
        aux.columnconfigure(1, weight=1); aux.columnconfigure(3, weight=1)

        actions = self._section_frame(parent, "四、画线与校对", padding=5, section_key="actions")
        actions.pack(fill="x", pady=(4, 0))
        rows = [
            (("运行普通画线（备用）", self.run_normal_draw_action), ("运行OCR画线（推荐）", self.run_ocr_draw_action)),
            (("清除画线", self.clear_entries), ("清除文本", self.clear_text), ("精修画线", self.refine_lines_selected_scope), ("新旧比较", self.compare_old_new_selected_scope), ("词条校对", self.open_review)),
            (("选择词条文件", self.select_existing_headwords_file), ("填充词条", self.fill_existing_headwords), ("修复排序", self.repair_pdic_order_selected_scope), ("备份PDIC", self.backup_pdic), ("恢复PDIC", self.restore_from_pdic_backup)),
            (("插图识别", self.detect_illustrations_selected_scope), ("编辑插图", self.toggle_polygon_drawing), ("保存当前页", self.save_current_page)),
        ]
        for ri, specs in enumerate(rows):
            row = ttk.Frame(actions)
            row.grid(row=ri, column=0, sticky="ew", pady=(0 if ri == 0 else 3, 0))
            for bi in range(len(specs)):
                row.columnconfigure(bi, weight=1, uniform=f"actions-row-{ri}")
            for bi, (text, command) in enumerate(specs):
                role = (
                    "primary" if text == "运行OCR画线（推荐）"
                    else "success" if text == "保存当前页"
                    else "primary" if text == "词条校对"
                    else "neutral"
                )
                button = self._sidebar_action_button(row, text, command, role=role)
                if text == "运行OCR画线（推荐）":
                    self._attach_tooltip(button, "推荐默认：结合 OCR 文字、位置与结构证据识别词头，并可复用有效缓存。")
                elif text == "运行普通画线（备用）":
                    self._attach_tooltip(button, "备用模式：只依赖栏左几何和墨迹，适合左缘极稳定版式或 OCR 暂不可用时。")
                if text == "编辑插图":
                    self.polygon_draw_button = button
                button.grid(
                    row=0, column=bi, sticky="ew",
                    padx=(0 if bi == 0 else 4, 0),
                )
        actions.columnconfigure(0, weight=1)

        postproduction = self._section_frame(
            parent, "五、后期词典制作", padding=5, section_key="postproduction"
        )
        postproduction.pack(fill="x", pady=(4, 0))
        production_rows = [
            (("切图设置", self.open_crop_settings), ("词条切图", self.split_entries_selected_scope), ("插图切图", self.split_illustrations_selected_scope)),
            (("项目详情", self.open_project_details), ("导出PicDic索引", self.export_picdic_index), ("PicDic制作", self.build_picdic)),
        ]
        for ri, specs in enumerate(production_rows):
            row = ttk.Frame(postproduction)
            row.grid(row=ri, column=0, sticky="ew", pady=(0 if ri == 0 else 3, 0))
            for bi in range(len(specs)):
                row.columnconfigure(bi, weight=1, uniform=f"postproduction-row-{ri}")
            for bi, (text, command) in enumerate(specs):
                self._sidebar_action_button(row, text, command).grid(
                    row=0, column=bi, sticky="ew",
                    padx=(0 if bi == 0 else 4, 0),
                )
        postproduction.columnconfigure(0, weight=1)

        # Main-panel parameters are live: after a short debounce, valid values
        # are applied and persisted without requiring a separate Apply step.
        for _var in list(self.quick_vars.values()) + list(self.quick_bool_vars.values()):
            try:
                _var.trace_add("write", lambda *_args: self._quick_parameter_changed())
            except Exception:
                pass
        self.lens_mode_var.trace_add("write", lambda *_args: self._quick_parameter_changed())
        self._quick_trace_ready = True

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
        """Apply a canvas visibility switch immediately and persist it.

        These switches control widgets created by ``redraw``.  Waiting for the
        general-purpose delayed parameter autosave made a click appear to do
        nothing, and the OCR switches were additionally masked outside the
        proofreading window.  Update the model first so redraw observes the
        new value, then persist through the normal quick-settings path.
        """
        setattr(self.settings, setting_name, bool(variable.get()))
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
        transform = LayoutTransform(
            str(getattr(self.settings, "layout_transform", "identity") or "identity")
        )
        canonical_width, _canonical_height = transform.canonical_size(self.image.size)

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
        return stored_geometry_to_canonical(raw, canonical_width, self.settings)

    def _refresh_quick_coordinate_labels(self) -> None:
        if not hasattr(self, "quick_field_labels"):
            return
        vertical = str(
            getattr(self.settings, "layout_writing_mode", "horizontal-tb") or "horizontal-tb"
        ).startswith("vertical")
        labels = {
            "start_y": "正文起始V：" if vertical else "页眉Y(原图)：",
            "bottom_y": "正文结束V：" if vertical else "页尾Y(原图)：",
            "manual_x": "首栏U：",
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
                    if name in {
                        "start_y", "bottom_y", "manual_x", "column_width",
                        "gutter", "character_height", "row_padding",
                    }:
                        value = self._quick_geometry_value(name)
                    if name == "main_entry_x_ratio":
                        value = round(float(value) * 100)
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
            if hasattr(self, "image_suffix_var"):
                self.image_suffix_var.set(self.settings.image_suffix)
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
                for name in (
                    "start_y", "bottom_y", "manual_x", "column_width",
                    "gutter", "character_height", "row_padding",
                )
                if name in self.quick_vars
            }
            for name, var in self.quick_vars.items():
                value = self.quick_field_casts[name](var.get())
                if name in original_geometry:
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
                    # Persist against the project's explicit canonical
                    # reference page. On the reference page this is identity;
                    # on a differently sized scan it removes current-page scaling.
                    if self.image is not None:
                        transform = LayoutTransform(
                            str(getattr(self.settings, "layout_transform", "identity") or "identity")
                        )
                        canonical_width = transform.canonical_size(self.image.size)[0]
                        value = canonical_geometry_to_stored(
                            value, canonical_width, self.settings,
                        )
                    else:
                        value = int(value)
                if name == "paddle_band_width_ratio" and not 1 <= int(value) <= 100:
                    raise ValueError("候选带宽比例必须在 1–100 之间；100 即原候选带宽。")
                if name == "paddle_separator_safety_px" and not 0 <= int(value) <= 50:
                    raise ValueError("Y精修安全空间必须在 0–50 px 之间。")
                if name == "paddle_separator_roi_width_ratio" and not 10 <= int(value) <= 100:
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
                setattr(self.settings, name, value)
            current_ocr_language = str(getattr(self.settings, "ocr_language", "") or "")
            if current_ocr_language != previous_ocr_language:
                for setting_name, setting_value in language_effective_settings(
                    current_ocr_language, self.settings.layout_writing_mode,
                ).items():
                    if hasattr(self.settings, setting_name):
                        setattr(self.settings, setting_name, setting_value)
            for name, var in self.quick_bool_vars.items(): setattr(self.settings, name, bool(var.get()))
            for name, var in getattr(self, "quick_color_vars", {}).items():
                value = str(var.get()).strip()
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                    raise ValueError(f"{name} 不是有效的 #RRGGBB 颜色")
                setattr(self.settings, name, value.lower())
            if not (self.settings.paddle_use_paddleocr or self.settings.paddle_compare_tesseract or self.settings.paddle_enable_lens):
                raise ValueError("OCR引擎至少需要勾选一个。")
            self.settings.paddle_lens_mode = LENS_MODE_VALUES.get(self.lens_mode_var.get(), self.settings.paddle_lens_mode)
            suffix = self.image_suffix_var.get().strip() if hasattr(self, "image_suffix_var") else self.settings.image_suffix
            if suffix: self.settings.image_suffix = suffix if suffix.startswith(".") else f".{suffix}"
            self.settings.hide_overlays = bool(self.hide_var.get())
            self.settings.polygon_mode = bool(self.polygon_var.get())
            if persist: self.save_settings()
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
        """Save only the artifact owned by the current editing mode.

        Normal/headword-line mode owns ``.pdic`` (separator lines + text-box
        contents). Illustration drawing mode owns ``.ppp``. Merely displaying
        illustration polygons does not switch the save target; only the active
        polygon drawing mode does.
        """
        if not self.project or not self.current_page or self.image is None:
            return None
        if self.polygon_draw_var.get():
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
        """Export saved PDIC pages plus OCR provenance as a reusable training package."""
        if not self.project or self._batch_active:
            if self._batch_active:
                self.status_var.set("已有批量任务正在运行，请结束后再导出训练标记包。")
            return
        if any(
            str(token[0]).startswith("training-cleanup-")
            for token in self._ui_worker_active
        ):
            self.status_var.set("上一轮训练导出仍在清理临时文件；清理完成后再重新导出。")
            return
        try:
            if self.current_page is not None and self.image is not None:
                self._save_current_page_by_mode()
        except Exception as exc:
            self.show_error("导出前保存当前页失败", exc)
            return

        project = self.project
        indices = [i for i, page in enumerate(project.images) if pdic_path(page).exists()]
        if not indices:
            messagebox.showinfo(
                "导出训练标记包",
                "当前项目没有已保存的 .pdic 页面。请先人工确认并保存画线结果。",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "导出训练标记包",
            f"将把 {len(indices)} 个已有 .pdic 的页面作为人工最终标注导出。\n\n"
            "请确认这些页面的画线/词条文本已经人工校对。\n"
            "原图、PDIC/PPP、OCR候选、原始/锚点/精修Y和人工覆盖记录都会一起保存。\n\n继续？",
            parent=self,
        ):
            return

        export_root = training_exports_root(project.root)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base_name = f"{project.root.name}_training_{stamp}"
        staging = export_root / f".{base_name}_building"
        zip_path = export_root / f"{base_name}.zip"
        settings = replace(self.settings)
        page_records: list[dict] = []
        context_files: list[str] = []
        items: list[object] = ["__prepare__"] + list(indices) + ["__finalize__"]

        def cleanup_partial() -> None:
            shutil.rmtree(staging, ignore_errors=True)
            zip_path.with_name(f".{zip_path.name}.tmp").unlink(missing_ok=True)

        def worker(item, _position: int, _total: int):
            try:
                if item == "__prepare__":
                    export_root.mkdir(parents=True, exist_ok=True)
                    cleanup_partial()
                    staging.mkdir(parents=True, exist_ok=True)
                    context_files[:] = copy_project_context(project.root, staging)
                    return {"prepared": True}
                if item == "__finalize__":
                    from . import __version__
                    if self._batch_stop_event.is_set():
                        raise TrainingExportCancelled("训练标记包导出已停止")
                    write_training_manifest(
                        staging,
                        project_name=project.root.name,
                        settings=settings,
                        pages=page_records,
                        context_files=context_files,
                        software_version=__version__,
                    )
                    make_training_zip(
                        staging, zip_path,
                        should_stop=self._batch_stop_event.is_set,
                    )
                    shutil.rmtree(staging, ignore_errors=True)
                    return {"final_zip": str(zip_path)}
                index = int(item)
                record = export_training_page(
                    project.images[index], project.root, settings, staging, index,
                )
                page_records.append(record)
                return record
            except TrainingExportCancelled:
                cleanup_partial()
                return {"cancelled": True}
            except Exception:
                cleanup_partial()
                raise

        def labeler(item) -> str:
            if item == "__prepare__":
                return "准备 staging 并复制项目上下文"
            if item == "__finalize__":
                return "生成 dataset_manifest.json 和 ZIP"
            return project.images[int(item)].name

        def done(_completed, _total, stopped, results, error):
            if error is not None:
                return
            produced = next(
                (str(row.get("final_zip")) for row in reversed(results)
                 if isinstance(row, dict) and row.get("final_zip")),
                "",
            )
            if produced:
                self.status_var.set(f"训练标记包已导出：{Path(produced).name}")
                messagebox.showinfo(
                    "导出训练标记包完成",
                    f"已导出 {len(page_records)} 页。\n\n{produced}",
                    parent=self,
                )
                return
            if stopped:
                self.status_var.set("训练标记包已停止；正在后台清理 staging…")

                def cleanup_worker():
                    cleanup_partial()
                    return True

                def cleanup_done(_result) -> None:
                    if self.project is project:
                        self.status_var.set("训练标记包导出已停止；未生成不完整数据包。")

                self._start_ui_worker(
                    f"training-cleanup-{base_name}",
                    cleanup_worker, cleanup_done,
                    lambda exc, detail: print(detail or str(exc)),
                    wait_on_close=True,
                )

        self._start_batch_task(
            "导出训练标记包", items, worker, done, item_label=labeler,
        )

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
            "\n\n多页结果将取均值并自动填充全部普通版面参数。是否继续？",
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
            for name, value in values.items():
                setattr(self.settings, name, value)
            self.sync_quick_settings(); self.save_settings(); self.redraw()
            suffix = "（任务提前停止，按已完成页面计算）" if stopped else ""
            self.status_var.set(f"版面参数检测完成：{consistency}；其余参数使用稳健中位数{suffix}")

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
            f"将快速扫描当前所选 {len(indices)} 页，检测规范坐标中的页眉横线 V 和正文最左 U。\n\n"
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
            transform_kind = str(
                getattr(settings, "layout_transform", "identity") or "identity"
            )
            transform = LayoutTransform(transform_kind)
            canonical_width, canonical_height = transform.canonical_size(image_size)
            header_ref = (
                canonical_geometry_to_stored(
                    estimate.header_rule_y, canonical_width, settings,
                )
                if estimate.header_rule_y is not None else None
            )
            left_ref = (
                canonical_geometry_to_stored(
                    estimate.body_left_x, canonical_width, settings,
                )
                if estimate.body_left_x is not None else None
            )
            header_source_segment = None
            if estimate.header_rule_y is not None:
                header_source_segment = transform.canonical_marker_to_source(
                    (0, int(estimate.header_rule_y)),
                    (max(0, canonical_width - 1), int(estimate.header_rule_y)),
                    image_size,
                )
            left_source_segment = None
            if estimate.body_left_x is not None:
                left_source_segment = transform.canonical_marker_to_source(
                    (int(estimate.body_left_x), 0),
                    (int(estimate.body_left_x), max(0, canonical_height - 1)),
                    image_size,
                )
            return (
                pages[index].name,
                estimate.header_rule_y,
                estimate.body_left_x,
                header_ref,
                left_ref,
                estimate.is_blank,
                estimate.coordinate_space,
                transform_kind,
                canonical_width,
                header_source_segment,
                left_source_segment,
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
                            "source_coordinate_space",
                            "header_rule_v_canonical_page",
                            "body_left_u_canonical_page",
                            "header_rule_v_reference",
                            "body_left_u_reference",
                            "runtime_coordinate_space",
                            "reference_coordinate_space",
                            "geometry_reference_width",
                            "page_canonical_width",
                            "layout_transform",
                            "status",
                        ))
                        writer.writerows((
                            row[0],
                            segment_text(row[9]),
                            segment_text(row[10]),
                            SOURCE_COORDINATE_SPACE,
                            row[1], row[2], row[3], row[4],
                            row[6], CANONICAL_REFERENCE_SPACE,
                            _geometry_reference_width(settings), row[8], row[7],
                            "blank_skipped" if row[5] else "analyzed",
                        ) for row in rows)

                    analyzed = [row for row in rows if not row[5]]
                    blanks = [row[0] for row in rows if row[5]]
                    header_values = [row[3] for row in analyzed if row[3] is not None]
                    left_values = [row[4] for row in analyzed if row[4] is not None]

                    def summary(values) -> str:
                        return (
                            "无有效值" if not values
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
                        f"页眉横线 V（参考页规范px）：{header_summary}\n"
                        f"正文起始 U（参考页规范px）：{left_summary}\n"
                        f"异常页面：{', '.join(abnormal) or '无'}\n"
                    )
                    temp_report.write_text(report_text, encoding="utf-8-sig")
                    temp_csv.replace(target)
                    try:
                        temp_report.replace(report)
                    except Exception:
                        # Both paths are timestamp-unique. If the second publish
                        # fails, remove the first so callers never see a half-pair.
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
                    f"页眉横线 V（参考页规范px）：{payload['header_summary']}\n"
                    f"正文起始 U（参考页规范px）：{payload['left_summary']}\n"
                    f"异常页面：{abnormal_text}\n\n"
                    "CSV 同时保存原图像素中的边界线段、当前页 canonical 值与统一参考页值；"
                    "统计/异常判断使用参考页坐标。\n"
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
        return self._parse_page_spec(self.page_range_spec_var.get())

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
        """Atomically reserve a pending batch page for foreground manual review.

        A page already being processed cannot be edited. A pending page becomes
        ``manual_locked`` before the UI mutation occurs, guaranteeing that the
        background runner will skip it instead of overwriting the user's PDIC.
        """
        if index is None:
            index = self.current_index
        if not self._batch_active:
            return True
        if not self._batch_foreground_pages:
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
    ) -> bool:
        """Run a multi-page task without blocking Tk.

        Pause and stop are deliberately cooperative: they are checked between
        pages. The current page is always allowed to finish so output files are
        written atomically by the existing processing functions.
        """
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
            self.batch_bar.pack(side="top", fill="x")
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
    ) -> bool:
        """Run page-independent crop jobs in a spawn-safe process pool.

        Only crop/export tasks use this path. Drawing and OCR line detection stay
        on the established sequential batch path so their behaviour is unchanged.
        Pause/stop are cooperative at the dispatch boundary: already-started
        pages finish and are committed, while no new pages are submitted.
        """
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
            return self._start_batch_task(title, items, serial_worker, on_done, item_label)

        self._batch_active = True
        self._batch_parallel = True
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
        # Very fast page tasks (notably page-aware word filling) can enqueue
        # thousands of progress events before Tk gets a turn.  Draining the
        # entire queue in one callback would freeze the UI again, so process a
        # bounded slice and yield back to Tk between slices.
        processed_events = 0
        max_events_per_poll = 120
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

            if processed_events >= max_events_per_poll and not finished:
                break

        if self._batch_active and not finished:
            # If the queue was saturated, continue quickly while still yielding
            # one Tk event cycle; otherwise keep the normal low-overhead cadence.
            delay = 8 if processed_events >= max_events_per_poll else 80
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
        dialog.title("已有项目")
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
            menu = tk.Menu(dialog, tearoff=False)
            self._apply_current_appearance(menu)
            menu.add_command(label="复制项目路径", command=lambda: copy_path(root))
            menu.add_separator()
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
                name_label = ttk.Label(title_row, text=full_name, font=card_title_font)
                name_label.pack(side="left")
                if abbreviation:
                    ttk.Label(title_row, text=f"  ·  {abbreviation}", foreground="#666666").pack(side="left")
                status = tk.Label(
                    title_row, text="可用" if exists else "路径失效", padx=8, pady=2,
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

            def worker():
                rows = load_recent_projects()
                details = [recent_project_details(row) for row in rows]
                covers: dict[str, Image.Image] = {}
                for detail in details:
                    root = Path(str(detail.get("path") or ""))
                    preview_text = str(detail.get("preview_path") or "")
                    preview_path = Path(preview_text) if preview_text else None
                    if not bool(detail.get("exists")) or preview_path is None or not preview_path.is_file():
                        continue
                    try:
                        with Image.open(preview_path) as opened:
                            cover_image = normalize_page_rgb(opened)
                        cover_image.thumbnail((72, 92), Image.Resampling.LANCZOS)
                        backdrop = Image.new("RGB", (76, 96), "#f4f6f8")
                        px = (backdrop.width - cover_image.width) // 2
                        py = (backdrop.height - cover_image.height) // 2
                        backdrop.paste(cover_image, (px, py))
                        covers[str(root)] = backdrop
                    except Exception:
                        continue
                return rows, details, covers

            def done(payload) -> None:
                try:
                    if not dialog.winfo_exists():
                        return
                except tk.TclError:
                    return
                rows, details, covers = payload
                state["rows"] = rows
                state["details"] = details
                state["cover_images"] = covers
                rebuild()

            def failed(exc, detail) -> None:
                if detail:
                    print(detail)
                try:
                    if dialog.winfo_exists():
                        count_var.set(f"读取最近项目失败：{exc}")
                except tk.TclError:
                    pass
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

    def open_project(self) -> None:
        chosen = filedialog.askdirectory(title="选择词典扫描项目目录")
        if not chosen:
            return
        try:
            if is_managed_project(Path(chosen)) and not messagebox.askyesno(
                "既有项目", "此目录已经包含 Picture Capture 项目资料。是否作为既有项目打开？", parent=self,
            ):
                return
            root = Path(chosen)
            existing_project = is_managed_project(root) or has_legacy_project_data(root)
            requested_suffix = None
            if not existing_project and hasattr(self, "image_suffix_var"):
                requested_suffix = self._normalize_suffix(self.image_suffix_var.get())
            self._load_project(
                root,
                requested_suffix=requested_suffix,
                launch_profile_setup=not existing_project,
            )
        except Exception as exc:
            self.show_error("无法打开项目", exc)

    def _load_project(
        self, root: Path, *, requested_suffix: str | None = None,
        target_page: str | None = None, target_index: object = None,
        target_view_scale: float | None = None,
        launch_profile_setup: bool = False,
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
                        page.name, self._page_section_count_text(index),
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
        if getattr(self, "_batch_active", False) and not self._batch_foreground_pages:
            if self.current_index >= 0:
                self._set_page_list_selection(self.current_index, ensure_visible=True)
            self.status_var.set("当前批量任务运行中，暂不允许切换页面；可先暂停/停止。")
            return
        selection = tuple(self.page_list.selection())
        if not selection:
            return
        focused = self.page_list.focus()
        chosen = focused if focused in selection else selection[-1]
        try:
            index = int(chosen)
        except (TypeError, ValueError):
            return
        if index != self.current_index:
            self._request_page_load(index)
        else:
            self._pending_page_index = None
            self._invalidate_ui_worker("page-load")

    def _request_page_load(
        self, index: int, *, reset_zoom: bool = False,
        current_already_saved: bool = False, force: bool = False,
    ) -> bool:
        """Decode/read a target page off-thread, then commit it on the Tk thread."""
        if not self.project or not (0 <= index < len(self.project.images)):
            return False
        if index == self.current_index and self.image is not None and not force:
            self._pending_page_index = None
            self._invalidate_ui_worker("page-load")
            self._set_page_list_selection(index, ensure_visible=True)
            return True
        if self._pending_page_index == index and not force:
            return True
        project = self.project
        page = project.images[index]
        project_root = project.root
        view_scale = float(self.view_scale)
        appearance_mode = self.appearance_mode
        self._pending_page_index = index
        self.status_var.set(f"正在后台加载 {page.name}…")

        def worker():
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            entries = read_pdic(pdic_path(page))
            polygons = read_ppp(ppp_read_path_for_image(page))
            page_sections = read_page_sections(page)
            cache_path = ocr_cache_root(project_root) / f"{page.stem}.json"
            ocr_payload: dict = {}
            if cache_path.exists():
                try:
                    loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        ocr_payload = loaded
                except Exception:
                    ocr_payload = {}
            display_size = (
                max(1, round(image.width * view_scale)),
                max(1, round(image.height * view_scale)),
            )
            display_image = themed_display_image(
                image.resize(display_size, Image.Resampling.LANCZOS),
                appearance_mode,
            )
            return {
                "project_root": str(project_root), "index": index, "image": image,
                "entries": entries, "polygons": polygons, "page_sections": page_sections,
                "ocr_payload": ocr_payload,
                "display_size": display_size, "display_image": display_image,
                "view_scale": view_scale,
            }

        def done(payload) -> None:
            if self.project is not project:
                return
            self._pending_page_index = None
            self.load_page(
                index, reset_zoom=reset_zoom, preloaded=payload,
                skip_current_save=current_already_saved,
            )

        def failed(exc, detail) -> None:
            if detail:
                print(detail)
            if self.project is project:
                self._pending_page_index = None
                self.show_error(f"加载页面失败：{page.name}", exc)

        self._start_ui_worker("page-load", worker, done, failed)
        return True

    def load_page(
        self, index: int, reset_zoom: bool = False, *,
        preloaded: dict | None = None, skip_current_save: bool = False,
    ) -> None:
        if not self.project or not (0 <= index < len(self.project.images)):
            return
        self._pending_page_index = None
        self._invalidate_ui_worker("page-load")
        self._flush_deferred_page_save()
        if self.current_page and self.image and index != self.current_index and not skip_current_save:
            if self._can_save_current_during_batch_navigation():
                self._save_current_page_by_mode()
        self.current_index = index; self.current_page = self.project.images[index]
        use_preloaded = bool(
            preloaded
            and preloaded.get("index") == index
            and preloaded.get("project_root") == str(self.project.root)
            and isinstance(preloaded.get("image"), Image.Image)
        )
        if use_preloaded:
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
                self.image = normalize_page_rgb(opened)
            self.page_sections = read_page_sections(self.current_page)
            self.entries = read_pdic(pdic_path(self.current_page))
            self._sort_entries_reading_order()
            self._restore_entry_ocr_metadata()
            self._load_ocr_review_candidates()
            self.polygons = read_ppp(self._ppp_read_path(self.current_page))
        self.new_polygon = []
        self._section_editing = False
        self._drag_section_boundary = None
        self.update_idletasks()
        if reset_zoom:
            available = max(500, self.canvas.winfo_width() - 24)
            self.view_scale = min(1.0, available / self.image.width)
        # Viewer zoom is presentation-only. Modern geometry is full-resolution
        # canonical and must never be rewritten when the canvas fit changes.
        if (
            not geometry_uses_canonical_pixels(self.settings)
            and (reset_zoom or self.settings.parameter_display_width <= 0)
        ):
            self.settings.parameter_display_width = round(
                self.image.width * self.view_scale
            )
        if self.settings.bottom_y <= 0:
            transform = LayoutTransform(
                str(getattr(self.settings, "layout_transform", "identity") or "identity")
            )
            canonical_width, canonical_height = transform.canonical_size(self.image.size)
            self.settings.bottom_y = canonical_geometry_to_stored(
                canonical_height, canonical_width, self.settings,
            )
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
        # A new page always starts from its top-left corner.  Keep the current
        # zoom level, but never inherit the previous page's scroll position.
        self.canvas.xview_moveto(0.0)
        self.canvas.yview_moveto(0.0)
        self._set_page_list_selection(index, ensure_visible=True)
        quality = self._current_page_quality_text()
        suffix = f"｜{quality}" if quality else ""
        self.status_var.set(f"{self.current_page.name}｜{self.image.width}×{self.image.height}｜{len(self.entries)} 个词条{suffix}")
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
        if getattr(self, "_batch_active", False) and not self._batch_foreground_pages:
            self.status_var.set("当前批量任务运行中，暂不允许切换页面；可先暂停/停止。")
            return False
        if not self.project:
            return False
        base_index = self._pending_page_index if self._pending_page_index is not None else self.current_index
        target = base_index + delta
        if not 0 <= target < len(self.project.images):
            if not current_already_saved and self._can_save_current_during_batch_navigation():
                self._save_current_page_by_mode()
            self.status_var.set("已经到起始页" if target < 0 else "已经到最末页")
            return False
        if preloaded is None and async_allowed:
            return self._request_page_load(
                target, current_already_saved=current_already_saved,
            )
        self.load_page(
            target, preloaded=preloaded, skip_current_save=current_already_saved,
        )
        return True

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

    def _display_mode_from_flags(self) -> str:
        """Return the compact viewer mode represented by the existing flags."""
        if self.crop_preview_var.get():
            return "切图预览"
        binary = bool(self.binary_preview_var.get())
        hidden = bool(self.hide_var.get())
        if hidden:
            return "仅二值" if binary else "仅原图"
        return "二值+标注" if binary else "原图+标注"

    def _sync_display_mode_from_flags(self) -> None:
        if getattr(self, "_display_mode_syncing", False):
            return
        try:
            self._display_mode_syncing = True
            self.display_mode_var.set(self._display_mode_from_flags())
        finally:
            self._display_mode_syncing = False

    def _apply_display_mode(self, _event=None) -> None:
        """Apply one of the practical combinations already supported by the viewer."""
        states = {
            "原图+标注": (False, False, False),
            "二值+标注": (True, False, False),
            "仅原图": (False, True, False),
            "仅二值": (True, True, False),
            "切图预览": (False, False, True),
        }
        mode = str(self.display_mode_var.get() or "原图+标注")
        binary, hidden, crop_preview = states.get(mode, states["原图+标注"])
        previous_binary = bool(self.binary_preview_var.get())
        try:
            self._display_mode_syncing = True
            self.binary_preview_var.set(binary)
            self.hide_var.set(hidden)
            self.crop_preview_var.set(crop_preview)
        finally:
            self._display_mode_syncing = False
        if previous_binary != binary:
            self.photo = None
            self._display_photo_cache_key = None
        if crop_preview:
            self.status_var.set(
                "切图预览：普通编辑线框已临时隐藏；切回其他显示模式即可恢复编辑。"
            )
        self.redraw()

    def _toggle_binary_preview(self) -> None:
        """Invalidate only the canvas bitmap; source/OCR geometry stays intact."""
        self.photo = None
        self._display_photo_cache_key = None
        self._sync_display_mode_from_flags()
        self.redraw()

    def _toggle_hide_overlays(self) -> None:
        """Keep the legacy overlay switch and the page-toolbar mode selector aligned."""
        if self.hide_var.get() and self.crop_preview_var.get():
            self.crop_preview_var.set(False)
        self._sync_display_mode_from_flags()
        self.redraw()

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
            int(getattr(s, "geometry_coordinate_version", 0) or 0),
            str(getattr(s, "geometry_coordinate_space", "") or ""),
            int(getattr(s, "geometry_reference_width", 0) or 0), int(s.columns),
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
        record = {"widgets": [], "canvas_items": [], "index_item": None}
        marker_start, marker_end = geometry.transform.canonical_marker_to_source(
            (canonical_x, entry_v),
            (canonical_x + round(geometry.column_widths[col] * 0.95), entry_v),
            geometry.source_size,
        )

        marker_line_width = max(2, round(self.settings.marker_height * overlay_scale))
        show_markers = (
            self.quick_bool_vars.get("show_headword_markers").get()
            if hasattr(self, "quick_bool_vars") and "show_headword_markers" in self.quick_bool_vars
            else self.settings.show_headword_markers
        )
        if show_markers:
            item = self.canvas.create_line(
                marker_start[0] * self.view_scale,
                marker_start[1] * self.view_scale,
                marker_end[0] * self.view_scale,
                marker_end[1] * self.view_scale,
                fill=self.settings.headword_marker_color,
                width=marker_line_width,
            )
            record["canvas_items"].append(item)

        editor_font_size = effective_main_overlay_font_size(
            self.image.width, self.view_scale, self.settings,
        )
        horizontal = self.settings.layout_writing_mode == "horizontal-tb"
        vertical = not horizontal
        rtl = horizontal and self.settings.layout_text_direction == "rtl"
        main_family = preferred_font_family(
            self.canvas,
            (
                self.settings.main_entry_font_family,
                "DengXian", "PingFang SC", "Noto Sans CJK SC", "Arial", "DejaVu Sans",
            ),
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
            # canonical column first, then transform that point to source space.
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

        # 编号位置与 OCR 菜单无关，必须放在 if ocr_menu is not None 外面。
        if horizontal:
            assert horizontal_index is not None
            index_x, index_y = horizontal_index
            index_anchor = horizontal_index_anchor
        elif self.settings.layout_writing_mode != "horizontal-tb":
            assert vertical_index is not None
            index_x, index_y = vertical_index
            index_anchor = vertical_index_anchor_name
        else:
            raise AssertionError("unreachable overlay layout")

        index_item = self.canvas.create_text(
            index_x,
            index_y,
            text=str(index),
            fill=("#e6edf3" if self.appearance_mode == "dark" else "#222"),
            anchor=index_anchor,
            font=("Arial", 8),
        )

        record["canvas_items"].append(index_item)
        record["index_item"] = index_item

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
        for item in list(record.get("canvas_items") or []):
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

    def _refresh_entry_index_labels(self) -> None:
        for index, entry in enumerate(self._ordered_entries_reading_order()):
            record = self._entry_visuals.get(id(entry))
            item = record.get("index_item") if record else None
            if item is not None:
                try:
                    self.canvas.itemconfigure(item, text=str(index))
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
        """Switch between the editable overlays and the complete crop-plan preview."""
        if self.crop_preview_var.get():
            # Crop-plan preview is a distinct mode; keep it on the original page
            # background and ignore the ordinary overlay-hiding state.
            if self.binary_preview_var.get():
                self.binary_preview_var.set(False)
                self.photo = None
                self._display_photo_cache_key = None
            self.hide_var.set(False)
            self.status_var.set(
                "切图预览：普通编辑线框已临时隐藏；关闭预览即可恢复编辑。"
            )
        self._sync_display_mode_from_flags()
        self.redraw()

    def _current_page_crop_plan(self):
        if self.image is None or self.current_page is None:
            return None
        config = self._load_crop_settings()
        special = config.get("special_pages", {}).get(self.current_page.stem, {}) if isinstance(config.get("special_pages", {}), dict) else {}
        top_y = int(special.get("top_v", config.get("general_top_v", self.settings.start_y)))
        bottom_y = int(special.get("bottom_v", config.get("general_bottom_v", 0)))
        margin = int(config.get("polygon_margin", 0))
        entry_left = int(config.get("entry_left_padding_u", 0))
        entry_right = int(config.get("entry_right_padding_u", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        return build_page_crop_plan(
            self.image, list(self.entries), list(self.polygons), self.settings,
            top_y=top_y, bottom_y=bottom_y, illustration_margin=margin,
            entry_left_padding=entry_left, entry_right_padding=entry_right,
            integrate_illustrations=integrate_illustrations,
            profile_page_index=max(0, int(self.current_index)),
            page_sections=list(self.page_sections),
        )

    def _draw_crop_plan_preview(self) -> None:
        """Overlay the exact entry/PPP crop plan on the main page image."""
        if self.image is None:
            return
        try:
            plan = self._current_page_crop_plan()
        except Exception as exc:
            self.status_var.set(f"切图预览生成失败：{exc}")
            return
        if plan is None:
            return
        scale = self.view_scale
        # Entry pieces: cyan = ordinary crop; green = entry carrying a linked
        # illustration. Orange is used when the rectangle is unioned with a PPP.
        illustrated_entries = {p.entry_ref_index for p in plan.entry_pieces if p.source_mode == "linked_original" and p.entry_ref_index is not None}
        preview_family = preferred_font_family(
            self.canvas,
            (
                self.settings.main_entry_font_family,
                "DengXian", "PingFang SC", "Noto Sans CJK SC", "Arial", "DejaVu Sans",
            ),
        )
        preview_font = _entry_font_spec(
            preview_family,
            effective_main_overlay_font_size(self.image.width, scale, self.settings),
            # helper reads self.settings.main_entry_font_size consistently with editors
            self.settings.main_entry_font_bold,
            self.settings.main_entry_font_italic,
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
            label = f"{piece.word}\n{filename}" if piece.word else filename
            self.canvas.create_text(
                ((x0+x1)/2)*scale, (y0+3)*scale,
                text=label, fill=color, anchor="n", justify="center",
                font=preview_font, tags=("crop-plan",),
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
            self.canvas.create_text((minx+4)*scale,(miny+4)*scale,text=label,fill=color,anchor="nw",font=("Microsoft YaHei",max(7,round(9*scale)),"bold"),tags=("crop-plan",))
        mode = "综合插图" if plan.integrate_illustrations else "仅词条矩形"
        self.status_var.set(
            f"切图预览｜{mode}｜词条切图片段 {len(plan.entry_pieces)}｜随词条PPP {linked_count}｜部分相交 {partial_count}｜独立PPP {standalone_count}"
        )

    def redraw(self) -> None:
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
        photo = self._get_cached_display_photo(size)
        self.canvas.create_image(0, 0, image=photo, anchor="nw", tags="page")
        if self.crop_preview_var.get():
            self._draw_crop_plan_preview()
            self._draw_page_sections(self._get_cached_display_geometry())
            self.canvas.configure(scrollregion=(0, 0, size[0], size[1]))
            if self.cursor_canvas_xy is not None:
                self.draw_cursor_guides(*self.cursor_canvas_xy)
            return
        hidden = self.hide_var.get()
        if not hidden:
            geometry = self._get_cached_display_geometry()
            self._draw_review_entry_highlight(geometry)
            overlay_scale = self.view_scale / parameter_scale(self.image, self.settings)
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
                        self.canvas.create_line(
                            *coords,
                            fill=self.settings.guide_color,
                            width=max(1, round(self.settings.guide_width * overlay_scale)),
                            smooth=True,
                        )
            self._draw_page_sections(geometry)
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
        if hidden and self._section_editing:
            self._draw_page_sections(self._get_cached_display_geometry())
        show_shapes = bool(self.polygon_var.get() or self.polygon_draw_var.get())
        show_labels = bool(self.settings.show_illustration_labels or self.polygon_draw_var.get())
        if show_shapes or show_labels:
            for region_index, region in enumerate(self.polygons):
                coords = [value * self.view_scale for point in region.points for value in point]
                if len(coords) < 6:
                    continue
                polygon_item = None
                if show_shapes:
                    polygon_item = self.canvas.create_polygon(
                        coords, fill=self.settings.illustration_fill_color, stipple="gray50",
                        outline=self.settings.illustration_outline_color,
                        width=max(1, int(self.settings.illustration_outline_width)),
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
                    label_border_width = max(1, int(self.settings.illustration_label_border_width))
                    label_frame = tk.Frame(
                        self.canvas, bg=self.settings.illustration_label_border_color,
                        bd=0, padx=label_border_width, pady=label_border_width,
                    )
                    label_entry = tk.Entry(
                        label_frame, width=18, relief="flat", bd=0, highlightthickness=0,
                        bg=self.settings.illustration_label_fill_color,
                        font=_entry_font_spec(
                            preferred_font_family(
                                self.canvas,
                                (
                                    self.settings.illustration_label_font_family,
                                    "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Arial", "DejaVu Sans",
                                ),
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
        self.canvas.configure(scrollregion=(0, 0, size[0], size[1]))
        if self.cursor_canvas_xy is not None:
            self.draw_cursor_guides(*self.cursor_canvas_xy)

        self._apply_current_appearance(self.canvas)

    def _update_view_zoom_label(self) -> None:
        if hasattr(self, "view_zoom_var"):
            self.view_zoom_var.set(f"{round(self.view_scale * 100):d}%")

    def zoom(self, factor: float) -> None:
        if self.image:
            self.view_scale = min(3.0, max(0.08, self.view_scale * factor))
            self._update_view_zoom_label()
            self.redraw()
            self._set_idle_cursor_status()

    def apply_view_zoom_text(self, _event=None) -> None:
        if not self.image:
            return
        try:
            percent = float(self.view_zoom_var.get().strip().rstrip("%"))
        except ValueError:
            self._update_view_zoom_label()
            return
        self.view_scale = min(3.0, max(0.08, percent / 100.0))
        self._update_view_zoom_label()
        self.redraw()
        self._set_idle_cursor_status()

    def fit_page_width(self) -> None:
        if not self.image:
            return
        self.update_idletasks()
        available = max(120, self.canvas.winfo_width() - 24)
        self.view_scale = min(3.0, max(0.08, available / self.image.width))
        self._update_view_zoom_label()
        self.redraw()
        self._set_idle_cursor_status()
        self.canvas.xview_moveto(0.0)

    def fit_page_height(self) -> None:
        if not self.image:
            return
        self.update_idletasks()
        available = max(120, self.canvas.winfo_height() - 24)
        self.view_scale = min(3.0, max(0.08, available / self.image.height))
        self._update_view_zoom_label()
        self.redraw()
        self._set_idle_cursor_status()
        self.canvas.yview_moveto(0.0)

    def canvas_mousewheel(self, event: tk.Event) -> str:
        step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step * 3, "units")
        return "break"

    def canvas_shift_mousewheel(self, event: tk.Event) -> str:
        step = -1 if event.delta > 0 else 1
        self.canvas.xview_scroll(step * 3, "units")
        return "break"

    def canvas_ctrl_mousewheel(self, event: tk.Event) -> str:
        self.zoom(1.15 if event.delta > 0 else 0.87)
        return "break"

    def canvas_linux_mousewheel(self, event: tk.Event, step: int) -> str:
        if event.state & 0x0004:
            self.zoom(0.87 if step > 0 else 1.15)
        elif event.state & 0x0001:
            self.canvas.xview_scroll(step * 3, "units")
        else:
            self.canvas.yview_scroll(step * 3, "units")
        return "break"

    def original_xy(self, event: tk.Event) -> tuple[int, int]:
        return round(self.canvas.canvasx(event.x) / self.view_scale), round(self.canvas.canvasy(event.y) / self.view_scale)

    def draw_cursor_guides(self, canvas_x: float, canvas_y: float) -> None:
        """Draw the blue dashed crosshair in the current canvas view."""
        self.canvas.delete("cursor-guide")
        if self.image is None or self._section_editing:
            return
        width = self.image.width * self.view_scale
        height = self.image.height * self.view_scale
        if not (0 <= canvas_x < width and 0 <= canvas_y < height):
            return
        style = dict(fill="#1976d2", width=1, dash=(4, 4), tags=("cursor-guide",))
        self.canvas.create_line(0, canvas_y, width, canvas_y, **style)
        self.canvas.create_line(canvas_x, 0, canvas_x, height, **style)
        self.canvas.tag_raise("cursor-guide")

    def canvas_leave(self, _event: tk.Event) -> None:
        self.cursor_canvas_xy = None
        self.canvas.delete("cursor-guide")
        self._set_idle_cursor_status()

    def _set_idle_cursor_status(self) -> None:
        zoom = round(self.view_scale * 100)
        self.cursor_status_var.set(f"坐标：—｜缩放 {zoom}%｜词条 {len(self.entries)}")

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
    def _external_polygon_label_position(
        min_x: float, min_y: float, max_x: float, max_y: float,
        label_width: int, label_height: int, canvas_width: float, canvas_height: float,
        gap: int = 6,
    ) -> tuple[float, float]:
        """Place a PPP label outside the polygon at its upper-right corner.

        Prefer the space immediately to the right of the polygon.  If the
        label would run past the page/canvas right edge, place it just above
        the polygon and right-align it to the polygon's right edge.  Remaining
        edge cases are clamped to the visible page while keeping the label as
        far outside the PPP region as the available space permits.
        """
        label_width = max(1, int(label_width))
        label_height = max(1, int(label_height))
        canvas_width = max(float(canvas_width), 1.0)
        canvas_height = max(float(canvas_height), 1.0)
        margin = 2.0

        # First choice: directly outside the right edge, aligned to the top.
        x = max_x + gap
        y = min_y
        if x + label_width <= canvas_width - margin:
            y = min(max(margin, y), max(margin, canvas_height - label_height - margin))
            return x, y

        # Right edge is tight: stay at the upper-right, but move above the PPP.
        x = max(margin, min(max_x, canvas_width - margin) - label_width)
        y = min_y - gap - label_height
        if y >= margin:
            return x, y

        # Last resort for a PPP touching both the top and right page edges.
        # Prefer the space to its left rather than covering the illustration.
        x = min_x - gap - label_width
        if x >= margin:
            y = min(max(margin, min_y), max(margin, canvas_height - label_height - margin))
            return x, y

        return (
            max(margin, min(canvas_width - label_width - margin, max_x - label_width)),
            max(margin, min(canvas_height - label_height - margin, min_y)),
        )

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
        line_width = max(
            1,
            round(int(getattr(self.settings, "page_section_width", 2) or 2) * overlay_scale),
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

    def toggle_polygon_drawing(self) -> None:
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
            self.status_var.set("插图多边形绘制：左键逐点添加，右键闭合并保存该多边形。")
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
        if self.polygon_draw_var.get():
            existing = self._nearest_polygon_vertex(x, y)
            if existing is not None:
                self._drag_polygon_vertex = existing
                self._drag_polygon_edge = None
                ri, pi = existing
                self.status_var.set(f"正在编辑PPP：拖动插图 {ri + 1} 的顶点 {pi + 1}")
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
        if self.image is None:
            return None
        x, y = self.original_xy(event)
        if self._drag_section_boundary is not None:
            x = max(0, min(self.image.width - 1, x))
            y = max(0, min(self.image.height - 1, y))
            self._drag_page_section_boundary_to(x, y)
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
                if self._section_editing:
                    self.cursor_canvas_xy = None
                    self.canvas.delete("cursor-guide")
                else:
                    self.cursor_canvas_xy = (canvas_x, canvas_y)
                    self.draw_cursor_guides(canvas_x, canvas_y)
                source_x = round(canvas_x / self.view_scale)
                source_y = round(canvas_y / self.view_scale)
                transform = LayoutTransform(
                    str(getattr(self.settings, "layout_transform", "identity") or "identity")
                )
                canonical_u, canonical_v = transform.source_to_canonical_point(
                    source_x, source_y, self.image.size,
                )
                self.cursor_status_var.set(
                    f"原图 X,Y {source_x}, {source_y}｜"
                    f"规范 U,V {canonical_u}, {canonical_v}｜"
                    f"缩放 {round(self.view_scale * 100)}%｜词条 {len(self.entries)}"
                )
            else:
                self.cursor_canvas_xy = None
                self.canvas.delete("cursor-guide")
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
        if in_wordlist:
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

    def _load_ocr_review_candidates(self) -> None:
        self.ocr_review_candidates = []
        path = self._paddle_cache_path()
        if not path or not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.ocr_review_candidates = list(payload.get("review_candidates") or [])
        except Exception:
            self.ocr_review_candidates = []

    def get_review_candidate(self, candidate_id: str) -> dict | None:
        for item in self.ocr_review_candidates:
            if str(item.get("candidate_id", "")) == candidate_id:
                return item
        return None

    def _candidate_is_selected(self, cand: dict) -> bool:
        cid = str(cand.get("candidate_id", ""))
        y = int(cand.get("source_y", -99999))
        x = int(cand.get("source_x", -99999))
        for entry in self.entries:
            if cid and entry.candidate_id == cid:
                return True
            if abs(entry.x - x) <= 12 and abs(entry.y - y) <= max(5, round(self._quick_geometry_value("character_height") * 0.45)):
                return True
        return False

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
        cid = str(cand.get("candidate_id", "")); y = int(cand.get("source_y", -99999)); x = int(cand.get("source_x", -99999))
        for entry in self.entries:
            if cid and entry.candidate_id == cid:
                return entry
            if abs(entry.x - x) <= 12 and abs(entry.y - y) <= max(5, round(self._quick_geometry_value("character_height") * 0.45)):
                return entry
        return None

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
        self._review_entry_highlight_target = None
        self._review_entry_highlight_photo = None
        try:
            self.canvas.delete("proofread-entry-highlight")
        except tk.TclError:
            pass

    def highlight_review_entry(self, entry: WordEntry) -> None:
        """Mirror the focused proofreading row on the main page in pale yellow."""
        if self.image is None or self.current_index < 0:
            return
        self._review_entry_highlight_target = (self.current_index, int(entry.x), int(entry.y))
        self._draw_review_entry_highlight()

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
        if not self.image: return
        y = int(cand.get("source_y", 0))
        # Scroll so the candidate appears around the upper third of the viewport.
        canvas_h = max(1, self.canvas.winfo_height())
        target = max(0.0, y * self.view_scale - canvas_h * 0.30)
        total = max(1.0, self.image.height * self.view_scale)
        self.canvas.yview_moveto(min(1.0, target / total))
        self.canvas.delete("review-highlight")
        geometry = self._get_cached_display_geometry()
        col = max(0, min(len(geometry.column_starts) - 1, int(cand.get("column", 0))))
        x_source = int(cand.get("source_x", 0))
        _u, v = geometry.source_to_canonical(x_source, y)
        canonical_box = (
            geometry.x_at(col, v), v - 5,
            geometry.x_at(col, v) + round(geometry.column_widths[col] * 0.98), v + 18,
        )
        x0, y0, x1, y1 = geometry.transform.canonical_box_to_source(canonical_box, self.image.size)
        self.canvas.create_rectangle(
            x0 * self.view_scale, y0 * self.view_scale,
            x1 * self.view_scale, y1 * self.view_scale,
            outline="#00bcd4", width=3, tags=("review-highlight",),
        )
        self.canvas.tag_raise("review-highlight")

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
        new_values = (bookmark, page.name, section, lined, fill_status, illustrations)
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
            f"{action}尚未启用 {self.settings.layout_transform} 的完整 source/canonical 坐标适配；"
            "为避免写入错误 PDIC 或方向错误的切图，本次操作已取消。"
        )
        self.status_var.set(message)
        return False

    def auto_detect_current(
        self, clicked_x: int | None = None, force_paddle_refresh: bool = False,
    ) -> None:
        """Backward-compatible single-page detection routed through the batch worker."""
        if self._batch_active:
            self.status_var.set("后台画线任务运行中，暂不启动前台自动识别；可进行人工校对。")
            return
        if not self.guard():
            return
        if not self._guard_transformed_geometry("自动画线"):
            return

        project = self.project
        page = self.current_page
        page_index = int(self.current_index)
        settings = replace(self.settings)
        page_sections = list(self.page_sections)
        existing_entries = [replace(entry) for entry in self.entries]
        cache_path = (
            ocr_cache_root(project.root) / f"{page.stem}.json"
            if settings.detection_method == "paddleocr" else None
        )
        filter_path = (
            headword_filter_rules_path(project.root, HEADWORD_FILTER_RULES_FILENAME)
            if settings.detection_method == "paddleocr" else None
        )

        def worker(_item, _position: int, _total: int):
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            detected, geometry = detect_entries(
                image,
                settings,
                paddle_cache_path=cache_path,
                force_paddle_refresh=force_paddle_refresh,
                paddle_filter_rules_path=filter_path,
                profile_page_index=page_index,
                page_sections=page_sections,
            )
            return detected, geometry

        def done(_completed, _total, stopped, results, error):
            if error is not None or stopped or not results:
                return
            if self.project is not project or self.current_page != page:
                return
            detected, geometry = results[-1]
            if clicked_x is None:
                self.entries = list(detected)
            else:
                col = column_index_for_click(clicked_x, geometry)
                merged = [
                    entry for entry in existing_entries
                    if column_index(entry.x, geometry, entry.y) != col
                ]
                merged.extend(
                    entry for entry in detected
                    if column_index(entry.x, geometry, entry.y) == col
                )
                self.entries = merged
            self._sort_entries_reading_order()
            if settings.detection_method == "paddleocr":
                self._load_ocr_review_candidates()
                self._refresh_page_quality_colors()
            self.redraw()
            if settings.detection_method == "paddleocr":
                diag = ocr_cache_root(project.root) / f"{page.stem}_ocr_diagnostics.txt"
                issues = ocr_cache_root(project.root) / f"{page.stem}_issues.tsv"
                quality = self._current_page_quality_text()
                self.status_var.set(
                    f"智能画线完成：{len(self.entries)} 个词条；{quality}；"
                    f"诊断 {diag.name}；复核 {issues.name}"
                )
            else:
                self.status_var.set(
                    f"智能画线完成：检测到 {len(self.entries)} 个词条；可手动增删后保存"
                )

        label = "PaddleOCR 当前页识别" if settings.detection_method == "paddleocr" else "当前页自动画线"
        self._start_batch_task(
            label, [page_index], worker, done,
            item_label=lambda _item: page.name,
            refresh_page_quality=settings.detection_method == "paddleocr",
        )

    def paddle_detect_current(self, force_refresh: bool = False) -> None:
        self.settings.detection_method = "paddleocr"
        self.sync_quick_settings()
        self.save_settings()
        self.auto_detect_current(force_paddle_refresh=force_refresh)

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

    def run_ocr_draw_action(self) -> None:
        if not self.guard() or not self.apply_quick_settings(show_status=False): return
        try: indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc); return
        self.settings.detection_method = "paddleocr"; self.save_settings()
        self._detect_pages(indices, method="paddleocr", force_refresh=self.ocr_refresh_var.get() == "force")

    def run_normal_draw_action(self) -> None:
        if not self.guard() or not self.apply_quick_settings(show_status=False): return
        try: indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc); return
        self.settings.detection_method = "left_edge"; self.save_settings()
        self._detect_pages(indices, method="left_edge", force_refresh=False)

    def run_ocr_draw(self, scope: str, force_refresh: bool) -> None:
        if not self.guard() or not self.apply_quick_settings(show_status=False): return
        self.settings.detection_method = "paddleocr"
        indices = [self.current_index] if scope == "current" else list(range(len(self.project.images)))
        self._detect_pages(indices, method="paddleocr", force_refresh=force_refresh)

    def _detect_pages(self, indices: list[int], *, method: str, force_refresh: bool) -> None:
        if not self.project or not indices:
            self.status_var.set("没有需要处理的页面"); return
        if not self._guard_transformed_geometry("批量画线"):
            return
        label = "OCR画线" if method == "paddleocr" else "普通画线"
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
            cache_path = ocr_cache_root(project.root) / f"{page.stem}.json" if method == "paddleocr" else None
            entries, _geometry = detect_entries(
                image, settings, paddle_cache_path=cache_path,
                force_paddle_refresh=force_refresh,
                paddle_filter_rules_path=filter_path,
                profile_page_index=index,
                page_sections=read_page_sections(page),
            )
            write_pdic(pdic_path(page), entries, image.width, pages_info[index])
            return {"index": int(index), "count": len(entries)}

        def done(completed, total, stopped, results, error):
            if normal_executor is not None:
                normal_executor.shutdown(wait=False, cancel_futures=True)
            if error is not None:
                return
            self.load_page(self.current_index)
            quality_text = ""
            if method == "paddleocr":
                self._refresh_page_quality_colors()
                quality_text = "；页面列表已按 OCR 一致性/质量状态更新"
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
            suffix = "（强制重新识别）" if method == "paddleocr" and force_refresh else ""
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
        if not self.guard(): return
        for entry in self.entries: entry.word = ""
        self.redraw()

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
        # Any explicit/autosave is a hard commit point. Cancel a queued checkbox
        # snapshot and write the newest live page state instead, then commit its
        # manual-selection sidecar in the same foreground save cycle.
        deferred_job = self.__dict__.get("_deferred_save_job")
        if deferred_job is not None:
            try:
                self.after_cancel(deferred_job)
            except tk.TclError:
                pass
        self.__dict__["_deferred_save_job"] = None
        self.__dict__["_deferred_save_snapshot"] = None
        self.__dict__["_deferred_save_page"] = None
        # ReviewWindow edits the shared Entry objects directly. Its save path must
        # not let stale main-canvas Entry widgets overwrite those newer values.
        if sync_editors:
            self._sync_entry_editor_texts()
        self._sort_entries_reading_order()
        write_pdic(pdic_path(self.current_page), self.entries, self.image.width, self.pages_tuple())
        self._flush_pending_manual_override()
        self._refresh_word_fill_check_from_line_count(self.current_index, len(self.entries), persist=True)
        self._update_page_row(self.current_index)
        if not silent: self.status_var.set(f"已保存 {pdic_path(self.current_page).name}")

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
            # Never let a foreground autosave overwrite a PDIC page currently
            # being regenerated by the background batch worker. The current
            # page was explicitly saved before the batch began.
            if self._batch_active:
                if not self._batch_foreground_pages or not self._can_save_current_during_batch_navigation():
                    self.toggle_autosave()
                    return
            if self.project and self.current_page:
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
                write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
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

    def export_text(self) -> None:
        if not self.guard(): return
        export_ocred(qt_root(self.project.root) / f"{self.current_page.stem}.OCRed",
                     [e.word for e in self._ordered_entries_reading_order()])
        self.status_var.set("当前文本已导出")

    def import_text(self) -> None:
        if not self.guard(): return
        path = qt_root(self.project.root) / f"{self.current_page.stem}.OCRed"
        try:
            texts = import_ocred(path)
            if len(texts) != len(self.entries): raise ValueError(f"文本 {len(texts)} 行，画线 {len(self.entries)} 条，数量不一致")
            for entry, text in zip(self._ordered_entries_reading_order(), texts): entry.word = text
            self.redraw(); self.status_var.set("当前文本已导入")
        except Exception as exc: self.show_error("导入失败", exc)

    def split_lines_current(self) -> None:
        """Backward-compatible single-line crop export routed off the Tk thread."""
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再执行单行切图。")
            return
        if not self.guard():
            return
        if not self._guard_transformed_geometry("单行切图"):
            return
        project = self.project
        page = self.current_page
        page_index = int(self.current_index)
        entries = [replace(entry) for entry in self.entries]
        settings = replace(self.settings)
        out_dir = qt_root(project.root) / "PSW"

        def worker(_item, _position: int, _total: int):
            records = split_single_lines(
                page, entries, settings, out_dir,
                profile_page_index=page_index,
            )
            append_crop_log(project.root, records)
            return len(records)

        def done(_completed, _total, stopped, results, error):
            if error is None and not stopped and results:
                self.status_var.set(f"已导出 {int(results[-1] or 0)} 张词条单行图")

        self._start_batch_task(
            "当前页单行切图", [page_index], worker, done,
            item_label=lambda _item: page.name,
        )

    def split_whole_current(self) -> None:
        """Backward-compatible whole-entry crop export routed off the Tk thread."""
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再执行整体切图。")
            return
        if not self.guard():
            return
        if not self._guard_transformed_geometry("整体切图"):
            return

        project = self.project
        page = self.current_page
        page_index = int(self.current_index)
        entries = [replace(entry) for entry in self.entries]
        polygons = list(self.polygons)
        settings = replace(self.settings)
        config = self._load_crop_settings()
        special = config.get("special_pages", {}).get(page.stem, {})
        top_y = int(special.get("top_v", config.get("general_top_v", settings.start_y)))
        bottom_y = int(special.get("bottom_v", config.get("general_bottom_v", 0)))
        entry_left = int(config.get("entry_left_padding_u", 0))
        entry_right = int(config.get("entry_right_padding_u", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        out_dir = qt_root(project.root) / "PWW"

        def worker(_item, _position: int, _total: int):
            records = split_whole_entries(
                page, entries, settings, out_dir,
                top_y=top_y, bottom_y=bottom_y, polygons=polygons,
                entry_left_padding=entry_left,
                entry_right_padding=entry_right,
                integrate_illustrations=integrate_illustrations,
                profile_page_index=page_index,
            )
            append_crop_log(project.root, records)
            return len(records)

        def done(_completed, _total, stopped, results, error):
            if error is None and not stopped and results:
                self.status_var.set(f"已导出 {int(results[-1] or 0)} 张词条整体图")

        self._start_batch_task(
            "当前页整体切图", [page_index], worker, done,
            item_label=lambda _item: page.name,
        )

    def _crop_settings_defaults(self) -> dict:
        default_bottom = self.settings.bottom_y if self.settings.crop_to_bottom_y else 0
        return {
            "version": CROP_SETTINGS_VERSION,
            "coordinate_space": CANONICAL_REFERENCE_SPACE,
            "geometry_reference_width": _geometry_reference_width(self.settings),
            "general_top_v": int(self.settings.start_y),
            "general_bottom_v": int(default_bottom),
            "entry_left_padding_u": 0,
            "entry_right_padding_u": 0,
            "integrate_illustrations": True,
            "polygon_margin": 0,
            "parallel_workers": int(self.settings.crop_parallel_workers),
            "special_pages": {},
        }

    def _load_crop_settings(self) -> dict:
        if not self.project:
            return self._crop_settings_defaults()
        new_path = qt_root(self.project.root) / CropSettingsDialog.CONFIG_NAME
        legacy_path = qt_root(self.project.root) / CropSettingsDialog.LEGACY_CONFIG_NAME
        path = new_path if new_path.exists() else legacy_path
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
        if not self.project or not self.current_page or self.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
            return
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再修改切图设置。")
            return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc); return
        if not indices:
            indices = [self.current_index]
        self._sync_polygon_label_texts()
        write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
        CropSettingsDialog(self, indices)

    def split_entries_selected_scope(self) -> None:
        if not self.guard(): return
        try: indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc); return
        self.save_pdic(silent=True)
        project = self.project
        settings = replace(self.settings)
        config = self._load_crop_settings()
        out_dir = qt_root(project.root) / "PWW"
        general_top = int(config.get("general_top_v", settings.start_y))
        general_bottom = int(config.get("general_bottom_v", 0))
        entry_left = int(config.get("entry_left_padding_u", 0))
        entry_right = int(config.get("entry_right_padding_u", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        specials = config.get("special_pages", {}) if isinstance(config.get("special_pages", {}), dict) else {}
        workers = int(config.get("parallel_workers", settings.crop_parallel_workers))

        def job_builder(index: int, _position: int, _total: int):
            page = project.images[index]
            special = specials.get(page.stem, {}) if isinstance(specials.get(page.stem, {}), dict) else {}
            top_y = int(special.get("top_v", general_top)); bottom_y = int(special.get("bottom_v", general_bottom))
            return (
                str(page), str(pdic_path(page)), settings, str(out_dir), top_y, bottom_y,
                str(self._ppp_read_path(page)), entry_left, entry_right, integrate_illustrations,
                index,
            )

        def consume_result(_index: int, records):
            append_crop_log(project.root, records); return len(records)

        def done(completed, total_pages, stopped, results, error):
            if error is not None: return
            count = sum(int(v or 0) for v in results)
            if stopped: self.status_var.set(f"词条切图已停止：完成 {completed}/{total_pages} 页，共导出 {count} 张")
            else: self.status_var.set(f"词条切图完成：{completed} 页，共 {count} 张")

        self._start_parallel_batch_task(
            "词条切图", indices, split_whole_entries_job, job_builder, consume_result, done,
            item_label=lambda i: project.images[i].name, max_workers=workers,
        )

    def detect_illustrations_selected_scope(self) -> None:
        """Automatically detect illustrations on the selected page range and save PPP polygons."""
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再执行插图识别。")
            return
        if not self.project or not self.current_page or self.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
            return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc)
            return
        if not indices:
            return
        # Persist the current foreground polygon edits before the worker sees it.
        write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
        first = self.project.images[indices[0]].name
        last = self.project.images[indices[-1]].name
        if not messagebox.askyesno(
            "插图识别",
            f"将在所选范围自动识别插图并写入 PPP：\n{first} → {last}（共 {len(indices)} 页）\n\n"
            "人工绘制的 PPP 多边形会保留；再次识别只替换此前自动生成的 AUTO 区域。\n"
            "识别结果可继续用“绘制插图多边形”手工修正。\n\n开始识别？",
            parent=self,
        ):
            return
        project = self.project
        settings = replace(self.settings)

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            return detect_illustrations_job(str(page), settings, index)

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            auto_count = sum(int((r or {}).get("auto", 0)) for r in results)
            if stopped:
                self.status_var.set(
                    f"插图识别已停止：完成 {completed}/{total_pages} 页，自动识别 {auto_count} 个插图区域"
                )
            else:
                self.status_var.set(
                    f"插图识别完成：{completed} 页，自动识别 {auto_count} 个插图区域；人工 PPP 已保留"
                )
            if self.current_index in indices and self.current_page is not None:
                self.polygons = read_ppp(self._ppp_read_path(self.current_page))
                self._update_page_row(self.current_index)
                self.polygon_var.set(True)
                self.redraw()

        self._start_batch_task(
            "插图识别", indices, worker, done,
            item_label=lambda i: project.images[i].name,
            foreground_page_edit=True, page_indexer=lambda i: int(i),
        )

    def split_illustrations_selected_scope(self) -> None:
        """Export PPP illustrations immediately using the shared 切图设置 snapshot."""
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再执行插图切图。")
            return
        if not self.project or not self.current_page or self.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
            return
        try: indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc); return
        if not indices: return
        self._sync_polygon_label_texts()
        write_ppp(self._ppp_write_path(self.current_page), self.polygons, self.current_page.stem)
        self._start_illustration_crop(indices, self._load_crop_settings())

    def _start_illustration_crop(self, indices: list[int], config: dict) -> None:
        """Start PPP illustration export from the shared crop-settings snapshot."""
        if not self.project or self._batch_active:
            if self._batch_active:
                self.status_var.set("已有批量任务正在运行，未启动插图切图。")
            return
        project = self.project
        settings = replace(self.settings)
        out_dir = qt_root(project.root) / "PIC"
        general_top = int(config.get("general_top_v", settings.start_y))
        general_bottom = int(config.get("general_bottom_v", 0))
        margin = int(config.get("polygon_margin", 0))
        entry_left = int(config.get("entry_left_padding_u", 0))
        entry_right = int(config.get("entry_right_padding_u", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        specials = config.get("special_pages", {}) if isinstance(config.get("special_pages", {}), dict) else {}
        workers = int(config.get("parallel_workers", settings.crop_parallel_workers))

        def job_builder(index: int, _position: int, _total: int):
            page = project.images[index]
            special = specials.get(page.stem, {}) if isinstance(specials.get(page.stem, {}), dict) else {}
            top_y = int(special.get("top_v", general_top))
            bottom_y = int(special.get("bottom_v", general_bottom))
            return (
                str(page), str(self._ppp_read_path(page)), str(out_dir), settings,
                top_y, bottom_y, margin, str(pdic_path(page)), entry_left, entry_right, integrate_illustrations,
                index,
            )

        def consume_result(_index: int, result):
            records = list(getattr(result, "records", []) or [])
            events = list(getattr(result, "events", []) or [])
            append_crop_log(project.root, records)
            append_illustration_crop_log(project.root, events)
            return len(records)

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            count = sum(int(v or 0) for v in results)
            if stopped:
                self.status_var.set(f"插图切图已停止：完成 {completed}/{total_pages} 页，共导出 {count} 张")
            else:
                self.status_var.set(f"插图切图完成：{completed} 页，共 {count} 张")

        self._start_parallel_batch_task(
            "插图切图", indices, split_illustrations_job, job_builder, consume_result, done,
            item_label=lambda i: project.images[i].name,
            max_workers=workers,
        )

    def build_picdic(self) -> None:
        if not self.guard():
            return
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再制作 PicDic。")
            return
        try:
            self.save_pdic(silent=True)
        except Exception as exc:
            self.show_error("PicDic 制作准备失败", exc)
            return
        root = self.project.root
        language = self.settings.ocr_language

        def worker(_item, _position: int, _total: int):
            try:
                return build_picdic_package(
                    root, language, should_stop=self._batch_stop_event.is_set,
                )
            except PicDicBuildCancelled:
                return None

        def done(_completed, _total, stopped, results, error):
            if error is not None or stopped or not results:
                return
            dsl, archive, words, images = results[-1]
            self.status_var.set(f"PicDic 制作完成：{words} 个词头，{images} 张图片")
            messagebox.showinfo(
                "PicDic 制作完成",
                f"词头：{words}\n图片：{images}\n\nDSL：{dsl.name}\n图片包：{archive.name}\n目录：{dsl.parent}",
                parent=self,
            )

        self._start_batch_task(
            "PicDic 制作", [root], worker, done,
            item_label=lambda _item: "生成 DSL 与图片包", refresh_page_quality=False,
        )

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
        if not self.guard():
            return
        self.save_pdic(silent=True)
        title = "所有词头顺序核对" if all_pages else "当前页词头顺序核对"

        if all_pages:
            project = self.project
            pages = list(project.images)
            indices = list(range(len(pages)))
            sort_mode = getattr(self.settings, "headword_sort_mode", "auto")
            language = getattr(self.settings, "ocr_language", "eng")
            custom_order = getattr(self.settings, "headword_custom_order", LATIN_ORDER)
            fold_accents = getattr(self.settings, "headword_custom_fold_accents", True)
            rule = profile_label(sort_mode, language)

            def worker(index: int, _position: int, _total: int):
                page = pages[index]
                rows: list[tuple[str, str, tuple, str]] = []
                for entry in read_pdic(pdic_path(page)):
                    word = entry.word.strip()
                    if not word:
                        continue
                    rows.append((
                        page.name,
                        word,
                        collation_key(
                            word, sort_mode, language, custom_order, fold_accents,
                        ),
                        display_key(
                            word, sort_mode, language, custom_order, fold_accents,
                        ),
                    ))
                return rows

            def done(completed, total_pages, stopped, results, error):
                if error is not None:
                    return
                page_results = list(results)
                self.status_var.set(
                    f"词头读取完成 {completed}/{total_pages} 页；正在后台汇总排序…"
                )

                def finalize():
                    sequence = [
                        row
                        for page_rows in page_results
                        if isinstance(page_rows, list)
                        for row in page_rows
                    ]
                    if len(sequence) < 2:
                        return {
                            "count": len(sequence), "inversions": 0,
                            "mismatches": 0, "rule": rule, "report": "",
                            "stopped": bool(stopped), "completed": completed,
                            "total": total_pages,
                        }
                    inversions: list[
                        tuple[
                            tuple[str, str, tuple, str],
                            tuple[str, str, tuple, str],
                        ]
                    ] = []
                    for i in range(1, len(sequence)):
                        if sequence[i][2] < sequence[i - 1][2]:
                            inversions.append((sequence[i - 1], sequence[i]))
                    expected = sorted(sequence, key=lambda item: item[2])
                    mismatches = sum(
                        1 for actual, wanted in zip(sequence, expected)
                        if actual[:3] != wanted[:3]
                    )
                    lines = [
                        f"共核对 {len(sequence)} 个非空词头；发现 {len(inversions)} 处相邻逆序，"
                        f"排序后有 {mismatches} 个位置变化。",
                        f"排序规则：{rule}",
                    ]
                    if stopped:
                        lines.extend([
                            f"注意：任务提前停止，仅统计已完成的 {completed}/{total_pages} 页。",
                            "",
                        ])
                    else:
                        lines.append("")
                    lines.append("以下为相邻逆序（前一词 > 后一词）：")
                    for number, (prev, cur) in enumerate(inversions[:200], 1):
                        lines.append(
                            f"{number}. {prev[0]}  {prev[1]} [{prev[3]}]  >  "
                            f"{cur[0]}  {cur[1]} [{cur[3]}]"
                        )
                    if len(inversions) > 200:
                        lines.append(f"…另有 {len(inversions) - 200} 处未显示")
                    return {
                        "count": len(sequence), "inversions": len(inversions),
                        "mismatches": mismatches, "rule": rule,
                        "report": "\n".join(lines), "stopped": bool(stopped),
                        "completed": completed, "total": total_pages,
                    }

                def finalized(result) -> None:
                    if self.project is not project:
                        return
                    count = int(result["count"])
                    inversions = int(result["inversions"])
                    stopped_suffix = (
                        f"（提前停止，仅完成 {result['completed']}/{result['total']} 页）"
                        if result["stopped"] else ""
                    )
                    if count < 2:
                        messagebox.showinfo(
                            title,
                            f"可核对的非空词头不足 2 个。{stopped_suffix}",
                            parent=self,
                        )
                    elif not inversions:
                        messagebox.showinfo(
                            title,
                            f"顺序正常。\n共核对 {count} 个非空词头。\n"
                            f"排序规则：{result['rule']}\n{stopped_suffix}",
                            parent=self,
                        )
                    else:
                        self._show_text_report(title, str(result["report"]))
                    self.status_var.set(
                        f"{title}完成：核对 {count} 个非空词头{stopped_suffix}"
                    )

                def finalize_failed(exc, detail) -> None:
                    if detail:
                        print(detail)
                    if self.project is project:
                        self.show_error(f"{title}汇总失败", exc)

                self._start_ui_worker(
                    "headword-order-finalize", finalize, finalized, finalize_failed,
                )

            self._start_batch_task(
                "所有词头顺序核对", indices, worker, done,
                item_label=lambda i: pages[i].name,
                refresh_page_quality=False,
            )
            return

        sequence: list[tuple[str, str, tuple]] = []
        for entry in self.entries:
            word = entry.word.strip()
            if word:
                sequence.append((self.current_page.name, word, self._order_key(word)))
        if len(sequence) < 2:
            messagebox.showinfo(title, "可核对的非空词头不足 2 个。", parent=self)
            return
        inversions: list[tuple[int, tuple[str, str, tuple], tuple[str, str, tuple]]] = []
        for i in range(1, len(sequence)):
            if sequence[i][2] < sequence[i - 1][2]:
                inversions.append((i, sequence[i - 1], sequence[i]))
        expected = sorted(sequence, key=lambda item: item[2])
        mismatches = sum(1 for actual, wanted in zip(sequence, expected) if actual != wanted)
        if not inversions:
            rule = profile_label(self.settings.headword_sort_mode, self.settings.ocr_language)
            messagebox.showinfo(
                title,
                f"顺序正常。\n共核对 {len(sequence)} 个非空词头。\n排序规则：{rule}",
                parent=self,
            )
            return
        rule = profile_label(self.settings.headword_sort_mode, self.settings.ocr_language)
        lines = [
            f"共核对 {len(sequence)} 个非空词头；发现 {len(inversions)} 处相邻逆序，排序后有 {mismatches} 个位置变化。",
            f"排序规则：{rule}",
            "",
            "以下为相邻逆序（前一词 > 后一词）：",
        ]
        for number, (_i, prev, cur) in enumerate(inversions[:200], 1):
            lines.append(
                f"{number}. {prev[0]}  {prev[1]} [{self._order_display_key(prev[1])}]  >  "
                f"{cur[0]}  {cur[1]} [{self._order_display_key(cur[1])}]"
            )
        if len(inversions) > 200:
            lines.append(f"…另有 {len(inversions)-200} 处未显示")
        self._show_text_report(title, "\n".join(lines))

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
        if not self.project: return
        self._detect_pages(
            list(range(len(self.project.images))),
            method=self.settings.detection_method,
            force_refresh=force_paddle_refresh,
        )

    def batch_ocr(self) -> None:
        if not self.project or self._batch_active: return
        if not self._guard_transformed_geometry("批量 OCR"):
            return
        indices = [i for i, page in enumerate(self.project.images) if read_pdic(pdic_path(page))]
        if not indices:
            self.status_var.set("没有含 PDIC 词条的页面可执行批量 OCR")
            return
        if not messagebox.askyesno(
            "批量 OCR",
            f"将对 {len(indices)} 个已有 PDIC 的页面执行 OCR。\n\n"
            "处理期间可暂停或停止；当前页会先完整处理并保存。继续？",
            parent=self,
        ):
            return
        project = self.project
        settings = replace(self.settings)
        rules = load_replace_rules(replace_rules_path(project.root))
        pages_info = {i: self.pages_tuple(i) for i in indices}

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            entries = read_pdic(pdic_path(page))
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            effective_settings = effective_page_settings(settings, image.size, index)
            analysis_image = page_template_analysis_image(image, effective_settings, index)
            sections = read_page_sections(page)
            entries = sort_entries_reading_order(
                entries, derive_geometry(analysis_image, effective_settings), sections,
            )
            texts = ocr_entries(
                image, entries, settings, rules, profile_page_index=index,
                page_sections=sections,
            )
            for entry, text in zip(entries, texts): entry.word = text
            export_ocred(qt_root(project.root) / f"{page.stem}.OCRed", texts)
            write_pdic(pdic_path(page), entries, image.width, pages_info[index])
            return len(texts)

        def done(completed, total_pages, stopped, results, error):
            if error is not None: return
            count = sum(int(v or 0) for v in results)
            self.load_page(self.current_index)
            if stopped:
                self.status_var.set(f"批量 OCR 已停止：完成 {completed}/{total_pages} 页，共 {count} 个词条")
            else:
                self.status_var.set(f"批量 OCR 完成：{count} 个词条")

        self._start_batch_task("批量 OCR", indices, worker, done, item_label=lambda i: project.images[i].name)

    def batch_split_whole(self) -> None:
        if not self.project or self._batch_active: return
        if not self._guard_transformed_geometry("批量整体切图"):
            return
        project = self.project
        settings = replace(self.settings)
        indices = list(range(len(project.images)))
        out_dir = qt_root(project.root) / "PWW"
        config = self._load_crop_settings()
        general_top = int(config.get("general_top_v", settings.start_y))
        general_bottom = int(config.get("general_bottom_v", 0))
        entry_left = int(config.get("entry_left_padding_u", 0))
        entry_right = int(config.get("entry_right_padding_u", 0))
        integrate_illustrations = bool(config.get("integrate_illustrations", True))
        specials = config.get("special_pages", {}) if isinstance(config.get("special_pages", {}), dict) else {}

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            entries = read_pdic(pdic_path(page))
            polygons = read_ppp(ppp_read_path_for_image(page))
            special = specials.get(page.stem, {}) if isinstance(specials.get(page.stem, {}), dict) else {}
            top_y = int(special.get("top_v", general_top))
            bottom_y = int(special.get("bottom_v", general_bottom))
            records = split_whole_entries(
                page, entries, settings, out_dir, top_y=top_y, bottom_y=bottom_y, polygons=polygons,
                entry_left_padding=entry_left, entry_right_padding=entry_right,
                integrate_illustrations=integrate_illustrations,
                profile_page_index=index,
            )
            append_crop_log(project.root, records)
            return len(records)

        def done(completed, total_pages, stopped, results, error):
            if error is not None: return
            count = sum(int(v or 0) for v in results)
            if stopped:
                self.status_var.set(f"批量整体切图已停止：完成 {completed}/{total_pages} 页，共 {count} 张")
            else:
                self.status_var.set(f"批量整体切图完成：{count} 张")

        self._start_batch_task("批量整体切图", indices, worker, done, item_label=lambda i: project.images[i].name)

    def repair_pdic_order_selected_scope(self) -> None:
        """Rewrite selected-page PDIC files in stable column/Y order.

        X deliberately does not participate in this repair sort.  Existing
        word<->coordinate pairs remain intact; records sharing the same column
        and Y retain their current relative order.
        """
        if not self.project or not self.current_page or self.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
            return
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再修复排序。")
            return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围错误", exc)
            return
        if not indices:
            self.status_var.set("没有选中需要修复的页面")
            return

        existing = [i for i in indices if pdic_path(self.project.images[i]).exists()]
        if not existing:
            self.status_var.set("所选范围没有已有 PDIC 文件")
            return
        try:
            self._flush_deferred_page_save()
            self._sync_entry_editor_texts()
            self.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            self.show_error("修复排序准备失败", exc)
            return

        if not messagebox.askyesno(
            "修复排序",
            f"将对所选范围中 {len(existing)} 个已有 PDIC 页面按“栏号 → Y”重新排序并原子写回（X 不参与排序）。\n\n"
            "每条记录现有的词条文字与 X/Y 坐标会保持绑定，不会重新 OCR 或改词。\n"
            "建议先点击【备份PDIC】保留当前状态。\n\n继续？",
            parent=self,
        ):
            return

        project = self.project
        settings = self.settings

        def worker(index: int, _position: int, _total: int):
            page = project.images[index]
            target = pdic_path(page)
            entries = read_pdic(target)
            if not entries:
                return (index, 0, False)
            before = [(e.word, int(e.x), int(e.y)) for e in entries]
            with Image.open(page) as opened:
                width, height = map(int, opened.size)
            geometry = derive_nominal_geometry(width, height, settings)
            ordered = sort_entries_column_y(
                entries, geometry, read_page_sections(page),
            )
            after = [(e.word, int(e.x), int(e.y)) for e in ordered]
            previous = project.images[index - 1].stem if index > 0 else "@"
            following = project.images[index + 1].stem if index + 1 < len(project.images) else "@"
            _write_pdic_atomic(target, ordered, width, (page.stem, previous, following))
            return (index, len(ordered), before != after)

        def done(completed: int, total: int, stopped: bool, results, error) -> None:
            if error is not None:
                return
            changed = sum(1 for result in results if result and result[2])
            records = sum(int(result[1]) for result in results if result)
            if self.current_index in existing:
                self.load_page(self.current_index)
            state = "已停止" if stopped else "完成"
            self.status_var.set(
                f"修复排序{state}：处理 {completed}/{total} 页；实际改序 {changed} 页；{records} 条记录"
            )

        self._start_batch_task(
            "修复排序", existing, worker, done,
            item_label=lambda i: project.images[i].name,
        )

    def export_picdic_index(self) -> None:
        """Export a project-wide four-column text index from saved PDIC records.

        The output is intentionally simple for downstream PicDic conversion::

            WORD<TAB>xx.xx<TAB>yy.yy<TAB>page

        Percentages are taken from the persisted PDIC percentage fields rather
        than recalculated from pixels.  This preserves the coordinate semantics
        of the source PDIC, including legacy projects.  Large projects are
        streamed in the background and never accumulated into one giant string.
        """
        if not self.project or not self.current_page or self.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
            return
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再导出PicDic索引。")
            return
        try:
            self._flush_deferred_page_save()
            self._sync_entry_editor_texts()
            self.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            self.show_error("导出PicDic索引失败", exc)
            return

        project = self.project
        pages = [page for page in project.images if pdic_path(page).exists()]
        if not pages:
            messagebox.showinfo("导出PicDic索引", "当前项目没有可导出的 PDIC 文件。", parent=self)
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = exports_root(project.root) / f"PicDic_index_{stamp}.txt"
        temp = target.with_name(f".{target.name}.tmp")
        state: dict[str, object] = {"stream": None, "page_count": 0, "record_count": 0}

        def worker(page: Path, _position: int, _total: int):
            stream = state.get("stream")
            if stream is None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                stream = temp.open("w", encoding="utf-8", newline="\n")
                state["stream"] = stream
            records = read_picdic_index_records(pdic_path(page), fallback_page=page.stem)
            if records:
                stream.write("\n".join(records))
                stream.write("\n")
                state["page_count"] = int(state.get("page_count", 0)) + 1
                state["record_count"] = int(state.get("record_count", 0)) + len(records)
            return len(records)

        def done(completed: int, total: int, stopped: bool, _results, error) -> None:
            stream = state.get("stream")
            if stream is not None:
                try:
                    stream.flush()
                    stream.close()
                except OSError:
                    pass
                state["stream"] = None
            if error is not None or stopped:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                if error is None:
                    self.status_var.set(
                        f"PicDic索引导出已停止：完成 {completed}/{total} 页，未生成不完整索引。"
                    )
                return
            try:
                if not temp.exists():
                    temp.write_text("", encoding="utf-8")
                os.replace(temp, target)
                page_count = int(state.get("page_count", 0))
                record_count = int(state.get("record_count", 0))
                self.status_var.set(
                    f"PicDic索引导出完成：{target.name}｜{page_count} 页｜{record_count} 条"
                )
                messagebox.showinfo(
                    "导出PicDic索引",
                    f"已生成：\n{target}\n\n共 {page_count} 个有记录页面，{record_count} 条索引。\n"
                    "格式：WORD\\txx.xx%\\tyy.yy%\\tpage",
                    parent=self,
                )
            except Exception as exc:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                self.show_error("导出PicDic索引失败", exc)

        self._start_batch_task(
            "导出PicDic索引", pages, worker, done, item_label=lambda page: page.name,
            refresh_page_quality=False,
        )

    def backup_pdic(self) -> None:
        """Stream every page PDIC into one timestamped backup without blocking Tk.

        Large projects can contain thousands of tiny PDIC files.  Reading every
        file and joining all records on the Tk thread made the window appear
        frozen even though disk I/O was still progressing.  The backup now uses
        the existing sequential background-task runner and writes each record
        directly to a temporary output stream.  No page image pixels are read
        and the full backup is never accumulated in memory.
        """
        if not self.project or not self.current_page or self.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
            return
        if self._batch_active:
            self.status_var.set("已有批量任务正在运行，请结束后再备份PDIC。")
            return
        try:
            self._flush_deferred_page_save()
            self._sync_entry_editor_texts()
            self.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            self.show_error("备份PDIC失败", exc)
            return

        project = self.project
        pages = [page for page in project.images if pdic_path(page).exists()]
        if not pages:
            messagebox.showinfo("备份PDIC", "当前项目没有可备份的 PDIC 文件。", parent=self)
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = exports_root(project.root) / f"all_pdic_backup_{stamp}.txt"
        temp = target.with_name(f".{target.name}.tmp")
        state: dict[str, object] = {"stream": None, "page_count": 0, "record_count": 0}

        def worker(page: Path, _position: int, _total: int):
            stream = state.get("stream")
            if stream is None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                stream = temp.open("w", encoding="utf-8", newline="\n")
                state["stream"] = stream
            source = pdic_path(page)
            # Keep only one page in memory at a time.  This is substantially
            # faster than per-line writes on Windows/network disks while still
            # avoiding the old project-wide list/join memory spike.
            page_lines = [
                raw for raw in source.read_text(encoding="utf-8-sig").splitlines()
                if raw.strip()
            ]
            count = len(page_lines)
            if count:
                stream.write("\n".join(page_lines))
                stream.write("\n")
                state["page_count"] = int(state.get("page_count", 0)) + 1
                state["record_count"] = int(state.get("record_count", 0)) + count
            return count

        def done(completed: int, total: int, stopped: bool, _results, error) -> None:
            stream = state.get("stream")
            if stream is not None:
                try:
                    stream.flush()
                    stream.close()
                except OSError:
                    pass
                state["stream"] = None
            if error is not None or stopped:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                if error is None:
                    self.status_var.set(f"PDIC备份已停止：完成 {completed}/{total} 页，未生成不完整备份。")
                return
            try:
                if not temp.exists():
                    temp.write_text("", encoding="utf-8")
                os.replace(temp, target)
                page_count = int(state.get("page_count", 0))
                record_count = int(state.get("record_count", 0))
                self.status_var.set(
                    f"PDIC备份完成：{target.name}｜{page_count} 页｜{record_count} 条"
                )
                messagebox.showinfo(
                    "备份PDIC",
                    f"已生成：\n{target}\n\n包含 {page_count} 个有记录页面，共 {record_count} 条 PDIC。",
                    parent=self,
                )
            except Exception as exc:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                self.show_error("备份PDIC失败", exc)

        self._start_batch_task(
            "备份PDIC", pages, worker, done, item_label=lambda page: page.name,
            refresh_page_quality=False,
        )

    def restore_from_pdic_backup(self) -> None:
        """Rebuild the selected page range from one PDIC backup text.

        The selected range is authoritative: every selected page is overwritten.
        If a selected page has no records in the merged source, its PDIC is
        replaced by an empty file instead of borrowing records from adjacent
        pages.  Parsing and per-page commits run off the Tk thread.
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

        path_text = filedialog.askopenfilename(
            title="选择备份的PDIC 备份 文本",
            initialdir=str(self.project.root),
            filetypes=[("PDIC/文本", "*.pdic *.txt"), ("PDIC", "*.pdic"), ("文本", "*.txt"), ("全部", "*")],
            parent=self,
        )
        if not path_text:
            return
        source = Path(path_text)
        if not messagebox.askyesno(
            "恢复PDIC",
            f"将从：\n{source.name}\n\n覆盖重建主界面所选范围内的 {len(indices)} 个页面 PDIC。\n"
            "范围外页面不会修改。PDIC 备份 中若某个选定页面没有记录，该页会被重建为空 PDIC。\n\n"
            "每页完成后立即原子覆盖，可暂停或停止；已完成页面不会回滚。继续？",
            parent=self,
        ):
            return

        try:
            # Commit the visible page before the destructive range restore begins.
            # Navigation/editing is blocked while this non-foreground batch runs,
            # so no stale canvas copy can overwrite a restored page afterward.
            self._flush_deferred_page_save()
            self._sync_entry_editor_texts()
            self.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            self.show_error("PDIC 备份 恢复准备失败", exc)
            return

        project = self.project
        settings_snapshot = replace(self.settings)
        pages = list(project.images)
        page_stems = [page.stem for page in pages]
        pages_meta = {i: self.pages_tuple(i) for i in indices}
        parsed_holder: dict[str, object] = {"mapping": None, "stats": None}
        parse_lock = threading.Lock()

        def ensure_parsed() -> tuple[dict[str, list[WordEntry]], dict[str, int]]:
            mapping = parsed_holder.get("mapping")
            stats = parsed_holder.get("stats")
            if isinstance(mapping, dict) and isinstance(stats, dict):
                return mapping, stats
            with parse_lock:
                mapping = parsed_holder.get("mapping")
                stats = parsed_holder.get("stats")
                if not isinstance(mapping, dict) or not isinstance(stats, dict):
                    text_data, _encoding = read_text_detected(source)
                    mapping, stats = _parse_merged_pdic_text(text_data, page_stems)
                    parsed_holder["mapping"] = mapping
                    parsed_holder["stats"] = stats
            return mapping, stats

        def worker(index: int, _position: int, _total: int):
            mapping, stats = ensure_parsed()
            page = pages[index]
            # Copy the list so writing this page cannot mutate the shared parsed
            # source.  The merged file remains a read-only source of truth.
            entries = [replace(entry) for entry in mapping.get(page.stem, [])]
            with Image.open(page) as opened:
                width, height = map(int, opened.size)
            entries = sort_entries_reading_order(
                entries, derive_nominal_geometry(width, height, settings_snapshot),
                read_page_sections(page),
            )
            _write_pdic_atomic(pdic_path(page), entries, width, pages_meta[index])
            return {
                "index": index,
                "records": len(entries),
                "empty": not entries,
                "source_records": int(stats.get("records", 0)),
                "source_matched": int(stats.get("matched", 0)),
                "source_unmatched": int(stats.get("unmatched", 0)),
            }

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            rebuilt = 0
            records = 0
            empty_pages = 0
            completed_indices: set[int] = set()
            stats = parsed_holder.get("stats") if isinstance(parsed_holder.get("stats"), dict) else {}
            for result in results:
                if not isinstance(result, dict):
                    continue
                index = int(result.get("index", -1))
                if index >= 0:
                    completed_indices.add(index)
                rebuilt += 1
                records += int(result.get("records", 0) or 0)
                empty_pages += int(bool(result.get("empty")))

            # A previous TXT-fill count check no longer describes a page that
            # has just been rebuilt from the merged PDIC source. Remove both the
            # visible warning and its persisted expected-count record.
            self._clear_word_fill_checks_for_indices(completed_indices, persist=True)
            for index in completed_indices:
                self._update_page_row(index)
            self._schedule_page_cell_overlay_refresh()
            if self.current_index in completed_indices:
                self.load_page(self.current_index)

            unmatched = int(stats.get("unmatched", 0) or 0)
            if stopped:
                self.status_var.set(
                    f"PDIC 备份 恢复已停止：完成 {completed}/{total_pages} 页，重建 {records} 条；"
                    f"空页 {empty_pages} 页"
                )
            else:
                extra = f"；源文件有 {unmatched} 条记录未对应当前项目页面" if unmatched else ""
                self.status_var.set(
                    f"PDIC 备份 恢复完成：{rebuilt}/{total_pages} 页，重建 {records} 条；"
                    f"空页 {empty_pages} 页{extra}"
                )

        started = self._start_batch_task(
            "恢复PDIC",
            indices,
            worker,
            done,
            item_label=lambda i: pages[i].name,
            foreground_page_edit=False,
        )
        if started:
            self.batch_text_var.set(f"恢复PDIC：准备读取备份文件 0/{len(indices)}")
            self.status_var.set(
                f"正在后台解析PDIC 备份 并逐页覆盖重建：共 {len(indices)} 页；"
                "进度按页面更新，可暂停或停止。"
            )

    def restore_from_merged_pdic(self) -> None:
        """Backward-compatible alias for old integrations."""
        self.restore_from_pdic_backup()

    @staticmethod
    def _word_fill_file_signature(path: Path) -> tuple[str, int, int]:
        stat = path.stat()
        return (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))

    def select_existing_headwords_file(self) -> None:
        """Choose the page-aware TXT used by subsequent fill operations.

        Selection is deliberately separate from filling: a large dictionary can
        be parsed once, then the user may change the main page range and refill
        mismatch pages repeatedly without reopening the file picker.
        """
        if not self.project:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
            return
        if self._batch_active:
            messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=self)
            return
        initialdir = self.project.root
        initialfile = "_WordsOfPages.txt"
        if self._word_fill_source_path is not None:
            initialdir = self._word_fill_source_path.parent
            initialfile = self._word_fill_source_path.name
        path_text = filedialog.askopenfilename(
            title="选择包含既有词条的 TXT",
            initialdir=str(initialdir),
            initialfile=initialfile,
            filetypes=[("文本", "*.txt"), ("全部", "*")],
            parent=self,
        )
        if not path_text:
            return
        path = Path(path_text)
        try:
            signature = self._word_fill_file_signature(path)
        except Exception as exc:
            self.show_error("词条文件不可用", exc)
            return

        # Re-selecting an unchanged source keeps the already parsed mapping.
        # Choosing another file, or choosing a changed version of the same file,
        # invalidates only the parse cache; no PDIC is touched at this stage.
        if signature != self._word_fill_source_signature:
            self._word_fill_source_mapping = None
            self._word_fill_source_present_pages = None
        self._word_fill_source_path = path
        self._word_fill_source_signature = signature
        cached = "（已缓存解析结果）" if self._word_fill_source_mapping is not None else ""
        self.status_var.set(f"已选择词条文件：{path.name}{cached}；调整页面范围后点击[填充词条]。")

    def fill_existing_headwords(self) -> None:
        """Fill the selected range from the already chosen page-aware TXT.

        The source file picker is intentionally *not* opened here.  Once a file
        has been selected, the parsed mapping survives repeated fill batches in
        this project. If the source changes on disk, its signature invalidates
        the cache and the next batch reparses it in the worker thread.
        """
        if not self.project or not self.current_page or self.image is None:
            messagebox.showinfo("尚未打开", "请先打开包含扫描图片的项目目录。", parent=self)
            return
        if self._batch_active:
            messagebox.showinfo("批量任务正在运行", "已有批量任务正在运行，请先暂停或停止。", parent=self)
            return
        if self._word_fill_source_path is None:
            messagebox.showinfo("尚未选择词条文件", "请先点击[选择词条文件]，再执行填充。", parent=self)
            return
        try:
            indices = self.selected_page_indices()
        except Exception as exc:
            self.show_error("页面范围无效", exc)
            return
        if not indices:
            return

        txt_path = self._word_fill_source_path
        try:
            current_signature = self._word_fill_file_signature(txt_path)
        except Exception as exc:
            self.show_error("词条文件不可用", exc)
            return
        if current_signature != self._word_fill_source_signature:
            self._word_fill_source_signature = current_signature
            self._word_fill_source_mapping = None
            self._word_fill_source_present_pages = None

        try:
            # Commit any live Entry edits before the worker starts reading PDIC.
            # During this task foreground page edits/navigation are intentionally
            # blocked, so a worker can never race a stale canvas copy.
            self._flush_deferred_page_save()
            self._sync_entry_editor_texts()
            self.save_pdic(silent=True, sync_editors=False)
        except Exception as exc:
            self.show_error("填充词条失败", exc)
            return

        project = self.project
        settings_snapshot = replace(self.settings)
        pages = list(project.images)
        page_stems = [page.stem for page in pages]
        pages_meta = [
            (page.stem, pages[i - 1].stem if i > 0 else "@", pages[i + 1].stem if i + 1 < len(pages) else "@")
            for i, page in enumerate(pages)
        ]
        # A holder local to this batch avoids any race where the first worker
        # resolves the app-level cache while subsequent page commits start.
        mapping_holder = {
            "value": self._word_fill_source_mapping,
            "present": self._word_fill_source_present_pages,
        }

        def ensure_mapping() -> tuple[dict[str, list[str]], set[str]]:
            mapping = mapping_holder["value"]
            present = mapping_holder["present"]
            if mapping is None or present is None:
                text_data, _detected_encoding = read_text_detected(txt_path)
                present = set()
                mapping = _parse_words_of_pages_text(text_data, page_stems, present_pages=present)
                mapping_holder["value"] = mapping
                mapping_holder["present"] = present
            return mapping, present

        def worker(index: int, _position: int, _total: int):
            mapping, present_pages = ensure_mapping()
            page = pages[index]
            entries = read_pdic(pdic_path(page))
            with Image.open(page) as opened:
                width, height = map(int, opened.size)
            entries = sort_entries_reading_order(
                entries, derive_nominal_geometry(width, height, settings_snapshot),
                read_page_sections(page),
            )
            has_data = page.stem in present_pages
            words = list(mapping.get(page.stem, [])) if has_data else []
            filled, line_count, word_count = _fill_page_entries(entries, words)

            # Empty pages stay empty; a page with TXT words but no lines must not
            # get a fabricated PDIC. Each completed page is its own commit point.
            if entries or pdic_path(page).exists():
                write_pdic(pdic_path(page), entries, width, pages_meta[index])
            return {
                "index": index,
                "filled": filled,
                "line_count": line_count,
                "word_count": word_count,
                "has_data": has_data,
                "mismatch": has_data and line_count != word_count,
            }

        def done(completed, total_pages, stopped, results, error):
            if error is not None:
                return
            if (
                self.project is project
                and self._word_fill_source_path == txt_path
                and self._word_fill_source_signature == current_signature
            ):
                mapping = mapping_holder.get("value")
                present = mapping_holder.get("present")
                if isinstance(mapping, dict) and isinstance(present, set):
                    self._word_fill_source_mapping = mapping
                    self._word_fill_source_present_pages = present
            filled_total = 0
            mismatch_count = 0
            no_data_count = 0
            completed_indices: set[int] = set()
            for result in results:
                if not isinstance(result, dict):
                    continue
                index = int(result.get("index", -1))
                if index < 0:
                    continue
                completed_indices.add(index)
                filled_total += int(result.get("filled", 0) or 0)
                line_count = int(result.get("line_count", 0) or 0)
                word_count = int(result.get("word_count", 0) or 0)
                has_data = bool(result.get("has_data", True))
                self._record_word_fill_check(
                    index, line_count, word_count, source=txt_path.name, has_data=has_data,
                    persist=False, refresh_overlay=False, refresh_row=False,
                )
                if not has_data:
                    no_data_count += 1
                elif line_count != word_count:
                    mismatch_count += 1

            if completed_indices:
                self._persist_word_fill_status()
            if self.current_index in completed_indices:
                self.load_page(self.current_index)

            source_name = txt_path.name
            if stopped:
                self.status_var.set(
                    f"既有词条填充已停止：完成 {completed}/{total_pages} 页，填入 {filled_total} 个词条；"
                    f"已完成页面中数量不一致 {mismatch_count} 页，无资料 {no_data_count} 页；来源：{source_name}"
                )
            else:
                self.status_var.set(
                    f"既有词条填充完成：{completed}/{total_pages} 页，填入 {filled_total} 个词条；"
                    f"数量不一致 {mismatch_count} 页（填充状态格淡红提示），无资料 {no_data_count} 页；来源：{source_name}"
                )

        started = self._start_batch_task(
            "填充词条",
            indices,
            worker,
            done,
            item_label=lambda i: pages[i].name,
            foreground_page_edit=False,
        )
        if started:
            cached = self._word_fill_source_mapping is not None
            phase = "使用已缓存词条索引" if cached else "准备读取并解析词条文件"
            self.batch_text_var.set(f"填充词条：{phase} 0/{len(indices)}")
            self.status_var.set(
                f"正在后台逐页填充：共 {len(indices)} 页；来源：{txt_path.name}；"
                "进度按页面更新，可暂停或停止。"
            )

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
