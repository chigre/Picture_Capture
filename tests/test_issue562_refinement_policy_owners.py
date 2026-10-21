"""Issue #562: strict physical owners for layout reuse and inference policy."""
from pathlib import Path
from importlib import import_module

ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_canonical_policy_and_layout_reuse_leaves():
    for old, new, attr in (
        ("marker_refinement_layoutrows.py", "refinement/layoutrows.py", "requested_refinement_fields"),
        ("inference_performance.py", "quality/inference_performance.py", "resolve_inference_policy"),
    ):
        assert not (ROOT / old).exists()
        assert (ROOT / new).is_file()
        assert callable(getattr(import_module("picture_capture." + new[:-3].replace("/", ".")), attr))
