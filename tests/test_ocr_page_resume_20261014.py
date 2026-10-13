"""Verified OCR batch-resume checkpoints with no false skips."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from picture_capture.formats import write_pdic
from picture_capture.models import AppSettings, Entry
from picture_capture.ocr_page_resume import (
    input_fingerprint, resume_path, validated_resume, write_page_resume,
)
from picture_capture.ui.settings import schema


def _case(tmp_path):
    image = tmp_path / "00001.tif"
    image.write_bytes(b"source-image-version-1")
    pdic = tmp_path / "00001.pdic"
    settings = AppSettings(ocr_resume_completed_pages=True)
    write_pdic(pdic, [Entry(word="alpha", x=15, y=37)], 1200, ("00001", "@", "@"))
    profile = tmp_path / "dictionary_profile.json"
    profile.write_text("profile-v1", encoding="utf-8")
    rules = tmp_path / "headword_filter_rules.txt"
    rules.write_text("rules-v1", encoding="utf-8")
    deps = (profile, rules)
    return image, pdic, settings, deps


def _write(tmp_path, image, pdic, settings, deps):
    return write_page_resume(
        tmp_path, image, pdic, page_index=0, method="paddleocr",
        settings=settings, marker_count=1, dependencies=deps,
    )


def _load(tmp_path, image, pdic, settings, deps):
    return validated_resume(
        tmp_path, image, pdic, page_index=0, method="paddleocr",
        settings=settings, dependencies=deps,
    )


def test_resume_exact_content_same_mode_same_settings_and_pdic(tmp_path):
    image, pdic, settings, deps = _case(tmp_path)
    path = _write(tmp_path, image, pdic, settings, deps)
    assert path == resume_path(tmp_path, image, "paddleocr")
    assert _load(tmp_path, image, pdic, settings, deps) == 1
    assert validated_resume(
        tmp_path, image, pdic, page_index=0, method="combined",
        settings=settings, dependencies=deps,
    ) is None
    assert validated_resume(
        tmp_path, image, pdic, page_index=1, method="paddleocr",
        settings=settings, dependencies=deps,
    ) is None


@pytest.mark.parametrize("mutate", [
    lambda image, pdic, settings, deps: image.write_bytes(b"source-image-version-2"),
    lambda image, pdic, settings, deps: pdic.write_bytes(b"human-corrected-pdic"),
    lambda image, pdic, settings, deps: setattr(settings, "ocr_language", "fra"),
    lambda image, pdic, settings, deps: setattr(settings, "paddle_rec_score_threshold", 0.65),
    lambda image, pdic, settings, deps: deps[0].write_bytes(b"profile-v2"),
    lambda image, pdic, settings, deps: deps[1].write_bytes(b"filter-rules-v2"),
])
def test_resume_never_skips_after_any_essential_input_or_human_change(tmp_path, mutate):
    image, pdic, settings, deps = _case(tmp_path)
    _write(tmp_path, image, pdic, settings, deps)
    mutate(image, pdic, settings, deps)
    assert _load(tmp_path, image, pdic, settings, deps) is None


def test_resume_does_not_trust_modified_image_even_if_stat_size_matches(tmp_path):
    image, pdic, settings, deps = _case(tmp_path)
    _write(tmp_path, image, pdic, settings, deps)
    image.write_bytes(b"source-image-version-2")  # same length, different pixels.
    assert _load(tmp_path, image, pdic, settings, deps) is None


def test_resume_missing_and_corrupt_checkpoint_fails_closed(tmp_path):
    image, pdic, settings, deps = _case(tmp_path)
    assert _load(tmp_path, image, pdic, settings, deps) is None
    p = resume_path(tmp_path, image, "paddleocr")
    p.parent.mkdir(parents=True)
    p.write_text("invalid!", encoding="utf-8")
    assert _load(tmp_path, image, pdic, settings, deps) is None


def test_checkpoint_requires_successful_final_pdic_count(tmp_path):
    image, pdic, settings, deps = _case(tmp_path)
    with pytest.raises(ValueError, match="PDIC marker count"):
        write_page_resume(
            tmp_path, image, pdic, page_index=0, method="paddleocr",
            settings=settings, marker_count=5, dependencies=deps,
        )
    assert _load(tmp_path, image, pdic, settings, deps) is None


def test_project_setting_defaults_off_and_is_explained(tmp_path):
    default = AppSettings()
    assert default.ocr_resume_completed_pages is False
    assert "ocr_resume_completed_pages" in [
        field for _, field in schema.OCR_ADVANCED_CHECKS
    ]
    assert "默认关闭" in schema.CHECK_HELP["ocr_resume_completed_pages"]
    p = tmp_path / "settings.json"
    AppSettings(ocr_resume_completed_pages=True).to_json(p)
    assert AppSettings.from_json(p).ocr_resume_completed_pages is True


def test_force_refresh_bypasses_resume_but_can_write_a_new_checkpoint():
    source = (Path(__file__).resolve().parents[1] /
              "src" / "picture_capture" / "app.py").read_text(encoding="utf-8")
    start = source.index("        def worker(index:", source.index("    def _detect_pages("))
    end = source.index("        def done(", start)
    worker = source[start:end]
    # A user-requested forced refresh must never be satisfied by yesterday's
    # otherwise-identical successful checkpoint.
    assert "and not force_refresh" in worker
    assert "validated_resume(" in worker
    assert "write_page_resume(" in worker
    assert "if not resume_dependencies:" in worker


@pytest.mark.parametrize("module_name", [
    "separator_y_refinement.py",
    "ink_safe_separator.py",
    "ocr_tesseract_runner.py",
    "ocr_lazy_secondary.py",
    "models.py",
    "new_detection_stage.py",
    "future_subpackage/new_detector.py",
])
def test_resume_invalidates_when_detection_source_changes(
    tmp_path, monkeypatch, module_name,
):
    """Even same-length edits to newly introduced modules must force OCR again."""
    from picture_capture import ocr_page_resume as resume_module

    fake_package = tmp_path / "fake_picture_capture"
    fake_package.mkdir()
    (fake_package / "ocr_page_resume.py").write_bytes(b"resume-v1")
    algorithm = fake_package / module_name
    algorithm.parent.mkdir(parents=True, exist_ok=True)
    algorithm.write_bytes(b"version-A")

    # Simulate installing an updated package, with otherwise identical image,
    # settings, Profile, filter rules and saved PDIC.
    monkeypatch.setattr(resume_module, "__file__", str(fake_package / "ocr_page_resume.py"))
    resume_module._algorithm_environment_key.cache_clear()
    try:
        image, pdic, settings, deps = _case(tmp_path)
        _write(tmp_path, image, pdic, settings, deps)
        assert _load(tmp_path, image, pdic, settings, deps) == 1
        algorithm.write_bytes(b"version-B")  # same size; different source bytes
        resume_module._algorithm_environment_key.cache_clear()
        assert _load(tmp_path, image, pdic, settings, deps) is None
    finally:
        resume_module._algorithm_environment_key.cache_clear()


def test_resume_invalidates_after_a_new_detection_module_is_added(
    tmp_path, monkeypatch,
):
    from picture_capture import ocr_page_resume as resume_module

    fake_package = tmp_path / "fake_picture_capture"
    fake_package.mkdir()
    (fake_package / "ocr_page_resume.py").write_bytes(b"resume-v1")
    monkeypatch.setattr(resume_module, "__file__", str(fake_package / "ocr_page_resume.py"))
    resume_module._algorithm_environment_key.cache_clear()
    try:
        image, pdic, settings, deps = _case(tmp_path)
        _write(tmp_path, image, pdic, settings, deps)
        assert _load(tmp_path, image, pdic, settings, deps) == 1
        (fake_package / "brand_new_scoring.py").write_bytes(b"new-logic")
        resume_module._algorithm_environment_key.cache_clear()
        assert _load(tmp_path, image, pdic, settings, deps) is None
    finally:
        resume_module._algorithm_environment_key.cache_clear()


def test_resume_fails_closed_without_readable_detection_sources(
    tmp_path, monkeypatch,
):
    from picture_capture import ocr_page_resume as resume_module

    fake_package = tmp_path / "fake_picture_capture"
    fake_package.mkdir()
    source = fake_package / "ocr_page_resume.py"
    source.write_bytes(b"resume-v1")
    monkeypatch.setattr(resume_module, "__file__", str(source))
    resume_module._algorithm_environment_key.cache_clear()
    try:
        image, pdic, settings, deps = _case(tmp_path)
        _write(tmp_path, image, pdic, settings, deps)
        source.unlink()
        resume_module._algorithm_environment_key.cache_clear()
        assert _load(tmp_path, image, pdic, settings, deps) is None
    finally:
        resume_module._algorithm_environment_key.cache_clear()


def test_resume_invalidates_after_tesseract_binary_replacement(
    tmp_path, monkeypatch,
):
    """A pip-level version check alone cannot detect replaced Tesseract binaries."""
    import subprocess
    from picture_capture import ocr_page_resume as resume_module

    image, pdic, settings, deps = _case(tmp_path)
    executable = tmp_path / "tesseract-for-test"
    executable.write_bytes(b"tess-binary-1")
    settings.paddle_compare_tesseract = True
    settings.ocr_executable = str(executable)
    monkeypatch.setattr(
        resume_module.subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=b"Tesseract 5.0", stderr=b"",
        ),
    )
    resume_module._tesseract_executable_key.cache_clear()
    try:
        _write(tmp_path, image, pdic, settings, deps)
        assert _load(tmp_path, image, pdic, settings, deps) == 1
        executable.write_bytes(b"tess-binary-2")  # same size, binary changed
        resume_module._tesseract_executable_key.cache_clear()
        assert _load(tmp_path, image, pdic, settings, deps) is None
    finally:
        resume_module._tesseract_executable_key.cache_clear()


def test_resume_fails_closed_when_enabled_tesseract_version_unavailable(tmp_path):
    image, pdic, settings, deps = _case(tmp_path)
    settings.paddle_compare_tesseract = True
    settings.ocr_executable = str(tmp_path / "missing-tesseract")
    with pytest.raises(OSError, match="Tesseract"):
        _write(tmp_path, image, pdic, settings, deps)
    assert _load(tmp_path, image, pdic, settings, deps) is None


def test_resume_does_not_skip_when_remote_lens_outputs_are_unversionable(tmp_path):
    image, pdic, settings, deps = _case(tmp_path)
    settings.paddle_enable_lens = True
    settings.paddle_lens_mode = "full"
    with pytest.raises(OSError, match="Lens"):
        _write(tmp_path, image, pdic, settings, deps)
    assert _load(tmp_path, image, pdic, settings, deps) is None
