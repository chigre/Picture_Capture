"""Round 19: manual review selection priority and sidecar compatibility."""
from __future__ import annotations

import json

from picture_capture import paddle_headwords_core as core
from picture_capture.ocr import review_manual_selection


def test_variant_exclusivity_prefers_last_manual_then_refined():
    candidates = [
        {"candidate_id": "r", "position_group_id": "g", "selected": True, "position_variant": "refined"},
        {"candidate_id": "a", "position_group_id": "g", "selected": True, "position_variant": "original"},
        {"candidate_id": "orphan", "selected": True},
    ]
    assert core._enforce_position_variant_exclusivity(candidates) == 1
    assert candidates[0]["selected"] is True
    assert candidates[1]["selected"] is False
    assert candidates[2]["selected"] is True

    candidates[0]["selected"] = True
    candidates[1]["selected"] = True
    candidates[1]["manual_override"] = True
    assert core._enforce_position_variant_exclusivity(candidates) == 1
    assert not candidates[0]["selected"] and candidates[1]["selected"]
    assert core._enforce_position_variant_exclusivity.__module__ == "picture_capture.paddle_headwords_core"


def test_manual_sidecar_read_and_apply_preserves_original_format(tmp_path):
    cache = tmp_path / "page.json"
    manual = core._manual_selection_path(cache)
    manual.write_text(json.dumps({
        "overrides": {
            "p1": {"selected": False, "word": "修正", "engine": "lens"},
            "invalid": "ignored",
        },
    }), encoding="utf-8")
    overrides = core._load_manual_selection_overrides(cache)
    assert overrides == {"p1": {"selected": False, "word": "修正", "engine": "lens"}}
    rows = [{"candidate_id": "p1", "selected": True, "issue_types": ["old"]},
            {"candidate_id": "p2", "selected": True}]
    core._apply_manual_selection_overrides(rows, overrides)
    assert rows[0]["selected"] is False
    assert rows[0]["word"] == "修正"
    assert rows[0]["final_engine"] == "lens"
    assert rows[0]["decision_reason"] == "manual_override"
    assert rows[0]["issue_types"] == ["old", "MANUAL_OVERRIDE"]
    assert rows[1] == {"candidate_id": "p2", "selected": True}
    core._apply_manual_selection_overrides(rows, overrides)
    assert rows[0]["issue_types"] == ["old", "MANUAL_OVERRIDE"]
    assert core._load_manual_selection_overrides(None) == {}


def test_selection_core_hooks_are_live_and_invalid_json_is_soft(tmp_path, monkeypatch):
    cache = tmp_path / "page.json"
    manual = core._manual_selection_path(cache)
    manual.write_text("{broken", encoding="utf-8")
    assert core._load_manual_selection_overrides(cache) == {}
    manual.write_text('{"overrides":{"ok":{"selected":true}}}', encoding="utf-8")
    called = []
    old = core._manual_selection_path
    def path_spy(cache_path):
        called.append(cache_path)
        return old(cache_path)
    monkeypatch.setattr(core, "_manual_selection_path", path_spy)
    assert core._load_manual_selection_overrides(cache) == {"ok": {"selected": True}}
    assert called == [cache]
    assert core._apply_manual_selection_overrides.__module__ == "picture_capture.paddle_headwords_core"
    assert review_manual_selection.enforce_position_variant_exclusivity([]) == 0
