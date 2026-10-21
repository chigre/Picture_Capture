"""Issue #562: Entry descriptor helpers have one physical owner."""
from __future__ import annotations

import importlib
from pathlib import Path

from picture_capture.models import Entry


ROOT = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_entry_descriptor_owner_is_physical_and_import_light():
    assert not (ROOT / "entry_classification_fields.py").exists()
    expected = ROOT / "proofreading" / "entry_classification_fields.py"
    assert expected.is_file()
    module = importlib.import_module("picture_capture.proofreading.entry_classification_fields")
    assert Path(module.__file__).resolve() == expected.resolve()
    assert module.install_entry_classification_fields() is None
    assert Entry.__module__ == "picture_capture.models"


def test_model_descriptor_delegation_uses_canonical_owner():
    model_source = (ROOT / "models.py").read_text(encoding="utf-8")
    assert model_source.count("from .proofreading.entry_classification_fields import") == 8
    assert "from .entry_classification_fields import" not in model_source
