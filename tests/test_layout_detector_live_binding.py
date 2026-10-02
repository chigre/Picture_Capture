from types import SimpleNamespace


def test_policy_detector_binding_tracks_runtime_replacement(monkeypatch):
    import picture_capture.dictionary_page_layout_policy as policy
    import picture_capture.layout_detection as layout_detection

    first = SimpleNamespace(character_height=39)
    second = SimpleNamespace(character_height=59)

    monkeypatch.setattr(
        layout_detection,
        "detect_layout_parameters",
        lambda _image, _settings: first,
    )
    assert policy.detect_layout_parameters(None, None) is first

    # Replacing the detector after policy import must be visible immediately.
    # This is the exact failure mode behind diagnostics such as
    # ``used=39 raw=59 APPLIED``.
    monkeypatch.setattr(
        layout_detection,
        "detect_layout_parameters",
        lambda _image, _settings: second,
    )
    assert policy.detect_layout_parameters(None, None) is second
    assert policy.detect_layout_parameters is not layout_detection.detect_layout_parameters


def test_live_binding_is_installed_before_processing_import():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    package = (root / "src/picture_capture/__init__.py").read_text(encoding="utf-8")

    live_install = package.index("install_live_layout_detector_binding()")
    processing_import = package.index("from . import processing as _processing")
    assert live_install < processing_import
