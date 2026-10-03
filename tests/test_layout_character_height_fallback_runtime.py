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
    composition = (
        root / "src/picture_capture/bootstrap/gui.py"
    ).read_text(encoding="utf-8")
    spawn = (root / "src/picture_capture/spawn_detection_runtime.py").read_text(encoding="utf-8")

    # This is the crucial process-wide ordering rule. Importing the package runs
    # __init__.py before the GUI composition root or any spawn target body.
    # __init__ itself imports processing, which imports Page Understanding and
    # the policy module that binds detect_layout_parameters by value.
    assert package_init.index("install_character_height_fallback_runtime()") < package_init.index(
        "from . import processing as _processing"
    )

    # Keep the more local guards too: they document the same contract for GUI
    # composition and for the spawn job body even though package init currently
    # makes the process-level ordering safe first.
    assert composition.index("install_character_height_fallback_runtime()") < composition.index(
        "from .. import dictionary_page_design"
    )
    assert spawn.index("install_character_height_fallback_runtime()") < spawn.index(
        "from . import processing as processing_module"
    )
