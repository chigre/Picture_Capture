"""Project-center performance and first-display behavior regressions."""
from pathlib import Path

from PIL import Image

from picture_capture import models
from picture_capture import recent_projects


def test_project_card_reuses_one_scan_directory_inventory(monkeypatch, tmp_path):
    root = tmp_path / "dictionary"
    root.mkdir()
    for index in range(140):
        (root / f"page{index}.jpg").touch()
    cover = root / "_cover.png"
    Image.new("RGB", (4, 4), "white").save(cover)
    originals = Path.iterdir
    calls = []

    def counted_iterdir(path):
        if path == root:
            calls.append(str(path))
        return originals(path)

    monkeypatch.setattr(Path, "iterdir", counted_iterdir)
    detail = recent_projects.recent_project_details({
        "path": str(root), "name": "Test dictionary", "last_page_index": 9,
    })
    assert detail["image_count"] == 140
    assert detail["cover_path"] == str(cover)
    assert detail["preview_path"] == str(cover)
    assert detail["position_text"] == "第 10 / 140 页"
    assert len(calls) == 1


def test_project_cover_inventory_preserves_case_insensitive_fallback(tmp_path):
    root = tmp_path / "dictionary"
    root.mkdir()
    first = root / "page2.jpg"
    first.touch()
    cover = root / "_PROJECT_COVER.PNG"
    cover.touch()
    inventory = tuple(root.iterdir())
    assert models.project_cover_path(root, candidates=inventory).samefile(cover)
    assert models.project_page_images(root, candidates=inventory) == [first]


def test_project_center_displays_cards_before_decoding_previews():
    source = (Path(__file__).resolve().parents[1] / "src" /
              "picture_capture" / "app.py").read_text(encoding="utf-8")
    entry = source.index("    def open_recent_project(self)")
    section = source[entry:source.index("\n    def ", entry + 10)]
    metadata_done = section.index('state["cover_images"] = {}')
    metadata_rebuild = section.index("                rebuild()", metadata_done)
    preview_dispatch = section.index('f"{key}-previews",', metadata_rebuild)
    assert metadata_done < metadata_rebuild < preview_dispatch
    worker = section[section.index("def previews_worker("):section.index("def alive()")]
    assert "load_project_center_preview(root, Path(preview_text))" in worker
