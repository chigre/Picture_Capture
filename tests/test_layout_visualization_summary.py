from __future__ import annotations

from types import SimpleNamespace

from picture_capture.layout_visualization_summary import _format_summary, _summary_anchor


class _Geometry:
    top = 100
    bottom = 900
    source_size = (1200, 1600)
    column_starts = [50, 430]
    column_widths = [340, 340]

    def x_at(self, column: int, y: int) -> int:
        if column == 0:
            return 50 if y == self.top else 54
        return 430 if y == self.top else 434

    def canonical_to_source(self, x: int, y: int) -> tuple[int, int]:
        return x, y


class _App:
    view_scale = 2.0
    image = SimpleNamespace(size=(1200, 1600))

    def _current_effective_profile_settings(self):
        return SimpleNamespace(
            layout_transform="identity",
            layout_writing_mode="horizontal-tb",
            layout_text_direction="ltr",
            columns=2,
            start_y=100,
            manual_x=50,
            column_width=340,
            gutter=40,
            character_height=26,
            row_padding=2,
        )


def _snapshot():
    return SimpleNamespace(
        geometry=_Geometry(),
        method="reliable_fusion+paddle+projection",
        confidence=0.91,
        auto_enabled=True,
        applied_fields={"start_y": 100, "manual_x": 50},
        raw_estimate={
            "columns": 2,
            "start_y": 100,
            "manual_x": 50,
            "column_width": 350,
            "gutter": 40,
            "character_height": 27,
            "row_padding": 2,
        },
        used_values={
            "columns": 2,
            "start_y": 100,
            "bottom_y": 900,
            "manual_x": 50,
            "column_width": 340,
            "gutter": 40,
            "character_height": 26,
            "row_padding": 2,
        },
    )


def test_summary_anchor_is_centered_in_first_column_at_five_line_heights() -> None:
    x, y = _summary_anchor(_App(), _snapshot())
    # body_top=100; five 26-px line heights -> canonical y=230.
    assert y == 230 * 2.0
    # At y=230 the first-column left track is x=54; centre is 54 + 340/2.
    assert x == (54 + 170) * 2.0


def test_detailed_summary_contains_geometry_gutters_and_raw_used_state() -> None:
    text = _format_summary(_App(), _snapshot())
    assert "method=reliable_fusion+paddle+projection" in text
    assert "body: top=100   bottom=900   height=800" in text
    assert "C1: left(top/bottom)=50/54" in text
    assert "C2: left(top/bottom)=430/434" in text
    assert "G1: width(top/bottom)=40/40" in text
    assert "column_width: used=340   raw=350   RAW ONLY" in text
    assert "start_y: used=100   raw=100   APPLIED" in text
