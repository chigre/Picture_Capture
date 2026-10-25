"""Round 26: crop staging helper extraction preserves atomic temp semantics."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from PIL import Image

from picture_capture import processing_core as core
from picture_capture.crop import image_staging_io


def test_crop_io_single_owner_and_original_function_paths():
    pkg = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert len(list(pkg.glob("*.py"))) == 7
    path = pkg / "crop" / "image_staging_io.py"
    assert path.is_file()
    assert not (pkg / path.name).exists()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert {n.name for n in tree.body if isinstance(n, ast.FunctionDef)} == {
        "save_crop_impl", "stage_text_file_impl", "stage_crop_impl",
    }
    assert not any(isinstance(n, (ast.Assign, ast.AnnAssign, ast.ClassDef)) for n in tree.body)
    for name in ("_save_crop", "_stage_text_file", "_stage_crop"):
        assert getattr(core, name).__module__ == "picture_capture.processing_core"
    assert list(inspect.signature(core._save_crop).parameters) == [
        "image", "output", "box", "transparent_background",
    ]
    assert list(inspect.signature(core._stage_text_file).parameters) == [
        "target", "text", "encoding",
    ]
    assert list(inspect.signature(core._stage_crop).parameters) == [
        "image", "target", "box", "transparent_background",
    ]


def test_png_crop_clipping_and_staging_keep_original_source_pixels(tmp_path):
    pixels = Image.new("RGB", (22, 16), (113, 37, 71))
    target = tmp_path / "cut.png"
    box = core._save_crop(pixels, target, (-8, -3, 10, 8))
    assert box == (0, 0, 10, 8)
    with Image.open(target) as out:
        assert out.size == (10, 8)
        assert out.getpixel((3, 4)) == (113, 37, 71)
    staged_box, staged = core._stage_crop(
        pixels, tmp_path / "stage.png", (4, 3, 20, 15),
    )
    assert staged_box == (4, 3, 20, 15)
    assert staged.is_file()
    with Image.open(staged) as out:
        assert out.size == (16, 12)
        assert out.getpixel((0, 0)) == (113, 37, 71)
    assert not (tmp_path / "stage.png").exists()
    staged.unlink()


def test_utf8_manifest_stage_preserves_lines_and_never_publishes_early(tmp_path):
    destination = tmp_path / "word_list.PSWords"
    text = "木\n山\n"
    staged = core._stage_text_file(destination, text)
    assert staged.is_file() and staged != destination
    assert staged.read_bytes() == text.encode("utf-8")
    assert not destination.exists()
    staged.unlink()


def test_live_staging_patch_seams_and_cleanup_on_write_failure(monkeypatch, tmp_path):
    image = Image.new("RGB", (30, 20), "white")
    target = tmp_path / "error.png"
    stage = tmp_path / "partial.tmp.png"
    def fake_temp(requested):
        assert requested == target
        return stage
    def fail_crop(image_arg, output, box, *, transparent_background=False):
        output.write_bytes(b"partial")
        raise OSError("simulated crop failure")
    monkeypatch.setattr(core, "_publish_temp_path", fake_temp)
    monkeypatch.setattr(core, "_save_crop", fail_crop)
    try:
        core._stage_crop(image, target, (0, 0, 15, 12))
    except OSError as exc:
        assert "simulated crop failure" in str(exc)
    else:
        raise AssertionError("staging should propagate crop failure")
    assert not stage.exists()
    assert not target.exists()
