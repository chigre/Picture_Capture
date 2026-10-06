from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "picture_capture"
OLD = PACKAGE / "windows_gpu_runtime.py"
NEW = PACKAGE / "windows_gpu.py"


def replace_exact(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected marker not found in {path}: {old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    if not OLD.exists():
        raise SystemExit(f"missing source helper: {OLD}")
    if NEW.exists():
        raise SystemExit(f"target helper already exists: {NEW}")

    OLD.rename(NEW)

    references = [
        PACKAGE / "document_unwarping.py",
        PACKAGE / "ocr_channel.py",
        PACKAGE / "layout_detection_legacy.py",
        PACKAGE / "paddle_headwords_core.py",
        ROOT / "scripts" / "verify_ocr_environment.py",
        ROOT / "tests" / "test_ocr_channel_runner_semantics.py",
        ROOT / "tests" / "test_core.py",
        ROOT / "docs" / "ocr-install.md",
        ROOT / "scripts" / "architecture_guard.py",
    ]
    for path in references:
        replace_exact(path, "windows_gpu_runtime", "windows_gpu")

    # Fail closed if any production/script caller still references the retired
    # module path. Tests may intentionally mention the historical filename in
    # assertions, so they are checked separately by pytest rather than here.
    for tree in (PACKAGE, ROOT / "scripts"):
        for path in tree.rglob("*.py"):
            if "windows_gpu_runtime" in path.read_text(encoding="utf-8"):
                raise SystemExit(f"stale Windows GPU module reference remains in {path}")
    install_doc = (ROOT / "docs" / "ocr-install.md").read_text(encoding="utf-8")
    if "windows_gpu_runtime" in install_doc:
        raise SystemExit("stale Windows GPU module reference remains in docs/ocr-install.md")

    test_path = ROOT / "tests" / "test_ocr_channel_runner_semantics.py"
    source = test_path.read_text(encoding="utf-8")
    marker = "\ndef test_legacy_boundary_bridge_no_longer_uses_core_paddle_runner_helpers():\n"
    if marker not in source:
        raise SystemExit("OCR runner insertion marker not found")
    addition = r'''

def test_windows_gpu_helper_rename_preserves_paddle_import_timing():
    root = Path(__file__).resolve().parents[1]
    package = root / "src" / "picture_capture"
    guard = (root / "scripts" / "architecture_guard.py").read_text(encoding="utf-8")
    verify = (root / "scripts" / "verify_ocr_environment.py").read_text(encoding="utf-8")
    install_doc = (root / "docs" / "ocr-install.md").read_text(encoding="utf-8")

    assert not (package / "windows_gpu_runtime.py").exists()
    assert (package / "windows_gpu.py").exists()
    assert "windows_gpu_runtime.py" not in guard
    assert "picture_capture.windows_gpu import configure_windows_nvidia_dlls" in verify
    assert "src/picture_capture/windows_gpu.py" in install_doc

    cases = (
        ("ocr_channel.py", "from paddleocr import PaddleOCR"),
        ("paddle_headwords_core.py", "from paddleocr import PaddleOCR"),
        ("document_unwarping.py", "from paddleocr import DocPreprocessor"),
        ("layout_detection_legacy.py", "from paddleocr import TextDetection"),
    )
    helper_import = "from .windows_gpu import configure_windows_nvidia_dlls"
    helper_call = "configure_windows_nvidia_dlls()"
    for filename, paddle_import in cases:
        text = (package / filename).read_text(encoding="utf-8")
        assert helper_import in text
        assert paddle_import in text
        assert text.index(helper_import) < text.index(helper_call) < text.index(paddle_import)
'''
    test_path.write_text(source.replace(marker, addition + marker), encoding="utf-8")

    print("Phase 5L migration applied")


if __name__ == "__main__":
    main()
