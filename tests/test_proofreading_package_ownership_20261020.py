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

    added_owners = {
            "proofreading_candidate_delete": "candidate_delete",
            "proofreading_capture": "capture",
            "proofreading_deferred_save": "deferred_save",
            "proofreading_events": "events",
            "proofreading_evidence": "evidence",
            "proofreading_quality_export": "quality_export",
            "proofreading_review_bundle": "review_bundle",
            "proofreading_save_safety": "save_safety",
            "proofreading_transactions": "transactions",
            "proofreading_verification": "verification",
            "proofreading_verify_ui": "verify_ui",
            "review_crop_extension": "crop_extension",
            "review_entry_classification_ui": "entry_classification_ui",
            "review_main_editor_sync": "main_editor_sync",
            "review_text_helpers": "text_helpers"
    }
    for retired, owner in added_owners.items():
        assert not (root / (retired + '.py')).exists(), retired
        canonical = root / 'proofreading' / (owner + '.py')
        assert canonical.is_file(), canonical
        module = import_module(f'picture_capture.proofreading.{owner}')
        assert Path(module.__file__).resolve() == canonical.resolve()

