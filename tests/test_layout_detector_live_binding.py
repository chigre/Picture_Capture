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
    core = (root / "src/picture_capture/bootstrap/core.py").read_text(encoding="utf-8")
    package = (root / "src/picture_capture/__init__.py").read_text(encoding="utf-8")

    live_install = core.index("install_live_layout_detector_binding()")
    processing_import = core.index("from .. import processing as processing_module")
    assert live_install < processing_import
    assert "install_live_layout_detector_binding()" not in package
