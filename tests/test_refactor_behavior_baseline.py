from __future__ import annotations

import json
from pathlib import Path

from picture_capture.formats import read_pdic, read_ppp, write_pdic, write_ppp
from picture_capture.models import AppSettings, Entry, PolygonRegion
from picture_capture.project_storage import (
    ensure_project_storage,
    ocr_cache_root,
    pdic_path_for_image,
    ppp_read_path_for_image,
    ppp_write_path_for_image,
    profile_path,
    settings_path,
    storage_root,
)


def test_app_settings_json_roundtrip_preserves_representative_user_state(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = AppSettings(
        dictionary_full_name="重构行为基线词典",
        dictionary_abbreviation="BASE",
        columns=2,
        column_start_offsets=[-3, 7],
        gutter=61,
        column_width=733,
        manual_x=31,
        character_height=29,
        ocr_language="eng",
        preprocess_auto_deskew=False,
        preprocess_export_canvas_enabled=True,
        preprocess_export_canvas_mode="custom",
        preprocess_export_canvas_width=1800,
        preprocess_export_margin_left=42,
        page_bookmarks=["0002", "0010"],
    )

    settings.to_json(path)
    reopened = AppSettings.from_json(path)

    assert reopened.dictionary_full_name == settings.dictionary_full_name
    assert reopened.dictionary_abbreviation == settings.dictionary_abbreviation
    assert reopened.columns == 2
    assert reopened.column_start_offsets == [-3, 7]
    assert reopened.gutter == 61
    assert reopened.column_width == 733
    assert reopened.manual_x == 31
    assert reopened.character_height == 29
    assert reopened.ocr_language == "eng"
    assert reopened.preprocess_auto_deskew is False
    assert reopened.preprocess_export_canvas_enabled is True
    assert reopened.preprocess_export_canvas_mode == "custom"
    assert reopened.preprocess_export_canvas_width == 1800
    assert reopened.preprocess_export_margin_left == 42
    assert reopened.page_bookmarks == ["0002", "0010"]

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["column_start_offsets"] == [-3, 7]
    assert payload["page_bookmarks"] == ["0002", "0010"]
    # Historical coordinate-normalization fields are migration input only and
    # must not reappear in newly written settings.
    assert "geometry_reference_width" not in payload
    assert "parameter_display_width" not in payload


def test_managed_project_paths_and_ocr_cache_are_stable(tmp_path: Path) -> None:
    root = tmp_path / "DictionaryProject"
    root.mkdir()
    ensure_project_storage(root, "2.14.2")
    page = root / "0007.png"
    page.write_bytes(b"")

    managed = root / "_PictureCapture"
    assert storage_root(root) == managed
    assert settings_path(root) == managed / "settings.json"
    assert profile_path(root) == managed / "dictionary_profile.json"
    assert pdic_path_for_image(page) == managed / "data" / "PDIC" / "0007.pdic"
    assert ppp_write_path_for_image(page) == managed / "data" / "PPP" / "0007.ppp"
    assert ppp_read_path_for_image(page) == managed / "data" / "PPP" / "0007.ppp"
    assert ocr_cache_root(root) == managed / "QT" / "PaddleOCR"

    manifest = json.loads((managed / "project.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "picture_capture_project"
    assert manifest["format_version"] == 2
    assert manifest["storage_root"] == "_PictureCapture"
    assert manifest["settings"] == "settings.json"


def test_pdic_serialization_and_roundtrip_remain_byte_compatible(tmp_path: Path) -> None:
    path = tmp_path / "0007.pdic"
    entries = [
        Entry(word="alpha#beta", x=100, y=250),
        Entry(word="二", x=333, y=444),
    ]

    write_pdic(path, entries, 1000, ("0007", "0006", "0008"))

    assert path.read_text(encoding="utf-8") == (
        "alpha＃beta#100#250#10#25#0007#0006#0008\n"
        "二#333#444#33.3#44.4#0007#0006#0008\n"
    )
    reopened = read_pdic(path)
    assert [item.word for item in reopened] == ["alpha＃beta", "二"]
    assert [(item.x, item.y) for item in reopened] == [(100, 250), (333, 444)]
    assert [item.current_page for item in reopened] == ["0007", "0007"]
    assert [item.previous_page for item in reopened] == ["0006", "0006"]
    assert [item.next_page for item in reopened] == ["0008", "0008"]


def test_ppp_illustration_polygon_serialization_and_roundtrip_are_stable(tmp_path: Path) -> None:
    path = tmp_path / "0007.ppp"
    regions = [
        PolygonRegion(
            label="0007|P_01|1|0007|",
            points=[(1, 2), (30, 40), (55, 63)],
        )
    ]

    write_ppp(path, regions, "0007")

    assert path.read_text(encoding="utf-8") == (
        "1\t0007|P_01|1|0007|\t|1,2|30,40|55,63\n"
    )
    reopened = read_ppp(path)
    assert len(reopened) == 1
    assert reopened[0].label == "0007|P_01|1|0007|"
    assert reopened[0].points == [(1, 2), (30, 40), (55, 63)]
