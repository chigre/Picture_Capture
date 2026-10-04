from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

from picture_capture.ui.controllers.review import ReviewController


ROOT = Path(__file__).resolve().parents[1]


class _Canvas:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.ymoves: list[float] = []
        self.rectangles: list[tuple[tuple, dict]] = []
        self.raised: list[object] = []

    def delete(self, tag: str) -> None:
        self.deleted.append(tag)

    def winfo_height(self) -> int:
        return 400

    def yview_moveto(self, value: float) -> None:
        self.ymoves.append(value)

    def create_rectangle(self, *args, **kwargs):
        self.rectangles.append((args, kwargs))
        return len(self.rectangles)

    def tag_raise(self, tag) -> None:
        self.raised.append(tag)


class _Transform:
    def canonical_box_to_source(self, box, image_size):
        assert image_size == (1000, 2000)
        return box


class _Geometry:
    column_starts = [0.0, 300.0]
    column_widths = [250.0, 300.0]
    transform = _Transform()

    def source_to_canonical(self, x: int, y: int):
        return float(x), float(y)

    def x_at(self, col: int, v: float) -> float:
        return self.column_starts[col] + v * 0.01


class _App:
    def __init__(self) -> None:
        self.ocr_review_candidates: list[dict] = []
        self.entries = []
        self.image = SimpleNamespace(width=1000, height=2000, size=(1000, 2000))
        self.current_index = 3
        self.view_scale = 0.5
        self.canvas = _Canvas()
        self._review_entry_highlight_target = None
        self._review_entry_highlight_photo = object()
        self.draw_highlight_calls = 0
        self.geometry = _Geometry()
        self.cache_path: Path | None = None

    def _paddle_cache_path(self):
        return self.cache_path

    def _quick_geometry_value(self, name: str) -> float:
        assert name == "character_height"
        return 20.0

    def _draw_review_entry_highlight(self) -> None:
        self.draw_highlight_calls += 1

    def _get_cached_display_geometry(self):
        return self.geometry


def test_load_and_lookup_review_candidates_preserve_cache_contract(tmp_path: Path) -> None:
    app = _App()
    controller = ReviewController(app)

    controller.load_ocr_review_candidates()
    assert app.ocr_review_candidates == []

    path = tmp_path / "page.json"
    app.cache_path = path
    path.write_text(
        json.dumps({"review_candidates": [{"candidate_id": "c1"}, {"candidate_id": "c2"}]}),
        encoding="utf-8",
    )
    controller.load_ocr_review_candidates()
    assert [item["candidate_id"] for item in app.ocr_review_candidates] == ["c1", "c2"]
    assert controller.get_review_candidate("c2") == {"candidate_id": "c2"}
    assert controller.get_review_candidate("missing") is None

    path.write_text("not json", encoding="utf-8")
    controller.load_ocr_review_candidates()
    assert app.ocr_review_candidates == []


def test_candidate_matching_prefers_id_and_keeps_coordinate_fallback() -> None:
    app = _App()
    exact = SimpleNamespace(candidate_id="cid", x=900, y=1500)
    nearby = SimpleNamespace(candidate_id="other", x=108, y=207)
    app.entries = [exact, nearby]
    controller = ReviewController(app)

    by_id = {"candidate_id": "cid", "source_x": 0, "source_y": 0}
    assert controller.candidate_is_selected(by_id) is True
    assert controller.entry_for_candidate(by_id) is exact

    by_position = {"candidate_id": "missing", "source_x": 100, "source_y": 200}
    assert controller.candidate_is_selected(by_position) is True
    assert controller.entry_for_candidate(by_position) is nearby

    too_far = {"candidate_id": "missing", "source_x": 100, "source_y": 220}
    assert controller.candidate_is_selected(too_far) is False
    assert controller.entry_for_candidate(too_far) is None


def test_review_highlight_state_and_cleanup_remain_on_main_canvas() -> None:
    app = _App()
    controller = ReviewController(app)
    entry = SimpleNamespace(x=123, y=456)

    controller.highlight_review_entry(entry)
    assert app._review_entry_highlight_target == (3, 123, 456)
    assert app.draw_highlight_calls == 1

    controller.clear_review_entry_highlight()
    assert app._review_entry_highlight_target is None
    assert app._review_entry_highlight_photo is None
    assert app.canvas.deleted[-1] == "proofread-entry-highlight"

    app.image = None
    controller.highlight_review_entry(entry)
    assert app.draw_highlight_calls == 1


def test_jump_to_review_candidate_preserves_scroll_column_clamp_and_box() -> None:
    app = _App()
    controller = ReviewController(app)

    controller.jump_to_review_candidate(
        {"source_x": 120, "source_y": 1000, "column": 99}
    )

    assert app.canvas.ymoves == [0.38]
    assert app.canvas.deleted[-1] == "review-highlight"
    args, kwargs = app.canvas.rectangles[-1]
    # column=99 clamps to the second/last column; x_at(1, 1000)=310.
    assert args == (155.0, 497.5, 302.0, 509.0)
    assert kwargs == {
        "outline": "#00bcd4",
        "width": 3,
        "tags": ("review-highlight",),
    }
    assert app.canvas.raised[-1] == "review-highlight"


def test_review_controller_has_no_reverse_dependency_on_app_module() -> None:
    path = ROOT / "src/picture_capture/ui/controllers/review.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "picture_capture.app" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"app", "picture_capture.app"}


def test_review_controller_wiring_keeps_picture_capture_app_compatibility_methods() -> None:
    app = (ROOT / "src/picture_capture/app.py").read_text(encoding="utf-8")
    controller = (ROOT / "src/picture_capture/ui/controllers/review.py").read_text(encoding="utf-8")

    imports = app[: app.index("class PictureCaptureApp")]
    assert "ReviewController" in imports
    assert "self.review_controller = ReviewController(self)" in app
    assert "def _review_controller_for_call(" in app
    assert 'self.__dict__.get("review_controller")' in app
    assert app.index("self.review_controller = ReviewController(self)") < app.index("self._build_ui()")

    expected = {
        "_load_ocr_review_candidates": "load_ocr_review_candidates",
        "get_review_candidate": "get_review_candidate",
        "_candidate_is_selected": "candidate_is_selected",
        "_entry_for_candidate": "entry_for_candidate",
        "clear_review_entry_highlight": "clear_review_entry_highlight",
        "highlight_review_entry": "highlight_review_entry",
        "jump_to_review_candidate": "jump_to_review_candidate",
    }
    for app_method, controller_method in expected.items():
        assert f"def {app_method}(" in app
        assert f"self._review_controller_for_call().{controller_method}" in app
        assert f"def {controller_method}(" in controller
