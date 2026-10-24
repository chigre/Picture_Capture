"""Round 27: historically persisted geometry and crop classes retain exact pickle identity."""
from __future__ import annotations

import ast
from dataclasses import fields, is_dataclass
from pathlib import Path
import pickle

from picture_capture import processing_core as core
from picture_capture.geometry import processing_models
from picture_capture.crop import plan_models
from picture_capture.geometry.layout_transform import LayoutTransform


def test_exact_model_owners_no_root_compat_stubs():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(root.glob("*.py"))) == 10
    mapping = {
        "geometry/processing_models.py": {"ColumnPath", "Geometry"},
        "crop/plan_models.py": {
            "CropRecord", "EntryCropPiecePlan", "IllustrationCropPlan",
            "PageCropPlan", "IllustrationCropEvent", "IllustrationSplitResult",
        },
    }
    for relative, names in mapping.items():
        leaf = root / relative
        assert leaf.is_file() and not (root / leaf.name).exists()
        nodes = ast.parse(leaf.read_text(encoding="utf-8")).body
        assert {n.name for n in nodes if isinstance(n, ast.ClassDef)} == names
    core_tree = ast.parse((root / "processing_core.py").read_text(encoding="utf-8"))
    assert not any(
        isinstance(n, ast.ClassDef) and n.name in {
            "ColumnPath", "Geometry", "CropRecord", "EntryCropPiecePlan",
            "IllustrationCropPlan", "PageCropPlan", "IllustrationCropEvent",
            "IllustrationSplitResult",
        } for n in core_tree.body
    )


def test_all_model_classes_keep_historical_module_and_same_identity():
    owner = {
        "ColumnPath": processing_models,
        "Geometry": processing_models,
        "CropRecord": plan_models,
        "EntryCropPiecePlan": plan_models,
        "IllustrationCropPlan": plan_models,
        "PageCropPlan": plan_models,
        "IllustrationCropEvent": plan_models,
        "IllustrationSplitResult": plan_models,
    }
    for name, module in owner.items():
        klass = getattr(core, name)
        assert klass is getattr(module, name)
        assert klass.__module__ == "picture_capture.processing_core"
        assert klass.__qualname__ == name
        assert is_dataclass(klass)
        assert pickle.loads(pickle.dumps(klass)) is klass


def test_geometry_preserves_source_coordinate_transforms_and_dataclass_pickles():
    path = core.ColumnPath([(0, 10), (20, 30), (40, 20)])
    assert [path.x_at(y) for y in [-5, 0, 10, 25, 40, 100]] == [10, 10, 20, 28, 20, 20]
    assert path.x_bounds(12, 28) == (22, 28)
    geometry = core.Geometry(
        column_starts=[10], column_widths=[80], top=0, bottom=40,
        column_paths=[path], source_size=(100, 80),
        transform=LayoutTransform("mirror_x"),
    )
    assert geometry.x_at(0, 10) == 20
    assert geometry.x_bounds(0, 12, 28) == (22, 28)
    assert geometry.source_to_canonical(20, 12) == (79, 12)
    restored = pickle.loads(pickle.dumps(geometry))
    assert type(restored) is core.Geometry
    assert type(restored.column_paths[0]) is core.ColumnPath
    assert restored.column_paths[0].points == path.points
    assert restored.source_to_canonical(20, 12) == geometry.source_to_canonical(20, 12)


def test_crop_plan_fields_sequence_compatibility_and_pickle_roundtrip():
    piece = core.EntryCropPiecePlan(0, 1, "词", (2, 3, 30, 40), "(1)")
    picture = core.IllustrationCropPlan(0, "picture", 1, "词", "partial", True, (2, 3, 6, 9))
    plan = core.PageCropPlan([piece], [picture])
    assert [f.name for f in fields(core.PageCropPlan)] == [
        "entry_pieces", "illustrations", "integrate_illustrations", "auxiliary_gaps",
    ]
    assert plan.integrate_illustrations is True and plan.auxiliary_gaps == []
    record = core.CropRecord("page.png", 0, "词", "page_WW_000.png", (2, 3, 30, 40))
    event = core.IllustrationCropEvent("page.png", 0, "pic", "词", "partial", "saved")
    result = core.IllustrationSplitResult([record], [event])
    assert len(result) == 1
    assert list(result) == [record] and result[0] is record
    assert isinstance(result[0], core.CropRecord)
    restored = pickle.loads(pickle.dumps((plan, result)))
    assert type(restored[0]) is core.PageCropPlan
    assert type(restored[1]) is core.IllustrationSplitResult
    assert restored[0].entry_pieces == [piece]
    assert restored[1].records == [record]
    assert restored[1].events == [event]
