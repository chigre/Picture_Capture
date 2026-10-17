from picture_capture.quality.ordinary_verified_evaluation import (
    TRUTH_SCHEMA, evaluate_ordinary_page,
)


def _truth(positions, verified=True):
    return {
        "schema": TRUTH_SCHEMA,
        "human_verified": verified,
        "image_size": [1388, 2156],
        "lines": [{"x": 0, "y": y} for y in positions],
    }


def _auto(positions):
    return {
        "page_index": 8,
        "image_size": [1388, 2156],
        "final_lines": [{"x": 0, "y": y} for y in positions],
    }


def test_verified_precision_recall_and_false_line_coordinates():
    result = evaluate_ordinary_page(
        _auto([100, 200, 310]),
        _truth([100, 200, 500]),
        tolerance_px=12,
    )
    assert result["tp"] == 2
    assert result["fp"] == 1
    assert result["fn"] == 1
    assert result["precision"] == 0.666667
    assert result["recall"] == 0.666667
    assert result["f1"] == 0.666667
    assert result["false_positives"][0]["y"] == 310
    assert result["false_negatives"][0]["y"] == 500
    assert result["auto_baseline_as_truth"] is False


def test_saved_auto_lines_cannot_silently_claim_ground_truth():
    for source in (
        _truth([100], verified=False),
        {"schema": "picture-capture-human-reviewed-lines-v1",
         "lines": [{"x": 0, "y": 100}]},
        {"schema": "picture-capture-large-head-diagnostics-v1",
         "human_verified": True, "lines": [{"x": 0, "y": 100}]},
    ):
        try:
            evaluate_ordinary_page(_auto([100]), source)
        except ValueError as error:
            assert "人工复核" in str(error)
        else:
            raise AssertionError("unverified automatic PDIC cannot be ground truth")


def test_verified_truth_and_prediction_must_use_same_image_coordinates():
    ref = _truth([100])
    ref["image_size"] = [1318, 2048]
    try:
        evaluate_ordinary_page(_auto([100]), ref)
    except ValueError as error:
        assert "尺寸" in str(error)
    else:
        raise AssertionError("do not quietly compare resized PNG coordinates")
