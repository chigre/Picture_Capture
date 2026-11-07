"""Round 25: Tesseract, saved-marker refinement, PPP update and crop worker APIs."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture import processing_core as core
from picture_capture.models import AppSettings, Entry
from picture_capture.ocr import tesseract_subprocess
from picture_capture.refinement import existing_entry_workflow
from picture_capture.illustration import ppp_detection_update, crop_box_policy
from picture_capture.crop import spawn_job_owners


def test_exact_owners_and_historical_module_identity():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(pkg.glob("*.py"))) == 5
    owners = {
        "ocr/tesseract_subprocess.py": {"run_tesseract_impl"},
        "refinement/existing_entry_workflow.py": {"refine_existing_entries_impl"},
        "illustration/ppp_detection_update.py": {"detect_illustrations_to_ppp_impl"},
        "illustration/crop_box_policy.py": {"illustration_polygon_box_impl"},
        "crop/spawn_job_owners.py": {"split_whole_entries_job_impl", "split_illustrations_job_impl"},
    }
    for path, expected in owners.items():
        leaf = pkg / path
        assert leaf.is_file() and not (pkg / leaf.name).exists()
        tree = ast.parse(leaf.read_text(encoding="utf-8"))
        assert {n.name for n in tree.body if isinstance(n, ast.FunctionDef)} == expected
        assert not any(isinstance(n, (ast.Assign, ast.AnnAssign, ast.ClassDef)) for n in tree.body)
    for name in ("run_tesseract", "refine_existing_entries", "detect_illustrations_to_ppp",
                 "illustration_polygon_box", "split_whole_entries_job", "split_illustrations_job"):
        assert getattr(core, name).__module__ == "picture_capture.processing_core"
    assert list(inspect.signature(core.run_tesseract).parameters) == [
        "image", "language", "executable", "psm",
    ]
    assert list(inspect.signature(core.refine_existing_entries).parameters) == [
        "image", "entries", "settings", "profile_page_index", "source_image_path", "fixed_half_gutter",
    ]
    assert list(inspect.signature(core.detect_illustrations_to_ppp).parameters) == [
        "image_path", "settings", "profile_page_index", "detected_regions",
    ]
    assert list(inspect.signature(core.illustration_polygon_box).parameters) == [
        "image", "region", "top", "bottom", "margin_px",
    ]


def test_tesseract_uses_current_core_executable_and_subprocess(monkeypatch):
    seen = {}
    monkeypatch.setattr(core, "find_tesseract", lambda executable: "/fake/tesseract")
    def fake_run(command, *, input, stdout, stderr, timeout):
        seen.update(command=command, input=input, timeout=timeout)
        return SimpleNamespace(returncode=0, stdout="汉字".encode(), stderr=b"")
    monkeypatch.setattr(core.subprocess, "run", fake_run)
    assert core.run_tesseract(Image.new("RGB", (12, 8), "white"), "chi_sim", psm=5) == "汉字"
    assert seen["command"] == ["/fake/tesseract", "stdin", "stdout", "-l", "chi_sim", "--psm", "5"]
    assert seen["input"].startswith(b"\x89PNG") and seen["timeout"] == 120


def test_refinement_keeps_live_page_context_and_geometry_seam(monkeypatch):
    seen = {}
    def delegate(*args, deps, **kwargs):
        seen.update(deps)
        return args[1], {"moved": 0}
    monkeypatch.setattr(existing_entry_workflow, "refine_existing_entries_impl", delegate)
    fake_context = lambda *a, **k: (None, None, None, None)
    monkeypatch.setattr(core, "_page_geometry_context", fake_context)
    page = Image.new("RGB", (40, 50), "white")
    row = Entry(word="字", x=2, y=5)
    out, stats = core.refine_existing_entries(page, [row], AppSettings())
    assert out == [row] and stats == {"moved": 0}
    assert seen["_page_geometry_context"] is fake_context
    assert seen["derive_geometry"] is core.derive_geometry


def test_ppp_redetection_preserves_manual_and_filters_overlap(monkeypatch, tmp_path):
    from picture_capture.illustration import labels
    manual = SimpleNamespace(box=(5, 5, 20, 20), is_auto=False)
    auto = SimpleNamespace(box=(60, 60, 70, 70), is_auto=True)
    new_blocked = SimpleNamespace(box=(10, 10, 18, 18), is_auto=True)
    new_clear = SimpleNamespace(box=(30, 30, 40, 40), is_auto=True)
    saved = []
    monkeypatch.setattr(core, "ppp_read_path_for_image", lambda p: tmp_path / "input.PPP")
    monkeypatch.setattr(core, "ppp_write_path_for_image", lambda p: tmp_path / "output.PPP")
    monkeypatch.setattr(core, "read_ppp", lambda p: [manual, auto])
    monkeypatch.setattr(core, "is_auto_illustration_region", lambda r: r.is_auto)
    monkeypatch.setattr(core, "_polygon_bbox", lambda r: r.box)
    monkeypatch.setattr(core, "_overlap_fraction", lambda a, b: 1.0 if a == new_blocked.box else 0.0)
    monkeypatch.setattr(labels, "write_ordered_auto_ppp", lambda *args: saved.append(args))
    result = core.detect_illustrations_to_ppp(
        tmp_path / "page.png", AppSettings(),
        detected_regions=[new_blocked, new_clear],
    )
    assert result == {"manual": 1, "auto": 1, "total": 2}
    assert len(saved) == 1
    assert saved[0][1] == [manual] and saved[0][2] == [new_clear]


def test_illustration_crop_box_clamps_original_pixels():
    page = Image.new("RGB", (100, 60), "white")
    polygon = SimpleNamespace(points=[(4, 5), (18, 5), (18, 25), (4, 25)])
    assert core.illustration_polygon_box(page, polygon, top=8, bottom=19) == (4, 8, 19, 19)
    assert core.illustration_polygon_box(page, SimpleNamespace(points=[(1, 1), (2, 1)])) is None


def test_spawn_safe_worker_still_uses_current_core_readers_and_previous_page(monkeypatch, tmp_path):
    rows = [Entry(word="word", x=2, y=3)]
    poly = [SimpleNamespace(points=[(1, 2), (3, 2), (3, 4)])]
    monkeypatch.setattr(core, "read_pdic", lambda path: rows)
    monkeypatch.setattr(core, "read_ppp", lambda path: poly)
    monkeypatch.setattr(core, "previous_entry_ref_for_image", lambda path: ("prior", 3))
    seen = []
    def ww(*args, **kwargs):
        seen.append(("WW", args, kwargs))
        return ["WW-success"]
    def pp(*args, **kwargs):
        seen.append(("PPP", args, kwargs))
        return "PPP-success"
    monkeypatch.setattr(core, "split_whole_entries", ww)
    monkeypatch.setattr(core, "split_illustrations", pp)
    page = tmp_path / "page.png"
    assert core.split_whole_entries_job(page, tmp_path / "page.PDIC", AppSettings(), tmp_path,
                                       ppp_file=tmp_path / "page.PPP") == ["WW-success"]
    assert core.split_illustrations_job(page, tmp_path / "page.PPP", tmp_path,
                                        pdic_file=tmp_path / "page.PDIC") == "PPP-success"
    assert [part[0] for part in seen] == ["WW", "PPP"]
    assert seen[0][2]["previous_entry_ref"] == ("prior", 3)
    assert seen[1][2]["previous_entry_ref"] == ("prior", 3)
