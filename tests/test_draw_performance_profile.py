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


def test_export_report_has_machine_readable_csv_and_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_directory", lambda: tmp_path)
    rows = [{
        "time": 1.0, "page": "page.png", "page_index": 0,
        "pid": 100, "stage_group": "detect_entries_inner",
        "stages_ms": {"inner_page_understanding": 1500.0},
    }]
    path = profile.export_batch_report(
        rows, label="普通画线", elapsed_seconds=2.0, completed=1,
    )
    assert path is not None and path.exists()
    assert "1.500" in path.read_text(encoding="utf-8")
    csv_path = path.with_suffix(".csv")
    assert csv_path.exists()
    assert "inner_page_understanding" in csv_path.read_text(encoding="utf-8-sig")


def test_empty_batch_still_produces_report(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_directory", lambda: tmp_path)
    path = profile.export_batch_report([], label="普通画线", elapsed_seconds=12, completed=3)
    assert path is not None
    assert path.exists()
    assert path.with_suffix(".csv").exists()
    assert "计时事件数：0" in path.read_text(encoding="utf-8")


def test_prepared_analysis_reuse_is_opt_in_and_pixel_identical(monkeypatch):
    import numpy as np
    from PIL import Image
    from types import SimpleNamespace
    from picture_capture.image_utils import build_analysis_image

    arr = np.full((45, 37, 3), 255, dtype=np.uint8)
    arr[10:30, 12:15] = 0
    settings = SimpleNamespace(analysis_denoise_strength="auto")
    monkeypatch.delenv("PICTURE_CAPTURE_REUSE_PREPARED_ANALYSIS", raising=False)
    original = Image.fromarray(arr, "RGB")
    prepared = build_analysis_image(original, settings)
    assert prepared.info["_picture_capture_analysis_strength"] == "auto"
    monkeypatch.setenv("PICTURE_CAPTURE_REUSE_PREPARED_ANALYSIS", "1")
    reused = build_analysis_image(prepared, settings)
    assert reused is not prepared
    np.testing.assert_array_equal(np.asarray(reused), np.asarray(prepared))
    other = SimpleNamespace(analysis_denoise_strength="weak")
    changed = build_analysis_image(prepared, other)
    assert changed.info["_picture_capture_analysis_strength"] == "weak"
