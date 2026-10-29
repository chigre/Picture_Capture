"""Read-only Windows E3 local evidence helper: synthetic contract tests."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "r3_e3_local_evidence.py"
spec = importlib.util.spec_from_file_location("e3_local", SCRIPT)
e3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e3)
SHA = "a" * 40


def fixtures(tmp_path):
    paths = {name: tmp_path / (name + ".dat") for name in e3.LABELS}
    paths["image"].write_bytes(b"synthetic source pixels")
    paths["pdic"].write_bytes("甲#10#20#10#20#001#@#@\n".encode("utf-8"))
    return paths


def test_snapshot_redacts_file_names_paths_and_source_words(tmp_path):
    paths = fixtures(tmp_path)
    before = {k: p.read_bytes() for k, p in paths.items() if p.exists()}
    report = e3.capture("before", SHA, paths)
    rendered = json.dumps(report, ensure_ascii=False)
    assert report["manual_acceptance"] == "UNVERIFIED_REQUIRES_HUMAN"
    assert report["artifacts"]["image"]["present"]
    assert not report["artifacts"]["manual"]["present"]
    for private in ("甲", "synthetic source pixels", str(tmp_path)):
        assert private not in rendered
    assert {k: p.read_bytes() for k, p in paths.items() if p.exists()} == before


def test_changed_pdic_and_stable_reopen_never_equal_human_pass(tmp_path):
    paths = fixtures(tmp_path)
    before = e3.capture("before", SHA, paths)
    paths["pdic"].write_bytes("乙#10#20#10#20#001#@#@\n".encode("utf-8"))
    after = e3.capture("after", SHA, paths)
    reopened = e3.capture("reopen", SHA, paths)
    diff = e3.compare(before, after, reopened)
    assert diff["image_hash_stable"] and diff["sidecars_stable_after_reopen"]
    assert diff["artifacts"]["pdic"]["changed_in_operation"]
    assert diff["manual_acceptance"] == "UNVERIFIED_REQUIRES_HUMAN"
    assert "PASS" not in json.dumps(diff)


def test_image_change_is_a_failed_source_integrity_check(tmp_path):
    paths = fixtures(tmp_path)
    before = e3.capture("before", SHA, paths)
    paths["image"].write_bytes(b"changed image")
    after = e3.capture("after", SHA, paths)
    assert not e3.compare(before, after, e3.capture("reopen", SHA, paths))["image_hash_stable"]


def test_post_reopen_sidecar_drift_is_detected(tmp_path):
    paths = fixtures(tmp_path)
    before = e3.capture("before", SHA, paths)
    after = e3.capture("after", SHA, paths)
    paths["pdic"].write_bytes(b"unexpected later write")
    diff = e3.compare(before, after, e3.capture("reopen", SHA, paths))
    assert not diff["sidecars_stable_after_reopen"]


def test_cross_revision_comparison_is_refused(tmp_path):
    paths = fixtures(tmp_path)
    before = e3.capture("before", SHA, paths)
    after = e3.capture("after", "b" * 40, paths)
    with pytest.raises(ValueError, match="one exact"):
        e3.compare(before, after, e3.capture("reopen", SHA, paths))


def test_symlink_is_rejected_not_followed(tmp_path):
    paths = fixtures(tmp_path)
    link = tmp_path / "link.dat"
    try:
        link.symlink_to(paths["pdic"])
    except (OSError, NotImplementedError):
        pytest.skip("OS cannot create symlink")
    paths["manual"] = link
    with pytest.raises(ValueError, match="symlink"):
        e3.capture("before", SHA, paths)


def test_existing_output_is_never_overwritten(tmp_path):
    paths = fixtures(tmp_path)
    report = tmp_path / "private-report.json"
    report.write_bytes(b"existing evidence")
    args = [sys.executable, str(SCRIPT), "capture", "--stage", "before", "--revision", SHA]
    for name, path in paths.items():
        args.extend(["--" + name, str(path)])
    args.extend(["--output", str(report)])
    run = subprocess.run(args, text=True, capture_output=True)
    assert run.returncode == 2
    assert report.read_bytes() == b"existing evidence"


def test_cli_capture_and_compare_without_acceptance_claim(tmp_path):
    paths = fixtures(tmp_path)
    for stage in ("before", "after", "reopen"):
        if stage == "after":
            paths["pdic"].write_bytes(b"new bytes")
        args = [sys.executable, str(SCRIPT), "capture", "--stage", stage, "--revision", SHA]
        for name, path in paths.items():
            args.extend(["--" + name, str(path)])
        args.extend(["--output", str(tmp_path / (stage + ".json"))])
        assert subprocess.run(args, text=True, capture_output=True).returncode == 0
    report = tmp_path / "comparison.json"
    args = [sys.executable, str(SCRIPT), "compare",
            "--before", str(tmp_path / "before.json"),
            "--after", str(tmp_path / "after.json"),
            "--reopen", str(tmp_path / "reopen.json"),
            "--output", str(report)]
    assert subprocess.run(args, text=True, capture_output=True).returncode == 0
    assert json.loads(report.read_text("utf-8"))["manual_acceptance"] == "UNVERIFIED_REQUIRES_HUMAN"
