"""Original-resolution ordinary VB page scan and transformed column edges.

All historical caller hooks are provided at call time rather than frozen at import.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
from PIL import Image
from ..models import AppSettings, Entry
from ..persistence.page_sections import PageSection
if TYPE_CHECKING:
    from ..processing_core import Geometry


def source_column_edge(
    geometry: Geometry, column: int, y: int
) -> tuple[int, int]:
    """Return dynamic source-X edge and source reading-right direction."""
    if geometry.transform.kind not in {"identity", "mirror_x"}:
        raise RuntimeError(
            "普通画线仅支持保持原图 Y 轴的横排版面；旋转/竖排页面请使用 OCR 画线。"
        )
    canonical_x = int(round(geometry.x_at(column, int(y))))
    source_x, source_y = geometry.canonical_to_source(canonical_x, int(y))
    next_x, next_y = geometry.canonical_to_source(canonical_x + 1, int(y))
    if int(source_y) != int(y) or int(next_y) != int(y):
        raise RuntimeError("普通画线检测到非水平坐标变换，已停止以避免混用坐标系。")
    direction = 1 if int(next_x) >= int(source_x) else -1
    return int(source_x), direction


def detect_entries_left_edge(
    image: Image.Image,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
    *,
    deps: dict[str, Any],
) -> tuple[list[Entry], Geometry]:
    """Restore the 2016 VB.NET Draw_Auto ordinary-drawing algorithm.

    The complete candidate/separator chain runs directly on original
    full-resolution source pixels:

      dynamic LX(y) -> 微调判距 dark anchor -> IsPoint 2D support ->
      upward separator search -> full-white first -> 999..700 fallback ->
      whitespace correction -> VB separator Y -> optional small modern refine.

    No downsampled analysis image and no scaled coordinate system participates
    in ordinary candidate or separator placement.
    """
    normalize_page_rgb = deps["normalize_page_rgb"]
    derive_geometry = deps["derive_geometry"]
    np = deps["np"]
    ImageOps = deps["ImageOps"]
    _source_px = deps["_source_px"]
    normalize_page_sections = deps["normalize_page_sections"]
    _ordinary_source_column_edge = deps["_ordinary_source_column_edge"]
    _legacy_is_point = deps["_legacy_is_point"]
    _legacy_find_separator_y = deps["_legacy_find_separator_y"]
    Entry = deps["Entry"]
    _collapse_ordinary_oversized_cjk_split_markers = deps["_collapse_ordinary_oversized_cjk_split_markers"]
    _recover_ordinary_oversized_cjk_missing_markers = deps["_recover_ordinary_oversized_cjk_missing_markers"]
    sort_entries_reading_order = deps["sort_entries_reading_order"]
    source = normalize_page_rgb(image)
    geometry = derive_geometry(source, settings)
    rgb = np.asarray(source, dtype=np.uint8)
    rgb_sum = rgb.astype(np.uint16).sum(axis=2)
    gray = np.asarray(ImageOps.grayscale(source), dtype=np.uint8)
    image_height, image_width = rgb_sum.shape[:2]

    body_indent = max(1, _source_px(settings.body_indent))
    character_height = max(1, _source_px(settings.character_height))
    row_padding = int(_source_px(settings.row_padding))
    row_height = max(1, character_height + row_padding)
    horizontal_tolerance = max(0, _source_px(settings.horizontal_tolerance))
    darkness_threshold = max(0, min(765, int(settings.darkness_threshold)))
    support_brightness = max(
        1.0, min(100.0, float(getattr(settings, "dark_area_percent", 90)))
    )
    row_step_multiplier = max(
        0.5, min(3.0, float(getattr(settings, "row_step_multiplier", 1.2)))
    )
    upward_ratio = max(
        0.1, float(getattr(settings, "upward_ratio", 1.5) or 1.5)
    )
    ordinary_right_divisor = max(
        1.0, float(getattr(settings, "ordinary_right_divisor", 1.0) or 1.0)
    )
    white_high = int(getattr(settings, "white_threshold_high", 999))
    white_low = int(getattr(settings, "white_threshold_low", 700))
    whitespace_adjustment = max(
        0, int(getattr(settings, "whitespace_adjustment", 2))
    )

    top = max(0, min(image_height - 1, int(geometry.top)))
    ordinary_bottom = min(image_height, int(geometry.bottom))
    bottom = max(top + 1, ordinary_bottom)

    # SECTION sidecars are the page-specific authority for exceptional body
    # ranges.  Restrict the expensive scan to their outer envelope; the final
    # entry filter below still excludes the gaps between multiple sections.
    if page_sections:
        sections = normalize_page_sections(page_sections, top, bottom)
        if sections:
            top = max(top, min(int(section.top_v) for section in sections))
            bottom = min(bottom, max(int(section.bottom_v) for section in sections))
            bottom = max(top + 1, bottom)

    analysis_left = int(getattr(settings, "analysis_left", 0) or 0)
    analysis_right = int(getattr(settings, "analysis_right", 0) or 0)
    if analysis_right > analysis_left >= 0:
        x_min = max(0, min(image_width - 1, analysis_left))
        x_max = max(x_min, min(image_width - 1, analysis_right))
    else:
        x_min, x_max = 0, image_width - 1

    entries: list[Entry] = []
    for col in range(len(geometry.column_starts)):
        y = top
        while y < bottom:
            edge_x, direction = _ordinary_source_column_edge(geometry, col, y)
            accepted_x: int | None = None

            # Dynamic LX(y) already supplies the modern slope/deformation term;
            # the remaining full-resolution source-pixel lane is 微调判距.
            for offset in range(horizontal_tolerance + 1):
                candidate_x = edge_x + direction * offset
                if candidate_x < x_min or candidate_x > x_max:
                    continue
                if candidate_x < 0 or candidate_x >= image_width:
                    continue
                if int(rgb_sum[y, candidate_x]) >= darkness_threshold:
                    continue
                if _legacy_is_point(
                    rgb_sum,
                    candidate_x,
                    y,
                    body_indent,
                    2 * body_indent,
                    support_brightness,
                    direction=direction,
                ):
                    accepted_x = int(candidate_x)
                    break

            if accepted_x is None:
                y += 2
                continue

            vb_separator_y, _vb_meta = _legacy_find_separator_y(
                rgb_sum,
                accepted_x,
                y,
                column_width=max(1, int(geometry.column_widths[col])),
                direction=direction,
                row_height=row_height,
                upward_ratio=upward_ratio,
                ordinary_right_divisor=ordinary_right_divisor,
                darkness_threshold=darkness_threshold,
                white_threshold_high=white_high,
                white_threshold_low=white_low,
                whitespace_adjustment=whitespace_adjustment,
                top=top,
                x_min=x_min,
                x_max=x_max,
            )

            if vb_separator_y is not None:
                final_y = int(vb_separator_y)

                # Modern enhancement is deliberately post-VB and tightly
                # bounded: it may only nudge an already valid VB separator.
                if settings.paddle_refine_separator_y:
                    from ..paddle_headwords import refine_separator_y
                    refine_edge_x, refine_direction = _ordinary_source_column_edge(
                        geometry, col, final_y
                    )
                    col_width = max(10, int(geometry.column_widths[col]))
                    other_x = refine_edge_x + refine_direction * col_width
                    crop_x0 = max(0, min(refine_edge_x, other_x))
                    crop_x1 = min(image_width, max(refine_edge_x, other_x) + 1)
                    if crop_x1 - crop_x0 > 8:
                        refined_y, _refinement = refine_separator_y(
                            gray[:, crop_x0:crop_x1],
                            final_y,
                            max(2, character_height),
                            settings,
                            pixel_scale=1.0,
                            lower_bound=top,
                        )
                        max_delta = max(2, round(row_height * 0.20))
                        final_y += max(
                            -max_delta,
                            min(max_delta, int(refined_y) - final_y),
                        )

                final_y = min(bottom - 1, max(top, int(final_y)))
                marker_x, _direction = _ordinary_source_column_edge(
                    geometry, col, final_y
                )
                vb_reason = str(_vb_meta.get("reason", "") or "")
                if vb_reason == "vb_full_white":
                    ordinary_confidence = 0.98
                    ordinary_issue = ""
                else:
                    threshold = int(_vb_meta.get("threshold", white_low) or white_low)
                    span = max(1, white_high - white_low)
                    whiteness = max(0.0, min(1.0, (threshold - white_low) / span))
                    ordinary_confidence = 0.76 + 0.18 * whiteness
                    ordinary_issue = "ORDINARY_VB_BRIGHTNESS_FALLBACK"
                entries.append(Entry(
                    word="",
                    x=int(marker_x),
                    y=int(final_y),
                    confidence=float(round(ordinary_confidence, 4)),
                    ocr_source="ordinary_vb",
                    issue_type=ordinary_issue,
                ))

                # VB: y = separatorY + rowHeight * 1.2 (default).
                y = max(
                    y + 2,
                    int(final_y + round(row_height * row_step_multiplier)),
                )
            else:
                # VB still advanced after a confirmed anchor even when neither
                # separator method succeeded; emulate that anti-retrigger step.
                upward = max(1, int(round(row_height / upward_ratio)))
                y = max(
                    y + 2,
                    int(y - upward + round(row_height * row_step_multiplier)),
                )

    entries = _collapse_ordinary_oversized_cjk_split_markers(
        source, entries, geometry, settings,
    )
    entries = _recover_ordinary_oversized_cjk_missing_markers(
        source, entries, geometry, settings,
    )
    return sort_entries_reading_order(entries, geometry), geometry
