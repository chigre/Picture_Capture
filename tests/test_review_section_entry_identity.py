"""Regression: proofreading text is anchored to marker identity across sections."""
from types import SimpleNamespace

from PIL import Image

from picture_capture.app import ReviewWindow
from picture_capture.formats import read_pdic, write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.page_sections import PageSection, read_page_sections, write_page_sections
from picture_capture.processing_core import derive_geometry, sort_entries_reading_order
from picture_capture.project_storage import (
    migrate_legacy_project, page_sections_path_for_image, page_sections_read_path_for_image,
)
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
        columns=2, manual_x=8, column_width=90,
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


def test_migrated_page_sections_are_loaded_without_double_click(tmp_path):
    """Regression: original QT/SECTION files survived migration but went unread."""
    root = tmp_path / "dictionary"
    root.mkdir()
    page = root / "page.png"
    Image.new("RGB", (220, 150), "white").save(page)
    original = [PageSection(0, 60), PageSection(60, 150)]
    old_sidecar = write_page_sections(page, original)
    assert old_sidecar.is_file()
    migrate_legacy_project(root, "test")
    copied = root / "_PictureCapture" / "QT" / "PageSections" / "page.json"
    assert copied.is_file()
    canonical = page_sections_path_for_image(page)
    assert not canonical.exists()
    assert page_sections_read_path_for_image(page) == copied
    loaded = read_page_sections(page)
    assert loaded == original

    # The same two-section reading order must reach the main canvas and review.
    image = Image.new("RGB", (220, 150), "white")
    settings = AppSettings(columns=2, manual_x=8, column_width=90,
                           start_y=0, bottom_y=150, ordinary_auto_layout=False)
    geometry = derive_geometry(image, settings)
    physical = [Entry("A", 12, 20), Entry("C", 12, 85),
                Entry("B", 125, 20), Entry("D", 125, 85)]
    assert [e.word for e in sort_entries_reading_order(physical, geometry, loaded)] == [
        "A", "B", "C", "D",
    ]


def test_edited_section_sidecar_takes_precedence_over_migrated_copy(tmp_path):
    root = tmp_path / "dictionary"
    root.mkdir()
    page = root / "page.png"
    Image.new("RGB", (220, 150), "white").save(page)
    old_sections = [PageSection(0, 60), PageSection(60, 150)]
    write_page_sections(page, old_sections)
    migrate_legacy_project(root, "test")
    migrated = page_sections_read_path_for_image(page)
    original_bytes = migrated.read_bytes()

    edited_sections = [PageSection(0, 100), PageSection(100, 150)]
    new_sidecar = write_page_sections(page, edited_sections)
    assert page_sections_read_path_for_image(page) == new_sidecar
    assert read_page_sections(page) == edited_sections
    assert migrated.read_bytes() == original_bytes


def test_preloaded_page_section_snapshot_is_rechecked_before_sorting():
    """The on-disk SECTION, not an old background snapshot, drives UI order."""
    from pathlib import Path
    import picture_capture.app as app_module

    source = Path(app_module.__file__).read_text(encoding="utf-8")
    start = source.index("    def load_page(")
    end = source.index("    def change_page(", start)
    block = source[start:end]
    assert 'self.page_sections = list(preloaded.get("page_sections") or [])' in block
    assert "latest_sections = read_page_sections(self.current_page)" in block
    assert "if latest_sections != self.page_sections:" in block
    assert block.index("latest_sections = read_page_sections") < block.index(
        "self._sort_entries_reading_order()"
    )


def test_disabling_migrated_sections_does_not_resurrect_old_reading_order(tmp_path):
    root = tmp_path / "dictionary"
    root.mkdir()
    page = root / "page.png"
    Image.new("RGB", (220, 150), "white").save(page)
    original = [PageSection(0, 60), PageSection(60, 150)]
    write_page_sections(page, original)
    migrate_legacy_project(root, "test")
    historical_path = page_sections_read_path_for_image(page)
    historical_bytes = historical_path.read_bytes()

    disabled = write_page_sections(page, [])
    assert disabled.is_file()  # Explicit managed-project Section=0 marker.
    assert page_sections_read_path_for_image(page) == disabled
    assert read_page_sections(page) == []
    assert historical_path.read_bytes() == historical_bytes

    # Re-enable and disable again: the old data may never override Section=0.
    write_page_sections(page, [PageSection(0, 150)])
    assert read_page_sections(page) == [PageSection(0, 150)]
    write_page_sections(page, [])
    assert read_page_sections(page) == []


def test_section_zero_still_removes_sidecar_when_no_migrated_copy(tmp_path):
    page = tmp_path / "page.png"
    Image.new("RGB", (220, 150), "white").save(page)
    sidecar = write_page_sections(page, [PageSection(0, 150)])
    assert sidecar.is_file()
    assert write_page_sections(page, []) == sidecar
    assert not sidecar.exists()
    assert read_page_sections(page) == []
