"""Direct-save regression: visible textbox text wins over old R3 sources.

Synthetic PDIC and simplified JSON, real persistence serializers.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.io.formats import pdic_path, read_pdic, write_pdic
from picture_capture.models import Entry
from picture_capture.persistence.project_storage import simplified_review_path_for_image
from picture_capture.proofreading import direct_review_save
from picture_capture.proofreading.simplified_review import read_records, write_records
from picture_capture.ui import review_simplified_workflow


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def case(tmp_path, *, old="原詞", original="新詞", shown="新简体", actual="旧简体",
         manual=True, source_word="前一版本"):
    page = tmp_path / "test.png"
    page.write_bytes(b"synthetic-page")
    row = Entry(old, 10, 20)
    write_pdic(pdic_path(page), [row], 100, (page.stem, "@", "@"))
    sidecar = simplified_review_path_for_image(page)
    write_records(sidecar, page.stem, {
        "10,20": {
            "x": 10, "y": 20, "source_word": source_word,
            "text": actual, "manual": manual,
        }
    })
    status = Value("")
    app = SimpleNamespace(
        current_page=page, current_index=0,
        project=SimpleNamespace(root=tmp_path), entries=[row],
        image=SimpleNamespace(width=100),
        pages_tuple=lambda: (page.stem, "@", "@"),
        entry_editor_bindings=[], status_var=status,
        _refresh_word_fill_check_from_line_count=lambda *a, **kw: None,
        _update_page_row=lambda *a, **kw: None,
    )
    review = SimpleNamespace(
        parent=app, _rendered_page_stem=page.stem,
        row_entries=[row], vars=[Value(original)],
        simplified_vars=[Value(shown)],
        simplified_actual_values=[actual],
        simplified_manual_flags=[manual],
        simplified_auto_refresh_flags=[False],
        _simplified_dirty_pages={page.stem},
        _simplified_page_cache={},
        _r3_simplified_source_bytes={},
        _simplified_display_from_value=lambda word, value, manual:
            review_simplified_workflow._simplified_display_from_value(
                None, word, value, manual,
            ),
    )
    review._bound_row_entries = lambda: list(review.row_entries)
    return page, sidecar, row, review


def test_original_and_simplified_textboxes_are_saved_despite_detached_history(tmp_path):
    page, sidecar, row, review = case(tmp_path)
    assert direct_review_save.direct_save_review(review)
    assert row.word == "新詞"
    assert read_pdic(pdic_path(page))[0].word == "新詞"
    assert read_records(sidecar)["10,20"] == {
        "x": 10, "y": 20, "source_word": "新詞",
        "text": "新简体", "manual": True,
    }
    assert review.parent.status_var.get().startswith("校对保存成功")


def test_untouched_equal_word_symbol_reopens_as_equal_simplified_word(tmp_path):
    page, sidecar, row, review = case(
        tmp_path, old="原詞", original="改詞", shown="√", actual="原詞",
        manual=False, source_word="历史版本",
    )
    direct_review_save.direct_save_review(review)
    assert read_pdic(pdic_path(page))[0].word == "改詞"
    saved = read_records(sidecar)["10,20"]
    assert saved["source_word"] == "改詞"
    assert saved["text"] == "改詞"  # "√" is display shorthand, not lexical data
    assert saved["manual"] is False


def test_simplified_only_edit_saves_exact_displayed_text(tmp_path):
    page, sidecar, _row, review = case(
        tmp_path, old="原詞", original="原詞", shown="人工修正",
        actual="旧转换", manual=False, source_word="不相符的来源",
    )
    direct_review_save.direct_save_review(review)
    assert read_records(sidecar)["10,20"]["text"] == "人工修正"
    assert read_records(sidecar)["10,20"]["manual"] is True
    assert read_pdic(pdic_path(page))[0].word == "原詞"


def test_failed_second_file_write_rolls_back_and_preserves_textboxes(
    tmp_path, monkeypatch,
):
    page, sidecar, row, review = case(tmp_path)
    pdic_before, sidecar_before = pdic_path(page).read_bytes(), sidecar.read_bytes()
    actual_publish = direct_review_save._publish
    attempts = []

    def fail_second(path, content):
        attempts.append(path)
        if path == sidecar:
            raise OSError("synthetic disk error")
        return actual_publish(path, content)

    monkeypatch.setattr(direct_review_save, "_publish", fail_second)
    with pytest.raises(OSError, match="synthetic disk error"):
        direct_review_save.direct_save_review(review)
    assert pdic_path(page).read_bytes() == pdic_before
    assert sidecar.read_bytes() == sidecar_before
    assert row.word == "原詞"
    assert review.vars[0].get() == "新詞"
    assert review.simplified_vars[0].get() == "新简体"


def test_stale_render_mapping_is_not_saved_into_wrong_entry(tmp_path):
    page, sidecar, row, review = case(tmp_path)
    prior = pdic_path(page).read_bytes(), sidecar.read_bytes()
    review.row_entries = [Entry("unrelated", 10, 20)]
    with pytest.raises(RuntimeError, match="加载|刷新"):
        direct_review_save.direct_save_review(review)
    assert (pdic_path(page).read_bytes(), sidecar.read_bytes()) == prior


def test_direct_writer_can_repeat_save_without_legacy_r3_source_prompt(tmp_path):
    page, sidecar, _row, review = case(tmp_path)
    direct_review_save.direct_save_review(review)
    direct_review_save.direct_save_review(review)
    assert read_pdic(pdic_path(page))[0].word == "新詞"
    assert read_records(sidecar)["10,20"]["text"] == "新简体"
