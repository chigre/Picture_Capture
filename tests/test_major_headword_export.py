"""Issue #428: major-headword strips use durable classification, not OCR text."""
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from picture_capture.entry_classification import (
    register_entry_classification, write_classification_sidecar,
)
from picture_capture.formats import write_pdic
from picture_capture.major_headword_export import (
    export_major_headword_page_job, selected_major_row_boxes,
)
from picture_capture.models import AppSettings, Entry


class _Identity:
    def source_to_canonical_point(self, x, y, _size):
        return x, y

    def canonical_to_source_point(self, x, y, _size):
        return x, y


class _Rotated:
    def source_to_canonical_point(self, x, y, _size):
        return y, 300 - x

    def canonical_to_source_point(self, x, y, _size):
        return 300 - y, x


def _layout(transform=None):
    return SimpleNamespace(
        columns=[SimpleNamespace(
            left=10, right=210, lines=[
                SimpleNamespace(y0=20, y1=40),
                SimpleNamespace(y0=70, y1=90),
            ],
        )],
        body_top=0, body_bottom=200, ordinary_line_height=20,
        transform=transform or _Identity(), source_size=(300, 300),
    )


def test_only_marked_oversized_rows_and_right_prefix_are_selected():
    a, b = Entry("major", 10, 15), Entry("regular", 10, 65)
    register_entry_classification(a, entry_scale="oversized", manual_override=True)
    assert selected_major_row_boxes(_layout(), [a, b], 25) == [(10, 19, 60, 41)]


def test_rotated_page_prefix_uses_corner_coordinate_conversion():
    major = Entry("major", 285, 10)
    register_entry_classification(major, entry_scale="oversized", manual_override=True)
    assert selected_major_row_boxes(_layout(_Rotated()), [major], 25) == [
        (259, 10, 281, 60),
    ]


def test_zero_markers_skips_layout_and_writes_nothing(tmp_path, monkeypatch):
    import picture_capture.major_headword_export as module
    page = tmp_path / "a.png"
    Image.new("RGB", (300, 300), "white").save(page)
    monkeypatch.setattr(module, "resolve_unlined_physical_rows", lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("no layout expected")))
    result = export_major_headword_page_job(tmp_path, page, 0, AppSettings(), False)
    assert result.marked == 0 and result.exported == 0


def test_sidecar_recovers_marker_and_page_merge(tmp_path, monkeypatch):
    import picture_capture.major_headword_export as module
    page = tmp_path / "a.png"
    image = Image.new("RGB", (300, 300), "white")
    ImageDraw.Draw(image).rectangle((12, 21, 55, 36), fill="black")
    image.save(page)
    marker = Entry("major", 10, 15)
    write_pdic(page.with_suffix(".pdic"), [marker], 300, ("", "", ""))
    register_entry_classification(marker, entry_scale="oversized", manual_override=True)
    write_classification_sidecar([marker], page.with_suffix(".pdic"))
    monkeypatch.setattr(module, "resolve_unlined_physical_rows", lambda *_args, **_kw: (_layout(), None))
    result = export_major_headword_page_job(tmp_path, page, 0, AppSettings(right_ratio=25), True)
    assert result.marked == 1
    assert result.exported == 1 and result.merged
    out = tmp_path / "QT" / module.OUTPUT_DIRNAME / "a_MH_PAGE.png"
    assert out.is_file()
