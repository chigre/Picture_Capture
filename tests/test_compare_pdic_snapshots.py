"""Regression contracts: full PDIC payload, not just per-page entry counts."""
from __future__ import annotations

from pathlib import Path
from scripts.compare_pdic_snapshots import compare_trees, main


def _pdic(root: Path, name: str, rows: list[str]) -> None:
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_full_record_equivalence(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    row = "word#100#200#10#20#page001#@#page002"
    _pdic(old, "page001.pdic", [row])
    _pdic(new, "page001.pdic", [row])
    assert compare_trees(old, new)["equal"]


def test_same_count_moved_marker_fails(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    _pdic(old, "page001.pdic", ["abc#100#200#10#20#p#@#@"])
    _pdic(new, "page001.pdic", ["abc#100#201#10#20.1#p#@#@"])
    result = compare_trees(old, new)
    assert not result["equal"]
    assert result["changed_files"] == 1
    assert result["examples"][0]["first_differences"][0]["row"] == 1


def test_reorder_and_text_changes_are_detected(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    first = "a#100#200#10#20#p#@#@"
    second = "b#100#300#10#30#p#@#@"
    _pdic(old, "p.pdic", [first, second])
    _pdic(new, "p.pdic", [second, first])
    assert not compare_trees(old, new)["equal"]
    _pdic(new, "p.pdic", [first.replace("a#", "changed#"), second])
    assert not compare_trees(old, new)["equal"]


def test_missing_page_or_unequal_extra_record(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    _pdic(old, "nested/page.pdic", ["abc#1#2#1#2#p#@#@"])
    new.mkdir()
    assert compare_trees(old, new)["examples"][0]["issue"] == "missing_candidate"
    assert main([str(old), str(new)]) == 1


def test_corrupt_coordinates_raise(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    _pdic(old, "x.pdic", ["x#bad#1#1#1#p#@#@"])
    _pdic(new, "x.pdic", ["x#bad#1#1#1#p#@#@"])
    assert main([str(old), str(new)]) == 2
