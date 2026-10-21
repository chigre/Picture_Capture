"""#562: proofreading companion state and PDIC text cleanup are physically packaged."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from picture_capture.proofreading import simplified_review
from picture_capture.proofreading.pdic_text_cleanup import clear_pdic_words

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_proofreading_sidecar_owners_are_physical_not_legacy_root_shims() -> None:
    for name in ("simplified_review", "pdic_text_cleanup"):
        assert not (PACKAGE_ROOT / (name + ".py")).exists()
        assert (PACKAGE_ROOT / "proofreading" / (name + ".py")).is_file()
        assert importlib.util.find_spec("picture_capture." + name) is None
        assert importlib.util.find_spec("picture_capture.proofreading." + name) is not None


def test_simplified_review_json_stable_xy_and_page_format(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    records = {
        "22,9": {"x": 22, "y": 9, "source_word": "甲", "text": "简体", "manual": True},
        "3,8": {"x": 3, "y": 8, "source_word": "乙", "text": "异体", "manual": False},
    }
    simplified_review.write_records(path, "page1", records)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format"] == "picture_capture_simplified_review"
    assert payload["format_version"] == 1
    assert payload["page"] == "page1"
    assert [(row["x"], row["y"]) for row in payload["entries"]] == [(3, 8), (22, 9)]
    assert simplified_review.read_records(path) == records


def test_pdic_clear_explicit_preserves_coordinates_and_nonword_bytes(tmp_path: Path) -> None:
    path = tmp_path / "page.PDIC"
    path.write_text("Old#8#18#5.0#20.0#page#@#next\n", encoding="utf-8")
    assert clear_pdic_words(path) == 1
    assert path.read_text(encoding="utf-8") == "#8#18#5.0#20.0#page#@#next\n"
