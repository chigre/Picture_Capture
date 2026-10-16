"""Profile v3 illustrated/mixed routing, independent OCR controls and menu contracts."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picture_capture.models import AppSettings
from picture_capture.dictionary_profile import (
    apply_project_profile_components, write_project_profile,
)
from picture_capture.illustrated_profile import (
    effective_page_kind, set_page_kind, validate_illustrated_preferences,
    languages, tesseract_languages, effective_ocr_roi,
)
from picture_capture.illustrated_ocr import (
    SpatialLine, group_spatial_lines, propose_page_entries,
)
from picture_capture.ocr_channel import (
    OcrChannelCandidate, OcrChannelPlan, OcrChannelRecord, OcrChannelResult,
)


def test_traditional_default_and_mixed_filename_identity():
    settings = AppSettings()
    assert effective_page_kind(settings, Path("chapter0001.png")) == "traditional"
    settings.dictionary_layout_kind = "illustrated"
    assert effective_page_kind(settings, Path("chapter0001.png")) == "illustrated"
    settings.dictionary_layout_kind = "mixed"
    set_page_kind(settings, Path("chapter0001.png"), "illustrated")
    assert effective_page_kind(settings, "chapter0001.png") == "illustrated"
    assert effective_page_kind(settings, "chapter0002.png") == "traditional"
    set_page_kind(settings, "chapter0001.png", "default")
    assert "chapter0001.png" not in settings.illustrated_page_overrides
    with pytest.raises(ValueError):
        set_page_kind(settings, "../path.png", "other")


def test_profile_settings_roundtrip_and_profile_sidecar(tmp_path):
    settings = AppSettings(
        dictionary_layout_kind="mixed",
        illustrated_page_overrides={"p001.png": "illustrated", "index.png": "traditional"},
        illustrated_primary_language="eng",
        illustrated_ocr_languages="eng+fra+deu+jpn+chi_sim",
        illustrated_grouping_mode="strict",
        illustrated_group_max_lines=5,
        illustrated_require_review=False,
        illustrated_export_split_aliases=False,
        illustrated_ocr_top_percent=6.,
        illustrated_ocr_bottom_percent=5.,
        illustrated_ocr_side_percent=3.,
    )
    path = tmp_path / "settings.json"
    settings.to_json(path)
    loaded = AppSettings.from_json(path)
    assert loaded == settings
    profile = tmp_path / "dictionary_profile.json"
    write_project_profile(profile, loaded, force=True)
    seeded = AppSettings()
    apply_project_profile_components(profile, seeded)
    for field in (
        "dictionary_layout_kind", "illustrated_page_overrides",
        "illustrated_ocr_languages", "illustrated_grouping_mode",
        "illustrated_group_max_lines", "illustrated_require_review",
        "illustrated_ocr_top_percent", "illustrated_export_split_aliases",
    ):
        assert getattr(seeded, field) == getattr(settings, field)


def test_parameter_template_excludes_page_specific_mixed_overrides():
    from picture_capture.project_parameter_templates import capture_parameters
    settings = AppSettings(
        dictionary_layout_kind="mixed",
        illustrated_page_overrides={"volume1_001.png": "illustrated"},
    )
    snapshot = capture_parameters(settings)
    assert snapshot["settings"]["dictionary_layout_kind"] == "mixed"
    assert "illustrated_page_overrides" not in snapshot["settings"]


def test_languages_validation_and_normalized_roi():
    settings = AppSettings(illustrated_ocr_languages="eng, fra+jpn, chi_sim",
                           illustrated_ocr_top_percent=10.,
                           illustrated_ocr_bottom_percent=5.,
                           illustrated_ocr_side_percent=7.)
    assert languages(settings.illustrated_ocr_languages) == ("eng", "fra", "jpn", "chi_sim")
    assert tesseract_languages(settings) == "eng+fra+jpn+chi_sim"
    assert effective_ocr_roi(settings, (1000, 2000)) == (70, 200, 930, 1900)
    settings.illustrated_group_max_lines = 40
    with pytest.raises(ValueError):
        validate_illustrated_preferences(settings)
    settings.illustrated_group_max_lines = 10
    settings.illustrated_ocr_top_percent = -1
    with pytest.raises(ValueError):
        validate_illustrated_preferences(settings)


def test_spatial_grouping_profile_modes_and_limit():
    lines = [
        SpatialLine("hair", (10, 10, 90, 23)),
        SpatialLine("les cheveux", (11, 35, 110, 48)),
        SpatialLine("das Haar", (10, 59, 100, 72)),
    ]
    assert len(group_spatial_lines(lines, mode="strict")) == 3
    assert len(group_spatial_lines(lines, mode="loose")) == 1
    assert len(group_spatial_lines(lines, mode="loose", max_lines=2)) == 2


def test_multilingual_full_page_ocr_uses_tesseract_and_roi_offsets(tmp_path):
    page = tmp_path / "page.png"
    Image.new("RGB", (400, 500), "white").save(page)
    settings = AppSettings(
        illustrated_ocr_languages="eng+fra+deu",
        illustrated_ocr_top_percent=10.,
        illustrated_ocr_side_percent=5.,
        illustrated_grouping_mode="auto",
        paddle_use_paddleocr=False,
        paddle_compare_tesseract=True,
    )
    plan = OcrChannelPlan(("tesseract",), ("tesseract",))
    records = (OcrChannelRecord("hair", .98, (10, 10, 60, 30)),)
    candidate = OcrChannelCandidate(engine="tesseract", records=records, text="hair")
    observed = []
    class FakeSession:
        def __init__(self, received, *, plan):
            observed.append(received.tesseract_language)
        def recognize_crop(self, image, *, tesseract_psm):
            observed.append((image.width, image.height, tesseract_psm))
            return OcrChannelResult(plan, (candidate,))
    proposed = propose_page_entries(page, settings, session_factory=FakeSession)
    assert observed == ["eng+fra+deu", (360, 450, 11)]
    assert (proposed[0].x, proposed[0].y) == (30, 60)
    assert not (tmp_path / "data" / "illustrated_entries" / "page.json").exists()
    settings.paddle_compare_tesseract = False
    settings.paddle_use_paddleocr = True
    with pytest.raises(RuntimeError, match="Tesseract"):
        propose_page_entries(page, settings, session_factory=FakeSession)



def test_multilingual_ocr_fails_closed_when_tesseract_language_packs_are_missing(tmp_path):
    page = tmp_path / "scan.png"
    Image.new("RGB", (200, 160), "white").save(page)
    settings = AppSettings(
        illustrated_ocr_languages="eng+fra",
        paddle_use_paddleocr=True,
        paddle_compare_tesseract=True,
    )
    plan = OcrChannelPlan(("paddle", "tesseract"), ("paddle", "tesseract"))
    paddle = OcrChannelCandidate(
        engine="paddle", text="hair",
        records=(OcrChannelRecord("hair", .95, (10, 12, 55, 30)),),
    )
    tess = OcrChannelCandidate(engine="tesseract", error="fra.traineddata not found")
    class FakeSession:
        def __init__(self, _settings, *, plan):
            pass
        def recognize_crop(self, _image, *, tesseract_psm):
            return OcrChannelResult(plan, (paddle, tess))
    with pytest.raises(RuntimeError, match="Tesseract"):
        propose_page_entries(page, settings, session_factory=FakeSession)


def test_profile_menu_and_draw_menu_are_layout_specific_without_app_monkeypatch():
    root = Path(__file__).resolve().parents[1] / "src" / "picture_capture" / "ui"
    profile = (root / "compact_layout_profile_menu.py").read_text(encoding="utf-8")
    drawing = (root / "compact_task_menus.py").read_text(encoding="utf-8")
    assert 'build_layout_kind_control' in profile
    assert 'layout_container = ordinary_host' in profile
    assert 'build_illustrated_profile_controls' in profile
    assert 'effective_page_kind(app.settings' in drawing
    assert 'ordinary.pack_forget()' in drawing
    assert '"主画布文字框编辑 / 校对"' in drawing
    assert '"全页 OCR 检测与文字组归并"' in drawing
    assert 'ACTION_GROUPS = (' in drawing
