from __future__ import annotations

"""Pure crop-plan naming and serialization helpers."""

import re
from typing import TYPE_CHECKING
import unicodedata

from .coordinate_space import SOURCE_COORDINATE_SPACE
from .models import PolygonRegion

if TYPE_CHECKING:
    from .processing_core import EntryCropPiecePlan, PageCropPlan


def entry_crop_piece_filename(page_stem: str, piece: EntryCropPiecePlan) -> str:
    """Return the exact output filename used for an entry crop-plan piece."""
    return f"{page_stem}_WW_{piece.output_index:03d}{piece.suffix}.png"


def _normalized_crop_name(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).strip().casefold()
    value = re.sub(r"\s+", " ", value)
    # A PPP may already carry a display suffix such as (P1); it still belongs
    # to the headword before that suffix.
    value = re.sub(r"\s*\(p\d+\)\s*$", "", value, flags=re.I)
    return value


def polygon_display_name(region: PolygonRegion, index: int) -> str:
    label = str(region.label or "").strip()
    fields = label.split("|")
    # New canonical PPP labels start with P_nn|page|entry_id. Legacy
    # page|P_nn|... remains supported for historical crop manifests.
    if len(fields) >= 3 and fields[0].startswith("P_"):
        return fields[0]
    if len(fields) >= 3 and fields[1].strip():
        return fields[1].strip()
    return label or f"P_{index + 1:02d}"


def canonical_polygon_link(region: PolygonRegion) -> tuple[str, int | None] | None:
    """Decode the *saved* P_nn|source_page|zero_based_entry_id[|AUTO_nn].

    The first field is the figure's number, NEVER the word's name or ID.
    'xxx' is an explicitly unlinked figure. An absent canonical pattern is
    legacy PPP and can still use the old exact-headword association path.
    """
    match = re.fullmatch(
        r"P_\d+\|([^|]+)\|(xxx|\d{3})(?:\|AUTO_\d+)?",
        str(region.label or "").strip(), flags=re.I,
    )
    if match is None:
        return None
    token = match.group(2).lower()
    return (match.group(1), None if token == "xxx" else int(token))


def page_crop_plan_dict(plan: PageCropPlan) -> dict:
    return {
        "version": 3,
        "coordinate_space": SOURCE_COORDINATE_SPACE,
        "box_format": "source_xyxy",
        "integrate_illustrations": bool(plan.integrate_illustrations),
        # Gaps are displayed in preview but do not create image records.
        "auxiliary_gaps": [list(box) for box in getattr(plan, "auxiliary_gaps", ())],
        "entry_pieces": [
            {
                "output_index": p.output_index,
                "entry_ref_index": p.entry_ref_index,
                "word": p.word,
                "box": list(p.box),
                "suffix": p.suffix,
                "source_mode": p.source_mode,
                "merge_polygon_indices": list(p.merge_polygon_indices),
            }
            for p in plan.entry_pieces
        ],
        "illustrations": [
            {
                "polygon_index": d.polygon_index,
                "name": d.name,
                "associated_entry_index": d.associated_entry_index,
                "associated_word": d.associated_word,
                "relation": d.relation,
                "standalone": d.standalone,
                "box": list(d.box) if d.box is not None else None,
            }
            for d in plan.illustrations
        ],
    }
