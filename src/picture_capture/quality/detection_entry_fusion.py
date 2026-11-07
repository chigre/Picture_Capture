"""Fusion of ordinary source-image separators with OCR-derived entry events.

This full historical implementation accepts live core callbacks per call,
including semantic vetoes, physical whitespace position choices and sort order.
No model classes or persisted fields are recreated or renamed.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
from PIL import Image
if TYPE_CHECKING:
    from ..models import Entry, AppSettings
    from ..processing_core import Geometry
    from ..persistence.page_sections import PageSection


def fuse_detection_entries(
    ordinary_entries: list[Entry],
    ocr_entries: list[Entry],
    geometry: Geometry,
    settings: AppSettings,
    page_sections: list[PageSection] | None = None,
    review_candidates: list[dict] | None = None,
    image: Image.Image | None = None,
    *, deps: dict[str, Any],
) -> list[Entry]:
    """Fuse the two independent detectors at the entry-event level.

    Ordinary drawing is treated as a strong geometric observation, while OCR is
    the semantic observation and an independent rescue path. Evidence-fusion v3
    additionally consults *rejected* OCR review candidates: high-confidence hard
    semantic negatives may veto an unmatched ordinary false positive, while soft
    rejected candidates may lend their recognized lemma to a geometrically valid
    ordinary marker. Nearby accepted observations in the same visual column are
    paired one-to-one;
    unmatched observations from either detector survive.  A final strict Y
    collapse guarantees exactly one marker for one physical entry boundary.

    For ordinary/bracketed entries, the restored VB separator is retained when
    both detectors agree.  A one-Han OCR entry keeps its OCR position because the
    OCR path has a dedicated oversized-CJK adaptive separator refiner that is more
    specific than the ordinary normal-line geometry.
    """
    sort_entries_reading_order = deps["sort_entries_reading_order"]
    _latent_review_rows = deps["_latent_review_rows"]
    column_index_for_click = deps["column_index_for_click"]
    _is_single_cjk_headword = deps["_is_single_cjk_headword"]
    _review_candidate_hard_negative_level = deps["_review_candidate_hard_negative_level"]
    _review_candidate_to_entry = deps["_review_candidate_to_entry"]
    _review_candidate_hard_negative_consensus = deps["_review_candidate_hard_negative_consensus"]
    _entry_with_fused_metadata = deps["_entry_with_fused_metadata"]
    _prefer_ocr_separator_position = deps["_prefer_ocr_separator_position"]
    np = deps["np"]
    ImageOps = deps["ImageOps"]
    normalize_page_rgb = deps["normalize_page_rgb"]
    if not ordinary_entries:
        return sort_entries_reading_order(list(ocr_entries), geometry, page_sections)
    if not ocr_entries and not review_candidates:
        return sort_entries_reading_order(list(ordinary_entries), geometry, page_sections)

    line_height = max(2, int(round(float(getattr(settings, "character_height", 26) or 26))))
    try:
        alignment_ratio = float(getattr(settings, "paddle_alignment_y_tolerance_ratio", 0.45) or 0.45)
    except (TypeError, ValueError):
        alignment_ratio = 0.45
    alignment_ratio = max(0.25, min(0.55, alignment_ratio))
    base_tolerance = max(4, round(line_height * alignment_ratio))
    strict_dedup = max(2, round(line_height * 0.22))
    latent_rows = _latent_review_rows(review_candidates, geometry)

    def axis(entry: Entry) -> tuple[int, int, int]:
        u, v = geometry.source_to_canonical(int(entry.x), int(entry.y))
        col = column_index_for_click(int(entry.x), geometry, int(entry.y))
        return int(col), int(u), int(v)

    ordinary_rows = [(entry, *axis(entry)) for entry in ordinary_entries]
    ocr_rows = [(entry, *axis(entry)) for entry in ocr_entries]
    ordinary_rows.sort(key=lambda row: (row[1], row[3], row[2]))
    ocr_rows.sort(key=lambda row: (row[1], row[3], row[2]))

    # Max-cardinality monotone pairing avoids stealing the only possible
    # OCR partner from a neighboring real headword on dense dictionary pages.
    pair_edges: list[tuple[int, int, int]] = []
    for ordinary_index, (_ordinary, ordinary_col, _ordinary_u, ordinary_v) in enumerate(ordinary_rows):
        for ocr_index, (ocr, ocr_col, _ocr_u, ocr_v) in enumerate(ocr_rows):
            if ocr_col != ordinary_col:
                continue
            tolerance = base_tolerance
            if _is_single_cjk_headword(ocr.word):
                tolerance = max(tolerance, round(line_height * 0.55))
            delta = abs(int(ocr_v) - int(ordinary_v))
            if delta <= tolerance:
                pair_edges.append((delta, ordinary_index, ocr_index))
    from .ordered_marker_matching import match_ordered_markers

    matched_ocr = match_ordered_markers(
        len(ordinary_rows), len(ocr_rows), pair_edges,
    )
    ordinary_to_ocr = dict(matched_ocr)
    used_ocr = {ocr_index for _, ocr_index in matched_ocr}

    # Rejected OCR review candidates are also observations and must be paired
    # one-to-one. Without global assignment, one rejected row could enrich or
    # veto two adjacent ordinary boundaries on dense dictionary pages.
    latent_edges: list[tuple[int, int, int]] = []
    for ordinary_index, (_ordinary, ordinary_col, _ordinary_u, ordinary_v) in enumerate(ordinary_rows):
        if ordinary_index in ordinary_to_ocr:
            continue
        for latent_index, (_candidate, latent_col, latent_v) in enumerate(latent_rows):
            if latent_col != ordinary_col:
                continue
            delta = abs(int(latent_v) - int(ordinary_v))
            if delta <= base_tolerance:
                latent_edges.append((delta, ordinary_index, latent_index))
    # Rejected OCR rows are collected in cache insertion order: sort them by
    # column and canonical reading V before matching, then remap indices.
    latent_order = sorted(range(len(latent_rows)), key=lambda i: (
        latent_rows[i][1], latent_rows[i][2], i,
    ))
    latent_rank = {old: position for position, old in enumerate(latent_order)}
    latent_pairs = match_ordered_markers(
        len(ordinary_rows), len(latent_rows),
        [(delta, ordinary_index, latent_rank[latent_index])
         for delta, ordinary_index, latent_index in latent_edges],
    )
    ordinary_to_latent = {
        ordinary_index: latent_order[rank]
        for ordinary_index, rank in latent_pairs
    }
    used_latent = set(ordinary_to_latent.values())

    # Oversized single-Han heads are taller than one ordinary text row. The
    # ordinary VB detector can therefore fire twice inside the same physical
    # glyph: once at the real entry boundary and once again on a lower ink run.
    # A one-to-one fusion match removes only one of those rows, so the second
    # ordinary-only row used to survive as a false "rescue".
    #
    # Do not solve this by widening global Y de-duplication. Instead, use OCR's
    # own large-glyph geometry to define a *forward occupancy zone* for confirmed
    # oversized single-CJK heads. Only unmatched ordinary rows inside that zone
    # are suppressed. A following OCR headword creates a safety boundary so one
    # large glyph can never swallow the next real entry.
    suppressed_ordinary: set[int] = set()
    suppressed_by_ocr: dict[int, int] = {}

    def oversized_occupancy_span(entry: Entry) -> int:
        normal = float(entry.ocr_line_height_reference or line_height)
        if normal <= 0:
            normal = float(line_height)
        extent_candidates = [
            float(entry.ocr_box_height or 0.0),
            float(entry.ocr_visual_run_height or 0.0),
        ]
        if entry.ocr_leading_height_ratio:
            extent_candidates.append(float(entry.ocr_leading_height_ratio) * normal)
        extent = max(extent_candidates or [0.0])
        oversized = bool(
            entry.ocr_oversized_cjk
            or (
                (entry.ocr_single_cjk or _is_single_cjk_headword(entry.word))
                and extent >= normal * 1.45
            )
        )
        if not oversized:
            return 0
        # Cover the physical glyph plus a small separator margin, but cap the
        # zone so a malformed OCR box cannot consume several following entries.
        return max(
            round(normal * 1.10),
            min(round(normal * 2.80), round(extent + normal * 0.20)),
        )

    for ocr_index, (ocr, ocr_col, _ocr_u, ocr_v) in enumerate(ocr_rows):
        span = oversized_occupancy_span(ocr)
        if span <= 0:
            continue
        upper_v = int(ocr_v) + int(span)
        # Protect the next OCR-confirmed entry in the same column. This is more
        # permissive than a midpoint for the current big glyph but leaves a
        # normal alignment-width guard before the next real headword.
        for next_index in range(ocr_index + 1, len(ocr_rows)):
            _next, next_col, _next_u, next_v = ocr_rows[next_index]
            if next_col != ocr_col:
                if next_col > ocr_col:
                    break
                continue
            next_guard = max(base_tolerance, round(line_height * 0.55))
            upper_v = min(upper_v, int(next_v) - next_guard)
            break
        if upper_v <= int(ocr_v) + strict_dedup:
            continue

        count = 0
        for ordinary_index, (_ordinary, ordinary_col, _ordinary_u, ordinary_v) in enumerate(ordinary_rows):
            if ordinary_index in ordinary_to_ocr or ordinary_col != ocr_col:
                continue
            if int(ocr_v) + strict_dedup < int(ordinary_v) <= upper_v:
                suppressed_ordinary.add(ordinary_index)
                count += 1
        if count:
            suppressed_by_ocr[ocr_index] = count

    separator_gray = (
        np.asarray(ImageOps.grayscale(normalize_page_rgb(image)), dtype=np.uint8)
        if image is not None and ordinary_to_ocr else None
    )
    fused: list[Entry] = []
    for ordinary_index, (ordinary, _ordinary_col, _ordinary_u, _ordinary_v) in enumerate(ordinary_rows):
        ocr_index = ordinary_to_ocr.get(ordinary_index)
        if ocr_index is None:
            if ordinary_index in suppressed_ordinary:
                continue

            # Candidate-level fusion: a rejected OCR row can still carry useful
            # semantics, or in the opposite direction can provide a highly
            # specific negative explanation for an ordinary false positive.
            latent_index = ordinary_to_latent.get(ordinary_index)
            nearest_latent = (
                latent_rows[latent_index][0]
                if latent_index is not None else None
            )

            hard_negative_level = (
                _review_candidate_hard_negative_level(nearest_latent)
                if nearest_latent is not None else ""
            )
            if hard_negative_level:
                # A pristine full-white VB separator is itself strong,
                # independent image evidence. One OCR engine is not enough to
                # erase it; require dual semantic agreement. A weaker
                # brightness-fallback ordinary marker may be vetoed by one
                # exceptionally confident, feature-backed semantic negative.
                ordinary_strength = float(
                    ordinary.confidence if ordinary.confidence is not None else 0.0
                )
                if hard_negative_level == "dual" or ordinary_strength < 0.96:
                    continue

            if nearest_latent is not None:
                latent_entry = _review_candidate_to_entry(nearest_latent)
                if (
                    latent_entry is not None
                    and latent_entry.word
                    and (latent_entry.confidence or 0.0) >= 0.65
                    and not _review_candidate_hard_negative_consensus(nearest_latent)
                ):
                    ordinary = _entry_with_fused_metadata(
                        ordinary, latent_entry, use_semantic_position=False,
                    )
                    issues = [
                        part for part in str(ordinary.issue_type or "").split(",")
                        if part
                    ]
                    if "COMBINED_LATENT_OCR_METADATA" not in issues:
                        issues.append("COMBINED_LATENT_OCR_METADATA")
                        ordinary.issue_type = ",".join(issues)
            fused.append(ordinary)
            continue
        ocr = ocr_rows[ocr_index][0]
        use_semantic_position, ordinary_ws, ocr_ws = _prefer_ocr_separator_position(
            image, ordinary, ocr, geometry, settings, separator_gray,
        )
        merged_entry = _entry_with_fused_metadata(
            ordinary,
            ocr,
            use_semantic_position=use_semantic_position,
        )
        if (
            ordinary_ws is not None
            and ocr_ws is not None
            and abs(float(ordinary_ws) - float(ocr_ws)) >= 0.055
        ):
            issue = "FUSION_WHITESPACE_POSITION_ARBITRATION"
            existing = [
                part for part in str(merged_entry.issue_type or "").split(",") if part
            ]
            if issue not in existing:
                existing.append(issue)
                merged_entry.issue_type = ",".join(existing)
        if suppressed_by_ocr.get(ocr_index):
            issue = "FUSION_OVERSIZED_CJK_ORDINARY_SUPPRESSED"
            existing = [part for part in str(merged_entry.issue_type or "").split(",") if part]
            if issue not in existing:
                existing.append(issue)
                merged_entry.issue_type = ",".join(existing)
        fused.append(merged_entry)

    for ocr_index, (ocr, _col, _u, _v) in enumerate(ocr_rows):
        if ocr_index not in used_ocr:
            if suppressed_by_ocr.get(ocr_index):
                issue = "FUSION_OVERSIZED_CJK_ORDINARY_SUPPRESSED"
                existing = [part for part in str(ocr.issue_type or "").split(",") if part]
                if issue not in existing:
                    existing.append(issue)
                    ocr.issue_type = ",".join(existing)
            fused.append(ocr)

    # Second-stage de-duplication is intentionally tighter than cross-detector
    # pairing.  It catches residual same-boundary duplicates without collapsing
    # genuinely adjacent dictionary entries.
    ranked: list[tuple[Entry, int, int, int]] = []
    for entry in fused:
        col, u, v = axis(entry)
        ranked.append((entry, col, u, v))
    ranked.sort(key=lambda row: (row[1], row[3], row[2]))

    output: list[tuple[Entry, int, int, int]] = []
    for row in ranked:
        if output and row[1] == output[-1][1] and abs(row[3] - output[-1][3]) <= strict_dedup:
            current = output[-1][0]
            incoming = row[0]

            def priority(item: Entry) -> tuple[int, int, float]:
                source = str(item.ocr_source or "")
                return (
                    1 if item.manually_selected else 0,
                    3 if source.startswith("combined:") else (2 if item.word or item.candidate_id or item.final_engine else 1),
                    float(item.confidence if item.confidence is not None else -1.0),
                )

            if priority(incoming) > priority(current):
                output[-1] = row
            continue
        output.append(row)

    return sort_entries_reading_order(
        [row[0] for row in output], geometry, page_sections
    )
