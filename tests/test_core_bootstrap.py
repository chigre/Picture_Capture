from __future__ import annotations

from pathlib import Path

from picture_capture import formats, processing
from picture_capture.bootstrap.core import CoreServices, build_core_services


ROOT = Path(__file__).resolve().parents[1]


def test_core_bootstrap_returns_shared_process_modules() -> None:
    services = build_core_services()

    assert isinstance(services, CoreServices)
    assert services.formats is formats
    assert services.processing is processing


def test_core_bootstrap_is_idempotent() -> None:
    layout_runtime = processing._ensure_layout_runtime
    first = build_core_services()
    second = build_core_services()

    assert first.formats is second.formats is formats
    assert first.processing is second.processing is processing
    assert processing._ensure_layout_runtime is layout_runtime
    assert bool(getattr(formats, "_entry_classification_installed", False))
    assert processing._ordinary_marker_local_crop is processing._core._ordinary_marker_local_crop
    assert (
        processing.ocr_existing_entry_words_from_markers
        is processing._core.ocr_existing_entry_words_from_markers
    )
    assert not hasattr(processing, "_pc_spawn_layout_runtime_installed")


def test_core_composition_preserves_remaining_import_sensitive_install_order() -> None:
    source = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "core.py"
    ).read_text(encoding="utf-8")

    processing_import = source.index("from .. import processing as processing_module")

    assert "install_live_layout_detector_binding" not in source
    assert "install_character_height_fallback_runtime" not in source
    assert "spawn_layout_runtime" not in source
    assert "install_ordinary_large_head_runtime" not in source
    assert "install_ordinary_large_head_role_guard" not in source
    assert "install_entry_classification_fields" not in source
    # Entry-crop wraps the current AppSettings JSON adapters, so separator-Y
    # must be installed first. Reversing these two would let separator-Y replace
    # the crop serializer instead of being wrapped by it.
    assert source.index("install_separator_y_settings()") < source.index(
        "install_entry_crop_settings()"
    )
    assert source.index("install_pdic_classification(formats)") < processing_import
    assert "install_processing_entry_classification" not in source
    assert "entry_classification_runtime" not in source


def test_core_profile_owns_only_remaining_compatibility_chain() -> None:
    core = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "core.py"
    ).read_text(encoding="utf-8")
    package_init = (
        ROOT / "src" / "picture_capture" / "__init__.py"
    ).read_text(encoding="utf-8")

    installers = (
        "install_separator_y_settings",
        "install_entry_crop_settings",
        "install_pdic_classification",
    )
    for name in installers:
        assert f"{name}(" in core
        assert f"{name}(" not in package_init

    for retired in (
        "install_entry_classification_fields",
        "install_spawn_layout_runtime",
        "install_ordinary_large_head_runtime",
        "install_ordinary_large_head_role_guard",
        "install_processing_entry_classification",
        "entry_classification_runtime",
        "install_layout_illustration_mask_settings",
        "install_layout_illustration_mask_runtime",
    ):
        assert retired not in core
        assert retired not in package_init

    assert "__version__" in package_init
    assert "from ." not in package_init
