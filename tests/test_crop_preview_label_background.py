"""Crop preview labels must have a readable backing with an outline."""
from pathlib import Path

from picture_capture.crop_preview_labels import draw_crop_preview_label


class CanvasStub:
    def __init__(self):
        self.items = []
        self.lowered = []

    def create_text(self, *args, **kwargs):
        self.items.append(("text", args, kwargs))
        return 1

    def bbox(self, item):
        assert item == 1
        return (10, 20, 80, 44)

    def create_rectangle(self, *args, **kwargs):
        self.items.append(("rectangle", args, kwargs))
        return 2

    def tag_lower(self, backing, foreground):
        self.lowered.append((backing, foreground))


def test_crop_label_is_backed_and_readable():
    canvas = CanvasStub()
    assert draw_crop_preview_label(
        canvas, 40, 30, text="dictionary\nword.png",
        outline="#00acc1", font=("Arial", 10),
    ) == (1, 2)
    assert canvas.items[0][2]["fill"] == "#19232d"
    assert canvas.items[1][1] == (6, 17, 84, 47)
    assert canvas.items[1][2]["fill"] == "#f8fafc"
    assert canvas.items[1][2]["outline"] == "#00acc1"
    assert canvas.lowered == [(2, 1)]
    assert "crop-plan" in canvas.items[0][2]["tags"]
    assert "crop-plan" in canvas.items[1][2]["tags"]


def test_main_crop_plan_applies_badges_to_entries_and_ppp():
    source = (Path(__file__).resolve().parents[1] /
              "src/picture_capture/app.py").read_text(encoding="utf-8")
    start = source.index("    def _draw_crop_plan_preview(")
    end = source.index("    def _rulers_visible(", start)
    code = source[start:end]
    assert code.count("draw_crop_preview_label(") == 2
    assert "self.canvas.create_text(" not in code
