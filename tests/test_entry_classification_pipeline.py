from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from picture_capture.entry_classification import (
    apply_classification_sidecar,
    classification_sidecar_path,
    classified_entry_crop_height,
    get_entry_classification,
    install_pdic_classification,
    register_layout_line_classification,
    set_entry_scale_manual,
    write_classification_sidecar,
)
from picture_capture.entry_classification_fields import install_entry_classification_fields
from picture_capture.models import AppSettings, Entry
from picture_capture.training_baseline import (
    baseline_path_for_pdic,
    build_write_pdic_capture,
)


def test_entry_classification_descriptors_are_static_and_installer_is_inert():
    names = (
        "entry_source",
        "entry_scale",
        "detected_head_height",
        "entry_scale_manual",
    )
    before = {name: Entry.__dict__[name] for name in names}
    assert all(isinstance(value, property) for value in before.values())

    install_entry_classification_fields()

    assert {name: Entry.__dict__[name] for name in names} == before


def test_entry_classification_fields_work_without_core_bootstrap():
    script = """
from picture_capture.models import Entry
entry = Entry(word="", x=10, y=20, ocr_source="ordinary_symbol_evidence")
assert entry.entry_source == "symbol_sample"
assert entry.entry_scale == "regular"
entry.entry_scale = "oversized"
assert entry.entry_scale == "oversized"
entry.entry_scale_manual = True
assert entry.entry_scale_manual is True
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_entry_exposes_canonical_classification_fields():
    entry = Entry(word="", x=10, y=20, ocr_source="ordinary_symbol_evidence")
    assert entry.entry_source == "symbol_sample"
    assert entry.entry_scale == "regular"
    assert entry.detected_head_height == 0.0
    assert entry.entry_scale_manual is False

    entry.entry_scale = "oversized"
    assert entry.entry_scale == "oversized"
    entry.entry_scale_manual = True
    assert entry.entry_scale_manual is True
    entry.entry_scale_manual = False
    assert entry.entry_scale == "oversized"
    assert entry.entry_scale_manual is False


def test_shared_entry_crop_fields_construct_and_persist(tmp_path: Path):
    settings = AppSettings(
        entry_regular_crop_height=42,
        entry_oversized_crop_height=96,
    )
    assert settings.entry_regular_crop_height == 42
    assert settings.entry_oversized_crop_height == 96

    path = tmp_path / "settings.json"
    settings.to_json(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["entry_regular_crop_height"] == 42
    assert raw["entry_oversized_crop_height"] == 96
    assert "review_regular_crop_height" not in raw
    assert "review_single_cjk_line_height" not in raw

    restored = AppSettings.from_json(path)
    assert restored.entry_regular_crop_height == 42
    assert restored.entry_oversized_crop_height == 96


def test_legacy_review_crop_fields_remain_readable(tmp_path: Path):
    settings = AppSettings()
    path = tmp_path / "old-settings.json"
    settings.to_json(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("entry_regular_crop_height", None)
    raw.pop("entry_oversized_crop_height", None)
    raw["review_regular_crop_height"] = 38
    raw["review_single_cjk_line_height"] = 88
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    restored = AppSettings.from_json(path)
    assert restored.entry_regular_crop_height == 38
    assert restored.entry_oversized_crop_height == 88


def test_symbol_and_large_head_evidence_share_one_scale_model():
    symbol_line = SimpleNamespace(role="body")
    large_line = SimpleNamespace(role="body")
    symbol = Entry(
        word="",
        x=10,
        y=20,
        ocr_source="ordinary_symbol_evidence",
        issue_type="ORDINARY_VISUAL_BRACKET_SAMPLE",
    )
    large = Entry(
        word="",
        x=10,
        y=40,
        ocr_source="ordinary_large_head_evidence",
        issue_type="ORDINARY_OVERSIZED_DISPLAY_HEAD",
        ocr_visual_run_height=84.0,
        ocr_oversized_cjk=True,
    )

    symbol_meta = register_layout_line_classification(symbol_line, symbol)
    large_meta = register_layout_line_classification(large_line, large)

    assert symbol_meta.entry_source == "symbol_sample"
    assert symbol_meta.entry_scale == "regular"
    assert large_meta.entry_source == "large_head"
    assert large_meta.entry_scale == "oversized"
    assert large_meta.detected_head_height == 84.0


def test_oversized_crop_prefers_observed_head_height():
    settings = AppSettings(character_height=30, row_padding=3)
    entry = Entry(
        word="",
        x=10,
        y=20,
        ocr_source="ordinary_large_head_evidence",
        ocr_visual_run_height=82.0,
        ocr_oversized_cjk=True,
    )
    regular = Entry(word="", x=10, y=50, ocr_source="ordinary_symbol_evidence")

    assert classified_entry_crop_height(regular, settings, regular_height=36) == 36
    assert classified_entry_crop_height(entry, settings, regular_height=36) == 88


def test_manual_scale_override_survives_sidecar_round_trip(tmp_path: Path):
    pdic = tmp_path / "page.pdic"
    entry = Entry(word="字", x=40, y=100, ocr_source="ordinary_large_head_evidence")
    set_entry_scale_manual(entry, "regular")
    write_classification_sidecar([entry], pdic)

    restored = Entry(word="字", x=40, y=100)
    apply_classification_sidecar([restored], pdic)
    meta = get_entry_classification(restored)
    assert meta.entry_scale == "regular"
    assert meta.manual_override is True


def test_manual_override_survives_small_separator_y_move(tmp_path: Path):
    pdic = tmp_path / "page.pdic"
    entry = Entry(word="字", x=40, y=100, ocr_source="ordinary_large_head_evidence")
    set_entry_scale_manual(entry, "regular")
    write_classification_sidecar([entry], pdic)

    moved = Entry(word="字", x=40, y=106, ocr_source="ordinary_large_head_evidence")
    apply_classification_sidecar([moved], pdic)
    assert get_entry_classification(moved).manual_override is True
    assert get_entry_classification(moved).entry_scale == "regular"


def test_review_and_marker_ocr_are_wired_to_canonical_classification():
    import picture_capture.processing_core as processing_core
    import picture_capture.review_entry_classification_ui as review

    marker_ocr_source = Path(processing_core.__file__).read_text(encoding="utf-8")
    review_source = Path(review.__file__).read_text(encoding="utf-8")

    # Marker OCR now delegates crop geometry to the shared entry_ocr_crop layer;
    # proofreading retains the same canonical regular/oversized classification.
    assert "entry_ocr_crop_box(" in marker_ocr_source
    assert "resolve_entry_ocr_row_metrics(" in marker_ocr_source
    assert 'meta.entry_scale == "oversized"' in marker_ocr_source
    assert "classified_entry_crop_height(" in review_source
    assert "entry_regular_crop_height" in review_source
    assert "entry_oversized_crop_height" in review_source
    assert "_is_single_cjk_review_headword" not in review_source
    assert '("自动", "普通词条", "大字头")' in review_source


def test_gui_composition_uses_static_pdic_io_and_installs_review_ui_after_app():
    import picture_capture.app as app_module
    import picture_capture.bootstrap.gui as gui_bootstrap
    import picture_capture.gui_io as gui_io

    source = Path(gui_bootstrap.__file__).read_text(encoding="utf-8")
    assert "install_pdic_classification(formats)" not in source
    assert "formats.write_pdic =" not in source
    assert "build_write_pdic_capture" not in source
    assert "install_processing_entry_classification" not in source
    assert "entry_classification_runtime" not in source
    assert app_module.write_pdic is gui_io.write_pdic
    assert app_module.read_pdic is gui_io.read_pdic
    assert "install_review_entry_classification(app_module)" in source
    assert source.index("from .. import app as app_module") < source.index(
        "install_review_entry_classification(app_module)"
    )


def test_gui_baseline_capture_wraps_core_classification_without_reinstall(tmp_path: Path):
    writes: list[list[Entry]] = []

    def read_pdic(_path: Path) -> list[Entry]:
        return []

    def write_pdic(
        path: Path,
        entries: list[Entry],
        _image_width: int,
        _pages: tuple[str, str, str],
    ) -> None:
        writes.append(list(entries))
        path.write_text("pdic\n", encoding="utf-8")

    formats_module = SimpleNamespace(read_pdic=read_pdic, write_pdic=write_pdic)
    install_pdic_classification(formats_module)
    classification_writer = formats_module.write_pdic

    formats_module.write_pdic = build_write_pdic_capture(formats_module.write_pdic)
    composed_writer = formats_module.write_pdic
    assert composed_writer._original_write_pdic is classification_writer

    # A second classification install is intentionally a no-op. GUI therefore
    # does not need to repeat the core-owned installation after adding baseline
    # capture.
    install_pdic_classification(formats_module)
    assert formats_module.write_pdic is composed_writer

    pdic = tmp_path / "page.pdic"
    automatic = [
        Entry(
            word="",
            x=42,
            y=84,
            confidence=0.97,
            ocr_source="ordinary_page_design",
            issue_type="ORDINARY_PAGE_DESIGN_ENTRY",
        )
    ]
    formats_module.write_pdic(
        pdic,
        automatic,
        1200,
        ("page.png", "@", "@"),
    )

    assert baseline_path_for_pdic(pdic).exists()
    assert classification_sidecar_path(pdic).exists()
    assert pdic.exists()
    assert len(writes) == 1


def test_gui_pdic_io_resolves_current_formats_callables_at_call_time(
    tmp_path: Path, monkeypatch,
):
    import picture_capture.gui_io as gui_io
    from picture_capture import formats

    reads: list[Path] = []
    writes: list[tuple[Path, list[Entry]]] = []

    def current_read(path: Path) -> list[Entry]:
        reads.append(path)
        return [Entry(word="read", x=1, y=2)]

    def current_write(
        path: Path,
        entries: list[Entry],
        _image_width: int,
        _pages: tuple[str, str, str],
    ) -> None:
        writes.append((path, list(entries)))
        path.write_text("pdic\n", encoding="utf-8")

    monkeypatch.setattr(formats, "read_pdic", current_read)
    monkeypatch.setattr(formats, "write_pdic", current_write)

    pdic = tmp_path / "page.pdic"
    assert gui_io.read_pdic(pdic)[0].word == "read"
    assert reads == [pdic]

    automatic = [
        Entry(
            word="",
            x=42,
            y=84,
            confidence=0.97,
            ocr_source="ordinary_page_design",
            issue_type="ORDINARY_PAGE_DESIGN_ENTRY",
        )
    ]
    gui_io.write_pdic(pdic, automatic, 1200, ("page.png", "@", "@"))

    assert baseline_path_for_pdic(pdic).exists()
    assert writes == [(pdic, automatic)]


def test_core_composition_installs_classification_for_non_gui_consumers():
    import picture_capture
    from picture_capture import formats, processing
    from picture_capture.bootstrap.core import build_core_services

    build_core_services()
    package_source = Path(picture_capture.__file__).read_text(encoding="utf-8")
    core_source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "picture_capture"
        / "bootstrap"
        / "core.py"
    ).read_text(encoding="utf-8")

    assert "install_entry_crop_settings()" not in package_source
    assert "install_entry_classification_fields()" not in package_source
    assert "install_pdic_classification(_formats)" not in package_source
    assert "install_entry_crop_settings()" in core_source
    assert "install_entry_classification_fields()" not in core_source
    assert "install_pdic_classification(formats)" in core_source
    assert bool(getattr(formats, "_entry_classification_installed", False))
    assert processing._ordinary_marker_local_crop is processing._core._ordinary_marker_local_crop
    assert (
        processing.ocr_existing_entry_words_from_markers
        is processing._core.ocr_existing_entry_words_from_markers
    )
    assert "install_processing_entry_classification" not in core_source
    assert "entry_classification_runtime" not in core_source
