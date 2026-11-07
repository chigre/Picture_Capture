"""OCR-independent oversized CJK ordinary marker reconciliation.

Split-marker suppression and missing-marker rescue stay observationally distinct.
Current core geometry, threshold, sorting and constructor callbacks are injected.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
from PIL import Image
from ..models import AppSettings, Entry
if TYPE_CHECKING:
    from ..processing_core import Geometry


def collapse_oversized_cjk_split_markers(
    image: Image.Image,
    entries: list[Entry],
    geometry: Geometry,
    settings: AppSettings,
    *,
    deps: dict[str, Any],
) -> list[Entry]:
    """Collapse duplicate ordinary markers created *inside* one oversized Han glyph.

    The restored VB detector deliberately knows nothing about OCR semantics. On
    CJK character dictionaries that is usually an advantage, but a display-size
    one-character headword can be roughly two body rows tall. The ordinary scan
    may then find a second apparently valid separator in an internal white/stroke
    gap and emit two markers for one physical entry.

    This post-pass is OCR-independent. It uses only the original page pixels and
    the existing large-CJK left-strip projection detector. It never creates a
    marker and never globally widens Y de-duplication: it removes a lower ordinary
    marker only when both markers are associated with the same visually confirmed
    oversized glyph run. Thus OCR may miss the character completely and ordinary
    mode can still self-correct its own internal duplicate.
    """
    normalize_page_rgb = deps["normalize_page_rgb"]
    np = deps["np"]
    ImageOps = deps["ImageOps"]
    column_index_for_click = deps["column_index_for_click"]
    _left_edge_otsu_threshold = deps["_left_edge_otsu_threshold"]
    sort_entries_reading_order = deps["sort_entries_reading_order"]
    if len(entries) < 2:
        return list(entries)
    if str(getattr(settings, "layout_writing_mode", "horizontal-tb")).startswith("vertical"):
        return list(entries)
    if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
        return list(entries)

    from ..paddle_headwords import (
        _cjk_visual_projection_runs,
        _is_chinese_ocr,
        unwrap_column_band,
    )

    profile_id = str(getattr(settings, "dictionary_profile_id", "") or "").lower()
    if not (_is_chinese_ocr(settings) or "cjk" in profile_id):
        return list(entries)

    source = normalize_page_rgb(image)
    character_height = max(
        2, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    top_margin = max(3, round(character_height * 0.55))
    lower_margin = max(2, round(character_height * 0.15))
    internal_floor = max(3, round(character_height * 0.22))
    strip_width = max(
        100,
        round(character_height * 3.2),
        int(getattr(settings, "paddle_band_left_margin", 0) or 0) + 72,
    )

    rows: list[tuple[Entry, int, int, int]] = []
    for entry in entries:
        u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        col = column_index_for_click(int(entry.x), geometry, int(entry.y))
        rows.append((entry, int(col), int(u), int(v)))
    rows.sort(key=lambda item: (item[1], item[3], item[2]))

    suppressed: set[int] = set()
    keeper_issue: set[int] = set()

    for col in range(len(geometry.column_starts)):
        column_rows = [
            (index, row) for index, row in enumerate(rows)
            if row[1] == col
        ]
        if len(column_rows) < 2:
            continue

        try:
            band, source_top, _left_margin = unwrap_column_band(
                source,
                geometry,
                col,
                settings,
                source_width=strip_width,
            )
        except (IndexError, ValueError):
            continue
        if band.height <= 1 or band.width <= 1:
            continue

        gray = np.asarray(ImageOps.grayscale(band), dtype=np.uint8)
        zone_width, visual_runs = _cjk_visual_projection_runs(
            gray,
            0,
            settings,
            1.0,
            relaxed=False,
        )

        # A large Han glyph may contain a real horizontal white slit wider than
        # the projection detector's tiny-hole filler. That is exactly where the
        # ordinary VB separator can retrigger. Recover such a split glyph only
        # when the two ink fragments are separated by a *very* small vertical
        # gap and occupy strongly overlapping X columns. This is intentionally
        # much stricter than line spacing, so two normal adjacent text rows stay
        # separate.
        projection_width = min(
            gray.shape[1],
            max(48, int(zone_width or 0), 100),
        )
        if projection_width > 0:
            projection = gray[:, :projection_width]
            threshold = _left_edge_otsu_threshold(projection)
            dark = projection <= threshold
            active = dark.sum(axis=1) >= max(
                3, round(projection_width * 0.015)
            )
            active_list = active.tolist()
            raw_runs: list[tuple[int, int]] = []
            index = 0
            while index < len(active_list):
                if not active_list[index]:
                    index += 1
                    continue
                end = index + 1
                while end < len(active_list) and active_list[end]:
                    end += 1
                raw_runs.append((index, end))
                index = end

            bridge_gap = max(2, round(character_height * 0.18))
            bridged: list[tuple[int, int]] = []
            for start, end in raw_runs:
                if not bridged:
                    bridged.append((start, end))
                    continue
                prev_start, prev_end = bridged[-1]
                gap = start - prev_end
                should_bridge = False
                if 0 <= gap <= bridge_gap:
                    prev_cols = dark[prev_start:prev_end].any(axis=0)
                    next_cols = dark[start:end].any(axis=0)
                    smaller = min(
                        int(prev_cols.sum()), int(next_cols.sum())
                    )
                    overlap = int((prev_cols & next_cols).sum())
                    overlap_ratio = (
                        overlap / float(smaller) if smaller > 0 else 0.0
                    )
                    should_bridge = overlap_ratio >= 0.65
                if should_bridge:
                    bridged[-1] = (prev_start, end)
                else:
                    bridged.append((start, end))

            minimum_large = max(
                round(character_height * 1.55),
                character_height + 1,
            )
            for start, end in bridged:
                if end - start < minimum_large:
                    continue
                if not any(
                    max(start, existing_start) < min(end, existing_end)
                    for existing_start, existing_end in visual_runs
                ):
                    visual_runs.append((start, end))
            visual_runs.sort()

        if not visual_runs:
            continue

        for run_start, run_end in visual_runs:
            run_start_v = int(source_top + run_start)
            run_end_v = int(source_top + run_end)
            run_height = max(1, run_end_v - run_start_v)
            if run_height < round(character_height * 1.45):
                continue

            # The true entry separator is normally just above the display glyph;
            # the false VB separator is lower, inside the glyph's vertical span.
            # Associate only rows around this one run and require a top boundary
            # before suppressing anything.
            associated: list[tuple[int, tuple[Entry, int, int, int]]] = []
            for row_index, row in column_rows:
                row_v = row[3]
                if (
                    run_start_v - top_margin
                    <= row_v
                    <= run_end_v + lower_margin
                ):
                    associated.append((row_index, row))
            if len(associated) < 2:
                continue
            associated.sort(key=lambda item: item[1][3])

            keeper_index, keeper_row = associated[0]
            keeper_v = keeper_row[3]
            if keeper_v > run_start_v + max(2, round(character_height * 0.25)):
                # No credible top-of-glyph boundary: do not infer an entry from
                # a large dark object or a title/illustration.
                continue

            local_losers = [
                (row_index, row)
                for row_index, row in associated[1:]
                if (
                    row[3] >= run_start_v + internal_floor
                    and row[3] <= run_end_v + lower_margin
                )
            ]
            if not local_losers:
                continue

            for row_index, _row in local_losers:
                suppressed.add(row_index)
            keeper_issue.add(keeper_index)

    output: list[Entry] = []
    for index, (entry, _col, _u, _v) in enumerate(rows):
        if index in suppressed:
            continue
        if index in keeper_issue:
            issue = "ORDINARY_OVERSIZED_CJK_SPLIT_COLLAPSED"
            existing = [
                part for part in str(entry.issue_type or "").split(",") if part
            ]
            if issue not in existing:
                existing.append(issue)
                entry.issue_type = ",".join(existing)
        output.append(entry)

    return sort_entries_reading_order(output, geometry)


def recover_oversized_cjk_missing_markers(
    image: Image.Image,
    entries: list[Entry],
    geometry: Geometry,
    settings: AppSettings,
    *,
    deps: dict[str, Any],
) -> list[Entry]:
    """Recover a missed oversized CJK entry from independent image evidence.

    This is deliberately narrower than the OCR visual-rescue path: ordinary
    mode has no recognized word to validate, so a new blank marker is added only
    when three geometry cues agree — an oversized left-strip run, a sparse
    right-side layout characteristic of display heads, and a plausible roughly
    square glyph footprint. Existing markers always win.

    The rescue is OCR-independent and therefore also gives combined mode a
    genuinely independent observation when Paddle misses a large Han head.
    """
    normalize_page_rgb = deps["normalize_page_rgb"]
    np = deps["np"]
    ImageOps = deps["ImageOps"]
    column_index_for_click = deps["column_index_for_click"]
    _left_edge_otsu_threshold = deps["_left_edge_otsu_threshold"]
    _ordinary_source_column_edge = deps["_ordinary_source_column_edge"]
    sort_entries_reading_order = deps["sort_entries_reading_order"]
    Entry = deps["Entry"]
    if str(getattr(settings, "layout_writing_mode", "horizontal-tb")).startswith("vertical"):
        return list(entries)
    if not bool(getattr(settings, "profile_cjk_allow_single_headword", True)):
        return list(entries)

    from ..paddle_headwords import (
        _cjk_right_context_metrics,
        _cjk_visual_projection_runs,
        _is_chinese_ocr,
        refine_separator_y_adaptive,
        unwrap_column_band,
    )

    profile_id = str(getattr(settings, "dictionary_profile_id", "") or "").lower()
    if not (_is_chinese_ocr(settings) or "cjk" in profile_id):
        return list(entries)

    source = normalize_page_rgb(image)
    character_height = max(
        2, int(round(float(getattr(settings, "character_height", 26) or 26)))
    )
    row_padding = max(0, int(round(float(getattr(settings, "row_padding", 0) or 0))))
    strip_width = max(
        100,
        round(character_height * 3.2),
        int(getattr(settings, "paddle_band_left_margin", 0) or 0) + 72,
    )
    # Recovery needs both the left projection *and* independent right-context
    # evidence.  Keep a wider analysis band than the projection zone itself.
    analysis_width = max(strip_width, round(character_height * 6.0), 180)
    duplicate_tolerance = max(5, round(character_height * 0.65))

    existing_by_column: dict[int, list[int]] = {
        col: [] for col in range(len(geometry.column_starts))
    }
    for entry in entries:
        _u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        col = column_index_for_click(int(entry.x), geometry, int(entry.y))
        existing_by_column.setdefault(int(col), []).append(int(v))

    recovered = list(entries)
    for col in range(len(geometry.column_starts)):
        try:
            band, source_top, _left_margin = unwrap_column_band(
                source,
                geometry,
                col,
                settings,
                source_width=analysis_width,
            )
        except (IndexError, ValueError):
            continue
        if band.height <= 1 or band.width <= 1:
            continue

        gray = np.asarray(ImageOps.grayscale(band), dtype=np.uint8)
        zone_width, visual_runs = _cjk_visual_projection_runs(
            gray, 0, settings, 1.0, relaxed=False,
        )
        if not visual_runs or zone_width <= 0:
            continue

        for run_index, (run_start, run_end) in enumerate(visual_runs):
            run_height = max(1, int(run_end) - int(run_start))
            if run_height < round(character_height * 1.50):
                continue

            context = _cjk_right_context_metrics(
                gray, (run_start, run_end), zone_width, settings, header_cutoff=0,
            )
            if not (
                context.get("available")
                and context.get("sparse")
                and int(context.get("sparse_votes", 0) or 0) >= 2
                and float(context.get("baseline_ink_density", 0.0) or 0.0) >= 0.01
            ):
                continue

            # Large Han display glyphs are approximately square. Reject long
            # rules, illustrations and narrow vertical artifacts that can also
            # create a tall left-strip projection.
            projection_width = min(gray.shape[1], max(1, int(zone_width)))
            roi = gray[max(0, run_start):min(gray.shape[0], run_end), :projection_width]
            if roi.size == 0:
                continue
            threshold = _left_edge_otsu_threshold(roi)
            dark = roi <= threshold
            active_columns = np.where(dark.any(axis=0))[0]
            if active_columns.size == 0:
                continue
            glyph_width = max(1, int(active_columns[-1] - active_columns[0] + 1))
            aspect = float(run_height) / float(glyph_width)
            if not 0.55 <= aspect <= 2.20:
                continue

            previous_end = (
                int(visual_runs[run_index - 1][1])
                if run_index > 0 else 0
            )
            preceding_gap = max(0, int(run_start) - previous_end)
            coarse_band_y = max(0, int(run_start) - row_padding)
            refined_band_y, _details = refine_separator_y_adaptive(
                gray,
                coarse_band_y,
                max(2, character_height),
                settings,
                pixel_scale=1.0,
                lower_bound=0,
                content_top=int(run_start),
                preceding_gap_hint=preceding_gap,
            )
            candidate_v = int(source_top + refined_band_y)
            run_specific_tolerance = max(
                duplicate_tolerance, round(run_height * 0.30)
            )
            if any(
                abs(candidate_v - existing_v) <= run_specific_tolerance
                for existing_v in existing_by_column.get(col, [])
            ):
                continue

            marker_x, _direction = _ordinary_source_column_edge(
                geometry, col, candidate_v
            )
            recovered.append(Entry(
                word="",
                x=int(marker_x),
                y=int(candidate_v),
                ocr_source="ordinary_visual",
                issue_type="ORDINARY_CJK_VISUAL_RESCUE",
                ocr_visual_run_height=float(run_height),
                ocr_line_height_reference=float(character_height),
                ocr_single_cjk=True,
                ocr_oversized_cjk=True,
            ))
            existing_by_column.setdefault(col, []).append(candidate_v)

    return sort_entries_reading_order(recovered, geometry)
