"""G3 R4.2: a human correction owns its displayed image and SECTION source.

Deterministic synthetic 8x8 BMP and PDIC; no real scans or operator E3.
"""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.io.formats import read_pdic, write_pdic
from picture_capture.persistence.project_storage import (
    page_sections_read_path_for_image, pdic_path_for_image,
)
from picture_capture.proofreading.focused_crop_source_fingerprint import (
    focused_crop_source_witness,
)
from picture_capture.proofreading.focused_pdic_updates import (
    FocusedPdicDeps, apply_focused_review_page_updates,
)
from picture_capture.ui import focused_filter_workflow as flow


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _files(tmp_path: Path):
    page = tmp_path / "001.bmp"
    Image.new("RGB", (8, 8), "black").save(page)
    pdic = pdic_path_for_image(page)
    pdic.write_bytes(b"old#3#4#37.5#50#001#@#@\n")
    section = page_sections_read_path_for_image(page)
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_bytes(b'{"revision":"A"}')
    target = {
        "page_index": 0, "page_name": page.name, "x": 3, "y": 4,
        "original_word": "old", "current_word": "old",
        "column_number": 1, "sequence_number": 1,
    }
    crop_witness = focused_crop_source_witness([page], [target])
    return page, pdic, section, target, crop_witness


def _replace_without_metadata_change(path: Path, new_content: bytes):
    old_stat = path.stat()
    assert len(new_content) == old_stat.st_size
    path.write_bytes(new_content)
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    assert path.stat().st_size == old_stat.st_size
    assert path.stat().st_mtime_ns == old_stat.st_mtime_ns


def _alter(tmp_path: Path, changed: str, page: Path, section: Path):
    if changed == "image":
        replacement = tmp_path / "replacement.bmp"
        Image.new("RGB", (8, 8), "red").save(replacement)
        _replace_without_metadata_change(page, replacement.read_bytes())
    elif changed == "section":
        _replace_without_metadata_change(section, b'{"revision":"B"}')
    elif changed == "section_removed":
        section.unlink()
    else:
        raise AssertionError(changed)


def _save_deps(page: Path, save_count: list):
    pdic_deps = FocusedPdicDeps(
        pdic_path=pdic_path_for_image,
        read_pdic=read_pdic,
        replace=replace,
        Image=Image,
        _write_pdic_atomic=lambda *args: (
            save_count.append(1), write_pdic(*args)
        )[-1],
    )
    def commit(the_page, pages, index, changes):
        return apply_focused_review_page_updates(
            the_page, pages, index, changes, deps=pdic_deps
        )
    alerts = []
    return SimpleNamespace(
        _apply_focused_review_page_updates=commit,
        messagebox=SimpleNamespace(
            showerror=lambda title, message, **kw: alerts.append((title, message)),
        ),
    ), alerts


def _review(page: Path, target: dict):
    calls = []
    parent = SimpleNamespace(
        project=SimpleNamespace(images=[page]),
        current_index=0,
        entries=[SimpleNamespace(
            word="old", x=3, y=4, confidence=0.5,
            ocr_source="ocr", final_engine="ocr", manually_selected=False,
        )],
        status_var=_Var(),
        _start_ui_worker=lambda *args, **kw: calls.append((args, kw)),
    )
    review = SimpleNamespace(
        parent=parent,
        _filter_rows_active=True,
        filtered_targets=[target],
        _filter_pending_changes={},
        _filter_save_job=None,
        _filter_save_running=False,
        _filter_close_after_save=True,
        _focused_timing_session=None,
    )
    return review, calls


def _edited_change(witness, *, word="edit-1"):
    return {
        "page_index": 0, "x": 3, "y": 4,
        "original_word": "old", "new_word": word,
        "_focused_save_source_witness": witness,
    }


def _save_witness(crop_witness):
    # Image and SECTION, excluding PDIC, which our own valid edit changes.
    row = crop_witness[1][0]
    return ("focused-save-source-v1", row[1], row[3])


def test_rendered_batch_binds_actual_source_to_human_change(tmp_path):
    page, _pdic, _section, target, crop_witness = _files(tmp_path)
    key = (0, (("source",), crop_witness))
    rendered = []
    review, _calls = _review(page, target)
    review.filtered_batch_index = 0
    review.review_zoom_auto = False
    review._focused_batch_size = lambda: 1
    review._filter_available_target_count = lambda: 1
    review._filter_batch_snapshot = lambda _: (
        key, [dict(target)], [page], None, 700, 640, 1.0, False
    )
    review._update_filter_batch_indicator = lambda: None
    review._render_filter_batch = lambda targets, crops: rendered.append(targets)
    review._reset_rows_scroll_top = lambda: None
    review._schedule_filter_next_batch_preload = lambda: None
    assert flow._apply_filter_batch_payload(
        review, SimpleNamespace(_format_layout_percent=str),
        0, key, ([object()], 1.0, [(1, 1)])
    )
    assert rendered and target["_focused_save_source_witness"] == _save_witness(
        crop_witness
    )
    timers = []
    review.after = lambda ms, fn: timers.append(ms) or "save"
    review._flush_focused_changes = lambda: None
    flow._queue_focused_change(
        review, SimpleNamespace(tk=SimpleNamespace(TclError=Exception)),
        target, "edit-1",
    )
    assert timers == [160]
    assert review._filter_pending_changes[0][(3, 4)][
        "_focused_save_source_witness"
    ] == _save_witness(crop_witness)


@pytest.mark.parametrize("changed", ["image", "section", "section_removed"])
@pytest.mark.parametrize("newer_edit", [False, True])
def test_source_changed_after_display_before_worker_preserves_human_edits(
    tmp_path, changed, newer_edit,
):
    page, pdic, section, target, crop_witness = _files(tmp_path)
    expected = _save_witness(crop_witness)
    review, calls = _review(page, target)
    target["current_word"] = "edit-1"
    review._filter_pending_changes[0] = {
        (3, 4): _edited_change(expected)
    }
    writes = []
    deps, alerts = _save_deps(page, writes)
    flow._flush_focused_changes(review, deps)
    assert len(calls) == 1 and review._filter_pending_changes == {}
    _name, worker, _done, failed = calls[0][0]
    old_pdic_bytes = pdic.read_bytes()
    if newer_edit:
        target["current_word"] = "edit-2"
        review._filter_pending_changes[0] = {
            (3, 4): _edited_change(expected, word="edit-2")
        }
    _alter(tmp_path, changed, page, section)
    with pytest.raises(RuntimeError, match="(来源|变化|拒绝|SECTION)"):
        worker()
    failed(RuntimeError("PRIVATE_IMAGE_HEADWORD_PATH"), "PRIVATE_TRACE")
    assert writes == [] and pdic.read_bytes() == old_pdic_bytes
    assert review._filter_save_running is False
    assert review._filter_close_after_save is False
    assert target["original_word"] == "old"
    assert review._filter_pending_changes[0][(3, 4)]["new_word"] == (
        "edit-2" if newer_edit else "edit-1"
    )
    assert len(alerts) == 1
    assert "PRIVATE_" not in (
        parent_output := review.parent.status_var.get() + str(alerts)
    )


def test_unchanged_attested_source_saves_exact_human_edit(tmp_path):
    page, pdic, _section, target, crop_witness = _files(tmp_path)
    review, calls = _review(page, target)
    review._filter_close_after_save = False
    review.after = lambda ms, callback: "next"
    review._finish_close_review = lambda: None
    target["current_word"] = "edit-1"
    review._filter_pending_changes[0] = {
        (3, 4): _edited_change(_save_witness(crop_witness))
    }
    writes = []
    deps, _alerts = _save_deps(page, writes)
    flow._flush_focused_changes(review, deps)
    _name, worker, done, _failed = calls[0][0]
    done(worker())
    assert writes == [1]
    assert read_pdic(pdic)[0].word == "edit-1"
    assert target["original_word"] == "edit-1"
    assert review._filter_pending_changes == {}


def test_writer_rechecks_source_after_pdic_read_before_publication(tmp_path):
    page, pdic, section, _target, crop_witness = _files(tmp_path)
    original_pdic = pdic.read_bytes()
    writes = []
    def read_pdic_during_save(path):
        rows = read_pdic(path)
        # Simulates an external SECTION update after initial provenance
        # checks/PDIC parse, but before _write_pdic_atomic publication.
        _replace_without_metadata_change(section, b'{"revision":"B"}')
        return rows
    deps = FocusedPdicDeps(
        pdic_path=pdic_path_for_image, read_pdic=read_pdic_during_save,
        replace=replace, Image=Image,
        _write_pdic_atomic=lambda *a: writes.append(a),
    )
    with pytest.raises(RuntimeError, match="(来源|变化|拒绝|SECTION)"):
        apply_focused_review_page_updates(
            page, [page], 0,
            [_edited_change(_save_witness(crop_witness))], deps=deps,
        )
    assert writes == []
    assert pdic.read_bytes() == original_pdic


def test_missing_render_provenance_cannot_publish_live_filter_edits(tmp_path):
    page, pdic, _section, target, _crop_witness = _files(tmp_path)
    before = pdic.read_bytes()
    review, calls = _review(page, target)
    review._filter_pending_changes[0] = {
        (3, 4): {k: v for k, v in _edited_change(None).items()
                 if k != "_focused_save_source_witness"}
    }
    writes = []
    deps, _alerts = _save_deps(page, writes)
    flow._flush_focused_changes(review, deps)
    worker = calls[0][0][1]
    with pytest.raises(RuntimeError, match="(来源|校验|拒绝)"):
        worker()
    assert writes == [] and pdic.read_bytes() == before
