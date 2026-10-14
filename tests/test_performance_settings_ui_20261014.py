"""Persisted performance diagnostics settings and report snapshot contracts."""
from dataclasses import fields
from pathlib import Path
import json

from picture_capture.models import AppSettings
from picture_capture.ui.settings import schema
from picture_capture import draw_performance_profile as profile


def test_performance_settings_are_persisted(tmp_path):
    settings = AppSettings(draw_performance_profile=True, reuse_prepared_analysis=True)
    assert {"draw_performance_profile", "reuse_prepared_analysis"} <= {
        f.name for f in fields(AppSettings)
    }
    path = tmp_path / "settings.json"
    settings.to_json(path)
    loaded = AppSettings.from_json(path)
    assert loaded.draw_performance_profile is True
    assert loaded.reuse_prepared_analysis is True
    assert AppSettings().draw_performance_profile is False
    assert AppSettings().reuse_prepared_analysis is False
    assert "复用" in schema.CHECK_HELP["reuse_prepared_analysis"]


def test_batch_report_contains_denoise_scale_and_runtime_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "_directory", lambda: tmp_path)
    monkeypatch.setenv("PICTURE_CAPTURE_DRAW_PROFILE", "1")
    monkeypatch.setenv("PICTURE_CAPTURE_REUSE_PREPARED_ANALYSIS", "1")
    config = AppSettings(
        draw_performance_profile=True, reuse_prepared_analysis=True,
        layout_scale_enabled=True, layout_denoise_enabled=False,
    )
    saved = profile.export_batch_report(
        [{"page": "a.png", "page_index": 0, "pid": 1,
          "stage_group": "layout_scale_50pct", "stages_ms": {"selected": 0}},
         {"page": "a.png", "page_index": 0, "pid": 1,
          "stage_group": "page", "stages_ms": {"total_page": 1000}}],
        label="ordinary", elapsed_seconds=1.0, completed=1, settings=config,
    )
    assert saved is not None and saved.exists()
    markdown = saved.read_text(encoding="utf-8")
    assert "## 运行配置快照" in markdown
    assert "50pct: 1 页" in markdown
    snapshot = json.loads(saved.with_suffix(".settings.json").read_text(encoding="utf-8"))
    assert snapshot["reuse_prepared_analysis"] is True
    assert snapshot["layout_scale_enabled"] is True
    assert snapshot["layout_denoise_enabled"] is False
    assert snapshot["prepared_reuse_environment"] == "1"
    assert saved.with_suffix(".csv").is_file()
