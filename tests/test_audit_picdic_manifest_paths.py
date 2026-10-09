"""Audit: PicDic crop manifests cannot escape the PWW directory."""
from pathlib import Path
import os

import pytest

from picture_capture.picdic import _manifest_crop_path


def test_only_direct_pww_crop_is_accepted(tmp_path):
    pww = tmp_path / "PWW"
    pww.mkdir()
    img = pww / "word.png"
    img.write_bytes(b"crop")
    assert _manifest_crop_path(pww, "word.png") == img
    assert _manifest_crop_path(pww, "WORD.PNG").samefile(img)


@pytest.mark.parametrize("filename", [
    "../outside.png", "sub/child.png", "..", ".", "",
    r"..\outside.png", r"C:\outside.png", r"sub\child.png",
])
def test_manifest_paths_with_directories_are_rejected(tmp_path, filename):
    pww = tmp_path / "PWW"
    pww.mkdir()
    assert _manifest_crop_path(pww, filename) is None


def test_symlink_to_external_file_is_rejected(tmp_path):
    pww = tmp_path / "PWW"
    pww.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"private")
    link = pww / "word.png"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError):
        pytest.skip("Platform does not support creating symlinks")
    assert _manifest_crop_path(pww, "word.png") is None
