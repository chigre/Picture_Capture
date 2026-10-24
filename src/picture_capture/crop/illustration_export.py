"""Transactional export of standalone and associated PPP image crops.

Algorithm owner invoked by the stable processing-core facade. Runtime helpers,
models and transaction writers come from the current caller each invocation.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..models import PolygonRegion, Entry, AppSettings
    from ..processing_core import CropRecord, IllustrationCropEvent, IllustrationSplitResult
    from ..persistence.page_sections import PageSection


def split_illustrations_impl(
    image_path: Path,
    polygons: list[PolygonRegion],
    output_dir: Path,
    settings: AppSettings | None = None,
    *,
    top_y: int = 0,
    bottom_y: int = 0,
    margin: int = 0,
    entries: list[Entry] | None = None,
    entry_left_padding: int = 0,
    entry_right_padding: int = 0,
    integrate_illustrations: bool = True,
    profile_page_index: int = 0,
    page_sections: list[PageSection] | None = None,
    transparent_background: bool = False,
    previous_entry_ref: tuple[str, int] | None = None,
    deps: dict[str, Any],
) -> IllustrationSplitResult:
    """Export only PPPs that are not already carried by an associated entry crop."""
    Image = deps["Image"]
    ImageOps = deps["ImageOps"]
    ImageDraw = deps["ImageDraw"]
    AppSettings = deps["AppSettings"]
    read_page_sections = deps["read_page_sections"]
    build_page_crop_plan = deps["build_page_crop_plan"]
    read_auxiliary_lines = deps["read_auxiliary_lines"]
    CropRecord = deps["CropRecord"]
    IllustrationCropEvent = deps["IllustrationCropEvent"]
    prepare_crop_background = deps["prepare_crop_background"]
    _publish_temp_path = deps["_publish_temp_path"]
    _stage_text_file = deps["_stage_text_file"]
    _stage_page_crop_plan = deps["_stage_page_crop_plan"]
    _publish_file_transaction = deps["_publish_file_transaction"]
    IllustrationSplitResult = deps["IllustrationSplitResult"]
    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    effective_settings = settings or AppSettings()
    if page_sections is None:
        page_sections = read_page_sections(image_path)
    rgb_for_plan = image.convert("RGB")
    try:
        plan = build_page_crop_plan(
            rgb_for_plan, list(entries or []), polygons, effective_settings,
            top_y=top_y, bottom_y=bottom_y, illustration_margin=margin,
            entry_left_padding=entry_left_padding, entry_right_padding=entry_right_padding,
            integrate_illustrations=integrate_illustrations,
            profile_page_index=profile_page_index, page_sections=page_sections,
            auxiliary_lines=read_auxiliary_lines(image_path),
            page_stem=image_path.stem, previous_entry_ref=previous_entry_ref,
        )
    finally:
        rgb_for_plan.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[CropRecord] = []
    events: list[IllustrationCropEvent] = []
    manifest: list[str] = []
    replacements: list[tuple[Path, Path]] = []
    staged: list[Path] = []
    p_counter: dict[int, int] = {}
    try:
        for decision in plan.illustrations:
            region = polygons[decision.polygon_index]
            if not decision.standalone:
                action = (
                    "跳过：已完整包含于词条切图"
                    if decision.relation == "contained"
                    else "跳过：与词条切图部分相交，已合并到词条切图"
                )
                events.append(IllustrationCropEvent(
                    image_path.name, decision.polygon_index + 1, decision.name,
                    decision.associated_word, decision.relation, action, "",
                ))
                manifest.append(
                    f"{decision.polygon_index+1:03d}|{decision.name}|SKIP|"
                    f"{decision.relation}|{decision.associated_word}"
                )
                continue
            box = decision.box
            if box is None:
                events.append(IllustrationCropEvent(
                    image_path.name, decision.polygon_index + 1, decision.name,
                    decision.associated_word, decision.relation,
                    "跳过：超出有效切图范围", "",
                ))
                continue
            crop = image.crop(box)
            mask = Image.new("L", crop.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.polygon([(x-box[0], y-box[1]) for x, y in region.points], fill=255)
            crop.putalpha(mask)
            formatted = prepare_crop_background(crop, transparent=transparent_background)
            if decision.associated_entry_index is not None and decision.associated_entry_index >= 0:
                ei = decision.associated_entry_index
                p_counter[ei] = p_counter.get(ei, 0) + 1
                filename = f"{image_path.stem}_WW_{ei:03d}(P{p_counter[ei]}).png"
            else:
                filename = f"{image_path.stem}_PIC_{decision.polygon_index+1:03d}.png"
            target = output_dir / filename
            temp = _publish_temp_path(target)
            try:
                formatted.save(temp, "PNG")
            except Exception:
                temp.unlink(missing_ok=True)
                raise
            finally:
                crop.close()
                formatted.close()
                mask.close()
            staged.append(temp)
            replacements.append((temp, target))
            label = region.label or (
                f"{image_path.stem}|P_{decision.polygon_index+1:02d}|1|{image_path.stem}|"
            )
            records.append(CropRecord(
                image_path.name, decision.polygon_index + 1,
                decision.associated_word or label, filename, box,
            ))
            if decision.relation == "partial" and not integrate_illustrations:
                action = "单独插图切图（部分超出词条；未综合插图）"
            else:
                action = (
                    "单独插图切图（关联词条外部）"
                    if decision.associated_entry_index is not None
                    else "单独插图切图（未关联词条）"
                )
            events.append(IllustrationCropEvent(
                image_path.name, decision.polygon_index + 1, decision.name,
                decision.associated_word, decision.relation, action, filename,
            ))
            manifest.append(
                f"{decision.polygon_index+1:03d}|{label}|{filename}|"
                f"{decision.relation}|{decision.associated_word}"
            )

        manifest_target = output_dir / f"{image_path.stem}.PPPictures"
        manifest_temp = _stage_text_file(
            manifest_target, "\n".join(manifest) + ("\n" if manifest else ""),
        )
        staged.append(manifest_temp)
        replacements.append((manifest_temp, manifest_target))
        plan_temp, plan_target = _stage_page_crop_plan(
            image_path.parent, image_path.stem, plan,
        )
        staged.append(plan_temp)
        replacements.append((plan_temp, plan_target))
        stale = [
            *output_dir.glob(f"{image_path.stem}_WW_*.png"),
            *output_dir.glob(f"{image_path.stem}_PIC_*.png"),
        ]
        _publish_file_transaction(replacements, stale_paths=stale)
    except Exception:
        for temp in staged:
            temp.unlink(missing_ok=True)
        raise
    finally:
        image.close()
    return IllustrationSplitResult(records, events)
