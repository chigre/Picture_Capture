from types import SimpleNamespace

from picture_capture.ordinary_large_head_runtime import (
    candidate_starts_at_row_front,
    observed_body_line_reference,
)


def _line(y0, y1, first_x, role="body", anchor_x=None):
    return SimpleNamespace(
        y0=y0,
        y1=y1,
        first_x=first_x,
        role=role,
        anchor_x=anchor_x,
    )


def test_observed_body_line_reference_recovers_underestimated_layout_scale():
    # The layout prior is wrong (39 px), but the physical body rows are 58 px.
    lines = [_line(i * 80, i * 80 + 58, 2, "body") for i in range(12)]
    layout = SimpleNamespace(
        ordinary_line_height=39.0,
        columns=[SimpleNamespace(lines=lines)],
    )

    assert observed_body_line_reference(layout) == 58.0


def test_mid_definition_tall_object_cannot_become_large_head():
    column = SimpleNamespace(lines=[
        _line(100, 158, 2, "body", anchor_x=4),
        _line(180, 238, 1, "body", anchor_x=3),
    ])

    # A tall object hundreds of pixels into definition text is not a row-leading
    # headword even if its box otherwise satisfies oversized geometry.
    assert not candidate_starts_at_row_front(
        column,
        (447, 102, 560, 237),
        58.0,
    )


def test_large_head_after_small_prefix_remains_eligible():
    column = SimpleNamespace(lines=[
        _line(100, 158, 0, "body", anchor_x=126),
        _line(180, 238, 1, "body", anchor_x=4),
    ])

    # Superscript/number prefixes may make first_x tiny. The full-height anchor
    # still authorizes a true large glyph at the row start.
    assert candidate_starts_at_row_front(
        column,
        (128, 98, 228, 220),
        58.0,
    )


def test_core_installs_large_head_guard_before_processing_import():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    core = (root / "src/picture_capture/bootstrap/core.py").read_text(encoding="utf-8")
    package = (root / "src/picture_capture/__init__.py").read_text(encoding="utf-8")

    assert core.index("install_ordinary_large_head_runtime()") < core.index(
        "from .. import processing as processing_module"
    )
    assert core.index("install_ordinary_large_head_role_guard()") < core.index(
        "from .. import processing as processing_module"
    )
    assert "install_ordinary_large_head_runtime()" not in package
    assert "install_ordinary_large_head_role_guard()" not in package


def test_column_drift_runtime_never_replaces_large_head_detector():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    drift = (root / "src/picture_capture/layout_column_drift_runtime.py").read_text(
        encoding="utf-8"
    )

    # Column drift owns first-X remeasurement only. Reintroducing an assignment
    # here would silently bypass row-front/strong-oversized guards because Layout
    # Core imports the detector later in the real GUI/spawn path.
    assert "large_head.detect_ordinary_large_head_entries =" not in drift
    assert "ordinary_large_head_evidence as large_head" not in drift


def test_guarded_large_head_detector_reuses_left_safety_without_losing_semantics():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    runtime = (root / "src/picture_capture/ordinary_large_head_runtime.py").read_text(
        encoding="utf-8"
    )

    assert "_analysis_left_for_column" in runtime
    assert "semantic_box" in runtime
    assert "candidate_starts_at_row_front(column, semantic_box, line_height)" in runtime
