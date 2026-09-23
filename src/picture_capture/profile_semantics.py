from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from PIL import Image, ImageDraw

from .dictionary_profile import available_dictionary_profiles, dictionary_profile_preset, language_effective_settings, profile_effective_settings
from .layout_transform import LayoutTransform
from .models import AppSettings

PROFILE_SETUP_VERSION = 1

READING_CHOICES = {
    "horizontal-ltr": ("horizontal-tb", "ltr", "identity"),
    "horizontal-rtl": ("horizontal-tb", "rtl", "mirror_x"),
    "vertical-rl": ("vertical-rl", "rtl", "rotate_ccw90"),
    "vertical-lr": ("vertical-lr", "ltr", "rotate_cw90"),
}

READING_LABELS = {
    "horizontal-ltr": "横排 · 左 → 右",
    "horizontal-rtl": "横排 · 右 → 左",
    "vertical-rl": "纵排 · 右 → 左",
    "vertical-lr": "纵排 · 左 → 右",
}

# Selecting a headword structure in the wizard must never silently replace the
# already-confirmed reading direction, page template, or language.  Only these
# recognition-style defaults are copied from the generic headword preset.
HEADWORD_PROFILE_SETTING_NAMES = (
    "paddle_band_width_ratio",
    "paddle_band_left_margin",
    "paddle_left_tolerance",
    "paddle_height_ratio",
    "paddle_boldness_ratio",
    "paddle_gap_ratio",
    "paddle_min_candidate_score",
    "paddle_require_visual_cue",
    "paddle_require_pos_or_symbol",
    "paddle_remove_syllable_separators",
    "paddle_pos_search_chars",
)


def sample_page_indices(total: int, target: int = 6) -> list[int]:
    """Choose front/middle/back pages while preserving an adjacent A/B sample.

    The four-page validation path must still include the back of the book rather
    than truncating the six-page analysis candidate list before the final pages.
    Six-page analysis keeps adjacent pairs at front/middle/back.
    """
    total = max(0, int(total))
    target = max(1, int(target))
    if total <= target:
        return list(range(total))
    last = total - 1
    middle = total // 2

    if target == 1:
        return [middle]
    if target == 2:
        return [0, last]
    if target == 3:
        return sorted({0, middle, last})
    if target == 4:
        return sorted({0, 1, middle, last})
    if target == 5:
        return sorted({0, 1, middle, max(0, last - 1), last})

    candidates = [
        0, 1,
        max(0, middle - 1), min(last, middle),
        max(0, last - 1), last,
    ]
    seen: list[int] = []
    for index in candidates:
        if index not in seen:
            seen.append(index)
    if len(seen) < target:
        for step in range(1, target + 1):
            index = round(step * last / max(1, target + 1))
            if index not in seen:
                seen.append(index)
            if len(seen) >= target:
                break
    return sorted(seen[:target])


def reading_choice_from_settings(settings: AppSettings) -> str:
    writing = str(getattr(settings, "layout_writing_mode", "horizontal-tb") or "horizontal-tb")
    direction = str(getattr(settings, "layout_text_direction", "ltr") or "ltr")
    if writing == "vertical-rl":
        return "vertical-rl"
    if writing == "vertical-lr":
        return "vertical-lr"
    return "horizontal-rtl" if direction == "rtl" else "horizontal-ltr"


def apply_reading_choice(settings: AppSettings, choice: str) -> None:
    writing, direction, transform = READING_CHOICES.get(choice, READING_CHOICES["horizontal-ltr"])
    settings.layout_writing_mode = writing
    settings.layout_text_direction = direction
    settings.layout_transform = transform
    for name, value in language_effective_settings(settings.ocr_language, writing).items():
        if hasattr(settings, name):
            setattr(settings, name, value)


def ordered_headword_profiles(custom_name: str = "") -> list[tuple[str, str]]:
    """Return numbered UI labels with custom permanently placed last."""
    profiles = list(available_dictionary_profiles())
    profiles.sort(key=lambda profile: profile.key == "custom")
    result: list[tuple[str, str]] = []
    for number, profile in enumerate(profiles, start=1):
        label = profile.display_name
        if profile.key == "custom" and custom_name.strip():
            label = f"{custom_name.strip()}（自定义）"
        result.append((f"{number}. {label}", profile.key))
    return result


def apply_headword_profile(settings: AppSettings, profile_key: str) -> None:
    """Apply only the headword-recognition dimension of a generic preset."""
    defaults = profile_effective_settings(profile_key, current_language=settings.ocr_language)
    for name in HEADWORD_PROFILE_SETTING_NAMES:
        if name in defaults and hasattr(settings, name):
            setattr(settings, name, defaults[name])
    settings.dictionary_profile_id = profile_key


def page_variant(settings: AppSettings, page_index: int) -> str:
    if str(getattr(settings, "profile_page_pair_mode", "same")) != "alternate":
        return "A"
    first = str(getattr(settings, "profile_first_page_variant", "A") or "A").upper()
    first = "B" if first == "B" else "A"
    if int(page_index) % 2 == 0:
        return first
    return "A" if first == "B" else "B"


def excluded_source_side(settings: AppSettings, page_index: int) -> str | None:
    mode = str(getattr(settings, "profile_side_content_mode", "none") or "none")
    if mode in {"left", "right"}:
        return mode
    if mode not in {"outer", "inner"}:
        return None
    variant = page_variant(settings, page_index)
    # A/B are deliberately explicit rather than calling them odd/even pages:
    # the first scan in a project need not equal the printed page parity.
    a_outer = "left"
    outer = a_outer if variant == "A" else "right"
    if mode == "outer":
        return outer
    return "right" if outer == "left" else "left"


def effective_page_settings(settings: AppSettings, image_size: tuple[int, int], page_index: int = 0) -> AppSettings:
    """Return a per-page copy with intuitive header/footer template applied."""
    current = replace(settings)
    transform = LayoutTransform(str(current.layout_transform or "identity"))
    canonical_width, canonical_height = transform.canonical_size(image_size)
    parameter_width = current.parameter_display_width or min(1400, canonical_width)
    scale = parameter_width / max(1, canonical_width)

    header_mode = str(getattr(current, "profile_header_mode", "auto") or "auto")
    if header_mode == "auto":
        current.paddle_auto_header_rule = True
    elif header_mode == "none":
        # "No running header" does not mean body ink starts at pixel 0. Keep
        # the representative-page body top learned by the Profile analysis,
        # but disable the extra running-header rule detector.
        current.paddle_auto_header_rule = False
    else:
        current.paddle_auto_header_rule = False
        pct = max(0.0, min(35.0, float(getattr(current, "profile_header_percent", 6.0))))
        current.start_y = round(canonical_height * pct / 100.0 * scale)

    footer_mode = str(getattr(current, "profile_footer_mode", "auto") or "auto")
    if footer_mode == "present":
        pct = max(0.0, min(35.0, float(getattr(current, "profile_footer_percent", 5.0))))
        current.bottom_y = round(canonical_height * (1.0 - pct / 100.0) * scale)
        current.crop_to_bottom_y = True
    elif footer_mode == "auto":
        # Representative-page analysis learns a robust body bottom. Reuse that
        # value when available; otherwise remain uncropped until analysis runs.
        current.crop_to_bottom_y = int(getattr(current, "bottom_y", 0) or 0) > 0
    elif footer_mode == "none":
        current.crop_to_bottom_y = False

    return current


def page_template_analysis_image(
    image: Image.Image,
    settings: AppSettings,
    page_index: int = 0,
) -> Image.Image:
    """Return a same-size analysis copy with configured physical page-edge noise removed.

    Page-edge indexes/tabs can otherwise be mistaken for a text column and shift
    layout/OCR geometry before the later entry-level filter gets a chance to
    reject them. Only the disposable analysis copy is whitened; source pixels,
    saved coordinates, crops and exports are untouched.
    """
    side = excluded_source_side(settings, page_index)
    if side is None:
        return image.copy()
    result = image.copy()
    width, height = result.size
    pct = max(0.0, min(30.0, float(getattr(settings, "profile_side_percent", 8.0))))
    margin = max(0, min(width, round(width * pct / 100.0)))
    if margin <= 0:
        return result
    draw = ImageDraw.Draw(result)
    if side == "left":
        draw.rectangle((0, 0, margin, height), fill="white")
    else:
        draw.rectangle((max(0, width - margin), 0, width, height), fill="white")
    return result


def entry_allowed_by_page_template(
    source_x: int,
    source_y: int,
    source_size: tuple[int, int],
    settings: AppSettings,
    page_index: int = 0,
) -> bool:
    """Reject entries inside a configured physical left/right page-edge exclusion."""
    side = excluded_source_side(settings, page_index)
    if side is None:
        return True
    width, _height = source_size
    pct = max(0.0, min(30.0, float(getattr(settings, "profile_side_percent", 8.0))))
    boundary = width * pct / 100.0
    if side == "left":
        return source_x >= boundary
    return source_x <= width - boundary


def profile_summary_tags(settings: AppSettings) -> list[str]:
    reading = READING_LABELS.get(reading_choice_from_settings(settings), "横排 · 左 → 右")
    columns = "栏数自动" if settings.layout_columns_policy == "detect" else f"{max(1, int(settings.columns))}栏"
    separator = {"auto": "分隔线自动", "present": "有中隔线", "absent": "无中隔线"}.get(
        str(settings.layout_column_separator_mode), "分隔线自动"
    )
    header = {"auto": "页眉自动", "none": "无页眉", "present": "有页眉"}.get(
        str(getattr(settings, "profile_header_mode", "auto")), "页眉自动"
    )
    footer = {"auto": "页尾自动", "none": "无页尾", "present": "有页尾"}.get(
        str(getattr(settings, "profile_footer_mode", "auto")), "页尾自动"
    )
    side = {
        "none": "无页边排除",
        "left": "左页边排除",
        "right": "右页边排除",
        "outer": "A/B 外侧页边",
        "inner": "A/B 内侧页边",
    }.get(str(getattr(settings, "profile_side_content_mode", "none")), "无页边排除")
    try:
        headword = dictionary_profile_preset(settings.dictionary_profile_id).display_name
    except Exception:
        headword = settings.dictionary_profile_id
    custom = str(getattr(settings, "dictionary_custom_profile_name", "") or "").strip()
    if settings.dictionary_profile_id == "custom" and custom:
        headword = f"{custom}（自定义）"
    return [reading, columns, separator, header, footer, side, settings.ocr_language, headword]


def copy_settings(dst: AppSettings, src: AppSettings) -> None:
    """Copy every persisted AppSettings field from a working copy to the project."""
    for name in src.__dataclass_fields__:
        setattr(dst, name, getattr(src, name))
