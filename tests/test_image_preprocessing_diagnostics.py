from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from picture_capture import (
    image_preprocessing,
    image_preprocessing_constants,
    image_preprocessing_reporting,
)


def test_phase7r_preprocessing_constants_keep_stable_old_module_aliases() -> None:
    for name in (
        "DEFAULT_MAX_AUTO_DESKEW_DEG",
        "DEFAULT_DESKEW_DEAD_ZONE_DEG",
        "AUTO_HOMOGRAPHY_HORIZONTAL_SCALE_SPAN_MAX",
        "AUTO_HOMOGRAPHY_VERTICAL_SCALE_SPAN_MAX",
        "AUTO_HOMOGRAPHY_AREA_SCALE_SPAN_MAX",
        "AUTO_HOMOGRAPHY_ANISOTROPY_P95_MAX",
        "ORTHOGONAL_AUTO_MIN_CONFIDENCE",
        "ORTHOGONAL_AUTO_MIN_SCORE_IMPROVEMENT",
        "ORTHOGONAL_AUTO_GAINS",
        "ORTHOGONAL_MIN_SAFE_GAIN",
        "ORTHOGONAL_SCALE_SAFETY_FRACTION",
        "ORTHOGONAL_TAIL_PROGRESS_RATIO",
        "ORTHOGONAL_TAIL_MAX_REGRESSION_PX",
        "ORTHOGONAL_MAX_AUTO_PASSES",
        "POST_PERSPECTIVE_REDETECT_MIN_BOXES",
        "ORTHOGONAL_VERTICAL_MAX_SPAN_MIN_PX",
        "ORTHOGONAL_VERTICAL_MAX_SPAN_WIDTH_RATIO",
    ):
        assert getattr(image_preprocessing, name) is getattr(
            image_preprocessing_constants, name
        )


def test_phase7r_diagnostic_export_keeps_historical_wrapper_path() -> None:
    assert (
        image_preprocessing.export_diagnostic_json.__module__
        == "picture_capture.image_preprocessing"
    )


def test_phase7r_diagnostic_wrapper_uses_current_canvas_hook(
    tmp_path: Path, monkeypatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_canvas_info(analysis, *, enabled):
        seen["analysis"] = analysis
        seen["enabled"] = enabled
        return SimpleNamespace(to_dict=lambda: {"hook": "current-module-global"})

    monkeypatch.setattr(
        image_preprocessing, "output_canvas_info", fake_canvas_info
    )
    analysis = SimpleNamespace(
        crop_box=(2, 3, 22, 33),
        to_dict=lambda: {"status": "ok"},
    )
    destination = tmp_path / "diagnostic.json"

    result = image_preprocessing.export_diagnostic_json(
        tmp_path / "page001.png",
        analysis,
        destination,
    )

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert result == destination
    assert seen == {"analysis": analysis, "enabled": False}
    assert payload["page"] == "page001.png"
    assert payload["export"]["canvas"] == {"hook": "current-module-global"}
    assert payload["algorithm_constants"]["max_auto_deskew_deg"] == 5.0


def test_phase7r_reporting_owner_has_no_runtime_back_import() -> None:
    source = Path(image_preprocessing_reporting.__file__).read_text(
        encoding="utf-8"
    )
    assert "from .image_preprocessing import" not in source
    assert "import picture_capture.image_preprocessing" not in source
