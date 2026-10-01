from __future__ import annotations

import inspect
from types import SimpleNamespace

from PIL import Image

from picture_capture import layout_visualization_shared, processing
from picture_capture.models import AppSettings, Entry


class _IdentityTransform:
    def canonical_to_source_point(self, x: int, y: int, _size):
        return int(x), int(y)


def _line(y0: int, role: str) -> SimpleNamespace:
    return SimpleNamespace(y0=y0, y1=y0 + 12, role=role)


def _understanding(
    roles: list[str],
    *,
    with_columns: bool = True,
    physical_reliable: bool = True,
):
    lines = [_line(20 + index * 30, role) for index, role in enumerate(roles)]
    columns = [SimpleNamespace(left=10, right=210, lines=lines)] if with_columns else []
    layout = SimpleNamespace(
        columns=columns,
        body_top=100,
        body_bottom=500,
        source_size=(800, 1000),
        transform=_IdentityTransform(),
    )
    return SimpleNamespace(
        layout=layout,
        physical_reliable=physical_reliable,
    )


def _patch_ordinary_dependencies(monkeypatch, understanding, *, vb_calls: list[int]) -> None:
    geometry = SimpleNamespace()
    monkeypatch.setattr(
        processing,
        "_understand_page_current",
        lambda *_args, **_kwargs: understanding,
    )
    monkeypatch.setattr(
        processing,
        "_geometry_from_page_understanding",
        lambda _understanding: geometry,
    )
    monkeypatch.setattr(
        processing,
        "_allowed_entries",
        lambda entries, *_args, **_kwargs: list(entries),
    )
    monkeypatch.setattr(
        processing._core,
        "sort_entries_reading_order",
        lambda entries, _geometry, _sections: list(entries),
    )

    def vb_fallback(*_args, **_kwargs):
        vb_calls.append(1)
        return [Entry(word="", x=1, y=2, ocr_source="vb_fallback")], geometry

    monkeypatch.setattr(processing, "_ordinary_vb_fallback", vb_fallback)


def test_ordinary_draws_only_entry_roles(monkeypatch) -> None:
    understanding = _understanding(["body", "entry", "body", "entry"])
    vb_calls: list[int] = []
    _patch_ordinary_dependencies(monkeypatch, understanding, vb_calls=vb_calls)

    entries, _geometry = processing.detect_entries(
        Image.new("RGB", (800, 1000), "white"),
        AppSettings(detection_method="left_edge"),
    )

    assert [entry.y for entry in entries] == [150, 210]
    assert 120 not in {entry.y for entry in entries}
    assert 180 not in {entry.y for entry in entries}
    assert all(
        entry.ocr_source == "page_understanding:ordinary_layout_role"
        for entry in entries
    )
    assert vb_calls == []


def test_zero_entry_layout_does_not_fall_back_to_vb(monkeypatch) -> None:
    understanding = _understanding(["body", "body", "body"])
    vb_calls: list[int] = []
    _patch_ordinary_dependencies(monkeypatch, understanding, vb_calls=vb_calls)

    entries, _geometry = processing.detect_entries(
        Image.new("RGB", (800, 1000), "white"),
        AppSettings(detection_method="left_edge"),
    )

    assert entries == []
    assert vb_calls == []


def test_physical_reliable_is_not_an_ordinary_routing_gate(monkeypatch) -> None:
    understanding = _understanding(
        ["body", "entry", "body"],
        physical_reliable=False,
    )
    vb_calls: list[int] = []
    _patch_ordinary_dependencies(monkeypatch, understanding, vb_calls=vb_calls)

    entries, _geometry = processing.detect_entries(
        Image.new("RGB", (800, 1000), "white"),
        AppSettings(detection_method="left_edge"),
    )

    assert [entry.y for entry in entries] == [150]
    assert vb_calls == []


def test_vb_is_only_used_when_layout_has_no_columns(monkeypatch) -> None:
    understanding = _understanding([], with_columns=False)
    vb_calls: list[int] = []
    _patch_ordinary_dependencies(monkeypatch, understanding, vb_calls=vb_calls)

    entries, _geometry = processing.detect_entries(
        Image.new("RGB", (800, 1000), "white"),
        AppSettings(detection_method="left_edge"),
    )

    assert vb_calls == [1]
    assert [entry.ocr_source for entry in entries] == ["vb_fallback"]


def test_spawn_job_uses_canonical_processing_detect_entries() -> None:
    source = inspect.getsource(processing.detect_entries_job)

    assert "entries, _geometry = detect_entries(" in source
    assert "ordinary_layout_worker" not in source
    assert "build_ordinary_layout_primary" not in source


def test_layout_visualization_shares_processing_understanding_entrypoint() -> None:
    source = inspect.getsource(layout_visualization_shared.shared_snapshot_for_app)

    assert "_understand_page_current(" in source
    assert "remember_visualized_understanding" not in source
