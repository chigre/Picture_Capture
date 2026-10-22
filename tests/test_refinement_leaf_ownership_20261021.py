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


def test_spawn_and_parent_commit_boundaries_have_real_refinement_owners() -> None:
    import importlib.util
    import pickle
    from picture_capture.refinement import parallel, separator_y

    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    assert not (root / "marker_refinement_parallel.py").exists()
    assert not (root / "separator_y_refinement.py").exists()
    assert (root / "refinement/layoutrows.py").is_file()
    assert (root / "refinement/parallel.py").is_file()
    assert (root / "refinement/separator_y.py").is_file()
    assert importlib.util.find_spec("picture_capture.marker_refinement_parallel") is None
    assert importlib.util.find_spec("picture_capture.separator_y_refinement") is None
    assert parallel.refine_page_job.__module__ == "picture_capture.refinement.parallel"
    assert pickle.loads(pickle.dumps(parallel.refine_page_job)) is parallel.refine_page_job
    assert callable(parallel.commit_refined_page_result)
    assert callable(separator_y.refine_separator_y)
    assert callable(separator_y.refined_layout_entry_y_by_line)
