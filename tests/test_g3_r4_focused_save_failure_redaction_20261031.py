"""G3 focused-save failure must preserve unsaved rows without disclosing source paths.

Synthetic PDIC bytes and callback failures only; this is not operator E3.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from picture_capture.ui import focused_filter_workflow as workflow


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


@pytest.mark.parametrize("newer_edit", [False, True])
def test_focused_save_failure_redacts_private_path_and_retains_edit(
    tmp_path, capsys, newer_edit,
):
    page = tmp_path / "001.png"
    pdic = tmp_path / "001.pdic"
    original_bytes = b"unchanged-synthetic-PDIC-bytes\n"
    pdic.write_bytes(original_bytes)
    point = (13, 27)
    old_change = {
        "page_index": 0, "x": point[0], "y": point[1],
        "original_word": "old", "new_word": "first edit",
    }
    target = {
        "page_index": 0, "x": point[0], "y": point[1],
        "original_word": "old", "current_word": "first edit",
    }
    calls, alerts = [], []
    status = _Var()
    parent = SimpleNamespace(
        project=SimpleNamespace(images=[page]),
        status_var=status,
        _start_ui_worker=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    review = SimpleNamespace(
        parent=parent,
        filtered_targets=[target],
        _filter_save_job=None,
        _filter_save_running=False,
        _filter_pending_changes={0: {point: old_change}},
        _filter_close_after_save=True,
        _focused_timing_session=None,
    )
    deps = SimpleNamespace(
        messagebox=SimpleNamespace(
            showerror=lambda title, message, **kwargs: alerts.append((title, message))
        ),
        _apply_focused_review_page_updates=lambda *args: None,
    )

    workflow._flush_focused_changes(review, deps)
    assert len(calls) == 1
    (_, _worker, _done, failed), options = calls[0]
    assert options == {"wait_on_close": True}
    assert review._filter_save_running is True
    assert review._filter_pending_changes == {}

    if newer_edit:
        target["current_word"] = "second edit"
        review._filter_pending_changes[0] = {
            point: {**old_change, "new_word": "second edit"}
        }

    failed(
        OSError("PRIVATE_SOURCE_PATH_DO_NOT_DISCLOSE"),
        "TRACE_PRIVATE_SOURCE_PATH_DO_NOT_DISCLOSE",
    )

    assert review._filter_save_running is False
    assert review._filter_close_after_save is False
    assert review._filter_pending_changes[0][point]["new_word"] == (
        "second edit" if newer_edit else "first edit"
    )
    assert target["original_word"] == "old"
    assert pdic.read_bytes() == original_bytes
    assert len(alerts) == 1
    assert "失败" in status.get() and "失败" in alerts[0][0]
    output = capsys.readouterr()
    presented = "\n".join(
        (status.get(), *alerts[0], output.out, output.err)
    )
    assert "PRIVATE_SOURCE_PATH_DO_NOT_DISCLOSE" not in presented
