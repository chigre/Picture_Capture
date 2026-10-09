"""Phase 13E installer exit preflight for explicitly composed consumers.

These checks intentionally exercise the real composition without invoking any
legacy installer. They are not permission to delete compatibility shims.
"""
import ast
from pathlib import Path

from PIL import Image, ImageDraw

from picture_capture import dictionary_page_design as base
from picture_capture import layout_composition as composed
from picture_capture import layout_core_understanding as core
from picture_capture import layout_line_start_refinement as robust
from picture_capture import layout_physical_indent as physical
from picture_capture.models import AppSettings


PACKAGE = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def _sample():
    image = Image.new("RGB", (250, 200), "white")
    draw = ImageDraw.Draw(image)
    for index in range(7):
        y = 17 + index * 22
        draw.rectangle((18, y, 26, y + 11), fill="black")
        draw.rectangle((45, y, 104, y + 11), fill="black")
    return image, AppSettings(
        columns=1, manual_x=15, column_width=180,
        start_y=8, character_height=14, ordinary_auto_layout=False,
    )


def test_composed_full_and_layout_only_run_without_installer_calls(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("legacy installer used by explicitly composed path")

    monkeypatch.setattr(robust, "install_robust_line_starts", reject)
    monkeypatch.setattr(physical, "install_physical_indent_inference", reject)
    # Even hostile global hook rebindings cannot affect explicit composition.
    for name in ("_line_runs", "_line_feature", "_indent_modes",
                 "_assign_indent_semantics"):
        monkeypatch.setattr(base, name, reject)

    image, settings = _sample()
    try:
        full = composed.understand_composed_page(image, settings)
        core._LAYOUT_CACHE.clear()
        only = core.understand_layout_core(image, settings)
        assert full.layout.columns and only.layout.columns
        assert full.page_settings.manual_x == only.page_settings.manual_x
        assert full.layout.body_top == only.layout.body_top
        assert [(c.left, c.right) for c in full.layout.columns] == [
            (c.left, c.right) for c in only.layout.columns
        ]
    finally:
        core._LAYOUT_CACHE.clear()
        image.close()


def test_migrated_consumers_do_not_import_legacy_full_understanding():
    for filename in (
        "training_export_page_understanding.py",
        "profile_validation_modes.py",
    ):
        tree = ast.parse((PACKAGE / filename).read_text(encoding="utf-8"))
        imported = [
            alias.name for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "page_understanding"
            for alias in node.names
        ]
        assert "understand_page" not in imported, filename


def test_remaining_installers_are_explicit_compatibility_boundary():
    processing = (PACKAGE / "processing.py").read_text(encoding="utf-8")
    bootstrap = (PACKAGE / "bootstrap" / "gui.py").read_text(encoding="utf-8")
    assert "def _ensure_layout_runtime()" in processing
    assert "install_physical_indent_inference()" in processing
    assert "install_robust_line_starts()" in processing
    assert "install_physical_indent_inference()" not in bootstrap
    assert "install_robust_line_starts()" not in bootstrap
