"""Regression tests for one (and only one) pinned proofreading preview.

The legacy review_pinned_entry_preview widget used to insert a second
image between the black-framed active preview and the ordinary editor rows.
"""
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from picture_capture.models import AppSettings, Entry


def test_review_has_exactly_one_pinned_preview_owner():
    import picture_capture.app as app
    import picture_capture.review_entry_classification_ui as classification_ui

    app_source = Path(app.__file__).read_text(encoding="utf-8")
    classification_source = Path(classification_ui.__file__).read_text(encoding="utf-8")
    assert app_source.count("self.active_crop_host = ttk.Frame(editor_area") == 1
    assert app_source.count("self.active_crop_label = tk.Label(self.active_crop_frame") == 1
    assert "initialize_review_entry_classification" not in app_source
    assert "initialize_pinned_entry_preview" not in classification_source
    assert "refresh_pinned_entry_preview" not in classification_source
    assert not (Path(app.__file__).parent / "review_pinned_entry_preview.py").exists()


def test_all_inline_crops_ignore_detected_large_head_height(monkeypatch):
    import picture_capture.app as app

    settings = AppSettings(
        character_height=30,
        row_padding=2,
        entry_regular_crop_height=36,
        entry_oversized_crop_height=96,
    )
    entry = Entry(
        word="八階",
        x=12,
        y=70,
        ocr_source="ordinary_large_head_evidence",
        ocr_visual_run_height=110.0,
        ocr_oversized_cjk=True,
    )
    geometry = SimpleNamespace(transform=SimpleNamespace(kind="identity"), top=0)
    image = Image.new("RGB", (180, 400), "white")
    monkeypatch.setattr(app, "line_box", lambda *_args: (10, 70, 110, 100))

    ordinary = app._review_line_box(
        entry, geometry, image, settings, ordinary_height_only=True,
    )
    classified = app._review_line_box(entry, geometry, image, settings)
    assert ordinary[3] - ordinary[1] == 36
    assert classified[3] - classified[1] > 36


def test_pinned_preview_uses_regular_source_box_while_rows_stay_normal():
    import picture_capture.app as app

    source = Path(app.__file__).read_text(encoding="utf-8")
    render_request = source.split("    def _request_render_rows(", 1)[1].split(
        "    def render_rows(", 1
    )[0]
    worker = render_request.split("        def worker():", 1)[1].split(
        "        def done(payload)", 1
    )[0]
    pinned = source.split("    def _update_active_crop_preview(", 1)[1].split(
        "    def _ordinary_review_photo(", 1
    )[0]
    assert "ordinary_height_only=True" in worker
    assert "ordinary_height_only=True" in pinned
    assert 'extended_review_crop_box(' in pinned
    assert 'ordinary_box = _review_line_box(' in pinned
    assert 'round(multiplier * crop.height)' in pinned
    assert 'center_y - half_height' not in pinned
    assert '_review_crop_context(' in pinned
    assert 'themed_display_image(crop, self.parent.appearance_mode)' in source


def test_review_activity_uses_its_rendered_entry_not_a_resorted_main_index(monkeypatch):
    """A review row must still refer to the same PDIC Entry after main reordering."""
    from types import SimpleNamespace
    import picture_capture.app as app_module

    first = SimpleNamespace(x=1, y=10, word="first")
    second = SimpleNamespace(x=1, y=20, word="second")
    selected = []
    candidate_values = []
    monkeypatch.setattr(app_module, "sync_review_entry_classification", lambda _review: None)
    review = SimpleNamespace(
        row_entries=[first, second],
        _bound_row_entries=lambda: [first, second],
        active_index=0,
        _update_active_crop_preview=lambda _index: None,
        _update_title=lambda: None,
        _candidate_for_entry=lambda entry: entry.word,
        _show_ocr_options=lambda candidate: candidate_values.append(candidate),
        vars=[SimpleNamespace(get=lambda: "first")],
        locate_reference_word=lambda *_args: None,
        _refresh_cc_simplified_comparison=lambda *_args: None,
        _schedule_network_lookup=lambda *_args: None,
        parent=SimpleNamespace(
            _ordered_entries_reading_order=lambda: [second, first],
            highlight_review_entry=lambda entry: selected.append(entry),
        ),
    )
    app_module.ReviewWindow.set_active(review, 0)
    assert selected == [first]
    assert candidate_values == ["first"]


def test_preview_ocr_and_async_crops_share_stable_review_entry_identity():
    from pathlib import Path
    import picture_capture.app as app_module

    source = Path(app_module.__file__).read_text(encoding="utf-8")
    for before, after in (
        ("def _refresh_editor_ocr_compare(", "def _show_ocr_options("),
        ("def _update_active_crop_preview(", "def _ordinary_review_photo("),
        ("def set_active(", "def _scroll_editor_into_view("),
    ):
        segment = source.split("    " + before, 1)[1].split("    " + after, 1)[0]
        assert "self._bound_row_entries()" in segment
        assert "self.parent._ordered_entries_reading_order()" not in segment
    assert "(id(source), int(entry.x), int(entry.y), str(entry.word))" in source
    assert "(id(entry), int(entry.x), int(entry.y), str(entry.word))" in source


def test_review_extended_multiplier_first_row_is_persisted_and_updates_pinned_only():
    from pathlib import Path
    from picture_capture import app as module
    from picture_capture.models import AppSettings

    assert AppSettings().review_extended_crop_height_multiplier == 2.5
    source = Path(module.__file__).read_text(encoding="utf-8")
    ui = source.split(
        'review_info = self._review_collapsible_section(', 1
    )[1].split('def add_review_height_control(', 1)[0]
    assert 'text="切片更大高度范围倍数:"' in ui
    assert "review_extended_crop_multiplier_var" in ui
    assert ui.index('text="切片更大高度范围倍数:"') < ui.index('def add_review_height_control') if 'def add_review_height_control' in ui else True
    apply = source.split('    def _apply_review_extended_crop_multiplier_setting(', 1)[1].split(
        '    def _apply_review_main_ocr_display_options(', 1
    )[0]
    assert "self.parent.settings.review_extended_crop_height_multiplier = multiplier" in apply
    assert "self._active_crop_fixed_size = None" in apply
    assert "self._update_active_crop_preview(self.active_index)" in apply
    assert "self._request_render_rows(" not in apply


def test_pinned_crop_uses_exact_ordinary_top_and_bottom_only_extension():
    from picture_capture.review_crop_extension import (
        extended_review_crop_box, parse_review_crop_multiplier,
    )
    import pytest

    ordinary = (8, 35, 70, 55)
    assert extended_review_crop_box(ordinary, 250, 2.5) == (8, 35, 70, 85)
    assert extended_review_crop_box(ordinary, 70, 2.5) == (8, 35, 70, 70)
    assert extended_review_crop_box(ordinary, 250, 1.0) == ordinary
    assert parse_review_crop_multiplier("2.5") == 2.5
    assert parse_review_crop_multiplier("3.25") == 3.25
    for invalid in ("", "0.7", "11", "nan", "inf"):
        with pytest.raises(ValueError):
            parse_review_crop_multiplier(invalid)
