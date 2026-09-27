from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from picture_capture import image_preprocessing
from picture_capture.image_preprocessing import (
    PreprocessAnalysis,
    analysis_is_current,
    analyze_preprocess_page,
    estimate_skew_from_polygons,
    load_analysis,
    overlay_excluded_regions,
    save_analysis,
)
from picture_capture.layout_detection import detect_text_polygons
from picture_capture.models import AppSettings


def _tilted_box(
    x0: float, y0: float, width: float, height: float, angle_deg: float,
) -> np.ndarray:
    slope = math.tan(math.radians(angle_deg))
    dy = slope * width
    return np.asarray(
        [
            [x0, y0],
            [x0 + width, y0 + dy],
            [x0 + width, y0 + height + dy],
            [x0, y0 + height],
        ],
        dtype=float,
    )


def test_polygon_skew_estimator_preserves_small_angle() -> None:
    polygons = [
        _tilted_box(80, 100 + row * 45, 260, 28, 1.25)
        for row in range(12)
    ]
    angle, samples, mad = estimate_skew_from_polygons(polygons)

    assert samples >= 20
    assert abs(angle - 1.25) < 0.08
    assert mad < 0.05


def test_text_polygon_detection_preserves_polygon_geometry(monkeypatch) -> None:
    class FakeDetector:
        @staticmethod
        def predict(_image, **_kwargs):
            return [
                {
                    "res": {
                        "dt_polys": [
                            [[10, 20], [110, 23], [109, 48], [9, 45]],
                        ]
                    }
                }
            ]

    import picture_capture.layout_detection as layout_detection

    monkeypatch.setattr(layout_detection, "_get_text_detector", lambda _settings: FakeDetector())
    polygons = detect_text_polygons(Image.new("RGB", (200, 120), "white"), AppSettings())

    assert len(polygons) == 1
    assert polygons[0].shape == (4, 2)
    assert polygons[0][1, 1] == 23
    assert polygons[0][2, 0] == 109


def test_preprocess_combines_text_envelope_with_edge_artifact_guard(monkeypatch) -> None:
    image = Image.new("RGB", (1000, 1400), "white")
    draw = ImageDraw.Draw(image)
    # Simulate a dark scanner/binding trace near the left physical edge.
    draw.rectangle((3, 80, 10, 1320), fill="black")
    polygons = []
    for row in range(12):
        y = 170 + row * 82
        draw.rectangle((120, y, 880, y + 25), fill="black")
        polygons.append(_tilted_box(120, y, 760, 25, 0.0))

    monkeypatch.setattr(
        image_preprocessing,
        "detect_text_polygons",
        lambda _image, _settings: polygons,
    )
    analysis = analyze_preprocess_page(
        image,
        AppSettings(analysis_threshold_mode="fixed", darkness_threshold=600),
        safety_margin_percent=1.5,
        auto_deskew=True,
    )

    x0, y0, x1, y1 = analysis.crop_box
    assert 25 < x0 < 120
    assert x1 >= 880
    assert y0 < 170
    assert y1 > 170 + 11 * 82 + 25
    assert analysis.source_boxes == 12
    assert analysis.status == "review"
    assert any("页边墨迹" in warning for warning in analysis.warnings)


def test_preview_overlay_marks_only_nonretained_area() -> None:
    source = Image.new("RGB", (100, 100), "white")
    preview = overlay_excluded_regions(source, (20, 20, 80, 80))

    assert preview.getpixel((5, 5)) != (255, 255, 255)
    assert preview.getpixel((50, 50)) == (255, 255, 255)
    assert preview.getpixel((20, 20)) != (255, 255, 255)


def test_preprocess_analysis_roundtrip_and_source_signature(tmp_path: Path) -> None:
    page = tmp_path / "0001.png"
    Image.new("RGB", (120, 180), "white").save(page)
    stat = page.stat()
    analysis = PreprocessAnalysis(
        source_width=120,
        source_height=180,
        correction_angle_deg=0.5,
        applied_angle_deg=0.5,
        crop_box=(10, 12, 110, 170),
        raw_content_box=(12, 14, 108, 168),
        text_box=(15, 18, 105, 165),
        source_boxes=20,
        angle_samples=30,
        angle_mad_deg=0.1,
        retained_ratio=0.73,
        confidence=0.9,
        status="normal",
        method="paddle_text_polygons",
        safety_margin_percent=1.5,
        auto_deskew=True,
        source_size_bytes=stat.st_size,
        source_mtime_ns=stat.st_mtime_ns,
    )

    save_analysis(tmp_path, page, analysis)
    loaded = load_analysis(tmp_path, page)

    assert loaded is not None
    assert loaded.crop_box == analysis.crop_box
    assert loaded.auto_deskew is True
    assert analysis_is_current(
        loaded, page, safety_margin_percent=1.5, auto_deskew=True
    )
    assert not analysis_is_current(
        loaded, page, safety_margin_percent=2.0, auto_deskew=True
    )
    assert not analysis_is_current(
        loaded, page, safety_margin_percent=1.5, auto_deskew=False
    )


def test_main_workspace_exposes_and_locks_preprocess_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/picture_capture/app.py").read_text(encoding="utf-8")

    assert '"图片预处理（前置）"' in source
    assert 'text="进入预处理模式"' in source
    assert 'text="自动纠偏"' in source
    assert 'text="安全边界："' in source
    assert 'text="分析所选范围"' in source
    assert 'text="导出检查小图"' in source
    assert 'text="导出预处理图片"' in source
    assert 'section_keys = ("normal", "aux", "ocr", "actions", "postproduction")' in source
    assert "if self._preprocess_mode_active():" in source
    assert "self._redraw_preprocess_preview(size)" in source
    assert "普通编辑已锁定" in source
