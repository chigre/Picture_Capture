from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import picture_capture.processing as processing
from picture_capture import crop_logging
from picture_capture.project_storage import crop_log_path, qt_root


def test_phase7l_core_reexports_crop_logging_helpers() -> None:
    assert processing._core.append_crop_log is crop_logging.append_crop_log
    assert (
        processing._core.append_illustration_crop_log
        is crop_logging.append_illustration_crop_log
    )


def test_crop_log_keeps_source_pixel_header_and_rows(tmp_path: Path) -> None:
    log = crop_log_path(tmp_path)
    log.parent.mkdir(parents=True, exist_ok=True)
    records = [
        SimpleNamespace(
            page="page001",
            filename="page001_SW_000.png",
            box=(10, 20, 40, 65),
        )
    ]

    crop_logging.append_crop_log(tmp_path, records)
    crop_logging.append_crop_log(tmp_path, records)

    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines[0] == (
        "# coordinate_space=source_image_pixels; "
        "columns=page,file,source_x,source_y,width,height"
    )
    assert lines[1] == "page001\tpage001_SW_000.png\t10\t20\t30\t45"
    assert lines[2] == lines[1]
    assert sum(line.startswith("# coordinate_space=") for line in lines) == 1


def test_illustration_crop_log_keeps_legacy_line_format(tmp_path: Path) -> None:
    event = SimpleNamespace(
        page="page001",
        polygon_index=3,
        name="Plate",
        associated_word="alpha",
        relation="linked",
        action="saved",
        filename="page001_PPP003.png",
    )

    crop_logging.append_illustration_crop_log(tmp_path, [event])

    path = qt_root(tmp_path) / "_illustration_crop_log.txt"
    assert path.read_text(encoding="utf-8") == (
        "page001\tPPP003\tPlate\talpha\tlinked\tsaved\t"
        "page001_PPP003.png\n"
    )


def test_phase7l_public_log_assignment_still_mirrors_into_core(monkeypatch) -> None:
    def fake_log(_root, _records) -> None:
        return None

    monkeypatch.setattr(processing, "append_crop_log", fake_log)

    assert processing._core.append_crop_log is fake_log
