from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import re

from PIL import Image

from .layout_transform import LayoutTransform
from .runtime_environment import portable_project_file


IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"}
PROJECT_COVER_STEMS = ("_cover", "_project_cover")
PROJECT_COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def is_project_cover_image(path: Path) -> bool:
    return (
        path.is_file()
        and path.stem.casefold() in {stem.casefold() for stem in PROJECT_COVER_STEMS}
        and path.suffix.casefold() in PROJECT_COVER_EXTENSIONS
    )


def project_cover_path(root: Path) -> Path | None:
    root = Path(root)
    try:
        items = tuple(root.iterdir())
    except OSError:
        return None
    for stem in PROJECT_COVER_STEMS:
        for suffix in PROJECT_COVER_EXTENSIONS:
            candidate = root / f"{stem}{suffix}"
            if candidate.is_file():
                return candidate
            for item in items:
                if item.is_file() and item.stem.casefold() == stem.casefold() and item.suffix.casefold() == suffix:
                    return item
    return None


def project_page_images(root: Path) -> list[Path]:
    root = Path(root)
    try:
        pages = [path for path in root.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and not is_project_cover_image(path)]
    except OSError:
        return []
    return sorted(pages, key=lambda p: natural_text_key(p.name))


def natural_text_key(value: object) -> tuple:
    parts = re.split(r"(\d+)", str(value or "").casefold())
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts if part)


@dataclass(slots=True)
class Entry:
    word: str
    x: int
    y: int
    current_page: str = ""
    previous_page: str = "@"
    next_page: str = "@"
    confidence: float | None = None
    ocr_source: str = ""
    alphabetical_warning: str = ""
    candidate_id: str = ""
    final_engine: str = ""
    issue_type: str = ""
    parser_score: float | None = None
    manually_selected: bool = False
    ocr_box_height: float | None = None
    ocr_line_height_reference: float | None = None
    ocr_visual_run_height: float | None = None
    ocr_leading_height_ratio: float | None = None
    ocr_single_cjk: bool = False
    ocr_oversized_cjk: bool = False


@dataclass(slots=True)
class PolygonRegion:
    label: str
    points: list[tuple[int, int]] = field(default_factory=list)


@dataclass(slots=True)
class AppSettings:
    dictionary_full_name: str = ""
    dictionary_abbreviation: str = ""
    dictionary_isbn: str = ""
    dictionary_index_language: str = ""
    dictionary_content_language: str = ""
    dictionary_body_page_range: str = ""
    columns: int = 2
    layout_writing_mode: str = "horizontal-tb"
    layout_text_direction: str = "ltr"
    layout_transform: str = "identity"
    layout_columns_policy: str = "detect"
    layout_column_separator_mode: str = "auto"
    analysis_threshold_mode: str = "auto"
    analysis_denoise_strength: str = "auto"
    gutter: int = 50
    column_width: int = 700
    start_y: int = 55
    bottom_y: int = 0
    manual_x: int = 28
    column_start_offsets: list[int] = field(default_factory=list)
    manual_y: int = 400
    body_indent: int = 26
    character_height: int = 26
    row_padding: int = 1
    right_ratio: float = 100.0
    right_ratio_percent_version: int = 1
    ordinary_right_divisor: float = 1.0
    horizontal_tolerance: int = 13
    marker_height: int = 2
    guide_width: int = 2
    guide_color: str = "#1976d2"
    page_section_color: str = "#1976d2"
    page_section_width: int = 2
    show_rulers: bool = True
    ruler_color: str = "#1976d2"
    headword_marker_color: str = "#ff0000"
    illustration_outline_color: str = "#1976d2"
    illustration_outline_width: int = 2
    illustration_fill_color: str = "#ffe66d"
    illustration_label_border_color: str = "#1976d2"
    illustration_label_border_width: int = 2
    illustration_label_fill_color: str = "#e6e6e6"
    illustration_label_font_family: str = "自动（系统推荐）"
    illustration_label_font_size: int = 16
    illustration_label_font_bold: bool = False
    illustration_label_font_italic: bool = False
    show_page_sections: bool = True
    show_column_guides: bool = True
    show_headword_markers: bool = True
    page_list_show_lined: bool = True
    page_list_show_fill_status: bool = False
    page_list_show_illustrations: bool = True
    page_bookmarks: list[str] = field(default_factory=list)
    darkness_threshold: int = 300
    dark_area_percent: float = 90.0
    batch_interval: float = 3.0
    crop_parallel_workers: int = 0
    illustration_detect_padding: int = 8
    illustration_detect_right_padding: int = 16
    white_threshold_high: int = 999
    row_step_multiplier: float = 1.2
    whitespace_adjustment: int = 2
    upward_ratio: float = 1.5
    white_threshold_low: int = 700
    analysis_left: int = 0
    analysis_right: int = 0
    ocr_language: str = "eng"
    tesseract_language: str = ""
    ocr_replace: bool = True
    lowercase_ocr: bool = False
    manual_columns: bool = False
    ordinary_auto_layout: bool = True
    ordinary_auto_columns: bool = False
    ordinary_auto_start_y: bool = True
    ordinary_auto_manual_x: bool = True
    ordinary_auto_column_width: bool = False
    ordinary_auto_gutter: bool = False
    ordinary_auto_character_height: bool = False
    ordinary_auto_row_padding: bool = False
    crop_to_bottom_y: bool = False
    hide_overlays: bool = False
    polygon_mode: bool = False
    show_illustration_labels: bool = False
    ocr_executable: str = "tesseract"
    image_suffix: str = ".png"

    # Remaining settings are populated by project JSON when present.  Keep
    # backwards compatibility by allowing legacy projects to deserialize through
    # the helpers below rather than requiring every historical field inline.


def _appsettings_from_dict(data: dict) -> AppSettings:
    names = set(AppSettings.__dataclass_fields__)
    return AppSettings(**{k: v for k, v in data.items() if k in names})
