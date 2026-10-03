from __future__ import annotations

"""Add shared Page Understanding diagnostics to supervised training packages."""

from pathlib import Path
from typing import Any, Callable
import json

from PIL import Image

from .generic_block_roles import generic_entry_candidates
from .image_utils import normalize_page_rgb
from .layout_illustration_mask_runtime import mask_large_illustrations_for_layout
from .page_sections import read_page_sections
from .page_understanding import (
    page_understanding_diagnostics,
    understand_page,
)


def build_export_training_page_with_understanding(
    original_export_training_page: Callable[..., dict[str, Any]],
):
    """Wrap the existing v3 exporter without changing its correction contract."""

    def export_training_page_with_understanding(
        page: Path,
        project_root: Path,
        settings,
        staging_root: Path,
        page_index: int,
    ) -> dict[str, Any]:
        record = original_export_training_page(
            page, project_root, settings, staging_root, page_index,
        )
        staging_root = Path(staging_root)
        annotation_path = staging_root / str(record["annotation"])
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))

        image: Image.Image | None = None
        analysis_image: Image.Image | None = None
        try:
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            analysis_image, mask_stats = mask_large_illustrations_for_layout(
                image,
                settings,
                profile_page_index=int(page_index),
            )
            understanding = understand_page(
                analysis_image,
                settings,
                page_index=page_index,
                page_sections=read_page_sections(Path(page)),
            )
            diagnostics = page_understanding_diagnostics(understanding)
            diagnostics["layout_illustration_mask"] = {
                "enabled": bool(getattr(settings, "layout_mask_illustrations", False)),
                "detected": int(mask_stats.detected),
                "masked": int(mask_stats.masked),
                "rejected_small": int(mask_stats.rejected_small),
                "rejected_headlike": int(mask_stats.rejected_headlike),
            }
            diagnostics["generic_block_role_model"] = {
                "enabled": bool(
                    understanding.role_model == "generic"
                    and understanding.generic_body_indent_reliable
                    and understanding.layout.indent_type == "body"
                ),
                "association": "next_visual_block_after_separator",
                "entry_candidate_count": len(
                    generic_entry_candidates(understanding)
                ),
            }
            annotation["page_understanding_diagnostics"] = diagnostics
        except Exception as exc:
            annotation["page_understanding_diagnostics"] = {
                "available": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        finally:
            if analysis_image is not None and analysis_image is not image:
                try:
                    analysis_image.close()
                except Exception:
                    pass
            if image is not None:
                try:
                    image.close()
                except Exception:
                    pass

        annotation_path.write_text(
            json.dumps(annotation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return record

    return export_training_page_with_understanding
