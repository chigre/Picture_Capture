"""Canonical proofreading physical ownership regression for Issue #562."""

from importlib import import_module
from pathlib import Path


def test_proofreading_owner_modules_are_physically_moved():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture"
    owners = {
        "proofreading_candidate_history": ("candidate_history", "CandidateReviewHistory"),
        "proofreading_identity": ("identity", "owned_entries_at_snapshot"),
        "proofreading_section": ("section", "section_fields_for_event"),
    }
    for retired, (owner, exported) in owners.items():
        assert not (root / (retired + ".py")).exists()
        assert (root / "proofreading" / (owner + ".py")).is_file()
        module = import_module(f"picture_capture.proofreading.{owner}")
        assert hasattr(module, exported)
