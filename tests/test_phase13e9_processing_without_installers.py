"""Phase 13E9: normal processing must not prepare global Layout hooks."""
import ast
from pathlib import Path

from PIL import Image

from picture_capture import layout_composition
from picture_capture import layout_core_understanding as core
from picture_capture import processing
from picture_capture.models import AppSettings


def test_processing_both_modes_skip_historical_installer(monkeypatch):
    def forbidden():
        raise AssertionError("normal processing installed legacy Layout hooks")

    monkeypatch.setattr(processing, "_ensure_layout_runtime", forbidden)
    full = object()
    ordinary = object()
    monkeypatch.setattr(layout_composition, "understand_composed_page",
                        lambda *args, **kwargs: full)
    monkeypatch.setattr(core, "understand_layout_core",
                        lambda *args, **kwargs: ordinary)

    image = Image.new("RGB", (120, 80), "white")
    settings = AppSettings()
    settings.layout_mask_illustrations = False
    assert processing._understand_page_current(
        image, settings, page_index=0, page_sections=[], layout_only=False,
    ) is full
    assert processing._understand_page_current(
        image, settings, page_index=0, page_sections=[], layout_only=True,
    ) is ordinary


def test_normal_processing_source_no_longer_calls_ensure_runtime():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    tree = ast.parse((root / "processing.py").read_text(encoding="utf-8"))
    definitions = [node for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef)
                   and node.name == "_understand_page_current"]
    assert len(definitions) == 1
    calls = [node.func.id for node in ast.walk(definitions[0])
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert "_ensure_layout_runtime" not in calls
    assert "understand_composed_page" in calls
