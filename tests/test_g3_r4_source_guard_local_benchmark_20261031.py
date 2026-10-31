"""Read-only G3 source-guard latency tool: synthetic, redacted, non-E3.

Tests use synthetic BMP/PDIC/SECTION only and never read real scans.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from PIL import Image

from picture_capture.persistence.project_storage import (
    page_sections_read_path_for_image, pdic_path_for_image,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_g3_focused_source_guard.py"


def _cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        text=True, capture_output=True, cwd=ROOT, timeout=50,
    )


def _files(tmp_path):
    page = tmp_path / "private_page.bmp"
    Image.new("RGB", (96, 96), "black").save(page)
    pdic = pdic_path_for_image(page)
    pdic.write_text(
        "PRIVATE_HEADWORD_SENTINEL#4#5#4.17#5.21#private#@#@\n",
        encoding="utf-8",
    )
    section = page_sections_read_path_for_image(page)
    section.parent.mkdir(parents=True, exist_ok=True)
    section.write_text('{"PRIVATE_SECTION_SENTINEL":"A"}', encoding="utf-8")
    return page, pdic, section


def _report_contains_no_raw_source(report, text, tmp_path):
    assert set(report) == {
        "schema", "dataset", "human_acceptance", "rounds", "warmups",
        "image_size_mib", "section_present", "crop_guard_ms",
        "save_guard_ms", "source_unchanged",
    }
    assert report["schema"] == "pc-g3-source-guard-benchmark-v1"
    assert report["human_acceptance"] == "NOT_PERFORMED"
    assert report["source_unchanged"] is True
    for name in ("crop_guard_ms", "save_guard_ms"):
        assert set(report[name]) == {"median", "p95", "max"}
        assert all(isinstance(v, (float, int)) and v >= 0 for v in report[name].values())
    for private in (
        "PRIVATE_HEADWORD_SENTINEL", "PRIVATE_SECTION_SENTINEL",
        "private_page", str(tmp_path), "sha256", "PRIVATE_PATH_SENTINEL",
    ):
        assert private not in text


def test_disposable_synthetic_quick_benchmark_has_no_persistent_output(tmp_path):
    result = _cli("--synthetic", "--side", "96", "--rounds", "2", "--warmups", "0")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    _report_contains_no_raw_source(report, result.stdout, tmp_path)
    assert report["dataset"] == "synthetic"
    assert report["rounds"] == 2 and report["warmups"] == 0
    assert report["section_present"] is True


@pytest.mark.parametrize("section_present", [True, False])
def test_real_page_probe_is_read_only_and_never_prints_private_source(tmp_path, section_present):
    page, pdic, section = _files(tmp_path)
    if not section_present:
        section.unlink()
    files = [page, pdic] + ([section] if section_present else [])
    before = {p: p.read_bytes() for p in files}
    before_stat = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in files}
    result = _cli("--image", page, "--rounds", "3", "--warmups", "1")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    _report_contains_no_raw_source(report, result.stdout + result.stderr, tmp_path)
    assert report["dataset"] == "local-readonly"
    assert report["section_present"] is section_present
    assert all(p.read_bytes() == b for p, b in before.items())
    assert all((p.stat().st_size, p.stat().st_mtime_ns) == s
               for p, s in before_stat.items())
    assert section.exists() is section_present


def test_missing_required_pdic_fails_closed_without_leaking_image_path(tmp_path):
    page, pdic, _section = _files(tmp_path)
    pdic.unlink()
    result = _cli("--image", page, "--rounds", "1", "--warmups", "0")
    assert result.returncode == 2
    assert not result.stdout.strip()
    assert "cannot verify" in result.stderr.lower() or "无法核验" in result.stderr
    assert str(tmp_path) not in result.stderr
    assert page.name not in result.stderr


def test_invalid_rounds_does_not_run_or_write(tmp_path):
    page, pdic, section = _files(tmp_path)
    before = (page.read_bytes(), pdic.read_bytes(), section.read_bytes())
    result = _cli("--image", page, "--rounds", "0")
    assert result.returncode == 2
    assert not result.stdout.strip()
    assert "Invalid benchmark configuration." in result.stderr
    assert (page.read_bytes(), pdic.read_bytes(), section.read_bytes()) == before
    assert page.name not in result.stderr


def test_symlink_image_refused_without_disclosing_target(tmp_path):
    page, _pdic, _section = _files(tmp_path)
    link = tmp_path / "private-link.bmp"
    try:
        link.symlink_to(page)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    result = _cli("--image", link, "--rounds", "1", "--warmups", "0")
    assert result.returncode == 2
    assert "Cannot verify stable source files" in result.stderr
    assert not result.stdout.strip()
    assert str(tmp_path) not in result.stderr
    assert link.name not in result.stderr


def test_interleaved_source_byte_drift_is_refused_before_latency_report(tmp_path):
    # Import the stand-alone tool for deterministic instrumentation; an
    # external writer can change SECTION between crop and save reads.
    page, _pdic, section = _files(tmp_path)
    spec = importlib.util.spec_from_file_location("g3_latency_tool", SCRIPT)
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    original = bench.focused_save_source_witness
    called = [0]

    def external_change(path):
        called[0] += 1
        if called[0] == 1:
            original_bytes = section.read_bytes()
            updated = original_bytes.replace(b'"A"', b'"B"')
            st = section.stat()
            section.write_bytes(updated)
            os.utime(section, ns=(st.st_atime_ns, st.st_mtime_ns))
        return original(path)

    bench.focused_save_source_witness = external_change
    with pytest.raises(bench.SourceChanged):
        bench.measure(page, rounds=2, warmups=0)
