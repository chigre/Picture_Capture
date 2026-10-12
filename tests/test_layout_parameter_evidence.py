"""Unobserved layout placeholders may not overwrite user Profile settings."""
from types import SimpleNamespace

from PIL import Image

from picture_capture.layout_parameter_evidence import (
    row_padding_is_measured,
    verified_multi_page_row_padding,
)
from picture_capture.dictionary_page_layout_policy import (
    _RAW_RESOLVE_PAGE_LAYOUT_POLICY,
)
from picture_capture.models import AppSettings


def estimate(method, row_padding):
    return SimpleNamespace(
        method=method, row_padding=row_padding,
        columns=2, character_height=30, start_y=30, manual_x=10,
        column_width=400, gutter=40, bottom_y=600,
    )


def test_projection_only_is_never_a_measured_row_gap():
    assert not row_padding_is_measured(estimate("projection_fallback", 1))
    assert not row_padding_is_measured(estimate(
        "reliable_fusion+projection_only+paddle_error=RuntimeError", 1,
    ))
    assert not row_padding_is_measured(estimate(
        "profile_bootstrap+projection_fallback+observed_character_height=30(n=80)", 1,
    ))
    assert row_padding_is_measured(estimate(
        "reliable_fusion+paddle+observed_row_padding=7(n=24)+projection_fallback", 7,
    ))


def test_multi_page_median_excludes_unobserved_placeholders():
    guesses = [estimate("reliable_fusion+projection_only", 1)] * 4
    real = [
        estimate("reliable_fusion+paddle+observed_row_padding=7(n=24)+projection_fallback", 9),
        estimate("reliable_fusion+paddle+observed_row_padding=7(n=24)+projection_fallback", 10),
    ]
    assert verified_multi_page_row_padding(guesses + real) == (None, 2)
    assert verified_multi_page_row_padding(real + guesses[:1]) == (10, 2)
    assert verified_multi_page_row_padding(guesses) == (None, 0)


def test_per_page_unmeasured_gap_keeps_existing_profile(monkeypatch):
    from picture_capture import layout_detection
    settings = AppSettings(
        ordinary_auto_layout=True,
        ordinary_auto_row_padding=True,
        row_padding=9,
        ordinary_auto_character_height=False,
        ordinary_auto_manual_x=False,
        ordinary_auto_columns=False,
    )
    img = Image.new("RGB", (900, 700), "white")
    try:
        monkeypatch.setattr(
            layout_detection, "detect_layout_parameters",
            lambda *_a, **_kw: estimate("reliable_fusion+projection_only", 1),
        )
        resolved, _estimate, applied = _RAW_RESOLVE_PAGE_LAYOUT_POLICY(img, settings)
        assert resolved.row_padding == 9
        assert "row_padding" not in applied

        monkeypatch.setattr(
            layout_detection, "detect_layout_parameters",
            lambda *_a, **_kw: estimate(
                "reliable_fusion+paddle+observed_row_padding=7(n=24)+projection_fallback", 6,
            ),
        )
        resolved, _estimate, applied = _RAW_RESOLVE_PAGE_LAYOUT_POLICY(img, settings)
        assert resolved.row_padding == 6
        assert applied["row_padding"] == 6
    finally:
        img.close()


def test_profile_bootstrap_suggestion_never_claims_measured_row_padding():
    from picture_capture.profile_layout_bootstrap import apply_profile_ink_height_suggestion

    proposed = {"character_height": 17, "row_padding": 1}
    notice = apply_profile_ink_height_suggestion(proposed, [
        estimate("profile_bootstrap+projection_fallback+observed_character_height=30(n=60)", 1)
    ])
    assert proposed["character_height"] == 30  # trustworthy estimate's value
    assert "row_padding" not in proposed
    assert "行间空" in notice
