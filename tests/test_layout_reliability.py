from types import SimpleNamespace

import numpy as np
from PIL import Image

from picture_capture.layout_detection import LayoutEstimate
from picture_capture.layout_reliability import _fuse_fixed_geometry, clean_layout_speckles
from picture_capture.models import AppSettings


def _estimate(**overrides):
    values = dict(
        columns=2,
        start_y=130,
        column_width=1202,
        gutter=92,
        manual_x=25,
        bottom_y=3660,
        character_height=49,
        row_padding=4,
        source_boxes=80,
        method="paddle",
        canonical_transform="identity",
        separator_x=1273,
        confidence=1.0,
        canonical_width=2536,
        column_starts=(25, 1319),
        column_rights=(1227, 2520),
    )
    values.update(overrides)
    return LayoutEstimate(**values)


def _settings():
    return AppSettings(
        columns=2,
        layout_columns_policy="fixed",
        layout_column_separator_mode="present",
        layout_transform="identity",
        manual_x=25,
        column_width=1202,
        gutter=92,
        start_y=128,
        character_height=49,
    )


def test_layout_speckle_cleaning_removes_isolated_noise_but_keeps_vertical_rule():
    arr = np.full((120, 120, 3), 255, dtype=np.uint8)
    arr[10:110, 60, :] = 0
    arr[20, 15, :] = 0
    arr[80:82, 95:97, :] = 0
    image = Image.fromarray(arr, mode="RGB")
    backend = SimpleNamespace(_analysis_ink_mask=lambda gray, _settings: gray < 128)

    cleaned = np.asarray(clean_layout_speckles(image, _settings(), backend))

    assert np.all(cleaned[20, 15] == 255)
    assert np.all(cleaned[80:82, 95:97] == 255)
    assert np.all(cleaned[20:100, 60] == 0)


def test_fixed_geometry_rejects_catastrophic_gutter_and_column_start():
    settings = _settings()
    primary = _estimate(
        gutter=9,
        column_width=1158,
        manual_x=38,
        column_starts=(38, 1205),
        separator_x=None,
    )
    secondary = _estimate(gutter=94, manual_x=35, column_starts=(35, 1324), method="projection_fallback")
    white = Image.new("RGB", (2536, 3765), "white")
    backend = SimpleNamespace(
        _analysis_ink_mask=lambda gray, _settings: gray < 128,
        _detect_persistent_vertical_rule=lambda *args, **kwargs: None,
    )

    fused = _fuse_fixed_geometry(primary, secondary, settings, white, backend)

    assert 80 <= fused.gutter <= 110
    assert abs(fused.column_starts[1] - 1319) < 40
    assert "reliable_fusion" in fused.method


def test_special_header_start_y_is_not_forced_back_to_project_default():
    settings = _settings()
    primary = _estimate(start_y=874)
    secondary = _estimate(start_y=868, method="projection_fallback")
    white = Image.new("RGB", (2536, 3765), "white")
    backend = SimpleNamespace(
        _analysis_ink_mask=lambda gray, _settings: gray < 128,
        _detect_persistent_vertical_rule=lambda *args, **kwargs: None,
    )

    fused = _fuse_fixed_geometry(primary, secondary, settings, white, backend)

    assert 850 <= fused.start_y <= 890


def test_separator_track_can_anchor_second_column_on_noisy_page():
    settings = _settings()
    arr = np.full((900, 700, 3), 255, dtype=np.uint8)
    settings.manual_x = 20
    settings.column_width = 300
    settings.gutter = 60
    settings.character_height = 20
    arr[80:850, 350:352, :] = 0
    for y, x in [(120, 330), (210, 365), (420, 344), (610, 370), (760, 338)]:
        arr[y, x, :] = 0
    image = Image.fromarray(arr, mode="RGB")
    primary = LayoutEstimate(
        2, 80, 270, 8, 22, 850, 20, 2, 80,
        method="paddle", canonical_width=700, column_starts=(22, 300), column_rights=(292, 690),
    )
    secondary = LayoutEstimate(
        2, 82, 298, 58, 19, 850, 20, 2, 6,
        method="projection_fallback", canonical_width=700, column_starts=(19, 379), column_rights=(317, 690),
    )
    backend = SimpleNamespace(
        _analysis_ink_mask=lambda gray, _settings: gray < 128,
        _detect_persistent_vertical_rule=lambda *args, **kwargs: None,
    )

    fused = _fuse_fixed_geometry(primary, secondary, settings, image, backend)

    assert fused.separator_x is not None
    assert abs(fused.separator_x - 351) <= 5
    assert 365 <= fused.column_starts[1] <= 390


def test_integral_reuse_matches_four_independent_box_sums():
    """Optimized 5/11/directional neighbourhoods must be pixel-identical."""
    from picture_capture.layout_reliability import _box_sum
    for shape in [(1, 1), (3, 5), (50, 73), (120, 120)]:
        ink = np.random.default_rng(20261014).integers(0, 2, shape, dtype=np.uint8).astype(bool)
        h, w = ink.shape
        padded = np.pad(ink.astype(np.uint8), ((6, 6), (6, 6)))
        integral = np.pad(
            padded.cumsum(axis=0, dtype=np.int32).cumsum(axis=1, dtype=np.int32),
            ((1, 0), (1, 0)),
        )
        for ry, rx in [(2, 2), (5, 5), (6, 0), (0, 6)]:
            y0, x0 = 6 - ry, 6 - rx
            y1, x1 = 7 + ry, 7 + rx
            actual = (
                integral[y1:y1 + h, x1:x1 + w]
                - integral[y0:y0 + h, x1:x1 + w]
                - integral[y1:y1 + h, x0:x0 + w]
                + integral[y0:y0 + h, x0:x0 + w]
            )
            np.testing.assert_array_equal(actual, _box_sum(ink, ry, rx))
