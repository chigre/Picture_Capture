"""Canonical whole-entry crop plan, illustration pairing and atomic publication.

The public processing_core module retains the long-standing API and dataclass /
pickle identities. All mutable public callback seams are passed to this leaf on
each invocation, without importing processing_core, installing hooks or cloning
a global namespace.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
import json

import numpy as np
from PIL import Image, ImageDraw

from ..models import AppSettings, Entry, PolygonRegion
from ..persistence.page_sections import PageSection

if TYPE_CHECKING:
    from ..processing_core import (
        CropRecord, EntryCropPiecePlan, IllustrationCropPlan, PageCropPlan,
    )


@dataclass(frozen=True)
class CropWorkflowDeps:
    """Live public adapters, services and historical model constructors."""
    EntryCropPiecePlan: object
    IllustrationCropPlan: object
    PageCropPlan: object
    CropRecord: object
    _page_geometry_context: object
    _source_px: object
    entry_crop_bounds: object
    normalize_page_sections: object
    build_reading_lanes: object
    sort_entries_reading_order: object
    _entry_crop_box_for_column: object
    reading_lane_index: object
    column_index: object
    effective_page_settings: object
    illustration_crop_bounds: object
    _normalized_crop_name: object
    polygon_display_name: object
    canonical_polygon_link: object
    _polygon_bbox: object
    polygon_fully_inside_boxes: object
    polygon_intersects_box: object
    _box_intersection_area: object
    illustration_polygon_box: object
    _base_entry_crop_pieces: object
    _stage_text_file: object
    qt_root: object
    page_crop_plan_dict: object
    _publish_file_transaction: object
    _stage_page_crop_plan: object
    _save_crop: object
    clamp_box: object
    prepare_crop_background: object
    normalize_page_rgb: object
    read_page_sections: object
    build_page_crop_plan: object
    read_auxiliary_lines: object
    entry_crop_piece_filename: object
    _stage_crop: object
    _publish_temp_path: object
    _whitefill_polygons: object
    _save_union_crop: object


def _base_entry_crop_pieces(
    deps: CropWorkflowDeps, 
    image: Image.Image, entries: list[Entry], settings: AppSettings,
    *, top_y: int | None = None, bottom_y: int | None = None,
    entry_left_padding: int = 0, entry_right_padding: int = 0,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
) -> tuple[list[Entry], list[EntryCropPiecePlan]]:
    EntryCropPiecePlan = deps.EntryCropPiecePlan
    _page_geometry_context = deps._page_geometry_context
    _source_px = deps._source_px
    entry_crop_bounds = deps.entry_crop_bounds
    normalize_page_sections = deps.normalize_page_sections
    build_reading_lanes = deps.build_reading_lanes
    sort_entries_reading_order = deps.sort_entries_reading_order
    _entry_crop_box_for_column = deps._entry_crop_box_for_column
    reading_lane_index = deps.reading_lane_index
    column_index = deps.column_index
    source, effective, _analysis_source, geometry = _page_geometry_context(
        image, settings, profile_page_index,
    )
    canonical_width = geometry.transform.canonical_size(source.size)[0]
    character_height = _source_px(effective.character_height)
    row_padding = _source_px(effective.row_padding)
    row_height = max(1, character_height + row_padding)
    if page_sections:
        # Explicit page SECTIONs are the authoritative crop range for that page.
        # This lets Section=1 replace the former per-page crop top/bottom override
        # while Section>=2 additionally contributes reading-lane gaps/order.
        sections = normalize_page_sections(page_sections, geometry.top, geometry.bottom)
        top, bottom = sections[0].top_v, sections[-1].bottom_v
    else:
        top, bottom = entry_crop_bounds(
            source, effective, top_y=top_y, bottom_y=bottom_y,
        )
        sections = normalize_page_sections(None, top, bottom)
    column_count = max(1, len(geometry.column_starts))
    lanes = build_reading_lanes(column_count, top, bottom, sections)
    ordered = sort_entries_reading_order(entries, geometry, sections)
    row_guard = round(row_height * 0.6)
    pieces: list[EntryCropPiecePlan] = []
    piece_counts: dict[int, int] = {}

    def lane_box(lane_index: int, y0: int, y1: int) -> tuple[int, int, int, int]:
        lane = lanes[lane_index]
        return _entry_crop_box_for_column(
            source, effective, geometry, lane.column_index, y0, y1,
            extra_left=entry_left_padding, extra_right=entry_right_padding,
        )

    def add(output_index: int, entry_ref: int | None, word: str, box, suffix: str | None = None):
        if box[3] - box[1] <= 1:
            return
        if suffix is None:
            piece_counts[output_index] = piece_counts.get(output_index, 0) + 1
            suffix = f"({piece_counts[output_index]})"
        pieces.append(EntryCropPiecePlan(output_index, entry_ref, word, box, suffix))

    def locate(entry: Entry) -> tuple[int, int]:
        _u, raw_v = geometry.source_to_canonical(entry.x, entry.y)
        column = column_index(entry.x, geometry, entry.y)
        lane_index = reading_lane_index(
            raw_v, column, column_count, top, bottom, sections,
        )
        lane = lanes[lane_index]
        # Markers should normally lie inside a SECTION. If an older PDIC marker
        # sits in a gap, attach it to the nearest lane but never crop the gap.
        clipped_v = max(lane.top_v, min(lane.bottom_v, int(raw_v)))
        return lane_index, clipped_v

    if not ordered:
        for lane_index, lane in enumerate(lanes):
            add(
                0, None, "_上页末词条_",
                lane_box(lane_index, lane.top_v, lane.bottom_v),
                f"(0-{lane_index + 1})",
            )
        return ordered, pieces

    first_lane_index, first_v = locate(ordered[0])
    for lane_index in range(first_lane_index):
        lane = lanes[lane_index]
        add(
            0, None, "_上页末词条_",
            lane_box(lane_index, lane.top_v, lane.bottom_v),
            f"(0-{lane_index + 1})",
        )
    first_lane = lanes[first_lane_index]
    if first_v - first_lane.top_v > row_guard:
        add(
            0, None, "_上页末词条_",
            lane_box(first_lane_index, first_lane.top_v, first_v),
            f"(0-{first_lane_index + 1})",
        )

    for index, entry in enumerate(ordered):
        lane_index, entry_v = locate(entry)
        lane = lanes[lane_index]
        next_entry = ordered[index + 1] if index + 1 < len(ordered) else None
        if next_entry is not None:
            next_lane_index, next_v = locate(next_entry)
        else:
            next_lane_index, next_v = len(lanes), bottom

        y0 = max(lane.top_v, entry_v - abs(row_padding))
        y1 = next_v if next_entry is not None and next_lane_index == lane_index else lane.bottom_v
        add(index, index, entry.word, lane_box(lane_index, y0, y1))

        if next_entry is not None and next_lane_index > lane_index:
            for continuation_lane in range(lane_index + 1, next_lane_index):
                current = lanes[continuation_lane]
                add(
                    index, index, entry.word,
                    lane_box(continuation_lane, current.top_v, current.bottom_v),
                )
            target = lanes[next_lane_index]
            if next_v - target.top_v > row_guard:
                add(
                    index, index, entry.word,
                    lane_box(next_lane_index, target.top_v, next_v),
                )
        elif next_entry is None:
            for continuation_lane in range(lane_index + 1, len(lanes)):
                current = lanes[continuation_lane]
                add(
                    index, index, entry.word,
                    lane_box(continuation_lane, current.top_v, current.bottom_v),
                )
    return ordered, pieces


def build_page_crop_plan(
    deps: CropWorkflowDeps, 
    image: Image.Image, entries: list[Entry], polygons: list[PolygonRegion], settings: AppSettings,
    *, top_y: int | None = None, bottom_y: int | None = None, illustration_margin: int = 0,
    entry_left_padding: int = 0, entry_right_padding: int = 0,
    integrate_illustrations: bool = True, profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None, auxiliary_lines=None,
    page_stem: str | None = None,
    previous_entry_ref: tuple[str, int] | None = None,
) -> PageCropPlan:
    IllustrationCropPlan = deps.IllustrationCropPlan
    PageCropPlan = deps.PageCropPlan
    _page_geometry_context = deps._page_geometry_context
    effective_page_settings = deps.effective_page_settings
    illustration_crop_bounds = deps.illustration_crop_bounds
    _normalized_crop_name = deps._normalized_crop_name
    polygon_display_name = deps.polygon_display_name
    canonical_polygon_link = deps.canonical_polygon_link
    _polygon_bbox = deps._polygon_bbox
    polygon_fully_inside_boxes = deps.polygon_fully_inside_boxes
    polygon_intersects_box = deps.polygon_intersects_box
    _box_intersection_area = deps._box_intersection_area
    illustration_polygon_box = deps.illustration_polygon_box
    _base_entry_crop_pieces = deps._base_entry_crop_pieces
    """Plan entry and PPP crops before any pixels are written.

    Canonical PPP labels link by explicit page + zero-based PDIC ordinal;
    historical free-text labels still link by normalized exact headword.
    PPPs contained by or intersecting their entry crop travel with that entry;
    linked PPPs completely outside become standalone P images. Unlinked PPPs are
    standalone and are removed from ordinary entry crops.
    """
    ordered, pieces = _base_entry_crop_pieces(
        image, entries, settings, top_y=top_y, bottom_y=bottom_y,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        profile_page_index=profile_page_index, page_sections=page_sections,
    )
    auxiliary_gaps: list[tuple[int, int, int, int]] = []
    if auxiliary_lines:
        from .auxiliary_partition import partition_entry_pieces
        _source, _effective, _analysis, geometry = _page_geometry_context(
            image, settings, profile_page_index,
        )
        pieces = partition_entry_pieces(
            pieces, auxiliary_lines, geometry, auxiliary_gaps=auxiliary_gaps,
        )
    boxes_by_entry: dict[int,list[tuple[int,int,int,int]]] = {}
    piece_indices_by_entry: dict[int,list[int]] = {}
    for pos,piece in enumerate(pieces):
        if piece.entry_ref_index is not None:
            boxes_by_entry.setdefault(piece.entry_ref_index,[]).append(piece.box)
            piece_indices_by_entry.setdefault(piece.entry_ref_index,[]).append(pos)
    names: dict[str,list[int]] = {}
    for i,entry in enumerate(ordered): names.setdefault(_normalized_crop_name(entry.word),[]).append(i)
    # Index -1 denotes the existing WW_000 previous-page continuation pieces;
    # it never indexes the current PDIC. Keep the original output filenames.
    previous_positions = [
        pos for pos, piece in enumerate(pieces)
        if piece.entry_ref_index is None and piece.output_index == 0
    ]
    if previous_entry_ref is not None and previous_positions:
        boxes_by_entry[-1] = [pieces[pos].box for pos in previous_positions]
        piece_indices_by_entry[-1] = previous_positions
    effective = effective_page_settings(settings, image.size, profile_page_index)
    illustration_top = effective.start_y if top_y is None else int(top_y)
    illustration_bottom = 0 if bottom_y is None else int(bottom_y)
    top,bottom,margin_px=illustration_crop_bounds(
        image, effective, top_y=illustration_top, bottom_y=illustration_bottom,
        margin=illustration_margin, page_sections=page_sections,
    )
    illustrations: list[IllustrationCropPlan] = []
    linked_inside: dict[int,list[int]] = {}
    partial_merge: dict[int,list[int]] = {}
    for pi,region in enumerate(polygons):
        name=polygon_display_name(region,pi)
        saved_link = canonical_polygon_link(region)
        if saved_link is None:
            candidates = names.get(_normalized_crop_name(name), [])
        else:
            source_page, linked_index = saved_link
            candidates = []
            if linked_index is not None:
                if page_stem is not None and source_page == page_stem and 0 <= linked_index < len(ordered):
                    candidates = [linked_index]
                elif previous_entry_ref == saved_link and previous_positions:
                    candidates = [-1]
        chosen=None; relation="unassociated"
        if candidates:
            scored=[]
            pbox=_polygon_bbox(region)
            for ei in candidates:
                boxes=boxes_by_entry.get(ei,[])
                if polygon_fully_inside_boxes(region.points,boxes): rank=2; rel="contained"
                elif any(polygon_intersects_box(region.points,b) for b in boxes): rank=1; rel="partial"
                else: rank=0; rel="outside"
                overlap=sum(_box_intersection_area(pbox,b) for b in boxes) if pbox else 0
                scored.append((rank,overlap,-ei,ei,rel))
            _rank,_overlap,_neg,chosen,relation=max(scored)
        word = (ordered[chosen].word if chosen is not None and chosen >= 0
                else "_上页末词条_" if chosen == -1 else "")
        box=illustration_polygon_box(image,region,top=top,bottom=bottom,margin_px=margin_px)
        standalone = relation in {"outside", "unassociated"} or (relation == "partial" and not integrate_illustrations)
        illustrations.append(IllustrationCropPlan(pi,name,chosen,word,relation,standalone,box))
        if integrate_illustrations and chosen is not None and relation in {"contained","partial"}:
            linked_inside.setdefault(chosen,[]).append(pi)
        if integrate_illustrations and chosen is not None and relation=="partial":
            pbox=_polygon_bbox(region)
            candidates_pieces=piece_indices_by_entry.get(chosen,[])
            if candidates_pieces:
                best=max(candidates_pieces,key=lambda pos:_box_intersection_area(pbox,pieces[pos].box) if pbox else 0)
                partial_merge.setdefault(best,[]).append(pi)
    illustrated_entries=set(linked_inside)
    if -1 in illustrated_entries:
        for pos in previous_positions:
            pieces[pos].entry_ref_index = -1
    for pos,piece in enumerate(pieces):
        if piece.entry_ref_index in illustrated_entries:
            piece.source_mode="linked_original"
        if pos in partial_merge:
            piece.merge_polygon_indices=tuple(partial_merge[pos])
    return PageCropPlan(
        pieces, illustrations, bool(integrate_illustrations), auxiliary_gaps,
    )


def _stage_page_crop_plan(
    deps: CropWorkflowDeps, 
    root: Path, page_stem: str, plan: PageCropPlan,
) -> tuple[Path, Path]:
    _stage_text_file = deps._stage_text_file
    qt_root = deps.qt_root
    page_crop_plan_dict = deps.page_crop_plan_dict
    folder = qt_root(Path(root)) / "CropPlan"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{page_stem}.json"
    temp = _stage_text_file(
        path, json.dumps(page_crop_plan_dict(plan), ensure_ascii=False, indent=2),
    )
    return temp, path


def write_page_crop_plan(
    deps: CropWorkflowDeps, root: Path, page_stem: str, plan: PageCropPlan) -> Path:
    _publish_file_transaction = deps._publish_file_transaction
    _stage_page_crop_plan = deps._stage_page_crop_plan
    temp, path = _stage_page_crop_plan(root, page_stem, plan)
    _publish_file_transaction([(temp, path)])
    return path


def _whitefill_polygons(
    deps: CropWorkflowDeps, image: Image.Image, polygons: list[PolygonRegion], skip: set[int] | None = None) -> Image.Image:
    out=image.copy().convert("RGB")
    draw=ImageDraw.Draw(out)
    skip=skip or set()
    for i,region in enumerate(polygons):
        if i in skip or len(region.points)<3: continue
        draw.polygon(region.points,fill=(255,255,255))
    return out


def _save_union_crop(
    deps: CropWorkflowDeps, image: Image.Image, path: Path, base_box: tuple[int,int,int,int], regions: list[PolygonRegion], *, transparent_background: bool = False) -> tuple[int,int,int,int]:
    _polygon_bbox = deps._polygon_bbox
    clamp_box = deps.clamp_box
    prepare_crop_background = deps.prepare_crop_background
    boxes=[base_box]+[b for r in regions if (b:=_polygon_bbox(r)) is not None]
    union=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
    union=clamp_box(union,image)
    crop=image.crop(union).convert("RGB")
    mask=Image.new("L",crop.size,0); d=ImageDraw.Draw(mask)
    d.rectangle((base_box[0]-union[0],base_box[1]-union[1],base_box[2]-union[0],base_box[3]-union[1]),fill=255)
    for region in regions:
        d.polygon([(x-union[0],y-union[1]) for x,y in region.points],fill=255)
    white=Image.new("RGB",crop.size,"white"); white.paste(crop,(0,0),mask); path.parent.mkdir(parents=True,exist_ok=True)
    result = prepare_crop_background(white, transparent=True) if transparent_background else white
    try:
        result.save(path, "PNG")
    finally:
        if result is not white:
            result.close()
        crop.close(); mask.close(); white.close()
    return union


def split_whole_entries(
    deps: CropWorkflowDeps, 
    image_path: Path, entries: list[Entry], settings: AppSettings, output_dir: Path,
    *, top_y: int | None = None, bottom_y: int | None = None, polygons: list[PolygonRegion] | None = None,
    entry_left_padding: int = 0, entry_right_padding: int = 0,
    integrate_illustrations: bool = True, profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    transparent_background: bool = False,
    previous_entry_ref: tuple[str, int] | None = None,
) -> list[CropRecord]:
    CropRecord = deps.CropRecord
    _stage_text_file = deps._stage_text_file
    _publish_file_transaction = deps._publish_file_transaction
    _stage_page_crop_plan = deps._stage_page_crop_plan
    _save_crop = deps._save_crop
    normalize_page_rgb = deps.normalize_page_rgb
    read_page_sections = deps.read_page_sections
    build_page_crop_plan = deps.build_page_crop_plan
    read_auxiliary_lines = deps.read_auxiliary_lines
    entry_crop_piece_filename = deps.entry_crop_piece_filename
    _stage_crop = deps._stage_crop
    _publish_temp_path = deps._publish_temp_path
    _whitefill_polygons = deps._whitefill_polygons
    _save_union_crop = deps._save_union_crop
    with Image.open(image_path) as opened:
        image = normalize_page_rgb(opened)
    polygons = list(polygons or [])
    if page_sections is None:
        page_sections = read_page_sections(image_path)
    plan = build_page_crop_plan(
        image, entries, polygons, settings, top_y=top_y, bottom_y=bottom_y,
        entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
        integrate_illustrations=integrate_illustrations,
        profile_page_index=profile_page_index, page_sections=page_sections,
        auxiliary_lines=read_auxiliary_lines(image_path),
        page_stem=image_path.stem, previous_entry_ref=previous_entry_ref,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[CropRecord] = []
    replacements: list[tuple[Path, Path]] = []
    staged: list[Path] = []

    try:
        if not integrate_illustrations:
            for piece in plan.entry_pieces:
                filename = entry_crop_piece_filename(image_path.stem, piece)
                target = output_dir / filename
                saved, temp = _stage_crop(image, target, piece.box, transparent_background=transparent_background)
                staged.append(temp)
                replacements.append((temp, target))
                records.append(CropRecord(
                    image_path.name, piece.output_index, piece.word, filename, saved,
                ))
        else:
            illustrated_entries = sorted({
                p.entry_ref_index for p in plan.entry_pieces
                if p.source_mode == "linked_original" and p.entry_ref_index is not None
            })
            completed_positions: set[int] = set()
            for entry_ref in illustrated_entries:
                keep = {
                    i.polygon_index for i in plan.illustrations
                    if i.associated_entry_index == entry_ref
                    and i.relation in {"contained", "partial"}
                }
                source = _whitefill_polygons(image, polygons, skip=keep)
                try:
                    for pos, piece in enumerate(plan.entry_pieces):
                        if piece.entry_ref_index != entry_ref:
                            continue
                        filename = entry_crop_piece_filename(image_path.stem, piece)
                        target = output_dir / filename
                        temp = _publish_temp_path(target)
                        merge_regions = [
                            polygons[i] for i in piece.merge_polygon_indices
                            if 0 <= i < len(polygons)
                        ]
                        try:
                            if merge_regions:
                                saved_box = _save_union_crop(
                                    source, temp, piece.box, merge_regions,
                                    transparent_background=transparent_background,
                                )
                            else:
                                saved_box = _save_crop(source, temp, piece.box, transparent_background=transparent_background)
                        except Exception:
                            temp.unlink(missing_ok=True)
                            raise
                        staged.append(temp)
                        replacements.append((temp, target))
                        records.append(CropRecord(
                            image_path.name, piece.output_index, piece.word,
                            filename, saved_box,
                        ))
                        completed_positions.add(pos)
                finally:
                    source.close()

            cleaned = _whitefill_polygons(image, polygons)
            try:
                for pos, piece in enumerate(plan.entry_pieces):
                    if pos in completed_positions:
                        continue
                    filename = entry_crop_piece_filename(image_path.stem, piece)
                    target = output_dir / filename
                    saved, temp = _stage_crop(cleaned, target, piece.box, transparent_background=transparent_background)
                    staged.append(temp)
                    replacements.append((temp, target))
                    records.append(CropRecord(
                        image_path.name, piece.output_index, piece.word,
                        filename, saved,
                    ))
            finally:
                cleaned.close()

        by_filename = {r.filename: r for r in records}
        ordered_records: list[CropRecord] = []
        for piece in plan.entry_pieces:
            filename = entry_crop_piece_filename(image_path.stem, piece)
            record = by_filename.get(filename)
            if record is not None:
                ordered_records.append(record)

        manifest = "".join(
            f"{r.page}|{r.index:03d}|{r.word}|{r.filename}\n"
            for r in ordered_records
        )
        manifest_target = output_dir / f"{image_path.stem}.PWWords"
        manifest_temp = _stage_text_file(manifest_target, manifest)
        staged.append(manifest_temp)
        replacements.append((manifest_temp, manifest_target))

        # Natural widths must not be inferred later from already-padded PNGs.
        width_target = output_dir / f"{image_path.stem}.PWWWidths.json"
        width_temp = _stage_text_file(
            width_target,
            json.dumps({
                record.filename: max(1, record.box[2] - record.box[0])
                for record in ordered_records
            }, ensure_ascii=False, sort_keys=True),
        )
        staged.append(width_temp)
        replacements.append((width_temp, width_target))
        plan_temp, plan_target = _stage_page_crop_plan(
            image_path.parent, image_path.stem, plan,
        )
        staged.append(plan_temp)
        replacements.append((plan_temp, plan_target))
        stale = list(output_dir.glob(f"{image_path.stem}_WW_*.png"))
        _publish_file_transaction(replacements, stale_paths=stale)
        return ordered_records
    except Exception:
        for temp in staged:
            temp.unlink(missing_ok=True)
        raise
    finally:
        image.close()
