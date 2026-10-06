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
    first = build_core_services()
    second = build_core_services()

    assert first.formats is second.formats is formats
    assert first.processing is second.processing is processing
    assert bool(getattr(formats, "_entry_classification_installed", False))
    assert bool(getattr(processing, "_entry_classification_runtime_installed", False))
    assert bool(getattr(processing, "_pc_spawn_layout_runtime_installed", False))


def test_core_composition_preserves_import_sensitive_install_order() -> None:
    source = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "core.py"
    ).read_text(encoding="utf-8")

    live_binding = source.index("install_live_layout_detector_binding()")
    large_head = source.index("install_ordinary_large_head_runtime()")
    processing_import = source.index("from .. import processing as processing_module")

    assert live_binding < large_head < processing_import
    assert "install_character_height_fallback_runtime" not in source
    assert source.index("install_pdic_classification(formats)") < processing_import
    assert source.index("install_processing_entry_classification(processing_module)") > processing_import


def test_core_profile_owns_former_package_import_compatibility_chain() -> None:
    core = (
        ROOT / "src" / "picture_capture" / "bootstrap" / "core.py"
    ).read_text(encoding="utf-8")
    package_init = (
        ROOT / "src" / "picture_capture" / "__init__.py"
    ).read_text(encoding="utf-8")

    installers = (
        "install_layout_illustration_mask_settings",
        "install_live_layout_detector_binding",
        "install_ordinary_large_head_runtime",
        "install_ordinary_large_head_role_guard",
        "install_separator_y_settings",
        "install_entry_crop_settings",
        "install_entry_classification_fields",
        "install_pdic_classification",
        "install_processing_entry_classification",
        "install_spawn_layout_runtime",
        "install_layout_illustration_mask_runtime",
    )
    for name in installers:
        assert f"{name}(" in core
        assert f"{name}(" not in package_init

    assert "__version__" in package_init
    assert "from ." not in package_init
