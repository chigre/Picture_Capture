from __future__ import annotations

from PIL import Image, ImageDraw

from picture_capture.models import AppSettings, Entry
from picture_capture.ordinary_lane_polarity import suppress_inverted_legacy_body_lane
from picture_capture.processing import derive_nominal_geometry


def _page_with_body_and_indented_lane(*, bracket_rows: int = 4):
    image = Image.new("RGB", (360, 520), "white")
    draw = ImageDraw.Draw(image)
    body_y = list(range(40, 400, 28))
    bracket_y = body_y[2:2 + bracket_rows]
    for y in body_y:
        if y in bracket_y:
            # Repeated indented structural marker + following text.
            draw.rectangle((62, y, 66, y + 11), fill="black")
            draw.rectangle((70, y, 78, y + 2), fill="black")
            draw.rectangle((70, y + 9, 78, y + 11), fill="black")
            draw.rectangle((82, y + 2, 190, y + 9), fill="black")
        else:
            # Dense flush-left body text.
            draw.rectangle((6, y, 210, y + 9), fill="black")
            for x in range(18, 205, 18):
                draw.rectangle((x, y, x + 2, y + 9), fill="white")
    return image, body_y, bracket_y


def _settings() -> AppSettings:
    return AppSettings(
        columns=1,
        manual_x=0,
        column_width=330,
        gutter=0,
        start_y=20,
        bottom_y=500,
        crop_to_bottom_y=True,
        character_height=20,
        row_padding=0,
        follow_column_deformation=False,
        dictionary_profile_id="cjk_visual",
        ocr_language="chi_sim",
        paddle_language="ch",
        profile_cjk_allow_bracketed_headword=True,
        profile_cjk_allow_single_headword=True,
    )


def _legacy_entries(body_y: list[int], bracket_y: list[int]) -> list[Entry]:
    return [
        Entry(word="", x=0, y=y - 5, confidence=0.98, ocr_source="ordinary_vb")
        for y in body_y if y not in bracket_y
    ]


def test_dense_flush_left_vb_rows_are_suppressed_when_indented_entry_lane_is_proven():
    image, body_y, bracket_y = _page_with_body_and_indented_lane(bracket_rows=4)
    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)

    legacy = _legacy_entries(body_y, bracket_y)
    # Independent visual observations must never be removed by polarity repair.
    visual = Entry(
        word="", x=0, y=18, confidence=0.96,
        ocr_source="ordinary_visual", issue_type="ORDINARY_CJK_VISUAL_RESCUE",
    )
    result = suppress_inverted_legacy_body_lane(
        image, legacy + [visual], geometry, settings,
    )

    assert visual in result
    assert not [item for item in result if item.ocr_source == "ordinary_vb"]
    recovered = [
        item for item in result if item.ocr_source == "ordinary_visual_lane"
    ]
    assert len(recovered) == 4
    assert all(
        "ORDINARY_INDENTED_ENTRY_LANE_POLARITY" in item.issue_type
        for item in recovered
    )


def test_sparse_indentation_never_flips_legacy_lane_polarity():
    image, body_y, bracket_y = _page_with_body_and_indented_lane(bracket_rows=2)
    settings = _settings()
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    legacy = _legacy_entries(body_y, bracket_y)

    result = suppress_inverted_legacy_body_lane(
        image, legacy, geometry, settings,
    )
    assert len(result) == len(legacy)
    assert all(item.ocr_source == "ordinary_vb" for item in result)


def test_parser_bracket_switch_does_not_disable_plain_ordinary_lane_detection():
    image, body_y, bracket_y = _page_with_body_and_indented_lane(bracket_rows=4)
    settings = _settings()
    settings.profile_cjk_allow_bracketed_headword = False
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    legacy = _legacy_entries(body_y, bracket_y)

    result = suppress_inverted_legacy_body_lane(
        image, legacy, geometry, settings,
    )
    assert not [item for item in result if item.ocr_source == "ordinary_vb"]
    assert len([
        item for item in result if item.ocr_source == "ordinary_visual_lane"
    ]) == 4


def test_plain_ordinary_lane_detection_does_not_require_cjk_ocr_profile():
    image, body_y, bracket_y = _page_with_body_and_indented_lane(bracket_rows=4)
    settings = _settings()
    settings.dictionary_profile_id = "default"
    settings.ocr_language = "eng"
    settings.paddle_language = "en"
    settings.profile_cjk_allow_bracketed_headword = False
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    legacy = _legacy_entries(body_y, bracket_y)

    result = suppress_inverted_legacy_body_lane(
        image, legacy, geometry, settings,
    )
    assert not [item for item in result if item.ocr_source == "ordinary_vb"]
    assert len([
        item for item in result if item.ocr_source == "ordinary_visual_lane"
    ]) == 4
