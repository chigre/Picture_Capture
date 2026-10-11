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
    assert "round(2.5 * crop.height)" in pinned
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
