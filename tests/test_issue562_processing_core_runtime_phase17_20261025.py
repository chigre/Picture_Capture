"""Issue #562 Phase 17: real processing integration code is no longer root."""
from __future__ import annotations

import importlib
import pickle
import subprocess
import sys
from pathlib import Path

from PIL import Image

from picture_capture.models import AppSettings, Entry
from picture_capture import processing as facade
from picture_capture.runtime import processing_core_runtime as canonical


def test_core_owned_by_runtime_and_legacy_import_aliases_one_module():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    source = (pkg / "processing_core.py").read_text(encoding="utf-8")
    implementation = (pkg / "runtime/processing_core_runtime.py").read_text(encoding="utf-8")
    assert "_sys.modules[__name__] = _canonical" in source
    assert "def " not in source and "class " not in source
    assert "def _crop_workflow_deps" in implementation
    assert "def split_illustrations_job" in implementation
    assert "def _detect_entries_left_edge" in implementation
    assert canonical is importlib.import_module("picture_capture.processing_core")
    assert canonical.__file__.endswith("runtime/processing_core_runtime.py")


def test_legacy_geometry_and_crop_dataclasses_are_same_pickle_objects():
    from picture_capture.geometry.processing_models import ColumnPath, Geometry
    from picture_capture.crop.plan_models import CropRecord, PageCropPlan, IllustrationSplitResult
    for typ in (ColumnPath, Geometry, CropRecord, PageCropPlan, IllustrationSplitResult):
        assert getattr(canonical, typ.__name__) is typ
        assert typ.__module__ == "picture_capture.processing_core"
        assert pickle.loads(pickle.dumps(typ)) is typ
    shape = Geometry(column_starts=[5], column_widths=[120], top=0, bottom=90, column_paths=[])
    assert pickle.loads(pickle.dumps(shape)) == shape


def test_worker_origins_and_public_assignments_remain_pickle_spawn_compatible(monkeypatch):
    old = importlib.import_module("picture_capture.processing_core")
    for name in ("detect_entries", "detect_entries_job", "split_single_lines",
                 "split_whole_entries_job", "split_illustrations_job", "build_page_crop_plan"):
        fn = getattr(old, name)
        assert fn.__module__ == "picture_capture.processing_core"
        assert pickle.loads(pickle.dumps(fn)) is fn
    original = old._source_px
    monkeypatch.setattr(facade, "_source_px", lambda value: 127)
    assert old._source_px(4.5) == 127
    assert canonical._source_px(4.5) == 127
    monkeypatch.setattr(facade, "_source_px", original)


def test_geometry_crop_boundaries_remain_in_source_coordinates():
    core = importlib.import_module("picture_capture.processing_core")
    img = Image.new("RGB", (160, 220), "white")
    cfg = AppSettings(columns=1)
    geom = core.derive_geometry(img, cfg)
    assert geom.source_size == (160, 220)
    assert core.parameter_scale(img, cfg) == 1.0
    assert core._source_px(8.6) == 9
    assert core.clamp_box((-4, 2, 168, 300), img) == (0, 2, 160, 220)


def test_bare_package_remains_metadata_only_and_old_import_is_lazy():
    command = (
        "import sys,picture_capture;"
        "assert not [k for k in sys.modules if k.startswith('picture_capture.')];"
        "import picture_capture.processing_core as old;"
        "from picture_capture.runtime import processing_core_runtime as new;"
        "assert old is new"
    )
    p = subprocess.run([sys.executable, "-c", command], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
