"""Settings Center migration and noise-tolerant unlined left-blank filtering."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from picture_capture.ui.settings.inference_performance import validate_draw_inference_values
from picture_capture.unlined_line_export import (
    UnlinedRow, _save_unlined_rows, left_contiguous_white_percent,
)


def test_draw_inference_options_validate_without_changing_project_settings():
    assert validate_draw_inference_values("AUTO", "On", " 4 ", cpu_limit=8) == ("auto", "on", "4")
    assert validate_draw_inference_values("cpu", "off", "auto", cpu_limit=2) == ("cpu", "off", "auto")
    for device, mkldnn, workers in [
        ("bad", "auto", "auto"), ("gpu", "unknown", "auto"),
        ("cpu", "on", "0"), ("cpu", "on", "9"), ("cpu", "on", "bad"),
    ]:
        with pytest.raises(ValueError):
            validate_draw_inference_values(device, mkldnn, workers, cpu_limit=8)


def test_performance_controls_are_inline_in_settings_center_not_environment_center():
    source = Path(__file__).resolve().parents[1] / "src/picture_capture"
    app = (source / "app.py").read_text(encoding="utf-8")
    env = (source / "environment_center.py").read_text(encoding="utf-8")
    ui = (source / "ui/settings/inference_performance.py").read_text(encoding="utf-8")
    assert '(performance_tab, "性能测试与诊断")' in app
    assert "build_inference_performance_group(self, performance_page)" in app
    assert '"画线性能设置"' not in env
    assert "_open_inference_settings" not in env
    for name in ("paddle_device", "paddle_mkldnn", "paddle_cpu_workers"):
        assert name in ui
    assert "save_runtime_setting(" in ui
    assert "clear_runtime_caches()" in ui
    assert "_batch_active" in ui
    assert "不随词典项目迁移" in ui


def test_noise_clusters_do_not_cut_off_contiguous_left_white_run():
    scan = Image.new("RGB", (100, 24), (221, 215, 202))
    draw = ImageDraw.Draw(scan)
    # Small 3x3 spots qualify the old column-ink vote but are NOT typography.
    for x, y in ((1, 2), (8, 10), (17, 18), (28, 4), (44, 12)):
        draw.rectangle((x, y, x + 2, y + 2), fill="black")
    draw.rectangle((65, 4, 77, 20), fill=(20, 20, 20))
    assert left_contiguous_white_percent(scan) == 65.0
    scan.close()


def test_sparse_dust_only_is_fully_blank_and_export_preserves_noise_pixels(tmp_path):
    scan = Image.new("RGB", (100, 24), "white")
    draw = ImageDraw.Draw(scan)
    for x, y in ((1, 2), (20, 12), (50, 7), (82, 18)):
        draw.rectangle((x, y, x + 2, y + 2), fill="black")
    assert left_contiguous_white_percent(scan) == 100.0
    page = tmp_path / "dust.png"
    output = tmp_path / "output"
    result = _save_unlined_rows(
        scan, page, [UnlinedRow(0, 0, "body", (0, 0, 100, 24), 0)],
        output, merge_by_page=False, filter_enabled=True,
        filter_blank=True, left_white_percent=50.0,
    )
    assert result == (1, 1, 0, False)
    with Image.open(output / "dust_UL_000.png") as saved:
        assert saved.size == (100, 24)
        assert saved.getpixel((1, 2)) == (0, 0, 0)
    scan.close()


@pytest.mark.parametrize("shape", ["vertical", "dash", "dense"])
def test_meaningful_thin_typography_still_ends_left_white_run(shape):
    scan = Image.new("RGB", (100, 24), "white")
    draw = ImageDraw.Draw(scan)
    if shape == "vertical":
        draw.line((8, 3, 8, 15), fill="black", width=1)
    elif shape == "dash":
        draw.line((8, 9, 18, 9), fill="black", width=2)
    else:
        draw.rectangle((8, 6, 10, 11), fill="black")
    assert left_contiguous_white_percent(scan) == 8.0
    scan.close()


def test_strict_50_percent_threshold_not_relaxed_by_noise_tolerance(tmp_path):
    scan = Image.new("RGB", (100, 24), "white")
    draw = ImageDraw.Draw(scan)
    draw.rectangle((2, 1, 4, 3), fill="black")
    draw.rectangle((50, 3, 70, 19), fill="black")
    assert left_contiguous_white_percent(scan) == 50.0
    result = _save_unlined_rows(
        scan, tmp_path / "edge.png",
        [UnlinedRow(0, 0, "body", (0, 0, 100, 24), 0)],
        tmp_path / "output", merge_by_page=False,
        filter_enabled=True, filter_blank=True, left_white_percent=50.0,
    )
    assert result == (0, 0, 1, False)
    scan.close()
