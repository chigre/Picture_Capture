from __future__ import annotations

from PIL import Image, ImageDraw

from picture_capture.layout_detection import LayoutEstimate
from picture_capture.models import AppSettings
import picture_capture.dictionary_page_layout_policy as policy


def _settings() -> AppSettings:
    return AppSettings(
        columns=2,
        start_y=30,
        manual_x=40,
        column_width=120,
        gutter=20,
        character_height=24,
        row_padding=3,
        layout_columns_policy="fixed",
        profile_header_mode="none",
        profile_footer_mode="none",
        profile_side_content_mode="none",
        ordinary_auto_layout=False,
        ordinary_auto_columns=False,
        ordinary_auto_start_y=False,
        ordinary_auto_manual_x=False,
        ordinary_auto_column_width=False,
        ordinary_auto_gutter=False,
        ordinary_auto_character_height=False,
        ordinary_auto_row_padding=False,
    )


def _estimate() -> LayoutEstimate:
    return LayoutEstimate(
        columns=3,
        start_y=77,
        column_width=90,
        gutter=15,
        manual_x=70,
        bottom_y=470,
        character_height=31,
        row_padding=7,
        source_boxes=20,
        method="projection_fallback",
        canonical_width=500,
        # Pure +30 page translation relative to the fixed 40/180/320 template.
        column_starts=(70, 210, 350),
        column_rights=(160, 300, 440),
    )


def _draw_rows(
    image: Image.Image,
    starts: list[int],
    *,
    body_indent: int = 0,
    translated: int = 0,
) -> None:
    draw = ImageDraw.Draw(image)
    for column_start in starts:
        outer = column_start + translated
        body = outer + body_indent
        y = 44
        for row in range(12):
            # Repeated outer rows establish the entry/physical lane.
            if row in {0, 4, 8}:
                x = outer
            else:
                x = body
            draw.rectangle((x, y, x + 76, y + 13), fill="black")
            y += 20


def test_master_off_uses_project_geometry_without_running_page_estimator(monkeypatch):
    settings = _settings()
    image = Image.new("RGB", (500, 520), "white")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("per-page estimator must not run when master switch is off")

    monkeypatch.setattr(policy, "detect_layout_parameters", forbidden)
    resolved, estimate, applied = policy.resolve_page_layout_policy(image, settings)

    assert estimate is None
    assert applied == {}
    assert resolved.columns == 2
    assert resolved.start_y == 30
    assert resolved.manual_x == 40
    assert resolved.column_width == 120
    assert resolved.gutter == 20
    starts, rights, gutters = policy._policy_geometry(500, resolved, estimate)
    assert starts == [40, 180]
    assert rights == [160, 300]
    assert gutters == [20, 0]


def test_master_on_replaces_only_selected_fields(monkeypatch):
    settings = _settings()
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_start_y = True
    settings.ordinary_auto_manual_x = True
    image = Image.new("RGB", (500, 520), "white")
    fake = _estimate()

    monkeypatch.setattr(policy, "detect_layout_parameters", lambda *_a, **_k: fake)
    resolved, estimate, applied = policy.resolve_page_layout_policy(image, settings)

    assert estimate is fake
    assert applied == {"start_y": 77, "manual_x": 70}
    assert resolved.start_y == 77
    assert resolved.manual_x == 70
    # Unselected fields remain the project/Profile baseline.
    assert resolved.columns == 2
    assert resolved.column_width == 120
    assert resolved.gutter == 20
    assert resolved.character_height == 24

    starts, rights, gutters = policy._policy_geometry(500, resolved, estimate)
    # Only the page origin moved.  Width/gutter were not selected, so the
    # second column remains at the fixed Project pitch instead of inheriting an
    # unrelated absolute start from the projection detector.
    assert starts == [70, 210]
    assert rights == [190, 330]
    assert gutters == [20, 0]


def test_unselected_first_column_x_stays_fixed_even_when_page_estimate_moves(monkeypatch):
    settings = _settings()
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_start_y = True
    settings.ordinary_auto_manual_x = False
    image = Image.new("RGB", (500, 520), "white")
    fake = _estimate()

    monkeypatch.setattr(policy, "detect_layout_parameters", lambda *_a, **_k: fake)
    resolved, estimate, applied = policy.resolve_page_layout_policy(image, settings)
    starts, rights, _gutters = policy._policy_geometry(500, resolved, estimate)

    assert applied == {"start_y": 77}
    assert resolved.manual_x == 40
    assert starts == [40, 180]
    assert rights == [160, 300]


def test_body_indent_auto_x_uses_outer_entry_lane_not_dominant_body_lane(monkeypatch):
    settings = _settings()
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_manual_x = True
    settings.profile_parser_controls_version = 3
    settings.profile_cjk_brackets_in_body = True  # 正文缩进
    image = Image.new("RGB", (360, 300), "white")
    # True physical lanes are 42 / 182 (+2 scan translation).  Most rows start
    # 30 px inward, mimicking 新时代西汉 where raw projection was pulled from
    # Project X=25 to the body lane around X=63.
    _draw_rows(image, [40, 180], body_indent=30, translated=2)
    fake = LayoutEstimate(
        columns=2,
        start_y=30,
        column_width=120,
        gutter=20,
        manual_x=72,
        bottom_y=290,
        character_height=24,
        row_padding=3,
        source_boxes=20,
        method="projection_fallback",
        canonical_width=360,
        column_starts=(72, 212),
        column_rights=(172, 312),
    )
    monkeypatch.setattr(policy, "detect_layout_parameters", lambda *_a, **_k: fake)

    resolved, estimate, applied = policy.resolve_page_layout_policy(image, settings)
    starts, _rights, _gutters = policy._policy_geometry(360, resolved, estimate)

    assert 40 <= resolved.manual_x <= 45
    assert applied["manual_x"] == resolved.manual_x
    assert starts[1] - starts[0] == 140
    assert starts[0] < 55  # never collapse onto the inward body lane at 72


def test_body_indent_x_registration_ignores_persistent_gutter_rule(monkeypatch):
    settings = _settings()
    settings.gutter = 40
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_manual_x = True
    settings.profile_parser_controls_version = 3
    settings.profile_cjk_brackets_in_body = True
    image = Image.new("RGB", (400, 300), "white")
    _draw_rows(image, [40, 200], body_indent=30, translated=2)
    draw = ImageDraw.Draw(image)
    # A persistent central divider must not merge all rows in the second search
    # strip or become a fake line-start family.
    draw.rectangle((179, 30, 181, 289), fill="black")
    fake = LayoutEstimate(
        columns=2,
        start_y=30,
        column_width=120,
        gutter=40,
        manual_x=72,
        bottom_y=290,
        character_height=24,
        row_padding=3,
        source_boxes=20,
        method="projection_fallback",
        canonical_width=400,
        column_starts=(72, 232),
        column_rights=(172, 332),
    )
    monkeypatch.setattr(policy, "detect_layout_parameters", lambda *_a, **_k: fake)

    resolved, estimate, _applied = policy.resolve_page_layout_policy(image, settings)
    starts, _rights, _gutters = policy._policy_geometry(400, resolved, estimate)

    assert 40 <= resolved.manual_x <= 45
    assert starts == [resolved.manual_x, resolved.manual_x + 160]


def test_headword_indent_auto_x_preserves_real_page_translation(monkeypatch):
    settings = _settings()
    settings.ordinary_auto_layout = True
    settings.ordinary_auto_manual_x = True
    settings.profile_parser_controls_version = 3
    settings.profile_cjk_brackets_in_body = False  # 词头缩进
    image = Image.new("RGB", (360, 300), "white")
    # Outer body lane really moved +8 px on this scan.  Sparse headword rows are
    # inward, so registration must keep the genuine page translation.
    _draw_rows(image, [40, 180], body_indent=0, translated=8)
    fake = LayoutEstimate(
        columns=2,
        start_y=30,
        column_width=120,
        gutter=20,
        manual_x=48,
        bottom_y=290,
        character_height=24,
        row_padding=3,
        source_boxes=20,
        method="projection_fallback",
        canonical_width=360,
        column_starts=(48, 188),
        column_rights=(168, 308),
    )
    monkeypatch.setattr(policy, "detect_layout_parameters", lambda *_a, **_k: fake)

    resolved, estimate, applied = policy.resolve_page_layout_policy(image, settings)
    starts, _rights, _gutters = policy._policy_geometry(360, resolved, estimate)

    assert 46 <= resolved.manual_x <= 50
    assert applied["manual_x"] == resolved.manual_x
    assert starts[1] - starts[0] == 140
