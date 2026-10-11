"""Issue #428 auxiliary boundaries do not become PDIC words/crops."""
from pathlib import Path
from types import SimpleNamespace

from picture_capture.auxiliary_lines import (
    AuxiliaryLine, AuxiliaryLineEdits, auxiliary_line_path,
    read_auxiliary_lines, write_auxiliary_lines,
)
from picture_capture.auxiliary_crop_partition import partition_entry_pieces
from picture_capture.processing_core import EntryCropPiecePlan


class _Geometry:
    column_starts = [10]
    column_widths = [200]

    def source_to_canonical(self, x, y):
        return int(x), int(y)

    def canonical_to_source(self, u, v):
        return int(u), int(v)


class _Rotated(_Geometry):
    def source_to_canonical(self, x, y):
        return int(y), int(300 - x)

    def canonical_to_source(self, u, v):
        return int(300 - v), int(u)


def test_auxiliary_lines_atomic_independent_storage_and_page_switch(tmp_path):
    a = tmp_path / "001.png"
    b = tmp_path / "002.png"
    lines = [AuxiliaryLine(10, 120), AuxiliaryLine(12, 150)]
    assert read_auxiliary_lines(a) == []
    path = write_auxiliary_lines(a, lines)
    assert path == auxiliary_line_path(a)
    assert read_auxiliary_lines(a) == lines
    assert read_auxiliary_lines(b) == []
    assert not a.with_suffix(".pdic").exists()
    assert list(path.parent.glob("*.tmp")) == []


def test_auxiliary_edit_move_delete_and_undo():
    editor = AuxiliaryLineEdits([AuxiliaryLine(10, 30)])
    editor.add(AuxiliaryLine(10, 70))
    editor.move(1, AuxiliaryLine(10, 90))
    editor.delete(0)
    assert editor.lines == [AuxiliaryLine(10, 90)]
    assert editor.undo()
    assert editor.lines == [AuxiliaryLine(10, 30), AuxiliaryLine(10, 90)]
    assert editor.undo()
    assert editor.lines == [AuxiliaryLine(10, 30), AuxiliaryLine(10, 70)]
    assert editor.undo()
    assert editor.lines == [AuxiliaryLine(10, 30)]


def test_auxiliary_partitions_keep_original_entry_identity_and_number():
    pieces = [
        EntryCropPiecePlan(0, None, "_上页末词条_", (10, 10, 210, 40), "(0)"),
        EntryCropPiecePlan(0, 0, "alpha", (10, 40, 210, 180), "(1)"),
        EntryCropPiecePlan(1, 1, "beta", (10, 180, 210, 250), "(1)"),
    ]
    partitions = partition_entry_pieces(pieces, [AuxiliaryLine(10, 100)], _Geometry())
    # The region beneath the auxiliary boundary now belongs to beta (the
    # following headword) rather than becoming alpha's continuation slice.
    assert len(partitions) == 3
    assert partitions[0] is pieces[0]
    assert [p.box for p in partitions[1:]] == [
        (10, 40, 210, 100), (10, 100, 210, 250),
    ]
    assert [p.entry_ref_index for p in partitions] == [None, 0, 1]
    assert [p.word for p in partitions] == ["_上页末词条_", "alpha", "beta"]
    assert [p.output_index for p in partitions] == [0, 0, 1]
    assert [p.suffix for p in partitions[1:]] == ["(1)", "(1)"]


def test_auxiliary_partition_on_rotated_page_splits_x_axis():
    pieces = [EntryCropPiecePlan(3, 3, "rotated", (70, 10, 200, 210), "(1)")]
    partitions = partition_entry_pieces(pieces, [AuxiliaryLine(130, 10)], _Rotated())
    assert len(partitions) == 2
    assert sorted(p.box for p in partitions) == [
        (70, 10, 130, 210), (130, 10, 200, 210),
    ]
    assert all(p.output_index == 3 for p in partitions)


def test_no_auxiliary_only_export_when_no_real_entry():
    empty = [EntryCropPiecePlan(0, None, "_上页末词条_", (10, 20, 210, 250), "(0)")]
    assert partition_entry_pieces(empty, [AuxiliaryLine(10, 150)], _Geometry()) == empty


def test_preview_and_real_export_use_same_crop_planner():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    app = (root / "app.py").read_text(encoding="utf-8")
    core = (root / "processing_core.py").read_text(encoding="utf-8")
    assert "auxiliary_lines=list(self._auxiliary_edits.lines)" in app
    assert "pieces = partition_entry_pieces(pieces, auxiliary_lines, geometry)" in core
    assert core.count('read_auxiliary_lines(image_path)') >= 2
    assert '"auxiliary-overlay"' in (root / "auxiliary_line_controller.py").read_text(encoding="utf-8")


def test_actual_whole_entry_export_matches_same_preview_plan(tmp_path):
    from PIL import Image
    from picture_capture.models import AppSettings, Entry
    from picture_capture.processing import build_page_crop_plan, split_whole_entries

    page = tmp_path / "001.png"
    image = Image.new("RGB", (400, 600), "white")
    image.save(page)
    settings = AppSettings(
        columns=1, manual_x=20, column_width=300, gutter=20,
        start_y=20, bottom_y=580, follow_column_deformation=False,
    )
    entries = [Entry("first", 20, 100), Entry("second", 20, 350)]
    aux = [AuxiliaryLine(20, 220)]
    write_auxiliary_lines(page, aux)
    preview = build_page_crop_plan(
        image, entries, [], settings,
        top_y=20, bottom_y=580, auxiliary_lines=aux,
    )
    result = split_whole_entries(
        page, entries, settings, tmp_path / "whole",
        top_y=20, bottom_y=580,
    )
    assert len(result) == len(preview.entry_pieces)
    assert [r.box for r in result] == [p.box for p in preview.entry_pieces]
    assert all(r.index in (0, 1) for r in result)
    assert any(p.word == "first" and p.box[3] == 220 for p in preview.entry_pieces)


def test_managed_project_auxiliary_sidecar_uses_data_storage(tmp_path):
    import json
    from picture_capture.project_storage import (
        PROJECT_FORMAT, PROJECT_FORMAT_VERSION, manifest_path,
    )
    manifest = manifest_path(tmp_path)
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "format": PROJECT_FORMAT,
        "format_version": PROJECT_FORMAT_VERSION,
    }), encoding="utf-8")
    page = tmp_path / "001.png"
    expected = tmp_path / "_PictureCapture" / "data" / "AuxiliaryLines" / "001.json"
    assert auxiliary_line_path(page) == expected
    write_auxiliary_lines(page, [AuxiliaryLine(40, 80)])
    assert read_auxiliary_lines(page) == [AuxiliaryLine(40, 80)]


def test_shift_click_routing_and_direct_delete_chip_are_wired():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    source = (root / "app.py").read_text(encoding="utf-8")
    controller = (root / "auxiliary_line_controller.py").read_text(encoding="utf-8")
    assert 'self.canvas.bind("<Shift-Button-1>", self.canvas_left_click)' in source
    assert 'self._auxiliary_controller.delete_at_chip(x, y)' in source
    assert 'self._auxiliary_controller.add(x, y)' in source
    assert 'not self._section_editing and not self.polygon_draw_var.get()' in source
    assert 'text="[X]"' in controller
    assert 'app._auxiliary_delete_hitboxes.append((*box, i))' in controller


def test_auxiliary_line_add_delete_chip_does_not_create_pdic_entries(monkeypatch):
    from picture_capture.auxiliary_line_controller import AuxiliaryLineController
    from picture_capture import auxiliary_line_controller as mod

    class Canvas:
        def create_line(self, *_args, **_kw):
            return None
        def create_rectangle(self, *_args, **_kw):
            return None
        def create_text(self, *_args, **_kw):
            return None

    labels = []
    app = SimpleNamespace(
        image=SimpleNamespace(width=500, height=600),
        view_scale=1.0,
        _auxiliary_edits=AuxiliaryLineEdits(),
        _auxiliary_drag=None,
        page_sections=[],
        canvas=Canvas(),
        entries=[SimpleNamespace(word="词条", x=10, y=40)],
        auxiliary_mode_var=SimpleNamespace(get=lambda: False),
        status_var=SimpleNamespace(set=lambda value: labels.append(value)),
        _get_cached_display_geometry=lambda: _Geometry(),
        current_page=Path("page.png"),
        redraw=lambda: None,
    )
    saves = []
    monkeypatch.setattr(mod, "write_auxiliary_lines",
                        lambda _page, lines: saves.append(list(lines)))
    ctrl = AuxiliaryLineController(app)
    ctrl.add(15, 130)
    assert app._auxiliary_edits.lines == [AuxiliaryLine(10, 130)]
    ctrl.redraw()
    assert len(app._auxiliary_delete_hitboxes) == 1
    x0, y0, x1, y1, index = app._auxiliary_delete_hitboxes[0]
    assert index == 0
    assert ctrl.delete_at_chip((x0+x1)/2, (y0+y1)/2) is True
    assert app._auxiliary_edits.lines == []
    assert len(app.entries) == 1
    assert saves[-1] == []
    assert ctrl.delete_at_chip(400, 400) is False



def test_auxiliary_cut_between_real_headwords_reassigns_lower_interval():
    pieces = [
        EntryCropPiecePlan(0, 0, "upper", (10, 100, 210, 300), "(1)"),
        EntryCropPiecePlan(1, 1, "lower", (10, 296, 210, 460), "(1)"),
    ]
    output = partition_entry_pieces(pieces, [AuxiliaryLine(10, 200)], _Geometry())
    assert len(output) == 2
    assert [(p.word, p.box) for p in output] == [
        ("upper", (10, 100, 210, 200)),
        ("lower", (10, 200, 210, 460)),
    ]
    assert [p.entry_ref_index for p in output] == [0, 1]
    assert pieces[0].box == (10, 100, 210, 300)  # No in-place mutation.
    assert pieces[1].box == (10, 296, 210, 460)


def test_auxiliary_without_following_marker_still_only_splits_existing_entry():
    pieces = [
        EntryCropPiecePlan(0, 0, "last", (10, 100, 210, 400), "(1)"),
    ]
    output = partition_entry_pieces(pieces, [AuxiliaryLine(10, 200)], _Geometry())
    assert [(p.word, p.box) for p in output] == [
        ("last", (10, 100, 210, 200)),
        ("last", (10, 200, 210, 400)),
    ]
    assert all(p.entry_ref_index == 0 for p in output)


def test_auxiliary_in_other_column_does_not_shift_adjacent_entry_boundary():
    class TwoColumns(_Geometry):
        column_starts = [10, 300]
        column_widths = [200, 200]

    pieces = [
        EntryCropPiecePlan(0, 0, "left", (10, 100, 210, 300), "(1)"),
        EntryCropPiecePlan(1, 1, "right", (300, 290, 500, 460), "(1)"),
    ]
    result = partition_entry_pieces(
        pieces, [AuxiliaryLine(10, 200)], TwoColumns(),
    )
    assert len(result) == 3
    assert result[2].word == "right"
    assert result[2].box == (300, 290, 500, 460)


def test_shared_boundary_rotation_uses_canonical_reading_direction():
    pieces = [
        EntryCropPiecePlan(0, 0, "upper", (130, 10, 240, 210), "(1)"),
        EntryCropPiecePlan(1, 1, "lower", (30, 10, 134, 210), "(1)"),
    ]
    output = partition_entry_pieces(
        pieces, [AuxiliaryLine(180, 10)], _Rotated(),
    )
    assert len(output) == 2
    assert output[0].box == (180, 10, 240, 210)
    assert output[1].box == (30, 10, 180, 210)
