from __future__ import annotations

from pathlib import Path
import queue

from picture_capture.models import Entry
import picture_capture.postproduction_single_line_runtime as runtime


def test_single_line_worker_reuses_proofreading_crop_path(tmp_path, monkeypatch):
    root = tmp_path / "dictionary"
    root.mkdir()
    images = (root / "page1.jpg", root / "page2.jpg")
    calls: list[dict] = []
    logged: list[list] = []

    monkeypatch.setattr(runtime.formats, "pdic_path", lambda path: path.with_suffix(".pdic"))
    monkeypatch.setattr(
        runtime.formats,
        "read_pdic",
        lambda path: [Entry(path.stem, 10, 20)],
    )
    monkeypatch.setattr(runtime, "read_page_sections", lambda path: [f"section:{path.stem}"])

    def fake_split(image_path, entries, settings, output_dir, **kwargs):
        calls.append({
            "image_path": image_path,
            "entries": entries,
            "settings": settings,
            "output_dir": output_dir,
            **kwargs,
        })
        return [f"record:{image_path.stem}"]

    monkeypatch.setattr(runtime, "split_single_lines", fake_split)
    monkeypatch.setattr(runtime, "append_crop_log", lambda _root, records: logged.append(list(records)))

    events: queue.Queue = queue.Queue()
    settings = object()
    runtime._single_line_worker(root, images, (1, 0), settings, events)

    assert [call["image_path"].name for call in calls] == ["page2.jpg", "page1.jpg"]
    assert [call["profile_page_index"] for call in calls] == [1, 0]
    assert [call["page_sections"] for call in calls] == [
        ["section:page2"],
        ["section:page1"],
    ]
    assert all(call["output_dir"] == root / "QT" / "PSW" for call in calls)
    assert all(call["settings"] is settings for call in calls)
    assert logged == [["record:page2"], ["record:page1"]]

    emitted = []
    while not events.empty():
        emitted.append(events.get_nowait())
    assert [kind for kind, _payload in emitted] == ["progress", "progress", "done"]
    assert emitted[-1][1][0:2] == (2, 2)
    assert emitted[-1][1][2] == root / "QT" / "PSW"


def test_runtime_contract_keeps_main_button_left_of_entry_crop_and_uses_selected_scope():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "picture_capture" / "postproduction_single_line_runtime.py").read_text(
        encoding="utf-8"
    )

    assert '_BUTTON_TEXT = "单行切图"' in source
    assert '_TARGET_TEXT = "词条切图"' in source
    assert "_pack_before(button, target)" in source
    assert "_grid_before(button, target)" in source
    assert "app.selected_page_indices()" in source
    assert "split_single_lines(" in source
    assert 'qt_root(project_root) / "PSW"' in source
    assert "profile_page_index=index" in source
    assert "page_sections=sections" in source
    # The main-window action must not fork a second line-box algorithm.
    worker = source[source.index("def _single_line_worker("):source.index("\ndef _start_single_line_export(")]
    assert ".crop(" not in worker
    assert "character_height" not in worker
    assert "row_padding" not in worker


def test_launcher_installs_single_line_postproduction_extension():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "src" / "picture_capture" / "launcher.py").read_text(encoding="utf-8")
    assert "from .postproduction_single_line_runtime import (" in launcher
    assert "install_postproduction_single_line_runtime(app_module)" in launcher
