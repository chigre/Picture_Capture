from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

import picture_capture.paddle_headwords as paddle_headwords

from picture_capture.app import (
    PictureCaptureApp, SettingsDialog, binary_preview_image, effective_main_overlay_font_size,
    _layout_pixels_to_percent, _layout_percent_to_pixels,
    ReviewWindow, VerticalWordText, entry_index_label_layout,
    horizontal_ocr_menu_layout, horizontal_overlay_layout,
    transformed_entry_anchor, vertical_marker_contact_gap, vertical_ocr_menu_layout,
    vertical_overlay_layout,
)
from picture_capture.dictionary_profile import (
    apply_project_profile_components, effective_project_profile_id,
    load_dictionary_profile, profile_symbol_inventory_defaults,
    profile_tail_structure_defaults, write_project_profile,
)
from picture_capture.models import (
    AppSettings, Entry, ProjectState, project_cover_path, project_page_images,
)
from picture_capture.layout_transform import LayoutTransform
from picture_capture.layout_detection import _analysis_ink_mask
from picture_capture.processing import (
    _collapse_ordinary_oversized_cjk_split_markers, _column_tracking_dimensions,
    _recover_ordinary_oversized_cjk_missing_markers,
    _legacy_find_separator_y, _legacy_is_point, _fuse_detection_entries,
    _left_edge_ink_mask, _ordinary_marker_local_crop, apply_column_start_offsets,
    derive_geometry, derive_nominal_geometry, detect_entries,
    _detect_entries_left_edge as legacy_detect_entries,
    ordinary_page_layout_settings, ocr_existing_entry_words_from_markers,
    refine_existing_entries,
)
from picture_capture.profile_semantics import (
    apply_headword_profile, apply_headword_tuning, apply_reading_choice, configured_body_page_indices,
    effective_page_settings,
    entry_allowed_by_page_template, excluded_source_side, excluded_source_side_percent,
    ordered_headword_profiles,
    page_template_analysis_image, probable_body_page_indices, READING_LABELS,
    reading_choice_from_settings, representative_page_indices, sample_page_indices,
    suggested_body_page_range,
)
from picture_capture.paddle_headwords import (
    OCRLine, OCRRecord, _cache_signature, _compile_patterns,
    _detect_visual_entry_markers, _entries_from_review_candidates,
    compact_ocr_cache_file, compact_ocr_cache_payload,
    _headword_script_compatibility, _ordinary_strong_edge_visual_rescue,
    _ordinary_visual_rescue_thresholds,
    _repair_multiline_headword_state_machine,
    _selected_tail_structure_evidence, filter_headword_records, HeadwordParse,
    parse_headword_filter_rules, parse_headword_text, prepare_ocr_band,
    run_paddle_band, unwrap_column_band, _separator_analysis_x_bounds,
    _recover_oversized_cjk_ocr_records,
)
from picture_capture.profile_setup import (
    _normalize_cjk_visual_symbol_roles,
    _visual_marker_capture_defaults,
)
from picture_capture.visual_marker_templates import (
    build_visual_marker_sample, match_visual_marker_template,
    parse_visual_marker_samples, serialize_visual_marker_samples,
    split_configured_symbols,
)
from picture_capture.project_storage import profile_path, qt_root, settings_path
from picture_capture.picdic import PicDicBuildCancelled, build_picdic_package
from picture_capture.training_export import TrainingExportCancelled, make_training_zip
from picture_capture.recent_projects import (
    load_recent_projects, recent_project_details, remove_recent_project, touch_recent_project,
)


def _project(root: Path, **settings) -> None:
    root.mkdir()
    Image.new("RGB", (8, 8), "white").save(root / "page10.jpg")
    Image.new("RGB", (8, 8), "white").save(root / "page2.jpg")
    Image.new("RGB", (8, 8), "white").save(root / "page1.jpg")
    state = ProjectState.open(root)
    for key, value in settings.items():
        setattr(state.settings, key, value)
    state.settings.to_json(settings_path(root))


def test_projects_restore_independent_settings_and_natural_order(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    _project(a, columns=1, main_entry_font_size=18, ocr_language="eng", paddle_band_width_ratio=60)
    _project(b, columns=3, main_entry_font_size=32, ocr_language="jpn", paddle_band_width_ratio=75)
    for root, expected in ((a, (1, 18, "eng", 60)), (b, (3, 32, "jpn", 75))) * 2:
        state = ProjectState.open(root)
        assert [page.name for page in state.images] == ["page1.jpg", "page2.jpg", "page10.jpg"]
        assert (state.settings.columns, state.settings.main_entry_font_size,
                state.settings.ocr_language, state.settings.paddle_band_width_ratio) == expected





def test_ordinary_mode_self_collapses_split_markers_inside_large_cjk_without_ocr():
    image = Image.new("RGB", (360, 260), "white")
    draw = ImageDraw.Draw(image)
    # One display-size Han glyph surrogate. The ordinary detector can plausibly
    # see a true boundary above it and a false separator in its interior.
    draw.rectangle((20, 60, 82, 130), fill="black")
    # Normal-height left-strip text establishes the page's ordinary line scale
    # for the CJK visual projection detector.
    draw.rectangle((20, 160, 72, 184), fill="black")
    draw.rectangle((20, 200, 78, 224), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=300,
        gutter=0,
        start_y=0,
        character_height=30,
        paddle_band_left_margin=0,
        ocr_language="chi_sim",
        paddle_language="ch",
        dictionary_profile_id="cjk_visual",
        profile_cjk_allow_single_headword=True,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = [
        Entry(word="", x=20, y=52),   # true top boundary
        Entry(word="", x=20, y=102),  # false internal VB separator
        Entry(word="", x=20, y=155),  # unrelated normal row
        Entry(word="", x=20, y=195),  # unrelated normal row
    ]

    collapsed = _collapse_ordinary_oversized_cjk_split_markers(
        image, entries, geometry, settings,
    )
    assert [entry.y for entry in collapsed] == [52, 155, 195]
    assert "ORDINARY_OVERSIZED_CJK_SPLIT_COLLAPSED" in collapsed[0].issue_type





def test_ordinary_mode_recovers_missing_oversized_cjk_from_three_visual_cues():
    image = Image.new("RGB", (360, 300), "white")
    draw = ImageDraw.Draw(image)
    # Oversized approximately-square display head at the column left.
    draw.rectangle((20, 60, 78, 126), fill="black")
    # Ordinary body rows establish the normal line scale and provide baseline
    # ink to the right of the display-head zone.
    draw.rectangle((20, 165, 72, 188), fill="black")
    draw.rectangle((105, 165, 170, 188), fill="black")
    draw.rectangle((20, 210, 74, 233), fill="black")
    draw.rectangle((105, 210, 175, 233), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=300,
        gutter=0,
        start_y=0,
        character_height=30,
        row_padding=1,
        paddle_band_left_margin=0,
        ocr_language="chi_sim",
        paddle_language="ch",
        dictionary_profile_id="cjk_visual",
        profile_cjk_allow_single_headword=True,
        profile_cjk_right_context_enabled=True,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    recovered = _recover_ordinary_oversized_cjk_missing_markers(
        image, [], geometry, settings,
    )
    assert len(recovered) == 1
    assert 45 <= recovered[0].y <= 65
    assert recovered[0].ocr_source == "ordinary_visual"
    assert "ORDINARY_CJK_VISUAL_RESCUE" in recovered[0].issue_type
    assert recovered[0].ocr_oversized_cjk is True


def test_ordinary_large_cjk_collapse_bridges_tiny_internal_glyph_gap():
    image = Image.new("RGB", (360, 260), "white")
    draw = ImageDraw.Draw(image)
    # One physical display glyph split into upper/lower ink fragments by a
    # narrow horizontal white slit. Their X footprints overlap strongly.
    draw.rectangle((20, 60, 82, 94), fill="black")
    draw.rectangle((22, 100, 80, 130), fill="black")
    # Normal body rows establish the ordinary line scale.
    draw.rectangle((20, 160, 72, 184), fill="black")
    draw.rectangle((20, 200, 78, 224), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=300,
        gutter=0,
        start_y=0,
        character_height=30,
        paddle_band_left_margin=0,
        ocr_language="chi_sim",
        paddle_language="ch",
        dictionary_profile_id="cjk_visual",
        profile_cjk_allow_single_headword=True,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = [
        Entry(word="", x=20, y=52),
        Entry(word="", x=20, y=97),
        Entry(word="", x=20, y=155),
        Entry(word="", x=20, y=195),
    ]

    collapsed = _collapse_ordinary_oversized_cjk_split_markers(
        image, entries, geometry, settings,
    )
    assert [entry.y for entry in collapsed] == [52, 155, 195]


def test_ordinary_large_cjk_collapse_does_not_merge_normal_adjacent_entries():
    image = Image.new("RGB", (360, 220), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 60, 78, 84), fill="black")
    draw.rectangle((20, 105, 80, 129), fill="black")
    draw.rectangle((20, 155, 76, 179), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=300,
        gutter=0,
        start_y=0,
        character_height=30,
        paddle_band_left_margin=0,
        ocr_language="chi_sim",
        paddle_language="ch",
        dictionary_profile_id="cjk_visual",
        profile_cjk_allow_single_headword=True,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    entries = [
        Entry(word="", x=20, y=52),
        Entry(word="", x=20, y=97),
        Entry(word="", x=20, y=147),
    ]

    collapsed = _collapse_ordinary_oversized_cjk_split_markers(
        image, entries, geometry, settings,
    )
    assert [entry.y for entry in collapsed] == [52, 97, 147]




def test_ordinary_marker_local_crop_uses_taller_box_for_visual_large_cjk():
    image = Image.new("RGB", (360, 260), "white")
    draw = ImageDraw.Draw(image)
    # Large display head immediately below y=50.
    draw.rectangle((20, 58, 80, 126), fill="black")
    # A normal row lower on the page.
    draw.rectangle((20, 170, 70, 194), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=300,
        gutter=0,
        start_y=0,
        character_height=30,
        row_padding=4,
        ocr_language="chi_sim",
        paddle_language="ch",
        dictionary_profile_id="cjk_visual",
        profile_cjk_allow_single_headword=True,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(image.width, image.height, settings)

    large_crop, large_flag = _ordinary_marker_local_crop(
        image, Entry(word="", x=20, y=50, ocr_source="ordinary_large_head_evidence", issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD", ocr_visual_run_height=68.0, ocr_oversized_cjk=True), geometry, settings,
    )
    normal_crop, normal_flag = _ordinary_marker_local_crop(
        image, Entry(word="", x=20, y=162), geometry, settings,
    )

    assert large_flag is True
    assert normal_flag is False
    assert large_crop.height > normal_crop.height


def test_ordinary_marker_text_ocr_fills_only_blank_without_moving_lines(monkeypatch):
    import picture_capture.paddle_headwords as ph
    import picture_capture.entry_classification_runtime as ecr

    image = Image.new("RGB", (360, 260), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 58, 80, 126), fill="black")
    draw.rectangle((20, 170, 70, 194), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=300,
        gutter=0,
        start_y=0,
        character_height=30,
        row_padding=4,
        ocr_language="chi_sim",
        paddle_language="ch",
        dictionary_profile_id="cjk_visual",
        profile_cjk_allow_single_headword=True,
        follow_column_deformation=False,
    )
    entries = [
        Entry(word="", x=20, y=50, ocr_source="ordinary_large_head_evidence", issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD", ocr_visual_run_height=68.0, ocr_oversized_cjk=True),
        Entry(word="", x=20, y=162),
        Entry(word="已校对", x=20, y=210, manually_selected=True),
    ]
    original_coords = [(entry.x, entry.y) for entry in entries]

    monkeypatch.setattr(ph, "get_paddle_engine", lambda _settings: object())
    monkeypatch.setattr(
        ph,
        "run_paddle_band",
        lambda crop, _settings, engine=None: [
            OCRRecord("dummy", 0.95, (0, 0, max(10, crop.width // 3), max(8, crop.height // 2)))
        ],
    )
    monkeypatch.setattr(
        ph,
        "_single_cjk_from_local_records",
        lambda records, _settings, _profile, max_left_x=None: ("北", 0.98, "北"),
    )
    monkeypatch.setattr(
        ph,
        "group_ocr_records",
        lambda records, y_ratio=0.55: [
            SimpleNamespace(text="【枫】", confidence=0.94, box=(0, 0, 60, 24))
        ],
    )
    monkeypatch.setattr(
        ph,
        "parse_headword_text",
        lambda text, _settings, profile=None: SimpleNamespace(normalized="枫"),
    )

    class FakeChannel:
        def __init__(self, _settings):
            pass

        def recognize_crop(self, crop, **_kwargs):
            return SimpleNamespace(
                plan=None,
                candidates=[SimpleNamespace(
                    ok=True, engine="paddle",
                    records=[OCRRecord("dummy", 0.95, (0, 0, max(10, crop.width // 3), max(8, crop.height // 2)))],
                    text="dummy", confidence=0.95,
                )],
            )

    monkeypatch.setattr(ecr, "OcrChannelSession", FakeChannel)
    monkeypatch.setattr(
        ecr, "choose_ocr_text",
        lambda _plan, resolved: (resolved[0] if resolved else None, False),
    )

    updated, stats = ocr_existing_entry_words_from_markers(
        image,
        entries,
        settings,
        [],
        profile_page_index=0,
        page_sections=None,
        profile_path=None,
        only_blank=True,
    )

    assert [(entry.x, entry.y) for entry in updated] == original_coords
    assert [entry.word for entry in updated] == ["北", "枫", "已校对"]
    assert stats["filled"] == 2
    assert stats["large"] == 1
    assert stats["regular"] == 1
    assert stats["skipped_existing"] == 1
    assert all(
        entry.ocr_source == "ordinary_marker:paddle"
        for entry in updated[:2]
    )




def test_combined_drawing_automatically_runs_marker_text_ocr_for_blank_rescues():
    import inspect
    import picture_capture.app as app_module

    source = Path(inspect.getsourcefile(app_module)).read_text(encoding="utf-8")
    detect_start = source.index("    def _detect_pages(")
    detect_end = source.index("    def clear_entries(", detect_start)
    batch = source[detect_start:detect_end]
    assert 'if method == "combined":' in batch
    assert "ocr_existing_entry_words_from_markers(" in batch
    assert "only_blank=True" in batch
    assert "融合画线自动补字意外修改了画线坐标" in batch
    assert '"text_filled"' in batch
    assert "普通救漏自动补字" in batch

    current_start = source.index("    def auto_detect_current(")
    current_end = source.index("    def paddle_detect_current(", current_start)
    current = source[current_start:current_end]
    assert 'if settings.detection_method == "combined":' in current
    assert "ocr_existing_entry_words_from_markers(" in current
    assert "only_blank=True" in current
    assert "融合画线自动补字不得修改任何画线坐标" in current


def test_cli_combined_autodraw_also_fills_blank_rescue_text():
    import inspect
    import picture_capture.cli as cli_module

    source = Path(inspect.getsourcefile(cli_module)).read_text(encoding="utf-8")
    assert 'if project.settings.detection_method == "combined":' in source
    assert "ocr_existing_entry_words_from_markers(" in source
    assert "only_blank=True" in source
    assert "普通救漏补字" in source


def test_ocr_candidate_band_ratio_is_relative_to_actual_column_width():
    image = Image.new("RGB", (1000, 500), "white")
    settings = AppSettings(
        columns=1,
        manual_x=100,
        column_width=700,
        gutter=0,
        start_y=0,
        paddle_band_width=600,  # legacy value must no longer define 100%
        paddle_band_width_ratio=60,
        paddle_band_left_margin=12,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(image.width, image.height, settings)
    # The last visual interval reaches the page edge (900px here), but the
    # resolved dictionary column itself is 700px wide.
    assert int(geometry.column_widths[0]) == 900
    effective_column_width = int(settings.column_width)

    band60, _top, margin = paddle_headwords.unwrap_column_band(
        image, geometry, 0, settings
    )
    assert margin == 12
    assert band60.width == round(effective_column_width * 0.60) + margin
    assert band60.width != round(settings.paddle_band_width * 0.60)

    settings.paddle_band_width_ratio = 100
    band100, _top, margin = paddle_headwords.unwrap_column_band(
        image, geometry, 0, settings
    )
    assert band100.width == effective_column_width + margin




def _latent_review_candidate(
    *,
    y=100,
    word="annual",
    selected=False,
    reason="missing_pos_inflection_descriptor_or_symbol",
    confidence=0.96,
    two_engines=False,
    features=None,
):
    features = dict(features or {"at_left": True})
    candidate = {
        "candidate_id": "latent-c1",
        "column": 0,
        "source_x": 20,
        "source_y": y,
        "position_variant": "refined",
        "selected": selected,
        "manual_override": False,
        "word": word,
        "final_engine": "paddle",
        "confidence": confidence,
        "score": 3.0,
        "issue_types": [],
        "paddle": {
            "source_x": 20, "source_y": y, "y": y,
            "confidence": confidence, "accepted": False,
            "score": 3.0, "lemma": word, "reason": reason,
            "features": features,
        },
        "tesseract": {},
        "lens": {},
    }
    if two_engines:
        candidate["tesseract"] = {
            "source_x": 20, "source_y": y, "y": y,
            "confidence": confidence, "accepted": False,
            "score": 3.0, "lemma": word, "reason": reason,
            "features": features,
        }
    return candidate


def test_combined_fusion_uses_soft_rejected_ocr_as_metadata_not_as_geometry():
    settings = AppSettings(
        columns=1, manual_x=20, column_width=360, gutter=0,
        start_y=0, character_height=20, follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 260, settings)
    x = int(geometry.column_starts[0])
    ordinary = [Entry(word="", x=x, y=100)]
    candidate = _latent_review_candidate(y=103, word="annual", confidence=0.91)

    fused = _fuse_detection_entries(
        ordinary, [], geometry, settings, review_candidates=[candidate],
    )
    assert len(fused) == 1
    assert fused[0].y == 100
    assert fused[0].word == "annual"
    assert fused[0].ocr_source.startswith("combined:latent:")
    assert "COMBINED_LATENT_OCR_METADATA" in fused[0].issue_type


def test_combined_latent_candidate_pairs_only_once_on_dense_rows():
    settings = AppSettings(
        columns=1, manual_x=20, column_width=360, gutter=0,
        start_y=0, character_height=20,
        paddle_alignment_y_tolerance_ratio=0.50,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 260, settings)
    x = int(geometry.column_starts[0])
    ordinary = [
        Entry(word="", x=x, y=100),
        Entry(word="", x=x, y=108),
    ]
    candidate = _latent_review_candidate(
        y=106, word="nearest", confidence=0.93,
    )

    fused = _fuse_detection_entries(
        ordinary, [], geometry, settings, review_candidates=[candidate],
    )
    assert [(item.word, item.y) for item in fused] == [
        ("", 100),
        ("nearest", 108),
    ]


def test_combined_fusion_suppresses_two_engine_hard_negative_ordinary_false_positive():
    settings = AppSettings(
        columns=1, manual_x=20, column_width=360, gutter=0,
        start_y=0, character_height=20, follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 260, settings)
    x = int(geometry.column_starts[0])
    ordinary = [Entry(word="", x=x, y=100)]
    candidate = _latent_review_candidate(
        y=101,
        word="",
        reason="continuation_fragment",
        confidence=0.96,
        two_engines=True,
        features={"at_left": True, "looks_like_continuation": True},
    )

    fused = _fuse_detection_entries(
        ordinary, [], geometry, settings, review_candidates=[candidate],
    )
    assert fused == []


def test_single_ocr_hard_negative_cannot_erase_strong_full_white_ordinary_boundary():
    settings = AppSettings(
        columns=1, manual_x=20, column_width=360, gutter=0,
        start_y=0, character_height=20, follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 260, settings)
    x = int(geometry.column_starts[0])
    ordinary = [
        Entry(
            word="", x=x, y=100, confidence=0.98,
            ocr_source="ordinary_vb",
        )
    ]
    candidate = _latent_review_candidate(
        y=101,
        word="",
        reason="continuation_fragment",
        confidence=0.99,
        two_engines=False,
        features={"at_left": True, "looks_like_continuation": True},
    )

    fused = _fuse_detection_entries(
        ordinary, [], geometry, settings, review_candidates=[candidate],
    )
    assert [(item.word, item.y) for item in fused] == [("", 100)]


def test_dual_ocr_hard_negative_can_override_strong_ordinary_boundary():
    settings = AppSettings(
        columns=1, manual_x=20, column_width=360, gutter=0,
        start_y=0, character_height=20, follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 260, settings)
    x = int(geometry.column_starts[0])
    ordinary = [
        Entry(
            word="", x=x, y=100, confidence=0.98,
            ocr_source="ordinary_vb",
        )
    ]
    candidate = _latent_review_candidate(
        y=101,
        word="",
        reason="continuation_fragment",
        confidence=0.96,
        two_engines=True,
        features={"at_left": True, "looks_like_continuation": True},
    )

    fused = _fuse_detection_entries(
        ordinary, [], geometry, settings, review_candidates=[candidate],
    )
    assert fused == []


def test_combined_fusion_never_lets_manual_deselection_be_auto_rescued_or_veto_geometry():
    settings = AppSettings(
        columns=1, manual_x=20, column_width=360, gutter=0,
        start_y=0, character_height=20, follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 260, settings)
    x = int(geometry.column_starts[0])
    ordinary = [Entry(word="", x=x, y=100)]
    candidate = _latent_review_candidate(
        y=101,
        word="wrong",
        reason="continuation_fragment",
        confidence=0.99,
        two_engines=True,
        features={"at_left": True, "looks_like_continuation": True},
    )
    candidate["manual_override"] = True
    candidate["selected"] = False

    fused = _fuse_detection_entries(
        ordinary, [], geometry, settings, review_candidates=[candidate],
    )
    assert [(item.word, item.y) for item in fused] == [("", 100)]

def test_combined_fusion_pairs_once_preserves_ordinary_geometry_and_ocr_semantics():
    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=360,
        gutter=0,
        start_y=0,
        character_height=20,
        paddle_alignment_y_tolerance_ratio=0.50,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 500, settings)
    x = int(geometry.column_starts[0])

    ordinary = [
        Entry(word="", x=x, y=100),
        Entry(word="", x=x, y=200),
        Entry(word="", x=x, y=300),
    ]
    ocr = [
        Entry(word="碍口", x=x, y=103, confidence=0.98, ocr_source="paddle",
              candidate_id="c1", final_engine="paddle"),
        Entry(word="OCR救漏", x=x, y=250, confidence=0.95, ocr_source="paddle",
              candidate_id="c2", final_engine="paddle"),
        Entry(word="碍手", x=x, y=304, confidence=0.99, ocr_source="paddle",
              candidate_id="c3", final_engine="paddle"),
    ]

    fused = _fuse_detection_entries(ordinary, ocr, geometry, settings)
    assert [(item.word, item.y) for item in fused] == [
        ("碍口", 100),
        ("", 200),
        ("OCR救漏", 250),
        ("碍手", 300),
    ]
    assert fused[0].ocr_source == "combined:paddle"
    assert fused[-1].candidate_id == "c3"



def test_combined_fusion_uses_cleaner_local_whitespace_separator_position():
    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=300,
        gutter=0,
        start_y=0,
        character_height=20,
        paddle_alignment_y_tolerance_ratio=0.50,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(360, 240, settings)
    x = int(geometry.column_starts[0])
    image = Image.new("RGB", (360, 240), "white")
    draw = ImageDraw.Draw(image)
    # Ordinary marker lies on ink, while the OCR marker is in a clean separator
    # row only four pixels away. Fusion should use image evidence instead of
    # blindly preferring ordinary Y for a non-CJK lemma.
    draw.rectangle((x, 99, x + 150, 101), fill="black")
    ordinary = [Entry(word="", x=x, y=100)]
    ocr = [
        Entry(
            word="annual", x=x, y=104, confidence=0.95,
            ocr_source="paddle", candidate_id="annual", final_engine="paddle",
        )
    ]

    fused = _fuse_detection_entries(
        ordinary, ocr, geometry, settings, image=image,
    )
    assert len(fused) == 1
    assert fused[0].word == "annual"
    assert fused[0].y == 104
    assert "FUSION_WHITESPACE_POSITION_ARBITRATION" in fused[0].issue_type


def test_combined_fusion_matches_globally_nearest_row_not_first_row():
    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=360,
        gutter=0,
        start_y=0,
        character_height=20,
        paddle_alignment_y_tolerance_ratio=0.50,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 300, settings)
    x = int(geometry.column_starts[0])
    ordinary = [Entry(word="", x=x, y=100), Entry(word="", x=x, y=108)]
    ocr = [
        Entry(word="nearest", x=x, y=106, confidence=0.95, ocr_source="paddle",
              candidate_id="nearest", final_engine="paddle")
    ]

    fused = _fuse_detection_entries(ordinary, ocr, geometry, settings)
    assert [(item.word, item.y) for item in fused] == [("", 100), ("nearest", 108)]


def test_combined_fusion_keeps_oversized_single_cjk_ocr_separator():
    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=360,
        gutter=0,
        start_y=0,
        character_height=30,
        paddle_alignment_y_tolerance_ratio=0.50,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 300, settings)
    x = int(geometry.column_starts[0])
    ordinary = [Entry(word="", x=x, y=104)]
    ocr = [
        Entry(word="嗳", x=x, y=96, confidence=0.90, ocr_source="paddle",
              candidate_id="single", final_engine="paddle")
    ]

    fused = _fuse_detection_entries(ordinary, ocr, geometry, settings)
    assert len(fused) == 1
    assert fused[0].word == "嗳"
    assert fused[0].y == 96
    assert fused[0].ocr_source == "combined:paddle"




def test_review_candidate_exports_oversized_single_cjk_geometry_for_fusion():
    entries = _entries_from_review_candidates([
        {
            "selected": True,
            "column": 0,
            "_axis_v": 100,
            "_axis_u": 20,
            "source_x": 20,
            "source_y": 100,
            "word": "北",
            "final_engine": "paddle",
            "confidence": 0.97,
            "candidate_id": "big-cjk",
            "issue_types": [],
            "score": 8.0,
            "line_height_reference": 30.0,
            "paddle": {
                "box": [0, 0, 62, 68],
                "features": {
                    "cjk_single_visual": True,
                    "cjk_single_prominent": True,
                    "leading_record_height_ratio": 2.1,
                    "cjk_visual_run_height": 66,
                },
                "parser_trace": ["chinese_single_character"],
            },
            "tesseract": {},
            "lens": {},
        }
    ])
    assert len(entries) == 1
    entry = entries[0]
    assert entry.ocr_single_cjk is True
    assert entry.ocr_oversized_cjk is True
    assert entry.ocr_box_height == 68
    assert entry.ocr_line_height_reference == 30.0
    assert entry.ocr_visual_run_height == 66
    assert entry.ocr_leading_height_ratio == 2.1


def test_combined_fusion_suppresses_ordinary_split_lines_inside_oversized_cjk_heads():
    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=360,
        gutter=0,
        start_y=0,
        character_height=30,
        paddle_alignment_y_tolerance_ratio=0.50,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 500, settings)
    x = int(geometry.column_starts[0])

    # This mirrors the reported failure: each physical display head produces
    # one correct boundary plus a second ordinary VB hit lower inside the same
    # tall glyph.
    ordinary = [
        Entry(word="", x=x, y=30), Entry(word="", x=x, y=68),
        Entry(word="", x=x, y=110), Entry(word="", x=x, y=151),
        Entry(word="", x=x, y=350), Entry(word="", x=x, y=406),
    ]
    ocr = [
        Entry(
            word="鹎", x=x, y=30, confidence=0.98, ocr_source="paddle",
            candidate_id="big1", final_engine="paddle",
            ocr_box_height=64, ocr_line_height_reference=30,
            ocr_visual_run_height=62, ocr_leading_height_ratio=2.0,
            ocr_single_cjk=True, ocr_oversized_cjk=True,
        ),
        Entry(
            word="筝", x=x, y=110, confidence=0.98, ocr_source="paddle",
            candidate_id="big2", final_engine="paddle",
            ocr_box_height=66, ocr_line_height_reference=30,
            ocr_visual_run_height=64, ocr_leading_height_ratio=2.1,
            ocr_single_cjk=True, ocr_oversized_cjk=True,
        ),
        Entry(
            word="北", x=x, y=350, confidence=0.98, ocr_source="paddle",
            candidate_id="big3", final_engine="paddle",
            ocr_box_height=72, ocr_line_height_reference=30,
            ocr_visual_run_height=70, ocr_leading_height_ratio=2.2,
            ocr_single_cjk=True, ocr_oversized_cjk=True,
        ),
    ]

    fused = _fuse_detection_entries(ordinary, ocr, geometry, settings)
    assert [(entry.word, entry.y) for entry in fused] == [
        ("鹎", 30), ("筝", 110), ("北", 350),
    ]
    assert all(
        "FUSION_OVERSIZED_CJK_ORDINARY_SUPPRESSED" in entry.issue_type
        for entry in fused
    )


def test_combined_fusion_does_not_suppress_after_normal_single_cjk():
    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=360,
        gutter=0,
        start_y=0,
        character_height=30,
        paddle_alignment_y_tolerance_ratio=0.50,
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(420, 260, settings)
    x = int(geometry.column_starts[0])
    ordinary = [Entry(word="", x=x, y=100), Entry(word="", x=x, y=145)]
    ocr = [
        Entry(
            word="中", x=x, y=100, confidence=0.96, ocr_source="paddle",
            candidate_id="normal-single", final_engine="paddle",
            ocr_box_height=29, ocr_line_height_reference=30,
            ocr_leading_height_ratio=0.97,
            ocr_single_cjk=True, ocr_oversized_cjk=False,
        )
    ]

    fused = _fuse_detection_entries(ordinary, ocr, geometry, settings)
    assert [(entry.word, entry.y) for entry in fused] == [("中", 100), ("", 145)]


def test_settings_json_beats_profile_sidecar(tmp_path):
    root = tmp_path / "project"
    _project(root, dictionary_profile_id="latin_pos_classic")
    profile_path(root).write_text('{"format":"dictionary-profile-v2","preset":"cjk_bracket_display"}', encoding="utf-8")
    assert ProjectState.open(root).settings.dictionary_profile_id == "latin_pos_classic"


def test_recent_removal_only_changes_registry(tmp_path):
    project, registry = tmp_path / "scan", tmp_path / "recent.json"
    project.mkdir(); (project / "user.jpg").write_bytes(b"user")
    touch_recent_project(project, registry)
    remove_recent_project(project, registry)
    assert load_recent_projects(registry) == []
    assert (project / "user.jpg").read_bytes() == b"user"


def test_recent_project_keeps_per_project_last_page(tmp_path):
    project, registry = tmp_path / "scan", tmp_path / "recent.json"
    project.mkdir()
    touch_recent_project(
        project, registry, last_page="page10.jpg", last_page_index=9,
    )
    # Re-touching a project without a page update must not erase its resume point.
    touch_recent_project(project, registry)
    row = load_recent_projects(registry)[0]
    assert row["last_page"] == "page10.jpg"
    assert row["last_page_index"] == 9


def test_project_cover_is_preferred_but_never_counted_as_a_page(tmp_path):
    project = tmp_path / "scan"
    _project(project)
    legacy_cover = project / "_project_cover.jpg"
    Image.new("RGB", (60, 90), "red").save(legacy_cover)
    cover = project / "_cover.jpg"
    Image.new("RGB", (60, 90), "blue").save(cover)

    assert project_cover_path(project) == cover
    assert [path.name for path in project_page_images(project)] == [
        "page1.jpg", "page2.jpg", "page10.jpg",
    ]
    state = ProjectState.open(project)
    assert [path.name for path in state.images] == [
        "page1.jpg", "page2.jpg", "page10.jpg",
    ]

    detail = recent_project_details({"name": "scan", "path": str(project)})
    assert detail["image_count"] == 3
    assert detail["cover_source"] == "cover"
    assert detail["cover_path"] == str(cover)
    assert detail["preview_path"] == str(cover)


def test_recent_project_details_expose_requested_columns(tmp_path):
    project = tmp_path / "scan"
    _project(project, dictionary_full_name="完整词典", dictionary_abbreviation="缩写")
    detail = recent_project_details({
        "name": "scan",
        "path": str(project),
        "opened_at": "old",
        "last_page": "page2.png",
        "last_page_index": 1,
    })
    assert detail["full_name"] == "完整词典"
    assert detail["abbreviation"] == "缩写"
    assert detail["image_count"] == 3
    assert detail["path"] == str(project)
    assert detail["last_edited"] != "old"
    missing = recent_project_details({
        "name": "missing",
        "path": str(tmp_path / "missing"),
        "opened_at": "2026-09-23T08:11:05.111954+00:00",
    })
    assert "T" not in str(missing["last_edited"])
    assert len(str(missing["last_edited"])) == 16
    assert detail["last_page"] == "page2.png"
    assert detail["last_page_index"] == 1
    assert detail["position_text"] == "第 2 / 3 页"


def test_recent_projects_dialog_uses_modern_card_information_hierarchy():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    start = source.index("    def open_recent_project(self) -> None:")
    end = source.index("\n    @staticmethod", start)
    text = source[start:end]

    assert 'dialog.title("项目中心")' in text
    assert 'text="最近项目"' in text
    assert 'text="搜索项目"' in text
    assert 'text="清理失效项"' in text
    assert 'text="新建项目", command=create_new_project' in text
    assert 'column=4' in text
    assert 'text="打开"' in text
    assert 'text="⋯"' in text
    assert '"可用" if exists else "路径失效"' in text
    assert "张图片" in text
    assert "上次停留：" in text
    assert "最近活动：" in text
    assert "复制项目路径" in text
    assert "从最近项目移除（不删除文件）" in text
    assert "_cover.jpg" in text
    assert "_project_cover.*" in text
    assert "该文件不会计入正文图片" in text
    assert 'cover_source == "cover"' in text
    assert 'cover_source == "first_page"' in text
    assert "ImageTk.PhotoImage" in text
    assert "width=76" in text and "height=96" in text
    assert "int(screen_w * 0.58)" in text
    assert 'tools.grid(row=1, column=0' in text
    assert 'list_host.grid(row=3, column=0' in text
    assert "显示列" not in text
    assert "词典完整名称" not in text
    assert "从列表删除" not in text


def test_refine_existing_entries_never_changes_count_or_exceeds_safe_delta(monkeypatch):
    import picture_capture.paddle_headwords as paddle_headwords

    def far_refiner(_gray, coarse_y, _line_height, _settings, **_kwargs):
        return coarse_y + 999, {"reason": "test"}

    monkeypatch.setattr(paddle_headwords, "refine_separator_y", far_refiner)
    image = Image.new("RGB", (120, 160), "white")
    settings = AppSettings(
        columns=1,
        manual_columns=True,
        manual_x=10,
        column_width=100,
        gutter=0,
        start_y=0,
        bottom_y=160,
        character_height=10,
        paddle_separator_search_ratio=0.30,
        paddle_refine_separator_y=True,
    )
    entries = [Entry("alpha", 10, 30), Entry("beta", 10, 70)]
    refined, stats = refine_existing_entries(image, entries, settings)

    assert len(refined) == len(entries) == stats["total"]
    assert [entry.word for entry in refined] == ["alpha", "beta"]
    assert stats["max_delta"] == 3
    assert all(abs(new.y - old.y) <= stats["max_delta"] for old, new in zip(entries, refined))


def test_custom_profile_name_persists_and_numbered_choices_keep_custom_last(tmp_path):
    path = tmp_path / "settings.json"
    AppSettings(dictionary_custom_profile_name="古汉语单字结构").to_json(path)
    reopened = AppSettings.from_json(path)
    assert reopened.dictionary_custom_profile_name == "古汉语单字结构"

    fake = SimpleNamespace(
        custom_profile_name_var=SimpleNamespace(get=lambda: "古汉语单字结构"),
    )
    labels = SettingsDialog._build_profile_choice_labels(fake)
    keys = list(labels.values())
    visible = list(labels.keys())
    assert keys[-1] == "custom"
    assert visible[-1].endswith("古汉语单字结构（自定义）")
    assert all(label.startswith(f"{index}. ") for index, label in enumerate(visible, start=1))


def test_secondary_windows_share_modern_shell_without_changing_review_window():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")

    settings_start = source.index("class SettingsDialog")
    settings_end = source.index("class ReviewWindow", settings_start)
    settings = source[settings_start:settings_end]
    assert '_build_modern_dialog_heading(' in settings
    assert '"设置中心"' in settings
    assert 'text="校验当前设置"' in settings
    assert 'command=self._close_validated' in settings
    assert 'text="保存并关闭"' not in settings
    assert 'text="环境中心"' in settings

    review_start = source.index("class ReviewWindow")
    review_end = source.index("class PictureCaptureApp", review_start)
    review = source[review_start:review_end]
    assert '_build_modern_dialog_heading(' not in review

    conflict_source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "dialogs" / "ocr_conflict.py"
    ).read_text(encoding="utf-8")
    conflict_start = conflict_source.index("class OCRConflictReviewDialog")
    conflict = conflict_source[conflict_start:]
    assert '"OCR 词头冲突复核"' in conflict
    assert 'text="所选候选"' in conflict
    assert 'text="关闭"' in conflict

    crop = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "dialogs" / "crop_settings.py"
    ).read_text(encoding="utf-8")
    assert '"通用切图规则"' in crop
    assert '"特殊页面范围"' in crop
    assert '主界面【六、页面列表】的 Section 列双击设置' in crop
    assert '"特殊页面覆盖"' not in crop
    assert 'text="保存并关闭"' in crop

    compare_source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "dialogs" / "old_new_comparison.py"
    ).read_text(encoding="utf-8")
    compare_start = compare_source.index("class OldNewComparisonWindow")
    compare = compare_source[compare_start:]
    assert '"新旧比较"' in compare
    assert 'text="比较来源"' in compare
    assert 'text="比较摘要"' in compare
    assert 'text="保存当前 PDIC 快照…"' in compare
    assert 'text="导出差异报告…"' in compare


def test_settings_center_uses_context_help_units_and_user_facing_modes():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("class SettingsDialog")
    end = text.index("class ReviewWindow", start)
    settings = text[start:end]
    schema = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "settings" / "schema.py"
    ).read_text(encoding="utf-8")
    help_source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "settings" / "help.py"
    ).read_text(encoding="utf-8")

    assert '"bottom_y", int' in schema
    assert '"bottom_y": "正文结束 Y"' in schema
    common_start = schema.index("COMMON_FIELDS = (")
    common_end = schema.index("\nNORMAL_COMMON_FIELDS", common_start)
    common_fields = schema[common_start:common_end]
    assert '"bottom_y"' not in common_fields
    assert '"columns": "正文栏数"' in schema
    assert '"manual_x": "第一栏左缘 X"' in schema
    assert '"start_y": "% 图高"' in schema
    assert '"manual_x": "% 图宽"' in schema
    assert '"column_width": "% 图宽"' in schema
    assert '"character_height": "% 图高"' in schema
    assert '"paddle_band_width_ratio": "%"' in schema
    assert '"paddle_left_tolerance": "% 单栏宽"' in schema
    assert '"analysis_left": "% 图宽"' in schema
    assert '"analysis_right": "% 图宽"' in schema
    assert '"paddle_header_search_height": "% 图高"' in schema
    assert '"paddle_separator_safety_px": "原图px"' in schema
    assert '"column_track_radius": "% 单栏宽"' in schema
    assert '"column_track_block_height": "% 正文高度"' in schema
    assert '"column_track_max_step": "% 分块高度"' in schema
    assert '"columns": (1, 12, 1)' in schema
    percent_float_fields = (
        "start_y", "manual_x", "column_width", "gutter", "body_indent",
        "character_height", "row_padding", "horizontal_tolerance",
        "dark_area_percent", "analysis_left", "analysis_right",
        "column_track_radius", "column_track_block_height", "column_track_max_step",
        "paddle_band_width_ratio", "paddle_left_tolerance",
        "paddle_separator_roi_width_ratio", "paddle_header_search_height",
        "right_ratio", "review_zoom_percent",
    )
    for name in percent_float_fields:
        assert f'"{name}", float' in schema, name
    assert "def _show_setting_help(" in settings
    assert 'text="设置说明"' in settings
    assert "程序取第 1 个捕获组作为原始词头" in schema
    assert "实际 POS 正则由 Profile 的 pos_labels 动态生成" in schema
    assert "可作为新词条起始证据" in schema
    assert "命中只增加一项结构证据，不会无条件把该行接受为词头" in schema
    assert 'text="ⓘ"' in settings
    assert 'panes = ttk.Panedwindow(host, orient="horizontal")' in settings
    assert 'panes.add(left, weight=3)' in settings
    assert 'panes.add(right, weight=2)' in settings
    assert 'panes.sashpos(0, int(width * 0.60))' in settings
    assert "def _bind_responsive_labels(" in settings
    assert "label_width = int(label.winfo_width())" in help_source
    assert "available = max(48, label_width - 12)" in help_source
    assert "_wrap_mixed_ui_text(" in help_source
    assert "label.configure(text=rendered, wraplength=0)" in help_source
    assert "label._pc_dynamic_textvariable = bool(textvariable)" in help_source
    assert "control.columnconfigure(0, weight=1)" in settings
    assert 'widget.grid(row=0, column=0, sticky="ew")' in settings
    assert "wraplength=0 if single_line_labels else 180" in settings
    assert 'justify="left"' in settings
    assert "self._settings_help_body_label = help_body" in settings
    assert 'style="PC.Settings.TNotebook"' in settings
    assert '"PC.Settings.TNotebook.Tab"' in settings
    assert 'padding=(13, 7)' in settings
    assert "self.transient(parent); self.grab_set()" not in settings
    assert "def select_tab(self, key: str | None)" in settings
    assert '(crop_tab, "切图")' in settings
    assert '"crop": crop_tab' in settings
    assert "def _build_crop_settings_tab(" in settings
    assert '"general_top_y"' in settings
    assert '"general_bottom_y"' in settings
    assert '"entry_left_padding_x"' in settings
    assert '"entry_right_padding_x"' in settings
    assert '"integrate_illustrations"' in settings
    assert '"polygon_margin"' in settings
    assert '"parallel_workers"' in settings
    assert "self._save_integrated_crop_settings()" in settings

    assert 'text="融合画线+OCR"' in settings
    assert 'text="OCR画线（默认）"' in settings
    assert 'text="普通画线（单独诊断）"' in settings
    assert 'value=DETECTION_LABELS["combined"]' in settings
    assert 'value=DETECTION_LABELS["left_edge"]' in settings
    assert 'value=DETECTION_LABELS["paddleocr"]' in settings

    assert 'text="校验当前设置"' in settings
    assert 'self.bind("<Escape>", lambda _event: self._close_validated())' in settings
    assert "✓ 已自动保存" in settings
    assert "⚠ 当前输入暂未保存" in settings

    # Every Settings Center field/check must have a real help entry; avoid
    # silently falling back to the generic "专家参数" text as the UI grows.
    from picture_capture.app import SettingsDialog
    field_names = {name for _label, name, _cast in SettingsDialog.FIELDS}
    assert field_names <= set(SettingsDialog.SETTING_HELP)
    visible_checks = (
        SettingsDialog.NORMAL_CHECKS
        + SettingsDialog.OCR_COMMON_CHECKS
        + SettingsDialog.OCR_ADVANCED_CHECKS
        + SettingsDialog.DISPLAY_STYLE_CHECKS
        + SettingsDialog.DISPLAY_CHECKS
    )
    check_names = {name for _label, name in visible_checks} | {"paddle_enable_lens"}
    assert check_names <= set(SettingsDialog.CHECK_HELP)
    for key in field_names:
        assert len(SettingsDialog.SETTING_HELP[key]) >= 40, key
    for key in check_names:
        assert len(SettingsDialog.CHECK_HELP[key]) >= 40, key
    for key in (
        "detection_method", "paddle_lens_mode", "ocr_engine",
        "headword_sort_mode", "headword_custom_order", "headword_custom_fold_accents",
    ):
        assert len(SettingsDialog.SETTING_HELP[key]) >= 60, key
    assert 'self._show_setting_help("paddle_lens_mode")' in settings
    assert 'self._show_setting_help("ocr_engine")' in settings
    assert 'self._show_setting_help("headword_sort_mode")' in settings



def test_settings_center_restores_inline_detailed_parameter_help():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    settings_start = text.index("class SettingsDialog")
    settings_end = text.index("class ", settings_start + len("class SettingsDialog"))
    settings = text[settings_start:settings_end]
    assert "inline_help = ttk.Label" in settings
    assert "text=self.SETTING_HELP.get(" in settings
    assert "check_help = ttk.Label" in settings
    assert "text=self.CHECK_HELP.get(" in settings
    assert '"analysis_left": "width"' in text
    assert '"analysis_right": "width"' in text
    assert '"paddle_header_search_height": "height"' in text
    assert "def _column_pixels_to_percent(" in text
    assert "def _column_percent_to_pixels(" in text

def test_settings_center_is_reused_without_blocking_main_workspace():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    start = source.index("    def open_settings(self, initial_tab:")
    end = source.index("\n    def open_project_profile(", start)
    open_settings = source[start:end]

    assert 'self.__dict__.get("_settings_dialog")' in open_settings
    assert "existing.select_tab(initial_tab)" in open_settings
    assert "existing.deiconify()" in open_settings
    assert "dialog = SettingsDialog(self, initial_tab=initial_tab)" in open_settings
    assert "self._settings_dialog = dialog" in open_settings


def test_common_layout_settings_show_packaged_context_diagrams():
    root = Path(__file__).resolve().parents[1]
    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = app_text.index("class SettingsDialog")
    end = app_text.index("class ReviewWindow", start)
    settings = app_text[start:end]
    schema = (root / "src" / "picture_capture" / "ui" / "settings" / "schema.py").read_text(encoding="utf-8")
    help_source = (root / "src" / "picture_capture" / "ui" / "settings" / "help.py").read_text(encoding="utf-8")

    assert '"columns": "layout_col_number.png"' in schema
    for field in (
        "start_y", "bottom_y", "manual_x", "column_width",
        "gutter", "character_height", "row_padding",
    ):
        assert f'"{field}": "layout_settings.png"' in schema
    assert "help_images=True" in settings
    assert "show_layout_image: bool = False" in settings
    assert '/ "data"' in help_source
    assert '/ "layout_example"' in help_source
    assert "Image.Resampling.LANCZOS" in help_source
    assert "ImageTk.PhotoImage(" in help_source
    assert "themed_display_image(rendered, dialog.parent.appearance_mode)" in help_source

    layout_dir = root / "src" / "picture_capture" / "data" / "layout_example"
    assert (layout_dir / "layout_col_number.png").is_file()
    assert (layout_dir / "layout_settings.png").is_file()

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"data/layout_example/*.png"' in pyproject


def test_project_toolbar_and_profile_scroll_layout_are_wired():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")

    project_bar_start = text.index("        project_row = ttk.Frame(self.project_action_bar")
    project_bar_end = text.index("        self.canvas = tk.Canvas(", project_bar_start)
    project_bar = text[project_bar_start:project_bar_end]
    expected = (
        '("项目中心", self.open_recent_project)',
        '("项目Profile", self.open_project_profile)',
        '("设置中心", self.open_settings)',
        '("帮助中心", self.show_help_dialog)',
    )
    positions = [project_bar.index(item) for item in expected]
    assert positions == sorted(positions)
    assert '("新建项目", self.open_project' not in project_bar
    assert "导出训练标记包" not in project_bar
    assert "保存参数" not in project_bar
    assert "使用指南" not in project_bar
    assert 'uniform="project-footer-columns"' in project_bar
    assert 'project_row.columnconfigure(col, weight=1, uniform="project-footer-columns")' in project_bar
    assert 'role="project"' in project_bar
    for tooltip in (
        "打开最近项目与项目管理；可从这里新建或切换词典项目。",
        "配置词典信息、阅读方向、页面模板和词头结构，并用代表页测试。",
        "按常用、OCR画线、普通画线、显示/校对、切图等任务调整项目参数。",
        "查看新版推荐流程、主界面说明、快捷操作与常见排错。",
    ):
        assert tooltip in project_bar
    assert 'text="图片后缀："' not in text
    assert "self.image_suffix_var" not in text

    suffix_choice_start = text.index("    def _choose_new_project_image_suffix(")
    suffix_choice_end = text.index("\n    def open_project(", suffix_choice_start)
    suffix_choice = text[suffix_choice_start:suffix_choice_end]
    assert "project_page_images(root)" in suffix_choice
    assert "if len(suffixes) == 1:" in suffix_choice
    assert "simpledialog.askstring(" in suffix_choice
    assert "if suffix in counts:" in suffix_choice

    open_start = text.index("    def open_project(self) -> None:")
    open_end = text.index("\n    def _load_project(", open_start)
    open_project = text[open_start:open_end]
    assert "if not existing_project:" in open_project
    assert "self._choose_new_project_image_suffix(root)" in open_project
    assert "if requested_suffix is None:" in open_project

    actions_start = text.index('            parent, "四、画线 / OCR / 插图 / 校对"')
    actions_end = text.index("        postproduction = self._section_frame(", actions_start)
    actions = text[actions_start:actions_end]
    assert '("设置中心", self.open_settings)' not in actions
    assert '("导出训练标记包", self.export_training_package)' not in actions

    post_start = text.index('        postproduction = self._section_frame(')
    post_end = text.index("        postproduction.columnconfigure(0, weight=1)", post_start)
    post = text[post_start:post_end]
    assert '("切图设置", self.open_crop_settings)' not in post
    assert '("词条切图", self.split_entries_selected_scope)' in post
    assert '("插图切图", self.split_illustrations_selected_scope)' in post
    assert post.rindex('("导出训练标记包", self.export_training_package)') > post.index('("PicDic制作", self.build_picdic)')
    for tooltip_key in (
        '"词条切图":', '"插图切图":', '"项目详情":',
        '"导出PicDic索引":', '"PicDic制作":', '"导出训练标记包":',
    ):
        assert tooltip_key in post

    profile_start = text.index("    def _build_profile_tab(")
    profile_end = text.index("    def _build_profile_choice_labels(", profile_start)
    profile = text[profile_start:profile_end]
    assert "self.profile_canvas = profile_canvas" in profile
    assert "profile_scrollbar" in profile
    assert 'text="自定义结构名称："' in profile
    assert "ProjectProfileWizard(self, new_project=new_project)" in text


def test_bottom_important_actions_follow_scheme_a_groups():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _footer_action_button(")
    end = text.index("    def _section_frame(", start)
    helper = text[start:end]
    assert '"project": (colors["success"], colors["success_hover"], "#ffffff")' in helper
    assert '"config": (colors["success"], colors["success_hover"], "#ffffff")' in helper
    assert 'border = colors["button_border"]' in helper
    assert '"profile":' not in helper
    assert '"settings":' not in helper
    assert '"save":' not in helper
    assert '"help":' not in helper
    assert 'highlightbackground=border' in helper
    assert 'highlightthickness=1' in helper

    project_bar_start = text.index("        project_row = ttk.Frame(self.project_action_bar")
    project_bar_end = text.index("        self.canvas = tk.Canvas(", project_bar_start)
    project_bar = text[project_bar_start:project_bar_end]
    for label, command in (
        ("项目中心", "self.open_recent_project"),
        ("项目Profile", "self.open_project_profile"),
        ("设置中心", "self.open_settings"),
        ("帮助中心", "self.show_help_dialog"),
    ):
        assert f'("{label}", {command})' in project_bar
    assert project_bar.count('role="project"') == 1
    assert "导出训练标记包" not in project_bar
    assert "保存参数" not in project_bar


def test_crop_settings_entry_redirects_to_settings_center_tab():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def open_crop_settings(self) -> None:")
    end = text.index("\n    def ", start + 10)
    method = text[start:end]
    assert 'self.open_settings(initial_tab="crop")' in method
    assert "CropSettingsDialog(self, indices)" not in method


def test_mixed_ui_wrap_collapses_hard_breaks_and_keeps_latin_words():
    from picture_capture.app import _normalize_ui_paragraphs, _wrap_mixed_ui_text

    assert _normalize_ui_paragraphs("页面\n模板\n\n作用：测试") == "页面模板\n\n作用：测试"
    wrapped = _wrap_mixed_ui_text(
        "先用代表页证明“版面 + Profile + OCR”组合可靠，再扩大页面范围。",
        lambda value: len(value) * 10,
        140,
    )
    assert "Profi\nle" not in wrapped
    assert "O\nCR" not in wrapped
    assert "\n" in wrapped



def test_mixed_ui_wrap_measures_tokens_incrementally_not_growing_prefixes():
    from picture_capture.app import _wrap_mixed_ui_text

    calls: list[str] = []

    def measure(value: str) -> int:
        calls.append(value)
        return len(value) * 10

    wrapped = _wrap_mixed_ui_text("测" * 240, measure, 120)
    assert "\n" in wrapped
    # Repeated CJK characters should be measured once from the cache rather
    # than measuring 240 successively longer prefixes through Tk.
    assert len(calls) <= 4
    assert max(map(len, calls)) <= 1


def test_usage_guide_is_modern_task_oriented_and_centered():
    root = Path(__file__).resolve().parents[1]
    app_source = root / "src" / "picture_capture" / "app.py"
    guide_source = root / "src" / "picture_capture" / "ui" / "dialogs" / "usage_guide.py"
    text = app_source.read_text(encoding="utf-8")
    guide_text = guide_source.read_text(encoding="utf-8")

    guide_start = guide_text.index("class UsageGuideWindow(tk.Toplevel):")
    guide_end = len(guide_text)
    guide = guide_text[guide_start:guide_end]

    assert '"快速开始"' in guide
    assert 'self.title("Picture Capture · 帮助中心")' in guide
    assert "work_x, work_y, work_w, work_h = screen_work_area(self)" in guide
    assert "x = work_x + max(0, (work_w - width) // 2)" in guide
    assert "y = work_y + max(0, (work_h - height) // 2)" in guide
    assert 'self.geometry(f"{width}x{height}+{x}+{y}")' in guide
    assert '"画线与 OCR"' in guide
    assert '"校对与词表"' in guide
    assert '"插图与切图"' in guide
    assert '"后期制作"' in guide
    assert '"导航与排错"' in guide
    assert 'self.search_var = tk.StringVar()' in guide
    assert '"推荐原则"' in guide
    assert '"项目Profile"' in guide
    assert '"版面与Section"' in guide
    assert "双击页面列表的 Section 单元格" in guide
    assert "重新简体化" in guide
    assert "重点筛选校对" in guide
    assert '"检测版面参数"' in guide
    assert '"环境中心"' in guide
    assert '"设置中心"' in guide
    assert "OCR画线是默认方式" in guide
    assert "普通画线、仅OCR和融合画线+OCR" in guide
    assert "默认先用 OCR画线验证代表页" in guide
    assert "sidebar_hint_text =" in guide
    assert "_wrap_mixed_ui_text(" in guide
    assert "wraplength=158" not in guide
    assert 'header.bind("<Configure>", resize_header, add="+")' in guide
    assert "def _register_wrapped_label(" in guide
    assert "self.after_idle(self._refresh_wrapped_labels)" in guide
    assert "_wrap_mixed_ui_text(" in guide
    assert "wraplength=660" not in guide
    assert "wraplength=620" not in guide
    assert "新建项目】或【已有项目" not in guide
    assert "一、普通版面参数" not in guide
    assert "所选页面 ≥2 时，数值字段使用**稳健中位数**" not in guide
    assert "数值参数采用稳健中位数" in guide
    from picture_capture.app import UsageGuideWindow
    for _key, _title, subtitle, cards in UsageGuideWindow.PAGES:
        assert "\n" not in subtitle
        for _badge, card_title, body in cards:
            assert "\n" not in card_title
            assert "\n" not in body
    assert 'self.bind("<Escape>", lambda _event: self.destroy())' in guide

    show_start = text.index("    def show_help_dialog(self) -> None:")
    show_end = text.index("    @staticmethod\n    def _distribution_version", show_start)
    show = text[show_start:show_end]
    assert "UsageGuideWindow(self)" in show
    assert "_usage_guide_window" in show
    assert "messagebox.showinfo" not in show
    assert "show_help_popup" not in text
    assert "OCR_USAGE_HELP" not in text
    assert "查看新版推荐流程、主界面说明、快捷操作与常见排错。" in text


def test_main_workspace_modern_styles_are_scoped_and_dense():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")

    styles_start = text.index("    def _configure_main_workspace_styles(")
    styles_end = text.index("    def _sidebar_action_button(", styles_start)
    styles = text[styles_start:styles_end]
    assert "theme_use(" not in styles
    assert '"PC.Section.TLabelframe"' in styles
    assert '"PC.Treeview"' in styles
    assert '"PC.Footer.TFrame"' in styles

    ui_start = text.index("    def _build_ui(self) -> None:")
    ui_end = text.index("    def _pointer_over_sidebar(", ui_start)
    ui = text[ui_start:ui_end]
    assert 'style="PC.Treeview"' in ui
    assert 'style="PC.Footer.TFrame"' in ui
    assert '"一、版面参数"' in text
    assert 'add_field(normal, 0, 0, "正文栏数：", "columns", int)' in text
    assert 'add_field(normal, 0, 0, "分栏数：", "columns", int)' not in text
    assert '"二、显示设置"' in text
    assert '"三、融合 / OCR画线参数"' in text
    assert text.index('"二、显示设置"') < text.index('"三、融合 / OCR画线参数"')
    assert 'text="普通画线设置…"' in text
    assert 'text="显示标尺"' in text
    assert '"ruler_color": tk.StringVar(value=self.settings.ruler_color)' in text
    assert 'command=lambda: self._apply_overlay_visibility_toggle("show_rulers", ruler_var)' in text
    assert 'ttk.Separator(size_row, orient="vertical")' in ui
    assert 'relief="sunken"' not in ui
    assert 'relief="ridge"' not in ui

    actions_start = text.index('            parent, "四、画线 / OCR / 插图 / 校对"')
    actions_end = text.index("        postproduction = self._section_frame(", actions_start)
    actions = text[actions_start:actions_end]
    assert 'self._sidebar_action_button(row, text, command, role=role)' in actions
    assert '"primary" if text == "OCR画线(默认)"' in actions
    assert '("普通画线", self.run_normal_draw_action)' in actions
    assert '("仅OCR", self.ocr_ordinary_lines_text_selected_scope)' in actions
    assert '("融合画线+OCR", self.run_combined_draw_action)' in actions
    assert '("OCR画线(默认)", self.run_ocr_draw_action)' in actions
    assert actions.index('("普通画线", self.run_normal_draw_action)') < actions.index('("仅OCR", self.ocr_ordinary_lines_text_selected_scope)')
    assert actions.index('("仅OCR", self.ocr_ordinary_lines_text_selected_scope)') < actions.index('("融合画线+OCR", self.run_combined_draw_action)')
    assert actions.index('("融合画线+OCR", self.run_combined_draw_action)') < actions.index('("OCR画线(默认)", self.run_ocr_draw_action)')
    assert '("填充词条", self.fill_existing_headwords)' in actions
    assert '("修复排序", self.repair_pdic_order_selected_scope)' in actions
    for tooltip_key in (
        '"普通画线":', '"仅OCR":', '"融合画线+OCR":', '"OCR画线(默认)":', '"清除画线":', '"清除文本":', '"精修画线":', '"新旧比较":',
        '"词条校对":', '"填充词条":', '"备份PDIC":', '"恢复PDIC":',
        '"插图识别":', '"编辑插图":', '"压缩OCR缓存":', '"保存当前页":',
    ):
        assert tooltip_key in actions
    assert '("恢复PDIC", self.restore_from_pdic_backup)' in actions
    assert '("压缩OCR缓存", self.cleanup_paddleocr_temp_selected_scope)' in actions
    assert actions.index('("压缩OCR缓存", self.cleanup_paddleocr_temp_selected_scope)') < actions.index('("保存当前页", self.save_current_page)')
    assert '"success" if text == "保存当前页"' in actions
    assert '"primary" if text == "词条校对"' in actions
    assert '"danger_soft"' not in actions
    assert '"refine_soft"' not in actions
    assert '"compare_soft"' not in actions
    assert '("新旧比较", self.compare_old_new_selected_scope), ("词条校对", self.open_review)' in actions
    assert '"text": "#000000"' in styles
    assert '"primary": "#4F7CAC"' in styles
    assert '"primary_hover": "#416A94"' in styles
    assert '"success": "#69A875"' in styles
    assert '"success_hover": "#588F64"' in styles
    assert '"review_soft"' not in styles
    assert '"button_border": "#d3d8df"' in styles

    button_start = text.index("    def _sidebar_action_button(")
    button_end = text.index("    def _section_frame(", button_start)
    button = text[button_start:button_end]
    assert 'if role == "neutral":' in button
    assert 'return ttk.Button(' in button
    assert 'style="PC.Compact.TButton"' in button
    assert 'border = colors["button_border"]' in button
    assert 'relief="flat"' in button
    assert "bd=0" in button
    assert "highlightthickness=1" in button
    assert "highlightbackground=border" in button
    assert "highlightcolor=border" in button
    assert '"PC.EditActive.TButton"' in styles


def test_new_project_sidebar_defaults_do_not_overwrite_existing_session_preferences():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")

    startup = text[
        text.index("        self.section_expanded = {"):
        text.index("        self._collapsible_sections:", text.index("        self.section_expanded = {"))
    ]
    assert "sidebar_section_defaults_version" not in startup
    assert "SIDEBAR_SECTION_DEFAULTS_VERSION" not in text
    assert "if key in stored_sections:" in startup

    start = text.index("    def _apply_new_project_sidebar_defaults(self) -> None:")
    end = text.index("    @staticmethod\n    def _default_session_state_path", start)
    method = text[start:end]
    for expected in (
        '"normal": True', '"aux": False', '"ocr": False',
        '"actions": False', '"postproduction": False', '"pages": True',
    ):
        assert expected in method
    assert "persist=False" in method
    assert "if launch_profile_setup:" in text
    assert "self._apply_new_project_sidebar_defaults()" in text


def test_binary_preview_and_font_scaling_are_display_only():
    source = Image.new("RGB", (2, 1)); source.putdata([(20, 20, 20), (240, 200, 160)])
    before = source.tobytes()
    preview = binary_preview_image(source)
    assert source.tobytes() == before and source.mode == "RGB"
    assert all(color in {(0, 0, 0), (255, 255, 255)} for _count, color in preview.getcolors())
    settings = AppSettings(main_entry_font_size=32, main_entry_follow_zoom=True)
    assert effective_main_overlay_font_size(1400, 1, settings) == 32
    assert effective_main_overlay_font_size(2800, .5, settings) == 32
    assert effective_main_overlay_font_size(4200, 1 / 3, settings) == 32


def test_vertical_overlay_anchor_uses_canonical_offset():
    # x_ratio is applied in canonical space before the rotated widget is placed.
    editor = transformed_entry_anchor(
        LayoutTransform("rotate_ccw90"), 100, 200, 600, .5, (1400, 2200), .5,
    )
    assert editor == (599.5, 200)
    assert VerticalWordText._entry_index(0) == "1.0"
    assert VerticalWordText._entry_index("end") == "end-1c"


def test_vertical_editor_border_touches_marker_stroke():
    # A 2 px marker paints 1 px to either side of its centreline, so the
    # editor edge should be exactly 1 px away from the centreline.
    assert vertical_marker_contact_gap(2) == 1
    assert vertical_marker_contact_gap(3) == 2
    assert vertical_marker_contact_gap(4) == 2

    rl_box, *_ = vertical_overlay_layout(
        600, 200, editor_width=28, editor_height=180,
        writing_mode="vertical-rl", gap=vertical_marker_contact_gap(2),
    )
    lr_box, *_ = vertical_overlay_layout(
        600, 200, editor_width=28, editor_height=180,
        writing_mode="vertical-lr", gap=vertical_marker_contact_gap(2),
    )
    assert rl_box[2] == 599
    assert lr_box[0] == 601


def test_vertical_entry_boxes_have_fixed_length_and_mirror_marker_side():
    # Real vertical Text widgets use the same fixed requested size for every word.
    rl_box, rl_popup, rl_anchor, rl_index, rl_index_anchor = vertical_overlay_layout(
        600, 200, editor_width=28, editor_height=180, writing_mode="vertical-rl", gap=4,
    )
    lr_box, lr_popup, lr_anchor, lr_index, lr_index_anchor = vertical_overlay_layout(
        600, 200, editor_width=28, editor_height=180, writing_mode="vertical-lr", gap=4,
    )

    assert rl_box == (568, 200, 596, 380)
    assert lr_box == (604, 200, 632, 380)
    assert rl_box[2] < 600 < lr_box[0]
    assert (rl_box[3] - rl_box[1]) == (lr_box[3] - lr_box[1]) == 180
    assert (rl_box[2] - rl_box[0]) == (lr_box[2] - lr_box[0]) == 28
    assert rl_popup == (596.0, 200.0) and rl_anchor == "ne"
    assert lr_popup == (604.0, 200.0) and lr_anchor == "nw"
    assert rl_index == (565.0, 200.0) and rl_index_anchor == "ne"
    assert lr_index == (635.0, 200.0) and lr_index_anchor == "nw"


def test_vertical_ocr_menu_follows_vertical_writing_side():
    assert vertical_ocr_menu_layout((568, 200, 596, 380), 80, "vertical-rl", 1000) == (
        565.0, 200.0, "ne",
    )
    assert vertical_ocr_menu_layout((604, 200, 632, 380), 80, "vertical-lr", 1000) == (
        635.0, 200.0, "nw",
    )


def test_vertical_proxy_reuses_editor_membership_and_confidence_style():
    fake = SimpleNamespace(
        _project_words={"known"}, settings=AppSettings(main_entry_default_color="#ffffff"),
        _main_ocr_review_option_enabled=lambda _name: True,
        _confidence_bg=lambda confidence: "#c8e6c9" if confidence == .97 else "#ffcdd2",
    )
    known = PictureCaptureApp._entry_overlay_style(fake, Entry("known", 0, 0, confidence=.97))
    missing = PictureCaptureApp._entry_overlay_style(fake, Entry("missing", 0, 0, confidence=.5))
    assert known == ("#c8e6c9", "#b0b0b0", 1)
    assert missing == ("#ffcdd2", "#d32f2f", 2)

def test_main_entry_border_is_light_gray_when_wordslist_file_is_absent(tmp_path):
    fake = SimpleNamespace(
        project=SimpleNamespace(root=tmp_path),
        _project_words=set(),
        settings=AppSettings(main_entry_default_color="#ffffff", wordslist_path="missing_wordslist.txt"),
        _main_ocr_review_option_enabled=lambda _name: False,
        _confidence_bg=lambda _confidence: "#eeeeee",
    )
    style = PictureCaptureApp._entry_overlay_style(
        fake, Entry("anything", 0, 0, confidence=None)
    )
    assert style == ("#ffffff", "#c7c7c7", 1)


def test_main_entry_sequence_numbers_use_page_uniform_width():
    fmt = PictureCaptureApp._entry_sequence_text
    assert [fmt(i, 9) for i in (0, 8)] == ["0", "8"]
    assert [fmt(i, 10) for i in (0, 9)] == ["00", "09"]
    assert [fmt(i, 99) for i in (0, 98)] == ["00", "98"]
    assert [fmt(i, 100) for i in (0, 99)] == ["000", "099"]


def test_main_entry_sequence_label_uses_light_gray_black_style():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    draw_start = text.index("        index_label = tk.Label(")
    draw_end = text.index("        index_label._pc_skip_classic_appearance", draw_start)
    block = text[draw_start:draw_end]
    assert "text=self._entry_sequence_text(index, len(self.entries))" in block
    assert 'bg="#e6e6e6"' in block
    assert 'fg="#000000"' in block


def test_entry_sequence_label_sits_before_editor_in_reading_direction():
    assert entry_index_label_layout(
        500, 150, 180, 24, horizontal=True, rtl=False,
    ) == (500.0, 150.0, "ne")
    assert entry_index_label_layout(
        500, 150, 180, 24, horizontal=True, rtl=True,
    ) == (500.0, 150.0, "nw")
    assert entry_index_label_layout(
        0, 0, 28, 180, horizontal=False, vertical_box=(568, 200, 596, 380),
    ) == (582.0, 200.0, "s")


def test_horizontal_ltr_rtl_are_mirror_equivalent():
    args = dict(canonical_x=100, canonical_y=300, column_width=600,
                source_size=(1400, 2200), view_scale=.5)
    ltr_low = horizontal_overlay_layout(LayoutTransform("identity"), x_ratio=.2, rtl=False, **args)
    ltr_high = horizontal_overlay_layout(LayoutTransform("identity"), x_ratio=.8, rtl=False, **args)
    rtl_low = horizontal_overlay_layout(LayoutTransform("mirror_x"), x_ratio=.2, rtl=True, **args)
    rtl_high = horizontal_overlay_layout(LayoutTransform("mirror_x"), x_ratio=.8, rtl=True, **args)
    assert ltr_low[0][1] == ltr_high[0][1] == rtl_low[0][1] == rtl_high[0][1] == 150
    assert ltr_high[0][0] > ltr_low[0][0]
    assert rtl_high[0][0] < rtl_low[0][0]
    assert ltr_low[1] == "nw" and rtl_low[1] == "ne"
    assert ltr_low[2][1] == rtl_low[2][1] == 150
    assert ltr_low[3] == "nw" and rtl_low[3] == "ne"
    assert horizontal_ocr_menu_layout(500, 150, 180, rtl=False) == (683, 150, "nw")
    assert horizontal_ocr_menu_layout(500, 150, 180, rtl=True) == (317, 150, "ne")


def test_horizontal_ui_uses_shared_layout_and_keeps_arabic_semantics():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("        horizontal = self.settings.layout_writing_mode == \"horizontal-tb\"")
    end = text.index("        vertical_box: tuple[int, int, int, int] | None = None", start)
    rtl_branch = text[start:end]
    assert "horizontal_overlay_layout(" in rtl_branch
    assert "line_box(" not in rtl_branch
    assert "if rtl:" in rtl_branch
    assert 'editor.configure(justify="right")' in rtl_branch


def test_review_edits_remain_bound_to_entries_after_main_line_insert():
    first, second = Entry("first", 10, 20), Entry("second", 10, 40)
    inserted = Entry("", 10, 30)
    fake = SimpleNamespace(
        row_entries=[first, second], vars=[SimpleNamespace(get=lambda: "FIRST"), SimpleNamespace(get=lambda: "SECOND")],
        parent=SimpleNamespace(entries=[first, inserted, second]),
        _capture_simplified_edits=lambda _stem: None, _rendered_page_stem="page",
    )
    fake._bound_row_entries = lambda: fake.row_entries
    ReviewWindow._commit_edits(fake)
    assert (first.word, inserted.word, second.word) == ("FIRST", "", "SECOND")


def test_latin_pronunciation_pos_and_cjk_rejection():
    profile = load_dictionary_profile(preset="latin_pos_classic", language="eng")
    settings = AppSettings(ocr_language="eng")
    for text in ("ab·a·cus ['æbəkəs] n. frame", "a·ban·don /ə'bændən/ v.t. leave"):
        parsed = parse_headword_text(text, settings, profile=profile)
        assert parsed is not None and parsed.has_pos
    assert parse_headword_text("中文正文", settings, profile=profile) is None


def test_script_neutral_default_is_narrowed_only_for_latin_profiles():
    assert r"[^\W\d_]" in AppSettings().paddle_headword_regex
    arabic = load_dictionary_profile(preset="arabic_rtl_bilingual_2col", language="ara")
    parsed_arabic = parse_headword_text("كتاب", AppSettings(ocr_language="ara"), profile=arabic)
    assert parsed_arabic is not None and parsed_arabic.normalized == "كتاب"
    japanese = load_dictionary_profile(preset="jpn_numbered_headword_2col", language="jpn")
    parsed_kana = parse_headword_text("10. かな", AppSettings(ocr_language="jpn"), profile=japanese)
    assert parsed_kana is not None and parsed_kana.normalized == "かな"


def test_settings_profile_is_authoritative_for_ui_and_ocr_resolution(tmp_path):
    root = tmp_path / "project"
    _project(root, dictionary_profile_id="latin_pos_classic", ocr_language="eng")
    sidecar = profile_path(root)
    sidecar.write_text(
        '{"format":"dictionary-profile-v2","preset":"cjk_bracket_display","language":"chi_sim"}',
        encoding="utf-8",
    )
    settings = ProjectState.open(root).settings
    # SettingsDialog and OCR both call this resolver; loading with its result
    # must ignore the disagreeing sidecar preset.
    selected = effective_project_profile_id(settings, sidecar)
    assert selected == "latin_pos_classic"
    ocr_profile = load_dictionary_profile(sidecar, preset=selected, language=settings.ocr_language)
    assert ocr_profile.key == "latin_pos_classic"
    assert parse_headword_text("中文正文", settings, profile=ocr_profile) is None


def test_cjk_pinyin_regex_handles_stars_and_apostrophes_without_ambiguity():
    profile = load_dictionary_profile(preset="cjk_large_head_pinyin_2col", language="chi_sim")
    settings = AppSettings(ocr_language="chi_sim")
    for text, expected in (("案* ān", "案"), ("暗* àn", "暗"), ("谙 ān", "谙"), ("西 xī'ān", "西")):
        assert parse_headword_text(text, settings, profile=profile).normalized == expected


def test_multiline_pronunciation_keeps_first_line_geometry():
    settings = AppSettings(ocr_language="eng")
    profile = load_dictionary_profile(preset="latin_pos_classic", language="eng")
    patterns = _compile_patterns(settings, profile)
    first = OCRLine("a·ban·don [ə'bændən;", .9, (3, 10, 180, 30), [])
    second = OCRLine("ə'bændən] v.t. leave", .9, (8, 31, 210, 50), [])
    repaired = _repair_multiline_headword_state_machine([first, second], settings, 20, patterns)
    assert repaired[0].box == first.box
    parsed = parse_headword_text(repaired[0].text, settings, patterns, profile)
    assert parsed is not None and parsed.has_pos


def test_cjk_features_gate_parsers_and_pinyin_is_structural():
    settings = AppSettings(ocr_language="chi_sim")
    pinyin = load_dictionary_profile(preset="cjk_large_head_pinyin_2col", language="chi_sim")
    parsed = parse_headword_text("案* ān", settings, profile=pinyin)
    assert parsed is not None and parsed.normalized == "案"
    disabled = replace(load_dictionary_profile(preset="cjk_bracket_display", language="chi_sim"), headword_features=())
    assert parse_headword_text("【案件】", settings, profile=disabled) is None
    enabled = load_dictionary_profile(preset="cjk_bracket_large_head_2col", language="chi_sim")
    assert parse_headword_text("【案件】", settings, profile=enabled).normalized == "案件"


def test_ocr_resize_coordinates_round_trip():
    class Result:
        json = {"res": {"rec_texts": ["word"], "rec_scores": [.9], "rec_boxes": [[100, 200, 300, 400]]}}
    class Engine:
        def predict(self, image, **kwargs):
            assert image.shape[:2] == (1400, 700)
            return [Result()]
    band = Image.new("RGB", (1400, 2800), "white")
    prepared, scale = prepare_ocr_band(band, max_long_side=1400)
    assert prepared.size == (700, 1400) and scale == .5
    records = run_paddle_band(band, AppSettings(paddle_max_input_side=1400), Engine())
    assert records == [OCRRecord("word", .9, (200, 400, 600, 800))]





def test_peer_typography_marks_only_boundary_supported_soft_rejects():
    diagnostics = []
    for index in range(4):
        diagnostics.append({
            "accepted": True,
            "confidence": 0.96,
            "normalized_headword": f"head{index}",
            "reject_reason": "",
            "features": {
                "at_left": True,
                "below_header": True,
                "height_ratio": 1.18 + index * 0.01,
                "boldness_ratio": 1.31 + index * 0.01,
                "preceding_gap": 18 + index,
                "forced_accept": False,
                "marker_noise": False,
                "looks_like_continuation": False,
            },
            "parser_trace": [],
            "bug_types": [],
        })
    candidate = {
        "accepted": False,
        "confidence": 0.87,
        "normalized_headword": "borderline",
        "reject_reason": "missing_pos_inflection_descriptor_or_symbol",
        "features": {
            "at_left": True,
            "below_header": True,
            "image_boundary_supported": True,
            "height_ratio": 1.19,
            "boldness_ratio": 1.32,
            "preceding_gap": 19,
        },
        "parser_trace": [],
        "bug_types": [],
    }
    diagnostics.append(candidate)

    matched = paddle_headwords._annotate_peer_typography_matches(diagnostics)

    assert matched == 1
    assert candidate["features"]["peer_typography_match"] is True
    assert candidate["features"]["peer_typography_votes"] >= 2
    assert candidate["features"]["peer_typography_anchor_count"] == 4
    assert "peer_typography_match" in candidate["parser_trace"]
    assert "PEER_TYPOGRAPHY_MATCH" in candidate["bug_types"]


def test_peer_typography_plus_image_boundary_can_rescue_single_engine_soft_reject():
    candidate = {
        "source_x": 20,
        "source_y": 100,
        "_axis_v": 100,
        "_coarse_axis_v": 100,
        "_anchor_axis_v": 100,
        "normalized_headword": "borderline",
        "confidence": 0.86,
        "accepted": False,
        "score": 2.0,
        "reject_reason": "missing_pos_inflection_descriptor_or_symbol",
        "features": {
            "at_left": True,
            "peer_typography_match": True,
            "peer_typography_votes": 3,
        },
        "image_boundary_match": {"strength": 0.9, "y": 100},
        "box": [0, 100, 90, 122],
    }
    pair = paddle_headwords._make_ocr_pair(candidate, None)
    item = paddle_headwords._arbitrate_pair(
        pair, 0, 20, AppSettings(), geometry=None,
    )
    assert item["selected"] is True
    assert item["decision_reason"] == "multi_evidence_visual_boundary_rescue"
    assert "MULTI_EVIDENCE_RESCUE" in item["issue_types"]


def test_peer_typography_does_not_mark_hard_negative_candidate():
    diagnostics = [
        {
            "accepted": True,
            "confidence": 0.97,
            "normalized_headword": f"h{i}",
            "features": {
                "at_left": True, "below_header": True,
                "height_ratio": 1.2, "boldness_ratio": 1.3,
                "preceding_gap": 20,
            },
        }
        for i in range(4)
    ]
    candidate = {
        "accepted": False,
        "confidence": 0.99,
        "normalized_headword": "body",
        "reject_reason": "continuation_fragment",
        "features": {
            "at_left": True,
            "below_header": True,
            "image_boundary_supported": True,
            "height_ratio": 1.2,
            "boldness_ratio": 1.3,
            "preceding_gap": 20,
            "looks_like_continuation": True,
        },
        "parser_trace": [],
        "bug_types": [],
    }
    diagnostics.append(candidate)
    matched = paddle_headwords._annotate_peer_typography_matches(diagnostics)
    assert matched == 0
    assert not candidate["features"].get("peer_typography_match")


def test_engine_quality_uses_independent_image_boundary_to_break_close_tie():
    base = {
        "source_x": 20,
        "source_y": 100,
        "_axis_v": 100,
        "_coarse_axis_v": 100,
        "_anchor_axis_v": 100,
        "normalized_headword": "annual",
        "confidence": 0.92,
        "accepted": True,
        "score": 5.0,
        "reject_reason": "",
        "features": {"at_left": True, "structural_cue": True},
        "box": [0, 100, 90, 122],
    }
    paddle = dict(base)
    paddle["image_boundary_match"] = {"strength": 1.0, "y": 100}
    tesseract = dict(base)
    tesseract["image_boundary_match"] = None

    pair = paddle_headwords._make_ocr_pair(paddle, tesseract)
    item = paddle_headwords._arbitrate_pair(
        pair, 0, 20, AppSettings(), geometry=None,
    )
    assert item["selected"] is True
    assert item["final_engine"] == "paddle"
    assert item["decision_reason"] == "dual_agree_higher_quality"


def test_dual_ocr_consensus_plus_image_boundary_rescues_missing_structure():
    common = {
        "source_x": 20,
        "source_y": 100,
        "_axis_v": 100,
        "_coarse_axis_v": 100,
        "_anchor_axis_v": 100,
        "normalized_headword": "annual",
        "confidence": 0.95,
        "accepted": False,
        "score": 3.0,
        "reject_reason": "missing_pos_inflection_descriptor_or_symbol",
        "features": {"at_left": True},
        "image_boundary_match": {"strength": 0.9, "y": 100},
        "box": [0, 100, 90, 122],
    }
    pair = paddle_headwords._make_ocr_pair(dict(common), dict(common))
    item = paddle_headwords._arbitrate_pair(
        pair, 0, 20, AppSettings(), geometry=None,
    )
    assert item["selected"] is True
    assert item["decision_reason"] == "dual_consensus_boundary_rescue"
    assert "DUAL_BOUNDARY_RESCUE" in item["issue_types"]
    assert item["needs_review"] is True


def test_single_engine_explicit_visual_plus_boundary_rescues_soft_parser_reject():
    candidate = {
        "source_x": 20,
        "source_y": 100,
        "_axis_v": 100,
        "_coarse_axis_v": 100,
        "_anchor_axis_v": 100,
        "normalized_headword": "○词",
        "confidence": 0.86,
        "accepted": False,
        "score": 2.0,
        "reject_reason": "missing_pos_inflection_descriptor_or_symbol",
        "features": {
            "at_left": True,
            "visual_entry_marker": True,
            "configured_marker_evidence": True,
        },
        "image_boundary_match": {"strength": 0.8, "y": 100},
        "box": [0, 100, 80, 124],
    }
    pair = paddle_headwords._make_ocr_pair(candidate, None)
    item = paddle_headwords._arbitrate_pair(
        pair, 0, 20, AppSettings(), geometry=None,
    )
    assert item["selected"] is True
    assert item["decision_reason"] == "multi_evidence_visual_boundary_rescue"
    assert "MULTI_EVIDENCE_RESCUE" in item["issue_types"]


def test_multi_evidence_rescue_never_overrides_hard_negative_semantics():
    candidate = {
        "source_x": 20,
        "source_y": 100,
        "_axis_v": 100,
        "_coarse_axis_v": 100,
        "_anchor_axis_v": 100,
        "normalized_headword": "body",
        "confidence": 0.99,
        "accepted": False,
        "score": 8.0,
        "reject_reason": "continuation_fragment",
        "features": {
            "at_left": True,
            "visual_entry_marker": True,
            "looks_like_continuation": True,
        },
        "image_boundary_match": {"strength": 1.0, "y": 100},
        "box": [0, 100, 80, 124],
    }
    pair = paddle_headwords._make_ocr_pair(candidate, None)
    item = paddle_headwords._arbitrate_pair(
        pair, 0, 20, AppSettings(), geometry=None,
    )
    assert item["selected"] is False

def test_raw_ocr_cache_signature_tracks_pixels_and_inference_settings():
    class PathStub:
        points = [(10, 20), (10, 200)]

    geometry = SimpleNamespace(
        transform=SimpleNamespace(kind="identity"),
        column_paths=[PathStub()],
        top=20,
        bottom=200,
    )
    image = Image.new("RGB", (64, 64), "white")
    base = AppSettings(
        paddle_preprocessing="original",
        paddle_max_input_side=2800,
        paddle_use_textline_orientation=False,
    )
    sig = _cache_signature(image, geometry, base)
    assert _cache_signature(image, geometry, replace(base, paddle_preprocessing="binary")) != sig
    assert _cache_signature(image, geometry, replace(base, paddle_max_input_side=1400)) != sig
    assert _cache_signature(image, geometry, replace(base, paddle_use_textline_orientation=True)) != sig
    assert _cache_signature(image, geometry, replace(base, column_width=base.column_width + 17)) != sig
    moved_body = SimpleNamespace(
        transform=geometry.transform,
        column_paths=geometry.column_paths,
        top=30,
        bottom=200,
    )
    assert _cache_signature(image, moved_body, base) != sig

    changed = image.copy()
    changed.putpixel((32, 32), (0, 0, 0))
    assert _cache_signature(changed, geometry, base) != sig

    # Candidate/parser-only settings deliberately do not invalidate raw OCR.
    assert _cache_signature(image, geometry, replace(base, paddle_min_candidate_score=9.0)) == sig
    assert _cache_signature(image, geometry, replace(base, paddle_headword_regex=r"^foo")) == sig


def test_decimal_percentage_settings_preserve_runtime_precision(tmp_path):
    path = tmp_path / "settings.json"
    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=200,
        gutter=0,
        start_y=0,
        bottom_y=200,
        paddle_band_left_margin=10,
        paddle_band_width_ratio=60.5,
        paddle_separator_roi_width_ratio=60.5,
        review_zoom_percent=88.5,
        follow_column_deformation=False,
    )
    settings.to_json(path)
    restored = AppSettings.from_json(path)
    assert restored.paddle_band_width_ratio == 60.5
    assert restored.paddle_separator_roi_width_ratio == 60.5
    assert restored.review_zoom_percent == 88.5

    image = Image.new("RGB", (400, 200), "white")
    geometry = derive_geometry(image, restored)
    band, _, left_margin = unwrap_column_band(image, geometry, 0, restored)
    assert left_margin == 10
    assert band.width == round(200 * 0.605) + 10

    x0, x1 = _separator_analysis_x_bounds(200, restored)
    usable = 200 - 2 * restored.paddle_separator_column_margin
    assert x0 == restored.paddle_separator_column_margin
    assert x1 == x0 + round(usable * 0.605)

    cache_base = replace(restored, paddle_band_width_ratio=60.1)
    cache_other = replace(restored, paddle_band_width_ratio=60.9)
    assert _cache_signature(image, geometry, cache_base) != _cache_signature(
        image, geometry, cache_other
    )


def test_decimal_percentage_ui_paths_do_not_integer_cast_values():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert 'add_field(ocr, 1, 2, "识别带宽%：", "paddle_band_width_ratio", float, 7)' in text
    assert "review_zoom_percent = float(self.parent.settings.review_zoom_percent)" in text
    assert "stored_review_zoom = float(getattr(parent.settings, \"review_zoom_percent\", 0.0) or 0.0)" in text
    assert "def _stored_review_zoom_percent(self) -> float:" in text
    assert "round(self.review_zoom * 100.0, 2)" in text
    assert "int(self.parent.settings.paddle_band_width_ratio)" not in text
    assert "int(self.parent.settings.paddle_separator_roi_width_ratio)" not in text


def test_project_profile_samples_front_middle_back_and_keeps_pairs():
    assert sample_page_indices(24, 6) == [0, 1, 11, 12, 22, 23]
    assert sample_page_indices(24, 4) == [0, 1, 12, 23]
    assert sample_page_indices(4, 6) == [0, 1, 2, 3]



def test_project_profile_configured_body_range_has_priority():
    images = [Path(f"{number:04d}.png") for number in range(1, 101)]
    allowed = configured_body_page_indices(len(images), "10-80")
    assert allowed[0] == 9
    assert allowed[-1] == 79
    samples = representative_page_indices(images, 6, allowed)
    assert len(samples) == 6
    assert min(samples) >= 9
    assert max(samples) <= 79

    assert configured_body_page_indices(len(images), "10至80") == allowed
    assert configured_body_page_indices(len(images), "10-800") == []



def test_project_profile_suggests_zero_padded_body_range():
    images = [
        Path("0000_cover.png"),
        Path("0001_title.png"),
        Path("0002.png"),
        Path("0003.png"),
        Path("0004.png"),
        Path("appendix_0005.png"),
    ]
    assert suggested_body_page_range(images) == "0003-0005"


def test_project_profile_representatives_avoid_obvious_front_and_back_matter():
    images = [Path("0000_cover.png")]
    images += [Path(f"{number:04d}_body.png") for number in range(1, 31)]
    images += [Path("appendix_01.png"), Path("附录_02.png")]
    candidates = probable_body_page_indices(images)
    assert 0 not in candidates
    assert len(images) - 1 not in candidates
    assert len(images) - 2 not in candidates

    samples = representative_page_indices(images, 6)
    assert len(samples) == 6
    assert all(index in candidates for index in samples)
    assert samples == sorted(samples)
    # Sampling stays inside the body rather than pinning to its absolute edges.
    assert samples[0] > candidates[0]
    assert samples[-1] < candidates[-1]


def test_project_profile_reading_labels_match_wizard_wording():
    assert READING_LABELS == {
        "horizontal-ltr": "横排：左→右",
        "horizontal-rtl": "横排：右→左",
        "vertical-rl": "纵排：右→左",
        "vertical-lr": "纵排：左→右",
    }


def test_project_profile_reading_dimension_is_independent():
    settings = AppSettings(
        layout_writing_mode="horizontal-tb",
        layout_text_direction="ltr",
        layout_transform="identity",
        ocr_language="ara",
    )
    apply_reading_choice(settings, "horizontal-rtl")
    assert reading_choice_from_settings(settings) == "horizontal-rtl"
    assert settings.layout_transform == "mirror_x"

    apply_reading_choice(settings, "vertical-rl")
    assert settings.layout_writing_mode == "vertical-rl"
    assert settings.layout_transform == "rotate_ccw90"


def test_headword_profile_does_not_override_confirmed_layout_or_language():
    settings = AppSettings(
        layout_writing_mode="vertical-rl",
        layout_text_direction="rtl",
        layout_transform="rotate_ccw90",
        layout_columns_policy="fixed",
        columns=3,
        layout_column_separator_mode="absent",
        ocr_language="jpn",
    )
    apply_headword_profile(settings, "latin_regular")
    assert settings.dictionary_profile_id == "latin_regular"
    assert settings.layout_writing_mode == "vertical-rl"
    assert settings.layout_text_direction == "rtl"
    assert settings.layout_transform == "rotate_ccw90"
    assert settings.columns == 3
    assert settings.layout_column_separator_mode == "absent"
    assert settings.ocr_language == "jpn"


def test_numbered_headword_profile_choices_keep_fixed_order_and_custom_last():
    choices = ordered_headword_profiles("古汉语单字结构")
    labels = [label for label, _key in choices]
    keys = [key for _label, key in choices]
    assert keys == [
        "latin_regular",
        "cjk_visual",
        "numbered_prefix",
        "marker_prefixed",
        "custom",
    ]
    assert labels == [
        "1. 常规边缘词头",
        "2. 视觉词头（大字/括号词头）",
        "3. 编号前缀词头",
        "4. 符号前缀词头",
        "5. 古汉语单字结构（自定义）",
    ]


def test_page_template_masks_side_content_before_geometry_without_mutating_source():
    image = Image.new("RGB", (100, 60), "white")
    for x in range(0, 12):
        for y in range(0, 60):
            image.putpixel((x, y), (0, 0, 0))
    settings = AppSettings(
        profile_side_content_mode="left",
        profile_side_percent=12,
    )
    masked = page_template_analysis_image(image, settings, 0)
    assert image.getpixel((5, 20)) == (0, 0, 0)
    assert masked.getpixel((5, 20)) == (255, 255, 255)
    assert masked.size == image.size


def test_page_template_alternating_ab_side_widths_are_independent():
    image = Image.new("RGB", (100, 60), "black")
    settings = AppSettings(
        profile_side_content_mode="outer",
        profile_page_pair_mode="alternate",
        profile_first_page_variant="A",
        profile_side_percent=8,
        profile_side_percent_a=6,
        profile_side_percent_b=14,
    )
    assert excluded_source_side(settings, 0) == "left"
    assert excluded_source_side(settings, 1) == "right"
    assert excluded_source_side_percent(settings, 0) == 6
    assert excluded_source_side_percent(settings, 1) == 14

    masked_a = page_template_analysis_image(image, settings, 0)
    masked_b = page_template_analysis_image(image, settings, 1)
    assert masked_a.getpixel((5, 30)) == (255, 255, 255)
    assert masked_a.getpixel((8, 30)) == (0, 0, 0)
    assert masked_b.getpixel((90, 30)) == (255, 255, 255)
    assert masked_b.getpixel((84, 30)) == (0, 0, 0)
    assert not entry_allowed_by_page_template(5, 30, image.size, settings, 0)
    assert entry_allowed_by_page_template(7, 30, image.size, settings, 0)
    assert not entry_allowed_by_page_template(90, 30, image.size, settings, 1)
    assert entry_allowed_by_page_template(84, 30, image.size, settings, 1)


def test_main_canvas_percentage_rulers_are_fixed_display_only_overlays():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    models = (root / "src" / "picture_capture" / "models.py").read_text(encoding="utf-8")

    assert "show_rulers: bool = True" in models
    assert 'ruler_color: str = "#1976d2"' in models
    assert "ruler_top_y_ratio" not in models
    assert "ruler_bottom_y_ratio" not in models
    assert "ruler_left_x_ratio" not in models
    assert "ruler_right_x_ratio" not in models
    assert 'for ruler_id, y in (("top", 0.0), ("bottom", display_height)):' in app
    assert 'for ruler_id, x in (("left", 0.0), ("right", display_width)):' in app
    assert "for half_percent in range(201):" in app
    assert "pct = half_percent * 0.5" in app
    assert "for value in range(5, 100, 5):" in app
    assert 'label_x = x - label_gap if ruler_id == "left" else x + label_gap' in app
    assert 'anchor = "e" if ruler_id == "left" else "w"' in app
    assert '"ruler_margin": "#f1f3f6"' in app
    assert '"ruler_margin": "#20252b"' in app
    assert 'tags=("ruler-margin",)' in app
    assert 'fill=margin_color, outline=""' in app
    assert "标尺可以帮助版面参数的手动填写。" in app
    assert "_drag_ruler_id" not in app
    assert "_ruler_drag_last_canvas" not in app
    assert "self.canvas.move(tag" not in app
    assert "build_page_crop_plan" not in app[
        app.index("    def _draw_percentage_rulers"):
        app.index("    def redraw(", app.index("    def _draw_percentage_rulers"))
    ]


def test_layout_percentage_helpers_preserve_pixel_backend_contract():
    image = Image.new("RGB", (1000, 2000), "white")
    assert _layout_pixels_to_percent(image, "manual_x", 125) == 12.5
    assert _layout_pixels_to_percent(image, "start_y", 200) == 10.0
    assert _layout_percent_to_pixels(image, "column_width", 25.0) == 250
    assert _layout_percent_to_pixels(image, "character_height", 1.5) == 30

    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    schema = (Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "ui" / "settings" / "schema.py").read_text(encoding="utf-8")
    assert '"start_y": "height"' in text
    assert '"manual_x": "width"' in text
    assert '"body_indent": "width"' in text
    assert '"horizontal_tolerance": "width"' in text
    quick_start = text.index("    def _build_quick_settings(")
    quick_end = text.index("\n    def ", quick_start + 10)
    quick = text[quick_start:quick_end]
    for label in ("正文起始Y：", "首栏X：", "单栏宽：", "栏间空："):
        assert label in quick
    for label in ("单行高：", "行间空：", "正文缩进：", "微调判距："):
        assert label not in quick
    assert quick.index('"单栏宽："') > quick.index('"首栏X："')
    assert quick.index('"栏间空："') > quick.index('"单栏宽："')
    assert "self.quick_pixel_vars: dict[str, tk.StringVar] = {}" in quick
    assert 'ttk.Label(value_frame, text="%")' in quick
    assert 'ttk.Label(value_frame, text="px")' in quick
    assert '"若所选页面数量≥2，参数为稳健中位数"' in quick
    detect_start = text.index("    def detect_layout_current(self) -> None:")
    detect_end = text.index("\n    def detect_layout_consistency_selected", detect_start)
    detect = text[detect_start:detect_end]
    assert 'numeric_summary="mean"' not in detect
    assert "多页数值参数将取稳健中位数" in detect
    assert '"start_y": "% 图高"' in schema
    assert '"manual_x": "% 图宽"' in schema
    assert "def _quick_percent_parameter_changed(self, name: str)" in text
    assert "def _quick_pixel_parameter_changed(self, name: str)" in text
    assert 'self._quick_geometry_edit_source[name] = "pixel"' in text
    assert 'geometry_source == "pixel"' in text


def test_page_template_auto_footer_uses_full_page_height_not_legacy_bottom_y():
    settings = AppSettings(
        bottom_y=1800,
        profile_footer_mode="auto",
    )
    effective = effective_page_settings(settings, (1000, 2000), 0)
    assert effective.crop_to_bottom_y is False

    explicit = replace(
        settings,
        profile_footer_mode="present",
        profile_footer_percent=10,
    )
    explicit_effective = effective_page_settings(explicit, (1000, 2000), 0)
    assert explicit_effective.crop_to_bottom_y is True
    assert explicit_effective.bottom_y == 1800


def test_page_template_applies_header_footer_and_ab_side_exclusion():
    settings = AppSettings(
        profile_header_mode="present",
        profile_header_percent=10,
        profile_footer_mode="present",
        profile_footer_percent=5,
        profile_side_content_mode="outer",
        profile_side_percent=8,
        profile_page_pair_mode="alternate",
        profile_first_page_variant="A",
    )
    effective = effective_page_settings(settings, (1000, 2000), 0)
    # For horizontal pages, the confirmed physical header/footer are also the
    # body/OCR geometry bounds. The blue column path must therefore begin/end
    # exactly at the yellow exclusion boundaries.
    assert effective.start_y == 200
    assert effective.bottom_y == 1900
    assert effective.crop_to_bottom_y is True

    source = Image.new("RGB", (1000, 2000), "white")
    masked_horizontal = page_template_analysis_image(source, effective, 0)
    geometry = derive_geometry(masked_horizontal, effective)
    assert geometry.top == 200
    assert geometry.bottom == 1900
    assert all(path.points[0][0] == 200 for path in geometry.column_paths)
    assert all(path.points[-1][0] == 1900 for path in geometry.column_paths)

    assert excluded_source_side(settings, 0) == "left"
    assert excluded_source_side(settings, 1) == "right"
    assert not entry_allowed_by_page_template(500, 100, (1000, 2000), settings, 0)
    assert not entry_allowed_by_page_template(500, 1950, (1000, 2000), settings, 0)
    assert not entry_allowed_by_page_template(50, 500, (1000, 2000), settings, 0)
    assert entry_allowed_by_page_template(950, 500, (1000, 2000), settings, 0)
    assert not entry_allowed_by_page_template(950, 500, (1000, 2000), settings, 1)

    vertical = replace(
        settings,
        layout_writing_mode="vertical-rl",
        layout_text_direction="rtl",
        layout_transform="rotate_ccw90",
    )
    vertical_effective = effective_page_settings(vertical, (1000, 2000), 0)
    # For vertical writing, physical top/bottom are not the canonical reading
    # axis, so keep the learned start_y/bottom_y and apply only source masks.
    assert vertical_effective.start_y == vertical.start_y
    assert vertical_effective.bottom_y == vertical.bottom_y
    masked = page_template_analysis_image(
        Image.new("RGB", (1000, 2000), "black"), vertical_effective, 0,
    )
    assert masked.getpixel((500, 50)) == (255, 255, 255)
    assert masked.getpixel((500, 1950)) == (255, 255, 255)


def test_project_profile_feedback_tuning_is_profile_aware():
    cjk = AppSettings(ocr_language="chi_tra")
    apply_headword_profile(cjk, "cjk_visual")
    base_cjk = (
        cjk.paddle_left_tolerance,
        cjk.paddle_height_ratio,
        cjk.paddle_boldness_ratio,
    )
    apply_headword_tuning(cjk, "cjk_visual", 1)
    assert cjk.paddle_left_tolerance < base_cjk[0]
    assert cjk.paddle_height_ratio > base_cjk[1]
    assert cjk.paddle_boldness_ratio > base_cjk[2]

    marker = AppSettings(ocr_language="chi_sim")
    apply_headword_profile(marker, "marker_prefixed")
    base_score = marker.paddle_min_candidate_score
    base_left = marker.paddle_left_tolerance
    apply_headword_tuning(marker, "marker_prefixed", 1)
    assert marker.paddle_left_tolerance < base_left
    assert marker.paddle_min_candidate_score == base_score


def test_project_profile_headword_examples_are_packaged():
    from PIL import Image

    root = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "data" / "headword_examples"
    )
    expected = [
        "headword_example_1.png",
        "headword_example_2.png",
        "headword_example_3.png",
        "headword_example_4.png",
    ]
    for name in expected:
        path = root / name
        assert path.exists()
        with Image.open(path) as image:
            assert image.width > 0 and image.height > 0

    assert not (root / "classic_headword_examples.jpg").exists()
    assert not (root / "recommended_current").exists()
    assert not (root / "manifest.csv").exists()
    assert not (root / "manifest.json").exists()

    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert "data/headword_examples/*.png" in pyproject
    assert "data/headword_examples/recommended_current/" not in pyproject
    assert "data/profile_previews/" not in pyproject
    assert "data/headword_examples/extended/" not in pyproject

    dictionary_source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "dictionary_profile.py"
    ).read_text(encoding="utf-8")
    app_source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    assert "profile_preview_path" not in dictionary_source
    assert "profile_preview_dir" not in dictionary_source
    assert "profile_preview_path" not in app_source
    assert "preview_profile_examples" not in app_source


def test_project_profile_wizard_uses_analysis_as_a_setup_aid_then_stable_columns():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "profile_setup.py"
    text = source.read_text(encoding="utf-8")
    assert "代表页会自动分析并建议栏数；确认后作为本项目的稳定栏数使用。" in text
    assert 's.layout_columns_policy = "fixed"' in text
    assert "设置已修改，需要重新测试" in text

    assert '"1 词典与阅读"' in text
    assert '"2 页面模板"' in text
    assert '"3 词头结构"' in text
    assert '"4 测试确认"' in text
    assert '"4 语言与 OCR"' not in text
    assert "self._build_language_section(tab, row=4)" in text
    assert 'text="词典项目详情"' in text
    assert 'text="词典全称："' in text
    assert 'text="词典简称(字母)："'.strip() in text
    assert 'text="ISBN："' in text
    assert 'text="正文页码："' in text
    assert 'row=0, column=0' in text
    assert 'row=0, column=2' in text
    assert 'row=1, column=0' in text
    assert 'row=1, column=2' in text
    assert "suggested_body_page_range(self.project.images)" in text
    assert "s.dictionary_full_name = self.dictionary_full_name_var.get().strip()" in text
    assert "s.dictionary_body_page_range = self.dictionary_body_page_range_var.get().strip()" in text
    assert "def _body_page_range_changed" in text

    assert "每一张都可在右侧手动更换" in text
    assert 'text="更换…"' in text
    assert '"页面模板即时预览"' in text
    assert 'text="◀ 上一张"' in text and 'text="下一张 ▶"' in text
    assert '"词头类型样例"' in text
    assert "self._build_right_image_workspace(right_panel)" in text
    assert 'ttk.Panedwindow(outer, orient="horizontal")' in text
    assert "self.profile_paned.add(left_panel, weight=40)" in text
    assert "self.profile_paned.add(right_panel, weight=60)" in text
    assert "def _apply_initial_pane_split" in text
    assert "round(pane_width * 0.40)" in text
    assert "self.after_idle(self._apply_initial_pane_split)" in text
    assert "self.profile_paned.sashpos" in text
    assert "def _apply_left_wraps" in text
    assert 'left_panel.bind(' in text
    assert 'child.configure(wraplength=wrap, justify="left")' in text
    assert "ProfileYellow.TLabelframe" not in text
    assert "fill=(255, 215, 0, 105)" in text
    marker_start = text.index("    def _marker_preview(")
    marker_end = text.index("    def _set_validation_fit(", marker_start)
    assert "fill=(255, 215, 0, 105)" in text[marker_start:marker_end]
    assert 'text="A 页排除宽度%"' in text
    assert 'text="B 页排除宽度%"' in text
    assert "s.profile_side_percent_a" in text
    assert "s.profile_side_percent_b" in text
    assert 'text="◀ 上一页"' in text
    assert 'text="适合高度"' in text
    assert 'text="适合宽度"' in text
    assert 'text="下一页 ▶"' in text
    assert "默认适合高度；适合宽度时图片横向占满" not in text
    assert 'self.validation_fit_mode = "height"' in text
    assert "def _set_validation_fit" in text
    assert "索引语言（2 位）" in text
    assert "indices = list(self.sample_indices)" in text
    assert 'uniform="sample"' in text
    assert 'uniform="sample_row"' in text
    assert "thumb_w = max(180, (available_w - 54) // 3)" in text
    assert "thumb_h = max(220, (available_h - 150) // 2 - 42)" in text

    # The window skeleton is built first; representative image decoding begins
    # later on a worker thread instead of blocking the button click.
    assert "self._show_sample_loading_state()" in text
    assert "self.after(20, self._start_sample_thumbnail_load)" in text
    assert "threading.Thread(target=worker, daemon=True).start()" in text
    assert "elif index == 2:" in text and "self._refresh_headword_description" in text

    # Replacing one representative page is a slot-local operation. It must not
    # rebuild/re-decode all six thumbnails or refresh a hidden template preview.
    assert "def _start_sample_thumbnail_slot_load" in text
    assert "def _render_sample_thumbnail_slot" in text
    choose_start = text.index("    def _choose_sample_page(")
    choose_end = text.index("    def _persist_current_profile(", choose_start)
    choose_text = text[choose_start:choose_end]
    assert "self._start_sample_thumbnail_slot_load(slot)" in choose_text
    assert "self._start_sample_thumbnail_load()" not in choose_text
    assert "preview_uses_slot = self.template_preview_slot == slot" in choose_text
    assert "self.notebook.index(self.notebook.select()) == 1" in choose_text

    # Multi-page validation is presented one page at a time with the same
    # previous/next navigation language as the page-template preview.
    assert "self._validation_results = list(results)" in text
    assert "def _move_validation_preview" in text
    assert "def _render_validation_result" in text
    assert "width = min(work_w, max(720, int(screen_w * 0.80)))" in text
    assert "return screen_work_area(widget)" in text
    ui_compat = (Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "ui_compat.py").read_text(encoding="utf-8")
    assert "SystemParametersInfoW" in ui_compat
    assert "height = max(1, int(work_h * 0.90))" in text
    assert "x = work_x + max(0, (work_w - width) // 2)" in text
    assert "y = work_y + max(0, (work_h - height) // 2)" in text
    assert "self._wizard_left_width = max(400, int(width * 0.40) - 36)" in text
    assert "self._wizard_image_width = max(560, int(width * 0.60) - 36)" in text
    assert "target_width = max(320, int(preview_width))" in text
    assert "source.resize(" in text
    assert "right_width = int(getattr(self, \"right_canvas\", self).winfo_width())" in text
    assert "HEADWORD_EXAMPLE_FILES" in text
    assert '"headword_example_1.png"' in text
    assert '"headword_example_2.png"' in text
    assert '"headword_example_3.png"' in text
    assert '"headword_example_4.png"' in text
    assert "HEADWORD_EXAMPLE_ATLAS_CROPS" not in text
    assert '"classic_headword_examples.jpg"' not in text
    assert "recommended_current" not in text
    assert 'root / "extended"' not in text
    assert "fill=(255, 0, 0, 255), width=1" in text
    assert "完整词头结构（词头前 + 词头本体 + 词头后）" in text
    assert "普通左缘短词可以作为词头" in text
    assert "【括号词】可以作为词头" in text
    assert "大字单字可以作为词头" in text
    assert "分析大字右侧留白（仅辅助“大字单字”判断）" in text
    assert "大字右侧检测宽度：" in text
    assert "profile_cjk_right_context_width_percent" in text
    assert "固定符号开头（○ / ● / ◆ …；不包括【括号】）可以作为词头" in text
    assert "本词典固定词头符号集" in text
    assert "启用独立入口标记符号集（○ / ● / ◆ …）" in text
    assert "独立入口标记：" in text
    assert "括号词头起始：" in text
    assert "括号内文字才是词头。该栏由“【括号词】”结构独立控制" in text
    assert "OCR 漏掉/错认符号时允许视觉形状补救" in text
    assert "使用同栏 marker lane 过滤正文中的相似符号" in text
    assert "self.symbol_inventory_frame.columnconfigure(1, weight=1, minsize=180)" in text
    assert "symbol_hint_wrap = max(220, self._wizard_content_width - 140)" in text
    assert "symbol_full_wrap = max(280, self._wizard_content_width - 40)" in text
    assert "textvariable=self.entry_marker_symbols_var" in text
    assert "textvariable=self.bracket_open_symbols_var" in text
    assert "width=24" in text
    assert 'grid(row=1, column=1, columnspan=2, sticky="ew", pady=3)' in text
    assert 'grid(row=3, column=1, columnspan=2, sticky="ew", pady=3)' in text
    assert "wraplength=symbol_hint_wrap" in text
    assert "wraplength=symbol_full_wrap" in text
    assert "OCR 漏掉/错认符号时允许视觉形状补救（默认关；" not in text
    assert "本词典视觉标记样本" in text
    assert "字符符号集 + 视觉样本" in text
    assert "视觉样本优先" in text
    assert "按角色合并（推荐）" in text
    assert "最低匹配分数：" in text
    assert "从页面采样…" in text
    assert "查看/删除样本" in text
    assert "有效入口标记：" in text
    assert "profile_symbol_template_version" in text
    assert "profile_symbol_templates_json" in text
    assert "profile_symbol_inventory_version" in text
    assert "profile_entry_marker_symbols" in text
    assert "profile_bracket_open_symbols" in text
    assert "profile_symbol_lane_tolerance_percent" in text
    assert "编号开头（1. / 2. / …）可以作为词头" in text
    assert "词头专属性（当前结构的视觉证据）" in text
    assert 'text="栏左缘容差："' in text
    assert "% 单栏宽（允许词头起点偏离栏左边界的最大距离；越小越严格）" in text
    assert 'text="文字大小倍率 ≥"' in text
    assert 'text="粗体倍率 ≥"' in text
    assert 'text="候选强度 ≥"' in text
    assert "CJK 单字 / 括号词附加条件" in text
    assert "右侧显示与当前词头结构匹配的经典局部裁切样例。" not in text
    assert "必须靠近栏左缘" in text
    assert "释义正文中也经常出现【括号词】" in text
    assert "只有视觉明显突出时才把单字/括号词当词头" in text
    assert 'text="偏多"' in text and 'text="合适"' in text and 'text="偏少"' in text
    assert "def _apply_validation_feedback" in text
    assert "def _headword_structure_changed" in text
    assert "recommended_headword_structures" in text
    assert "s.profile_parser_controls_version = 1" in text
    assert "s.profile_allow_ordinary_left_edge" in text
    assert "s.profile_allow_numbered_prefix" in text
    assert "s.profile_allow_marker_prefix" in text
    assert "s.paddle_left_tolerance = max(" in text
    assert "s.paddle_height_ratio = max(" in text
    assert "s.paddle_boldness_ratio = max(" in text
    assert "s.paddle_min_candidate_score = max(" in text
    assert "def _persist_current_profile" in text
    assert "def _save_profile_progress" in text
    assert "if not self._save_profile_progress():" in text
    assert 'text="关闭"' in text
    assert "当前内容已经保存。项目 Profile 尚未完整确认" in text
    assert "settings.profile_setup_version = int(" in text
    assert 'header_mode == "auto" and geometry.top > 0' in text
    assert 'elif header_mode == "present"' in text
    validate_start = text.index("    def validate_profile(")
    validate_end = text.index("    def _poll_validation_queue(", validate_start)
    validate_text = text[validate_start:validate_end]
    assert 'settings.detection_method = "paddleocr"' in validate_text
    assert "settings.paddle_use_paddleocr = True" in validate_text
    assert "force_paddle_refresh=True" in validate_text
    assert "正在强制重新识别并测试代表页" in text
    assert "def _validation_coverage_summary" in text
    assert "self.validation_diagnostic_var" in text
    assert "下半页候选" in text
    assert "左缘最大漂移" in text
    assert "原始OCR完整但词头在中途停止" in text


def _parsed_headword_for_script_test(value: str) -> HeadwordParse:
    return HeadwordParse(
        raw=value,
        normalized=value,
        has_pos=False,
        pos_text="",
        has_inflection=False,
        inflection_text="",
        has_descriptor=False,
        descriptor_text="",
        match_end=max(1, len(value)),
    )


def test_headword_script_guard_rejects_cjk_for_non_cjk_ocr_but_keeps_japanese_kanji():
    han = _parsed_headword_for_script_test("波")
    kana = _parsed_headword_for_script_test("あい")
    latin = _parsed_headword_for_script_test("abbassare")

    ita = AppSettings(
        ocr_language="ita",
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=True,
    )
    assert _headword_script_compatibility(ita, han) == (False, "han")
    assert _headword_script_compatibility(ita, kana) == (False, "kana")
    assert _headword_script_compatibility(ita, latin) == (True, "other")

    jpn = AppSettings(
        ocr_language="jpn",
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=True,
    )
    assert _headword_script_compatibility(jpn, han) == (True, "han")
    assert _headword_script_compatibility(jpn, kana) == (True, "kana")

    chi = AppSettings(
        ocr_language="chi_sim",
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=True,
    )
    assert _headword_script_compatibility(chi, han) == (True, "han")
    assert _headword_script_compatibility(chi, kana) == (False, "kana")


def test_headword_script_guard_is_a_hard_candidate_gate():
    settings = AppSettings(
        ocr_language="ita",
        profile_parser_controls_version=1,
        profile_allow_ordinary_left_edge=True,
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=True,
        paddle_auto_header_rule=False,
        paddle_left_tolerance=40,
        paddle_band_left_margin=12,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(preset="latin_regular", language="ita")
    records = [
        OCRRecord(text="波 s.m. definizione", confidence=0.99, box=(2, 20, 95, 38))
    ]
    entries, diagnostics = filter_headword_records(
        records,
        Image.new("RGB", (160, 100), "white"),
        0,
        0,
        settings,
        user_rules=parse_headword_filter_rules("accept_lemma_exact: 波"),
        profile=profile,
    )
    assert entries == []
    rows = [row for row in diagnostics if "meta" not in row]
    assert rows
    assert rows[0]["normalized_headword"] == "波"
    assert rows[0]["reject_reason"] == "incompatible_headword_script"
    assert rows[0]["features"]["headword_leading_script"] == "han"
    assert rows[0]["features"]["headword_script_compatible"] is False


def test_headword_script_guard_can_be_disabled_for_special_bilingual_projects():
    han = _parsed_headword_for_script_test("波")
    settings = AppSettings(
        ocr_language="ita",
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=False,
    )
    assert _headword_script_compatibility(settings, han) == (True, "")


def test_headword_profiles_seed_explicit_tail_structure_defaults():
    latin = profile_tail_structure_defaults("latin_regular")
    assert latin == {
        "allow_pos": True,
        "allow_inflection": True,
        "allow_variant": True,
        "allow_pronunciation": False,
        "allow_descriptor": True,
        "require_selected": True,
        "allow_visual_rescue": True,
    }
    numbered = profile_tail_structure_defaults("numbered_prefix")
    assert numbered["require_selected"] is False
    assert numbered["allow_visual_rescue"] is False
    cjk = profile_tail_structure_defaults("cjk_visual")
    assert not any(
        cjk[name]
        for name in (
            "allow_pos", "allow_inflection", "allow_variant",
            "allow_pronunciation", "allow_descriptor",
            "require_selected", "allow_visual_rescue",
        )
    )


def test_selected_tail_structure_evidence_obeys_project_checkboxes():
    settings = AppSettings(
        ocr_language="ita",
        profile_tail_structure_version=1,
        profile_tail_allow_pos=False,
        profile_tail_allow_inflection=False,
        profile_tail_allow_variant=True,
        profile_tail_allow_pronunciation=False,
        profile_tail_allow_descriptor=False,
    )
    profile = load_dictionary_profile(preset="latin_regular", language="ita")
    patterns = _compile_patterns(settings, profile)
    parsed = parse_headword_text(
        "abbandonata, da agg. forma femminile",
        settings, patterns, profile,
    )
    assert parsed is not None
    assert parsed.has_pos
    assert parsed.variants
    evidence, features = _selected_tail_structure_evidence(settings, parsed)
    assert evidence == ("variant",)
    assert features["available_pos"] is True
    assert features["selected_pos"] is False
    assert features["selected_variant"] is True


def test_complete_headword_structure_round_trips_in_v3_sidecar(tmp_path):
    path = tmp_path / "dictionary_profile.json"
    settings = AppSettings(
        dictionary_profile_id="latin_regular",
        ocr_language="ita",
        profile_parser_controls_version=1,
        profile_headword_script_guard_version=1,
        profile_headword_script_guard_enabled=True,
        profile_allow_ordinary_left_edge=True,
        profile_allow_numbered_prefix=False,
        profile_allow_marker_prefix=True,
        profile_cjk_allow_single_headword=False,
        profile_cjk_allow_bracketed_headword=False,
        profile_tail_structure_version=1,
        profile_tail_allow_pos=True,
        profile_tail_allow_inflection=False,
        profile_tail_allow_variant=True,
        profile_tail_allow_pronunciation=True,
        profile_tail_allow_descriptor=False,
        profile_tail_require_selected=True,
        profile_tail_allow_visual_rescue=True,
        profile_symbol_inventory_version=1,
        profile_symbol_inventory_enabled=True,
        profile_entry_marker_symbols="◆ ◇",
        profile_bracket_open_symbols="",
        profile_symbol_visual_rescue_enabled=True,
        profile_symbol_lane_required=True,
        profile_symbol_lane_tolerance_percent=45,
    )
    write_project_profile(path, settings, "latin_regular", force=True)
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))
    assert payload["headword_structure"]["tail"]["allow_pronunciation"] is True
    assert payload["headword_structure"]["script_guard_enabled"] is True
    assert payload["headword_structure"]["starts"]["marker_prefix"] is True
    assert payload["headword_structure"]["symbol_inventory"]["entry_markers"] == "◆ ◇"

    restored = AppSettings()
    apply_project_profile_components(path, restored)
    assert restored.profile_headword_script_guard_version == 1
    assert restored.profile_headword_script_guard_enabled is True
    assert restored.profile_tail_structure_version == 1
    assert restored.profile_tail_allow_pos is True
    assert restored.profile_tail_allow_inflection is False
    assert restored.profile_tail_allow_variant is True
    assert restored.profile_tail_allow_pronunciation is True
    assert restored.profile_tail_allow_descriptor is False
    assert restored.profile_tail_require_selected is True
    assert restored.profile_tail_allow_visual_rescue is True
    assert restored.profile_allow_marker_prefix is True
    assert restored.profile_entry_marker_symbols == "◆ ◇"


def test_profile_setup_exposes_complete_headword_structure_controls():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "profile_setup.py"
    )
    text = source.read_text(encoding="utf-8")
    assert "完整词头结构（词头前 + 词头本体 + 词头后）" in text
    assert "按 OCR 语言排除不兼容的词头首字符（推荐）" in text
    assert "日语允许汉字/假名，中文允许汉字" in text
    assert "profile_headword_script_guard_version = 1" in text
    assert "词头后结构（哪些内容可以作为新词条证据）" in text
    assert "词性 POS（s.m. / v.tr. / agg. / adj. …）" in text
    assert "词形 / 屈折变化" in text
    assert "变体 / 性数变化" in text
    assert "发音 / 音标" in text
    assert "描述型结构" in text
    assert "普通左缘词至少需要命中一种上面勾选的词后结构" in text
    assert "允许“严格左缘 + 粗体”视觉补救" in text
    assert "不再另设隐藏的粗体/行高门槛" in text
    assert "profile_tail_structure_version = 1" in text


def test_latin_regular_italian_pos_labels_tolerate_ocr_dot_spacing():
    settings = AppSettings(
        ocr_language="ita",
        profile_parser_controls_version=1,
        profile_allow_ordinary_left_edge=True,
    )
    profile = load_dictionary_profile(preset="latin_regular", language="ita")
    patterns = _compile_patterns(settings, profile)
    examples = (
        "abbassare v. tr. abbassare qualcosa",
        "abbarbagliare vtr. la mente",
        "abbandono s. m. stato di abbandono",
        "abbattere v. intr. forma rara",
    )
    for text in examples:
        parsed = parse_headword_text(text, settings, patterns, profile)
        assert parsed is not None, text
        assert parsed.has_pos, text


def test_latin_regular_profile_enables_conservative_strong_edge_visual_rescue():
    settings = AppSettings(ocr_language="ita")
    apply_headword_profile(settings, "latin_regular")
    assert settings.paddle_require_pos_or_symbol is True
    assert settings.paddle_allow_strong_edge_visual_rescue is True
    assert settings.paddle_strong_edge_visual_boldness_ratio == 1.22
    assert settings.paddle_strong_edge_visual_height_ratio == 0.90


def test_explicit_tail_visual_rescue_uses_visible_profile_thresholds_only():
    settings = AppSettings(
        ocr_language="ita",
        profile_tail_structure_version=1,
        profile_tail_allow_visual_rescue=True,
        paddle_boldness_ratio=1.00,
        paddle_rec_score_threshold=0.20,
        # Deliberately impossible legacy thresholds: explicit Profile mode must
        # ignore them instead of silently overriding the visible UI.
        paddle_strong_edge_visual_boldness_ratio=2.80,
        paddle_strong_edge_visual_height_ratio=2.20,
        paddle_strong_edge_visual_min_confidence=0.99,
    )
    profile = load_dictionary_profile(preset="latin_regular", language="ita")
    patterns = _compile_patterns(settings, profile)
    parsed = parse_headword_text(
        "addomesticare vti. addomesticare qualcosa",
        settings,
        patterns,
        profile,
    )
    assert parsed is not None
    assert not parsed.has_pos

    thresholds = _ordinary_visual_rescue_thresholds(settings)
    assert thresholds["source"] == "visible_profile_specificity"
    assert thresholds["boldness"] == 1.00
    assert thresholds["height"] == 0.0
    assert thresholds["confidence"] == 0.20

    assert _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.04,
        height_ratio=0.78,
        confidence=0.85,
        looks_like_continuation=False,
        marker_noise=False,
    )

    # Raising the visible UI boldness threshold must immediately tighten the
    # same rescue path; no second hidden threshold participates.
    settings.paddle_boldness_ratio = 1.10
    assert not _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.04,
        height_ratio=1.10,
        confidence=0.85,
        looks_like_continuation=False,
        marker_noise=False,
    )
    assert _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.12,
        height_ratio=0.78,
        confidence=0.85,
        looks_like_continuation=False,
        marker_noise=False,
    )


def test_strong_edge_visual_rescue_recovers_pos_ocr_failure_but_not_body_text():
    settings = AppSettings(
        ocr_language="ita",
        paddle_allow_strong_edge_visual_rescue=True,
        paddle_strong_edge_visual_boldness_ratio=1.22,
        paddle_strong_edge_visual_height_ratio=0.90,
        paddle_strong_edge_visual_min_confidence=0.55,
        paddle_boldness_ratio=1.12,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(preset="latin_regular", language="ita")
    patterns = _compile_patterns(settings, profile)
    parsed = parse_headword_text(
        "abbarbagliamento sim. 眩眼，迷乱",
        settings,
        patterns,
        profile,
    )
    assert parsed is not None
    assert not parsed.has_pos

    assert _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.34,
        height_ratio=0.96,
        confidence=0.91,
        looks_like_continuation=False,
        marker_noise=False,
    )
    assert not _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.08,
        height_ratio=0.96,
        confidence=0.91,
        looks_like_continuation=False,
        marker_noise=False,
    )
    assert not _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=True,
        below_header=True,
        boldness_ratio=1.34,
        height_ratio=0.96,
        confidence=0.91,
        looks_like_continuation=True,
        marker_noise=False,
    )
    assert not _ordinary_strong_edge_visual_rescue(
        settings,
        parsed,
        at_left=False,
        below_header=True,
        boldness_ratio=1.34,
        height_ratio=0.96,
        confidence=0.91,
        looks_like_continuation=False,
        marker_noise=False,
    )


def test_visual_marker_symbol_inventory_accepts_contiguous_input():
    expected = ("●", "○", "◉", "◯")
    assert split_configured_symbols("●○◉◯") == expected
    assert split_configured_symbols("● ○ ◉ ◯") == expected
    assert split_configured_symbols("●,○,◉,◯") == expected
    assert split_configured_symbols("●，○，◉，◯") == expected
    assert split_configured_symbols("ABC") == ("ABC",)


def test_visual_marker_templates_round_trip_with_project_settings(tmp_path):
    image = Image.new("L", (36, 36), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((7, 7, 28, 28), outline=0, width=4)
    sample = build_visual_marker_sample(
        image,
        role="entry_marker",
        literal="○",
        sample_id="entry:test",
        source_page="0023.png",
        source_box=(10, 20, 46, 56),
    )
    settings = AppSettings(
        profile_symbol_template_version=1,
        profile_symbol_template_mode="combined",
        profile_symbol_template_group_mode="role",
        profile_symbol_template_threshold=0.68,
        profile_symbol_templates_json=serialize_visual_marker_samples([sample]),
    )
    path = tmp_path / "settings.json"
    settings.to_json(path)
    reopened = AppSettings.from_json(path)
    samples = parse_visual_marker_samples(reopened.profile_symbol_templates_json)
    assert reopened.profile_symbol_template_version == 1
    assert reopened.profile_symbol_template_mode == "combined"
    assert len(samples) == 1
    assert samples[0]["literal"] == "○"
    assert samples[0]["source_page"] == "0023.png"
    assert samples[0]["source_box"] == [10, 20, 46, 56]


def test_dictionary_visual_template_matches_scan_variation():
    reference = Image.new("L", (40, 40), 255)
    draw = ImageDraw.Draw(reference)
    draw.ellipse((8, 8, 31, 31), outline=0, width=4)
    sample = build_visual_marker_sample(
        reference, role="entry_marker", literal="○", sample_id="ring"
    )

    candidate = Image.new("L", (42, 42), 255)
    draw = ImageDraw.Draw(candidate)
    draw.ellipse((8, 9, 33, 34), outline=0, width=5)
    candidate_mask = np.asarray(candidate, dtype=np.uint8) < 128
    match = match_visual_marker_template(candidate_mask, [sample])
    assert match is not None
    assert float(match["score"]) >= 0.55
    assert match["sample"]["id"] == "ring"


def test_visual_marker_detector_can_use_dictionary_template_without_generic_family():
    reference = Image.new("L", (24, 24), 255)
    draw = ImageDraw.Draw(reference)
    draw.ellipse((4, 4, 19, 19), outline=0, width=3)
    sample = build_visual_marker_sample(
        reference, role="entry_marker", literal="○", sample_id="ring"
    )

    page = Image.new("L", (90, 120), 255)
    draw = ImageDraw.Draw(page)
    draw.ellipse((6, 46, 21, 61), outline=0, width=3)
    markers = _detect_visual_entry_markers(
        np.asarray(page, dtype=np.uint8),
        18.0,
        24,
        lower_bound=0,
        inventory={
            "enabled": True,
            "entry_markers": ("○",),
            "bracket_openers": (),
            "visual_rescue": True,
            "lane_required": False,
            "lane_tolerance_percent": 50,
            "visual_families": (),
            "visual_templates": [sample],
            "visual_template_mode": "template_first",
            "visual_template_threshold": 0.50,
        },
    )
    assert markers
    assert markers[0]["family"] == "dictionary_template"
    assert markers[0]["role"] == "entry_marker"
    assert markers[0]["symbol"] == "○"
    assert float(markers[0]["template_score"]) >= 0.50


def test_visual_marker_capture_uses_source_pixel_zoom_controls():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "visual_marker_ui.py"
    )
    text = source.read_text(encoding="utf-8")
    assert "self.zoom_percent = 100" in text
    assert 'text="图片缩放（默认 100% 原始像素）："' in text
    assert 'text="100%", command=lambda: self._set_zoom(100)' in text
    assert 'text="适合窗口", command=self._fit_window' in text
    assert '"<Control-MouseWheel>"' in text
    assert "self.canvas.canvasx(event.x)" in text
    assert "self.canvas.canvasy(event.y)" in text
    assert 'orient="horizontal", command=self.canvas.xview' in text
    assert 'orient="vertical", command=self.canvas.yview' in text
    assert "self.selection_source = source_box" in text
    assert "当前缩放 {self.zoom_percent}%" in text


def test_project_profile_column_left_nudges_persist_and_drive_geometry(tmp_path):
    settings = AppSettings(
        columns=2,
        manual_x=40,
        column_width=300,
        gutter=40,
        column_start_offsets=[0, 12],
        follow_column_deformation=False,
    )
    geometry = derive_nominal_geometry(800, 1000, settings)
    assert geometry.column_starts == [40, 392]

    # Version-3 values are literal image pixels. A wider image must not silently
    # double the user's X positions or per-column corrections.
    larger = derive_nominal_geometry(1600, 2000, settings)
    assert larger.column_starts == [40, 392]

    path = tmp_path / "settings.json"
    settings.to_json(path)
    saved = path.read_text(encoding="utf-8")
    reopened = AppSettings.from_json(path)
    assert reopened.column_start_offsets == [0, 12]
    # Corrupt/extreme nudges are clipped before columns can cross.
    guarded = apply_column_start_offsets(
        [40, 380], [250, -250], gutter=40, max_x=799,
    )
    assert guarded[0] < guarded[1]
    assert guarded[1] - guarded[0] >= 50


def test_source_pixel_settings_never_scale_against_page_width():
    settings = AppSettings(
        paddle_left_tolerance=34,
        paddle_separator_safety_px=2,
    )
    assert settings.paddle_left_tolerance == 34
    assert settings.paddle_separator_safety_px == 2
    geometry_1400 = derive_nominal_geometry(1400, 1800, settings)
    geometry_4200 = derive_nominal_geometry(4200, 5400, settings)
    assert geometry_1400.column_starts[0] == geometry_4200.column_starts[0]
    assert geometry_1400.top == geometry_4200.top

def test_project_profile_exposes_clickable_column_left_line_nudging():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "profile_setup.py"
    text = source.read_text(encoding="utf-8")
    assert 'text="栏左线微调"' in text
    assert "点击右侧预览中的栏左线选择；选中线显示为橙色" in text
    assert "每次移动约 0.1% 单栏宽" in text
    assert 'text="← 左移 0.1%"' in text
    assert 'text="右移 0.1% →"' in text
    assert "人工偏移 {percent:+.2f}% 单栏宽" in text
    assert 'text="重置当前"' in text
    assert 'text="重置全部"' in text
    assert "def _shift_selected_column" in text
    assert "self.working.column_start_offsets = offsets" in text
    assert "s.column_start_offsets = self._column_offsets_for_count(s.columns)" in text
    assert 'canvas.bind(\n                "<Button-1>"' in text
    assert 'fill="#ee7c00" if column_index == selected_column else "#1e78d2"' in text
    assert "self.working.column_start_offsets = [0] * max(1, int(self.columns_var.get()))" in text
    assert "def _nudge_template_column_preview" in text
    assert "canvas.move(items[index], dx, dy)" in text
    assert "self._profile_input_changed(refresh_preview=False)" in text
    select_start = text.index("    def _select_template_column(")
    select_end = text.index("\n\n    def _refresh_template_controls", select_start)
    assert "_refresh_template_preview" not in text[select_start:select_end]
    assert "self._update_template_column_highlight()" in text[select_start:select_end]
    assert "canvas.create_image(0, 0, image=photo, anchor=\"nw\")" in text


def test_project_profile_validation_masks_remain_translucent():
    from picture_capture.processing import ColumnPath, Geometry
    from picture_capture.profile_setup import ProjectProfileWizard

    image = Image.new("RGB", (100, 100), "white")
    geometry = Geometry(
        column_starts=[10], column_widths=[80], top=20, bottom=100,
        column_paths=[ColumnPath([(20, 10), (100, 10)])],
    )
    settings = AppSettings(
        profile_header_mode="present", profile_header_percent=20.0,
        profile_footer_mode="none", profile_side_content_mode="none",
    )
    preview = ProjectProfileWizard._marker_preview(
        image, [], geometry, settings, 0, 100,
    )
    pixel = preview.getpixel((50, 10))
    assert pixel != (255, 215, 0)
    assert pixel != (255, 255, 255)
    assert pixel[0] == 255 and 215 < pixel[1] < 255 and 0 < pixel[2] < 255



def test_project_profile_wizard_is_the_normal_entry_path():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert "ProjectProfileWizard(self, new_project=new_project)" in text
    assert "launch_profile_setup=not existing_project" in text

    profile_source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "profile_setup.py"
    ).read_text(encoding="utf-8")
    wizard_start = profile_source.index("class ProjectProfileWizard(tk.Toplevel):")
    wizard_end = profile_source.index("    def _build_vars(self) -> None:", wizard_start)
    wizard_init = profile_source[wizard_start:wizard_end]
    assert "x = work_x + max(0, (work_w - width) // 2)" in wizard_init
    assert "y = work_y + max(0, (work_h - height) // 2)" in wizard_init
    assert '(common_tab, "常用")' in text
    assert '(ocr_tab, "OCR画线")' in text
    assert '(normal_tab, "普通画线")' in text
    assert text.index('(ocr_tab, "OCR画线")') < text.index('(normal_tab, "普通画线")')
    assert '(display_tab, "显示/校对")' in text
    assert '(project_tab, "项目/批量")' in text
    assert '(crop_tab, "切图")' in text
    assert '(advanced_tab, "高级")' in text
    assert '"profile": advanced_tab' in text
    start = text.index("    def open_project_profile(")
    end = text.index("    def open_project_details(", start)
    assert 'self.open_settings(initial_tab="profile")' not in text[start:end]


def test_main_ocr_drawing_defaults_to_cache_reuse_and_paddle_only():
    root = Path(__file__).resolve().parents[1]
    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    guide_text = (
        root / "src" / "picture_capture" / "ui" / "dialogs" / "usage_guide.py"
    ).read_text(encoding="utf-8")
    assert 'self.ocr_refresh_var = tk.StringVar(value="reuse")' in app_text
    assert "使用有效缓存（推荐）" in app_text
    assert "重新OCR（模型/图像改变时）" in app_text
    assert "默认只启用 PaddleOCR；Tesseract 与 Google Lens 按需手动开启" in guide_text
    assert 'LENS_MODE_LABELS["off"]' in app_text

    settings = AppSettings()
    assert settings.paddle_use_paddleocr is True
    assert settings.paddle_compare_tesseract is False
    assert settings.paddle_enable_lens is False
    assert settings.paddle_lens_mode == "off"

def test_vb_ordinary_defaults_are_not_replaced_by_scale_heuristics():
    settings = AppSettings()
    assert settings.body_indent == settings.character_height == 26
    assert settings.horizontal_tolerance == settings.character_height // 2 == 13

    root = Path(__file__).resolve().parents[1]
    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile_text = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")
    assert "body_indent_was_auto" in app_text
    assert "horizontal_tolerance_was_auto" in app_text
    assert 'if "character_height" in values:' in app_text
    assert "body_indent_was_auto" in profile_text
    assert "horizontal_tolerance_was_auto" in profile_text
    assert 'if "character_height" in self._analysis_suggestion:' in profile_text
    assert settings.ordinary_right_divisor == 1.0
    assert settings.white_threshold_high == 999
    assert settings.white_threshold_low == 700
    assert settings.whitespace_adjustment == 2
    assert settings.upward_ratio == 1.5
    assert settings.row_step_multiplier == 1.2


def test_vb_ispoint_uses_original_two_dimensional_brightness_gate():
    rgb_sum = np.full((80, 120), 765, dtype=np.uint16)
    rgb_sum[35:46, 31:51] = 0
    assert _legacy_is_point(
        rgb_sum, 30, 40, 20, 20, 90, direction=1
    )
    assert not _legacy_is_point(
        np.full((80, 120), 765, dtype=np.uint16),
        30, 40, 20, 20, 90, direction=1,
    )


def test_vb_separator_prefers_full_white_row_then_centres_short_white_band():
    rgb_sum = np.full((100, 160), 765, dtype=np.uint16)
    separator, meta = _legacy_find_separator_y(
        rgb_sum, 20, 60,
        column_width=100, direction=1, row_height=20,
        upward_ratio=1.5, ordinary_right_divisor=1.0,
        darkness_threshold=300, white_threshold_high=999,
        white_threshold_low=700, whitespace_adjustment=2,
        top=10, x_min=0, x_max=159,
    )
    assert separator == 58
    assert meta["reason"] == "vb_full_white"
    assert meta["span"] == 98


def test_vb_separator_falls_back_from_999_toward_700_when_no_clean_row_exists():
    rgb_sum = np.full((100, 160), 765, dtype=np.uint16)
    # One black pixel in every candidate row defeats method 1 but leaves the
    # 98-pixel row roughly 990/1000 white, so method 2 should recover it.
    for y in range(47, 60):
        rgb_sum[y, 21] = 0
    separator, meta = _legacy_find_separator_y(
        rgb_sum, 20, 60,
        column_width=100, direction=1, row_height=20,
        upward_ratio=1.5, ordinary_right_divisor=1.0,
        darkness_threshold=300, white_threshold_high=999,
        white_threshold_low=700, whitespace_adjustment=2,
        top=10, x_min=0, x_max=159,
    )
    assert separator == 59
    assert meta["reason"] == "vb_brightness_fallback"
    assert 700 <= int(meta["threshold"]) < 999


def test_ordinary_drawing_auto_refine_y_is_shared_and_switchable(monkeypatch):
    import picture_capture.paddle_headwords as paddle_headwords

    calls: list[int] = []

    def fake_refiner(_gray, coarse_y, _line_height, _settings, **_kwargs):
        calls.append(int(coarse_y))
        return int(coarse_y) + 3, {"reason": "test"}

    monkeypatch.setattr(paddle_headwords, "refine_separator_y", fake_refiner)

    image = Image.new("RGB", (220, 220), "white")
    draw = ImageDraw.Draw(image)
    for y in (35, 85, 135, 185):
        draw.rectangle((20, y, 115, y + 12), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=180,
        gutter=0,
        start_y=0,
        body_indent=30,
        character_height=16,
        row_padding=2,
        detection_method="left_edge",
        follow_column_deformation=False,
        paddle_refine_separator_y=True,
    )
    refined, _ = legacy_detect_entries(image, settings)
    assert refined
    assert calls
    refined_calls = len(calls)

    calls.clear()
    settings.paddle_refine_separator_y = False
    coarse, _ = legacy_detect_entries(image, settings)
    assert coarse
    assert calls == []
    assert len(refined) == len(coarse)
    assert [entry.y for entry in refined] == [entry.y + 3 for entry in coarse]
    assert refined_calls == len(refined)


def test_ordinary_only_controls_stay_out_of_main_layout_section():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")

    schema = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "settings" / "schema.py"
    ).read_text(encoding="utf-8")

    normal_checks_start = schema.index("NORMAL_CHECKS = (")
    normal_checks_end = schema.index("OCR_COMMON_CHECKS = (", normal_checks_start)
    normal_checks = schema[normal_checks_start:normal_checks_end]
    assert '("自动精修横线 Y", "paddle_refine_separator_y")' in normal_checks
    assert '("使用自动版面参数", "ordinary_auto_layout")' in normal_checks

    quick_start = source.index("    def _build_quick_settings(")
    quick_end = source.index("\n    def ", quick_start + 10)
    quick = source[quick_start:quick_end]
    assert 'text="自动精修横线Y（通用）"' not in quick
    assert 'self.quick_bool_vars["paddle_refine_separator_y"] = refine_y_var' not in quick
    assert 'text="使用自动版面参数"' not in quick
    for label in ("单行高%：", "行间空%：", "正文缩进%：", "微调判距%："):
        assert label not in quick
    for name in (
        "ordinary_auto_columns", "ordinary_auto_start_y", "ordinary_auto_manual_x",
        "ordinary_auto_column_width", "ordinary_auto_gutter",
        "ordinary_auto_character_height", "ordinary_auto_row_padding",
    ):
        assert name not in quick
        assert name in normal_checks
    assert '"bottom_y"' not in quick

    hide_line = 'option_row, text="隐藏线框(插图除外)", variable=self.hide_var'
    hide_at = quick.index(hide_line)
    hide_tail = quick[hide_at:hide_at + 260]
    assert ').pack(side="left")' in hide_tail
    assert 'padx=(8, 0)' not in hide_tail


def test_ordinary_backup_checkbox_defaults_and_two_row_auto_layout_grid():
    settings = AppSettings()
    assert settings.paddle_refine_separator_y is True
    assert settings.follow_column_deformation is False
    assert settings.ordinary_auto_layout is True
    assert settings.ordinary_auto_columns is False
    assert settings.ordinary_auto_start_y is True
    assert settings.ordinary_auto_manual_x is True
    assert settings.ordinary_auto_column_width is False
    assert settings.ordinary_auto_gutter is False
    assert settings.ordinary_auto_character_height is False
    assert settings.ordinary_auto_row_padding is False

    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "app.py"
    ).read_text(encoding="utf-8")
    start = source.index("    def _add_check_group(")
    end = source.index("\n    def _add_collapsible_settings(", start)
    check_group = source[start:end]
    assert 'child_row = 0 if index < 3 else 1' in check_group
    assert 'child_col = index if index < 3 else index - 3' in check_group
    ordered = (
        "\"ordinary_auto_columns\"",
        "\"ordinary_auto_start_y\"",
        "\"ordinary_auto_manual_x\"",
        "\"ordinary_auto_column_width\"",
        "\"ordinary_auto_gutter\"",
        "\"ordinary_auto_character_height\"",
        "\"ordinary_auto_row_padding\"",
    )
    positions = [check_group.index(name) for name in ordered]
    assert positions == sorted(positions)

def test_ordinary_drawing_restores_vb_left_edge_gate():
    image = Image.new("RGB", (260, 240), "white")
    draw = ImageDraw.Draw(image)

    # True headwords start inside the 6 px left-edge gate.
    for y in (45, 145):
        draw.rectangle((22, y, 100, y + 12), fill="black")

    # Definition-only lines start at the body indent. The former wide-strip
    # projection treated these as candidates; the VB gate must reject them.
    for y in (95, 195):
        draw.rectangle((52, y, 150, y + 12), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=210,
        gutter=0,
        start_y=20,
        body_indent=32,
        horizontal_tolerance=6,
        character_height=18,
        row_padding=2,
        darkness_threshold=300,
        dark_area_percent=90,
        row_step_multiplier=1.2,
        detection_method="left_edge",
        follow_column_deformation=False,
        ordinary_auto_layout=False,
        paddle_refine_separator_y=False,
    )
    entries, _ = legacy_detect_entries(image, settings)

    assert len(entries) == 2
    assert abs(entries[0].y - 45) <= 3
    assert abs(entries[1].y - 145) <= 3


def test_legacy_manual_columns_and_manual_y_no_longer_change_ordinary_start():
    image = Image.new("RGB", (220, 170), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 55, 110, 66), fill="black")
    draw.rectangle((20, 105, 110, 116), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        manual_y=90,
        column_width=180,
        gutter=0,
        start_y=20,
        body_indent=20,
        horizontal_tolerance=5,
        character_height=18,
        row_padding=2,
        darkness_threshold=300,
        dark_area_percent=90,
        manual_columns=True,
        detection_method="left_edge",
        follow_column_deformation=False,
        paddle_refine_separator_y=False,
    )
    entries, _ = legacy_detect_entries(image, settings)
    assert len(entries) == 2


def test_column_tracking_percentages_scale_with_page_geometry():
    settings = AppSettings(
        column_track_radius=5.0,
        column_track_block_height=3.0,
        column_track_max_step=8.0,
    )
    radius, block, step = _column_tracking_dimensions(2000, 5800, settings)
    assert radius == 100
    assert block == 174
    assert step == 14

    radius2, block2, step2 = _column_tracking_dimensions(4000, 11600, settings)
    assert radius2 == 200
    assert block2 == 348
    assert step2 == 28


def test_ordinary_auto_layout_applies_only_checked_page_specific_fields(monkeypatch):
    import picture_capture.layout_detection as layout_detection

    estimate = SimpleNamespace(
        columns=3,
        start_y=77,
        manual_x=41,
        column_width=333,
        gutter=27,
        character_height=31,
        row_padding=4,
        bottom_y=999,
    )
    monkeypatch.setattr(
        layout_detection, "detect_layout_parameters",
        lambda _image, _settings: estimate,
    )
    settings = AppSettings(
        columns=2,
        start_y=20,
        manual_x=10,
        column_width=250,
        gutter=15,
        character_height=24,
        row_padding=2,
        ordinary_auto_layout=True,
        ordinary_auto_columns=True,
        ordinary_auto_start_y=True,
        ordinary_auto_manual_x=False,
        ordinary_auto_column_width=True,
        ordinary_auto_gutter=False,
        ordinary_auto_character_height=True,
        ordinary_auto_row_padding=False,
    )
    effective, applied = ordinary_page_layout_settings(
        Image.new("RGB", (900, 1200), "white"), settings
    )
    assert effective.columns == 3
    assert effective.start_y == 77
    assert effective.manual_x == 10
    assert effective.column_width == 333
    assert effective.gutter == 15
    assert effective.character_height == 31
    assert effective.row_padding == 2
    assert "bottom_y" not in applied
    assert settings.columns == 2  # project baseline is never mutated


def test_restored_vb_controls_are_exposed_separately_from_modern_right_ratio():
    schema_source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "settings" / "schema.py"
    ).read_text(encoding="utf-8")
    assert '("向右比例 %", "right_ratio", float)' in schema_source
    assert '("VB 向右比例 1/x", "ordinary_right_divisor", float)' in schema_source
    for name in (
        "white_threshold_high", "white_threshold_low", "whitespace_adjustment",
        "upward_ratio", "analysis_left", "analysis_right",
    ):
        assert name in schema_source


def test_ordinary_micro_tolerance_is_not_clipped_by_body_indent():
    image = Image.new("RGB", (220, 150), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 55, 110, 66), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=180,
        gutter=0,
        start_y=20,
        body_indent=5,
        horizontal_tolerance=12,
        character_height=18,
        row_padding=2,
        darkness_threshold=300,
        dark_area_percent=90,
        detection_method="left_edge",
        follow_column_deformation=False,
        ordinary_auto_layout=False,
        paddle_refine_separator_y=False,
    )
    accepted, _ = legacy_detect_entries(image, settings)
    assert len(accepted) == 1

    settings.horizontal_tolerance = 8
    rejected, _ = legacy_detect_entries(image, settings)
    assert rejected == []


def test_ordinary_micro_tolerance_controls_headword_anchor_lane():
    image = Image.new("RGB", (220, 150), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((27, 55, 110, 68), fill="black")

    settings = AppSettings(
        columns=1,
        manual_x=20,
        column_width=180,
        gutter=0,
        start_y=20,
        body_indent=30,
        horizontal_tolerance=8,
        character_height=18,
        row_padding=2,
        darkness_threshold=300,
        dark_area_percent=90,
        detection_method="left_edge",
        follow_column_deformation=False,
        ordinary_auto_layout=False,
        paddle_refine_separator_y=False,
    )
    accepted, _ = legacy_detect_entries(image, settings)
    assert len(accepted) == 1

    settings.horizontal_tolerance = 4
    rejected, _ = legacy_detect_entries(image, settings)
    assert rejected == []


def test_ordinary_y_refinement_receives_full_resolution_coordinates(monkeypatch):
    import picture_capture.paddle_headwords as paddle_headwords

    seen: list[tuple[tuple[int, int], int]] = []

    def fake_refiner(gray, coarse_y, _line_height, _settings, **_kwargs):
        seen.append((tuple(gray.shape), int(coarse_y)))
        return int(coarse_y), {"reason": "test"}

    monkeypatch.setattr(paddle_headwords, "refine_separator_y", fake_refiner)

    image = Image.new("RGB", (2400, 1800), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((120, 1200, 500, 1240), fill="black")
    settings = AppSettings(
        columns=1,
        manual_x=120,
        column_width=1800,
        gutter=0,
        start_y=100,
        body_indent=90,
        horizontal_tolerance=20,
        character_height=45,
        row_padding=5,
        darkness_threshold=300,
        dark_area_percent=95,
        detection_method="left_edge",
        follow_column_deformation=False,
        paddle_refine_separator_y=True,
    )
    entries, _ = legacy_detect_entries(image, settings)
    assert entries and seen
    # Ordinary candidate and VB separator placement are already full-resolution;
    # the optional modern refiner receives the same source-resolution Y axis.
    assert seen[0][0][0] == 1800
    assert seen[0][1] > 1000


def test_ordinary_layout_threshold_policy_remains_available_for_layout_analysis():
    import numpy as np

    gray = np.array([
        [30, 90, 150, 230],
        [40, 100, 160, 240],
        [50, 110, 170, 250],
        [60, 120, 180, 245],
    ], dtype=np.uint8)
    fixed = _left_edge_ink_mask(
        gray, AppSettings(analysis_threshold_mode="fixed", darkness_threshold=300)
    )
    assert fixed.dtype == bool and fixed.shape == gray.shape
    assert fixed[0, 0] and fixed[0, 1]
    assert not fixed[1, 1] and not fixed[0, 2]

    auto = _left_edge_ink_mask(gray, AppSettings(analysis_threshold_mode="auto"))
    adaptive = _left_edge_ink_mask(gray, AppSettings(analysis_threshold_mode="adaptive"))
    assert auto.dtype == bool and adaptive.dtype == bool

    processing_source = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "processing.py"
    ).read_text(encoding="utf-8")
    start = processing_source.index("def _detect_entries_left_edge(")
    end = processing_source.index("\ndef detect_entries(", start)
    ordinary = processing_source[start:end]
    assert "_legacy_is_point(" in ordinary
    assert "_legacy_find_separator_y(" in ordinary
    assert "ordinary_right_divisor" in ordinary
    assert "white_threshold_high" in ordinary
    assert "white_threshold_low" in ordinary
    assert "whitespace_adjustment" in ordinary
    assert "upward_ratio" in ordinary
    assert "_analysis_image(" not in ordinary
    assert "density_floor" not in ordinary


def test_analysis_threshold_modes_are_effective():
    import numpy as np

    gray = np.array([
        [40, 80, 140, 220],
        [50, 90, 150, 230],
        [60, 100, 160, 240],
        [70, 110, 170, 250],
    ], dtype=np.uint8)
    fixed = _analysis_ink_mask(gray, AppSettings(analysis_threshold_mode="fixed", darkness_threshold=300))
    # RGB-sum threshold 300 corresponds to grayscale threshold 100.
    assert fixed[0, 0] and fixed[1, 1]
    assert not fixed[2, 1] and not fixed[0, 2]

    auto = _analysis_ink_mask(gray, AppSettings(analysis_threshold_mode="auto"))
    otsu = _analysis_ink_mask(gray, AppSettings(analysis_threshold_mode="otsu"))
    assert np.array_equal(auto, otsu)
    adaptive = _analysis_ink_mask(gray, AppSettings(analysis_threshold_mode="adaptive"))
    assert adaptive.shape == gray.shape and adaptive.dtype == bool


def test_sidecar_only_v3_project_restores_components(tmp_path):
    root = tmp_path / "sidecar"
    root.mkdir()
    Image.new("RGB", (8, 8), "white").save(root / "1.jpg")
    # First opening creates the managed storage; remove settings to emulate a
    # sidecar-only migration project.
    ProjectState.open(root)
    settings_path(root).unlink(missing_ok=True)
    profile_path(root).write_text(
        '{"format":"picture-capture-dictionary-profile-v3","preset":"cjk_bracket_display",'
        '"layout":{"writing_mode":"vertical-rl","text_direction":"rtl","columns":3,'
        '"columns_policy":"fixed","column_separator":"absent","analysis_threshold_mode":"fixed"},'
        '"ocr":{"semantic_language":"jpn","paddle_language":"japan",'
        '"tesseract_language":"jpn","use_textline_orientation":true}}',
        encoding="utf-8",
    )
    restored = ProjectState.open(root).settings
    assert restored.layout_writing_mode == "vertical-rl"
    assert restored.layout_text_direction == "rtl"
    assert restored.layout_transform == "rotate_ccw90"
    assert restored.columns == 3
    assert restored.layout_columns_policy == "fixed"
    assert restored.layout_column_separator_mode == "absent"
    assert restored.analysis_threshold_mode == "fixed"
    assert restored.ocr_language == "jpn"
    assert restored.tesseract_language == "jpn"
    assert restored.paddle_use_textline_orientation is True


def test_numbered_profile_accepts_three_and_four_digit_prefixes():
    profile = load_dictionary_profile(preset="numbered_prefix", language="eng")
    settings = AppSettings(ocr_language="eng")
    for text, expected in (
        ("100. anniversary", "anniversary"),
        ("1234. word", "word"),
        ("100 word", "word"),
    ):
        parsed = parse_headword_text(text, settings, profile=profile)
        assert parsed is not None and parsed.normalized == expected


def test_vertical_main_editor_is_a_real_text_widget_not_a_canvas_proxy():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def _draw_entry_overlay(")
    end = text.index("    def _remove_entry_overlay(", start)
    block = text[start:end]

    assert "VerticalWordText(" in block
    assert 'cursor="xterm"' in block
    assert "window=editor" in block
    assert "width=vertical_box[2] - vertical_box[0]" in block
    assert "height=vertical_box[3] - vertical_box[1]" in block
    assert "vertical_ocr_menu_layout(" in block
    assert "vertical_overlay_layout(" in block

    # The old non-editable proxy/popup architecture must not return.
    assert "proxy_box_item" not in block
    assert "label_item" not in block
    assert "open_vertical_editor" not in block
    assert "_suppress_next_canvas_left_click" not in text
    assert 'if rtl:\n            editor.configure(justify="right")' in block


def test_round1_blocking_ui_paths_use_background_workers():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")

    assert "def _start_ui_worker(" in text
    assert "self._ui_worker_queue.put(event)" in text
    assert "def _poll_ui_worker_queue(" in text

    settings_start = text.index("class SettingsDialog")
    settings_check = text.index("    def check_ocr_engines(self) -> None:", settings_start)
    settings_check_end = text.index("\n\ndef _review_window_dimensions", settings_check)
    settings_block = text[settings_check:settings_check_end]
    assert "self.parent.show_environment_center()" in settings_block

    app_start = text.index("class PictureCaptureApp")
    main_check = text.index("    def check_ocr_engines(self) -> None:", app_start)
    main_check_end = text.index("\n    def detect_layout_current", main_check)
    assert "self.show_environment_center()" in text[main_check:main_check_end]

    environment_center = (
        Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "environment_center.py"
    ).read_text(encoding="utf-8")
    refresh_start = environment_center.index("    def refresh(self) -> None:")
    refresh_end = environment_center.index("\n    def _open_ocr_settings", refresh_start)
    refresh = environment_center[refresh_start:refresh_end]
    assert "def worker():" in refresh
    assert 'self.app._start_ui_worker(f"environment-center-' in refresh

    page_request = text.index("    def _request_page_load(", app_start)
    page_load = text.index("    def load_page(", page_request)
    page_block = text[page_request:page_load]
    assert "with Image.open(page) as opened:" in page_block
    assert 'self._start_ui_worker("page-load"' in page_block
    select_start = text.index("    def on_page_select(", app_start)
    assert "self._request_page_load(index)" in text[select_start:page_request]

    project_start = text.index("    def _load_project(", app_start)
    project_end = text.index("\n    def on_page_select", project_start)
    project_block = text[project_start:project_end]
    worker_pos = project_block.index("        def worker():")
    done_pos = project_block.index("        def done(result)")
    assert worker_pos < project_block.index("migrate_legacy_project(", worker_pos) < done_pos
    assert worker_pos < project_block.index("ProjectState.open(root)", worker_pos) < done_pos
    assert worker_pos < project_block.index("with Image.open(page) as opened:", worker_pos) < done_pos
    assert "self._start_ui_worker(" in project_block
    assert '"project-load", worker, done, failed, wait_on_close=True' in project_block

    recent_start = text.index("    def open_recent_project(", app_start)
    recent_end = text.index("\n    @staticmethod\n    def _attach_tooltip", recent_start)
    recent_block = text[recent_start:recent_end]
    rebuild_start = recent_block.index("        def rebuild(")
    refresh_start = recent_block.index("        def refresh_recent_data(")
    rebuild_block = recent_block[rebuild_start:refresh_start]
    assert "recent_project_details(" not in rebuild_block
    assert "Image.open(" not in rebuild_block
    assert "recent_project_details(row)" in recent_block[refresh_start:]
    assert "with Image.open(preview_path) as opened:" in recent_block[refresh_start:]

    picdic_start = text.index("    def build_picdic(", app_start)
    picdic_end = text.index("\n    def _order_key", picdic_start)
    picdic_block = text[picdic_start:picdic_end]
    assert "self._start_batch_task(" in picdic_block
    assert "should_stop=self._batch_stop_event.is_set" in picdic_block


def test_round1_picdic_cancel_is_atomic(tmp_path):
    root = tmp_path / "dictionary"
    pww = qt_root(root) / "PWW"
    pww.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(pww / "0001_0001.png")
    (pww / "0001.PWWords").write_text(
        "0001|1|alpha|0001_0001.png\n", encoding="utf-8"
    )

    try:
        build_picdic_package(root, should_stop=lambda: True)
    except PicDicBuildCancelled:
        pass
    else:
        raise AssertionError("expected cooperative PicDic cancellation")

    out = qt_root(root) / "PicDic"
    assert not list(out.glob("*.tmp")) if out.exists() else True
    assert not list(out.glob("*.dsl")) if out.exists() else True
    assert not list(out.glob("*.zip")) if out.exists() else True



def test_round2_heavy_finalizers_and_review_crops_stay_off_tk():
    root = Path(__file__).resolve().parents[1]
    app_text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile_text = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")

    app_start = app_text.index("class PictureCaptureApp")
    training_start = app_text.index("    def export_training_package(", app_start)
    training_end = app_text.index("\n    def show_help_dialog", training_start)
    training = app_text[training_start:training_end]
    assert 'items: list[object] = ["__prepare__"]' in training
    assert "context_files[:] = copy_project_context(project.root, staging)" in training
    assert "make_training_zip(" in training
    assert "should_stop=self._batch_stop_event.is_set" in training
    assert "shutil.rmtree(staging, ignore_errors=True)" in training
    done_start = training.index("        def done(")
    done = training[done_start:]
    assert "shutil.rmtree(staging, ignore_errors=True)" not in done
    assert 'self._start_ui_worker(' in done

    layout_start = app_text.index("    def detect_layout_consistency_selected(", app_start)
    layout_end = app_text.index("\n    @staticmethod\n    def _normalize_suffix", layout_start)
    layout = app_text[layout_start:layout_end]
    done_start = layout.index("        def done(")
    layout_done = layout[done_start:]
    assert "def finalize_report():" in layout_done
    assert 'self._start_ui_worker(' in layout_done
    finalized_start = layout_done.index("        def finalized(")
    ui_finalized = layout_done[finalized_start:]
    assert 'target.open("w"' not in ui_finalized
    assert "statistics.fmean(" not in ui_finalized

    review_start = app_text.index("class ReviewWindow")
    review_end = app_text.index("class PictureCaptureApp", review_start)
    review = app_text[review_start:review_end]
    request_start = review.index("    def _request_render_rows(")
    render_start = review.index("    def render_rows(", request_start)
    render_end = review.index("\n    def _candidate_for_entry", render_start)
    request = review[request_start:render_start]
    render = review[render_start:render_end]
    assert "with Image.open(page) as opened:" in request
    assert "Image.Resampling.LANCZOS" in request
    assert "self.parent._start_ui_worker(" in request
    assert "Image.Resampling.LANCZOS" not in render
    assert "_review_line_box(" not in render
    assert "ImageTk.PhotoImage(themed_display_image(crop, self.parent.appearance_mode))" in render
    assert "self.render_rows()" not in review

    preview_start = profile_text.index("    def _refresh_template_preview(")
    preview_end = profile_text.index("\n    @staticmethod\n    def _mode_row", preview_start)
    preview = profile_text[preview_start:preview_end]
    assert "with Image.open(path) as opened:" in preview
    assert "derive_geometry(" in preview
    assert "self.parent._start_ui_worker(" in preview
    worker_start = preview.index("        def worker():")
    done_start = preview.index("        def done(", worker_start)
    worker = preview[worker_start:done_start]
    assert "ImageTk.PhotoImage" not in worker
    assert "themed_display_image(" in preview[done_start:]
    assert 'preview, getattr(self.parent, "appearance_mode", "light")' in preview[done_start:]


def test_round2_training_zip_cancel_is_atomic(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "dataset_manifest.json").write_text("{}", encoding="utf-8")
    (staging / "large.bin").write_bytes(b"x" * 1024)
    target = tmp_path / "training.zip"

    try:
        make_training_zip(staging, target, should_stop=lambda: True)
    except TrainingExportCancelled:
        pass
    else:
        raise AssertionError("expected cooperative training ZIP cancellation")

    assert not target.exists()
    assert not target.with_name(f".{target.name}.tmp").exists()



def test_round3_long_tail_ui_paths_are_backgrounded_and_snapshotted():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    app_start = text.index("class PictureCaptureApp")

    reload_start = text.index("    def _request_wordslist_reload(", app_start)
    reload_end = text.index("\n    def open_recent_project", reload_start)
    reload_block = text[reload_start:reload_end]
    assert "read_noncomment_lines(path)" in reload_block
    assert 'self._start_ui_worker("wordslist-reload"' in reload_block

    settings_start = text.index("class SettingsDialog")
    settings_end = text.index("class ReviewWindow", settings_start)
    settings = text[settings_start:settings_end]
    assert "self.parent._request_wordslist_reload(persist=False, redraw=False)" in settings

    review_start = text.index("class ReviewWindow")
    review_end = text.index("class PictureCaptureApp", review_start)
    review = text[review_start:review_end]
    assert "self.parent._request_wordslist_reload(" in review
    assert "reload_wordslist_reference(Path(chosen)" not in review

    order_start = text.index("    def check_headword_order(", app_start)
    order_end = text.index("\n    def _show_text_report", order_start)
    order = text[order_start:order_end]
    all_pages_branch = order[order.index("        if all_pages:"):]
    assert 'self._start_batch_task(' in all_pages_branch
    assert '"所有词头顺序核对"' in all_pages_branch
    assert 'self._start_ui_worker(' in all_pages_branch
    assert '"headword-order-finalize"' in all_pages_branch
    worker_start = all_pages_branch.index("            def worker(")
    worker_done = all_pages_branch.index("            def done(", worker_start)
    worker = all_pages_branch[worker_start:worker_done]
    assert "read_pdic(pdic_path(page))" in worker
    assert "self.settings" not in worker
    finalize_start = all_pages_branch.index("                def finalize():")
    finalized_start = all_pages_branch.index("                def finalized(", finalize_start)
    finalize = all_pages_branch[finalize_start:finalized_start]
    assert "sorted(sequence" in finalize

    for name, next_name in (
        ("auto_detect_current", "paddle_detect_current"),
        ("ocr_current", "export_text"),
        ("split_lines_current", "split_whole_current"),
        ("split_whole_current", "_crop_settings_defaults"),
        ("import_legacy_words", "_default_old_new_compare_source"),
    ):
        start = text.index(f"    def {name}(", app_start)
        end = text.index(f"\n    def {next_name}(", start)
        block = text[start:end]
        assert "self._start_batch_task(" in block

    fill_start = text.index("    def fill_existing_headwords(", app_start)
    fill_end = text.index("\n    def import_legacy_words", fill_start)
    fill = text[fill_start:fill_end]
    ensure_start = fill.index("        def ensure_mapping()")
    worker_start = fill.index("        def worker(", ensure_start)
    ensure = fill[ensure_start:worker_start]
    assert "self._word_fill_source_mapping =" not in ensure
    assert "settings_snapshot = replace(self.settings)" in fill
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in fill
    done_start = fill.index("        def done(", worker_start)
    assert "self._word_fill_source_mapping = mapping" in fill[done_start:]

    prefetch_start = review.index("    def _schedule_adjacent_preload(")
    prefetch_end = review.index("\n    def change_page(", prefetch_start)
    prefetch = review[prefetch_start:prefetch_end]
    worker_start = prefetch.index("            def worker(")
    worker = prefetch[worker_start:]
    assert "local_anchor_index=anchor_index" in worker
    assert "self.parent.current_index" not in worker
    assert "self.parent._ppp_read_path" not in worker


def test_round3_wordslist_stream_reader_supports_legacy_encodings(tmp_path):
    from picture_capture.models import read_noncomment_lines

    samples = {
        "utf8.txt": ("alpha\n'comment\nβeta\n", "utf-8"),
        "utf16.txt": ("繁體\n詞條\n", "utf-16"),
        "gb.txt": ("简体\n词条\n", "gb18030"),
        "big5.txt": ("繁體\n詞條\n", "big5"),
    }
    for name, (content, encoding) in samples.items():
        path = tmp_path / name
        path.write_bytes(content.encode(encoding))
        expected = [
            line for line in content.splitlines()
            if line.strip() and not line.lstrip().startswith("'")
        ]
        assert read_noncomment_lines(path) == expected


def test_round3_wordslist_reader_does_not_materialize_full_text_source():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "models.py"
    ).read_text(encoding="utf-8")
    start = source.index("def read_noncomment_lines(")
    block = source[start:]
    assert "iter_text_lines_detected" in block
    assert "read_text_detected" not in block
    assert ".splitlines()" not in block



def test_concurrency_atomic_text_replace_failure_preserves_previous_file(tmp_path, monkeypatch):
    import pytest
    import picture_capture.formats as formats

    target = tmp_path / "page.pdic"
    target.write_text("old-complete\n", encoding="utf-8")
    original_replace = formats.os.replace

    def fail_publish(src, dst):
        if Path(dst) == target:
            raise OSError("injected replace failure")
        return original_replace(src, dst)

    monkeypatch.setattr(formats.os, "replace", fail_publish)
    with pytest.raises(OSError, match="injected replace failure"):
        formats.write_text_atomic(target, "new-complete\n")

    assert target.read_text(encoding="utf-8") == "old-complete\n"
    assert not list(tmp_path.glob(".page.pdic.*.tmp"))


def test_concurrency_picdic_pair_rolls_back_when_second_publish_fails(tmp_path, monkeypatch):
    import pytest
    import picture_capture.picdic as picdic

    root = tmp_path / "dictionary"
    pww = qt_root(root) / "PWW"
    pww.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(pww / "0001_0001.png")
    (pww / "0001.PWWords").write_text(
        "0001|1|alpha|0001_0001.png\n", encoding="utf-8"
    )

    out = qt_root(root) / "PicDic"
    out.mkdir(parents=True)
    dsl = out / "PicDic_dictionary.dsl"
    archive = out / "PicDic_dictionary.dsl.files.zip"
    dsl.write_text("old-dsl", encoding="utf-8")
    archive.write_bytes(b"old-zip")

    original_replace = picdic.os.replace

    def fail_second_publish(src, dst):
        src_path = Path(src)
        dst_path = Path(dst)
        if dst_path == archive and src_path.suffix == ".tmp":
            raise OSError("injected zip publish failure")
        return original_replace(src, dst)

    monkeypatch.setattr(picdic.os, "replace", fail_second_publish)
    with pytest.raises(OSError, match="injected zip publish failure"):
        picdic.build_picdic_package(root)

    assert dsl.read_text(encoding="utf-8") == "old-dsl"
    assert archive.read_bytes() == b"old-zip"
    assert not list(out.glob("*.tmp"))
    assert not list(out.glob("*.bak"))


def test_focused_filter_streams_complete_batches_and_prefetches_next_batch():
    fake = SimpleNamespace(
        filtered_targets=[{} for _ in range(45)],
        _filter_scan_complete=False,
        _focused_batch_size=lambda: 20,
    )
    assert ReviewWindow._filter_available_target_count(fake) == 40
    fake._filter_scan_complete = True
    assert ReviewWindow._filter_available_target_count(fake) == 45

    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    review_start = app.index("class ReviewWindow")
    review_end = app.index("class PictureCaptureApp", review_start)
    review = app[review_start:review_end]

    focused_start = review.index("    def run_focused_filter(")
    focused_end = review.index("\n    def _render_filter_batch(", focused_start)
    focused = review[focused_start:focused_end]
    assert "needed_for_next" in focused
    assert "if len(additions) >= needed_for_next:" in focused
    assert "start_remaining_scan(" in focused
    assert "self._schedule_filter_next_batch_preload()" in focused
    assert 'f"focused-filter-prefetch-{id(self)}"' in focused
    assert "_filter_batch_render_cache" in focused
    assert "下一批已在后台预生成，即将显示" in focused
    assert "return (total // batch_size) * batch_size" in focused


def test_concurrency_review_tracks_critical_workers_and_stale_results():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")

    worker_start = app.index("    def _ui_worker_key_active(")
    worker_end = app.index("\n    def _configure_main_workspace_styles", worker_start)
    workers = app[worker_start:worker_end]
    assert "_ui_worker_active" in workers
    assert "_ui_worker_close_wait" in workers
    assert "generation == self._ui_worker_generations.get(key)" in workers
    assert "not self._ui_close_requested" in workers
    assert "self._ui_worker_active.discard(token)" in workers
    assert "self._ui_worker_close_wait.discard(token)" in workers
    assert "if self._ui_close_requested and not self._ui_worker_close_wait:" in workers

    close_start = app.index("    def on_close(")
    close_end = app.index("\n    def _build_ui", close_start)
    close = app[close_start:close_end]
    assert "if self._ui_worker_close_wait:" in close
    assert "self.withdraw()" in close
    assert "正在完成后台文件操作" in close

    project_start = app.index("    def _load_project(")
    project_end = app.index("\n    def on_page_select", project_start)
    project = app[project_start:project_end]
    assert 'self._ui_worker_key_active("project-load")' in project
    assert 'self._ui_worker_key_active("profile-validation")' in project
    assert 'wait_on_close=True' in project

    sequential = app[app.index("    def _start_batch_task("):app.index("    def _start_parallel_batch_task(")]
    parallel = app[app.index("    def _start_parallel_batch_task("):app.index("    def _poll_batch_queue(")]
    for block in (sequential, parallel):
        assert 'self._ui_worker_key_active("project-load")' in block
        assert 'self._ui_worker_key_active("profile-validation")' in block
        assert "self._ui_close_requested" in block

    validate_start = profile.index("    def validate_profile(")
    validate_end = profile.index("\n    def _poll_validation_queue", validate_start)
    validate = profile[validate_start:validate_end]
    assert 'self.parent._start_ui_worker(' in validate
    assert '"profile-validation"' in validate
    assert "wait_on_close=True" in validate
    assert "stop_event.is_set()" in validate
    assert "self.project.images[index]" not in validate[validate.index("        def worker():"):]

    close_profile = profile[profile.index("    def _close_without_save("):]
    assert "self._validation_close_requested = True" in close_profile
    assert "self._validation_stop_event.set()" in close_profile
    assert "正在安全结束当前测试页" in close_profile


def test_concurrency_review_atomic_ocr_cache_and_timeouts_are_enforced():
    root = Path(__file__).resolve().parents[1]
    paddle = (root / "src" / "picture_capture" / "paddle_headwords.py").read_text(encoding="utf-8")
    processing = (root / "src" / "picture_capture" / "processing.py").read_text(encoding="utf-8")

    assert "_QUALITY_SUMMARY_LOCK = threading.Lock()" in paddle
    assert "with _QUALITY_SUMMARY_LOCK:" in paddle
    assert "_atomic_write_json(cache_path, payload)" in paddle
    assert "compact_ocr_cache_payload(payload)" in paddle
    assert "_OCR_REGENERABLE_SIDECAR_SUFFIXES" in paddle
    assert "for obsolete in _regenerable_sidecars(cache_path):" in paddle
    assert "timeout=120" in paddle
    assert "except subprocess.TimeoutExpired" in paddle
    assert "timeout=120" in processing
    assert "except subprocess.TimeoutExpired" in processing


def test_concurrency_review_workers_use_snapshots_not_live_app_state():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")

    check_start = app.index("    def check_ocr_engines(self) -> None:", app.index("class PictureCaptureApp"))
    check_end = app.index("\n    def detect_layout_current", check_start)
    check = app[check_start:check_end]
    assert "self.show_environment_center()" in check

    environment_center = (root / "src" / "picture_capture" / "environment_center.py").read_text(encoding="utf-8")
    refresh_start = environment_center.index("    def refresh(self) -> None:")
    refresh_end = environment_center.index("\n    def _open_ocr_settings", refresh_start)
    refresh = environment_center[refresh_start:refresh_end]
    worker = refresh[refresh.index("        def worker():"):refresh.index("        def done(", refresh.index("        def worker():"))]
    assert "tesseract_status(executable, language)" in worker
    assert "opencc_runtime_status(retry=True)" in worker

    split_start = app.index("    def batch_split_whole(")
    split_end = app.index("\n    def repair_pdic_order_selected_scope", split_start)
    split = app[split_start:split_end]
    worker = split[split.index("        def worker("):split.index("        def done(", split.index("        def worker("))]
    assert "self._ppp_read_path" not in worker
    assert "ppp_read_path_for_image(page)" in worker

    restore_start = app.index("    def restore_from_pdic_backup(")
    restore_end = app.index("\n    def restore_from_merged_pdic", restore_start)
    restore = app[restore_start:restore_end]
    assert "settings_snapshot = replace(self.settings)" in restore
    worker = restore[restore.index("        def worker("):restore.index("        def done(", restore.index("        def worker("))]
    assert "self.settings" not in worker
    assert "derive_nominal_geometry(width, height, settings_snapshot)" in worker

    preview_start = profile.index("    def _refresh_template_preview(")
    preview_end = profile.index("\n    @staticmethod\n    def _mode_row", preview_start)
    preview = profile[preview_start:preview_end]
    worker = preview[preview.index("        def worker():"):preview.index("        def done(", preview.index("        def worker():"))]
    assert "len(self.sample_indices)" not in worker
    assert "sample_count" in worker

    analysis_start = profile.index("    def analyze_representative_pages(")
    analysis_end = profile.index("\n    def _poll_analysis_queue", analysis_start)
    analysis = profile[analysis_start:analysis_end]
    worker = analysis[analysis.index("        def worker()"):analysis.index("        threading.Thread", analysis.index("        def worker()"))]
    assert "self.project" not in worker
    assert "self._analysis_queue" not in worker
    assert "result_queue.put" in worker



def test_concurrency_audit_p0_p1_guards_are_present():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    profile = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")
    training = (root / "src" / "picture_capture" / "training_export.py").read_text(encoding="utf-8")

    poll_start = app.index("    def _poll_ui_worker_queue(")
    poll_end = app.index("\n    def _configure_main_workspace_styles", poll_start)
    assert "_ui_worker_active" in app[poll_start:poll_end]

    load_start = app.index("    def _load_project(")
    load_end = app.index("\n    def on_page_select", load_start)
    load = app[load_start:load_end]
    assert "root == Path(self.project.root).expanduser().resolve()" in load
    assert load.index("root == Path(self.project.root).expanduser().resolve()") < load.index("def worker():")

    profile_open_start = app.index("    def open_project_profile(")
    profile_open_end = app.index("\n    def open_project_details", profile_open_start)
    assert "if self._batch_active:" in app[profile_open_start:profile_open_end]

    validate_start = profile.index("    def validate_profile(")
    validate_end = profile.index("\n    def _poll_validation_queue", validate_start)
    assert "if self.parent._batch_active:" in profile[validate_start:validate_end]

    export_start = app.index("    def export_training_package(")
    export_end = app.index("\n    def show_help_dialog", export_start)
    export = app[export_start:export_end]
    assert 'startswith("training-cleanup-")' in export
    assert '%Y%m%d_%H%M%S_%f' in export
    assert "uuid.uuid4().hex" in training


def test_project_profile_legacy_workers_drop_results_while_closing():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "picture_capture" / "profile_setup.py").read_text(encoding="utf-8")
    assert "self._closing = False" in text
    for name in (
        "_start_sample_thumbnail_load",
        "_poll_sample_thumbnail_load",
        "_start_sample_thumbnail_slot_load",
        "_poll_sample_thumbnail_slot_load",
        "analyze_representative_pages",
        "_poll_analysis_queue",
        "validate_profile",
    ):
        start = text.index(f"    def {name}(")
        next_def = text.find("\n    def ", start + 8)
        block = text[start: next_def if next_def >= 0 else len(text)]
        assert "_closing" in block



def test_crop_file_transaction_rolls_back_complete_previous_set(tmp_path, monkeypatch):
    from picture_capture.processing import _publish_file_transaction

    first = tmp_path / "page_SW_000.png"
    second = tmp_path / "page.PSWords"
    stale = tmp_path / "page_SW_999.png"
    first.write_text("old-image", encoding="utf-8")
    second.write_text("old-manifest", encoding="utf-8")
    stale.write_text("old-stale", encoding="utf-8")
    first_tmp = tmp_path / ".first.tmp"
    second_tmp = tmp_path / ".second.tmp"
    first_tmp.write_text("new-image", encoding="utf-8")
    second_tmp.write_text("new-manifest", encoding="utf-8")

    import os
    real_replace = os.replace

    def fail_second_publish(src, dst):
        if Path(src) == second_tmp:
            raise OSError("injected manifest publish failure")
        return real_replace(src, dst)

    monkeypatch.setattr("picture_capture.processing.os.replace", fail_second_publish)
    try:
        _publish_file_transaction(
            [(first_tmp, first), (second_tmp, second)],
            stale_paths=[stale],
        )
    except OSError:
        pass
    else:
        raise AssertionError("expected injected publish failure")

    assert first.read_text(encoding="utf-8") == "old-image"
    assert second.read_text(encoding="utf-8") == "old-manifest"
    assert stale.read_text(encoding="utf-8") == "old-stale"
    assert not list(tmp_path.glob(".*.bak"))
    assert not first_tmp.exists()
    assert not second_tmp.exists()


def test_crop_exports_stage_pngs_manifest_and_crop_plan_before_publish():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "picture_capture" / "processing.py").read_text(encoding="utf-8")

    assert "def _publish_file_transaction(" in text
    assert "def _stage_page_crop_plan(" in text
    assert "uuid.uuid4().hex" in text

    single_start = text.index("def split_single_lines(")
    single_end = text.index("\ndef _special_bounds", single_start)
    single = text[single_start:single_end]
    assert "_stage_crop(" in single
    assert "_stage_text_file(" in single
    assert "_publish_file_transaction(" in single

    whole_start = text.index("def split_whole_entries(")
    whole_end = text.index("\ndef append_crop_log", whole_start)
    whole = text[whole_start:whole_end]
    assert "_stage_page_crop_plan(" in whole
    assert "_publish_file_transaction(" in whole
    assert '.PWWords"' in whole

    ill_start = text.index("def split_illustrations(")
    ill_end = text.index("\ndef append_illustration_crop_log", ill_start)
    illustrations = text[ill_start:ill_end]
    assert "_stage_page_crop_plan(" in illustrations
    assert "_publish_file_transaction(" in illustrations
    assert '.PPPictures"' in illustrations



def test_crop_transaction_preserves_backup_when_rollback_itself_fails(tmp_path, monkeypatch):
    from picture_capture.processing import _publish_file_transaction

    first = tmp_path / "page_SW_000.png"
    second = tmp_path / "page.PSWords"
    first.write_text("old-image", encoding="utf-8")
    second.write_text("old-manifest", encoding="utf-8")
    first_tmp = tmp_path / ".first.tmp"
    second_tmp = tmp_path / ".second.tmp"
    first_tmp.write_text("new-image", encoding="utf-8")
    second_tmp.write_text("new-manifest", encoding="utf-8")

    import os
    real_replace = os.replace
    restore_attempted = False

    def fail_publish_and_one_restore(src, dst):
        nonlocal restore_attempted
        src_path = Path(src)
        dst_path = Path(dst)
        if src_path == second_tmp:
            raise OSError("injected publish failure")
        if src_path.name.startswith(f".{first.name}.") and src_path.suffix == ".bak":
            restore_attempted = True
            raise OSError("injected rollback failure")
        return real_replace(src, dst)

    monkeypatch.setattr(
        "picture_capture.processing.os.replace", fail_publish_and_one_restore,
    )
    try:
        _publish_file_transaction([(first_tmp, first), (second_tmp, second)])
    except RuntimeError as exc:
        assert "已保留隐藏 .bak 恢复副本" in str(exc)
    else:
        raise AssertionError("expected rollback RuntimeError")

    assert restore_attempted
    backups = list(tmp_path.glob(".*.bak"))
    assert backups
    assert any(path.read_text(encoding="utf-8") == "old-image" for path in backups)


def test_headword_order_finalizer_blocks_new_batches_until_snapshot_report_finishes():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")

    sequential_start = text.index("    def _start_batch_task(")
    parallel_start = text.index("    def _start_parallel_batch_task(", sequential_start)
    sequential = text[sequential_start:parallel_start]
    parallel_end = text.index("\n    def _poll_batch_queue", parallel_start)
    parallel = text[parallel_start:parallel_end]
    expected = 'self._ui_worker_key_active("headword-order-finalize")'
    assert expected in sequential
    assert expected in parallel

def test_v214_application_icon_is_packaged_and_propagated_to_toplevels():
    root = Path(__file__).resolve().parents[1]
    icon = root / "src" / "picture_capture" / "data" / "app_icon.png"
    assert icon.is_file()
    assert icon.stat().st_size > 0

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"data/*.png"' in pyproject

    app_source = (root / "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    assert "self.iconphoto(True, self._app_icon_photo)" in app_source
    assert "self.iconphoto(False, self._app_icon_photo)" in app_source
    assert "self._app_icon_registered = True" in app_source
    assert 'self.bind_class("Toplevel", "<Map>", self._app_icon_toplevel_mapped, add="+")' in app_source
    handler_start = app_source.index("    def _app_icon_toplevel_mapped(")
    handler_end = app_source.index("\n    def ", handler_start + 10)
    handler = app_source[handler_start:handler_end]
    assert "isinstance(widget, tk.Toplevel)" in handler
    assert 'getattr(widget, "_pc_app_icon_applied", False)' in handler
    assert "widget._pc_app_icon_applied = True" in handler
    assert "widget.iconphoto(False, self._app_icon_photo)" in handler

    smoke = (root / "scripts" / "gui_smoke.py").read_text(encoding="utf-8")
    assert 'if app._app_icon_photo is None:' in smoke
    assert '"Packaged application icon failed to load: "' in smoke
    assert 'raise RuntimeError("Application icon could not be registered")' in smoke




def test_oversized_cjk_box_recovers_each_physical_display_head(monkeypatch):
    """0007 regression: one giant 厂广安 box must not collapse four visual heads."""
    settings = AppSettings(
        ocr_language="chi_tra",
        character_height=100,
        profile_parser_controls_version=1,
        profile_cjk_allow_single_headword=True,
    )
    profile = load_dictionary_profile(
        preset="cjk_visual", language="chi_tra",
    )
    band = Image.new("RGB", (360, 1000), "white")
    giant = OCRRecord("厂广安", 0.9949, (0, 80, 317, 850))
    records = [
        OCRRecord("正文", 0.99, (130, 0, 350, 105)),
        OCRRecord("正文", 0.99, (130, 860, 350, 965)),
        giant,
    ]
    runs = [(100, 190), (285, 380), (480, 575), (675, 775)]
    monkeypatch.setattr(
        paddle_headwords,
        "_cjk_visual_projection_runs",
        lambda *_args, **_kwargs: (90, list(runs)),
    )
    monkeypatch.setattr(
        paddle_headwords,
        "_header_cutoff",
        lambda *_args, **_kwargs: 0,
    )

    words = iter(("暖", "厂", "广", "安"))

    class Result:
        def __init__(self, word):
            self.json = {
                "res": {
                    "rec_texts": [word],
                    "rec_scores": [0.96],
                    "rec_boxes": [[2, 3, 70, 78]],
                }
            }

    class Engine:
        def predict(self, _image, **_kwargs):
            return [Result(next(words))]

    recovered, details = _recover_oversized_cjk_ocr_records(
        records,
        band,
        settings,
        profile,
        engine=Engine(),
    )

    children = [
        record for record in recovered
        if record.recovery == "oversized_multi_entry_local_ocr"
    ]
    assert [record.text for record in children] == ["暖", "厂", "广", "安"]
    assert [record.box[1:4:2] for record in children] == [
        (100, 190), (285, 380), (480, 575), (675, 775),
    ]
    assert all(record.parent_box == giant.box for record in children)
    assert all(abs(record.confidence - 0.96) < 1e-6 for record in children)
    assert giant not in recovered
    assert len(details) == 1
    assert details[0]["parent_text"] == "厂广安"
    assert details[0]["visual_run_count"] == 4
    assert details[0]["recovered_count"] == 4
    assert details[0]["applied"] is True



def test_recovered_oversized_cjk_children_are_auto_selected_and_refined(
    monkeypatch,
):
    """Recovered physical heads must not be rejected by a second size-ratio gate."""
    settings = AppSettings(
        ocr_language="chi_tra",
        character_height=100,
        profile_parser_controls_version=1,
        profile_cjk_allow_single_headword=True,
        profile_cjk_require_visual_evidence=True,
        profile_cjk_require_left_edge=True,
        paddle_auto_header_rule=False,
        paddle_left_tolerance=40,
        paddle_band_left_margin=8,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(
        preset="cjk_visual", language="chi_tra",
    )
    recovered = [
        OCRRecord(
            word,
            0.96,
            box,
            recovery="oversized_multi_entry_local_ocr",
            recovery_source_text=word,
            parent_box=(0, 80, 317, 850),
        )
        for word, box in zip(
            ("暖", "厂", "广", "安"),
            (
                (0, 100, 90, 190),
                (0, 285, 90, 380),
                (0, 480, 90, 575),
                (0, 675, 90, 775),
            ),
        )
    ]

    # The recovery provenance itself is the physical oversized-run proof.  The
    # downstream filter must not depend on re-detecting those same runs.
    monkeypatch.setattr(
        paddle_headwords,
        "_cjk_visual_projection_runs",
        lambda *_args, **_kwargs: (90, []),
    )
    monkeypatch.setattr(
        paddle_headwords,
        "_header_cutoff",
        lambda *_args, **_kwargs: 0,
    )

    def fake_refine(_gray, coarse_y, *_args, **_kwargs):
        refined = int(coarse_y) + 7
        return refined, {
            "enabled": True,
            "reason": "test_recovered_refined",
            "anchor_y": int(coarse_y) + 3,
            "refined_y": refined,
            "shift": 7,
        }

    monkeypatch.setattr(
        paddle_headwords, "refine_first_content_y", fake_refine,
    )
    monkeypatch.setattr(
        paddle_headwords, "refine_separator_y_adaptive", fake_refine,
    )

    entries, diagnostics = filter_headword_records(
        recovered,
        Image.new("RGB", (360, 900), "white"),
        0,
        0,
        settings,
        profile=profile,
    )

    assert [entry.word for entry in entries] == ["暖", "厂", "广", "安"]
    rows = [
        row for row in diagnostics
        if "meta" not in row and row.get("normalized_headword") in {"暖", "厂", "广", "安"}
    ]
    assert len(rows) == 4
    assert all(row["accepted"] is True for row in rows)
    assert all(row["features"]["cjk_oversized_recovery"] is True for row in rows)
    assert all(
        row["features"]["cjk_oversized_recovery_kind"]
        == "oversized_multi_entry_local_ocr"
        for row in rows
    )
    assert all(
        row["separator_refinement"]["reason"] == "test_recovered_refined"
        for row in rows
    )
    assert all(row["source_y"] == row["coarse_source_y"] + 7 for row in rows)


def test_recovered_oversized_cjk_manual_promotion_keeps_refined_geometry(
    monkeypatch,
):
    """An explicitly rejected recovered head stays unchecked but keeps refined Y."""
    settings = AppSettings(
        ocr_language="chi_tra",
        character_height=100,
        profile_parser_controls_version=1,
        profile_cjk_allow_single_headword=True,
        profile_cjk_require_visual_evidence=True,
        profile_cjk_require_left_edge=True,
        paddle_auto_header_rule=False,
        paddle_left_tolerance=40,
        paddle_band_left_margin=8,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(
        preset="cjk_visual", language="chi_tra",
    )
    record = OCRRecord(
        "广",
        0.96,
        (0, 220, 90, 315),
        recovery="oversized_multi_entry_local_ocr",
        recovery_source_text="广",
        parent_box=(0, 80, 317, 850),
    )
    monkeypatch.setattr(
        paddle_headwords,
        "_cjk_visual_projection_runs",
        lambda *_args, **_kwargs: (90, []),
    )
    monkeypatch.setattr(
        paddle_headwords,
        "_header_cutoff",
        lambda *_args, **_kwargs: 0,
    )

    def fake_refine(_gray, coarse_y, *_args, **_kwargs):
        refined = int(coarse_y) + 9
        return refined, {
            "enabled": True,
            "reason": "test_rejected_recovered_refined",
            "anchor_y": int(coarse_y) + 4,
            "refined_y": refined,
            "shift": 9,
        }

    monkeypatch.setattr(
        paddle_headwords, "refine_first_content_y", fake_refine,
    )
    monkeypatch.setattr(
        paddle_headwords, "refine_separator_y_adaptive", fake_refine,
    )

    entries, diagnostics = filter_headword_records(
        [record],
        Image.new("RGB", (360, 500), "white"),
        0,
        0,
        settings,
        user_rules=parse_headword_filter_rules("reject_lemma_exact: 广"),
        profile=profile,
    )

    assert entries == []
    rows = [
        row for row in diagnostics
        if "meta" not in row and row.get("normalized_headword") == "广"
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["accepted"] is False
    assert row["reject_reason"] == "user_reject_rule"
    assert row["features"]["cjk_oversized_recovery"] is True
    assert row["separator_refinement"]["reason"] == "test_rejected_recovered_refined"
    assert row["source_y"] == row["coarse_source_y"] + 9


def test_oversized_cjk_box_never_guesses_missing_children_from_parent_text(
    monkeypatch,
):
    """If parent text has 3 chars for 4 physical heads, do not distribute it."""
    settings = AppSettings(
        ocr_language="chi_tra",
        character_height=100,
        profile_parser_controls_version=1,
        profile_cjk_allow_single_headword=True,
    )
    profile = load_dictionary_profile(
        preset="cjk_visual", language="chi_tra",
    )
    band = Image.new("RGB", (360, 1000), "white")
    giant = OCRRecord("厂广安", 0.99, (0, 80, 317, 850))
    records = [
        OCRRecord("正文", 0.99, (130, 0, 350, 105)),
        OCRRecord("正文", 0.99, (130, 860, 350, 965)),
        giant,
    ]
    monkeypatch.setattr(
        paddle_headwords,
        "_cjk_visual_projection_runs",
        lambda *_args, **_kwargs: (
            90,
            [(100, 190), (285, 380), (480, 575), (675, 775)],
        ),
    )
    monkeypatch.setattr(
        paddle_headwords,
        "_header_cutoff",
        lambda *_args, **_kwargs: 0,
    )

    class FailingEngine:
        def predict(self, _image, **_kwargs):
            raise RuntimeError("local OCR unavailable")

    recovered, details = _recover_oversized_cjk_ocr_records(
        records,
        band,
        settings,
        profile,
        engine=FailingEngine(),
    )

    assert sorted(recovered, key=lambda row: (row.box[1], row.box[0])) == sorted(
        records, key=lambda row: (row.box[1], row.box[0])
    )
    assert len(details) == 1
    assert details[0]["applied"] is False
    assert details[0]["visual_run_count"] == 4
    assert details[0]["recovered_count"] == 0
    assert not any(record.recovery for record in recovered)




def test_trusted_bracket_lane_comes_from_explicit_ocr_not_visual_candidates():
    inventory = {
        "lane_required": True,
        "lane_tolerance_percent": 50,
        "bracket_openers": ("【",),
    }
    lines = [
        OCRLine("【甲】", 0.99, (2, 20, 120, 120), []),
        OCRLine("正文", 0.99, (125, 140, 260, 240), []),
        OCRLine("【乙】", 0.99, (4, 260, 120, 360), []),
    ]

    lanes = paddle_headwords._trusted_visual_marker_lanes(
        lines, inventory, 100.0,
    )

    lane = lanes["bracket_open"]
    assert lane["x"] == 3.0
    assert lane["count"] == 2
    assert lane["source"] == "explicit_ocr_bracket_rows"
    assert lane["tolerance"] == 40.0

    candidates = [
        {
            "role": "bracket_open",
            "family": "bracket_open",
            "x0": 18,
            "template_score": 0.0,
        },
        {
            "role": "bracket_open",
            "family": "bracket_open",
            "x0": 78,
            "template_score": 0.0,
        },
        {
            "role": "entry_marker",
            "family": "circle_open",
            "x0": 88,
        },
    ]
    filtered = paddle_headwords._apply_trusted_visual_marker_lanes(
        candidates, lanes, template_threshold=0.65,
    )

    assert len(filtered) == 2
    bracket = next(item for item in filtered if item["role"] == "bracket_open")
    assert bracket["x0"] == 18
    assert bracket["lane_source"] == "explicit_ocr_bracket_rows"
    assert bracket["lane_anchor_count"] == 2
    assert bracket["lane_delta"] == 15.0
    assert any(item["role"] == "entry_marker" for item in filtered)


def test_unanchored_bracket_rescue_rejects_generic_shape_and_weak_template():
    candidates = [
        {
            "role": "bracket_open",
            "family": "bracket_open",
            "x0": 12,
            "template_score": 0.0,
        },
        {
            "role": "bracket_open",
            "family": "dictionary_template",
            "x0": 12,
            "template_score": 0.665,
        },
        {
            "role": "bracket_open",
            "family": "dictionary_template",
            "x0": 12,
            "template_score": 0.74,
        },
    ]

    filtered = paddle_headwords._apply_trusted_visual_marker_lanes(
        candidates, {}, template_threshold=0.65,
    )

    assert len(filtered) == 1
    assert filtered[0]["template_score"] == 0.74
    assert filtered[0]["lane_source"] == "template_only_no_ocr_anchor"


def test_verified_cjk_recovery_suppresses_its_raw_source_before_line_grouping():
    records = [
        OCRRecord("摆1", 0.987, (0, 157, 359, 480)),
        OCRRecord(
            "摆",
            0.927,
            (0, 203, 253, 433),
            recovery="image_first_oversized_local_ocr",
            recovery_source_text="摆1",
        ),
        OCRRecord("正文", 0.99, (130, 500, 300, 610)),
    ]

    effective, details = (
        paddle_headwords._suppress_raw_records_shadowed_by_verified_cjk_recovery(
            records
        )
    )

    assert [record.text for record in effective] == ["摆", "正文"]
    assert len(details) == 1
    assert details[0]["raw_text"] == "摆1"
    assert details[0]["recovered_word"] == "摆"
    assert details[0]["reason"] == "same_recovery_source_text"
    grouped = paddle_headwords.group_ocr_records(effective)
    assert grouped
    assert grouped[0].text == "摆"


def test_verified_cjk_recovery_suppresses_giant_raw_box_spanning_recovered_heads():
    records = [
        OCRRecord("霸", 0.998, (0, 5854, 359, 6464)),
        OCRRecord(
            "耦",
            0.769,
            (0, 5890, 255, 6122),
            recovery="image_first_oversized_local_ocr",
            recovery_source_text="耦",
        ),
        OCRRecord(
            "霸",
            0.999,
            (0, 6162, 182, 6327),
            recovery="image_first_oversized_local_ocr",
            recovery_source_text="霸",
        ),
    ]

    effective, details = (
        paddle_headwords._suppress_raw_records_shadowed_by_verified_cjk_recovery(
            records
        )
    )

    assert [record.text for record in effective] == ["耦", "霸"]
    assert len(details) == 1
    assert details[0]["raw_text"] == "霸"
    assert details[0]["recovered_word"] == "霸"
    lines = paddle_headwords.group_ocr_records(effective)
    assert [line.text for line in lines] == ["耦", "霸"]


def test_explicit_ocr_bracket_headword_does_not_need_large_or_bold_visual_evidence():
    settings = AppSettings(
        ocr_language="chi_tra",
        profile_parser_controls_version=1,
        profile_cjk_allow_bracketed_headword=True,
        profile_cjk_require_left_edge=True,
        profile_cjk_require_visual_evidence=True,
        profile_symbol_inventory_version=1,
        profile_symbol_inventory_enabled=False,
        profile_bracket_open_symbols="【",
        profile_symbol_visual_rescue_enabled=True,
        profile_tail_structure_version=1,
        profile_tail_require_selected=False,
        profile_tail_allow_descriptor=False,
        paddle_auto_header_rule=False,
        paddle_left_tolerance=40,
        paddle_band_left_margin=8,
        paddle_min_candidate_score=1.0,
        paddle_require_pos_or_symbol=False,
        paddle_require_visual_cue=False,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(
        preset="cjk_visual", language="chi_tra",
    )
    entries, diagnostics = filter_headword_records(
        [OCRRecord("【艾艾】", 0.99, (2, 30, 100, 55))],
        Image.new("RGB", (220, 120), "white"),
        0,
        0,
        settings,
        profile=profile,
    )

    assert [entry.word for entry in entries] == ["艾艾"]
    rows = [row for row in diagnostics if "meta" not in row]
    assert len(rows) == 1
    row = rows[0]
    assert row["accepted"] is True
    assert row["features"]["cjk_bracket_explicit_ocr"] is True
    assert row["features"]["cjk_bracket_explicit_symbol"] == "【"
    assert row["features"]["cjk_bracket_extra_required"] is False


def test_bracket_role_and_templates_remain_active_when_standalone_marker_inventory_is_off():
    marker = Image.new("L", (20, 24), 255)
    draw = ImageDraw.Draw(marker)
    draw.rectangle((4, 2, 7, 21), fill=0)
    draw.rectangle((4, 2, 14, 5), fill=0)
    sample = build_visual_marker_sample(
        marker.convert("RGB"),
        role="bracket_open",
        literal="【",
        sample_id="bracket-sample",
    )
    settings = AppSettings(
        ocr_language="chi_tra",
        profile_parser_controls_version=1,
        profile_allow_marker_prefix=False,
        profile_cjk_allow_bracketed_headword=True,
        profile_symbol_inventory_version=1,
        profile_symbol_inventory_enabled=False,
        profile_entry_marker_symbols="",
        profile_bracket_open_symbols="【",
        profile_symbol_visual_rescue_enabled=True,
        profile_symbol_template_version=1,
        profile_symbol_template_mode="combined",
        profile_symbol_templates_json=serialize_visual_marker_samples([sample]),
    )
    profile = load_dictionary_profile(
        preset="cjk_visual", language="chi_tra",
    )
    inventory = paddle_headwords._configured_symbol_inventory(settings, profile)

    assert inventory["enabled"] is True
    assert inventory["standalone_inventory_enabled"] is False
    assert inventory["entry_markers"] == ()
    assert inventory["bracket_openers"] == ("【",)
    assert inventory["bracket_role_enabled"] is True
    assert len(inventory["visual_templates"]) == 1
    assert inventory["visual_templates"][0]["role"] == "bracket_open"



def test_relaxed_cjk_visual_run_discovery_uses_configured_body_height_cap():
    settings = AppSettings(
        ocr_language="chi_tra",
        character_height=122,
    )
    gray = np.full((500, 220), 255, dtype=np.uint8)
    gray[120:280, 0:30] = 0

    _zone, strict_runs = paddle_headwords._cjk_visual_projection_runs(
        gray, 0, settings, 1.0,
    )
    _zone, relaxed_runs = paddle_headwords._cjk_visual_projection_runs(
        gray, 0, settings, 1.0, relaxed=True,
    )

    assert strict_runs == []
    assert relaxed_runs == [(120, 280)]


def test_image_first_cjk_rescue_recovers_run_without_any_parent_ocr_box(monkeypatch):
    settings = AppSettings(
        ocr_language="chi_tra",
        character_height=100,
        profile_parser_controls_version=1,
        profile_cjk_allow_single_headword=True,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(
        preset="cjk_visual", language="chi_tra",
    )
    band = Image.new("RGB", (360, 700), "white")
    monkeypatch.setattr(
        paddle_headwords,
        "_cjk_visual_projection_runs",
        lambda *_args, **kwargs: (
            90,
            [(100, 190), (330, 425)] if kwargs.get("relaxed") else [],
        ),
    )
    monkeypatch.setattr(
        paddle_headwords,
        "_header_cutoff",
        lambda *_args, **_kwargs: 0,
    )

    words = iter(("啊", "安"))

    class Result:
        def __init__(self, word):
            self.json = {
                "res": {
                    "rec_texts": [word],
                    "rec_scores": [0.97],
                    "rec_boxes": [[2, 3, 70, 78]],
                }
            }

    class Engine:
        def predict(self, _image, **_kwargs):
            return [Result(next(words))]

    recovered, details = paddle_headwords._recover_image_first_oversized_cjk_records(
        [],
        band,
        settings,
        profile,
        engine=Engine(),
    )

    assert [row.text for row in recovered] == ["啊", "安"]
    assert all(
        row.recovery == "image_first_oversized_local_ocr"
        for row in recovered
    )
    assert all(row.parent_box is None for row in recovered)
    assert sum(bool(row.get("applied")) for row in details) == 2


def test_image_first_cjk_rescue_skips_existing_good_head_and_recovers_missing_neighbor(
    monkeypatch,
):
    settings = AppSettings(
        ocr_language="chi_tra",
        character_height=100,
        profile_parser_controls_version=1,
        profile_cjk_allow_single_headword=True,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(
        preset="cjk_visual", language="chi_tra",
    )
    band = Image.new("RGB", (360, 700), "white")
    monkeypatch.setattr(
        paddle_headwords,
        "_cjk_visual_projection_runs",
        lambda *_args, **kwargs: (
            90,
            [(100, 190), (330, 425)] if kwargs.get("relaxed") else [],
        ),
    )
    monkeypatch.setattr(
        paddle_headwords,
        "_header_cutoff",
        lambda *_args, **_kwargs: 0,
    )

    class Result:
        json = {
            "res": {
                "rec_texts": ["安"],
                "rec_scores": [0.98],
                "rec_boxes": [[2, 3, 70, 78]],
            }
        }

    class Engine:
        def __init__(self):
            self.calls = 0

        def predict(self, _image, **_kwargs):
            self.calls += 1
            return [Result()]

    engine = Engine()
    recovered, details = paddle_headwords._recover_image_first_oversized_cjk_records(
        [OCRRecord("啊", 0.99, (0, 100, 90, 190))],
        band,
        settings,
        profile,
        engine=engine,
    )

    assert [row.text for row in recovered] == ["啊", "安"]
    assert engine.calls == 1
    assert any(row.get("status") == "already_represented" for row in details)
    assert any(row.get("status") == "recovered" for row in details)


def test_image_first_cjk_rescue_accepts_sense_number_but_rejects_latin_initial(
    monkeypatch,
):
    assert paddle_headwords._leading_cjk_ideograph("案1") == "案"
    assert paddle_headwords._leading_cjk_ideograph("暗②") == "暗"
    assert paddle_headwords._leading_cjk_ideograph("安定") == ""

    settings = AppSettings(
        ocr_language="chi_tra",
        character_height=100,
        profile_parser_controls_version=1,
        profile_cjk_allow_single_headword=True,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(
        preset="cjk_visual", language="chi_tra",
    )
    band = Image.new("RGB", (360, 700), "white")
    monkeypatch.setattr(
        paddle_headwords,
        "_cjk_visual_projection_runs",
        lambda *_args, **kwargs: (
            90,
            [(100, 190), (330, 425)] if kwargs.get("relaxed") else [],
        ),
    )
    monkeypatch.setattr(
        paddle_headwords,
        "_header_cutoff",
        lambda *_args, **_kwargs: 0,
    )

    words = iter(("案1", "A"))

    class Result:
        def __init__(self, word):
            self.json = {
                "res": {
                    "rec_texts": [word],
                    "rec_scores": [0.96],
                    "rec_boxes": [[2, 3, 70, 78]],
                }
            }

    class Engine:
        def predict(self, _image, **_kwargs):
            return [Result(next(words))]

    recovered, details = paddle_headwords._recover_image_first_oversized_cjk_records(
        [],
        band,
        settings,
        profile,
        engine=Engine(),
    )

    assert [row.text for row in recovered] == ["案"]
    assert recovered[0].recovery_source_text == "案1"
    assert any(
        row.get("status") == "local_ocr_no_single_cjk"
        for row in details
    )


def test_image_first_recovered_cjk_head_is_auto_selected_and_refined(monkeypatch):
    settings = AppSettings(
        ocr_language="chi_tra",
        character_height=100,
        profile_parser_controls_version=1,
        profile_cjk_allow_single_headword=True,
        profile_cjk_require_visual_evidence=True,
        profile_cjk_require_left_edge=True,
        paddle_auto_header_rule=False,
        paddle_left_tolerance=40,
        paddle_band_left_margin=8,
        paddle_rec_score_threshold=0.20,
    )
    profile = load_dictionary_profile(
        preset="cjk_visual", language="chi_tra",
    )
    record = OCRRecord(
        "安",
        0.96,
        (0, 220, 90, 315),
        recovery="image_first_oversized_local_ocr",
        recovery_source_text="安",
    )
    monkeypatch.setattr(
        paddle_headwords,
        "_header_cutoff",
        lambda *_args, **_kwargs: 0,
    )

    def fake_refine(_gray, coarse_y, *_args, **_kwargs):
        refined = int(coarse_y) + 8
        return refined, {
            "enabled": True,
            "reason": "test_image_first_refined",
            "anchor_y": int(coarse_y) + 4,
            "refined_y": refined,
            "shift": 8,
        }

    monkeypatch.setattr(
        paddle_headwords, "refine_first_content_y", fake_refine,
    )
    monkeypatch.setattr(
        paddle_headwords, "refine_separator_y_adaptive", fake_refine,
    )

    entries, diagnostics = filter_headword_records(
        [record],
        Image.new("RGB", (360, 500), "white"),
        0,
        0,
        settings,
        profile=profile,
    )

    assert [entry.word for entry in entries] == ["安"]
    rows = [row for row in diagnostics if "meta" not in row]
    assert len(rows) == 1
    row = rows[0]
    assert row["accepted"] is True
    assert row["features"]["cjk_oversized_recovery"] is True
    assert row["separator_refinement"]["reason"] == "test_image_first_refined"
    assert row["source_y"] == row["coarse_source_y"] + 8


def test_cjk_visual_profile_defaults_separate_brackets_from_entry_markers():
    defaults = profile_symbol_inventory_defaults("cjk_visual")
    assert defaults["entry_markers"] == []
    assert defaults["bracket_openers"] == ["【"]
    assert defaults["visual_rescue"] is False
    assert defaults["lane_required"] is True
    assert defaults["lane_tolerance_percent"] == 45


def test_cjk_visual_symbol_role_normalization_moves_legacy_bracket_sample():
    sample = {
        "id": "legacy-bracket",
        "role": "entry_marker",
        "literal": "【",
        "source_page": "0002.png",
        "source_box": [1, 2, 10, 20],
        "size": 16,
        "bitmap": "0" * 256,
        "aspect_ratio": 0.5,
        "density": 0.1,
        "central_ink": 0.1,
        "hole_count": 0,
    }
    entry, bracket, samples = _normalize_cjk_visual_symbol_roles(
        "【 ○", "【", [sample],
    )
    assert split_configured_symbols(entry) == ("○",)
    assert split_configured_symbols(bracket) == ("【",)
    assert samples[0]["role"] == "bracket_open"

    role, literal = _visual_marker_capture_defaults(
        marker_prefix_enabled=False,
        bracket_enabled=True,
        entry_text="",
        bracket_text="【",
    )
    assert (role, literal) == ("bracket_open", "【")


def test_old_cjk_visual_settings_migrate_bracket_role_once(tmp_path):
    marker = Image.new("L", (20, 24), 255)
    draw = ImageDraw.Draw(marker)
    draw.rectangle((4, 2, 7, 21), fill=0)
    draw.rectangle((4, 2, 14, 5), fill=0)
    sample = build_visual_marker_sample(
        marker.convert("RGB"),
        role="entry_marker",
        literal="【",
        sample_id="legacy",
    )
    settings_path_value = tmp_path / "settings.json"
    settings_path_value.write_text(
        __import__("json").dumps(
            {
                "dictionary_profile_id": "cjk_visual",
                "profile_symbol_role_semantics_version": 0,
                "profile_parser_controls_version": 1,
                "profile_allow_marker_prefix": True,
                "profile_cjk_allow_bracketed_headword": True,
                "profile_symbol_inventory_version": 1,
                "profile_entry_marker_symbols": "【",
                "profile_bracket_open_symbols": "【",
                "profile_symbol_lane_required": False,
                "profile_symbol_template_version": 1,
                "profile_symbol_templates_json": serialize_visual_marker_samples(
                    [sample]
                ),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    migrated = AppSettings.from_json(settings_path_value)
    assert migrated.profile_symbol_role_semantics_version == 1
    assert migrated.profile_allow_marker_prefix is False
    assert migrated.profile_entry_marker_symbols == ""
    assert migrated.profile_bracket_open_symbols == "【"
    assert migrated.profile_symbol_lane_required is True
    assert migrated.profile_symbol_visual_rescue_enabled is False
    samples = parse_visual_marker_samples(
        migrated.profile_symbol_templates_json
    )
    assert len(samples) == 1
    assert samples[0]["literal"] == "【"
    assert samples[0]["role"] == "bracket_open"


def test_cjk_profile_ui_explains_bracket_role_at_the_controls():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "profile_setup.py"
    ).read_text(encoding="utf-8")
    assert "不包括【括号】" in source
    assert "【不要填这里】" in source
    assert "采【时按“括号起始”保存" in source


def test_selected_paddle_cache_compaction_is_scoped_and_preserves_reusable_ocr():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("    def cleanup_paddleocr_temp_selected_scope(self) -> None:")
    end = text.index("    def jump_to_page_spec", start)
    block = text[start:end]
    assert "indices = self.selected_page_indices()" in block
    assert "cache_root = ocr_cache_root(self.project.root)" in block
    assert "compact_ocr_cache_file(cache_path)" in block
    assert "messagebox.askyesno(" in block
    assert "保留 <page>_manual_selection.json 人工选择" in block
    assert "保留 OCR 原始记录" in block
    assert "无需重新 OCR" in block
    assert "shutil.rmtree" not in block


def test_paddle_cache_payload_compaction_keeps_only_reusable_column_data():
    payload = {
        "signature": "abc",
        "review_candidates": [{"candidate_id": "c1", "word": "test"}],
        "final_entries": [{"word": "test", "x": 1, "y": 2}],
        "columns": [{
            "column": 0,
            "band_size": [400, 1200],
            "ocr_records": [{"text": "test", "confidence": 0.9, "box": [1, 2, 30, 40]}],
            "paddle_effective_records": [{"text": "duplicate"}],
            "paddle_full_text": "large duplicate text",
            "paddle_merged_lines": [{"text": "duplicate"}],
            "candidates": [{
                "box": [1, 2, 30, 40],
                "accepted": False,
                "reject_reason": "body_line",
                "features": {
                    "visual_marker_template_score": 0.81,
                    "ordinary_strong_edge_visual_rescue": True,
                    "large_unused_feature": "drop-me",
                },
                "large_unused_field": "drop-me",
            }],
            "tesseract": {"candidates": [{"text": "duplicate"}]},
            "lens": {"candidates": [{"text": "duplicate"}]},
            "ocr_y_comparison": [{"huge": "duplicate"}],
            "review_candidates": [{"candidate_id": "duplicate"}],
        }],
    }
    compact = compact_ocr_cache_payload(payload)
    assert compact["cache_storage"] == "compact-v1"
    assert compact["signature"] == "abc"
    assert compact["review_candidates"] == payload["review_candidates"]
    column = compact["columns"][0]
    assert set(column) == {"column", "band_size", "ocr_records", "candidates"}
    assert column["ocr_records"] == payload["columns"][0]["ocr_records"]
    candidate = column["candidates"][0]
    assert set(candidate) == {"box", "accepted", "reject_reason", "features"}
    assert set(candidate["features"]) == {
        "visual_marker_template_score", "ordinary_strong_edge_visual_rescue",
    }


def test_paddle_cache_file_compaction_preserves_manual_selection_and_removes_sidecars(tmp_path):
    cache = tmp_path / "0001.json"
    manual = tmp_path / "0001_manual_selection.json"
    payload = {
        "signature": "sig",
        "review_candidates": [{"candidate_id": "c1", "word": "word"}],
        "columns": [{
            "column": 0, "band_size": [300, 900],
            "ocr_records": [{"text": "word", "confidence": 0.9, "box": [1, 2, 20, 30]}],
            "paddle_full_text": "x" * 5000,
            "candidates": [],
        }],
    }
    cache.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    manual.write_text('{"version":1,"overrides":{"c1":{"selected":true}}}', encoding="utf-8")
    suffixes = (
        "_ocr_diagnostics.txt", "_ocr_comparison.txt", "_issues.tsv",
        "_ocr_engines.tsv", "_fusion.tsv",
    )
    for suffix in suffixes:
        (tmp_path / f"0001{suffix}").write_text("diagnostic" * 100, encoding="utf-8")

    before, after, removed = compact_ocr_cache_file(cache)
    assert removed == len(suffixes)
    assert after < before
    assert manual.exists()
    assert "selected" in manual.read_text(encoding="utf-8")
    compact = __import__("json").loads(cache.read_text(encoding="utf-8"))
    assert compact["signature"] == "sig"
    assert compact["cache_storage"] == "compact-v1"
    assert compact["columns"][0]["ocr_records"][0]["text"] == "word"
    assert "paddle_full_text" not in compact["columns"][0]
    assert all(not (tmp_path / f"0001{suffix}").exists() for suffix in suffixes)

def test_paddle_temp_page_match_uses_stem_boundaries():
    from picture_capture.app import PictureCaptureApp

    matches = PictureCaptureApp._paddle_temp_matches_page
    assert matches(Path("0001.json"), "0001")
    assert matches(Path("0001_ocr_diagnostics.txt"), "0001")
    assert matches(Path("0001-tiles"), "0001")
    assert not matches(Path("00010.json"), "0001")
    assert not matches(Path("other_0001.json"), "0001")


def test_settings_center_avoids_full_hidden_tab_idle_layout_cascade():
    source = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "app.py"
    text = source.read_text(encoding="utf-8")
    help_source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "settings" / "help.py"
    ).read_text(encoding="utf-8")
    start = text.index('    def __init__(self, parent: "PictureCaptureApp", initial_tab: str | None = None) -> None:')
    end = text.index("    @staticmethod\n    def _crop_nonnegative_int", start)
    block = text[start:end]
    # The early update_idletasks() used only to obtain screen/window geometry is
    # allowed.  The old trailing all-tab layout flush after autosave binding was
    # the Windows/Tk hang and must not return.
    tail = block[block.index("        self._autosave_ready = True"):]
    assert "self.update_idletasks()" not in tail
    assert "for _canvas in self._settings_canvases.values():" not in tail
    assert "content.bind(" in text
    assert 'cv.configure(scrollregion=cv.bbox("all"))' in text
    assert "每个参数下方已直接显示详细说明" in text
    assert 'pending["job"] = dialog.after(80, refresh)' in help_source
    assert 'pending["job"] = dialog.after_idle(refresh)' not in help_source



def test_responsive_help_wrapping_does_not_self_trigger_on_label_configure():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "picture_capture" / "ui" / "settings" / "help.py"
    )
    text = source.read_text(encoding="utf-8")
    start = text.index("def bind_responsive_labels(")
    block = text[start:]
    assert 'container.bind("<Configure>", schedule, add="+")' in block
    assert 'label.bind("<Configure>", schedule, add="+")' not in block
    assert "_pc_wrap_cache_key" in block
    assert "_pc_wrap_width" in block

