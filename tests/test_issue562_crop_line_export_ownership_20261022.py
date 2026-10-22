"""#562: no root shims; page-level crop/export owners and spawn ABI are real."""
from __future__ import annotations

import importlib.util
import pickle
from pathlib import Path

from picture_capture.crop import single_line_parallel, unlined_line_export

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_crop_page_export_owners_are_physical_and_retired_paths_absent() -> None:
    for retired in ("single_line_parallel", "unlined_line_export"):
        assert not (ROOT / f"{retired}.py").exists()
        assert (ROOT / "crop" / f"{retired}.py").is_file()
        assert importlib.util.find_spec(f"picture_capture.{retired}") is None
        assert importlib.util.find_spec(f"picture_capture.crop.{retired}") is not None


def test_spawn_worker_functions_and_unlined_result_types_have_real_package_paths() -> None:
    for function, name in (
        (single_line_parallel.single_line_page_job, "single_line_parallel"),
        (unlined_line_export.export_unlined_page_job, "unlined_line_export"),
    ):
        assert function.__module__ == f"picture_capture.crop.{name}"
        assert pickle.loads(pickle.dumps(function)) is function

    for cls in (unlined_line_export.UnlinedRow, unlined_line_export.UnlinedPageResult):
        assert cls.__module__ == "picture_capture.crop.unlined_line_export"
        assert pickle.loads(pickle.dumps(cls)) is cls


def test_crop_coordinator_public_exports_exist() -> None:
    assert callable(single_line_parallel.configured_single_line_workers)
    assert callable(single_line_parallel.run_single_line_pages)
    assert callable(unlined_line_export.run_unlined_export)
    assert callable(unlined_line_export.export_unlined_page_job)
