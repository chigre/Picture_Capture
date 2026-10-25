"""Issue #562 round 14: nominal and deformable geometry ownership."""
from __future__ import annotations

import inspect
from pathlib import Path

from PIL import Image
from picture_capture import processing as facade
from picture_capture import processing_core as core
from picture_capture.geometry import geometry_construction
from picture_capture.models import AppSettings

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def settings(*, deform=False, transform="identity"):
    value = AppSettings()
    value.columns = 2
    value.manual_x = 10
    value.column_width = 40
    value.gutter = 15
    value.start_y = 10
    value.bottom_y = 85
    value.crop_to_bottom_y = True
    value.follow_column_deformation = deform
    value.column_start_offsets = [4, -2]
    value.layout_transform = transform
    return value


def test_public_functions_keep_signatures_and_identity():
    assert len(list(ROOT.glob("*.py"))) == 9
    assert (ROOT / "geometry/geometry_construction.py").is_file()
    assert not (ROOT / "geometry_construction.py").exists()
    for name, args in (
        ("_derive_nominal_geometry_canonical", ["image_width", "image_height", "settings"]),
        ("derive_nominal_geometry", ["image_width", "image_height", "settings"]),
        ("_derive_geometry_canonical", ["image", "settings"]),
        ("derive_geometry", ["image", "settings"]),
    ):
        fn = getattr(core, name)
        assert fn.__module__ == "picture_capture.processing_core"
        assert list(inspect.signature(fn).parameters) == args
    assert core.Geometry.__module__ == "picture_capture.processing_core"
    assert core.ColumnPath.__module__ == "picture_capture.processing_core"


def test_nominal_geometry_equivalence_and_live_offset_patch(monkeypatch):
    cfg = settings()
    got = core._derive_nominal_geometry_canonical(180, 100, cfg)
    direct = geometry_construction.derive_nominal_geometry_canonical(
        180, 100, cfg,
        source_px_fn=core._source_px,
        offsets_fn=core._column_start_offsets_canonical,
        apply_offsets_fn=core.apply_column_start_offsets,
        column_path_cls=core.ColumnPath, geometry_cls=core.Geometry,
    )
    assert type(got) is core.Geometry
    assert got.column_starts == direct.column_starts
    assert got.column_widths == direct.column_widths
    assert got.column_starts == [14, 63]
    assert (got.top, got.bottom) == (10, 85)
    assert all(type(path) is core.ColumnPath for path in got.column_paths)
    original = core._column_start_offsets_canonical
    monkeypatch.setattr(facade, "_column_start_offsets_canonical", lambda *_: [0, 0])
    adjusted = core._derive_nominal_geometry_canonical(180, 100, cfg)
    assert adjusted.column_starts == [10, 65]
    monkeypatch.setattr(facade, "_column_start_offsets_canonical", original)


def test_transformed_nominal_geometry_keeps_source_image_coordinates():
    cfg = settings(transform="rotate_cw90")
    result = core.derive_nominal_geometry(180, 100, cfg)
    assert type(result) is core.Geometry
    assert result.source_size == (180, 100)
    assert result.transform.kind == "rotate_cw90"
    assert result.transform.canonical_size(result.source_size) == (100, 180)
    assert result.column_starts[0] == 14


def test_actual_geometry_straight_column_and_live_deformation_hook(monkeypatch):
    cfg = settings()
    img = Image.new("RGB", (180, 100), "white")
    g = core.derive_geometry(img, cfg)
    assert g.column_starts == [14, 63]
    assert (g.top, g.bottom) == (10, 85)
    assert g.source_size == img.size
    assert type(g) is core.Geometry
    assert all(type(v) is core.ColumnPath for v in g.column_paths)

    cfg.follow_column_deformation = True
    original = core._estimate_column_paths
    calls = []
    def estimator(analysis, scale, starts, widths, top, bottom, settings, extra):
        calls.append((scale, tuple(starts), top, bottom))
        return [core.ColumnPath([(top, left), (bottom, left)]) for left in starts]
    monkeypatch.setattr(facade, "_estimate_column_paths", estimator)
    curved = core._derive_geometry_canonical(img, cfg)
    assert len(curved.column_paths) == 2
    assert len(calls) == 1
    assert type(curved) is core.Geometry
    monkeypatch.setattr(facade, "_estimate_column_paths", original)


def test_derive_geometry_observes_current_canonical_builder(monkeypatch):
    cfg = settings(transform="mirror_x")
    img = Image.new("RGB", (180, 100), "white")
    original = core._derive_geometry_canonical
    seen = []
    def builder(canonical, settings):
        seen.append(canonical.size)
        return original(canonical, settings)
    monkeypatch.setattr(facade, "_derive_geometry_canonical", builder)
    g = core.derive_geometry(img, cfg)
    assert seen == [(180, 100)]
    assert g.transform.kind == "mirror_x"
    assert g.source_size == img.size
    monkeypatch.setattr(facade, "_derive_geometry_canonical", original)
