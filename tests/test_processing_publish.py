from __future__ import annotations

from pathlib import Path

import picture_capture.processing as processing
from picture_capture import processing_publish


def test_phase7i_core_reexports_publish_helpers_from_new_owner() -> None:
    assert (
        processing._core._publish_temp_path
        is processing_publish._publish_temp_path
    )
    assert (
        processing._core._publish_file_transaction
        is processing_publish._publish_file_transaction
    )


def test_phase7i_public_temp_path_monkeypatch_still_drives_core_stage_text(
    tmp_path: Path, monkeypatch,
) -> None:
    target = tmp_path / "manifest.txt"
    staged = tmp_path / ".custom.tmp"
    seen: list[Path] = []

    def fake_temp_path(path: Path) -> Path:
        seen.append(Path(path))
        return staged

    monkeypatch.setattr(processing, "_publish_temp_path", fake_temp_path)

    result = processing._core._stage_text_file(target, "hello")

    assert result == staged
    assert seen == [target]
    assert staged.read_text(encoding="utf-8") == "hello"


def test_phase7i_public_publish_assignment_still_mirrors_into_core(monkeypatch) -> None:
    def fake_publish(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(processing, "_publish_file_transaction", fake_publish)

    assert processing._core._publish_file_transaction is fake_publish
