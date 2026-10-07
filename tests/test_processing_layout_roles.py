from __future__ import annotations

import inspect
from types import SimpleNamespace

from PIL import Image

from picture_capture import layout_physical_indent, layout_visualization_shared, processing
from picture_capture.entry_classification import register_layout_line_classification
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
        ordinary_line_height=20.0,
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


def test_static_materializer_uses_large_head_classification_for_ocr_hints() -> None:
    understanding = _understanding(["entry"])
    line = understanding.layout.columns[0].lines[0]
    evidence = Entry(
        word="",
        x=10,
        y=120,
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=64.0,
        ocr_oversized_cjk=True,
    )
    registered = register_layout_line_classification(line, evidence)
    assert registered.entry_source == "large_head"
    assert registered.entry_scale == "oversized"
    assert registered.detected_head_height == 64.0

    entries = processing._ordinary_entries_from_layout_roles(understanding)

    assert len(entries) == 1
    entry = entries[0]
    assert (entry.x, entry.y) == (10, 120)
    assert entry.ocr_oversized_cjk is True
    assert entry.ocr_single_cjk is True
    assert entry.ocr_visual_run_height == 64.0
    assert entry.ocr_line_height_reference == 20.0


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

    assert "entries, _geometry = processing_module.detect_entries(" in source
    assert "ordinary_layout_worker" not in source
    assert "build_ordinary_layout_primary" not in source


def test_layout_visualization_shares_processing_understanding_entrypoint() -> None:
    impl = inspect.getsource(layout_visualization_shared._shared_snapshot_for_app_impl)
    public = inspect.getsource(layout_visualization_shared.shared_snapshot_for_app)

    assert "_understand_page_current(" in impl
    assert "remember_visualized_understanding" not in impl
    assert "capture_layout_rows(" in public
    assert "_shared_snapshot_for_app_impl(app)" in public


def test_layout_runtime_does_not_replace_canonical_entry_materializer() -> None:
    runtime_source = inspect.getsource(layout_physical_indent)
    install_source = inspect.getsource(layout_physical_indent.install_physical_indent_inference)

    assert "_install_processing_entry_materializer" not in runtime_source
    assert "_ENTRY_Y_BY_UNDERSTANDING" not in runtime_source
    assert "processing._ordinary_entries_from_layout_roles" not in install_source

    signature = inspect.signature(processing._ordinary_entries_from_layout_roles)
    assert "image" in signature.parameters
    assert "page_index" in signature.parameters
    assert signature.parameters["page_index"].kind is inspect.Parameter.KEYWORD_ONLY


def test_phase6d_processing_import_keeps_core_left_edge_native() -> None:
    assert (
        processing._core._detect_entries_left_edge
        is processing._original_detect_entries_left_edge
    )


def test_phase6d_processing_fallback_injects_enhanced_left_edge(monkeypatch) -> None:
    seen = {}
    geometry = SimpleNamespace()

    monkeypatch.setattr(
        processing,
        "_understand_page_current",
        lambda *_args, **_kwargs: None,
    )

    def fake_core_detect(*_args, **kwargs):
        seen.update(kwargs)
        return [], geometry

    monkeypatch.setattr(processing._core, "detect_entries", fake_core_detect)

    entries, returned_geometry = processing.detect_entries(
        Image.new("RGB", (120, 160), "white"),
        AppSettings(detection_method="combined"),
    )

    assert entries == []
    assert returned_geometry is geometry
    assert seen["left_edge_detector"] is processing._detect_entries_left_edge


def test_phase6d_core_detect_entries_exposes_optional_left_edge_hook() -> None:
    signature = inspect.signature(processing._core.detect_entries)
    assert "left_edge_detector" in signature.parameters
    assert signature.parameters["left_edge_detector"].default is None
