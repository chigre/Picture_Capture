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


def test_runtime_is_installed_before_layout_and_spawn_processing_imports() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    launcher = (root / "src/picture_capture/launcher.py").read_text(encoding="utf-8")
    spawn = (root / "src/picture_capture/spawn_detection_runtime.py").read_text(encoding="utf-8")

    assert launcher.index("install_character_height_fallback_runtime()") < launcher.index(
        "from . import dictionary_page_design"
    )
    assert spawn.index("install_character_height_fallback_runtime()") < spawn.index(
        "from . import processing as processing_module"
    )
