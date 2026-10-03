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

    assert '_BUTTON_TEXT = "单行切图"' in runtime_source
    assert '_TARGET_TEXT = "词条切图"' in runtime_source
    assert "_pack_before(button, target)" in runtime_source
    assert "_grid_before(button, target)" in runtime_source
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


def test_gui_composition_installs_single_line_postproduction_extension():
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "src" / "picture_capture" / "bootstrap" / "gui.py"
    ).read_text(encoding="utf-8")
    assert "install_postproduction_single_line_runtime" in source
    assert "install_postproduction_single_line_runtime(app_module)" in source
