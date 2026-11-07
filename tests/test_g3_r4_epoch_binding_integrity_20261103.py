"""G3 R4.2: a populated scan witness map must be bound to its scan serial."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.ui import focused_filter_workflow as workflow


@pytest.mark.parametrize("epoch_serial", [None, 7])
def test_populated_epoch_witness_with_missing_or_stale_serial_fails_closed(
    tmp_path, epoch_serial,
):
    project = SimpleNamespace(root=tmp_path, images=[])
    review = SimpleNamespace(
        parent=SimpleNamespace(project=project),
        _filter_scan_epoch_source_witnesses={0: ("synthetic-source-witness",)},
        _filter_scan_epoch_source_serial=epoch_serial,
        _filter_scan_serial=8,
        _filter_scan_epoch_project=project,
        _filter_scan_epoch_pages=(),
        _filter_scan_epoch_project_root=tmp_path,
        _filter_scan_epoch_invalidated=False,
        _filter_scan_complete=False,
    )

    assert workflow._verify_active_filter_scan_epoch_sources(
        review, SimpleNamespace(),
    ) is False, (
        "a populated witness map with no matching epoch serial must not "
        "skip ProjectState/source ownership validation"
    )


def test_legacy_helper_without_epoch_witnesses_keeps_compatibility():
    review = SimpleNamespace(
        _filter_scan_epoch_source_witnesses=None,
        _filter_scan_epoch_source_serial=None,
        _filter_scan_serial=8,
    )

    assert workflow._verify_active_filter_scan_epoch_sources(
        review, SimpleNamespace(),
    ) is True
