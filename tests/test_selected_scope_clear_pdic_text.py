"""Selected-scope PDIC text clearing preserves every marker field."""
from pathlib import Path

from picture_capture.formats import read_pdic
from picture_capture.pdic_text_cleanup import clear_pdic_words


def test_clear_words_preserves_coordinates_percent_and_page_metadata(tmp_path):
    path = tmp_path / "page.PDIC"
    old = (
        "Alpha#12#34#6.0#17.0#page#@#next\n"
        "Beta#15#50#7.5#25.0#page#@#next\n"
    )
    path.write_text(old, encoding="utf-8")
    assert clear_pdic_words(path) == 2
    assert path.read_text(encoding="utf-8") == (
        "#12#34#6.0#17.0#page#@#next\n"
        "#15#50#7.5#25.0#page#@#next\n"
    )
    rows = read_pdic(path)
    assert [(r.word, r.x, r.y) for r in rows] == [("", 12, 34), ("", 15, 50)]
    assert clear_pdic_words(path) == 0


def test_clear_words_missing_file_is_noop(tmp_path):
    path = tmp_path / "missing.PDIC"
    assert clear_pdic_words(path) == 0
    assert not path.exists()


def test_clear_words_validates_before_overwriting(tmp_path):
    path = tmp_path / "broken.PDIC"
    path.write_text("Alpha#not-a-number#20\n", encoding="utf-8")
    try:
        clear_pdic_words(path)
    except ValueError:
        pass
    else:
        raise AssertionError("Malformed PDIC must be rejected")
    assert path.read_text(encoding="utf-8") == "Alpha#not-a-number#20\n"


def test_clear_text_button_uses_page_range_confirmation_and_batch():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    begin = source.index("    def clear_text(self)")
    end = source.index("\n    def ", begin + 10)
    block = source[begin:end]
    assert "self.selected_page_indices()" in block
    assert 'messagebox.askyesno(' in block
    assert 'self.save_pdic(silent=True)' in block
    assert 'clear_pdic_words(pdic_path(pages[index]))' in block
    assert 'self._start_batch_task(' in block
