from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/picture_capture/app.py"
TEST = ROOT / "tests/test_ui_detection_controller.py"


def replace_method(text: str, name: str, next_name: str, replacement: str) -> str:
    start = text.index(f"    def {name}(")
    end = text.index(f"    def {next_name}(", start)
    return text[:start] + replacement + text[end:]


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")
    replacement = (
        "    def auto_detect_current(\n"
        "        self, clicked_x: int | None = None, force_paddle_refresh: bool = False,\n"
        "    ) -> None:\n"
        "        self._detection_controller_for_call().auto_detect_current(\n"
        "            clicked_x=clicked_x,\n"
        "            force_paddle_refresh=force_paddle_refresh,\n"
        "        )\n\n"
    )
    updated = replace_method(
        text, "auto_detect_current", "_detection_controller_for_call", replacement,
    )
    if updated == text:
        raise RuntimeError("Phase 4Y app patch produced no change")
    APP.write_text(updated, encoding="utf-8")


def patch_tests() -> None:
    text = TEST.read_text(encoding="utf-8")
    old = '        "paddle_detect_current": "paddle_detect_current",\n'
    new = (
        '        "auto_detect_current": "auto_detect_current",\n'
        '        "paddle_detect_current": "paddle_detect_current",\n'
    )
    if new not in text:
        if old not in text:
            raise RuntimeError("Phase 4Y wiring insertion point missing")
        text = text.replace(old, new, 1)

    marker = "def test_batch_ocr_preserves_filter_worker_persistence_and_done(tmp_path, monkeypatch) -> None:\n"
    if "def test_auto_detect_current_preserves_single_page_worker_and_done" not in text:
        if marker not in text:
            raise RuntimeError("Phase 4Y behavior-test insertion point missing")
        insertion = r'''class _CurrentDetectApp:
    def __init__(self, root: Path, page: Path) -> None:
        self.project = SimpleNamespace(root=root, images=[page])
        self.current_page = page
        self.current_index = 0
        self.settings = AppSettings(columns=1, detection_method="left_edge")
        self.page_sections = []
        self.entries = [Entry(word="old", x=5, y=10)]
        self._batch_active = False
        self.status_var = _Var("")
        self.calls: list[tuple] = []
        self.batch = None

    def guard(self) -> bool:
        self.calls.append(("guard",))
        return True

    def _guard_transformed_geometry(self, title: str) -> bool:
        self.calls.append(("guard_transformed_geometry", title))
        return True

    def _start_batch_task(self, title, items, worker, done, **kwargs):
        self.batch = (title, list(items), worker, done, kwargs)
        return True

    def _sort_entries_reading_order(self) -> None:
        self.calls.append(("sort_entries",))

    def _load_ocr_review_candidates(self) -> None:
        self.calls.append(("load_ocr_review_candidates",))

    def _refresh_page_quality_colors(self) -> None:
        self.calls.append(("refresh_page_quality_colors",))

    def _current_page_quality_text(self) -> str:
        return "quality"

    def redraw(self) -> None:
        self.calls.append(("redraw",))


def test_auto_detect_current_busy_guard_preserves_existing_status() -> None:
    app = SimpleNamespace(_batch_active=True, status_var=_Var(""))

    DetectionController(app).auto_detect_current()

    assert app.status_var.value == "后台画线任务运行中，暂不启动前台自动识别；可进行人工校对。"


def test_auto_detect_current_preserves_single_page_worker_and_done(tmp_path, monkeypatch) -> None:
    page = tmp_path / "001.png"
    Image.new("RGB", (80, 120), "white").save(page)
    app = _CurrentDetectApp(tmp_path, page)
    geometry = object()
    detected = [Entry(word="new", x=7, y=20)]
    calls: list[tuple] = []

    def fake_detect(image, settings, **kwargs):
        calls.append((image.size, settings.detection_method, kwargs))
        return detected, geometry

    monkeypatch.setattr(detection_module, "detect_entries", fake_detect)

    DetectionController(app).auto_detect_current(force_paddle_refresh=True)

    assert app.calls[:2] == [("guard",), ("guard_transformed_geometry", "自动画线")]
    assert app.batch is not None
    title, items, worker, done, kwargs = app.batch
    assert title == "当前页自动画线"
    assert items == [0]
    assert kwargs["item_label"](0) == "001.png"
    assert kwargs["refresh_page_quality"] is False

    result = worker(0, 1, 1)
    assert result == (detected, geometry, None)
    assert calls[0][0] == (80, 120)
    assert calls[0][1] == "left_edge"
    assert calls[0][2]["force_paddle_refresh"] is True
    assert calls[0][2]["profile_page_index"] == 0

    done(1, 1, False, [result], None)

    assert app.entries == detected
    assert ("sort_entries",) in app.calls
    assert ("redraw",) in app.calls
    assert app.status_var.value == "智能画线完成：检测到 1 个词条；可手动增删后保存"


def test_auto_detect_current_clicked_column_replaces_only_target_column(
    tmp_path, monkeypatch,
) -> None:
    page = tmp_path / "001.png"
    Image.new("RGB", (80, 120), "white").save(page)
    app = _CurrentDetectApp(tmp_path, page)
    app.entries = [
        Entry(word="keep", x=10, y=10),
        Entry(word="replace", x=60, y=20),
    ]
    geometry = object()
    detected = [
        Entry(word="ignored", x=12, y=30),
        Entry(word="fresh", x=65, y=40),
    ]
    monkeypatch.setattr(
        detection_module, "detect_entries", lambda *_args, **_kwargs: (detected, geometry),
    )
    monkeypatch.setattr(detection_module, "column_index_for_click", lambda _x, _g: 1)
    monkeypatch.setattr(
        detection_module, "column_index", lambda x, _g, _y: 0 if int(x) < 40 else 1,
    )

    DetectionController(app).auto_detect_current(clicked_x=70)
    _, _, worker, done, _ = app.batch
    result = worker(0, 1, 1)
    done(1, 1, False, [result], None)

    assert [(entry.word, entry.x) for entry in app.entries] == [
        ("keep", 10),
        ("fresh", 65),
    ]


def test_auto_detect_current_does_not_publish_to_different_page(tmp_path, monkeypatch) -> None:
    page = tmp_path / "001.png"
    other = tmp_path / "002.png"
    Image.new("RGB", (80, 120), "white").save(page)
    Image.new("RGB", (80, 120), "white").save(other)
    app = _CurrentDetectApp(tmp_path, page)
    original_entries = list(app.entries)
    result = ([Entry(word="new", x=7, y=20)], object(), None)
    monkeypatch.setattr(
        detection_module, "detect_entries", lambda *_args, **_kwargs: (result[0], result[1]),
    )

    DetectionController(app).auto_detect_current()
    _, _, _worker, done, _ = app.batch
    app.current_page = other
    done(1, 1, False, [result], None)

    assert app.entries == original_entries
    assert ("sort_entries",) not in app.calls
    assert ("redraw",) not in app.calls


'''
        text = text.replace(marker, insertion + marker, 1)

    TEST.write_text(text, encoding="utf-8")


def main() -> None:
    patch_app()
    patch_tests()
    controller = (
        ROOT / "src/picture_capture/ui/controllers/detection.py"
    ).read_text(encoding="utf-8")
    if "    def auto_detect_current(" not in controller:
        raise RuntimeError("DetectionController.auto_detect_current missing")


if __name__ == "__main__":
    main()
