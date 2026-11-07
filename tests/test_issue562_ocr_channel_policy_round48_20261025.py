"""Round 48: OCR public model identity and policy/result physical ownership."""
from __future__ import annotations

import inspect
import pickle
from dataclasses import fields

from picture_capture import ocr_channel
from picture_capture.ocr import channel_policy, channel_results


def _candidate(engine: str, text: str, error: str = ""):
    return ocr_channel.OcrChannelCandidate(engine=engine, text=text, error=error)


def test_public_session_and_models_keep_original_pickle_module_and_signatures():
    for cls in (
        ocr_channel.OcrChannelPlan,
        ocr_channel.OcrChannelRecord,
        ocr_channel.OcrChannelCandidate,
        ocr_channel.OcrChannelResult,
        ocr_channel.OcrTextChoice,
    ):
        assert cls.__module__ == "picture_capture.ocr_channel"
        assert pickle.loads(pickle.dumps(cls)) is cls
    plan = ocr_channel.OcrChannelPlan(("paddle", "lens"), ("paddle",), "diagnostic")
    result = ocr_channel.OcrChannelResult(plan, (_candidate("paddle", "a"),))
    assert pickle.loads(pickle.dumps(result)) == result
    assert [field.name for field in fields(ocr_channel.OcrChannelCandidate)] == [
        "engine", "text", "confidence", "records", "error",
        "participates_in_fusion", "metadata",
    ]
    assert isinstance(
        inspect.getattr_static(ocr_channel.OcrChannelSession, "_needs_conflict_lens"),
        staticmethod,
    )
    assert list(inspect.signature(
        ocr_channel.OcrChannelSession._needs_conflict_lens
    ).parameters) == ["candidates"]


def test_actual_policy_and_result_owners_with_thin_historical_facade():
    channel = inspect.getsource(ocr_channel.OcrChannelSession._needs_conflict_lens)
    assert "_channel_policy.needs_conflict_lens" in channel
    assert "successful = [" in inspect.getsource(channel_policy.needs_conflict_lens)
    assert "_channel_results.find_channel_candidate" in inspect.getsource(
        ocr_channel.OcrChannelResult.candidate
    )
    assert "next(" in inspect.getsource(channel_results.find_channel_candidate)
    assert "_channel_results.candidate_is_ok" in inspect.getsource(
        ocr_channel.OcrChannelCandidate.ok.fget
    )
    assert "_channel_policy.plan_enabled" in inspect.getsource(
        ocr_channel.OcrChannelPlan.enabled
    )


def test_engine_plan_name_and_candidate_access_behave_identically(monkeypatch):
    plan = ocr_channel.OcrChannelPlan(("paddle", "lens"), ("paddle",), "diagnostic")
    assert plan.enabled(" PADDLE ") and plan.enabled("lens")
    assert not plan.enabled("tesseract")
    assert plan.votes("PADDLE") and not plan.votes("lens")
    assert ocr_channel._normalized_engine_name(" PaddleOCR ") == "paddle"
    monkeypatch.setitem(ocr_channel._ENGINE_ALIASES, "my_ocr", "tesseract")
    assert ocr_channel._normalized_engine_name("MY_OCR") == "tesseract"
    candidates = (
        _candidate("paddle", " Apple "),
        _candidate("tesseract", " ", "failed"),
        _candidate("paddle", "backup"),
        _candidate("lens", "pear", "network failed"),
    )
    result = ocr_channel.OcrChannelResult(plan, candidates)
    assert result.candidate(" PADDLE ") is candidates[0]
    assert result.candidate("TESSERACT") is candidates[1]
    assert result.candidate("missing") is None
    assert result.successful == (candidates[0], candidates[2])
    assert isinstance(result.successful, tuple)
    assert candidates[0].ok and candidates[2].ok
    assert not candidates[1].ok and not candidates[3].ok


def test_conflict_lens_keeps_live_public_text_key_and_one_vote_edge_cases(monkeypatch):
    session = ocr_channel.OcrChannelSession
    assert session._needs_conflict_lens(iter(())) is True
    assert session._needs_conflict_lens(iter((_candidate("paddle", "X"),))) is True
    matched = (_candidate("paddle", " ABC "), _candidate("tesseract", "abc"))
    seen = []
    def live_key(text):
        seen.append(text)
        return text.strip().lower()
    monkeypatch.setattr(ocr_channel, "channel_text_key", live_key)
    assert session._needs_conflict_lens(iter(matched)) is False
    assert seen == [" ABC ", " ABC ", "abc", "abc"]
    monkeypatch.setattr(ocr_channel, "channel_text_key", lambda _: "one")
    assert session._needs_conflict_lens(matched) is False
    monkeypatch.setattr(ocr_channel, "channel_text_key", lambda s: s)
    assert session._needs_conflict_lens(matched) is True
    blank = (_candidate("paddle", "a"), _candidate("tesseract", "b"))
    monkeypatch.setattr(ocr_channel, "channel_text_key", lambda _: "")
    assert session._needs_conflict_lens(blank) is False
