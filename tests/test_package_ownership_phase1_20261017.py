"""Package layout regression: physical modules, no root duplicate imports."""
from pathlib import Path
import importlib


ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"

GROUPS = {
    "quality": (
        "benchmark_provenance",
        "detection_quality_metrics",
        "performance_metrics",
        "ordered_marker_matching",
        "ordinary_verified_evaluation",
        "ordinary_unified_diff",
        "draw_performance_profile",
        "inference_monitor",
        "paddle_diagnostic_formatting",
    ),
    "geometry": (
        "visual_boundary_locator",
        "layout_gutter_rule",
        "layout_percent_helpers",
        "boundary_evidence",
    ),
}


def test_migrated_modules_have_single_physical_package_owner():
    for package, modules in GROUPS.items():
        for name in modules:
            assert (ROOT / package / (name + ".py")).is_file()
            assert not (ROOT / (name + ".py")).exists()
            loaded = importlib.import_module(
                f"picture_capture.{package}.{name}"
            )
            assert Path(loaded.__file__).resolve() == (
                ROOT / package / (name + ".py")
            ).resolve()


def test_quality_and_geometry_public_function_references_still_work():
    from picture_capture.quality.detection_quality_metrics import marker_metrics
    from picture_capture.quality.ordered_marker_matching import match_ordered_markers
    from picture_capture.geometry.layout_percent_helpers import (
        _layout_percent_to_pixels,
    )
    from picture_capture.geometry.visual_boundary_locator import safe_gap_above
    from PIL import Image

    assert match_ordered_markers(2, 2, [(0, 0, 0), (0, 1, 1)]) == [
        (0, 0), (1, 1),
    ]
    assert marker_metrics([(0, 0)], [(0, 0)], 0)["matched"] == 1
    assert _layout_percent_to_pixels(
        Image.new("RGB", (200, 300)), "column_width", 20,
    ) == 40
    assert callable(safe_gap_above)
