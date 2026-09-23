from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace

from PIL import Image

from picture_capture.app import (
    PictureCaptureApp, binary_preview_image, effective_main_overlay_font_size,
    ReviewWindow, VerticalWordText, horizontal_ocr_menu_layout, horizontal_overlay_layout,
    transformed_entry_anchor, vertical_marker_contact_gap, vertical_ocr_menu_layout,
    vertical_overlay_layout,
)
from picture_capture.dictionary_profile import effective_project_profile_id, load_dictionary_profile
from picture_capture.models import AppSettings, Entry, ProjectState
from picture_capture.layout_transform import LayoutTransform
from picture_capture.layout_detection import _analysis_ink_mask
from picture_capture.paddle_headwords import (
    OCRLine, OCRRecord, _cache_signature, _compile_patterns,
    _repair_multiline_headword_state_machine, parse_headword_text,
    prepare_ocr_band, run_paddle_band,
)
from picture_capture.project_storage import profile_path, settings_path
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


def test_recent_project_details_expose_requested_columns(tmp_path):
    project = tmp_path / "scan"
    _project(project, dictionary_full_name="完整词典", dictionary_abbreviation="缩写")
    detail = recent_project_details({"name": "scan", "path": str(project), "opened_at": "old"})
    assert detail["full_name"] == "完整词典"
    assert detail["abbreviation"] == "缩写"
    assert detail["image_count"] == 3
    assert detail["path"] == str(project)
    assert detail["last_edited"] != "old"


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



def test_raw_ocr_cache_signature_tracks_pixels_and_inference_settings():
    class PathStub:
        points = [(10, 20), (10, 200)]

    geometry = SimpleNamespace(
        transform=SimpleNamespace(kind="identity"),
        column_paths=[PathStub()],
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

    changed = image.copy()
    changed.putpixel((32, 32), (0, 0, 0))
    assert _cache_signature(changed, geometry, base) != sig

    # Candidate/parser-only settings deliberately do not invalidate raw OCR.
    assert _cache_signature(image, geometry, replace(base, paddle_min_candidate_score=9.0)) == sig
    assert _cache_signature(image, geometry, replace(base, paddle_headword_regex=r"^foo")) == sig


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
