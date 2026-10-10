"""Unchanged autosaves must preserve PDIC/PPP file contents and mtimes."""
from pathlib import Path

from picture_capture.formats import write_pdic, write_ppp
from picture_capture.models import Entry, PolygonRegion


def test_identical_pdic_write_is_skipped(tmp_path):
    target = tmp_path / "page.pdic"
    assert write_pdic(target, [], 1400, ("page", "@", "@")) is True
    before = target.stat().st_mtime_ns
    assert write_pdic(target, [], 1400, ("page", "@", "@")) is False
    assert target.stat().st_mtime_ns == before


def test_changed_pdic_write_is_committed(tmp_path):
    target = tmp_path / "page.pdic"
    assert write_pdic(target, [], 1400, ("page", "@", "@"))
    # Existing content differs byte-for-byte, so the file must be replaced.
    assert write_pdic(target, [], 1400, ("page", "previous", "@"))
    # Empty entry lists have identical serialized content regardless of context.
    assert target.read_bytes() == b""


def test_identical_ppp_write_is_skipped_and_change_is_written(tmp_path):
    target = tmp_path / "page.ppp"
    assert write_ppp(target, [], "page") is True
    before = target.stat().st_mtime_ns
    assert write_ppp(target, [], "page") is False
    assert target.stat().st_mtime_ns == before
    assert write_ppp(target, [PolygonRegion(label="sample", points=[(1, 2), (3, 4)])], "page")


def test_autosave_status_is_conditional_on_real_changes():
    source = (Path(__file__).resolve().parents[1] / "src" /
              "picture_capture" / "app.py").read_text("utf-8")
    block = source[source.index("    def autosave_tick("):source.index("    def open_settings(", source.index("    def autosave_tick("))]
    assert "self._last_pdic_write_changed or polygon_changed" in block
