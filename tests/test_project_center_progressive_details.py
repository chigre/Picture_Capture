"""Project Center first paint must not wait for scanning project directories."""
from pathlib import Path

from picture_capture.recent_projects import recent_project_stub_details


def test_stub_details_are_registry_only(monkeypatch, tmp_path):
    def unexpected(self):
        raise AssertionError("first card queried filesystem")
    monkeypatch.setattr(Path, "is_dir", unexpected)
    monkeypatch.setattr(Path, "iterdir", unexpected)
    row = {
        "path": str(tmp_path / "nonexistent"), "name": "Fast card",
        "opened_at": "2026-10-10T10:10:00+00:00",
        "last_page": "page20.jpg", "last_page_index": 19,
    }
    stub = recent_project_stub_details(row)
    assert stub["full_name"] == "Fast card"
    assert stub["checking"] is True
    assert stub["last_page"] == "page20.jpg"
    assert stub["image_count"] == 0
    assert stub["exists"] is True


def test_first_paint_precedes_metadata_and_cover_workers():
    source = (Path(__file__).resolve().parents[1] / "src" /
              "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = source.index("    def open_recent_project(self)")
    block = source[start:source.index("\n    @staticmethod", start)]
    staged = block.index('state["details"] = [recent_project_stub_details(row) for row in rows]')
    first_paint = block.index("                rebuild()", staged)
    detail_worker = block.index('f"{key}-details",', first_paint)
    preview_worker = block.index('f"{key}-previews",')
    assert staged < first_paint < detail_worker
    assert 'def details_done(details)' in block
    assert preview_worker < first_paint  # declaration, invoked only after details callback


def test_project_detail_worker_still_reads_full_metadata():
    source = (Path(__file__).resolve().parents[1] / "src" /
              "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = source.index("    def open_recent_project(self)")
    block = source[start:source.index("\n    @staticmethod", start)]
    assert 'lambda: [recent_project_details(row) for row in rows]' in block
    assert 'state["details"] = details' in block
    assert "load_project_center_preview(root, Path(preview_text))" in block
