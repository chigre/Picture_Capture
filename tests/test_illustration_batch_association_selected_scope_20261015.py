"""Batch association reads only existing PPP, uses per-page layout, atomically saves labels."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from picture_capture.formats import read_pdic, read_ppp, write_pdic, write_ppp
from picture_capture.models import AppSettings, Entry, PolygonRegion
from picture_capture.processing_core import Geometry
from picture_capture.project_storage import ppp_read_path_for_image, ppp_write_path_for_image
from picture_capture.illustration_batch_association import (
    associate_existing_ppp_page, associate_existing_ppp_job,
)
from picture_capture.ui.controllers import illustration as ui
import picture_capture.illustration_batch_association as service


def geometry():
    return Geometry(
        column_starts=[0, 110], column_widths=[100, 100],
        top=0, bottom=500, column_paths=[],
    )


def setup_page(root: Path, stem: str, *, ppp: bool = True, pdic: bool = True):
    page = root / f"{stem}.png"
    Image.new("RGB", (250, 500), "white").save(page)
    if pdic:
        # Logical order is [early, middle, late], NOT file insertion order.
        words = [Entry("late", 15, 190), Entry("early", 15, 40), Entry("middle", 15, 90)]
        write_pdic(page.with_suffix(".pdic"), words, 250, (stem, "@", "@"))
    if ppp:
        shape = PolygonRegion("P_99|stale|999", [
            (15, 120), (95, 120), (95, 260), (15, 260),
        ])
        write_ppp(ppp_write_path_for_image(page), [shape], stem)
    return page


@pytest.fixture(autouse=True)
def fixed_geometry(monkeypatch):
    # Eliminate image-based column-track estimation from source-I/O tests.
    monkeypatch.setattr(service, "derive_geometry", lambda *_a: geometry())


def test_job_updates_each_ppp_using_zero_based_current_page_logical_id(tmp_path):
    pages = [
        setup_page(tmp_path, "080005"),
        setup_page(tmp_path, "080035"),
    ]
    results = [
        associate_existing_ppp_page(pages[index], AppSettings(), index)
        for index in range(2)
    ]
    assert [r["status"] for r in results] == ["changed", "changed"]
    for page in pages:
        saved = read_ppp(ppp_read_path_for_image(page))
        assert saved[0].label == f"P_01|{page.stem}|001"
        assert saved[0].points == [(15, 120), (95, 120), (95, 260), (15, 260)]
        assert len(read_pdic(page.with_suffix(".pdic"))) == 3
    assert [r["linked"] for r in results] == [1, 1]
    # No accidental rewrite when running the action a second time.
    assert associate_existing_ppp_page(pages[0], AppSettings(), 0)["status"] == "unchanged"


def test_missing_ppp_is_skipped_and_never_created(tmp_path):
    page = setup_page(tmp_path, "080011", ppp=False)
    before = page.with_suffix(".pdic").read_bytes()
    result = associate_existing_ppp_page(page, AppSettings(), 0)
    assert result["status"] == "skipped_no_ppp"
    assert not ppp_read_path_for_image(page).exists()
    assert not ppp_write_path_for_image(page).exists()
    assert page.with_suffix(".pdic").read_bytes() == before


def test_ppp_without_pdic_is_skipped_not_unlinked_destructively(tmp_path):
    page = setup_page(tmp_path, "080012", pdic=False)
    output = ppp_write_path_for_image(page)
    before = output.read_bytes()
    result = associate_existing_ppp_page(page, AppSettings(), 0)
    assert result["status"] == "skipped_no_pdic"
    assert output.read_bytes() == before


def test_write_failure_preserves_source_and_worker_continues(tmp_path, monkeypatch):
    page = setup_page(tmp_path, "080013")
    original = ppp_write_path_for_image(page).read_bytes()

    def fail(*_args, **_kwargs):
        raise PermissionError("simulated read-only PPP")

    monkeypatch.setattr(service, "write_ppp", fail)
    failed = associate_existing_ppp_job(str(page), AppSettings(), 0)
    assert failed["status"] == "failed"
    assert "read-only PPP" in failed["error"]
    assert ppp_write_path_for_image(page).read_bytes() == original
    other = setup_page(tmp_path, "no_ppp", ppp=False)
    assert associate_existing_ppp_job(str(other), AppSettings(), 1)["status"] == "skipped_no_ppp"


def test_concurrent_ppp_edit_is_detected_before_commit(tmp_path, monkeypatch):
    page = setup_page(tmp_path, "080014")
    initial = read_ppp(ppp_read_path_for_image(page))
    source = ppp_read_path_for_image(page)
    real_illustration_labels = service.illustration_labels

    def race(*args, **kwargs):
        source.write_text("external-change\n", encoding="utf-8")
        return real_illustration_labels(*args, **kwargs)

    monkeypatch.setattr(service, "illustration_labels", race)
    result = associate_existing_ppp_job(str(page), AppSettings(), 0)
    assert result["status"] == "failed"
    assert "changed concurrently" in result["error"]
    assert source.read_text(encoding="utf-8") == "external-change\n"
    assert initial[0].label == "P_99|stale|999"


class MockApp:
    def __init__(self, pages):
        self.project = SimpleNamespace(images=pages)
        self.current_page = pages[0]
        self.current_index = 0
        self.polygons = []
        self.page_sections = []
        self.settings = AppSettings()
        self._batch_active = False
        self.polygon_draw_var = SimpleNamespace(get=lambda: False)
        self.statuses = []
        self.status_var = SimpleNamespace(set=self.statuses.append)
        self.errors = []
        self.jobs = []
        self.redraws = 0
        self.saved = 0
        self.updated_rows = []
        self.guard = lambda: True

    def selected_page_indices(self):
        return list(range(len(self.project.images)))

    def _ppp_read_path(self, page):
        return ppp_read_path_for_image(page)

    def _ppp_write_path(self, page):
        return ppp_write_path_for_image(page)

    def _flush_deferred_page_save(self):
        self.saved += 1

    def save_pdic(self, silent=True):
        self.saved += 1

    def _sync_polygon_label_texts(self):
        pass

    def _update_page_row(self, index):
        self.updated_rows.append(index)

    def redraw(self):
        assert self.__dict__.get("_suppress_polygon_label_sync", False)
        self.redraws += 1

    def show_error(self, title, exc):
        self.errors.append((title, str(exc)))

    def _start_batch_task(self, title, pages, worker, on_done=None, **kwargs):
        self.jobs.append((title, list(pages), kwargs))
        results = [worker(index, position + 1, len(pages)) for position, index in enumerate(pages)]
        on_done(len(pages), len(pages), False, results, None)
        return True


def test_range_batch_skips_unannotated_page_without_creating_ppp(tmp_path, monkeypatch):
    pages = [
        setup_page(tmp_path, "080020", ppp=False),
        setup_page(tmp_path, "080021"),
        setup_page(tmp_path, "080022"),
    ]
    app = MockApp(pages)
    monkeypatch.setattr(ui, "confirm_illustration_association", lambda _app: True)
    ui.IllustrationController(app).associate_selected_scope()
    assert app.jobs[0][1] == [1, 2]
    assert app.saved == 0  # Current page has no PPP; do not save it.
    assert not ppp_read_path_for_image(pages[0]).exists()
    assert [read_ppp(ppp_read_path_for_image(p))[0].label for p in pages[1:]] == [
        "P_01|080021|001", "P_01|080022|001",
    ]
    assert app.updated_rows == [1, 2]
    assert "跳过 1 页" in app.statuses[-1]
    assert app.redraws == 0
    assert not app.errors


def test_batch_scope_cancel_does_not_write_any_file(tmp_path, monkeypatch):
    pages = [setup_page(tmp_path, "080030"), setup_page(tmp_path, "080031")]
    app = MockApp(pages)
    app.polygons = read_ppp(ppp_read_path_for_image(pages[0]))
    originals = [ppp_read_path_for_image(page).read_bytes() for page in pages]
    monkeypatch.setattr(ui, "confirm_illustration_association", lambda _app: False)
    ui.IllustrationController(app).associate_selected_scope()
    assert app.jobs == []
    assert app.saved == 0
    assert originals == [ppp_read_path_for_image(page).read_bytes() for page in pages]


def test_batch_scope_error_summary_survives_one_page_failure(tmp_path, monkeypatch):
    pages = [setup_page(tmp_path, "080040", ppp=False), setup_page(tmp_path, "080041")]
    app = MockApp(pages)
    monkeypatch.setattr(ui, "confirm_illustration_association", lambda _app: True)
    monkeypatch.setattr(
        ui, "associate_existing_ppp_job",
        lambda path, _settings, index: {
            "page_index": index, "page": Path(path).name,
            "status": "failed", "error": "PermissionError: read-only",
        },
    )
    ui.IllustrationController(app).associate_selected_scope()
    assert "错误 1 页" in app.statuses[-1]
    assert "跳过 1 页" in app.statuses[-1]
    assert "080041.png" in app.statuses[-1]
