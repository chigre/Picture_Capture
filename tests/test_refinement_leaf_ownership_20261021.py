"""Physical ownership regression for bounded explicit-Y refinement leaves."""
from importlib import import_module
from pathlib import Path


def test_refinement_leaves_have_canonical_owners_without_root_shims() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    owners = {
        "marker_refinement_analysis": "analysis",
        "marker_refinement_fixed_band": "fixed_band",
        "marker_refinement_guard": "guard",
        "marker_refinement_progress": "progress",
        "marker_refinement_top_edge": "top_edge",
    }
    for former, owner in owners.items():
        assert not (root / f"{former}.py").exists()
        assert (root / "refinement" / f"{owner}.py").is_file()
        module = import_module(f"picture_capture.refinement.{owner}")
        assert module.__name__ == f"picture_capture.refinement.{owner}"


def test_spawn_and_parent_commit_boundaries_remain_root_owned() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert (root / "marker_refinement_parallel.py").is_file()
    assert (root / "refinement/layoutrows.py").is_file()
    assert (root / "separator_y_refinement.py").is_file()
