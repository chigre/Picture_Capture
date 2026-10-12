"""Differential diagnostics: old v1 exports and new unified v2 exports."""
from picture_capture.ordinary_unified_diff import compare_ordinary_diagnostics


def _line(y, source="ordinary_layout_role"):
    return {"x": 20, "y": y, "source": source}


def _page(lines, *, roles=None, image_size=(1388, 2156), accepted=2):
    return {
        "image_size": list(image_size),
        "final_lines": [_line(y) for y in lines],
        "layout_snapshot": {
            "physical_rows": [
                {"source_y": y, "column": 0, "role": role,
                 "entry_source": "indent"}
                for y, role in (roles or [])
            ]
        },
        "summary": {"accepted": accepted},
    }


def test_added_removed_shifted_and_role_flips_are_separately_reported():
    earlier = _page([100, 203, 400], roles=[
        (100, "entry"), (203, "entry"), (400, "body"),
    ])
    later = _page([104, 400, 800], roles=[
        (104, "entry"), (203, "body"), (400, "body"),
    ], accepted=4)
    diff = compare_ordinary_diagnostics(earlier, later, tolerance_px=12)
    assert diff["counts"]["before_lines"] == 3
    assert diff["counts"]["after_lines"] == 3
    assert diff["counts"]["matched"] == 2
    assert diff["counts"]["removed"] == 1
    assert diff["counts"]["added"] == 1
    assert diff["counts"]["shifted"] == 1
    assert diff["counts"]["layout_role_changes"] == 1
    assert diff["layout_role_changes"][0]["before_role"] == "entry"
    assert diff["layout_role_changes"][0]["after_role"] == "body"
    assert diff["added_lines"][0]["y"] == 800
    assert diff["removed_lines"][0]["y"] == 203
    assert diff["counts"]["before_accepted_large_heads"] == 2
    assert diff["counts"]["after_accepted_large_heads"] == 4
    assert diff["ground_truth"] == "not_provided"


def test_old_large_head_v1_without_layout_uses_final_line_compatibility():
    legacy = {
        "schema": "picture-capture-large-head-diagnostics-v1",
        "image_size": [1388, 2156],
        "summary": {"accepted": 9},
        "final_lines": [_line(100), _line(400)],
    }
    new = {
        "schema": "picture-capture-ordinary-evidence-v2",
        "image_size": [1388, 2156],
        "summary": {"accepted": 21},
        "final_lines": [_line(104), _line(500)],
        "review_queue": [{"candidate_id": "C01-R007"}],
    }
    result = compare_ordinary_diagnostics(legacy, new)
    assert result["counts"]["matched"] == 1
    assert result["counts"]["added"] == 1
    assert result["counts"]["removed"] == 1
    assert result["counts"]["after_review"] == 1


def test_mismatched_image_size_is_not_silently_compared():
    try:
        compare_ordinary_diagnostics(
            _page([100]), _page([100], image_size=(1200, 1500)),
        )
    except ValueError as exc:
        assert "不同原图尺寸" in str(exc)
    else:
        raise AssertionError("must not compare coordinates of unequal images")


def test_same_image_without_lines_is_safe():
    result = compare_ordinary_diagnostics(
        _page([]), _page([]),
    )
    assert result["counts"]["matched"] == 0
    assert result["counts"]["added"] == 0
    assert result["counts"]["removed"] == 0


def test_same_pixel_dimensions_different_page_or_sha256_are_rejected():
    earlier = _page([100])
    later = _page([100])
    earlier["page_index"] = 8
    later["page_index"] = 9
    try:
        compare_ordinary_diagnostics(earlier, later)
    except ValueError as exc:
        assert "page_index" in str(exc)
    else:
        raise AssertionError("should not compare different dictionary pages")

    later["page_index"] = 8
    earlier["image_sha256"] = "a" * 64
    later["image_sha256"] = "b" * 64
    try:
        compare_ordinary_diagnostics(earlier, later)
    except ValueError as exc:
        assert "SHA256" in str(exc)
    else:
        raise AssertionError("should not compare unrelated same-sized scans")
