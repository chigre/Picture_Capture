from __future__ import annotations

from dataclasses import replace

from .coordinate_space import (
    canonical_geometry_to_stored,
    geometry_uses_canonical_pixels,
)
import re
from typing import Iterable

from PIL import Image, ImageDraw

from .dictionary_profile import available_dictionary_profiles, dictionary_profile_preset, language_effective_settings, profile_effective_settings
from .models import AppSettings

PROFILE_SETUP_VERSION = 1

READING_CHOICES = {
    "horizontal-ltr": ("horizontal-tb", "ltr", "identity"),
    "horizontal-rtl": ("horizontal-tb", "rtl", "mirror_x"),
    "vertical-rl": ("vertical-rl", "rtl", "rotate_ccw90"),
    "vertical-lr": ("vertical-lr", "ltr", "rotate_cw90"),
}

READING_LABELS = {
    "horizontal-ltr": "横排：左→右",
    "horizontal-rtl": "横排：右→左",
    "vertical-rl": "纵排：右→左",
    "vertical-lr": "纵排：左→右",
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



_NON_BODY_PAGE_TOKENS = (
    "cover", "title", "copyright", "contents", "toc", "preface", "foreword",
    "appendix", "appendices", "supplement", "supplements", "backmatter",
    "封面", "扉页", "版权", "目录", "前言", "序言", "附录", "附表", "后记",
)


def configured_body_page_indices(total: int, value: str | None) -> list[int]:
    """Resolve a 1-based project body-page range such as 12-980.

    The project-details field is used only when it resolves cleanly inside the
    current image sequence. Invalid/stale metadata is ignored instead of
    silently clipping to a different range.
    """
    total = max(0, int(total))
    text = str(value or "").strip()
    if not text or total <= 0:
        return []
    match = re.fullmatch(r"\s*(\d+)\s*(?:-|–|—|~|～|至|到)\s*(\d+)\s*", text)
    if not match:
        return []
    first, last = (int(match.group(1)), int(match.group(2)))
    if first < 1 or last < first or last > total:
        return []
    return list(range(first - 1, last))


def probable_body_page_indices(
    images: Iterable[object],
    allowed_indices: Iterable[int] | None = None,
) -> list[int]:
    """Return likely body-page indexes for Profile sampling.

    A valid project body-page range may be supplied as allowed_indices so
    front matter and appendices outside that range never enter automatic
    sampling. Filename filtering then removes obvious non-body pages inside
    the candidate range as a second line of defense.
    """
    items = list(images)
    if not items:
        return []

    if allowed_indices is None:
        pool = list(range(len(items)))
    else:
        pool = []
        seen: set[int] = set()
        for raw_index in allowed_indices:
            index = int(raw_index)
            if 0 <= index < len(items) and index not in seen:
                seen.add(index)
                pool.append(index)
        if not pool:
            pool = list(range(len(items)))

    candidates: list[int] = []
    for index in pool:
        item = items[index]
        name = str(getattr(item, "name", item) or "")
        stem = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0].lower()
        if re.match(r"^0{4}(?:[_\-\s]|$)", stem):
            continue
        if any(token in stem for token in _NON_BODY_PAGE_TOKENS):
            continue
        candidates.append(index)

    # If naming is unusually aggressive, only keep the explicit 0000_* guard
    # inside the already-approved pool. Manual replacement remains unrestricted.
    if len(candidates) < min(3, len(pool)):
        candidates = []
        for index in pool:
            item = items[index]
            name = str(getattr(item, "name", item) or "")
            stem = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0].lower()
            if not re.match(r"^0{4}(?:[_\-\s]|$)", stem):
                candidates.append(index)
    return candidates or pool


def suggested_body_page_range(images: Iterable[object]) -> str:
    """Suggest a 1-based, zero-padded body-page range for Project Profile.

    The suggestion uses the same conservative filename filtering as automatic
    representative-page sampling. Existing user-entered metadata should always
    take precedence over this initial suggestion.
    """
    items = list(images)
    if not items:
        return ""
    candidates = probable_body_page_indices(items)
    if not candidates:
        return ""
    width = max(4, len(str(len(items))))
    first = min(candidates) + 1
    last = max(candidates) + 1
    return f"{first:0{width}d}-{last:0{width}d}"


def representative_page_indices(
    images: Iterable[object],
    target: int = 6,
    allowed_indices: Iterable[int] | None = None,
) -> list[int]:
    """Pick editable front/middle/back body representatives."""
    pool = probable_body_page_indices(images, allowed_indices)
    target = max(1, int(target))
    if len(pool) <= target:
        return list(pool)

    anchors = (0.12, 0.50, 0.82)
    base, remainder = divmod(target, len(anchors))
    quotas = [base] * len(anchors)
    # Extra samples are most useful around the middle, then front, then back.
    for slot in (1, 0, 2)[:remainder]:
        quotas[slot] += 1

    selected: list[int] = []
    used_positions: set[int] = set()
    last_pos = len(pool) - 1
    for anchor, quota in zip(anchors, quotas):
        center = round(last_pos * anchor)
        offsets = [0]
        for distance in range(1, len(pool)):
            offsets.extend((-distance, distance))
        taken = 0
        for offset in offsets:
            pos = center + offset
            if pos < 0 or pos > last_pos or pos in used_positions:
                continue
            used_positions.add(pos)
            selected.append(pool[pos])
            taken += 1
            if taken >= quota:
                break

    if len(selected) < target:
        for pos, index in enumerate(pool):
            if pos in used_positions:
                continue
            selected.append(index)
            if len(selected) >= target:
                break
    return sorted(selected[:target])

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
    """Return the five user-facing headword types in their fixed UI order."""
    order = (
        "latin_regular",
        "cjk_visual",
        "numbered_prefix",
        "marker_prefixed",
        "custom",
    )
    rank = {key: index for index, key in enumerate(order)}
    profiles = sorted(
        available_dictionary_profiles(),
        key=lambda profile: rank.get(profile.key, len(order)),
    )
    result: list[tuple[str, str]] = []
    for number, profile in enumerate(profiles, start=1):
        label = profile.display_name
        if profile.key == "custom" and custom_name.strip():
            label = f"{custom_name.strip()}（自定义）"
        result.append((f"{number}. {label}", profile.key))
    return result


def recommended_headword_structures(profile_key: str) -> dict[str, bool]:
    """Return human-facing parser defaults for one structure preset."""
    key = str(profile_key or "custom")
    defaults = {
        "ordinary_left_edge": False,
        "cjk_bracketed": False,
        "cjk_single_visual": False,
        "numbered_prefix": False,
        "marker_prefix": False,
    }
    if key in {"latin_regular", "edge_visual_regular", "legacy_spanish_structured", "custom"}:
        defaults["ordinary_left_edge"] = True
    elif key == "cjk_visual":
        defaults["cjk_bracketed"] = True
        defaults["cjk_single_visual"] = True
    elif key == "numbered_prefix":
        defaults["numbered_prefix"] = True
    elif key == "marker_prefixed":
        defaults["marker_prefix"] = True
    else:
        defaults["ordinary_left_edge"] = True
    return defaults


def apply_headword_profile(settings: AppSettings, profile_key: str) -> None:
    """Apply only the headword-recognition dimension of a generic preset."""
    defaults = profile_effective_settings(profile_key, current_language=settings.ocr_language)
    for name in HEADWORD_PROFILE_SETTING_NAMES:
        if name in defaults and hasattr(settings, name):
            setattr(settings, name, defaults[name])
    settings.dictionary_profile_id = profile_key


def apply_headword_tuning(
    settings: AppSettings, profile_key: str, level: int | None = None,
) -> None:
    """Apply small profile-aware precision/recall shifts after preset defaults.

    The Wizard exposes "偏多 / 合适 / 偏少" instead of raw OCR/parser
    thresholds. Positive levels tighten recognition; negative levels loosen it.
    The adjustment is deliberately profile-specific so a marker/prefix dictionary
    is not tuned the same way as a visual CJK or Latin dictionary.
    """
    try:
        key = dictionary_profile_preset(profile_key).key
    except Exception:
        key = str(profile_key or "custom")
    try:
        amount = int(
            getattr(settings, "profile_headword_tuning_level", 0)
            if level is None else level
        )
    except (TypeError, ValueError):
        amount = 0
    amount = max(-2, min(2, amount))
    settings.profile_headword_tuning_level = amount
    if amount == 0:
        return

    if key == "cjk_visual":
        # Bracketed entries and large single-character heads rely on visual
        # prominence much more than POS grammar. Tightening therefore narrows
        # the left-edge zone and strengthens typography evidence.
        settings.paddle_left_tolerance = max(
            10, int(settings.paddle_left_tolerance) - 4 * amount,
        )
        settings.paddle_height_ratio = max(
            1.00, float(settings.paddle_height_ratio) + 0.04 * amount,
        )
        settings.paddle_boldness_ratio = max(
            1.00, float(settings.paddle_boldness_ratio) + 0.05 * amount,
        )
        settings.paddle_min_candidate_score = max(
            0.5, float(settings.paddle_min_candidate_score) + 0.25 * amount,
        )
    elif key in {"latin_regular", "edge_visual_regular", "legacy_spanish_structured"}:
        settings.paddle_left_tolerance = max(
            10, int(settings.paddle_left_tolerance) - 4 * amount,
        )
        settings.paddle_boldness_ratio = max(
            1.00, float(settings.paddle_boldness_ratio) + 0.06 * amount,
        )
        settings.paddle_min_candidate_score = max(
            0.5, float(settings.paddle_min_candidate_score) + 0.50 * amount,
        )
    elif key in {"numbered_prefix", "marker_prefixed"}:
        # Explicit number/marker structure is already strong evidence. Avoid
        # weakening that grammar; only change how far from the column edge a
        # candidate may drift.
        settings.paddle_left_tolerance = max(
            8, int(settings.paddle_left_tolerance) - 3 * amount,
        )
    else:
        settings.paddle_left_tolerance = max(
            10, int(settings.paddle_left_tolerance) - 3 * amount,
        )
        settings.paddle_min_candidate_score = max(
            0.5, float(settings.paddle_min_candidate_score) + 0.35 * amount,
        )


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


def excluded_source_side_percent(settings: AppSettings, page_index: int) -> float:
    """Return the physical page-edge exclusion width for this scan variant."""
    mode = str(getattr(settings, "profile_side_content_mode", "none") or "none")
    if mode in {"outer", "inner"}:
        variant = page_variant(settings, page_index)
        name = "profile_side_percent_a" if variant == "A" else "profile_side_percent_b"
        value = getattr(
            settings, name,
            getattr(settings, "profile_side_percent", 8.0),
        )
    else:
        value = getattr(settings, "profile_side_percent", 8.0)
    try:
        return max(0.0, min(30.0, float(value)))
    except (TypeError, ValueError):
        return 8.0


def effective_page_settings(settings: AppSettings, image_size: tuple[int, int], page_index: int = 0) -> AppSettings:
    """Return a per-page copy with the confirmed page template applied.

    Explicit physical header/footer percentages are converted at one boundary
    only. Modern settings store full-resolution canonical pixels; legacy
    settings receive the old display-scaled representation through the shared
    compatibility helper. Vertical dictionaries keep physical top/bottom masks
    separate from canonical reading-axis V.
    """
    current = replace(settings)
    source_width = max(1, int(image_size[0]))
    source_height = max(1, int(image_size[1]))
    horizontal = (
        str(getattr(current, "layout_writing_mode", "horizontal-tb") or "horizontal-tb")
        == "horizontal-tb"
    )

    header_mode = str(getattr(current, "profile_header_mode", "auto") or "auto")
    if header_mode == "present" and horizontal:
        pct = max(
            0.0, min(35.0, float(getattr(current, "profile_header_percent", 6.0)))
        )
        source_top = round(source_height * pct / 100.0)
        current.start_y = canonical_geometry_to_stored(
            source_top, source_width, current,
        )
        current.paddle_auto_header_rule = False
    elif header_mode == "auto" and horizontal:
        current.paddle_auto_header_rule = True
    else:
        current.paddle_auto_header_rule = False

    footer_mode = str(getattr(current, "profile_footer_mode", "auto") or "auto")
    if footer_mode == "present" and horizontal:
        pct = max(
            0.0, min(35.0, float(getattr(current, "profile_footer_percent", 5.0)))
        )
        source_bottom = round(source_height * (1.0 - pct / 100.0))
        current.bottom_y = canonical_geometry_to_stored(
            source_bottom, source_width, current,
        )
        current.crop_to_bottom_y = True
    elif footer_mode == "auto":
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
    result = image.copy()
    width, height = result.size
    draw = ImageDraw.Draw(result)

    if str(getattr(settings, "profile_header_mode", "auto") or "auto") == "present":
        pct = max(0.0, min(35.0, float(getattr(settings, "profile_header_percent", 6.0))))
        margin = max(0, min(height, round(height * pct / 100.0)))
        if margin > 0:
            draw.rectangle((0, 0, width, margin), fill="white")

    if str(getattr(settings, "profile_footer_mode", "auto") or "auto") == "present":
        pct = max(0.0, min(35.0, float(getattr(settings, "profile_footer_percent", 5.0))))
        margin = max(0, min(height, round(height * pct / 100.0)))
        if margin > 0:
            draw.rectangle((0, max(0, height - margin), width, height), fill="white")

    side = excluded_source_side(settings, page_index)
    if side is not None:
        pct = excluded_source_side_percent(settings, page_index)
        margin = max(0, min(width, round(width * pct / 100.0)))
        if margin > 0:
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
    width, height = source_size

    if str(getattr(settings, "profile_header_mode", "auto") or "auto") == "present":
        pct = max(0.0, min(35.0, float(getattr(settings, "profile_header_percent", 6.0))))
        if source_y < height * pct / 100.0:
            return False
    if str(getattr(settings, "profile_footer_mode", "auto") or "auto") == "present":
        pct = max(0.0, min(35.0, float(getattr(settings, "profile_footer_percent", 5.0))))
        if source_y > height * (1.0 - pct / 100.0):
            return False

    side = excluded_source_side(settings, page_index)
    if side is None:
        return True
    pct = excluded_source_side_percent(settings, page_index)
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
