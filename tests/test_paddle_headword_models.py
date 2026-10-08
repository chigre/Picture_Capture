from __future__ import annotations

import pickle

import picture_capture.evidence_fusion as evidence_fusion
import picture_capture.paddle_headwords as public_headwords
import picture_capture.paddle_headwords_core as core
from picture_capture import paddle_headword_models as models


MODEL_NAMES = (
    "OCRRecord",
    "OCRLine",
    "GrammarTailParse",
    "HeadwordParse",
    "HeadwordFilterRule",
)


def test_phase7n_core_and_public_facade_reexport_model_objects() -> None:
    for name in MODEL_NAMES:
        model = getattr(models, name)
        assert getattr(core, name) is model
        assert getattr(public_headwords, name) is model


def test_phase7n_headword_models_keep_historical_core_module_path() -> None:
    for name in MODEL_NAMES:
        model = getattr(models, name)
        assert model.__module__ == "picture_capture.paddle_headwords_core"
        assert pickle.loads(pickle.dumps(model)) is model


def test_phase7n_evidence_fusion_keeps_direct_model_identity() -> None:
    assert evidence_fusion.OCRRecord is models.OCRRecord
    assert evidence_fusion.HeadwordFilterRule is models.HeadwordFilterRule


def test_phase7n_public_model_assignment_still_mirrors_into_core(monkeypatch) -> None:
    replacement = object()

    monkeypatch.setattr(public_headwords, "OCRRecord", replacement)

    assert core.OCRRecord is replacement
