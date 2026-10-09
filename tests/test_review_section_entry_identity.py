"""Regression: proofreading text is anchored to marker identity across sections."""
from types import SimpleNamespace

from PIL import Image

from picture_capture.app import ReviewWindow
from picture_capture.formats import read_pdic, write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.page_sections import PageSection
from picture_capture.processing_core import derive_geometry, sort_entries_reading_order
from picture_capture.review_main_editor_sync import reconcile_main_editors_after_review


class FakeEditor:
    def __init__(self, text):
        self.text = text
    def get(self):
        return self.text
    def delete(self, start, stop):
        self.text = ""
    def insert(self, start, text):
        self.text = text


def test_saved_review_words_follow_section_order_not_raw_column_order(tmp_path):
    image = Image.new("RGB", (220, 150), "white")
    settings = AppSettings(
        columns=2, manual_x=8, column_width=90, column_gap=18,
        start_y=0, bottom_y=150, ordinary_auto_layout=False,
    )
    geometry = derive_geometry(image, settings)
    sections = [PageSection(0, 60), PageSection(60, 150)]
    # PDIC may initially be column-major, but SECTION order is row-first.
    top_left = Entry("old-A", 12, 20)
    bottom_left = Entry("old-C", 12, 85)
    top_right = Entry("old-B", 125, 20)
    bottom_right = Entry("old-D", 125, 85)
    physical = [top_left, bottom_left, top_right, bottom_right]
    reading = sort_entries_reading_order(physical, geometry, sections)
    assert reading == [top_left, top_right, bottom_left, bottom_right]

    buffers = [FakeEditor(f"review-{letter}") for letter in "ABCD"]
    fake = SimpleNamespace(
        row_entries=reading,
        vars=buffers,
        parent=SimpleNamespace(entries=physical),
        _rendered_page_stem="page",
        _capture_simplified_edits=lambda stem: None,
        _bound_row_entries=lambda: reading,
    )
    ReviewWindow._commit_edits(fake)
    path = tmp_path / "page.PDIC"
    write_pdic(path, reading, image.width, ("page", "@", "@"))
    stored = read_pdic(path)
    assert [(entry.word, entry.x, entry.y) for entry in stored] == [
        ("review-A", 12, 20),
        ("review-B", 125, 20),
        ("review-C", 12, 85),
        ("review-D", 125, 85),
    ]


def test_review_edits_replace_stale_main_canvas_buffers():
    first, second = Entry("review-A", 12, 20), Entry("review-B", 125, 20)
    stale = FakeEditor("before-A")
    unrelated = FakeEditor("unrelated")
    app = SimpleNamespace(entry_editor_bindings=[
        (stale, first), (unrelated, Entry("other", 12, 110)),
    ])
    reconcile_main_editors_after_review(app, [first, second])
    assert stale.get() == "review-A"
    assert unrelated.get() == "unrelated"


def test_simplified_sidecar_uses_rendered_identity_after_section_reorder():
    original_a = Entry("source-A", 12, 20)
    original_b = Entry("source-B", 125, 20)
    records = {}
    fake = SimpleNamespace(
        simplified_vars=[FakeEditor("simplified-A"), FakeEditor("simplified-B")],
        simplified_manual_flags=[True, True],
        simplified_actual_values=[None, None],
        _simplified_page_records=lambda stem: records,
        _bound_row_entries=lambda: [original_a, original_b],
        parent=SimpleNamespace(
            current_page=SimpleNamespace(stem="page"),
            _ordered_entries_reading_order=lambda: [original_b, original_a],
        ),
        _simplified_display_from_value=lambda source, value, manual: source,
        _simplified_dirty_pages=set(),
    )
    ReviewWindow._capture_simplified_edits(fake, "page")
    assert records["12,20"]["text"] == "simplified-A"
    assert records["125,20"]["text"] == "simplified-B"
