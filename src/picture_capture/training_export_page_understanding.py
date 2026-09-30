from __future__ import annotations

"""Add shared Page Understanding diagnostics to supervised training packages."""

from pathlib import Path
from typing import Any, Callable
import json

from PIL import Image

from .image_utils import normalize_page_rgb
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

        try:
            with Image.open(page) as opened:
                image = normalize_page_rgb(opened)
            understanding = understand_page(
                image,
                settings,
                page_index=page_index,
                page_sections=read_page_sections(Path(page)),
            )
            annotation["page_understanding_diagnostics"] = (
                page_understanding_diagnostics(understanding)
            )
        except Exception as exc:
            annotation["page_understanding_diagnostics"] = {
                "available": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

        annotation_path.write_text(
            json.dumps(annotation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return record

    return export_training_page_with_understanding
