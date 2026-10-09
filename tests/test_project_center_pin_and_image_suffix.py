"""Project Center count is selected image format and pin order persists."""
import json
from pathlib import Path

from picture_capture.project_storage import settings_path
from picture_capture.recent_projects import (
    load_recent_projects, recent_project_details, set_recent_project_pinned,
)


def test_existing_project_card_counts_only_selected_image_suffix(tmp_path):
    root = tmp_path / "dictionary"
    root.mkdir()
    for name in ("1.png", "2.png", "3.jpg", "4.tif"):
        (root / name).touch()
    settings = settings_path(root)
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({
        "image_suffix": ".png", "dictionary_full_name": "Series volume",
    }), encoding="utf-8")
    detail = recent_project_details({
        "path": str(root), "last_page_index": 1,
    })
    assert detail["image_count"] == 2
    assert detail["position_text"] == "第 2 / 2 页"
    assert Path(detail["preview_path"]).name == "1.png"
    assert detail["full_name"] == "Series volume"


def test_pin_unpin_changes_recent_order_and_survives_reload(tmp_path):
    path = tmp_path / "recent_projects.json"
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    path.write_text(json.dumps([
        {"path": str(first), "name": "first"},
        {"path": str(second), "name": "second"},
    ]), encoding="utf-8")
    pinned = set_recent_project_pinned(second, True, path)
    assert [row["path"] for row in pinned] == [str(second), str(first)]
    assert load_recent_projects(path)[0]["pinned"] is True
    unpinned = set_recent_project_pinned(second, False, path)
    assert load_recent_projects(path)[0]["pinned"] is False
    assert unpinned[0]["path"] == str(second)


def test_project_center_ui_exposes_pin_context_action():
    src = (Path(__file__).resolve().parents[1]
           / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = src.index("    def open_recent_project(self)")
    end = src.index("\n    @staticmethod", start)
    part = src[start:end]
    assert 'label="取消置顶" if pinned else "置顶项目"' in part
    assert "set_recent_project_pinned(root, not pinned)" in part
    assert '("📌 " if row.get("pinned") else "")' in part
