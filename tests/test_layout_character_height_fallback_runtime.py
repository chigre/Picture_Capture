from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from picture_capture.layout_character_height_runtime import observed_character_height


class _Backend:
    @staticmethod
    def analysis_ink_mask(gray: np.ndarray, _settings: object) -> np.ndarray:
        return np.asarray(gray, dtype=np.uint8) < 128


def test_observed_character_height_recovers_real_row_ink_height() -> None:
    image = Image.new("RGB", (320, 720), "white")
    draw = ImageDraw.Draw(image)
    # Project/fallback says 37 px, but the physical body rows are 58 px tall
    # with an 82 px pitch. This mirrors the failure shape from dense CJK pages.
    for top in range(20, 680, 82):
        draw.rectangle((30, top, 190, top + 57), fill="black")

    estimate = SimpleNamespace(
        character_height=37,
        start_y=0,
        bottom_y=720,
        column_width=220,
        column_starts=(20,),
        columns=1,
        manual_x=20,
        gutter=0,
    )
    observed, stats = observed_character_height(
        image,
        SimpleNamespace(),
        estimate,
        _Backend,
    )

    assert observed == 58
    assert int(stats["samples"]) >= 8
    assert float(stats["spread"]) <= 4.0


def test_observed_character_height_rejects_sparse_ambiguous_page() -> None:
    image = Image.new("RGB", (320, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 20, 190, 77), fill="black")
    draw.rectangle((30, 120, 190, 177), fill="black")

    estimate = SimpleNamespace(
        character_height=37,
        start_y=0,
        bottom_y=300,
        column_width=220,
        column_starts=(20,),
        columns=1,
        manual_x=20,
        gutter=0,
    )
    observed, stats = observed_character_height(
        image,
        SimpleNamespace(),
        estimate,
        _Backend,
    )

    assert observed is None
    assert int(stats["samples"]) < 8


def test_runtime_is_installed_before_any_page_layout_import_can_capture_detector() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    package_init = (root / "src/picture_capture/__init__.py").read_text(encoding="utf-8")
    gui = (root / "src/picture_capture/bootstrap/gui.py").read_text(encoding="utf-8")
    worker = (root / "src/picture_capture/bootstrap/worker.py").read_text(encoding="utf-8")

    # This remains the process-wide compatibility rule during Phase 1C. Package
    # import still prepares character-height recovery before importing processing;
    # removing package import side effects is intentionally a later PR.
    assert package_init.index("install_character_height_fallback_runtime()") < package_init.index(
        "from . import processing as _processing"
    )

    # Both explicit process profiles also document and preserve their local
    # ordering, so Phase 1D can later remove the package-level compatibility path
    # without changing GUI/worker semantics.
    assert gui.index("install_character_height_fallback_runtime()") < gui.index(
        "from .. import dictionary_page_design"
    )
    assert worker.index("install_character_height_fallback_runtime()") < worker.index(
        "from .. import processing as processing_module"
    )
