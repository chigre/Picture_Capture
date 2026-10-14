from __future__ import annotations

from picture_capture import draw_performance_profile as profile


def test_profile_is_opt_in_and_preserves_stage_values(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_directory", lambda: tmp_path)
    monkeypatch.delenv("PICTURE_CAPTURE_DRAW_PROFILE", raising=False)
    profile.record_page("one.png", 3, {"detect_entries": 0.5})
    assert profile.recent_profiles(0) == []
    monkeypatch.setenv("PICTURE_CAPTURE_DRAW_PROFILE", "1")
    profile.record_page("one.png", 3, {"detect_entries": 0.5, "pdic_write": 0.01})
    rows = profile.recent_profiles(0, pages={"one.png"})
    assert len(rows) == 1
    assert rows[0]["stages_ms"]["detect_entries"] == 500.0
    assert profile.summarize(rows) == {
        "detect_entries": 500.0, "pdic_write": 10.0,
    }
    assert profile.recent_profiles(0, pages={"other.png"}) == []


def test_profile_malformed_line_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_directory", lambda: tmp_path)
    (tmp_path / "bad.jsonl").write_text("invalid json\n", encoding="utf-8")
    assert profile.recent_profiles(0) == []
