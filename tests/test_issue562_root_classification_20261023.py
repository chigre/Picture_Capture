"""The remaining roots are explicit contracts; resume belongs to OCR."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re

from picture_capture.ocr import page_resume

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "src" / "picture_capture"


def test_current_inventory_classifies_every_physical_root_once():
    doc = (REPO / "docs/architecture/ROOT_MODULE_CLASSIFICATION_20261023.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([^`]+\.py)` \|", doc, re.MULTILINE)
    assert len(rows) == len(set(rows)) == 15
    assert set(rows) == {p.name for p in ROOT.glob("*.py")}


def test_resume_has_one_physical_owner():
    assert not (ROOT / "ocr_page_resume.py").exists()
    assert importlib.util.find_spec("picture_capture.ocr_page_resume") is None
    assert Path(page_resume.__file__).resolve() == ROOT / "ocr/page_resume.py"
    assert page_resume.validated_resume.__module__ == "picture_capture.ocr.page_resume"


def test_relocated_resume_hashes_exact_package_paths_and_bytes(tmp_path, monkeypatch):
    package = tmp_path / "picture_capture"
    source = package / "ocr/page_resume.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"resume")
    files = {"ocr/page_resume.py": b"resume", "models.py": b"settings",
             "layout/detection.py": b"layout", "refinement/separator_y.py": b"refinement"}
    for name, data in files.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # A sibling outside the package must never enter the algorithm fingerprint.
    (tmp_path / "unrelated.py").write_bytes(b"outside")
    monkeypatch.setattr(page_resume, "__file__", str(source))
    monkeypatch.setattr(page_resume, "package_version", lambda name: "test-version")
    expected = hashlib.sha256(page_resume.ALGORITHM_FINGERPRINT_FORMAT.encode("ascii"))
    for name in sorted(files):
        expected.update(name.encode("utf-8"))
        expected.update(bytes((0,)))
        expected.update(b"present-file\0")
        expected.update(files[name])
    for name in ("paddleocr", "paddlepaddle", "pytesseract", "Pillow", "numpy",
                 "opencv-python", "opencv-python-headless", "chrome-lens-py"):
        expected.update(f"{name}=test-version|".encode("utf-8"))
    page_resume._algorithm_environment_key.cache_clear()
    try:
        assert page_resume._algorithm_environment_key() == expected.hexdigest()
        (package / "layout/detection.py").unlink()
        page_resume._algorithm_environment_key.cache_clear()
        assert page_resume._algorithm_environment_key() != expected.hexdigest()
    finally:
        page_resume._algorithm_environment_key.cache_clear()
