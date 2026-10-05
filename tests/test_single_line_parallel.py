from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

import picture_capture.single_line_parallel as single_line_parallel


def test_single_line_parallel_reuses_integrated_crop_worker_setting(tmp_path, monkeypatch):
    root = tmp_path / "project"
    path = root / "QT" / "_CropSettings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"parallel_workers": 3}), encoding="utf-8")

    monkeypatch.setattr(
        single_line_parallel,
        "resolve_crop_worker_count",
        lambda configured: int(configured),
    )
    assert single_line_parallel.configured_single_line_workers(root) == 3


def test_single_line_parallel_serial_coordinator_owns_shared_log(tmp_path, monkeypatch):
    root = tmp_path / "project"
    images = (root / "p1.jpg", root / "p2.jpg")
    logged = []
    progress = []

    monkeypatch.setattr(single_line_parallel, "configured_single_line_workers", lambda _root: 1)
    monkeypatch.setattr(
        single_line_parallel,
        "single_line_page_job",
        lambda _root, image, index, _settings, _output, _merge: (
            index,
            Path(image).name,
            [SimpleNamespace(filename=f"{Path(image).stem}.png")],
            False,
        ),
    )
    monkeypatch.setattr(
        single_line_parallel,
        "append_crop_log",
        lambda _root, records: logged.append([record.filename for record in records]),
    )

    result = single_line_parallel.run_single_line_pages(
        root,
        images,
        (0, 1),
        object(),
        lambda *args: progress.append(args),
    )

    assert result[0] == 2
    assert result[1] == 2
    assert result[4] == 1
    assert logged == [["p1.png"], ["p2.png"]]
    assert [item[0] for item in progress] == [1, 2]
    assert all(item[-1] == 1 for item in progress)


def test_single_line_parallel_source_keeps_page_files_independent_and_log_coordinated():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "single_line_parallel.py"
    ).read_text(encoding="utf-8")
    page_start = source.index("def single_line_page_job(")
    page_end = source.index("\ndef run_single_line_pages(", page_start)
    page_job = source[page_start:page_end]
    coordinator = source[page_end:]

    assert "ProcessPoolExecutor" in source
    assert 'get_context("spawn")' in source
    assert 'PARALLEL_WORKERS_KEY = "parallel_workers"' in source
    assert "resolve_crop_worker_count(configured)" in source
    assert "split_single_lines(" in page_job
    assert "merge_page_line_images(" in page_job
    assert "append_crop_log(" not in page_job
    assert "append_crop_log(project_root, records)" in coordinator
    assert "max_workers=workers" in coordinator
    assert "as_completed(futures)" in coordinator


def test_main_single_line_controller_reports_effective_parallelism_through_shared_runner():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "controllers" / "crop.py"
    ).read_text(encoding="utf-8")

    assert "configured_single_line_workers(project_root)" in source
    assert 'f"并行×{workers}"' in source
    assert "single_line_page_job" in source
    assert "app._start_parallel_batch_task(" in source
    assert "run_single_line_pages(" not in source
