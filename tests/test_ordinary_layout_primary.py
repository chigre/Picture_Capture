from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_layout_primary import (
    build_ordinary_layout_primary,
    layout_role_entries,
    remember_visualized_understanding,
)


class _IdentityTransform:
    def canonical_to_source_point(self, x: int, y: int, _size):
        return int(x), int(y)


def _line(y0: int, role: str) -> SimpleNamespace:
    return SimpleNamespace(y0=y0, y1=y0 + 12, role=role)


def _understanding(*, roles: list[str], physical_reliable: bool = True):
    lines = [_line(20 + index * 30, role) for index, role in enumerate(roles)]
    column = SimpleNamespace(left=10, lines=lines)
    layout = SimpleNamespace(
        columns=[column],
        body_top=100,
        body_bottom=500,
        source_size=(800, 1000),
        transform=_IdentityTransform(),
    )
    return SimpleNamespace(
        layout=layout,
        line_height=20.0,
        physical_reliable=physical_reliable,
    )


def test_layout_role_entries_use_only_final_entry_rows() -> None:
    understanding = _understanding(roles=["body", "entry", "body", "entry"])

    entries = layout_role_entries(understanding)

    assert len(entries) == 2
    assert all(entry.x == 10 for entry in entries)
    # LayoutLine.y0 is body-local.  The ordinary marker must land on the exact
    # top of each role=entry row, never at an old midpoint above it.
    assert [entry.y for entry in entries] == [150, 210]
    # Body rows are at source Y 120 and 180 and can never create a marker.
    assert 120 not in {entry.y for entry in entries}
    assert 180 not in {entry.y for entry in entries}
    assert all(
        entry.ocr_source == "page_understanding:ordinary_layout_role"
        for entry in entries
    )
    assert all(
        entry.issue_type == "PAGE_UNDERSTANDING_ORDINARY_LAYOUT_ROLE"
        for entry in entries
    )


def _fake_processing(understanding, *, vb_calls: list[int]):
    geometry = SimpleNamespace()

    def vb_detector(_image, _settings, page_sections=None):
        vb_calls.append(1)
        return [Entry(word="", x=1, y=2, ocr_source="vb_fallback")], geometry

    core = SimpleNamespace(
        normalize_page_rgb=lambda image: image,
        effective_page_settings=lambda settings, _size, _page_index: settings,
        sort_entries_reading_order=lambda entries, _geometry, _sections: list(entries),
    )
    return SimpleNamespace(
        _core=core,
        understand_page=lambda *_args, **_kwargs: understanding,
        _geometry_from_page_understanding=lambda _understanding: geometry,
        _allowed_entries=lambda entries, *_args, **_kwargs: list(entries),
        _ordinary_settings_for_shared_geometry=lambda settings, _geometry, method: settings,
        _page_template_image=lambda image, _settings, _page_index: image,
        _original_detect_entries_left_edge=vb_detector,
    )


def test_successful_layout_primary_never_calls_vb() -> None:
    understanding = _understanding(roles=["body", "entry", "body"])
    vb_calls: list[int] = []
    processing = _fake_processing(understanding, vb_calls=vb_calls)

    def original(*_args, **_kwargs):
        raise AssertionError("ordinary layout-primary must not delegate to old pipeline")

    detect = build_ordinary_layout_primary(processing, original)
    settings = AppSettings(detection_method="left_edge")
    entries, _geometry = detect(Image.new("RGB", (800, 1000), "white"), settings)

    assert len(entries) == 1
    assert entries[0].ocr_source == "page_understanding:ordinary_layout_role"
    assert entries[0].y == 150
    assert vb_calls == []


def test_visualized_understanding_is_reused_without_second_inference() -> None:
    understanding = _understanding(roles=["body", "entry", "body"])
    vb_calls: list[int] = []
    processing = _fake_processing(understanding, vb_calls=vb_calls)
    image = Image.new("RGB", (800, 1000), "white")
    settings = AppSettings(detection_method="left_edge")

    remember_visualized_understanding(
        image,
        settings,
        0,
        None,
        understanding,
    )

    def forbidden_inference(*_args, **_kwargs):
        raise AssertionError("ordinary drawing must reuse the visible Layout snapshot")

    processing.understand_page = forbidden_inference
    detect = build_ordinary_layout_primary(
        processing,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("ordinary layout-primary must not delegate")
        ),
    )

    entries, _geometry = detect(image, settings)

    assert [entry.y for entry in entries] == [150]
    assert vb_calls == []


def test_vb_runs_only_when_layout_has_no_entry_role() -> None:
    understanding = _understanding(roles=["body", "body", "body"])
    vb_calls: list[int] = []
    processing = _fake_processing(understanding, vb_calls=vb_calls)

    detect = build_ordinary_layout_primary(
        processing,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("ordinary fallback must use isolated VB, not old full pipeline")
        ),
    )
    settings = AppSettings(detection_method="left_edge")
    entries, _geometry = detect(Image.new("RGB", (800, 1000), "white"), settings)

    assert len(vb_calls) == 1
    assert len(entries) == 1
    assert entries[0].ocr_source == "vb_fallback"


def test_combined_mode_still_delegates_to_existing_pipeline() -> None:
    understanding = _understanding(roles=["body", "entry"])
    vb_calls: list[int] = []
    processing = _fake_processing(understanding, vb_calls=vb_calls)
    delegated: list[int] = []

    def original(*_args, **_kwargs):
        delegated.append(1)
        return [Entry(word="ocr", x=7, y=8, ocr_source="combined")], SimpleNamespace()

    detect = build_ordinary_layout_primary(processing, original)
    settings = AppSettings(detection_method="combined")
    entries, _geometry = detect(Image.new("RGB", (800, 1000), "white"), settings)

    assert delegated == [1]
    assert vb_calls == []
    assert entries[0].ocr_source == "combined"
