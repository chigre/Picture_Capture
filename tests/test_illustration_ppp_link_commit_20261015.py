"""PPP linkage action commits disk before changing any live region objects."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from picture_capture.formats import read_ppp, write_ppp
from picture_capture.models import Entry, PolygonRegion
from picture_capture.processing_core import Geometry
from picture_capture.ui.controllers import illustration as ui


def fig(x0, y0, x1, y1, label=""):
    return PolygonRegion(label, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


class Bool:
    def __init__(self, value=False):
        self.value = value

    def get(self):
        return self.value


class FakeApp:
    def __init__(self, root):
        self.current_page = root / "080123.png"
        self.current_index = 0
        self.polygons = [
            fig(120, 140, 190, 210, "080123|AUTO_01|1|080123|"),
            fig(10, 240, 90, 290, ""),
        ]
        self.entries = [Entry("left", 12, 160), Entry("right", 125, 80)]
        self.page_sections = []
        self.polygon_draw_var = Bool()
        self._batch_active = False
        self._batch_allow_pdic_edits = False
        self._suppress_polygon_label_sync = False
        self.statuses = []
        self.status_var = SimpleNamespace(set=self.statuses.append)
        self.errors = []
        self.rendered = []
        self.guard = lambda: True
        self._sync_entry_editor_texts = lambda: None
        self._sync_polygon_label_texts = lambda: None

    def _get_cached_display_geometry(self):
        return Geometry(
            column_starts=[0, 110], column_widths=[100, 100],
            top=0, bottom=400, column_paths=[],
        )

    def _ordered_entries_reading_order(self):
        return list(self.entries)

    def _ppp_write_path(self, page):
        return page.with_suffix(".ppp")

    def _ppp_read_path(self, page):
        return page.with_suffix(".ppp")

    def _update_page_row(self, index):
        assert index == 0

    def redraw(self):
        self.rendered.append([p.label for p in self.polygons])
        assert self.__dict__.get("_suppress_polygon_label_sync") is True

    def show_error(self, title, exc):
        self.errors.append((title, str(exc)))


def test_association_cancellation_never_changes_ppp_or_live_state(tmp_path, monkeypatch):
    app = FakeApp(tmp_path)
    original = [p.label for p in app.polygons]
    monkeypatch.setattr(ui, "confirm_illustration_association", lambda _app: False)
    ui.IllustrationController(app).associate_current_page()
    assert [p.label for p in app.polygons] == original
    assert not app.current_page.with_suffix(".ppp").exists()


def test_link_writes_complete_ppp_before_ui_change(tmp_path, monkeypatch):
    app = FakeApp(tmp_path)
    ui.IllustrationController(app).persist_current()
    original_objects = list(app.polygons)
    monkeypatch.setattr(ui, "confirm_illustration_association", lambda _app: True)
    ui.IllustrationController(app).associate_current_page()
    assert [p.label for p in app.polygons] == [
        "P_02|080123|001|AUTO_01", "P_01|080123|000",
    ]
    assert all(a is b for a, b in zip(app.polygons, original_objects))
    saved = read_ppp(app.current_page.with_suffix(".ppp"))
    assert [p.label for p in saved] == [p.label for p in app.polygons]
    assert [p.points for p in saved] == [p.points for p in app.polygons]
    assert not app.errors
    assert app.__dict__.get("_suppress_polygon_label_sync") is False


def test_injected_ppp_write_failure_leaves_old_ui_and_disk_unchanged(tmp_path, monkeypatch):
    app = FakeApp(tmp_path)
    ui.IllustrationController(app).persist_current()
    before = [p.label for p in app.polygons]
    content = app.current_page.with_suffix(".ppp").read_bytes()

    def failed(_path, _regions, _stem):
        raise PermissionError("read-only PPP")

    monkeypatch.setattr(ui, "write_ppp", failed)
    monkeypatch.setattr(ui, "confirm_illustration_association", lambda _app: True)
    ui.IllustrationController(app).associate_current_page()
    assert [p.label for p in app.polygons] == before
    assert app.current_page.with_suffix(".ppp").read_bytes() == content
    assert app.errors and "read-only PPP" in app.errors[-1][1]


def test_deletion_renumbers_same_page_and_preserves_auto_marker(tmp_path):
    app = FakeApp(tmp_path)
    ctl = ui.IllustrationController(app)
    ctl.persist_current()
    removed = app.polygons[1]
    assert ctl.delete_polygon(removed)
    assert len(app.polygons) == 1
    assert app.polygons[0].label == "P_01|080123|xxx|AUTO_01"
    assert [p.label for p in read_ppp(app.current_page.with_suffix(".ppp"))] == [
        app.polygons[0].label,
    ]


def test_manually_added_polygon_fills_reading_order_and_saves(tmp_path):
    app = FakeApp(tmp_path)
    ctl = ui.IllustrationController(app)
    ctl.persist_current()
    assert ctl.add_manual_polygon([(5, 100), (85, 100), (85, 120), (5, 120)])
    assert len(app.polygons) == 3
    assert app.polygons[2].label == "P_01|080123|xxx"
    assert app.polygons[1].label == "P_02|080123|xxx"
    assert app.polygons[0].label == "P_03|080123|xxx|AUTO_01"


def test_editing_association_suffix_reuses_original_region_identity(tmp_path):
    app = FakeApp(tmp_path)
    ctl = ui.IllustrationController(app)
    ctl.persist_current()
    original_region = app.polygons[0]
    assert ctl.update_label(original_region, "P_99|forged|007")
    assert app.polygons[0] is original_region
    assert app.polygons[0].label == "P_02|080123|007|AUTO_01"
    assert read_ppp(app.current_page.with_suffix(".ppp"))[0].label == app.polygons[0].label
