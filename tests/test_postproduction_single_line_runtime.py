from __future__ import annotations

from pathlib import Path

from picture_capture.models import Entry
import picture_capture.postproduction_single_line_runtime as runtime
import picture_capture.single_line_parallel as parallel


def test_single_line_worker_reuses_proofreading_crop_path(tmp_path, monkeypatch):
    root = tmp_path / "dictionary"
    root.mkdir()
    images = (root / "page1.jpg", root / "page2.jpg")
    calls: list[dict] = []
    logged: list[list] = []
    progress: list[tuple] = []

    monkeypatch.setattr(parallel.formats, "pdic_path", lambda path: path.with_suffix(".pdic"))
    monkeypatch.setattr(
        parallel.formats,
        "read_pdic",
        lambda path: [Entry(path.stem, 10, 20)],
    )
    monkeypatch.setattr(parallel, "read_page_sections", lambda path: [f"section:{path.stem}"])

    def fake_split(image_path, entries, settings, output_dir, **kwargs):
        calls.append({
            "image_path": image_path,
            "entries": entries,
            "settings": settings,
            "output_dir": output_dir,
            **kwargs,
        })
        return [f"record:{image_path.stem}"]

    monkeypatch.setattr(parallel, "split_single_lines", fake_split)
    monkeypatch.setattr(parallel, "append_crop_log", lambda _root, records: logged.append(list(records)))
    monkeypatch.setattr(parallel, "load_merge_by_page", lambda _root: False)
    monkeypatch.setattr(parallel, "configured_single_line_workers", lambda _root: 1)

    settings = object()
    result = parallel.run_single_line_pages(
        root,
        images,
        (1, 0),
        settings,
        lambda *args: progress.append(tuple(args)),
    )

    assert [call["image_path"].name for call in calls] == ["page2.jpg", "page1.jpg"]
    assert [call["profile_page_index"] for call in calls] == [1, 0]
    assert [call["page_sections"] for call in calls] == [
        ["section:page2"],
        ["section:page1"],
    ]
    assert all(call["output_dir"] == root / "QT" / "PSW" for call in calls)
    assert all(call["settings"] is settings for call in calls)
    assert logged == [["record:page2"], ["record:page1"]]
    assert [item[0:2] for item in progress] == [(1, 2), (2, 2)]
    assert result[0:2] == (2, 2)
    assert result[2] == root / "QT" / "PSW"
    assert result[4] == 1


def test_runtime_contract_keeps_main_button_left_of_entry_crop_and_uses_selected_scope():
    root = Path(__file__).resolve().parents[1]
    runtime_source = (root / "src" / "picture_capture" / "postproduction_single_line_runtime.py").read_text(
        encoding="utf-8"
    )
    worker_source = (root / "src" / "picture_capture" / "single_line_parallel.py").read_text(
        encoding="utf-8"
    )
    app_source = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    assert (
        '(("单行切图", self.split_single_lines_selected_scope), '
        '("词条切图", self.split_entries_selected_scope), '
        '("插图切图", self.split_illustrations_selected_scope))'
    ) in app_source
    assert 'if text == "单行切图":' in app_source
    assert "self._pc_single_line_crop_button = button" in app_source
    assert "app.selected_page_indices()" in runtime_source

    # Page-level work owns the mature crop call; the Tk runtime only schedules it.
    assert "split_single_lines(" in worker_source
    assert 'qt_root(project_root) / "PSW"' in worker_source
    assert "profile_page_index=int(page_index)" in worker_source
    assert "page_sections=sections" in worker_source
    page_job = worker_source[
        worker_source.index("def single_line_page_job("):
        worker_source.index("\ndef run_single_line_pages(")
    ]
    assert ".crop(" not in page_job
    assert "character_height" not in page_job
    assert "row_padding" not in page_job


def test_gui_composition_no_longer_installs_single_line_ui_runtime():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "picture_capture" / "bootstrap" / "gui.py"
    ).read_text(encoding="utf-8")
    assert "install_postproduction_single_line_runtime" not in source
    assert "install_unlined_line_export_ui(app_module)" in source

def test_phase5c_runtime_keeps_worker_poll_but_no_ui_or_method_monkey_patch():
    root = Path(__file__).resolve().parents[1]
    runtime_source = (
        root / "src" / "picture_capture" / "postproduction_single_line_runtime.py"
    ).read_text(encoding="utf-8")
    app_source = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    crop_source = (
        root / "src" / "picture_capture" / "ui" / "controllers" / "crop.py"
    ).read_text(encoding="utf-8")

    assert "app_class.split_single_lines_selected_scope = split_single_lines_selected_scope" not in runtime_source
    assert "app_class.__init__ = wrapped_init" not in runtime_source
    assert "_insert_single_line_button" not in runtime_source
    assert "install_postproduction_single_line_runtime" not in runtime_source
    assert "def start_single_line_export(app: Any)" in runtime_source
    assert "threading.Thread(" in runtime_source
    assert "app.after(80, poll)" in runtime_source
    assert 'if text == "单行切图":' in app_source
    assert "self._pc_single_line_crop_button = button" in app_source
    assert "def split_single_lines_selected_scope(self)" in app_source
    assert "self._crop_controller_for_call().split_single_lines_selected_scope()" in app_source
    assert "def split_single_lines_selected_scope(self)" in crop_source
    assert "start_single_line_export(self.app)" in crop_source
