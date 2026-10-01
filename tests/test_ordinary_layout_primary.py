from __future__ import annotations

from types import SimpleNamespace

from PIL import Image

from picture_capture import page_understanding
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


def _understanding(
    *,
    roles: list[str],
    physical_reliable: bool = True,
    with_columns: bool = True,
):
    lines = [_line(20 + index * 30, role) for index, role in enumerate(roles)]
    columns = [SimpleNamespace(left=10, lines=lines)] if with_columns else []
    layout = SimpleNamespace(
        columns=columns,
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
    assert [entry.y for entry in entries] == [150, 210]
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


def _fake_processing(*, vb_calls: list[int]):
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
        # Deliberately stale/incorrect. Ordinary routing must never use this
        # bound reference; it must resolve page_understanding.understand_page
        # dynamically after runtime installers have patched the module.
        understand_page=lambda *_args, **_kwargs: _understanding(roles=[]),
        _geometry_from_page_understanding=lambda _understanding: geometry,
        _allowed_entries=lambda entries, *_args, **_kwargs: list(entries),
        _page_template_image=lambda image, _settings, _page_index: image,
        _original_detect_entries_left_edge=vb_detector,
    )


def _install_understanding(monkeypatch, understanding) -> None:
    monkeypatch.setattr(
        page_understanding,
        "understand_page",
        lambda *_args, **_kwargs: understanding,
    )


def _forbidden_original(*_args, **_kwargs):
    raise AssertionError("ordinary layout-primary must not delegate to old pipeline")


def test_successful_layout_primary_never_calls_vb(monkeypatch) -> None:
    understanding = _understanding(roles=["body", "entry", "body"])
    _install_understanding(monkeypatch, understanding)
    vb_calls: list[int] = []
    processing = _fake_processing(vb_calls=vb_calls)

    detect = build_ordinary_layout_primary(processing, _forbidden_original)
    settings = AppSettings(detection_method="left_edge")
    entries, _geometry = detect(Image.new("RGB", (800, 1000), "white"), settings)

    assert len(entries) == 1
    assert entries[0].ocr_source == "page_understanding:ordinary_layout_role"
    assert entries[0].y == 150
    assert vb_calls == []


def test_dynamic_module_function_wins_over_stale_processing_binding(monkeypatch) -> None:
    current = _understanding(roles=["body", "entry", "body"])
    _install_understanding(monkeypatch, current)
    vb_calls: list[int] = []
    processing = _fake_processing(vb_calls=vb_calls)

    # The fake processing object intentionally contains a stale understand_page
    # that returns no columns. If ordinary routing ever regresses to that bound
    # symbol, this test falls into VB instead of returning the entry at Y=150.
    detect = build_ordinary_layout_primary(processing, _forbidden_original)
    entries, _geometry = detect(
        Image.new("RGB", (800, 1000), "white"),
        AppSettings(detection_method="left_edge"),
    )

    assert [entry.y for entry in entries] == [150]
    assert vb_calls == []


def test_layout_roles_remain_authoritative_when_physical_reliable_is_false(monkeypatch) -> None:
    understanding = _understanding(
        roles=["body", "entry", "body"],
        physical_reliable=False,
    )
    _install_understanding(monkeypatch, understanding)
    vb_calls: list[int] = []
    processing = _fake_processing(vb_calls=vb_calls)

    detect = build_ordinary_layout_primary(processing, _forbidden_original)
    settings = AppSettings(detection_method="left_edge")
    entries, _geometry = detect(Image.new("RGB", (800, 1000), "white"), settings)

    assert [entry.y for entry in entries] == [150]
    assert vb_calls == []


def test_zero_entry_layout_returns_zero_markers_without_vb(monkeypatch) -> None:
    understanding = _understanding(roles=["body", "body", "body"])
    _install_understanding(monkeypatch, understanding)
    vb_calls: list[int] = []
    processing = _fake_processing(vb_calls=vb_calls)

    detect = build_ordinary_layout_primary(processing, _forbidden_original)
    settings = AppSettings(detection_method="left_edge")
    entries, _geometry = detect(Image.new("RGB", (800, 1000), "white"), settings)

    assert entries == []
    assert vb_calls == []


def test_vb_runs_only_when_page_understanding_has_no_columns(monkeypatch) -> None:
    understanding = _understanding(roles=[], with_columns=False)
    _install_understanding(monkeypatch, understanding)
    vb_calls: list[int] = []
    processing = _fake_processing(vb_calls=vb_calls)

    detect = build_ordinary_layout_primary(processing, _forbidden_original)
    settings = AppSettings(detection_method="left_edge")
    entries, _geometry = detect(Image.new("RGB", (800, 1000), "white"), settings)

    assert vb_calls == [1]
    assert len(entries) == 1
    assert entries[0].ocr_source == "vb_fallback"


def test_visualized_understanding_is_reused_without_second_inference(monkeypatch) -> None:
    understanding = _understanding(roles=["body", "entry", "body"])
    vb_calls: list[int] = []
    processing = _fake_processing(vb_calls=vb_calls)
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

    monkeypatch.setattr(page_understanding, "understand_page", forbidden_inference)
    detect = build_ordinary_layout_primary(processing, _forbidden_original)

    entries, _geometry = detect(image, settings)

    assert [entry.y for entry in entries] == [150]
    assert vb_calls == []


def test_combined_mode_still_delegates_to_existing_pipeline() -> None:
    vb_calls: list[int] = []
    processing = _fake_processing(vb_calls=vb_calls)
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
