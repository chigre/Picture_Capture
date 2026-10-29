"""G1 fail-first: resolve E3 local evidence slots through real project storage.

The current runbook asks operators to guess paths. Managed v2, legacy
case-insensitive PDIC/PPP, and migrated historical SECTION are routed
differently; sampling a non-active copy can create misleading evidence.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from picture_capture.persistence.project_storage import (
    ensure_project_storage,
    page_sections_read_path_for_image,
    pdic_path_for_image,
    ppp_read_path_for_image,
    qt_root,
    simplified_review_path_for_image,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "r3_e3_local_evidence.py"
spec = importlib.util.spec_from_file_location("r3_e3_project_path_contract", SCRIPT)
e3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e3)
SHA = "e" * 40


def _page(tmp_path):
    page = tmp_path / "001.png"
    page.write_bytes(b"test pixels, not licensed images")
    return page


def test_e3_legacy_path_resolver_uses_active_case_insensitive_pdic_ppp(tmp_path):
    page = _page(tmp_path)
    pdic = tmp_path / "001.PDIC"
    ppp = tmp_path / "001.PPP"
    pdic.write_bytes(b"pdic bytes")
    ppp.write_bytes(b"ppp bytes")
    actual = e3.project_paths_for_page(page)
    assert set(actual) == set(e3.LABELS)
    assert actual["image"] == page
    assert actual["pdic"] == pdic_path_for_image(page) == pdic
    assert actual["ppp"] == ppp_read_path_for_image(page) == ppp
    assert actual["section"] == page_sections_read_path_for_image(page)
    assert actual["simplified"] == simplified_review_path_for_image(page)
    assert actual["manual"] == qt_root(tmp_path) / "PaddleOCR" / "001_manual_selection.json"


def test_e3_managed_project_resolver_never_uses_legacy_root_sidecars(tmp_path):
    page = _page(tmp_path)
    (tmp_path / "001.pdic").write_bytes(b"historical root PDIC")
    ensure_project_storage(tmp_path, "e3-test")
    paths = e3.project_paths_for_page(page)
    assert paths["pdic"] == tmp_path / "_PictureCapture" / "data" / "PDIC" / "001.pdic"
    assert paths["ppp"] == tmp_path / "_PictureCapture" / "data" / "PPP" / "001.ppp"
    assert paths["section"] == tmp_path / "_PictureCapture" / "data" / "PageSections" / "001.json"
    assert paths["simplified"] == tmp_path / "_PictureCapture" / "data" / "Simplified" / "001.json"
    assert paths["manual"] == tmp_path / "_PictureCapture" / "QT" / "PaddleOCR" / "001_manual_selection.json"


def test_e3_managed_section_historical_read_fallback_is_captured(tmp_path):
    page = _page(tmp_path)
    ensure_project_storage(tmp_path, "e3-test")
    historical = tmp_path / "_PictureCapture" / "QT" / "PageSections" / "001.json"
    historical.parent.mkdir(parents=True, exist_ok=True)
    historical.write_bytes(b"historical sections")
    assert e3.project_paths_for_page(page)["section"] == historical


def test_e3_capture_page_cli_only_hashes_resolved_paths(tmp_path):
    page = _page(tmp_path)
    pdic = tmp_path / "001.pdic"
    pdic.write_bytes(b"human synthetic PDIC")
    source_bytes = page.read_bytes(), pdic.read_bytes()
    output = tmp_path / "before.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "capture-page", "--page", str(page),
         "--stage", "before", "--revision", SHA, "--output", str(output)],
        text=True, capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["stage"] == "before"
    assert data["manual_acceptance"] == "UNVERIFIED_REQUIRES_HUMAN"
    assert data["artifacts"]["pdic"]["present"]
    assert not data["artifacts"]["manual"]["present"]
    assert (page.read_bytes(), pdic.read_bytes()) == source_bytes
    assert str(page) not in output.read_text(encoding="utf-8")


def test_e3_capture_page_refuses_creating_json_in_missing_sidecar_slot(tmp_path):
    page = _page(tmp_path)
    bad_output = tmp_path / "QT" / "PaddleOCR" / "001_manual_selection.json"
    bad_output.parent.mkdir(parents=True)
    assert not bad_output.exists()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "capture-page", "--page", str(page),
         "--stage", "before", "--revision", SHA, "--output", str(bad_output)],
        text=True, capture_output=True,
    )
    assert result.returncode == 2
    assert not bad_output.exists()


def test_e3_capture_page_fails_closed_when_page_missing(tmp_path):
    page = tmp_path / "missing.png"
    out = tmp_path / "before.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "capture-page", "--page", str(page),
         "--stage", "before", "--revision", SHA, "--output", str(out)],
        text=True, capture_output=True,
    )
    assert result.returncode == 2
    assert not out.exists()
