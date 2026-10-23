"""Issue #562: column-tracking math and Paddle result decoding keep legacy hooks."""
from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

from picture_capture import processing as processing_public
from picture_capture import processing_core
from picture_capture import paddle_headwords as headwords_public
from picture_capture import paddle_headwords_core
from picture_capture.geometry import column_tracking_math
from picture_capture.models import AppSettings
from picture_capture.ocr import paddle_results
from picture_capture.ocr.headword_models import OCRRecord

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "picture_capture"


def test_leaf_ownership_and_old_core_import_signatures():
    assert (PACKAGE / "geometry/column_tracking_math.py").is_file()
    assert (PACKAGE / "ocr/paddle_results.py").is_file()
    assert not (PACKAGE / "column_tracking_math.py").exists()
    assert not (PACKAGE / "paddle_results.py").exists()
    assert len(list(PACKAGE.glob("*.py"))) == 10
    assert processing_core._smooth_track.__module__ == "picture_capture.processing_core"
    assert processing_core._column_tracking_dimensions.__module__ == "picture_capture.processing_core"
    assert paddle_headwords_core._json_payload.__module__ == "picture_capture.paddle_headwords_core"
    assert paddle_headwords_core.extract_ocr_records.__module__ == "picture_capture.paddle_headwords_core"
    assert list(inspect.signature(processing_core._smooth_track).parameters) == [
        "values", "max_step", "nominal_x",
    ]
    assert list(inspect.signature(paddle_headwords_core.extract_ocr_records).parameters) == ["result"]
    assert paddle_headwords_core.OCRRecord is OCRRecord
    assert headwords_public.OCRRecord is OCRRecord


def test_track_math_matches_core_for_outliers_and_monotonic_slopes():
    samples = [
        ([], 3, None),
        ([20], 5, 5),
        ([10, 11, 12, 13, 14, 15], 3, 10),
        ([10, 11, 55, 12, 13, 14], 4, 10),
        ([18, 19, 20, 95, 99, 21, 22], 5, 20),
        ([20, 80, 80, 80, 20], 3, None),
    ]
    for values, step, nominal in samples:
        assert processing_core._smooth_track(values, step, nominal_x=nominal) == (
            column_tracking_math._smooth_track(values, step, nominal_x=nominal)
        )
    assert processing_core._smooth_track([10, 11, 12, 13], 2) == [10, 11, 12, 13]
    assert processing_core._smooth_track([100], 5, nominal_x=10) == [10]


def test_column_dimensions_use_current_settings_and_public_patch_bridge(monkeypatch):
    settings = AppSettings()
    for width, height in ((10, 10), (500, 1200), (2800, 9000)):
        assert processing_core._column_tracking_dimensions(width, height, settings) == (
            column_tracking_math._column_tracking_dimensions(width, height, settings)
        )
    original = processing_core._smooth_track
    fake = lambda values, max_step, *, nominal_x=None: [42] * len(values)
    monkeypatch.setattr(processing_public, "_smooth_track", fake)
    assert processing_core._smooth_track is fake
    assert processing_core._smooth_track([1, 2], 3) == [42, 42]
    monkeypatch.setattr(processing_public, "_smooth_track", original)


def test_paddle_result_dict_callable_and_native_record_identity():
    payload = {
        "rec_texts": [" late ", " first ", "invalid"],
        "rec_scores": [0.7, 0.9, 0.6],
        "rec_boxes": [[10, 20, 30, 40], [1, 2, 9, 8], [2, 4, 2, 8]],
    }
    for result in (payload, {"res": payload}, type("Result", (), {"json": lambda self: {"res": payload}})()):
        rows = paddle_headwords_core.extract_ocr_records(result)
        assert rows == paddle_results.extract_ocr_records(result)
        assert [(r.text, r.box) for r in rows] == [
            ("first", (1, 2, 9, 8)),
            ("late", (10, 20, 30, 40)),
        ]
        assert all(isinstance(row, OCRRecord) for row in rows)


def test_paddle_polygon_fallback_and_invalid_payload():
    raw = {"rec_texts": [" han "], "rec_scores": [0.88],
           "rec_polys": [np.array([[1, 2], [5, 2], [5, 9], [1, 9]])]}
    rows = paddle_headwords_core.extract_ocr_records(raw)
    assert [(row.text, row.box) for row in rows] == [("han", (1, 2, 5, 9))]
    with pytest.raises(RuntimeError, match="无法解析"):
        paddle_headwords_core.extract_ocr_records(["bad"])


def test_paddle_core_parser_reads_facade_patch_at_call_time(monkeypatch):
    original = paddle_headwords_core._json_payload
    monkeypatch.setattr(headwords_public, "_json_payload",
                        lambda _: {"rec_texts": [" patched "], "rec_scores": [1.0],
                                   "rec_boxes": [[0, 1, 4, 5]]})
    rows = paddle_headwords_core.extract_ocr_records(object())
    assert len(rows) == 1 and rows[0].text == "patched"
    assert rows[0].box == (0, 1, 4, 5)
    monkeypatch.setattr(headwords_public, "_json_payload", original)
